"""T02-01 — Lecture (simulée ou avec le vrai lecteur).

Essai (énoncé T02) : un message UART ASCII valide est décodé; un message
incomplet ou un identifiant invalide est rejeté. Une carte maintenue ou
repassée tout de suite ne déclenche qu'une seule lecture.

Ce que le terminal montre : chaque trame en octets (hexa et texte), le
checksum calculé, l'ID brut (5 octets), le numéro imprimé sur la puce
(décimal des 4 derniers octets), l'identifiant utilisé par le code selon
config.FORMAT_CARTE, et les rejets avec leur raison.

Matériel minimal
    MATERIEL_REEL = False : aucun (trames construites par le test).
    MATERIEL_REEL = True  : lecteur RFID ID-12LA (PCB-07, D0 en 3,3 V sur le
                            RX du PMOD type 3) et une ou deux puces.
                            Rien d'autre (ni CAN, ni MQTT).

Exécution : python3 test_t02_01_lecture_simulee.py
"""


import atexit
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from src import config
from src.format_carte import brut_vers_carte, brut_vers_decimal, carte_vers_texte, decrire_carte
from src.hardware.t02_lecteur_rfid import calculer_checksum, construire_trame, decoder_trame, decoder_trame_brut, LecteurRFID
from src.horloge import Horloge


# ----------------------------------------------------------------------
# RÉGLAGES DU TEST (modifiez ici)
# ----------------------------------------------------------------------
MATERIEL_REEL = True       # True = vrai lecteur RFID (config.PORT_RFID) | False = simulation
DEUXIEME_PUCE = True       # mode réel : l'opérateur a une 2e puce différente

# lancer_tous_les_tests.py force la simulation (ESA_SIMULATION=1) sans modifier les réglages
if os.environ.get("ESA_SIMULATION") == "1":
    MATERIEL_REEL = False


# ======================================================================
# OUTILS DU TEST — recopiés dans chaque test pour qu'il soit autonome :
# ce fichier n'a besoin d'aucun autre fichier de test, seulement de src/.
# Rien n'est écrit sur le disque : tout s'affiche dans le terminal.
# ======================================================================
# ---------- Affichage et vérifications : tout est écrit dans le terminal ----------
_VERIFICATIONS = []                     # (description, réussie)
_DEBUT = time.monotonic()
_EN_ATTENTE = []                        # lignes venues d'un autre thread (ex. MQTT), affichées dans l'ordre


def afficher_en_attente():
    """Affiche les lignes produites par les autres threads (réseau MQTT)."""
    while _EN_ATTENTE:
        print(_EN_ATTENTE.pop(0), flush=True)


def titre(nom: str, mode: str):
    """En-tête du test."""
    print("\n" + "=" * 78)
    print(nom)
    print(f"Mode : {mode}")
    print("=" * 78)


def etape(texte: str):
    """Début d'une étape de l'essai."""
    afficher_en_attente()
    print(f"\n--- {texte} " + "-" * max(3, 72 - len(texte)))


def info(texte: str = ""):
    """Donnée ou explication affichée pendant l'essai."""
    afficher_en_attente()
    print(f"    {texte}", flush=True)


def verifier(description: str, obtenu, attendu) -> bool:
    """Compare la valeur obtenue à la valeur attendue et affiche le verdict."""
    reussie = obtenu == attendu
    _VERIFICATIONS.append((description, reussie))
    afficher_en_attente()

    if reussie:
        valeur = repr(obtenu)
        separateur = "\n            " if len(valeur) + len(description) > 90 else " "
        print(f"  [OK]    {description} :{separateur}{valeur}")
    else:
        print(f"  [ÉCHEC] {description}")
        print(f"            attendu : {attendu!r}")
        print(f"            obtenu  : {obtenu!r}")

    return reussie


def consigne(texte: str):
    """Action à faire par l'opérateur (mode réel)."""
    afficher_en_attente()
    print(f"\n>>> {texte}", flush=True)


def confirmer(question: str) -> bool:
    """Demande à l'opérateur ce qu'il voit (mode réel)."""
    reponse = input(f"\n>>> {question} (o/n) : ").strip().lower()
    return verifier(f"Observation : {question}", reponse, "o")


def erreur_de(fonction, *arguments, **options) -> str:
    """Nom de l'exception levée par l'appel (affichée), ou "aucune"."""
    try:
        fonction(*arguments, **options)
    except Exception as erreur:
        info(f"exception levée : {type(erreur).__name__} — {erreur}")
        return type(erreur).__name__

    return "aucune"


def tableau(entetes: list, lignes: list):
    """Affiche un petit tableau aligné."""
    lignes = [[("" if valeur is None else str(valeur)) for valeur in ligne] for ligne in lignes]
    largeurs = [max(len(str(texte)) for texte in colonne) for colonne in zip(entetes, *lignes)]
    print("    " + "  ".join(str(texte).ljust(largeur) for texte, largeur in zip(entetes, largeurs)))
    print("    " + "  ".join("-" * largeur for largeur in largeurs))

    for ligne in lignes:
        print("    " + "  ".join(texte.ljust(largeur) for texte, largeur in zip(ligne, largeurs)))

    if not lignes:
        print("    (aucune ligne)")


def arreter_test(message: str):
    """Arrête le test quand le matériel demandé ne répond pas."""
    print(f"\nTEST IMPOSSIBLE : {message}")
    print("RÉSULTAT : NON EXÉCUTÉ (matériel absent ou mal configuré)")
    sys.exit(2)


def terminer():
    """Affiche le bilan et termine (code 0 = réussi, 1 = échoué)."""
    echecs = [description for description, reussie in _VERIFICATIONS if not reussie]
    afficher_en_attente()
    print("\n" + "=" * 78)

    if echecs:
        print(f"RÉSULTAT : ÉCHOUÉ — {len(echecs)} vérification(s) en échec sur {len(_VERIFICATIONS)}")
        for description in echecs:
            print(f"   - {description}")
    else:
        print(f"RÉSULTAT : RÉUSSI — {len(_VERIFICATIONS)}/{len(_VERIFICATIONS)} vérifications "
              f"({time.monotonic() - _DEBUT:.1f} s)")

    print("=" * 78)
    sys.exit(1 if echecs else 0)


def _sur_exception(type_erreur, erreur, trace):
    sys.__excepthook__(type_erreur, erreur, trace)
    print("RÉSULTAT : ERREUR — le test s'est arrêté sur l'exception ci-dessus")


sys.excepthook = _sur_exception


# ---------- Données de départ (dossier temporaire, effacé à la fin) ----------
# data/ n'est jamais touché : le test travaille dans une copie temporaire.
# Cartes fictives sur 4 octets : valides en DECIMAL et en BRUT (config.FORMAT_CARTE).
# Leur texte suit le format choisi : "1111111111" en DECIMAL, "00423A35C7" en BRUT.
CARTE_A = 1111111111            # 2500 ¢ au départ
CARTE_B = 2222222222            # 1000 ¢
CARTE_C = 3333333333            #    0 ¢
CARTE_INCONNUE = 4000000000     # aucun compte
TXT_A, TXT_B, TXT_C, TXT_INCONNUE = (carte_vers_texte(c) for c in (CARTE_A, CARTE_B, CARTE_C, CARTE_INCONNUE))
COMPTES_DEPART = {TXT_A: 2500, TXT_B: 1000, TXT_C: 0}
NOMS_DEPART = {TXT_A: "Carte A", TXT_B: "Carte B", TXT_C: "Carte C"}


def creer_dossier_donnees(comptes: dict | None = None, noms: dict | None = None) -> Path:
    """Crée un dossier temporaire avec comptes.csv (rfid,nom,solde) et operations.csv."""
    dossier = Path(tempfile.mkdtemp(prefix="esa_test_"))
    atexit.register(shutil.rmtree, dossier, True)
    comptes = COMPTES_DEPART if comptes is None else comptes
    noms = NOMS_DEPART if noms is None else noms

    lignes = ["rfid,nom,solde"] + [f"{carte},{noms.get(carte, carte)},{solde}" for carte, solde in comptes.items()]
    (dossier / "comptes.csv").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    (dossier / "operations.csv").write_text("operation_id,rfid,type,montant\n", encoding="utf-8")

    return dossier


def afficher_fichier(chemin: Path):
    """Affiche le contenu d'un fichier de données, ligne par ligne."""
    if not chemin.exists():
        info(f"{chemin.name} : (absent)")
        return

    info(f"{chemin.name} :")

    for ligne in chemin.read_text(encoding="utf-8").splitlines() or ["(vide)"]:
        info(f"   | {ligne}")


def carte_txt(identifiant: int | None) -> str | None:
    """Identifiant de carte en texte, format de config.FORMAT_CARTE (ex. "1111111111"), ou None."""
    return None if identifiant is None else carte_vers_texte(identifiant)


def argent(cents) -> str:
    """Montant lisible : 2500 -> "2500 ¢ (25,00 $)"."""
    if not isinstance(cents, int):
        return repr(cents)

    return f"{cents} ¢ ({cents / 100:.2f} $)".replace(".", ",")


# ---------- Horloge du test ----------
class HorlogeTest(Horloge):
    """Horloge qu'on peut faire avancer d'un coup (avancer(600) = 10 min).

    temps_reel = False : le temps n'avance QUE par avancer() (simulation :
                         60 s de délai passent instantanément).
    temps_reel = True  : le temps avance aussi tout seul (vrai matériel).
    """

    def __init__(self, temps_reel: bool = False):
        self.temps_reel = temps_reel
        self._depart = time.monotonic()
        self._decalage = 0.0

    def _ecoule(self) -> float:
        reel = time.monotonic() - self._depart if self.temps_reel else 0.0
        return reel + self._decalage

    def maintenant(self) -> float:
        return 1_800_000_000.0 + self._ecoule()

    def monotone(self) -> float:
        return 1000.0 + self._ecoule()

    def avancer(self, secondes: float):
        self._decalage += secondes


def un_tour_de_temps(horloge: HorlogeTest):
    """Fait passer une période de boucle (vraie attente en temps réel)."""
    if horloge.temps_reel:
        time.sleep(config.PERIODE_BOUCLE_S)
    else:
        horloge.avancer(config.PERIODE_BOUCLE_S)


# ======================================================================
# ESSAI
# ======================================================================
def montrer_trame(description: str, trame: bytes):
    """Affiche une trame octet par octet."""
    info(f"{description}")
    info(f"   octets : {trame.hex(' ').upper()}")
    info(f"   texte  : {trame!r}")


def attendu(brut: str) -> str:
    """Identifiant attendu pour un ID brut, dans le format de config.FORMAT_CARTE."""
    return carte_txt(brut_vers_carte(brut))


titre("T02-01 — Lecture RFID",
      f"MATÉRIEL RÉEL : lecteur ID-12LA sur {config.PORT_RFID} à {config.VITESSE_RFID} bauds"
      if MATERIEL_REEL else "SIMULATION : aucun matériel")

# ----------------------------------------------------------------------
etape("1. Décodage d'une trame valide (format ASCII de l'ID-12LA)")
info("Trame : STX | 10 caractères hexa | 2 caractères de checksum | CR LF | ETX (16 octets)")
trame = construire_trame("110082EEC8")
montrer_trame("Trame que le lecteur envoie pour la puce 110082EEC8 (numéro imprimé 0008580808) :", trame)
info("   STX=02 | '110082EEC8' = ID brut | 'B5' = checksum | 0D 0A = CR LF | ETX=03")
info(f"Checksum = XOR de 11 00 82 EE C8 = {calculer_checksum('110082EEC8'):02X}")
verifier("Longueur de la trame (octets)", len(trame), 16)
verifier("Checksum de la trame", trame[11:13], b"B5")
verifier("ID brut décodé", decoder_trame_brut(trame), "110082EEC8")
info(decrire_carte(decoder_trame_brut(trame)))
info(f"Format choisi dans config.py : FORMAT_CARTE = {config.FORMAT_CARTE!r}")
verifier(f"Identifiant utilisé par le code ({config.FORMAT_CARTE})", carte_txt(decoder_trame(trame)),
         "0008580808" if config.FORMAT_CARTE == "DECIMAL" else "110082EEC8")
verifier("Autre carte décodée", carte_txt(decoder_trame(construire_trame("ABCDEF0123"))), attendu("ABCDEF0123"))

# ----------------------------------------------------------------------
etape("1b. ID brut -> numéro imprimé sur la puce (décimal des 4 derniers octets)")
for brut, imprime in [("110082EEC8", "0008580808"), ("0000000000", "0000000000"), ("FFFFFFFFFF", "4294967295")]:
    info(f"{brut} = {' '.join(brut[i:i + 2] for i in range(0, 10, 2))} -> 4 derniers octets "
         f"0x{brut[2:]} = {int(brut[2:], 16)}")
    verifier(f"Numéro imprimé de {brut}", brut_vers_decimal(brut), imprime)

format_choisi = config.FORMAT_CARTE
for essai_format, texte_attendu in (("DECIMAL", "0008580808"), ("BRUT", "110082EEC8")):
    config.FORMAT_CARTE = essai_format
    verifier(f"FORMAT_CARTE = {essai_format!r} : la puce 110082EEC8 devient", carte_txt(decoder_trame(trame)),
             texte_attendu)
config.FORMAT_CARTE = format_choisi

# ----------------------------------------------------------------------
etape("2. Trames incomplètes ou invalides : rejetées")
cas_invalides = {
    "Trame incomplète (10 octets sur 16)": trame[:10],
    "Checksum incorrect": trame[:11] + b"00" + trame[13:],
    "Caractère non hexadécimal (Z)": trame[:3] + b"Z" + trame[4:],
    "ETX manquant": trame[:15] + b"\x00",
    "CR LF manquants": trame[:13] + b"  " + trame[15:],
    "STX manquant": b"\x00" + trame[1:],
}
for description, mauvaise in cas_invalides.items():
    montrer_trame(description, mauvaise)
    verifier(f"{description} : rejetée", erreur_de(decoder_trame, mauvaise), "TrameRFIDInvalide")

if not MATERIEL_REEL:
    horloge = HorlogeTest()
    lecteur = LecteurRFID(simuler=True, horloge=horloge)

    # ------------------------------------------------------------------
    etape("3. Réception octet par octet (l'UART livre la trame en morceaux)")
    lecteur.recevoir_octets(trame[:7])
    info(f"Reçu 7 octets : {trame[:7].hex(' ').upper()}")
    verifier("Moitié de trame : aucune carte encore", carte_txt(lecteur.lire_identifiant()), None)
    lecteur.recevoir_octets(trame[7:])
    info(f"Reçu les 9 autres : {trame[7:].hex(' ').upper()}")
    verifier("Trame complétée : carte lue", carte_txt(lecteur.lire_identifiant()), attendu("110082EEC8"))
    verifier("Le lecteur garde aussi l'ID brut", lecteur.dernier_brut, "110082EEC8")

    horloge.avancer(5)
    lecteur.recevoir_octets(b"\xff\x13garbage" + construire_trame("1F00AA5501"))
    info("Octets parasites avant le STX, puis une trame valide")
    verifier("Parasites ignorés, la trame suivante est lue", carte_txt(lecteur.lire_identifiant()), attendu("1F00AA5501"))
    verifier("Aucune erreur comptée pour des parasites hors trame", lecteur.nombre_erreurs, 0)

    horloge.avancer(5)
    lecteur.recevoir_octets(trame[:10])
    lecteur.recevoir_octets(construire_trame("2B7C3900E4"))
    info("Trame coupée après 10 octets, puis une nouvelle trame complète")
    verifier("Trame coupée comptée en erreur", lecteur.nombre_erreurs, 1)
    info(f"Raison notée par le lecteur : {lecteur.derniere_erreur}")
    verifier("La trame suivante est quand même lue", carte_txt(lecteur.lire_identifiant()), attendu("2B7C3900E4"))

    lecteur.recevoir_octets(trame[:11] + b"00" + trame[13:])
    verifier("Trame au mauvais checksum : aucune carte", carte_txt(lecteur.lire_identifiant()), None)
    verifier("Erreur comptée", lecteur.nombre_erreurs, 2)

    # ------------------------------------------------------------------
    etape(f"4. Anti-répétition (délai de {config.DELAI_REPETITION_RFID_S} s)")
    horloge.avancer(5)
    lecteur.recevoir_octets(trame)
    verifier("t = 0 s : carte lue", carte_txt(lecteur.lire_identifiant()), attendu("110082EEC8"))
    for seconde in (1, 2):
        horloge.avancer(1)
        lecteur.recevoir_octets(trame)
        verifier(f"t = {seconde} s : même carte maintenue, ignorée", carte_txt(lecteur.lire_identifiant()), None)
    verifier("Carte considérée présente", lecteur.est_carte_presente(), True)

    lecteur.recevoir_octets(construire_trame("1F00AA5501"))
    verifier("Une AUTRE carte est lue tout de suite", carte_txt(lecteur.lire_identifiant()), attendu("1F00AA5501"))

    horloge.avancer(4)
    verifier("Plus de 3 s sans trame : carte considérée partie", lecteur.est_carte_presente(), False)
    lecteur.recevoir_octets(trame)
    verifier("Première carte repassée plus tard : lue de nouveau", carte_txt(lecteur.lire_identifiant()), attendu("110082EEC8"))

else:
    lecteur = LecteurRFID(simuler=False)
    verifier("Port série du lecteur ouvert", lecteur.connecter(), True)

    if not lecteur.est_disponible():
        arreter_test(lecteur.derniere_erreur)

    # Chaque paquet d'octets reçu du vrai lecteur est affiché tel quel
    recevoir = lecteur.recevoir_octets

    def recevoir_et_afficher(donnees: bytes):
        info(f"UART reçu ({len(donnees)} octets) : {donnees.hex(' ').upper()}   {donnees!r}")
        recevoir(donnees)

    lecteur.recevoir_octets = recevoir_et_afficher

    def attendre_lectures(secondes: float) -> list:
        """Toutes les cartes NOUVELLES lues pendant « secondes »."""
        lues, fin = [], time.monotonic() + secondes
        while time.monotonic() < fin:
            identifiant = lecteur.lire_identifiant()
            if identifiant is not None:
                lues.append(identifiant)
                brut = lecteur.dernier_brut
                info(f"--> puce lue : {decrire_carte(brut)} (checksum {calculer_checksum(brut):02X} vérifié)")
                info(f"    identifiant utilisé par le code ({config.FORMAT_CARTE}) : {carte_txt(identifiant)}")
            time.sleep(0.05)
        return lues

    etape("3. Lecture d'une vraie puce")
    consigne("Passez UNE puce devant le lecteur (10 s)")
    premieres = attendre_lectures(10)
    verifier("Une puce lue", len(premieres) >= 1, True)
    verifier("Aucune trame rejetée", lecteur.nombre_erreurs, 0)
    puce = premieres[0] if premieres else None

    etape("4. Anti-répétition avec la vraie puce")
    consigne("Repassez la MÊME puce 3 fois rapidement, en moins de 3 s (8 s)")
    repetees = attendre_lectures(8)
    info(f"Lectures retenues : {[carte_txt(carte) for carte in repetees]}")
    verifier("Passages rapides : au plus une lecture", len(repetees) <= 1, True)

    consigne("Attendez 4 s sans rien passer, puis passez la puce une fois (10 s)")
    time.sleep(4)
    plus_tard = attendre_lectures(10)
    verifier("Puce repassée plus tard : lue de nouveau", len(plus_tard), 1)
    if puce is not None and plus_tard:
        verifier("Même identifiant qu'au premier passage", carte_txt(plus_tard[0]), carte_txt(puce))

    if DEUXIEME_PUCE:
        consigne("Passez maintenant une AUTRE puce (10 s)")
        autres = attendre_lectures(10)
        verifier("Deuxième puce lue", len(autres), 1)
        verifier("Identifiant différent de la première", bool(autres) and autres[0] != puce, True)

    verifier("Aucune trame rejetée pendant tout l'essai", lecteur.nombre_erreurs, 0)
    lecteur.deconnecter()

terminer()
