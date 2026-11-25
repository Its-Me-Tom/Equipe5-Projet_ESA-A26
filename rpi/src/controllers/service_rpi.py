"""Service du Raspberry Pi : construit les modules et fait tourner la boucle.

    ServiceRPi.demarrer()        ouvre le CAN, le lecteur RFID et MQTT
    ServiceRPi.executer_tour()   UN tour de boucle, non bloquant
    ServiceRPi.arreter()         ferme tout

executer_tour() est appelée en boucle par le thread ServiceWorker
(interface) ou directement par les tests. Toute la logique roule dans ce
seul thread : pas de verrou à gérer entre les modules.

INTÉGRATION AVEC L'ÉQUIPE : les endroits où brancher les modules des
coéquipiers sont marqués « POINT DE BRANCHEMENT ».
"""

import queue

from src import config
from src.format_carte import carte_vers_texte, decrire_carte, texte_vers_carte
from src.hardware import protocole_can as proto
from src.hardware.can_manager import CanManager
from src.hardware.t02_lecteur_rfid import LecteurRFID
from src.horloge import Horloge
from src.models import t12_gestion_retrait as etats_retrait
from src.models.erreurs import ErreurFichier
from src.models.heartbeat_rpi import HeartbeatRPi
from src.models.stationnement import Stationnement
from src.models.t02_fichier_comptes import FichierComptes
from src.models.t02_gestion_comptes import GestionComptes
from src.models.t04_gestion_transactions import GestionTransactions
from src.models.t07_gestion_eclairage import GestionEclairage
from src.models.t12_gestion_retrait import GestionRetrait
from src.models.t13_supervision_mqtt import SupervisionMQTT
from src.network.mqtt_client import MqttClient
from src.simulation.doublures import DepotSimule, RecepteurIRSimule
from src.simulation.faux_stm32 import FauxStm32


class ServiceRPi:
    """Assemble T02, T04, T07, T12 et T13 et les fait fonctionner ensemble.

    Par défaut, chaque matériel suit config.py. Les tests peuvent choisir
    pièce par pièce :
        simuler_rfid, simuler_can, simuler_mqtt : True / False
        fonctions_reelles : fonctions fournies par de vrais STM32 sur le
            vrai bus (ex. {"ir_rampe"}); le faux STM32 simule les autres.
    """

    def __init__(self, horloge=None, dossier_donnees=None, simuler_rfid=None,
                 simuler_can=None, simuler_mqtt=None, fonctions_reelles=None):
        self.horloge = horloge or Horloge()
        dossier = dossier_donnees or config.DOSSIER_DONNEES

        self.journal = []                # lignes affichées par l'interface
        self._actions = queue.Queue()    # actions demandées par l'interface

        # --- Matériel ---
        self.can = CanManager(simulate=simuler_can)
        self.lecteur = LecteurRFID(simuler=simuler_rfid, horloge=self.horloge)
        self.mqtt = MqttClient(simulate=simuler_mqtt)

        # Faux STM32 : tout simulé sur le bus virtuel, ou seulement les
        # fonctions manquantes sur le vrai bus.
        self._fonctions_reelles = fonctions_reelles
        self.faux_stm32 = None

        # --- Modèle partagé de l'équipe ---
        self.stationnement = Stationnement(self.horloge)

        # --- T02 : comptes ---
        self.comptes = GestionComptes(
            FichierComptes(dossier / "comptes.csv", dossier / "operations.csv")
        )

        # --- T04 : transactions ---
        self.transactions = GestionTransactions(
            self.comptes, dossier / "transactions.csv", self.horloge
        )

        # --- T07 : DEL et éclairage ---
        self.eclairage = GestionEclairage(self.can, self.stationnement, self.horloge, self.journaliser)

        # --- T12 : retrait ---
        self.retrait = GestionRetrait(
            self.can, self.stationnement, self.transactions, self.horloge, self.journaliser
        )

        # --- T13 : supervision ---
        self.supervision = SupervisionMQTT(
            self.mqtt, self.stationnement, self.comptes, self.can,
            self.transactions, self.retrait, self.horloge, self.journaliser,
        )
        self.heartbeat = HeartbeatRPi(self.can, self.stationnement, self.retrait, self.horloge)

        # --------------------------------------------------------------
        # POINT DE BRANCHEMENT : modules des coéquipiers
        # Remplacer chaque doublure par le vrai module quand il existe.
        # --------------------------------------------------------------
        # T06 (IR, partie RPi) — doublure
        self.recepteur_ir = RecepteurIRSimule(self.stationnement, self.retrait.traiter_presence_ir)

        # T03 + T11 (dépôt) — doublure
        self.depot = DepotSimule(self.stationnement, self.transactions, self.horloge)

        # --------------------------------------------------------------
        # POINT DE BRANCHEMENT : qui reçoit quoi
        # Un module de coéquipier s'ajoute avec UNE ligne dans la liste.
        # --------------------------------------------------------------
        # Fonctions appelées pour CHAQUE trame CAN reçue
        self.receveurs_can = [
            self.recepteur_ir.traiter_trame_can,     # T06 (doublure)
            self.retrait.traiter_reponse_can,        # T12
            self._transmettre_a_eclairage,           # T07
            self.supervision.traiter_trame_can,      # T13
        ]

        # Fonctions appelées pour chaque NOUVELLE carte RFID lue
        self.receveurs_carte = [
            self._afficher_carte,                    # solde (T02), compte créé si inconnue
            self._payer_si_paiement_en_cours,        # paiement d'un retrait (T12)
        ]

        # Fonctions appelées à CHAQUE tour de boucle
        self.taches_boucle = [
            self.retrait.mettre_a_jour,              # T12
            self.eclairage.mettre_a_jour,            # T07
            self.supervision.mettre_a_jour,          # T13
            self.heartbeat.mettre_a_jour,            # commun
        ]

        # Dernière carte lue (affichage)
        self.derniere_carte = None
        self.dernier_nom = None
        self.dernier_solde = None

    # ------------------------------------------------------------------
    # Démarrage et arrêt
    # ------------------------------------------------------------------

    def demarrer(self):
        """Ouvre les interfaces et synchronise les états."""
        if self.can.simulate or self._fonctions_reelles is not None:
            self.faux_stm32 = FauxStm32(
                self.horloge,
                bus_reel=not self.can.simulate,
                fonctions_reelles=self._fonctions_reelles or (),
            )
            self.depot.faux_stm32 = self.faux_stm32

        if self.can.connect():
            self.journaliser("CAN : bus ouvert" + (" (simulé)" if self.can.simulate else ""))
        else:
            self.journaliser(f"CAN : ERREUR — {self.can.last_error}")

        if self.lecteur.connecter():
            self.journaliser("RFID : lecteur prêt" + (" (simulé)" if self.lecteur.simuler else ""))
        else:
            self.journaliser(f"RFID : ERREUR — {self.lecteur.derniere_erreur}")

        # Contrôle des fichiers au démarrage (T02)
        try:
            for probleme in self.comptes.verifier_coherence():
                self.journaliser(f"T02 : incohérence — {probleme}")
        except ErreurFichier as erreur:
            self.journaliser(f"T02 : ERREUR DE FICHIER — {erreur}")

        # Reprise après redémarrage (T04)
        for note in self.transactions.notes_reprise:
            self.journaliser(f"T04 : reprise — {note}")

        self.stationnement.reconstruire_places(self.transactions.obtenir_transactions())
        self._remettre_vehicules_simules()

        # Éclairage blanc des trois niveaux (T07). Les DEL des places
        # suivent au premier tour de boucle (eclairage.mettre_a_jour).
        for niveau, intensite in config.INTENSITE_ECLAIRAGE.items():
            self.eclairage.definir_luminosite_niveau(niveau, intensite)

        self.supervision.demarrer()

        # Demande aux STM32 tous leurs états courants (SYNCHRO_CMD)
        self.can.send(proto.SYNCHRO_CMD, [0x03])

    def arreter(self):
        self.mqtt.disconnect_from_broker()
        self.lecteur.deconnecter()
        self.can.disconnect()

        if self.faux_stm32 is not None:
            self.faux_stm32.fermer()
            self.faux_stm32 = None

    def _remettre_vehicules_simules(self):
        """Simulation : remet un véhicule dans chaque place déjà occupée."""
        if self.faux_stm32 is None:
            return

        for nom, etat in self.stationnement.etats_places.items():
            if etat == "OCCUPE":
                self.faux_stm32.ir_places[config.PLACES[nom]["indice_ir"]] = True

    # ------------------------------------------------------------------
    # Boucle
    # ------------------------------------------------------------------

    def executer_tour(self):
        """Un tour de boucle. Ne bloque jamais."""
        # 1) Actions demandées par l'interface (boutons)
        while not self._actions.empty():
            fonction, arguments = self._actions.get()
            fonction(*arguments)

        # 2) Faux STM32 (simulation)
        if self.faux_stm32 is not None:
            self.faux_stm32.mettre_a_jour()

        # 3) Trames CAN reçues : chaque module prend celles qui le concernent
        message = self.can.receive()

        while message is not None:
            for receveur in self.receveurs_can:
                receveur(message)

            message = self.can.receive()

        # 4) Carte RFID
        identifiant = self.lecteur.lire_identifiant()

        if identifiant is not None:
            for receveur in self.receveurs_carte:
                receveur(identifiant)

        # 5) Machines à états et publications
        for tache in self.taches_boucle:
            tache()

    def _transmettre_a_eclairage(self, message):
        """T07 reçoit l'identifiant et les données (signature du contrat)."""
        self.eclairage.traiter_retour_can(message.arbitration_id, message.data)

    def _afficher_carte(self, identifiant: int):
        """Une nouvelle carte vient d'être lue : noter son nom et son solde.

        Carte inconnue + config.AJOUTER_CARTES_INCONNUES : un compte est créé
        (nom = numéro de la carte, solde = config.SOLDE_NOUVELLE_CARTE_CENTS).
        """
        self.derniere_carte = carte_vers_texte(identifiant)
        self.dernier_nom = None

        if self.lecteur.dernier_brut:
            self.journaliser(f"RFID : {decrire_carte(self.lecteur.dernier_brut)}")

        try:
            self.dernier_solde = self.comptes.obtenir_solde(identifiant)

            if self.dernier_solde is None and config.AJOUTER_CARTES_INCONNUES:
                self.comptes.creer_compte(identifiant)
                self.dernier_solde = self.comptes.obtenir_solde(identifiant)
                self.journaliser(f"RFID : carte {self.derniere_carte} inconnue -> compte créé "
                                 f"({self.dernier_solde} ¢ de départ)")

            self.dernier_nom = self.comptes.obtenir_nom(identifiant)

        except ErreurFichier as erreur:
            self.dernier_solde = None
            self.journaliser(f"T02 : ERREUR DE FICHIER — {erreur}")
            return

        if self.dernier_solde is None:
            self.journaliser(f"RFID : carte {self.derniere_carte} inconnue")
        else:
            self.journaliser(f"RFID : carte {self.derniere_carte} ({self.dernier_nom}), "
                             f"solde {self.dernier_solde} ¢")

    def _payer_si_paiement_en_cours(self, identifiant: int):
        """Pendant la fenêtre de paiement, la carte sert à payer (T12)."""
        if self.retrait.etat == etats_retrait.PAIEMENT:
            self.retrait.presenter_carte(identifiant)
            self.journaliser(f"T12 : {self.retrait.message}")

    # ------------------------------------------------------------------
    # Liens avec l'interface graphique
    # ------------------------------------------------------------------

    def demander(self, fonction, *arguments):
        """Demande d'exécuter une fonction dans le thread du service.

        L'interface n'appelle jamais les modules directement : elle dépose
        sa demande ici et executer_tour() l'exécute au prochain tour.
        """
        self._actions.put((fonction, arguments))

    def journaliser(self, texte: str):
        self.journal.append(texte)

    def simuler_carte(self, texte_carte: str):
        """Simulation : présente une carte au lecteur."""
        self.lecteur.simuler_carte(texte_vers_carte(texte_carte))

    def simuler_depot(self, place: str, texte_carte: str):
        """Simulation : range un véhicule (doublure de T03 + T11)."""
        transaction_id = self.depot.deposer(place, texte_vers_carte(texte_carte))

        if transaction_id is None:
            self.journaliser(f"Dépôt refusé à la place {place}")
        else:
            self.journaliser(f"Dépôt simulé : transaction {transaction_id:06d}, place {place}")

    def simuler_retrait_vehicule(self):
        """Simulation : l'utilisateur retire le véhicule devant la barrière."""
        if self.faux_stm32 is not None and self.faux_stm32.ir_rampe:
            self.faux_stm32.definir_ir_rampe(False)
            self.journaliser("Véhicule retiré devant la barrière (simulé)")

    def remettre_en_service(self):
        """Remise en service locale (même règle que la commande MQTT)."""
        self.supervision.traiter_commande({"id_commande": "LOCAL", "commande": "REMETTRE_EN_SERVICE"})

    def demander_retrait(self, transaction_id: int):
        self.retrait.demander_retrait(transaction_id)
        self.journaliser(f"T12 : {self.retrait.message}")

    def regler_eclairage(self, niveau: int, intensite: int):
        """Réglage manuel du blanc d'un niveau (T07)."""
        self.eclairage.definir_luminosite_niveau(niveau, intensite)
        self.journaliser(f"T07 : éclairage du niveau {niveau} à {intensite}")

    def instantane(self) -> dict:
        """Copie de tout ce que l'interface doit afficher."""
        retrait = self.retrait
        cout = None

        if retrait.etat == etats_retrait.DEMANDE:
            cout = retrait.obtenir_cout_actuel()

        transaction = None

        if retrait.transaction_id is not None:
            transaction = self.transactions.obtenir_transaction(retrait.transaction_id)

        journal, self.journal = self.journal, []

        return {
            "etat_service": self.stationnement.etat_service,
            "mqtt_connecte": self.mqtt.is_connected(),
            "can_connecte": self.can.is_connected(),
            "rfid_disponible": self.lecteur.est_disponible(),
            "derniere_carte": self.derniere_carte,
            "dernier_nom": self.dernier_nom,
            "dernier_solde": self.dernier_solde,
            "etat_retrait": retrait.etat,
            "message_retrait": retrait.message,
            "transaction": transaction,
            "cout": cout,
            "secondes_restantes": retrait.secondes_restantes(),
            "tarif": config.TARIF_CENTS_PAR_MINUTE,
            "delai_paiement": config.DELAI_PAIEMENT_S,
            "places": dict(self.stationnement.etats_places),
            "presences": dict(self.stationnement.presence_places),
            "rampe": self.stationnement.presence_rampe,
            "del_confirmees": dict(self.eclairage.confirmations),
            "intensites": dict(self.eclairage.intensites),
            "transactions": self.transactions.obtenir_transactions(),
            "anomalies": list(self.stationnement.anomalies),
            "journal": journal,
        }
