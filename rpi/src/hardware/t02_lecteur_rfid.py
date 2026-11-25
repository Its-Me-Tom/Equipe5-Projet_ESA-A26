"""T02 — Lecteur RFID ID-12LA (« LecteurRFID » du contrat).

Le lecteur envoie une trame ASCII par l'UART (9600 bauds, 8N1) chaque fois
qu'une carte est présentée (broche FORMAT à GND = format ASCII) :

    STX | 10 caractères hexa | 2 caractères de checksum | CR | LF | ETX
    0x02|      numéro        |  XOR des 5 octets        |0x0D|0x0A|0x03

Total : 16 octets. Le checksum est le OU exclusif (XOR) des 5 octets du
numéro, écrit lui aussi en 2 caractères hexadécimaux.

Les 10 caractères forment l'ID BRUT (ex. "110082EEC8"). Il est converti
selon config.FORMAT_CARTE par src/format_carte.py (ex. en DECIMAL : le
numéro imprimé sur la puce, "0008580808").
"""

from src import config
from src.format_carte import CHIFFRES_CARTE, brut_vers_carte, carte_vers_brut
from src.horloge import Horloge

STX = 0x02
ETX = 0x03
LONGUEUR_TRAME = 16


class TrameRFIDInvalide(Exception):
    """Trame UART incomplète ou incorrecte."""


def calculer_checksum(texte_carte: str) -> int:
    """XOR des 5 octets représentés par les 10 caractères hexadécimaux."""
    checksum = 0

    for position in range(0, CHIFFRES_CARTE, 2):
        checksum ^= int(texte_carte[position:position + 2], 16)

    return checksum


def construire_trame(texte_carte: str) -> bytes:
    """Construit la trame qu'enverrait le lecteur (pour la simulation)."""
    texte_carte = texte_carte.upper()
    texte = f"{texte_carte}{calculer_checksum(texte_carte):02X}"

    return bytes([STX]) + texte.encode("ascii") + b"\r\n" + bytes([ETX])


def decoder_trame(trame: bytes) -> int:
    """Valide une trame complète et retourne l'identifiant de la carte
    (dans le format de config.FORMAT_CARTE).

    Lève TrameRFIDInvalide si la trame est incomplète ou incorrecte.
    """
    return brut_vers_carte(decoder_trame_brut(trame))


def decoder_trame_brut(trame: bytes) -> str:
    """Valide une trame complète et retourne l'ID brut : "110082EEC8".

    Lève TrameRFIDInvalide si la trame est incomplète ou incorrecte.
    """
    if len(trame) != LONGUEUR_TRAME:
        raise TrameRFIDInvalide(f"Trame incomplète ({len(trame)} octets sur 16)")

    if trame[0] != STX or trame[-1] != ETX or trame[13:15] != b"\r\n":
        raise TrameRFIDInvalide("Délimiteurs STX / CR LF / ETX incorrects")

    try:
        texte = trame[1:13].decode("ascii").upper()
        brut = texte[:CHIFFRES_CARTE]
        brut_vers_carte(brut)                       # vérifie les 10 caractères hexa
        checksum_recu = int(texte[CHIFFRES_CARTE:], 16)
    except ValueError:
        raise TrameRFIDInvalide("Caractères non hexadécimaux dans la trame")

    if checksum_recu != calculer_checksum(brut):
        raise TrameRFIDInvalide("Checksum incorrect")

    return brut


class LecteurRFID:
    """Lit les cartes RFID, avec le vrai lecteur ou en simulation."""

    def __init__(self, simuler: bool | None = None, horloge: Horloge | None = None):
        self.simuler = config.SIMULER_RFID if simuler is None else simuler
        self.horloge = horloge or Horloge()

        self.port_serie = None
        self.derniere_erreur = ""
        self.nombre_erreurs = 0          # nombre de trames rejetées

        self._tampon = bytearray()       # trame en cours de réception
        self._cartes = []                # (identifiant, ID brut) validés, pas encore lus
        self.dernier_brut = None         # ID brut de la dernière carte retournée
        self._derniere_carte = None      # dernière carte acceptée
        self._dernier_moment = None      # moment où elle a été vue

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------

    def connecter(self) -> bool:
        """Ouvre le port série du lecteur. Retourne False si impossible."""
        if self.simuler:
            return True

        try:
            import serial   # pyserial : requis seulement avec le vrai lecteur

            # timeout=0 : la lecture ne bloque jamais
            self.port_serie = serial.Serial(
                port=config.PORT_RFID,
                baudrate=config.VITESSE_RFID,
                timeout=0,
            )
            return True

        except Exception as erreur:
            self.port_serie = None
            self.derniere_erreur = f"Lecteur RFID inaccessible : {erreur}"
            return False

    def deconnecter(self):
        if self.port_serie is not None:
            self.port_serie.close()
            self.port_serie = None

    def est_disponible(self) -> bool:
        """True si le lecteur peut être utilisé."""
        return self.simuler or self.port_serie is not None

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def est_carte_presente(self) -> bool:
        """True si une carte a été vue pendant le délai d'anti-répétition.

        Le signal RNG du lecteur n'est pas câblé : la présence est déduite
        de la dernière lecture valide.
        """
        if self._dernier_moment is None:
            return False

        ecoule = self.horloge.monotone() - self._dernier_moment
        return ecoule < config.DELAI_REPETITION_RFID_S

    def lire_identifiant(self) -> int | None:
        """Retourne l'identifiant d'une NOUVELLE carte, sinon None.

        Une carte maintenue devant le lecteur n'est retournée qu'une fois.
        """
        self._lire_port_serie()

        if not self._cartes:
            return None

        identifiant, self.dernier_brut = self._cartes.pop(0)
        return identifiant

    def _lire_port_serie(self):
        """Récupère les octets reçus du vrai lecteur, sans bloquer."""
        if self.port_serie is None:
            return

        try:
            donnees = self.port_serie.read(64)
        except Exception as erreur:
            self.derniere_erreur = f"Erreur de lecture RFID : {erreur}"
            self.deconnecter()
            return

        if donnees:
            self.recevoir_octets(donnees)

    def recevoir_octets(self, donnees: bytes):
        """Traite des octets reçus. Sert aussi à injecter une trame simulée."""
        for octet in donnees:
            if octet == STX:
                # Début d'une nouvelle trame. S'il restait des octets, la
                # trame précédente n'a jamais été terminée.
                if self._tampon:
                    self._rejeter("Trame incomplète")

                self._tampon = bytearray([octet])

            elif self._tampon:
                self._tampon.append(octet)

                if octet == ETX or len(self._tampon) >= LONGUEUR_TRAME:
                    self._traiter_trame(bytes(self._tampon))
                    self._tampon = bytearray()

            # Sinon : octet reçu hors d'une trame, ignoré.

    def _traiter_trame(self, trame: bytes):
        try:
            brut = decoder_trame_brut(trame)
        except TrameRFIDInvalide as erreur:
            self._rejeter(str(erreur))
            return

        self._accepter(brut_vers_carte(brut), brut)

    def _rejeter(self, raison: str):
        self.nombre_erreurs += 1
        self.derniere_erreur = raison

    def _accepter(self, identifiant: int, brut: str):
        """Garde la carte, sauf si c'est une répétition de la même carte."""
        maintenant = self.horloge.monotone()

        repetee = (
            identifiant == self._derniere_carte
            and self._dernier_moment is not None
            and maintenant - self._dernier_moment < config.DELAI_REPETITION_RFID_S
        )

        self._derniere_carte = identifiant
        self._dernier_moment = maintenant     # une carte maintenue prolonge le délai

        if not repetee:
            self._cartes.append((identifiant, brut))

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simuler_carte(self, identifiant: int):
        """Simule la présentation d'une carte (trame ASCII complète)."""
        self.recevoir_octets(construire_trame(carte_vers_brut(identifiant)))
