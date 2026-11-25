"""T07 — DEL des places et éclairage blanc, partie Raspberry Pi
(« GestionEclairage » du contrat).

Le RPi décide seul des états des places et des intensités; les STM32 ne
font qu'appliquer :
    - DEL : état logique -> couleur (config.COULEURS_DEL) -> DEL_PLACE_CMD
      (0x340), au STM32 Bas pour les places 1-7, au Haut pour 8-14;
    - éclairage : intensité 0-255 -> ECLAIRAGE_CMD (0x130) avec
      rouge = vert = bleu, au Bas (niveau 0), au Haut (1) ou à la Borne (2).

Chaque commande attend un accusé (0x341/0x342, 0x350 à 0x352) dans
config.DELAI_ACCUSE_S. Sans accusé : une retransmission, puis une anomalie
NON critique (un éclairage en panne ne bloque pas le stationnement).

Les STM32 gardent les consignes en RAM seulement : après le redémarrage
d'un STM32 (vu dans son heartbeat), toutes ses consignes sont renvoyées.

Tout est non bloquant : mettre_a_jour() est appelée à chaque tour.
"""

from src import config
from src.hardware import protocole_can as proto
from src.horloge import Horloge
from src.models.erreurs import ParametreInvalide

# Carte qui porte les DEL d'un niveau de places, et ID de son accusé
DEL_CARTES = {1: ("BAS", proto.DEL_BAS_ETAT), 2: ("HAUT", proto.DEL_HAUT_ETAT)}

# Carte qui porte l'éclairage d'un niveau, et ID de son accusé
ECLAIRAGE_CARTES = {
    0: ("BAS", proto.ECLAIRAGE_BAS_ETAT),
    1: ("HAUT", proto.ECLAIRAGE_HAUT_ETAT),
    2: ("BORNE", proto.ECLAIRAGE_BORNE_ETAT),
}

# Heartbeat -> carte
HEARTBEATS = {
    proto.HEARTBEAT_HAUT: "HAUT",
    proto.HEARTBEAT_BAS: "BAS",
    proto.HEARTBEAT_BORNE: "BORNE",
}


def carte_de_place(place: str) -> str:
    """Carte qui commande la DEL d'une place : "E1.x" -> BAS, "E2.x" -> HAUT."""
    return DEL_CARTES[config.PLACES[place]["niveau"]][0]


class GestionEclairage:
    """Commande les 14 DEL d'état et les trois éclairages blancs."""

    def __init__(self, can, stationnement=None, horloge: Horloge | None = None, journal=None):
        self.can = can                        # CanManager
        self.stationnement = stationnement    # modèle partagé (peut être None)
        self.horloge = horloge or Horloge()
        self.journal = journal or (lambda texte: None)

        # Dernières consignes demandées (renvoyées après un redémarrage)
        self.etats_places = {}     # "E1.3" -> "OCCUPE"
        self.intensites = {}       # niveau -> 0-255

        # Résultat de la dernière commande de chaque sortie :
        # True = appliquée, False = refusée ou sans accusé, None = en attente
        self.confirmations = {}    # "E1.3" ou "niveau 0" -> True/False/None

        self._attentes = {}        # clé -> commande qui attend son accusé
        self._cartes_en_anomalie = set()

        # Suivi des heartbeats de chaque STM32
        self._suivi = {
            carte: {"vu": None, "etat": None, "tout_renvoyer": False}
            for carte in ("HAUT", "BAS", "BORNE")
        }

    # ------------------------------------------------------------------
    # Interface du contrat
    # ------------------------------------------------------------------

    def definir_etat_place(self, place: str, etat: str) -> None:
        """Allume la DEL d'une place selon son état logique.

        Lève ParametreInvalide si la place ou l'état n'existe pas.
        """
        if place not in config.PLACES:
            raise ParametreInvalide(f"Place {place!r} invalide")

        if etat not in config.COULEURS_DEL:
            raise ParametreInvalide(f"État {etat!r} invalide")

        rouge, vert, bleu, mode = config.COULEURS_DEL[etat]
        numero = config.PLACES[place]["numero"]
        carte, accuse_id = DEL_CARTES[config.PLACES[place]["niveau"]]

        self.etats_places[place] = etat
        self._envoyer(place, carte, proto.DEL_PLACE_CMD,
                      [numero, rouge, vert, bleu, mode], accuse_id, numero)

    def definir_luminosite_niveau(self, niveau: int, intensite: int) -> None:
        """Règle le blanc d'un niveau (0 = éteint, 255 = maximum).

        Lève ParametreInvalide si le niveau ou l'intensité est invalide.
        """
        if niveau not in ECLAIRAGE_CARTES:
            raise ParametreInvalide(f"Niveau {niveau!r} invalide (0, 1 ou 2)")

        # bool est refusé : True serait accepté comme 1
        if type(intensite) is not int or not 0 <= intensite <= 255:
            raise ParametreInvalide(f"Intensité {intensite!r} invalide (0 à 255)")

        carte, accuse_id = ECLAIRAGE_CARTES[niveau]

        self.intensites[niveau] = intensite
        self._envoyer(f"niveau {niveau}", carte, proto.ECLAIRAGE_CMD,
                      [niveau, intensite, intensite, intensite], accuse_id, niveau)

    def appliquer_etats_complets(self, etats: dict) -> None:
        """Commande plusieurs places d'un coup : {"E1.1": "LIBRE", ...}."""
        for place, etat in etats.items():
            self.definir_etat_place(place, etat)

    def traiter_retour_can(self, can_id: int, donnees: bytes) -> None:
        """Traite un accusé de T07 ou un heartbeat de STM32."""
        if can_id in HEARTBEATS and len(donnees) >= 2:
            self._traiter_heartbeat(HEARTBEATS[can_id], donnees[1])
            return

        if len(donnees) < 3:
            return

        # Accusé : séquence, place ou niveau, résultat
        for cle, attente in list(self._attentes.items()):
            correspond = (
                attente["accuse_id"] == can_id
                and attente["sequence"] == donnees[0]
                and attente["reference"] == donnees[1]
            )

            if not correspond:
                continue

            del self._attentes[cle]
            self._cartes_en_anomalie.discard(attente["carte"])   # la carte répond

            if donnees[2] == proto.ACCUSE_APPLIQUE:
                self.confirmations[cle] = True
            else:
                self.confirmations[cle] = False
                self._signaler(attente, "REFUSEE", f"{cle} : commande refusée par le STM32 {attente['carte']}")

            return

    # ------------------------------------------------------------------
    # Boucle non bloquante
    # ------------------------------------------------------------------

    def mettre_a_jour(self) -> None:
        """À appeler à chaque tour de la boucle du service."""
        maintenant = self.horloge.monotone()

        # 1) Suivre les états logiques décidés par T03, T04, T11 et T12
        if self.stationnement is not None:
            for place, etat in self.stationnement.etats_places.items():
                if self.etats_places.get(place) != etat:
                    self.definir_etat_place(place, etat)

        # 2) Commandes sans accusé : retransmettre une fois, puis anomalie
        for cle, attente in list(self._attentes.items()):
            if maintenant < attente["echeance"]:
                continue

            if attente["essais"] < config.ESSAIS_ENVOI_T07:
                attente["essais"] += 1
                attente["echeance"] = maintenant + config.DELAI_ACCUSE_S
                self.can.send(attente["can_id"], attente["donnees"])
            else:
                del self._attentes[cle]
                self.confirmations[cle] = False
                self._signaler(attente, "SANS_ACCUSE",
                               f"{cle} : aucun accusé du STM32 {attente['carte']}")

        # 3) Heartbeat absent depuis trop longtemps : STM32 considéré perdu
        for carte, suivi in self._suivi.items():
            if suivi["vu"] is not None and maintenant - suivi["vu"] > config.DELAI_PERTE_HEARTBEAT_S:
                suivi["vu"] = None
                suivi["tout_renvoyer"] = True       # à son retour, il a pu redémarrer
                self.journal(f"T07 : heartbeat du STM32 {carte} perdu")

    # ------------------------------------------------------------------
    # Redémarrage d'un STM32
    # ------------------------------------------------------------------

    def renvoyer_consignes(self, carte: str, seulement_echouees: bool = False) -> None:
        """Renvoie les consignes d'une carte (DEL et éclairage).

        seulement_echouees = True : seulement celles restées sans accusé
        ou refusées (confirmation à False).
        """
        for place, etat in list(self.etats_places.items()):
            if carte_de_place(place) == carte and self._a_renvoyer(place, seulement_echouees):
                self.definir_etat_place(place, etat)

        for niveau, intensite in list(self.intensites.items()):
            cle = f"niveau {niveau}"

            if ECLAIRAGE_CARTES[niveau][0] == carte and self._a_renvoyer(cle, seulement_echouees):
                self.definir_luminosite_niveau(niveau, intensite)

    def _a_renvoyer(self, cle: str, seulement_echouees: bool) -> bool:
        if not seulement_echouees:
            return True

        return self.confirmations.get(cle) is False

    def _traiter_heartbeat(self, carte: str, etat: int):
        suivi = self._suivi[carte]
        premiere_fois = suivi["vu"] is None and suivi["etat"] is None

        # Passage à « initialisation » = le STM32 vient de redémarrer
        if etat == proto.HEARTBEAT_INITIALISATION and suivi["etat"] != proto.HEARTBEAT_INITIALISATION:
            suivi["tout_renvoyer"] = True
            self.journal(f"T07 : redémarrage du STM32 {carte} détecté")

        suivi["vu"] = self.horloge.monotone()
        suivi["etat"] = etat

        # On attend que la carte soit sortie de l'initialisation
        if etat == proto.HEARTBEAT_INITIALISATION:
            return

        if suivi["tout_renvoyer"]:
            suivi["tout_renvoyer"] = False
            self.journal(f"T07 : consignes renvoyées au STM32 {carte}")
            self.renvoyer_consignes(carte)

        elif premiere_fois:
            # Carte vue pour la première fois (ex. allumée après le RPi) :
            # renvoyer ce qu'elle a manqué
            self.renvoyer_consignes(carte, seulement_echouees=True)

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _envoyer(self, cle, carte, can_id, valeurs, accuse_id, reference):
        """Envoie une commande et note qu'on attend son accusé."""
        sequence = self.can.next_sequence()
        donnees = [sequence] + valeurs

        # Une nouvelle commande remplace celle qui attendait encore
        self._attentes[cle] = {
            "carte": carte,
            "can_id": can_id,
            "donnees": donnees,
            "accuse_id": accuse_id,
            "sequence": sequence,
            "reference": reference,
            "essais": 1,
            "echeance": self.horloge.monotone() + config.DELAI_ACCUSE_S,
        }
        self.confirmations[cle] = None

        self.can.send(can_id, donnees)

    def _signaler(self, attente: dict, suffixe: str, message: str):
        """Anomalie non critique, une seule par carte tant qu'elle ne répond pas."""
        self.journal(f"T07 : {message}")

        if self.stationnement is None or attente["carte"] in self._cartes_en_anomalie:
            return

        self._cartes_en_anomalie.add(attente["carte"])
        prefixe = "DEL" if attente["can_id"] == proto.DEL_PLACE_CMD else "ECLAIRAGE"
        self.stationnement.ajouter_anomalie("T07", f"{prefixe}_{suffixe}", message, critique=False)
