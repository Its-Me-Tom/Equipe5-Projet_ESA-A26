"""Test RFID -> PC : chaque puce lue sur le Raspberry Pi est envoyée à l'app PC.

Essai : passer une puce devant le lecteur ID-12LA. Le terminal du Pi affiche
toutes les données de la puce (trame brute, ID brut, numéro imprimé en
décimal, identifiant utilisé selon config.FORMAT_CARTE, checksum, compte),
puis le Pi publie la lecture au PC par MQTT. L'app PC n'est PAS modifiée :
la lecture arrive comme une réponse sur le topic comptes/reponse, donc on la
voit dans le journal MQTT (ligne RX LECTURE_RFID) et dans l'onglet
« Comptes RFID » (ligne Réponse + la carte et son solde dans le tableau).

Matériel minimal
    - lecteur RFID branché sur l'UART du Pi (config.PORT_RFID, 9600 bauds)
    - broker MQTT joignable à config.BROKER_IP
    - l'app PC lancée et connectée au même broker
    Pas de CAN ni de STM32. Ne pas lancer main.py en même temps (port série).

Exécution : python3 test_rfid_vers_pc.py      (Ctrl+C pour arrêter)

Ce test ne modifie pas data/comptes.csv (une carte inconnue reste inconnue).
"""

import json
import time

import serial

from src import config
from src.format_carte import brut_vers_decimal, carte_vers_texte
from src.hardware.t02_lecteur_rfid import LecteurRFID, calculer_checksum
from src.models.t02_fichier_comptes import FichierComptes
from src.mqtt_topics import MqttTopics
from src.network.mqtt_client import MqttClient


def afficher_puce(numero: int, identifiant: int, brut: str, trame: bytes, fiches: dict):
    """Affiche dans le terminal tout ce qu'on sait de la puce."""
    texte = carte_vers_texte(identifiant)
    octets_id = " ".join(brut[i:i + 2] for i in range(0, 10, 2))
    checksum_recu = trame[11:13].decode("ascii", errors="replace") if len(trame) == 16 else "??"
    fiche = fiches.get(texte)

    print(f"\n=== Lecture #{numero}  {time.strftime('%H:%M:%S')} ===")
    print(f"  Trame brute (hexa)         : {trame.hex(' ').upper()}")
    print(f"  Trame brute (texte)        : {trame!r}")
    print(f"  ID brut (5 octets)         : {brut}   ({octets_id})")
    print(f"  ID brut en décimal         : {int(brut, 16)}")
    print(f"  Numéro imprimé (décimal)   : {brut_vers_decimal(brut)}   (4 derniers octets)")
    print(f"  {'Identifiant utilisé (' + config.FORMAT_CARTE + ')':27}: {texte}")
    print(f"  Checksum reçu/calculé      : {checksum_recu} / {calculer_checksum(brut):02X}  -> OK")
    if fiche is None:
        suite = (f" -> main.py lui créera un compte de {config.SOLDE_NOUVELLE_CARTE_CENTS} cents"
                 if config.AJOUTER_CARTES_INCONNUES else "")
        print(f"  Compte                     : INCONNU (absent de data/comptes.csv){suite}")
    else:
        solde = fiche["solde"]
        print(f"  Compte                     : {fiche['nom']}, solde = {solde} cents ({solde / 100:.2f} $)")


def publier_au_pc(mqtt: MqttClient, numero: int, identifiant: int, fiches: dict):
    """Envoie la lecture au PC sous la forme d'une réponse « comptes »."""
    texte = carte_vers_texte(identifiant)
    fiche = fiches.get(texte)
    connue = fiche is not None
    solde = fiche["solde"] if connue else None

    message = {
        "id_commande": f"RFID-{numero}",
        "commande": "LECTURE_RFID",
        "resultat": "ACCEPTEE" if connue else "REFUSEE",
        "code": "CARTE_CONNUE" if connue else "CARTE_INCONNUE",
        "message": f"Carte {texte} lue sur le Raspberry Pi",
        "rfid": texte,
        "nom": fiche["nom"] if connue else None,
        "solde": solde,
        "horodatage": time.time(),
    }
    mqtt.publish(MqttTopics.REPONSE_COMPTES, json.dumps(message))
    print(f"  Envoyé au PC               : {MqttTopics.REPONSE_COMPTES}")


# --- MQTT (vrai broker) ---
mqtt = MqttClient(client_id=f"esa-rpi-rfid-test-{config.NUMERO_EQUIPE}", simulate=False)
mqtt.definir_presence(MqttTopics.CONNEXION_RPI)     # bande RPi verte dans l'app PC
mqtt.connect_to_broker()

print(f"Connexion au broker {config.BROKER_IP}:{config.BROKER_PORT} ...")
for _ in range(50):
    if mqtt.is_connected():
        break
    time.sleep(0.1)
print("MQTT : connecté" if mqtt.is_connected() else f"MQTT : PAS connecté ({mqtt.last_error}), on continue quand même")

# --- Lecteur RFID : on lit le port nous-mêmes pour afficher la trame brute,
#     et LecteurRFID (T02) valide la trame et filtre les répétitions ---
port = serial.Serial(config.PORT_RFID, config.VITESSE_RFID, timeout=0.1)
lecteur = LecteurRFID(simuler=True)        # pas de port à lui : on lui donne les octets
fiches = FichierComptes().charger_fiches()     # {carte: {"nom", "solde"}}

print(f"Lecteur RFID sur {config.PORT_RFID} à {config.VITESSE_RFID} bauds")
print(f"Format des cartes : {config.FORMAT_CARTE}. {len(fiches)} comptes chargés. Passe une puce (Ctrl+C pour arrêter).")

tampon = bytearray()
numero = 0
erreurs_vues = 0

try:
    while True:
        donnees = port.read(64)
        if not donnees:
            continue

        for octet in donnees:
            if octet == 0x02:                    # STX : début d'une trame
                tampon = bytearray([octet])
            elif tampon:
                tampon.append(octet)
                if octet == 0x03 or len(tampon) >= 16:
                    trame = bytes(tampon)
                    tampon = bytearray()

                    lecteur.recevoir_octets(trame)
                    identifiant = lecteur.lire_identifiant()

                    if lecteur.nombre_erreurs > erreurs_vues:
                        erreurs_vues = lecteur.nombre_erreurs
                        print(f"\n!! Trame rejetée : {lecteur.derniere_erreur}  ({trame.hex(' ').upper()})")
                    elif identifiant is None:
                        print(".", end="", flush=True)   # même puce maintenue : ignorée
                    else:
                        numero += 1
                        afficher_puce(numero, identifiant, lecteur.dernier_brut, trame, fiches)
                        publier_au_pc(mqtt, numero, identifiant, fiches)

except KeyboardInterrupt:
    print("\nArrêt.")
finally:
    port.close()
    mqtt.disconnect_from_broker()
