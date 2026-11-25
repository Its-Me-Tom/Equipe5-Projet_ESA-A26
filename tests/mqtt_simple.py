# mqtt_simple.py - Test MQTT tout seul pour le Raspberry Pi (rien d'autre du projet).
#
#   python3 mqtt_simple.py
#   Ctrl+C pour arreter
#
# Ce qu'il fait :
#   1. se connecte au broker (BROKER_IP ci-dessous)
#   2. annonce le Pi "en ligne" sur esa/Equipe_5/rpi/connexion
#      -> la bande "Raspberry Pi -> MQTT" de l'app PC doit devenir VERTE
#   3. affiche tout ce qui passe sur esa/Equipe_5/# (ex. les commandes du PC)
#   4. a Ctrl+C : annonce "hors ligne" -> la bande devient ROUGE
#
# Si paho manque : pip install paho-mqtt  (ou sudo apt install python3-paho-mqtt)

import json
import time

import paho.mqtt.client as mqtt

BROKER_IP = "10.50.86.13"     # <- mets la MEME adresse que dans pc/src/config.py
BROKER_PORT = 1883
RACINE = "esa/Equipe_5"
TOPIC_CONNEXION = f"{RACINE}/rpi/connexion"


def sur_connexion(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"Connexion REFUSEE par le broker : {reason_code}")
        return

    print(f"CONNECTE a {BROKER_IP}:{BROKER_PORT}")
    client.subscribe(f"{RACINE}/#", qos=1)
    client.publish(TOPIC_CONNEXION, json.dumps({"en_ligne": True, "client": "mqtt_simple"}), qos=1, retain=True)
    print(f"Annonce envoyee sur {TOPIC_CONNEXION} : en_ligne = true\n")


def sur_deconnexion(client, userdata, flags, reason_code, properties):
    print(f"DECONNECTE ({reason_code}) - reconnexion automatique...")


def sur_message(client, userdata, message):
    heure = time.strftime("%H:%M:%S")
    print(f"{heure}  {message.topic}  {message.payload.decode('utf-8', errors='replace')}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="esa-rpi-test-simple")
client.on_connect = sur_connexion
client.on_disconnect = sur_deconnexion
client.on_message = sur_message

# Testament : si le Pi disparait sans prevenir, le broker publie "hors ligne"
client.will_set(TOPIC_CONNEXION, json.dumps({"en_ligne": False, "client": "mqtt_simple"}), qos=1, retain=True)

print(f"Connexion a {BROKER_IP}:{BROKER_PORT} ...")
try:
    client.connect(BROKER_IP, BROKER_PORT, keepalive=15)
except OSError as erreur:
    print(f"Broker INJOIGNABLE : {erreur}")
    print("-> verifie BROKER_IP, que le Pi est sur le bon reseau (hostname -I), et le port 1883.")
    raise SystemExit(1)

client.loop_start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.publish(TOPIC_CONNEXION, json.dumps({"en_ligne": False, "client": "mqtt_simple"}),
                   qos=1, retain=True).wait_for_publish(2)
    print("\nAnnonce hors ligne envoyee. Arret.")
finally:
    client.loop_stop()
    client.disconnect()
