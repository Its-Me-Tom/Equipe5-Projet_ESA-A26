"""Diagnostic du VRAI bus CAN (HAT MCP2515 du PCB-10, interface can0).

Émet le heartbeat du RPi (0x040) pendant 10 secondes et affiche toutes
les trames reçues. Sert à vérifier le câblage avant les tests en mode réel.

Avant : sudo ip link set can0 up type can bitrate 500000

Exécution (sur le Raspberry Pi) : python diagnostic_can.py
"""

import sys
import time

from src.hardware import protocole_can as proto
from src.hardware.can_manager import CanManager

can = CanManager(simulate=False)

if not can.connect():
    print("Bus CAN inaccessible :", can.last_error)
    sys.exit(1)

print("Bus can0 ouvert. Émission du heartbeat pendant 10 s...")

fin = time.monotonic() + 10
prochain_heartbeat = 0.0
compteur = 0

while time.monotonic() < fin:
    if time.monotonic() >= prochain_heartbeat:
        prochain_heartbeat = time.monotonic() + 0.5
        envoye = can.send(proto.HEARTBEAT_RPI, [compteur, proto.HEARTBEAT_PRET])
        print(f"TX : 0x040 compteur={compteur}" if envoye else f"TX : ÉCHEC {can.last_error}")
        compteur = (compteur + 1) % 256

    message = can.receive()

    while message is not None:
        donnees = " ".join(f"{octet:02X}" for octet in message.data)
        print(f"RX : 0x{message.arbitration_id:03X} [{donnees}]")
        message = can.receive()

    time.sleep(0.01)

can.disconnect()
print("Fin du diagnostic.")
