"""PC-02 — Commandes et réponses.

Essai : chaque commande a un id_commande unique, est publiée sur le bon
topic, et la réponse du Raspberry Pi lui est associée par cet identifiant.

Matériel minimal : aucun (messages simulés, sans broker).

Exécution : python test_pc_02_commandes_reponses.py
"""

import json

from outils_tests import RapportTest
from src.models.modele_supervision import ModeleSupervision
from src.mqtt_topics import MqttTopics

rapport = RapportTest(2, "Commandes et réponses")

modele = ModeleSupervision()

# --- Construction des commandes ---
arret = modele.construire_commande("ARRET_IMMEDIAT")
credit = modele.construire_commande("AJOUTER_CREDIT", rfid="0A1B2C3D4E", montant=500)
reinitialisation = modele.construire_commande("REINITIALISER", intervention_confirmee=True)

rapport.verifier("Champs d'une commande", list(arret), ["id_commande", "commande"])
rapport.verifier("Champs d'un crédit", [credit["commande"], credit["rfid"], credit["montant"]],
                 ["AJOUTER_CREDIT", "0A1B2C3D4E", 500])
rapport.verifier("Confirmation d'intervention transmise", reinitialisation["intervention_confirmee"], True)
rapport.verifier("Identifiants tous différents",
                 len({arret["id_commande"], credit["id_commande"], reinitialisation["id_commande"]}), 3)

# --- Choix du topic ---
rapport.verifier("Commande générale -> topic commande", modele.topic_de(arret), MqttTopics.COMMANDE)
rapport.verifier("Commande de compte -> topic comptes/commande", modele.topic_de(credit), MqttTopics.COMMANDE_COMPTES)

# --- Suivi : deux commandes envoyées, une seule réponse reçue ---
modele.noter_envoi(arret)
modele.noter_envoi(credit)
rapport.verifier("Deux commandes en attente", len(modele.en_attente), 2)

changement = modele.traiter_message(MqttTopics.REPONSE_COMPTES, json.dumps({
    "id_commande": credit["id_commande"], "commande": "AJOUTER_CREDIT", "resultat": "ACCEPTEE", "code": "OK",
    "message": "Crédit ajouté", "rfid": "0A1B2C3D4E", "solde": 3000, "horodatage": 1800000000.0,
}))
rapport.verifier("Réponse reconnue", changement, "reponse")
rapport.verifier("La bonne commande n'est plus en attente", list(modele.en_attente), [arret["id_commande"]])
rapport.verifier("Solde mis à jour par la réponse", modele.comptes["0A1B2C3D4E"], 3000)

# --- Renvoi : la dernière commande garde le même id_commande ---
rapport.verifier("Dernière commande conservée pour le renvoi", modele.derniere_commande["id_commande"],
                 credit["id_commande"])

# --- Réponse à une consultation de tous les comptes ---
modele.traiter_message(MqttTopics.REPONSE_COMPTES, json.dumps({
    "id_commande": "AUTRE", "commande": "CONSULTER_SOLDE", "resultat": "ACCEPTEE", "code": "OK",
    "message": "", "horodatage": 1800000000.0,
    "comptes": [{"rfid": "0A1B2C3D4E", "solde": 3000}, {"rfid": "1F00AA5501", "solde": 1000}],
}))
rapport.verifier("Soldes de tous les comptes", modele.comptes, {"0A1B2C3D4E": 3000, "1F00AA5501": 1000})

rapport.terminer()
