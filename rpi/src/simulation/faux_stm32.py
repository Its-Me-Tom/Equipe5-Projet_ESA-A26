"""Faux STM32 (Haut, Bas et Borne) pour tester avec le minimum de matériel.

Ce fichier ne fait partie d'aucune tâche : c'est un outil d'essai. Il est
branché sur le bus CAN (virtuel ou réel) et répond comme le feraient les
vrais STM32.

Il simule FONCTION PAR FONCTION. On lui dit quelles fonctions sont
fournies par un vrai STM32 (fonctions_reelles) et il simule toutes les
autres. Exemple : pour essayer le vrai détecteur IR de la rampe (STM32
Haut) sans moteurs, fonctions_reelles = {"ir_rampe"} : le faux STM32
répond aux commandes moteur, le vrai Haut fournit seulement l'IR.

Attention : une fonction simulée ne doit pas être active aussi sur le vrai
STM32, sinon il y aura deux réponses à la même commande.

Les attributs silencieux, refuser_prochaine, defaut_prochain,
rearmement_refuse et del_refusee permettent aux tests de provoquer des
défauts.
"""

import can

from src import config
from src.hardware import protocole_can as proto

# Fonctions de chaque STM32
FONCTIONS_HAUT = {"moteurs", "ir_rampe", "del_niveau2", "eclairage_niveau1", "systeme_haut"}
FONCTIONS_BAS = {"ir_places", "del_niveau1", "eclairage_niveau0", "systeme_bas"}
FONCTIONS_BORNE = {"eclairage_niveau2", "systeme_borne"}
TOUTES_LES_FONCTIONS = FONCTIONS_HAUT | FONCTIONS_BAS | FONCTIONS_BORNE

# « systeme_xxx » = heartbeat, réponse au réarmement et verrouillage de la carte
CARTES = {"HAUT": FONCTIONS_HAUT, "BAS": FONCTIONS_BAS, "BORNE": FONCTIONS_BORNE}

HEARTBEATS = {"HAUT": proto.HEARTBEAT_HAUT, "BAS": proto.HEARTBEAT_BAS,
              "BORNE": proto.HEARTBEAT_BORNE}
REARMEMENTS = {"HAUT": proto.REARMEMENT_HAUT, "BAS": proto.REARMEMENT_BAS,
               "BORNE": proto.REARMEMENT_BORNE}

# Éclairage : niveau -> (fonction, carte, ID de l'accusé)
ECLAIRAGES = {
    0: ("eclairage_niveau0", "BAS", proto.ECLAIRAGE_BAS_ETAT),
    1: ("eclairage_niveau1", "HAUT", proto.ECLAIRAGE_HAUT_ETAT),
    2: ("eclairage_niveau2", "BORNE", proto.ECLAIRAGE_BORNE_ETAT),
}


def developper(fonctions) -> set:
    """Remplace un nom de carte ("HAUT") par toutes ses fonctions."""
    resultat = set()

    for fonction in fonctions:
        resultat |= CARTES.get(fonction, {fonction})

    return resultat


class FauxStm32:
    """Simule les réponses CAN des fonctions qui ne sont pas réelles."""

    def __init__(self, horloge, bus_reel: bool = False, fonctions_reelles=(),
                 duree_mouvement: float | None = None):
        self.horloge = horloge
        self.duree_mouvement = (
            config.DUREE_MOUVEMENT_SIMULE_S if duree_mouvement is None else duree_mouvement
        )

        # Fonctions simulées = toutes, sauf celles du vrai matériel
        self.simulees = TOUTES_LES_FONCTIONS - developper(fonctions_reelles)

        if bus_reel:
            # Sur le vrai bus, le Linux du Pi relaie nos trames vers le
            # CanManager (et inversement) comme si c'était un autre nœud.
            self.bus = can.Bus(interface=config.CAN_INTERFACE, channel=config.CAN_CANAL)
        else:
            self.bus = can.Bus(interface="virtual", channel=config.CAN_CANAL_SIMULE)

        # État mécanique simulé
        self.niveau = config.NIVEAU_DEPART
        self.angle = 0
        self.bras_deploye = False
        self.porte_vehicule = False      # un véhicule est sur le bras
        self.verrouille = False          # arrêt verrouillé

        # Détecteurs IR simulés
        self.ir_places = [False] * 14
        self.ir_rampe = False
        self._compteur_ir = 0

        # T07 : dernières consignes reçues (mémoire RAM des STM32)
        self.del_places = {}             # numéro 1-14 -> (R, V, B, mode)
        self.eclairages = {}             # niveau 0-2 -> intensité

        # Comportements provoqués par les tests
        self.silencieux = False          # ne répond plus du tout
        self.refuser_prochaine = False   # refuse la prochaine commande moteur
        self.defaut_prochain = False     # termine le prochain mouvement en défaut
        self.rearmement_refuse = False   # refuse le réarmement
        self.del_refusee = False         # refuse les commandes DEL et éclairage

        # Journal des trames reçues : liste de (identifiant, données)
        self.recues = []

        self._mouvement = None           # mouvement en cours
        self._arrivee_rampe = None       # heure d'arrivée du véhicule sur la rampe
        self._compteurs_hb = {"HAUT": 0, "BAS": 0, "BORNE": 0}
        self._etats_hb = {"HAUT": 1, "BAS": 1, "BORNE": 1}
        self._prochain_hb = 0.0

    def simule(self, fonction: str) -> bool:
        return fonction in self.simulees

    def fermer(self):
        self.bus.shutdown()

    # ------------------------------------------------------------------
    # Boucle : à appeler régulièrement
    # ------------------------------------------------------------------

    def mettre_a_jour(self):
        """Traite les trames reçues, termine le mouvement, émet les heartbeats."""
        message = self.bus.recv(timeout=0)

        while message is not None:
            self.recues.append((message.arbitration_id, list(message.data)))

            if not self.silencieux:
                self._traiter(message.arbitration_id, list(message.data))

            message = self.bus.recv(timeout=0)

        maintenant = self.horloge.monotone()

        if self._mouvement is not None and maintenant >= self._mouvement["fin"]:
            self._terminer_mouvement()

        if self._arrivee_rampe is not None and maintenant >= self._arrivee_rampe:
            self._arrivee_rampe = None
            self.definir_ir_rampe(True)

        if maintenant >= self._prochain_hb and not self.silencieux:
            self._prochain_hb = maintenant + 0.5
            self._emettre_heartbeats()

    # ------------------------------------------------------------------
    # Détecteurs IR (utilisés par les tests et la fenêtre de test)
    # ------------------------------------------------------------------

    def definir_ir_place(self, indice: int, present: bool):
        """Change un détecteur de place et émet IR_BAS_CHANGEMENT."""
        self.ir_places[indice] = present

        if self.simule("ir_places"):
            self._compteur_ir = (self._compteur_ir + 1) % 256
            self.envoyer(proto.IR_BAS_CHANGEMENT, [indice, int(present), self._compteur_ir])

    def definir_ir_rampe(self, present: bool):
        """Change le détecteur devant la barrière (IR_ENTREE_CHANGEMENT)."""
        self.ir_rampe = present

        if self.simule("ir_rampe"):
            self._compteur_ir = (self._compteur_ir + 1) % 256
            self.envoyer(proto.IR_ENTREE_CHANGEMENT, [0, int(present), self._compteur_ir])

    def _envoyer_ir_complets(self):
        """Émet les états complets (réponse à SYNCHRO_CMD / IR_LECTURE_CMD)."""
        if self.simule("ir_places"):
            bas = sum(1 << i for i in range(8) if self.ir_places[i])
            haut = sum(1 << (i - 8) for i in range(8, 14) if self.ir_places[i])
            self.envoyer(proto.IR_BAS_COMPLET, [bas, haut, self._compteur_ir, 1])

        if self.simule("ir_rampe"):
            self.envoyer(proto.IR_ENTREE_COMPLET, [int(self.ir_rampe), self._compteur_ir, 1])

    # ------------------------------------------------------------------
    # Redémarrage d'une carte (essai « Redémarrage » de T07)
    # ------------------------------------------------------------------

    def redemarrer(self, carte: str):
        """Simule le redémarrage d'un STM32 : sa mémoire RAM est perdue."""
        if carte in ("BAS", "HAUT"):
            premiere = 1 if carte == "BAS" else 8

            for numero in range(premiere, premiere + 7):
                self.del_places.pop(numero, None)

        for niveau, (fonction, carte_eclairage, accuse) in ECLAIRAGES.items():
            if carte_eclairage == carte:
                self.eclairages.pop(niveau, None)

        # Le heartbeat repart à zéro, en état « initialisation »
        self._compteurs_hb[carte] = 0
        self._etats_hb[carte] = proto.HEARTBEAT_INITIALISATION

    def _emettre_heartbeats(self):
        for carte, can_id in HEARTBEATS.items():
            if not self.simule(f"systeme_{carte.lower()}"):
                continue

            etat = self._etats_hb[carte]

            if etat != proto.HEARTBEAT_INITIALISATION:
                etat = proto.HEARTBEAT_VERROUILLE if self.verrouille else proto.HEARTBEAT_PRET

            self.envoyer(can_id, [self._compteurs_hb[carte], etat])
            self._compteurs_hb[carte] = (self._compteurs_hb[carte] + 1) % 256

            # Après un seul heartbeat d'initialisation, la carte est prête
            self._etats_hb[carte] = proto.HEARTBEAT_PRET

    # ------------------------------------------------------------------
    # Traitement des trames reçues
    # ------------------------------------------------------------------

    def _traiter(self, can_id: int, data: list):
        if can_id in (proto.ELEVATION_CMD, proto.ROTATION_CMD, proto.BRAS_CMD):
            if self.simule("moteurs"):
                self._traiter_mouvement(can_id, data)

        elif can_id == proto.ARRET_RPI:
            # Arrêt prioritaire : mouvement interrompu, système verrouillé
            self.verrouille = True
            self._interrompre_mouvement()

        elif can_id == proto.REARMEMENT_CMD:
            self._traiter_rearmement(data)

        elif can_id in (proto.SYNCHRO_CMD, proto.IR_LECTURE_CMD):
            self._envoyer_ir_complets()

        elif can_id == proto.DEL_PLACE_CMD:
            self._traiter_del(data)

        elif can_id == proto.ECLAIRAGE_CMD:
            self._traiter_eclairage(data)

    def _traiter_del(self, data: list):
        """DEL_PLACE_CMD : places 1-7 -> Bas, 8-14 -> Haut."""
        sequence, numero = data[0], data[1]

        if 1 <= numero <= 7:
            fonction, accuse = "del_niveau1", proto.DEL_BAS_ETAT
        elif 8 <= numero <= 14:
            fonction, accuse = "del_niveau2", proto.DEL_HAUT_ETAT
        else:
            return      # aucune carte n'a cette place : aucune réponse

        if not self.simule(fonction):
            return

        valide = len(data) == 6 and data[5] in (0, 1) and not self.del_refusee

        if valide:
            self.del_places[numero] = tuple(data[2:6])

        self.envoyer(accuse, [sequence, numero, int(valide)])

    def _traiter_eclairage(self, data: list):
        """ECLAIRAGE_CMD : niveau 0 -> Bas, 1 -> Haut, 2 -> Borne."""
        sequence, niveau = data[0], data[1]

        if niveau not in ECLAIRAGES:
            return

        fonction, carte, accuse = ECLAIRAGES[niveau]

        if not self.simule(fonction):
            return

        # Blanc seulement : rouge = vert = bleu
        valide = len(data) == 5 and data[2] == data[3] == data[4] and not self.del_refusee

        if valide:
            self.eclairages[niveau] = data[2]

        self.envoyer(accuse, [sequence, niveau, int(valide)])

    def _traiter_mouvement(self, can_id: int, data: list):
        """Répond à une commande ELEVATION_CMD, ROTATION_CMD ou BRAS_CMD."""
        sequence, action, cible = data[0], data[1], data[2]

        # Action 0 = arrêt pour les trois moteurs
        if action == 0:
            self._interrompre_mouvement()
            return

        refusee = (
            self.verrouille
            or self.refuser_prochaine
            or self._mouvement is not None              # un mouvement à la fois
            or self._bloque_par_bras(can_id, action)    # interverrouillage du bras
        )
        self.refuser_prochaine = False

        if refusee:
            self._envoyer_etat(can_id, sequence, proto.RESULTAT_REFUSE)
            return

        self._envoyer_etat(can_id, sequence, proto.RESULTAT_ACCEPTE)

        self._mouvement = {
            "can_id": can_id,
            "sequence": sequence,
            "action": action,
            "cible": cible,
            "fin": self.horloge.monotone() + self.duree_mouvement,
        }

    def _bloque_par_bras(self, can_id: int, action: int) -> bool:
        """Rotation et changement de niveau refusés si le bras est déployé."""
        if not self.bras_deploye:
            return False

        if can_id == proto.ROTATION_CMD:
            return True

        return can_id == proto.ELEVATION_CMD and action == proto.ELEVATION_DEPLACER

    def _terminer_mouvement(self):
        """Fin du mouvement en cours : applique l'effet et répond « terminée »."""
        mouvement = self._mouvement
        self._mouvement = None

        if self.defaut_prochain:
            self.defaut_prochain = False
            self._envoyer_etat(mouvement["can_id"], mouvement["sequence"],
                               proto.RESULTAT_DEFAUT, defaut=1)
            return

        self._appliquer(mouvement)
        self._envoyer_etat(mouvement["can_id"], mouvement["sequence"], proto.RESULTAT_TERMINE)

    def _interrompre_mouvement(self):
        if self._mouvement is not None:
            mouvement = self._mouvement
            self._mouvement = None
            self._envoyer_etat(mouvement["can_id"], mouvement["sequence"],
                               proto.RESULTAT_INTERROMPU)

    def _appliquer(self, mouvement: dict):
        """Met à jour l'état mécanique simulé et les IR qui en dépendent."""
        can_id, action = mouvement["can_id"], mouvement["action"]

        if can_id == proto.ROTATION_CMD:
            self.angle = mouvement["cible"]

        elif can_id == proto.BRAS_CMD:
            self.bras_deploye = action == proto.BRAS_DEPLOYER

            # Le bras se rétracte avec un véhicule : la place se libère
            if not self.bras_deploye and self.porte_vehicule:
                indice = self._indice_place()

                if indice is not None and self.ir_places[indice]:
                    self.definir_ir_place(indice, False)

        elif action == proto.ELEVATION_DEPLACER:
            self.niveau = mouvement["cible"]

        elif action == proto.ELEVATION_SOULEVER:
            # Soulever avec le bras sous un véhicule : il est pris
            indice = self._indice_place()

            if self.bras_deploye and indice is not None and self.ir_places[indice]:
                self.porte_vehicule = True

        elif action == proto.ELEVATION_ABAISSER:
            # Abaisser à la sortie : le véhicule glisse vers la barrière
            a_la_sortie = (
                self.niveau == config.NIVEAU_SORTIE and self.angle == config.ANGLE_SORTIE
            )

            if self.bras_deploye and self.porte_vehicule and a_la_sortie:
                self.porte_vehicule = False
                self._arrivee_rampe = self.horloge.monotone() + self.duree_mouvement / 2

    def _indice_place(self):
        """Indice IR de la place devant l'ascenseur, ou None."""
        for place in config.PLACES.values():
            if place["niveau"] == self.niveau and place["angle"] == self.angle:
                return place["indice_ir"]

        return None

    def _traiter_rearmement(self, data: list):
        """Répond à REARMEMENT_CMD pour chaque STM32 simulé."""
        sequence = data[0]
        accepte = not self.rearmement_refuse

        if accepte:
            self.verrouille = False

        for carte, can_id in REARMEMENTS.items():
            if self.simule(f"systeme_{carte.lower()}"):
                self.envoyer(can_id, [sequence, int(accepte), 0 if accepte else 1])

    # ------------------------------------------------------------------
    # Émission
    # ------------------------------------------------------------------

    def _envoyer_etat(self, commande_id: int, sequence: int, resultat: int, defaut: int = 0):
        """Émet la trame *_ETAT qui correspond à une commande moteur."""
        if commande_id == proto.ELEVATION_CMD:
            self.envoyer(proto.ELEVATION_ETAT, [sequence, resultat, self.niveau, defaut, 2])

        elif commande_id == proto.ROTATION_CMD:
            self.envoyer(proto.ROTATION_ETAT, [sequence, resultat, self.angle, defaut])

        else:
            position = 2 if self.bras_deploye else 1
            self.envoyer(proto.BRAS_ETAT, [sequence, resultat, position, defaut])

    def envoyer(self, can_id: int, data: list):
        """Émet une trame sur le bus (les tests s'en servent aussi)."""
        self.bus.send(can.Message(arbitration_id=can_id, data=data, is_extended_id=False))
