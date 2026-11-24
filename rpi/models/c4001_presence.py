"""
Capteur de presence C4001 (SEN0609), UART.

Utilisation :
    from c4001_presence import presence

    etat = presence()   # True = quelqu'un, False = personne, None = capteur muet

Les reglages sont ci-dessous. Apres les avoir modifies, applique-les UNE fois
(ils sont sauvegardes dans la Flash du capteur) :
    python3 c4001_presence.py --configurer

Autres commandes :
    python3 c4001_presence.py            # affiche les changements d'etat
    python3 c4001_presence.py --lire     # affiche la config actuelle du capteur
"""
import sys
import time

import serial

# ======================= REGLAGES =======================
PORT = "/dev/ttyAMA0"
BAUD = 9600                       # None = detection auto (9600 puis 115200)

PORTEE_MAX = 2.0                  # m, 0.6 a 25
DISTANCE_DECLENCHEMENT = 1.4      # m, doit etre <= PORTEE_MAX - 0.6
SENSIBILITE_MAINTIEN = 5          # 0-9, facilite de continuer a voir quelqu'un
SENSIBILITE_DECLENCHEMENT = 5     # 0-9, facilite de detecter (datasheet : 2-6)
LATENCE_CONFIRMATION = 0.3        # s avant de dire "quelqu'un"
LATENCE_DISPARITION = 0.5         # s sans detection avant de dire "personne"

DELAI_MUET = 5                    # s sans donnee du capteur -> presence() = None
# ========================================================

_ser = None
_present = None
_derniere_trame = 0.0
_prochain_essai = 0.0


# ---------- Fonction principale ----------
def presence():
    """True = quelqu'un, False = personne, None = pas de donnees du capteur.
    Ne bloque pas : lit ce que le capteur a envoye depuis le dernier appel."""
    global _present, _derniere_trame, _prochain_essai

    if _ser is None:
        if time.time() < _prochain_essai:
            return None
        try:
            _ouvrir()
        except (RuntimeError, serial.SerialException):
            _prochain_essai = time.time() + 10   # evite de bloquer a chaque appel
            return None

    try:
        texte = _ser.read(_ser.in_waiting).decode(errors="ignore")
    except (serial.SerialException, OSError):
        fermer()
        return None

    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if ligne.startswith(("$DFHPD", "$DFDMD")) and ligne.endswith("*"):
            champs = ligne.strip("$*").split(",")
            if len(champs) > 1:
                _present = champs[1].strip() == "1"
                _derniere_trame = time.time()

    if time.time() - _derniere_trame > DELAI_MUET:
        return None
    return _present


def fermer():
    global _ser
    if _ser is not None:
        _ser.close()
        _ser = None


# ---------- Configuration ----------
def configurer():
    """Ecrit les reglages du fichier dans le capteur (Flash), puis affiche
    la config reelle. A faire une seule fois apres chaque changement."""
    if DISTANCE_DECLENCHEMENT > PORTEE_MAX - 0.6:
        raise ValueError("DISTANCE_DECLENCHEMENT doit etre <= PORTEE_MAX - 0.6")
    if _ser is None:
        _ouvrir()

    _envoyer("sensorStop")
    time.sleep(0.5)
    _ser.write(b"setRunApp 0\r\n")            # mode presence (pas de reponse)
    time.sleep(0.5)
    for commande in (
        f"setRange 0.6 {PORTEE_MAX}",
        f"setTrigRange {DISTANCE_DECLENCHEMENT}",
        f"setSensitivity {SENSIBILITE_MAINTIEN} {SENSIBILITE_DECLENCHEMENT}",
        f"setLatency {LATENCE_CONFIRMATION} {LATENCE_DISPARITION}",
        "saveConfig",
        "sensorStart",
    ):
        rep = _envoyer(commande)
        ok = rep and "Error" not in rep
        print(f"  {'ok       ' if ok else 'ATTENTION'} {commande:<32} {'' if ok else rep}")

    print("Config reelle du capteur :")
    for cle, val in lire_config().items():
        print(f"  {cle:<14} {val}")


def lire_config():
    """Config reelle du capteur (l'arrete puis le redemarre)."""
    if _ser is None:
        _ouvrir()
    _envoyer("sensorStop")
    time.sleep(0.3)
    config = {}
    for nom in ("Range", "TrigRange", "Sensitivity", "Latency", "Inhibit"):
        for morceau in _envoyer("get" + nom).split("|"):
            if "Response" in morceau:
                config[nom] = morceau.replace("Response", "").strip()
    _envoyer("sensorStart")
    return config


# ---------- Interne ----------
def _ouvrir():
    global _ser
    baud = BAUD or _detecter_debit()
    _ser = serial.Serial(PORT, baud, timeout=0.5)


def _detecter_debit():
    for baud in (9600, 115200):
        with serial.Serial(PORT, baud, timeout=1) as ser:
            ser.write(b"sensorStart\r\n")     # redemarre le capteur s'il etait arrete
            time.sleep(0.5)
            ser.reset_input_buffer()
            fin = time.time() + 4
            while time.time() < fin:
                if "$DF" in ser.readline().decode(errors="ignore"):
                    return baud
    raise RuntimeError(
        "Aucune trame du capteur : verifie le cablage, l'alimentation "
        "et qu'aucun autre programme n'utilise le port."
    )


def _envoyer(commande, attente=2.0):
    """Envoie une commande, retourne les lignes recues jusqu'a Done/Error."""
    _ser.reset_input_buffer()
    _ser.write((commande + "\r\n").encode())
    lignes = []
    fin = time.time() + attente
    while time.time() < fin:
        ligne = _ser.readline().decode(errors="ignore").strip()
        if not ligne or ligne.startswith("$DF"):
            continue
        lignes.append(ligne)
        if "Done" in ligne or "Error" in ligne:
            break
    return " | ".join(lignes)


# ---------- Test en ligne de commande ----------
if __name__ == "__main__":
    if "--configurer" in sys.argv:
        configurer()
    elif "--lire" in sys.argv:
        for cle, val in lire_config().items():
            print(f"{cle:<14} {val}")
    else:
        noms = {True: "il y a quelqu'un", False: "personne", None: "inconnu"}
        precedent = "init"
        try:
            while True:
                etat = presence()
                if etat != precedent:
                    print(f"[{time.strftime('%H:%M:%S')}] {noms[etat]}")
                    precedent = etat
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
    fermer()