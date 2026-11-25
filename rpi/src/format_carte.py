"""Conversion des identifiants de carte RFID.

Le lecteur ID-12LA envoie 5 octets, écrits en 10 caractères hexadécimaux
(ex. "110082EEC8" = 11 00 82 EE C8). On appelle ça l'ID BRUT.

Le numéro IMPRIMÉ sur la puce (ex. "0008580808") est le DÉCIMAL des 4
derniers octets : 0x0082EEC8 = 8580808, écrit sur 10 chiffres. Le premier
octet (0x11, code du fabricant) n'est pas imprimé.

config.FORMAT_CARTE choisit le numéro utilisé partout dans le code :
    "DECIMAL" : le numéro imprimé, 10 chiffres     -> "0008580808"
    "BRUT"    : les 5 octets, 10 caractères hexa   -> "110082EEC8"

    - Dans le code, une carte est un entier (int), comme dans le contrat T02.
    - Dans les CSV et les messages MQTT, c'est le texte de 10 caractères.
La conversion est toujours faite par les fonctions de ce fichier.
"""

from src import config

CHIFFRES_CARTE = 10
MASQUE_4_OCTETS = 0xFFFFFFFF      # garde les 4 derniers octets
CHIFFRES_DECIMAUX = set("0123456789")
CHIFFRES_HEXA = set("0123456789ABCDEF")


def _format() -> str:
    """Format choisi dans config.py (relu à chaque appel)."""
    if config.FORMAT_CARTE not in ("DECIMAL", "BRUT"):
        raise ValueError(f"config.FORMAT_CARTE doit être \"DECIMAL\" ou \"BRUT\", pas {config.FORMAT_CARTE!r}")

    return config.FORMAT_CARTE


def brut_vers_decimal(texte_brut: str) -> str:
    """ID brut -> numéro imprimé sur la puce : "110082EEC8" -> "0008580808"."""
    return f"{int(texte_brut, 16) & MASQUE_4_OCTETS:0{CHIFFRES_CARTE}d}"


def brut_vers_carte(texte_brut: str) -> int:
    """ID brut reçu du lecteur -> identifiant utilisé par le code.

    DECIMAL : seulement les 4 derniers octets (le numéro imprimé).
    BRUT    : les 5 octets.
    Lève ValueError si le texte n'est pas 10 caractères hexadécimaux.
    """
    texte_brut = str(texte_brut).strip().upper()

    if len(texte_brut) != CHIFFRES_CARTE or not set(texte_brut) <= CHIFFRES_HEXA:
        raise ValueError(f"ID brut invalide : {texte_brut!r}")

    valeur = int(texte_brut, 16)

    if _format() == "DECIMAL":
        return valeur & MASQUE_4_OCTETS

    return valeur


def carte_vers_brut(identifiant_rfid: int) -> str:
    """Identifiant -> ID brut de 10 caractères hexa (pour simuler une trame).

    En DECIMAL, le premier octet est perdu : il est remplacé par 00.
    """
    return f"{identifiant_rfid:0{CHIFFRES_CARTE}X}"


def carte_vers_texte(identifiant_rfid: int) -> str:
    """Entier -> texte de 10 caractères, dans le format choisi."""
    if _format() == "DECIMAL":
        return f"{identifiant_rfid:0{CHIFFRES_CARTE}d}"

    return f"{identifiant_rfid:0{CHIFFRES_CARTE}X}"


def texte_vers_carte(texte: str) -> int:
    """Texte de 10 caractères, dans le format choisi -> entier.

    DECIMAL : 10 chiffres (ex. "0008580808"), au plus 4294967295.
    BRUT    : 10 caractères hexadécimaux (ex. "110082EEC8").
    Lève ValueError si le texte n'a pas le bon format.
    """
    texte = str(texte).strip().upper()

    if len(texte) != CHIFFRES_CARTE:
        raise ValueError(f"Identifiant de carte invalide : {texte!r}")

    if _format() == "DECIMAL":
        if not set(texte) <= CHIFFRES_DECIMAUX or int(texte) > MASQUE_4_OCTETS:
            raise ValueError(f"Numéro de carte invalide (10 chiffres attendus) : {texte!r}")

        return int(texte)

    if not set(texte) <= CHIFFRES_HEXA:
        raise ValueError(f"Identifiant de carte invalide (10 caractères hexa attendus) : {texte!r}")

    return int(texte, 16)


def decrire_carte(texte_brut: str) -> str:
    """Les deux écritures d'une puce, pour l'affichage.

    "110082EEC8" -> "ID brut 110082EEC8 | numéro imprimé (décimal) 0008580808"
    """
    texte_brut = str(texte_brut).strip().upper()

    return f"ID brut {texte_brut} | numéro imprimé (décimal) {brut_vers_decimal(texte_brut)}"
