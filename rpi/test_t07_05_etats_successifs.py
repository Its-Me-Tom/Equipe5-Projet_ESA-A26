"""T07-05 — États successifs.

Essai (énoncé T07) : une place passe par tous les états :
    disponible (vert) -> réservé (bleu) -> occupé (rouge)
    -> maintenance (orange) -> défaut (jaune clignotant 1 Hz) -> disponible.

Ce que le terminal montre : pour chaque état, la trame 0x340 (place,
R, V, B, mode), l'accusé, et la couleur appliquée.

Matériel minimal
    MATERIEL_REEL = False : aucun (faux STM32).
    MATERIEL_REEL = True  : HAT CAN + le STM32 qui porte la DEL de PLACE
                            (E1.x -> STM32 Bas, E2.x -> STM32 Haut).

Exécution : python3 test_t07_05_etats_successifs.py
"""


import os
import sys
import time

from src import config
from src.hardware import protocole_can as proto
from src.hardware.can_manager import CanManager
from src.horloge import Horloge
from src.models.t07_gestion_eclairage import GestionEclairage
from src.simulation.faux_stm32 import FauxStm32


# ----------------------------------------------------------------------
# RÉGLAGES DU TEST (modifiez ici)
# ----------------------------------------------------------------------
MATERIEL_REEL = True       # True = vrai bus can0 + STM32 de la place | False = simulation
PLACE = "E1.1"
DUREE_OBSERVATION_S = 3    # mode réel : temps pour regarder chaque couleur

# lancer_tous_les_tests.py force la simulation (ESA_SIMULATION=1) sans modifier les réglages
if os.environ.get("ESA_SIMULATION") == "1":
    MATERIEL_REEL = False


# ======================================================================
# OUTILS DU TEST — recopiés dans chaque test pour qu'il soit autonome :
# ce fichier n'a besoin d'aucun autre fichier de test, seulement de src/.
# Rien n'est écrit sur le disque : tout s'affiche dans le terminal.
# ======================================================================
# ---------- Affichage et vérifications : tout est écrit dans le terminal ----------
_VERIFICATIONS = []                     # (description, réussie)
_DEBUT = time.monotonic()
_EN_ATTENTE = []                        # lignes venues d'un autre thread (ex. MQTT), affichées dans l'ordre


def afficher_en_attente():
    """Affiche les lignes produites par les autres threads (réseau MQTT)."""
    while _EN_ATTENTE:
        print(_EN_ATTENTE.pop(0), flush=True)


def titre(nom: str, mode: str):
    """En-tête du test."""
    print("\n" + "=" * 78)
    print(nom)
    print(f"Mode : {mode}")
    print("=" * 78)


def etape(texte: str):
    """Début d'une étape de l'essai."""
    afficher_en_attente()
    print(f"\n--- {texte} " + "-" * max(3, 72 - len(texte)))


def info(texte: str = ""):
    """Donnée ou explication affichée pendant l'essai."""
    afficher_en_attente()
    print(f"    {texte}", flush=True)


def verifier(description: str, obtenu, attendu) -> bool:
    """Compare la valeur obtenue à la valeur attendue et affiche le verdict."""
    reussie = obtenu == attendu
    _VERIFICATIONS.append((description, reussie))
    afficher_en_attente()

    if reussie:
        valeur = repr(obtenu)
        separateur = "\n            " if len(valeur) + len(description) > 90 else " "
        print(f"  [OK]    {description} :{separateur}{valeur}")
    else:
        print(f"  [ÉCHEC] {description}")
        print(f"            attendu : {attendu!r}")
        print(f"            obtenu  : {obtenu!r}")

    return reussie


def consigne(texte: str):
    """Action à faire par l'opérateur (mode réel)."""
    afficher_en_attente()
    print(f"\n>>> {texte}", flush=True)


def confirmer(question: str) -> bool:
    """Demande à l'opérateur ce qu'il voit (mode réel)."""
    reponse = input(f"\n>>> {question} (o/n) : ").strip().lower()
    return verifier(f"Observation : {question}", reponse, "o")


def erreur_de(fonction, *arguments, **options) -> str:
    """Nom de l'exception levée par l'appel (affichée), ou "aucune"."""
    try:
        fonction(*arguments, **options)
    except Exception as erreur:
        info(f"exception levée : {type(erreur).__name__} — {erreur}")
        return type(erreur).__name__

    return "aucune"


def tableau(entetes: list, lignes: list):
    """Affiche un petit tableau aligné."""
    lignes = [[("" if valeur is None else str(valeur)) for valeur in ligne] for ligne in lignes]
    largeurs = [max(len(str(texte)) for texte in colonne) for colonne in zip(entetes, *lignes)]
    print("    " + "  ".join(str(texte).ljust(largeur) for texte, largeur in zip(entetes, largeurs)))
    print("    " + "  ".join("-" * largeur for largeur in largeurs))

    for ligne in lignes:
        print("    " + "  ".join(texte.ljust(largeur) for texte, largeur in zip(ligne, largeurs)))

    if not lignes:
        print("    (aucune ligne)")


def arreter_test(message: str):
    """Arrête le test quand le matériel demandé ne répond pas."""
    print(f"\nTEST IMPOSSIBLE : {message}")
    print("RÉSULTAT : NON EXÉCUTÉ (matériel absent ou mal configuré)")
    sys.exit(2)


def terminer():
    """Affiche le bilan et termine (code 0 = réussi, 1 = échoué)."""
    echecs = [description for description, reussie in _VERIFICATIONS if not reussie]
    afficher_en_attente()
    print("\n" + "=" * 78)

    if echecs:
        print(f"RÉSULTAT : ÉCHOUÉ — {len(echecs)} vérification(s) en échec sur {len(_VERIFICATIONS)}")
        for description in echecs:
            print(f"   - {description}")
    else:
        print(f"RÉSULTAT : RÉUSSI — {len(_VERIFICATIONS)}/{len(_VERIFICATIONS)} vérifications "
              f"({time.monotonic() - _DEBUT:.1f} s)")

    print("=" * 78)
    sys.exit(1 if echecs else 0)


def _sur_exception(type_erreur, erreur, trace):
    sys.__excepthook__(type_erreur, erreur, trace)
    print("RÉSULTAT : ERREUR — le test s'est arrêté sur l'exception ci-dessus")


sys.excepthook = _sur_exception


# ---------- Horloge du test ----------
class HorlogeTest(Horloge):
    """Horloge qu'on peut faire avancer d'un coup (avancer(600) = 10 min).

    temps_reel = False : le temps n'avance QUE par avancer() (simulation :
                         60 s de délai passent instantanément).
    temps_reel = True  : le temps avance aussi tout seul (vrai matériel).
    """

    def __init__(self, temps_reel: bool = False):
        self.temps_reel = temps_reel
        self._depart = time.monotonic()
        self._decalage = 0.0

    def _ecoule(self) -> float:
        reel = time.monotonic() - self._depart if self.temps_reel else 0.0
        return reel + self._decalage

    def maintenant(self) -> float:
        return 1_800_000_000.0 + self._ecoule()

    def monotone(self) -> float:
        return 1000.0 + self._ecoule()

    def avancer(self, secondes: float):
        self._decalage += secondes


def un_tour_de_temps(horloge: HorlogeTest):
    """Fait passer une période de boucle (vraie attente en temps réel)."""
    if horloge.temps_reel:
        time.sleep(config.PERIODE_BOUCLE_S)
    else:
        horloge.avancer(config.PERIODE_BOUCLE_S)


# ---------- Décodage lisible des trames CAN (protocole ESA v1.6) ----------
NOMS_CAN = {
    0x001: "ARRET_HAUT", 0x002: "ARRET_BAS", 0x003: "ARRET_BORNE", 0x004: "ARRET_RPI",
    0x010: "DEFAUT_HAUT", 0x011: "DEFAUT_BAS", 0x012: "DEFAUT_BORNE",
    0x040: "HEARTBEAT_RPI", 0x041: "HEARTBEAT_HAUT", 0x042: "HEARTBEAT_BAS", 0x043: "HEARTBEAT_BORNE",
    0x050: "REARMEMENT_CMD", 0x051: "REARMEMENT_HAUT", 0x052: "REARMEMENT_BAS", 0x053: "REARMEMENT_BORNE",
    0x080: "SYNCHRO_CMD",
    0x100: "ELEVATION_CMD", 0x110: "ROTATION_CMD", 0x120: "BRAS_CMD", 0x130: "ECLAIRAGE_CMD",
    0x200: "ELEVATION_ETAT", 0x210: "ROTATION_ETAT", 0x220: "BRAS_ETAT",
    0x300: "IR_BAS_CHANGEMENT", 0x301: "IR_BAS_COMPLET", 0x302: "IR_LECTURE_CMD",
    0x310: "IR_ENTREE_CHANGEMENT", 0x311: "IR_ENTREE_COMPLET",
    0x340: "DEL_PLACE_CMD", 0x341: "DEL_BAS_ETAT", 0x342: "DEL_HAUT_ETAT",
    0x350: "ECLAIRAGE_BAS_ETAT", 0x351: "ECLAIRAGE_HAUT_ETAT", 0x352: "ECLAIRAGE_BORNE_ETAT",
}
ACTIONS_CAN = {
    0x100: {0: "arrêt", 1: "déplacer", 3: "soulever", 4: "abaisser"},
    0x110: {0: "arrêt", 1: "déplacer"},
    0x120: {0: "arrêt", 1: "déployer", 2: "rétracter"},
}
RESULTATS_CAN = {0: "refusé", 1: "accepté", 2: "terminé", 3: "interrompu", 4: "défaut"}
ETATS_HEARTBEAT = {0: "initialisation", 1: "prêt", 2: "occupé", 3: "verrouillé", 4: "défaut"}
HEARTBEATS = (0x040, 0x041, 0x042, 0x043)


def decoder_trame(can_id: int, donnees) -> str:
    """Une trame CAN en texte : identifiant, nom, octets bruts et champs."""
    d = list(donnees)
    brut = " ".join(f"{octet:02X}" for octet in d)

    try:
        if can_id in ACTIONS_CAN:
            cible = {0x100: "niveau", 0x110: "angle", 0x120: "réservé"}[can_id]
            champs = f"séq={d[0]} action={ACTIONS_CAN[can_id].get(d[1], d[1])} {cible}={d[2]}"
        elif can_id in (0x200, 0x210, 0x220):
            champs = f"séq={d[0]} résultat={RESULTATS_CAN.get(d[1], d[1])} position={d[2]} défaut={d[3]}"
        elif can_id == 0x340:
            mode = "clignotant 1 Hz" if d[5] else "fixe"
            champs = f"séq={d[0]} place={d[1]} R={d[2]} V={d[3]} B={d[4]} mode={mode}"
        elif can_id in (0x341, 0x342):
            champs = f"séq={d[0]} place={d[1]} résultat={'appliqué' if d[2] == 1 else 'REFUSÉ'}"
        elif can_id == 0x130:
            champs = f"séq={d[0]} niveau={d[1]} R={d[2]} V={d[3]} B={d[4]}"
        elif can_id in (0x350, 0x351, 0x352):
            champs = f"séq={d[0]} niveau={d[1]} résultat={'appliqué' if d[2] == 1 else 'REFUSÉ'}"
        elif can_id in (0x001, 0x002, 0x003, 0x004):
            champs = f"motif={d[0]} source={d[1]} détail={d[2]}"
        elif can_id in (0x010, 0x011, 0x012):
            champs = f"source={d[0]} code={d[1]} gravité={d[2]} détail={d[3]}"
        elif can_id in HEARTBEATS:
            champs = f"compteur={d[0]} état={ETATS_HEARTBEAT.get(d[1], d[1])}"
        elif can_id == 0x050:
            champs = f"séq={d[0]} action={d[1]}"
        elif can_id in (0x051, 0x052, 0x053):
            champs = f"séq={d[0]} résultat={'accepté' if d[1] == 1 else 'REFUSÉ'} motif={d[2]}"
        elif can_id == 0x080:
            champs = f"cible={ {1: 'capteurs', 2: 'moteurs', 3: 'tous'}.get(d[0], d[0]) }"
        elif can_id == 0x300:
            champs = f"IR place {d[0]} -> {'présent' if d[1] else 'absent'} compteur={d[2]}"
        elif can_id == 0x301:
            masque = d[0] | (d[1] << 8)
            presents = [indice for indice in range(14) if masque & (1 << indice)]
            champs = f"IR présents={presents} compteur={d[2]} valide={d[3] == 1}"
        elif can_id == 0x310:
            champs = f"IR rampe -> {'présent' if d[1] else 'absent'} compteur={d[2]}"
        elif can_id == 0x311:
            champs = f"IR rampe={'présent' if d[0] else 'absent'} compteur={d[1]} valide={d[2] == 1}"
        else:
            champs = ""
    except IndexError:
        champs = "(trame trop courte)"

    return f"0x{can_id:03X} {NOMS_CAN.get(can_id, '?'):<20} [{brut}]  {champs}"


# ---------- Banc CAN seul (T07) : bus + faux STM32, avec trace des trames ----------
NOMS_COULEURS = {
    (0, 255, 0, 0): "vert", (0, 0, 255, 0): "bleu", (255, 0, 0, 0): "rouge",
    (255, 165, 0, 0): "orange", (255, 255, 0, 1): "jaune clignotant", (0, 0, 0, 0): "éteinte",
}


def nom_couleur(couleur) -> str:
    couleur = tuple(couleur)
    return NOMS_COULEURS.get(couleur, "R={} V={} B={} mode={}".format(*couleur))


class BancCan:
    """Bus CAN + faux STM32, rien d'autre. Chaque trame est affichée.

    fonctions_reelles = None : bus virtuel, tout est simulé.
    fonctions_reelles = {"del_niveau1"} : vrai bus can0; le vrai STM32
        fournit ces fonctions, le faux STM32 simule les autres.
    """

    def __init__(self, fonctions_reelles=None, trace: bool = True):
        reel = fonctions_reelles is not None
        self.trace = trace
        self.horloge = HorlogeTest(temps_reel=reel)
        self.can = CanManager(simulate=not reel)

        if not self.can.connect():
            arreter_test(f"Bus CAN inaccessible : {self.can.last_error}")

        info(f"Bus CAN ouvert : {'can0 (réel)' if reel else 'bus virtuel (simulation)'}")
        self.faux_stm32 = FauxStm32(self.horloge, bus_reel=reel, fonctions_reelles=fonctions_reelles or ())
        self.envoyees = []      # (identifiant, données) envoyées par le RPi
        self.recues = []        # (identifiant, données) reçues des STM32
        self.receveurs = []     # fonctions(message) appelées pour chaque trame reçue
        self.taches = []        # fonctions appelées à chaque tour

        envoyer = self.can.send

        def envoyer_et_afficher(can_id, donnees):
            resultat = envoyer(can_id, donnees)
            self.envoyees.append((can_id, list(donnees)))
            if self.trace:
                self._afficher("RPi -> CAN", can_id, donnees)
            return resultat

        self.can.send = envoyer_et_afficher

    def _afficher(self, sens: str, can_id: int, donnees):
        if can_id not in HEARTBEATS:
            temps = self.horloge.monotone() - 1000.0
            print(f"      [t={temps:7.2f} s] {sens} {decoder_trame(can_id, donnees)}")

    def executer(self, secondes: float, jusqua=None) -> bool:
        """Fait tourner le bus pendant « secondes » (ou jusqu'à la condition)."""
        for _ in range(max(1, int(secondes / config.PERIODE_BOUCLE_S))):
            self.faux_stm32.mettre_a_jour()
            message = self.can.receive()

            while message is not None:
                self.recues.append((message.arbitration_id, list(message.data)))
                if self.trace:
                    self._afficher("CAN -> RPi", message.arbitration_id, message.data)
                for receveur in self.receveurs:
                    receveur(message)
                message = self.can.receive()

            for tache in self.taches:
                tache()

            un_tour_de_temps(self.horloge)

            if jusqua is not None and jusqua():
                return True

        return False

    def trames(self, can_id: int) -> list:
        """Données des trames de cet identifiant envoyées par le RPi."""
        return [donnees for identifiant, donnees in self.envoyees if identifiant == can_id]

    def afficher_del(self, numeros=range(1, 15)):
        """Couleur que chaque DEL a reçue du point de vue du faux STM32."""
        lignes = []
        for numero in numeros:
            couleur = self.faux_stm32.del_places.get(numero)
            lignes.append([numero, "(aucune consigne)" if couleur is None else nom_couleur(couleur)])
        tableau(["DEL n°", "couleur appliquée (faux STM32)"], lignes)

    def fermer(self):
        self.can.disconnect()
        self.faux_stm32.fermer()


# ======================================================================
# ESSAI
# ======================================================================
carte = "Bas" if config.PLACES[PLACE]["niveau"] == 1 else "Haut"
titre(f"T07-05 — États successifs de la place {PLACE}",
      f"MATÉRIEL RÉEL : can0 + STM32 {carte}" if MATERIEL_REEL else "SIMULATION : faux STM32 sur bus virtuel")

fonction = "del_niveau1" if config.PLACES[PLACE]["niveau"] == 1 else "del_niveau2"
banc = BancCan({fonction} if MATERIEL_REEL else None)
eclairage = GestionEclairage(banc.can, horloge=banc.horloge)
banc.receveurs.append(lambda message: eclairage.traiter_retour_can(message.arbitration_id, message.data))
banc.taches.append(eclairage.mettre_a_jour)
numero = config.PLACES[PLACE]["numero"]
info(f"{PLACE} = DEL n° {numero} sur le STM32 {carte}")

# état -> (rouge, vert, bleu, mode) attendus dans la trame 0x340
sequence = [
    ("LIBRE", (0, 255, 0, 0), "vert"),
    ("RESERVE", (0, 0, 255, 0), "bleu"),
    ("OCCUPE", (255, 0, 0, 0), "rouge"),
    ("MAINTENANCE", (255, 165, 0, 0), "orange"),
    ("DEFAUT", (255, 255, 0, 1), "jaune clignotant (1 Hz)"),
    ("LIBRE", (0, 255, 0, 0), "vert"),
]
info(f"Couleurs configurées (config.COULEURS_DEL) : {config.COULEURS_DEL}")

for etat, couleur, nom in sequence:
    etape(f"{etat} -> {nom}")
    eclairage.definir_etat_place(PLACE, etat)
    banc.executer(2, jusqua=lambda: eclairage.confirmations.get(PLACE) is True)

    trame = banc.trames(proto.DEL_PLACE_CMD)[-1]
    verifier("Trame 0x340 (place, R, V, B, mode)", tuple(trame[1:6]), (numero,) + couleur)
    verifier("Accusé « appliqué »", eclairage.confirmations[PLACE], True)

    if MATERIEL_REEL:
        consigne(f"{PLACE} doit être {nom} ({DUREE_OBSERVATION_S} s)")
        banc.executer(DUREE_OBSERVATION_S)
        confirmer(f"{PLACE} était bien {nom} ?")
    else:
        verifier("Couleur appliquée par le faux STM32", nom_couleur(banc.faux_stm32.del_places[numero]),
                 nom_couleur(couleur))

etape("Bilan")
verifier("Six commandes envoyées, une par état", len(banc.trames(proto.DEL_PLACE_CMD)), 6)
verifier("État courant de la place", eclairage.etats_places[PLACE], "LIBRE")

banc.fermer()
terminer()
