"""PC-01 — Réception des états.

Essai : le modèle du PC enregistre correctement l'état général, les 14
places, les anomalies, les transactions et les statistiques publiés par
le Raspberry Pi.

Matériel minimal : aucun (messages simulés, sans broker).

Exécution : python test_pc_01_reception_etats.py
"""

import json

from outils_tests import RapportTest
from src.models.modele_supervision import ModeleSupervision
from src.mqtt_topics import MqttTopics

rapport = RapportTest(1, "Réception des états")

modele = ModeleSupervision()
rapport.verifier("État inconnu avant le premier message", modele.etat_service, "INCONNU")

# --- État général ---
changement = modele.traiter_message(MqttTopics.ETAT, json.dumps({
    "etat_service": "MISE_HORS_SERVICE", "etat_retrait": "MOUVEMENT",
    "transaction_active": 12, "message": "Récupération en cours", "horodatage": 1800000000.0,
}))
rapport.verifier("Message reconnu", changement, "etat")
rapport.verifier("État de service", modele.etat_service, "MISE_HORS_SERVICE")
rapport.verifier("État du retrait", modele.etat_retrait, "MOUVEMENT")

# --- Places ---
places = [{"place": f"E1.{i}", "numero": i, "etat": "LIBRE", "presence": False} for i in range(1, 8)]
places += [{"place": f"E2.{i}", "numero": i + 7, "etat": "OCCUPE", "presence": True} for i in range(1, 8)]

changement = modele.traiter_message(MqttTopics.PLACES, json.dumps({"places": places, "rampe": True}))
rapport.verifier("Message reconnu", changement, "places")
rapport.verifier("14 places enregistrées", len(modele.places), 14)
rapport.verifier("État d'une place", modele.places[7]["etat"], "OCCUPE")
rapport.verifier("Présence devant la barrière", modele.rampe, True)

# --- Anomalies ---
modele.traiter_message(MqttTopics.ANOMALIES, json.dumps({"anomalies": [
    {"id": 1, "tache": "T12", "code": "CAN_SANS_REPONSE", "message": "Aucune réponse",
     "place": None, "critique": True, "horodatage": 1800000000.0},
]}))
rapport.verifier("Anomalie enregistrée", [modele.anomalies[0]["tache"], modele.anomalies[0]["code"]],
                 ["T12", "CAN_SANS_REPONSE"])

# --- Transactions et statistiques ---
changement = modele.traiter_message(MqttTopics.TRANSACTIONS, json.dumps({
    "tarif_cents_par_minute": 25,
    "transactions": [{"id": 12, "place": "E2.1", "etat": "RETRAIT_EN_COURS"}],
    "statistiques": {"comptes": [{"rfid": "0A1B2C3D4E", "solde": 2250, "nb_credits": 0, "total_credits": 0,
                                  "nb_debits": 1, "total_debits": 250}]},
}))
rapport.verifier("Message reconnu", changement, "transactions")
rapport.verifier("Transaction enregistrée", modele.transactions[0]["id"], 12)
rapport.verifier("Statistiques enregistrées", modele.statistiques[0]["total_debits"], 250)
rapport.verifier("Tarif enregistré", modele.tarif, 25)

# --- Un topic d'une autre équipe n'est pas traité ---
changement = modele.traiter_message("esa/Equipe_99/etat", json.dumps({"etat_service": "ARRET_VERROUILLE"}))
rapport.verifier("Topic d'une autre équipe ignoré", changement, "inconnu")
rapport.verifier("État de service inchangé", modele.etat_service, "MISE_HORS_SERVICE")

rapport.terminer()
