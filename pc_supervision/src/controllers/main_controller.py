"""Contrôleur de l'application de supervision (PC) — T13.

Relie les boutons des pages au client MQTT, et les messages MQTT reçus
au modèle puis aux pages.
"""

import json

from PyQt6.QtCore import QTimer

from src.models.modele_supervision import ModeleSupervision
from src.mqtt_topics import MqttTopics
from src.network.mqtt_client import MqttClient


class MainController:
    """Contrôleur principal de l'application PC."""

    def __init__(self, view):
        self.view = view
        self.modele = ModeleSupervision()
        self.mqtt = MqttClient()

        # --- Signaux MQTT (livrés par Qt dans le thread de l'interface) ---
        self.mqtt.connected.connect(self.on_mqtt_connected)
        self.mqtt.disconnected.connect(self.on_mqtt_disconnected)
        self.mqtt.connection_failed.connect(self.on_mqtt_connection_failed)
        self.mqtt.message_received.connect(self.on_message)

        # --- Boutons des pages ---
        view.page_commandes.commande_cliquee.connect(self.envoyer_commande_generale)
        view.page_comptes.actualiser_clique.connect(self.demander_soldes)
        view.page_comptes.crediter_clique.connect(self.ajouter_credit)
        view.page_comptes.renvoyer_clique.connect(self.renvoyer_derniere_commande)

        # --- Surveillance des commandes restées sans réponse ---
        self.minuterie_reponses = QTimer()
        self.minuterie_reponses.timeout.connect(self.verifier_commandes_en_retard)
        self.minuterie_reponses.start(1000)

        for topic in MqttTopics.DU_RPI:
            self.mqtt.subscribe(topic)

        self.mqtt.connect_to_broker()

    def shutdown(self):
        self.mqtt.disconnect_from_broker()

    # ------------------------------------------------------------------
    # Connexion (mêmes noms que dans le labo 4)
    # ------------------------------------------------------------------

    def on_mqtt_connected(self):
        self.view.afficher_connexion(True)
        self.view.add_log("Connecté au broker.")

        # Le broker renvoie tout de suite les derniers états (messages
        # conservés). Les soldes, eux, doivent être demandés.
        self.demander_soldes()

    def on_mqtt_disconnected(self):
        self.view.afficher_connexion(False)

        # Sans broker, le PC ne peut plus savoir si le RPi est connecté
        self.modele.rpi_en_ligne = None
        self.view.afficher_connexion_rpi(None)
        self.view.add_log("Déconnecté du broker. Reconnexion automatique...")

    def on_mqtt_connection_failed(self, erreur: str):
        self.view.afficher_connexion(False)
        self.view.afficher_connexion_rpi(None)
        self.view.add_log(f"Connexion impossible : {erreur}")

    # ------------------------------------------------------------------
    # Commandes PC -> RPi
    # ------------------------------------------------------------------

    def envoyer_commande_generale(self, nom: str):
        """Envoie une des quatre commandes générales."""
        champs = {}

        if nom == "REINITIALISER":
            # Le RPi refuse si l'intervention manuelle n'est pas confirmée
            champs["intervention_confirmee"] = self.view.page_commandes.intervention_confirmee()

        self._envoyer(self.modele.construire_commande(nom, **champs))

    def demander_soldes(self):
        self._envoyer(self.modele.construire_commande("CONSULTER_SOLDE"))

    def ajouter_credit(self, carte: str, cents: int):
        self._envoyer(self.modele.construire_commande("AJOUTER_CREDIT", rfid=carte, montant=cents))

    def renvoyer_derniere_commande(self):
        """Renvoie la dernière commande avec le MÊME id_commande.

        Simule une retransmission : le RPi ne doit pas créditer deux fois.
        """
        if self.modele.derniere_commande is None:
            self.view.add_log("Aucune commande à renvoyer.")
            return

        self._envoyer(self.modele.derniere_commande)

    def _envoyer(self, commande: dict):
        topic = self.modele.topic_de(commande)

        if not self.mqtt.publish(topic, json.dumps(commande)):
            self.view.add_log(f"Non envoyée (déconnecté) : {commande['commande']}")
            return

        self.modele.noter_envoi(commande)
        self.view.add_log(f"TX {commande['commande']} (id {commande['id_commande']})")

    def verifier_commandes_en_retard(self):
        """Signale les commandes sans réponse (RPi éteint ou hors ligne)."""
        for id_commande in self.modele.commandes_en_retard():
            self.modele.en_attente.pop(id_commande)
            self.view.add_log(f"Aucune réponse du Raspberry Pi à la commande {id_commande}")

    # ------------------------------------------------------------------
    # Messages RPi -> PC
    # ------------------------------------------------------------------

    def on_message(self, topic: str, payload: str):
        """Met le modèle à jour, puis rafraîchit la page concernée."""
        view, modele = self.view, self.modele
        changement = modele.traiter_message(topic, payload)

        if changement == "connexion_rpi":
            view.afficher_connexion_rpi(modele.rpi_en_ligne)
            view.add_log("Raspberry Pi " + ("connecté au broker." if modele.rpi_en_ligne else "déconnecté du broker."))

        elif changement == "etat":
            view.page_commandes.afficher_etat(modele.etat_service, modele.etat_retrait, modele.message)

        elif changement == "places":
            view.page_stationnement.afficher_places(modele.places, modele.rampe)
            self._rafraichir_clients_et_historique()

        elif changement == "anomalies":
            view.page_commandes.afficher_anomalies(modele.anomalies)

            for anomalie in modele.anomalies:
                view.add_log(f"ANOMALIE {anomalie.get('tache', '')} {anomalie['code']} : {anomalie['message']}")

        elif changement == "transactions":
            view.page_statistiques.afficher_statistiques(modele.statistiques, modele.transactions)
            self._rafraichir_clients_et_historique()

        elif changement == "reponse":
            self._afficher_reponse(topic, modele.derniere_reponse)

        elif changement == "invalide":
            view.add_log(f"Message invalide ignoré sur {topic}")

    def _rafraichir_clients_et_historique(self):
        """Client de chaque place et nouveaux événements de l'historique (onglet Stationnement)."""
        modele = self.modele
        occupants = {
            place: (modele.nom_court(carte), modele.decrire_carte(carte))
            for place, carte in modele.occupants().items()
        }

        self.view.page_stationnement.afficher_occupants(occupants)
        self.view.page_stationnement.ajouter_historique(modele.prendre_nouveaux_evenements())

    def _afficher_reponse(self, topic: str, reponse: dict):
        """Affiche la réponse du RPi à une commande."""
        texte = f"{reponse['commande']} -> {reponse['resultat']} ({reponse['code']}) {reponse['message']}"
        self.view.add_log(f"RX {texte} (id {reponse['id_commande']})")

        if topic == MqttTopics.REPONSE_COMPTES:
            self.view.page_comptes.afficher_reponse(texte)
            self.view.page_comptes.afficher_comptes(self.modele.comptes, self.modele.noms)
            self._rafraichir_clients_et_historique()      # les noms ont pu arriver
        else:
            self.view.page_commandes.afficher_reponse(texte)