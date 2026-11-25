"""T13 — Supervision MQTT côté Raspberry Pi (« SupervisionMQTT » du contrat).

Rôle :
    - publier l'état général, les 14 places, les anomalies, les
      transactions et les statistiques vers le PC;
    - recevoir les commandes du PC, les valider, y répondre avec le même
      id_commande et les acheminer aux bons modules;
    - gérer les états de service de la borne.

Le RPi reste la source de référence : le PC ne modifie jamais rien
directement et ne parle jamais aux STM32.

Le format exact des messages JSON est décrit dans docs/CONTRAT_MQTT.md.
"""

import json
import queue

from src import config
from src.format_carte import carte_vers_texte, texte_vers_carte
from src.hardware import protocole_can as proto
from src.horloge import Horloge
from src.models import stationnement as etats
from src.models.erreurs import CarteInconnue, ErreurEsa, OperationRepetee
from src.mqtt_topics import MqttTopics

COMMANDES_GENERALES = ("METTRE_HORS_SERVICE", "REMETTRE_EN_SERVICE", "ARRET_IMMEDIAT", "REINITIALISER")
COMMANDES_COMPTES = ("CONSULTER_SOLDE", "AJOUTER_CREDIT")

# Trame de réponse au réarmement -> nom du STM32
REPONSES_REARMEMENT = {
    proto.REARMEMENT_HAUT: "HAUT",
    proto.REARMEMENT_BAS: "BAS",
    proto.REARMEMENT_BORNE: "BORNE",
}

# Trames d'arrêt et de défaut émises par les STM32 -> nom du STM32
ARRETS_STM32 = {proto.ARRET_HAUT: "HAUT", proto.ARRET_BAS: "BAS", proto.ARRET_BORNE: "BORNE"}
DEFAUTS_STM32 = {proto.DEFAUT_HAUT: "HAUT", proto.DEFAUT_BAS: "BAS", proto.DEFAUT_BORNE: "BORNE"}


class SupervisionMQTT:
    """Lien entre le PC (MQTT) et les modules du Raspberry Pi."""

    def __init__(self, mqtt, stationnement, comptes, can=None, transactions=None,
                 retrait=None, horloge: Horloge | None = None, journal=None):
        self.mqtt = mqtt                    # MqttClient
        self.stationnement = stationnement  # modèle partagé
        self.comptes = comptes              # GestionComptes (T02)
        self.can = can                      # CanManager
        self.transactions = transactions    # GestionTransactions (T04)
        self.retrait = retrait              # GestionRetrait (T12)
        self.horloge = horloge or Horloge()
        self.journal = journal or (lambda texte: None)

        # Messages MQTT reçus, déposés par le thread réseau de Paho et
        # traités plus tard par mettre_a_jour() dans le thread du service.
        self._boite_reception = queue.Queue()

        self._resynchroniser = False        # tout republier (après connexion)
        self._derniers_publies = {}         # topic -> dernier contenu publié
        self._prochaine_pub_etat = 0.0
        self._prochaine_pub_donnees = 0.0
        self._anomalies_vues = 0            # anomalies déjà traitées
        self._rearmement = None             # réarmement en cours

    # ------------------------------------------------------------------
    # Démarrage
    # ------------------------------------------------------------------

    def demarrer(self) -> None:
        """S'abonne aux commandes du PC et lance la connexion au broker."""
        self.mqtt.on_message = self.recevoir_message_mqtt
        self.mqtt.on_connected = self._sur_connexion

        self.mqtt.subscribe(MqttTopics.COMMANDE)
        self.mqtt.subscribe(MqttTopics.COMMANDE_COMPTES)

        # Le PC voit si le RPi est en ligne (retain + testament MQTT)
        self.mqtt.definir_presence(MqttTopics.CONNEXION_RPI)

        self.mqtt.connect_to_broker()

    def recevoir_message_mqtt(self, topic: str, payload: str):
        """Appelée par le thread MQTT : on dépose seulement le message."""
        self._boite_reception.put((topic, payload))

    def _sur_connexion(self):
        """Appelée par le thread MQTT à chaque (re)connexion."""
        self._resynchroniser = True

    # ------------------------------------------------------------------
    # Boucle non bloquante
    # ------------------------------------------------------------------

    def mettre_a_jour(self) -> None:
        """À appeler à chaque tour de la boucle du service."""
        self._traiter_boite_reception()
        self._verifier_nouvelles_anomalies()
        self._verifier_rearmement()
        self._verifier_fin_de_service()
        self._publier_changements()

    def _traiter_boite_reception(self):
        """Traite les messages MQTT reçus depuis le dernier tour."""
        while not self._boite_reception.empty():
            topic, payload = self._boite_reception.get()

            if topic == MqttTopics.COMMANDE:
                topic_reponse, traiter = MqttTopics.REPONSE_COMMANDE, self.traiter_commande
            else:
                topic_reponse, traiter = MqttTopics.REPONSE_COMPTES, self.traiter_commande_compte

            try:
                message = json.loads(payload)
            except ValueError:
                self._repondre(topic_reponse, None, None, False, "JSON_INVALIDE",
                               "Le message n'est pas du JSON valide")
                continue

            traiter(message)

    def _verifier_nouvelles_anomalies(self):
        """Publie les nouvelles anomalies; une anomalie critique verrouille la borne."""
        nouvelles = self.stationnement.anomalies[self._anomalies_vues:]
        self._anomalies_vues = len(self.stationnement.anomalies)

        for anomalie in nouvelles:
            self.publier_anomalie(anomalie)

            if anomalie["critique"]:
                self._verrouiller()

    def _verifier_fin_de_service(self):
        """MISE_HORS_SERVICE -> HORS_SERVICE quand la transaction est finie."""
        if self.stationnement.etat_service != etats.MISE_HORS_SERVICE:
            return

        if self.retrait is None or not self.retrait.est_confirme():
            self.stationnement.etat_service = etats.HORS_SERVICE
            self.journal("T13 : borne HORS_SERVICE")

    # ------------------------------------------------------------------
    # Commandes générales (topic « commande »)
    # ------------------------------------------------------------------

    def traiter_commande(self, message: dict) -> None:
        """Valide et exécute une commande générale du PC."""
        topic = MqttTopics.REPONSE_COMMANDE
        id_commande, commande = self._lire_entete(message, topic, COMMANDES_GENERALES)

        if commande is None:
            return

        etat = self.stationnement.etat_service
        acceptee, code, texte = True, "OK", ""

        if commande == "ARRET_IMMEDIAT":
            # Toujours acceptée, même pendant une transaction confirmée
            self._verrouiller()
            texte = "Arrêt logiciel verrouillé"

        elif etat == etats.ARRET_VERROUILLE and commande != "REINITIALISER":
            acceptee, code = False, "ETAT_INCOMPATIBLE"
            texte = "Arrêt verrouillé : seule REINITIALISER est permise"

        elif commande == "METTRE_HORS_SERVICE":
            self._mettre_hors_service()
            texte = "Nouvelles transactions refusées"

        elif commande == "REMETTRE_EN_SERVICE":
            self.stationnement.etat_service = etats.EN_SERVICE
            texte = "Borne en service"

        elif commande == "REINITIALISER":
            acceptee, code, texte = self._lancer_reinitialisation(message)

        self.journal(f"T13 : commande {commande} -> {'acceptée' if acceptee else code}")
        self._repondre(topic, id_commande, commande, acceptee, code, texte)

    def _mettre_hors_service(self):
        """Refuse les nouvelles transactions dès maintenant."""
        if self.retrait is not None:
            # Une transaction non confirmée est annulée...
            self.retrait.annuler()

            # ...une transaction confirmée se termine normalement.
            if self.retrait.est_confirme():
                self.stationnement.etat_service = etats.MISE_HORS_SERVICE
                return

        self.stationnement.etat_service = etats.HORS_SERVICE

    def _verrouiller(self):
        """Arrêt logiciel : ARRET_RPI sur le CAN et borne verrouillée.

        Ce n'est pas un arrêt d'urgence matériel certifié.
        """
        if self.stationnement.etat_service == etats.ARRET_VERROUILLE:
            return

        self.stationnement.etat_service = etats.ARRET_VERROUILLE
        self._rearmement = None

        if self.can is not None:
            self.can.send(proto.ARRET_RPI, [config.ARRET_MOTIF, config.ARRET_SOURCE, config.ARRET_DETAIL])

        if self.retrait is not None:
            self.retrait.arreter()

        self.journal("T13 : ARRÊT VERROUILLÉ")

    # ------------------------------------------------------------------
    # Réinitialisation (REINITIALISER)
    # ------------------------------------------------------------------

    def _lancer_reinitialisation(self, message: dict):
        """Lance le réarmement des STM32. Retourne (acceptée, code, texte).

        « Acceptée » ne veut pas dire terminée : le résultat est confirmé
        par la publication de l'état HORS_SERVICE.
        """
        if self.stationnement.etat_service != etats.ARRET_VERROUILLE:
            return False, "ETAT_INCOMPATIBLE", "La borne n'est pas verrouillée"

        if message.get("intervention_confirmee") is not True:
            return False, "INTERVENTION_NON_CONFIRMEE", (
                "Confirmer l'intervention manuelle avant de réinitialiser"
            )

        if self._rearmement is not None:
            return False, "ETAT_INCOMPATIBLE", "Réarmement déjà en cours"

        sequence = self.can.next_sequence() if self.can is not None else 0

        self._rearmement = {
            "sequence": sequence,
            "reponses": {},       # nom du STM32 -> True (accepté) / False
            "echeance": self.horloge.monotone() + config.DELAI_REARMEMENT_S,
        }

        if self.can is not None:
            self.can.send(proto.REARMEMENT_CMD, [sequence, 0x01])

        return True, "OK", "Réarmement demandé aux STM32"

    def _verifier_rearmement(self):
        """Vérifie les réponses au réarmement (non bloquant)."""
        if self._rearmement is None:
            return

        reponses = self._rearmement["reponses"]
        requises = config.REARMEMENT_CARTES_REQUISES

        if any(reponses.get(carte) is False for carte in requises):
            self._echec_rearmement("Réarmement refusé par un STM32")

        elif all(reponses.get(carte) is True for carte in requises):
            # Succès : les défauts sont levés. On revient à HORS_SERVICE,
            # jamais à EN_SERVICE, et aucun mouvement ne redémarre.
            self._rearmement = None
            self.stationnement.anomalies.clear()
            self._anomalies_vues = 0

            if self.retrait is not None:
                self.retrait.reinitialiser()

            if self.transactions is not None:
                self.stationnement.reconstruire_places(self.transactions.obtenir_transactions())

            self.stationnement.etat_service = etats.HORS_SERVICE
            self.journal("T13 : réinitialisation réussie -> HORS_SERVICE")

        elif self.horloge.monotone() >= self._rearmement["echeance"]:
            self._echec_rearmement("Aucune réponse au réarmement")

    def _echec_rearmement(self, texte: str):
        """Réarmement échoué : la borne reste verrouillée."""
        self._rearmement = None
        self.stationnement.ajouter_anomalie("T13", "REARMEMENT_REFUSE", texte, critique=False)
        self.journal(f"T13 : {texte}")

    def traiter_trame_can(self, message):
        """Traite les trames CAN qui concernent la supervision."""
        can_id, donnees = message.arbitration_id, message.data

        if can_id in REPONSES_REARMEMENT and self._rearmement is not None:
            if donnees[0] == self._rearmement["sequence"]:
                self._rearmement["reponses"][REPONSES_REARMEMENT[can_id]] = donnees[1] == 1

        elif can_id in ARRETS_STM32:
            # Un STM32 s'est arrêté de lui-même : anomalie critique
            self.stationnement.ajouter_anomalie(
                "T13", "ARRET_STM32",
                f"Arrêt signalé par le STM32 {ARRETS_STM32[can_id]} "
                f"(motif {donnees[0]}, source {donnees[1]})",
            )

        elif can_id in DEFAUTS_STM32:
            self.stationnement.ajouter_anomalie(
                "T13", "DEFAUT_STM32",
                f"Défaut du STM32 {DEFAUTS_STM32[can_id]} (source {donnees[0]}, code {donnees[1]})",
                critique=donnees[2] == 2,       # gravité 2 = critique
            )

    # ------------------------------------------------------------------
    # Commandes sur les comptes (topic « comptes/commande »)
    # ------------------------------------------------------------------

    def traiter_commande_compte(self, message: dict) -> None:
        """Consultation de solde et ajout de crédit, acheminés à T02."""
        topic = MqttTopics.REPONSE_COMPTES
        id_commande, commande = self._lire_entete(message, topic, COMMANDES_COMPTES)

        if commande is None:
            return

        try:
            if commande == "CONSULTER_SOLDE":
                extra = self._lire_soldes(message)
                acceptee, code, texte = True, "OK", ""
            else:
                acceptee, code, texte, extra = self._ajouter_credit(id_commande, message)

        except ErreurEsa as erreur:
            # Carte inconnue, montant invalide, erreur de fichier...
            acceptee, code, texte, extra = False, erreur.code, str(erreur), {}

        except (KeyError, ValueError, TypeError):
            # Champ absent, numéro de carte au mauvais format, mauvais type...
            acceptee, code, extra = False, "CHAMP_INVALIDE", {}
            texte = "Champ rfid ou montant absent ou invalide"

        self.journal(f"T13 : commande {commande} -> {'acceptée' if acceptee else code}")
        self._repondre(topic, id_commande, commande, acceptee, code, texte, **extra)

    def _lire_soldes(self, message: dict) -> dict:
        """Un compte si « rfid » est fourni, sinon tous les comptes."""
        comptes = self.comptes.obtenir_comptes()
        noms = self.comptes.obtenir_noms()

        if "rfid" in message:
            carte = carte_vers_texte(texte_vers_carte(message["rfid"]))

            if carte not in comptes:
                raise CarteInconnue(f"Carte {carte} inconnue")

            comptes = {carte: comptes[carte]}

        return {"comptes": [{"rfid": carte, "nom": noms.get(carte, carte), "solde": solde}
                            for carte, solde in comptes.items()]}

    def _ajouter_credit(self, id_commande: str, message: dict):
        """Ajoute du crédit. id_commande sert d'identifiant d'opération :
        le même message reçu deux fois ne crédite qu'une fois."""
        identifiant_rfid = texte_vers_carte(message["rfid"])
        montant = message["montant"]

        try:
            self.comptes.ajouter_credit(identifiant_rfid, montant, operation_id=id_commande)
            code, texte = "OK", "Crédit ajouté"

        except OperationRepetee:
            code, texte = "DEJA_TRAITEE", "Commande déjà traitée : aucun 2e crédit"

        extra = {
            "rfid": carte_vers_texte(identifiant_rfid),
            "nom": self.comptes.obtenir_nom(identifiant_rfid),
            "solde": self.comptes.obtenir_solde(identifiant_rfid),
        }

        return True, code, texte, extra

    # ------------------------------------------------------------------
    # Publications
    # ------------------------------------------------------------------

    def publier_etat(self) -> None:
        """État général de la borne (topic « etat », conservé)."""
        self._publier(MqttTopics.ETAT, self._contenu_etat(), forcer=True)

    def publier_places(self) -> None:
        """Les 14 emplacements et la rampe (topic « places », conservé)."""
        self._publier(MqttTopics.PLACES, self._contenu_places(), forcer=True)

    def publier_anomalie(self, anomalie: dict) -> None:
        """Liste des anomalies actives (topic « anomalies », conservé).

        Toute la liste est publiée : après une reconnexion, le PC la
        retrouve au complet.
        """
        self.journal(f"T13 : anomalie {anomalie['code']} — {anomalie['message']}")
        self._publier(MqttTopics.ANOMALIES, self._contenu_anomalies(), forcer=True)

    def publier_transactions(self) -> None:
        """Transactions et statistiques (topic « transactions », conservé)."""
        self._publier(MqttTopics.TRANSACTIONS, self._contenu_transactions(), forcer=True)

    def _publier_changements(self):
        """Publie ce qui a changé, et tout après une (re)connexion."""
        if not self.mqtt.is_connected():
            return          # hors ligne : la borne continue localement

        maintenant = self.horloge.monotone()
        forcer = self._resynchroniser
        self._resynchroniser = False

        # « etat » est aussi republié périodiquement
        if forcer or maintenant >= self._prochaine_pub_etat:
            self._prochaine_pub_etat = maintenant + config.PERIODE_PUBLICATION_ETAT_S
            self.publier_etat()
        else:
            self._publier(MqttTopics.ETAT, self._contenu_etat())

        self._publier(MqttTopics.PLACES, self._contenu_places(), forcer)
        self._publier(MqttTopics.ANOMALIES, self._contenu_anomalies(), forcer)

        # Les comptes sont relus dans les fichiers : pas à chaque tour
        if forcer or maintenant >= self._prochaine_pub_donnees:
            self._prochaine_pub_donnees = maintenant + config.PERIODE_PUBLICATION_DONNEES_S
            self._publier(MqttTopics.TRANSACTIONS, self._contenu_transactions(), forcer)

    def _contenu_etat(self) -> dict:
        contenu = {"etat_service": self.stationnement.etat_service}

        if self.retrait is not None:
            contenu["etat_retrait"] = self.retrait.etat
            contenu["transaction_active"] = self.retrait.transaction_id
            contenu["message"] = self.retrait.message

        return contenu

    def _contenu_places(self) -> dict:
        return {
            "places": [
                {
                    "place": nom,
                    "numero": config.PLACES[nom]["numero"],
                    "etat": self.stationnement.etats_places[nom],
                    "presence": self.stationnement.presence_places[nom],
                }
                for nom in config.PLACES
            ],
            "rampe": self.stationnement.presence_rampe,
        }

    def _contenu_anomalies(self) -> dict:
        return {"anomalies": list(self.stationnement.anomalies)}

    def _contenu_transactions(self) -> dict:
        contenu = {
            "tarif_cents_par_minute": config.TARIF_CENTS_PAR_MINUTE,
            "transactions": [],
            "statistiques": {"comptes": []},
        }

        if self.transactions is not None:
            contenu["transactions"] = self.transactions.obtenir_transactions()

        try:
            contenu["statistiques"]["comptes"] = self._statistiques_comptes()
        except ErreurEsa as erreur:
            contenu["statistiques"]["erreur"] = str(erreur)

        return contenu

    def _statistiques_comptes(self) -> list:
        """Historique d'utilisation par compte (pour les graphiques du PC)."""
        noms = self.comptes.obtenir_noms()
        statistiques = {
            carte: {
                "rfid": carte, "nom": noms.get(carte, carte), "solde": solde,
                "nb_credits": 0, "total_credits": 0,
                "nb_debits": 0, "total_debits": 0,
            }
            for carte, solde in self.comptes.obtenir_comptes().items()
        }

        for operation in self.comptes.obtenir_operations():
            compte = statistiques.get(operation["rfid"])

            if compte is not None and operation["type"] in ("credit", "debit"):
                compte[f"nb_{operation['type']}s"] += 1
                compte[f"total_{operation['type']}s"] += operation["montant"]

        return list(statistiques.values())

    def _publier(self, topic: str, contenu: dict, forcer: bool = False):
        """Publie en JSON si le contenu a changé (ou si forcer = True)."""
        if not forcer and self._derniers_publies.get(topic) == contenu:
            return

        message = dict(contenu)
        message["horodatage"] = self.horloge.maintenant()

        if self.mqtt.publish(topic, json.dumps(message), retain=True):
            # Copie profonde simple : le contenu peut changer ensuite
            self._derniers_publies[topic] = json.loads(json.dumps(contenu))

    # ------------------------------------------------------------------
    # Utilitaires des commandes
    # ------------------------------------------------------------------

    def _lire_entete(self, message, topic: str, permises: tuple):
        """Vérifie id_commande et commande. Retourne (id, commande).

        En cas d'erreur, répond « REFUSEE » et retourne (id, None).
        """
        if not isinstance(message, dict):
            self._repondre(topic, None, None, False, "JSON_INVALIDE", "Le message doit être un objet JSON")
            return None, None

        id_commande = message.get("id_commande")
        commande = message.get("commande")

        if not isinstance(id_commande, str) or id_commande == "":
            self._repondre(topic, None, commande, False, "CHAMP_MANQUANT", "id_commande absent ou invalide")
            return None, None

        if commande not in permises:
            self._repondre(topic, id_commande, commande, False, "COMMANDE_INCONNUE",
                           f"Commande inconnue : {commande!r}")
            return id_commande, None

        return id_commande, commande

    def _repondre(self, topic, id_commande, commande, acceptee, code, texte, **extra):
        """Publie la réponse à une commande, avec le même id_commande."""
        reponse = {
            "id_commande": id_commande,
            "commande": commande,
            "resultat": "ACCEPTEE" if acceptee else "REFUSEE",
            "code": code,
            "message": texte,
            "horodatage": self.horloge.maintenant(),
        }
        reponse.update(extra)

        self.mqtt.publish(topic, json.dumps(reponse))
