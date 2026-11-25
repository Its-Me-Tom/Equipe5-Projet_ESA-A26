"""Test simple du lecteur RFID ID-12LA. Aucune installation requise.

    python3 rfid_simple.py                  (port /dev/ttyAMA0)
    python3 rfid_simple.py /dev/serial0     (autre port)

Affiche chaque puce présentée : l'ID brut (5 octets en hexa) et le numéro
imprimé sur la puce (décimal des 4 derniers octets). Ctrl+C pour arrêter.
"""

import os
import sys
import termios

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyAMA0"

# Ouvrir le port série et le régler à 9600 bauds, 8N1, mode brut
port = os.open(PORT, os.O_RDONLY | os.O_NOCTTY)

settings = termios.tcgetattr(port)
settings[0] = 0                                             # entrée : aucun traitement
settings[1] = 0                                             # sortie : aucun traitement
settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # 8 bits, réception active
settings[3] = 0                                             # mode brut (pas d'écho)
settings[4] = termios.B9600                                 # vitesse en entrée
settings[5] = termios.B9600                                 # vitesse en sortie
settings[6][termios.VMIN] = 1                               # attendre au moins 1 octet
settings[6][termios.VTIME] = 0
termios.tcsetattr(port, termios.TCSANOW, settings)

print(f"Port {PORT} ouvert à 9600 bauds. Passe une puce (Ctrl+C pour arrêter).")

frame = b""     # octets de la trame en cours

try:
    while True:
        byte = os.read(port, 1)

        if byte == b"\x02":         # STX : début d'une trame
            frame = b""

        elif byte == b"\x03":       # ETX : fin de la trame
            # La trame contient : 10 caractères de numéro, 2 de checksum, CR, LF
            text = frame.decode("ascii", errors="replace").strip()
            card, checksum = text[:10], text[10:12]

            # Checksum = XOR des 5 octets du numéro
            try:
                computed = 0
                for i in range(0, 10, 2):
                    computed ^= int(card[i:i + 2], 16)
                ok = computed == int(checksum, 16)
            except ValueError:
                ok = False

            # Numéro imprimé sur la puce = 4 derniers octets en décimal, 10 chiffres
            try:
                printed = f"{int(card, 16) & 0xFFFFFFFF:010d}"
            except ValueError:
                printed = "??????????"

            print(f"ID brut : {card}   numéro imprimé (décimal) : {printed}"
                  f"   checksum : {'OK' if ok else 'INCORRECT'}   (reçu : {text!r})")

        else:
            frame += byte

except KeyboardInterrupt:
    print("\nArrêt.")

finally:
    os.close(port)
