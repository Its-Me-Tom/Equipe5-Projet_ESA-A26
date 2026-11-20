"""Modèle de l'application de supervision (PC) — T13.

Le PC ne décide de rien : il garde seulement la dernière copie de ce que
le Raspberry Pi a publié et la liste des commandes en attente de réponse.
Aucun PyQt ici : le modèle se teste seul (voir test_pc_*.py).
"""

import json
import time

from src import config
from src.mqtt_topics import MqttTopics

COMMANDES_GENERALES = ("METTRE_HORS_SERVICE", "REMETTRE_EN_SERVICE", "ARRET_IMMEDIAT", "REINITIALISER")
COMMANDES_COMPTES = ("CONSULTER_SOLDE", "AJOUTER_CREDIT")


class ModeleSupervision:
    """Dernier état connu du stationnement et suivi des commandes."""

    def __init__(self):
        # Données publiées par le Raspberry Pi
        self.etat_service = "INCONNU"
        self.etat_retrait = ""
        self.message = ""
        self.places = []           # 14 dictionnaires : place, numero, etat, presence
        self.rampe = None          # présence devant la barrière
        self.anomalies = []
        self.transactions = []
        self.statistiques = []     # un dictionnaire par compte
        self.tarif = None          # tarif en cents par minute
        self.comptes = {}          # carte -> solde (réponses sur les comptes)
        self.rpi_en_ligne = None   # None = inconnu, True / False = annoncé par le RPi

        # Suivi des commandes
        self.en_attente = {}       # id_commande -> heure d'envoi
        self.derniere_commande = None   # dernière commande envoyée (pour la renvoyer)
        self.derniere_reponse = None    # dernière réponse reçue
        self._compteur = 0

    # ------------------------------------------------------------------
    # Commandes PC -> RPi
    # ------------------------------------------------------------------

    def construire_commande(self, nom: str, **champs) -> dict:
        """Construit une commande avec un id_commande unique."""
        self._compteur += 1

        # L'heure en millisecondes rend l'identifiant unique même après un
        # redémarrage du PC (important pour ne pas bloquer un vrai crédit).
        id_commande = f"PC{config.NUMERO_EQUIPE}-{int(time.time() * 1000)}-{self._compteur}"

        commande = {"id_commande": id_commande, "commande": nom}
        commande.update(champs)

        return commande

    def noter_envoi(self, commande: dict):
        """Note qu'une commande vient d'être envoyée."""
        self.en_attente[commande["id_commande"]] = time.monotonic()
        self.derniere_commande = commande

    @staticmethod
    def topic_de(commande: dict) -> str:
        """Topic sur lequel une commande doit être publiée."""
        if commande["commande"] in COMMANDES_COMPTES:
            return MqttTopics.COMMANDE_COMPTES

        return MqttTopics.COMMANDE

    def commandes_en_retard(self) -> list:
        """id_commande des commandes sans réponse après le délai."""
        maintenant = time.monotonic()

        return [
            id_commande
            for id_commande, envoi in self.en_attente.items()
            if maintenant - envoi > config.DELAI_REPONSE_S
        ]

    # ------------------------------------------------------------------
    # Messages RPi -> PC
    # ------------------------------------------------------------------

    def traiter_message(self, topic: str, payload: str) -> str:
        """Met le modèle à jour. Retourne ce qui a changé :

        "etat", "places", "anomalies", "transactions", "reponse", "connexion_rpi",
        "invalide" (JSON incorrect) ou "inconnu" (topic non prévu).
        """
        try:
            message = json.loads(payload)

            if topic == MqttTopics.CONNEXION_RPI:
                en_ligne = message["en_ligne"]
                if not isinstance(en_ligne, bool):
                    return "invalide"
                self.rpi_en_ligne = en_ligne
                return "connexion_rpi"

            if topic == MqttTopics.ETAT:
                self.etat_service = message["etat_service"]
                self.etat_retrait = message.get("etat_retrait", "")
                self.message = message.get("message", "")
                return "etat"

            if topic == MqttTopics.PLACES:
                self.places = message["places"]
                self.rampe = message.get("rampe")
                return "places"

            if topic == MqttTopics.ANOMALIES:
                self.anomalies = message["anomalies"]
                return "anomalies"

            if topic == MqttTopics.TRANSACTIONS:
                self.transactions = message["transactions"]
                self.statistiques = message["statistiques"]["comptes"]
                self.tarif = message.get("tarif_cents_par_minute")
                return "transactions"

            if topic in (MqttTopics.REPONSE_COMMANDE, MqttTopics.REPONSE_COMPTES):
                self._traiter_reponse(message)
                return "reponse"

        except (ValueError, KeyError, TypeError):
            # JSON incorrect ou champ manquant : le modèle n'est pas modifié
            return "invalide"

        return "inconnu"

    def _traiter_reponse(self, reponse: dict):
        """Associe une réponse à sa commande grâce à id_commande."""
        id_commande = reponse["id_commande"]        # KeyError si absent : invalide

        self.derniere_reponse = reponse
        self.en_attente.pop(id_commande, None)

        # Les réponses sur les comptes contiennent des soldes à jour
        for compte in reponse.get("comptes", []):
            self.comptes[compte["rfid"]] = compte["solde"]

        if "rfid" in reponse and reponse.get("solde") is not None:
            self.comptes[reponse["rfid"]] = reponse["solde"]
