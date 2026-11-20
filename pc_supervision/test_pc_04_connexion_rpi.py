"""PC-04 — Connexion du Raspberry Pi au broker.

Essai : le modèle du PC suit l'état en ligne / hors ligne du Raspberry Pi
publié sur le topic rpi/connexion (message conservé + testament MQTT).

Matériel minimal : aucun (messages simulés, sans broker).

Exécution : python test_pc_04_connexion_rpi.py
"""

import json

from outils_tests import RapportTest
from src.models.modele_supervision import ModeleSupervision
from src.mqtt_topics import MqttTopics

rapport = RapportTest(4, "Connexion du Raspberry Pi")

modele = ModeleSupervision()
rapport.verifier("Inconnu avant le premier message", modele.rpi_en_ligne, None)

# Le RPi se connecte et s'annonce
changement = modele.traiter_message(MqttTopics.CONNEXION_RPI, json.dumps({"en_ligne": True, "client": "esa-rpi"}))
rapport.verifier("Message reconnu", changement, "connexion_rpi")
rapport.verifier("RPi en ligne", modele.rpi_en_ligne, True)

# Le broker publie le testament (RPi débranché)
modele.traiter_message(MqttTopics.CONNEXION_RPI, json.dumps({"en_ligne": False, "client": "esa-rpi"}))
rapport.verifier("RPi hors ligne", modele.rpi_en_ligne, False)

# Message mal formé : ignoré, l'état ne change pas
changement = modele.traiter_message(MqttTopics.CONNEXION_RPI, json.dumps({"en_ligne": "oui"}))
rapport.verifier("Valeur invalide refusée", changement, "invalide")
rapport.verifier("État inchangé", modele.rpi_en_ligne, False)

rapport.verifier("Topic écouté par le PC", MqttTopics.CONNEXION_RPI in MqttTopics.DU_RPI, True)

rapport.terminer()
