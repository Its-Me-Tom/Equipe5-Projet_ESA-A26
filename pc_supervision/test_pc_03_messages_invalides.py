"""PC-03 — Messages invalides.

Essai : un message MQTT incorrect (JSON invalide, champ manquant) est
ignoré sans modifier les données affichées ni faire planter le PC.

Matériel minimal : aucun (messages simulés, sans broker).

Exécution : python test_pc_03_messages_invalides.py
"""

import json

from outils_tests import RapportTest
from src.models.modele_supervision import ModeleSupervision
from src.mqtt_topics import MqttTopics

rapport = RapportTest(3, "Messages invalides")

modele = ModeleSupervision()
modele.traiter_message(MqttTopics.ETAT, json.dumps({"etat_service": "EN_SERVICE"}))

# --- JSON incorrect ---
rapport.verifier("Texte qui n'est pas du JSON", modele.traiter_message(MqttTopics.ETAT, "{pas du json"), "invalide")
rapport.verifier("Message vide", modele.traiter_message(MqttTopics.PLACES, ""), "invalide")

# --- Champs manquants ---
rapport.verifier("État sans etat_service",
                 modele.traiter_message(MqttTopics.ETAT, json.dumps({"message": "x"})), "invalide")
rapport.verifier("Transactions sans statistiques",
                 modele.traiter_message(MqttTopics.TRANSACTIONS, json.dumps({"transactions": []})), "invalide")
rapport.verifier("Réponse sans id_commande",
                 modele.traiter_message(MqttTopics.REPONSE_COMMANDE, json.dumps({"resultat": "ACCEPTEE"})), "invalide")
rapport.verifier("JSON qui n'est pas un objet", modele.traiter_message(MqttTopics.ANOMALIES, "[1, 2]"), "invalide")

# --- Rien n'a été modifié ---
rapport.verifier("État de service conservé", modele.etat_service, "EN_SERVICE")
rapport.verifier("Places conservées", modele.places, [])
rapport.verifier("Transactions conservées", modele.transactions, [])

# --- Un message valide est toujours accepté ensuite ---
rapport.verifier("Message valide accepté après les erreurs",
                 modele.traiter_message(MqttTopics.ETAT, json.dumps({"etat_service": "HORS_SERVICE"})), "etat")
rapport.verifier("État mis à jour", modele.etat_service, "HORS_SERVICE")

rapport.terminer()
