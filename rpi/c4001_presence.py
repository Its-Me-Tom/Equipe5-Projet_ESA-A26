"""
Module de presence pour le capteur C4001 (SEN0609) sur P11 (UART).

Utilisation dans ton application :

    from c4001 import CapteurPresence

    capteur = CapteurPresence(configurer=True)   # configurer=True la 1re fois seulement
    ...
    print(capteur.etat())        # "il y a quelqu'un" ou "personne"
    if capteur.est_present():    # True / False
        ...
    capteur.fermer()             # a la fin

La lecture se fait en arriere-plan : etat() et est_present() repondent
immediatement avec la derniere valeur recue du capteur.
Un seul programme peut utiliser le port serie a la fois.
"""
import threading
import time

import serial

PORT = "/dev/ttyAMA0"
BAUDS = (9600, 115200)


class CapteurPresence:
    def __init__(self, port=PORT, baud=None, configurer=False,
                 portee_max=3.0, latence_confirmation=0.5, latence_disparition=5):
        """
        portee_max            : distance max de detection en m (0.6 a 25)
        latence_confirmation  : s avant de declarer "quelqu'un" (apres detection)
        latence_disparition   : s sans detection avant de declarer "personne"
        configurer            : True = envoie la configuration au capteur et la
                                sauvegarde (a faire une seule fois, ou si tu
                                changes les parametres ci-dessus)
        """
        self._port = port
        self._baud = baud or self._detecter_debit()
        self._ser = serial.Serial(port, self._baud, timeout=1)
        self._present = False
        self._derniere_trame = 0.0
        self._actif = True

        if configurer:
            self._configurer(portee_max, latence_confirmation, latence_disparition)

        self._thread = threading.Thread(target=self._lire, daemon=True)
        self._thread.start()

    # ---------- API publique ----------
    def est_present(self):
        """True s'il y a quelqu'un dans la zone de detection."""
        return self._present

    def etat(self):
        """"il y a quelqu'un", "personne", ou "inconnu" si le capteur ne repond plus."""
        if time.time() - self._derniere_trame > 5:
            return "inconnu"
        return "il y a quelqu'un" if self._present else "personne"

    def fermer(self):
        self._actif = False
        self._thread.join(timeout=2)
        self._ser.close()

    # ---------- Interne ----------
    def _detecter_debit(self):
        for baud in BAUDS:
            with serial.Serial(self._port, baud, timeout=1) as ser:
                ser.reset_input_buffer()
                fin = time.time() + 4
                while time.time() < fin:
                    if "$DF" in ser.readline().decode(errors="ignore"):
                        return baud
        raise RuntimeError(
            "Aucune trame du capteur. Verifie le selecteur UART (coupure complete "
            "de l'alimentation), le cablage P11 et qu'aucun autre programme n'utilise le port."
        )

    def _envoyer(self, commande, attente=2.0):
        self._ser.reset_input_buffer()
        self._ser.write((commande + "\r\n").encode())
        fin = time.time() + attente
        while time.time() < fin:
            ligne = self._ser.readline().decode(errors="ignore").strip()
            if "Done" in ligne or "Error" in ligne:
                return ligne
        return ""

    def _configurer(self, portee_max, confirm, disparition):
        self._envoyer("sensorStop")
        time.sleep(0.5)
        self._ser.write(b"setRunApp 0\r\n")  # mode presence (pas de reponse)
        time.sleep(0.5)
        self._envoyer(f"setRange 0.6 {portee_max}")
        self._envoyer("setSensitivity 6 5")
        self._envoyer(f"setLatency {confirm} {disparition}")
        self._envoyer("saveConfig")
        self._envoyer("sensorStart")

    def _lire(self):
        while self._actif:
            try:
                ligne = self._ser.readline().decode(errors="ignore").strip()
            except serial.SerialException:
                time.sleep(0.5)
                continue
            if ligne.startswith("$DFHPD"):          # mode presence
                champs = ligne.strip("$*").split(",")
                self._present = champs[1].strip() == "1"
                self._derniere_trame = time.time()
            elif ligne.startswith("$DFDMD"):        # mode distance (au cas ou)
                champs = ligne.strip("$*").split(",")
                self._present = champs[1].strip() == "1"
                self._derniere_trame = time.time()


if __name__ == "__main__":
    # Test rapide : python3 c4001.py
    capteur = CapteurPresence(configurer=True)
    try:
        while True:
            print(capteur.etat())
            time.sleep(1)
    except KeyboardInterrupt:
        capteur.fermer()