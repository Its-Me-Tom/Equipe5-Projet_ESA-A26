"""T04-03 — Tarification.

Essai (énoncé T04) : durées connues, tarif configuré et montants entiers
en cents. Toute minute commencée est facturée au complet.

Ce que le terminal montre : un tableau durée -> minutes facturées ->
montant, avec le tarif utilisé.

Matériel minimal : aucun.

Exécution : python3 test_t04_03_tarification.py
"""


import atexit
import shutil
import sys
import tempfile
import time
from pathlib import Path

from src import config
from src.format_carte import carte_vers_texte
from src.horloge import Horloge
from src.models.t02_fichier_comptes import FichierComptes
from src.models.t02_gestion_comptes import GestionComptes
from src.models.t04_gestion_transactions import GestionTransactions
from src.views.formatage import formater_transaction


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


# ---------- T02 seul : comptes dans un dossier temporaire ----------
def creer_comptes(dossier: Path | None = None):
    """Construit T02 (GestionComptes) sur un dossier. Retourne (comptes, dossier)."""
    dossier = dossier or creer_dossier_donnees()
    fichier = FichierComptes(dossier / "comptes.csv", dossier / "operations.csv")
    return GestionComptes(fichier), dossier


def afficher_comptes(comptes):
    """Soldes et journal des opérations, tels que T02 les lit dans ses fichiers."""
    info(f"Soldes (comptes.csv, cartes en format {config.FORMAT_CARTE}) :")
    noms = comptes.obtenir_noms()
    tableau(["carte", "nom", "solde"], [[carte, noms.get(carte, ""), argent(solde)]
                                        for carte, solde in sorted(comptes.obtenir_comptes().items())])
    info("Journal (operations.csv) :")
    tableau(["operation_id", "carte", "type", "montant (¢)"],
            [[o["operation_id"], o["rfid"], o["type"], o["montant"]] for o in comptes.obtenir_operations()])


# ---------- T04 avec le vrai T02 (fichiers temporaires) ----------
def creer_transactions(dossier: Path | None = None, horloge: HorlogeTest | None = None):
    """Construit T04 avec le vrai T02. Retourne (transactions, comptes, horloge, dossier)."""
    comptes, dossier = creer_comptes(dossier)
    horloge = horloge or HorlogeTest()
    transactions = GestionTransactions(comptes, dossier / "transactions.csv", horloge)
    return transactions, comptes, horloge, dossier


def heure(horloge, horodatage) -> str:
    """Horodatage en temps écoulé depuis le début du test (+mm:ss)."""
    if horodatage is None:
        return "-"
    secondes = horodatage - 1_800_000_000.0
    return f"+{int(secondes // 60):02d}:{secondes % 60:04.1f}"


def afficher_transactions(transactions, horloge):
    """Tableau de toutes les transactions de T04."""
    tableau(["n°", "place", "état", "carte départ", "début facturation", "montant figé", "carte paiement", "fin",
             "erreur"],
            [[formater_transaction(t["id"]), t["place"], t["etat"], t["rfid_initial"],
              heure(horloge, t["debut_facturation"]), t["montant_fige"], t["rfid_paiement"],
              heure(horloge, t["fin"]), t["erreur"]] for t in transactions.obtenir_transactions()])


# ======================================================================
# ESSAI
# ======================================================================
titre("T04-03 — Tarification", "SIMULATION : aucun matériel")

transactions, comptes, horloge, dossier = creer_transactions()
numero = transactions.creer_transaction("E1.3", CARTE_A)
debut = horloge.maintenant()
transactions.confirmer_rangement(numero, debut)

etape("Tarif configuré (src/config.py)")
info(f"TARIF_CENTS_PAR_MINUTE = {config.TARIF_CENTS_PAR_MINUTE}")
verifier("Tarif utilisé par T04 (¢ par minute)", transactions.tarif, config.TARIF_CENTS_PAR_MINUTE)

etape("Durées connues (toute minute commencée est facturée)")
cas = {0: (0, 0), 1: (1, 25), 59: (1, 25), 60: (1, 25), 61: (2, 50), 600: (10, 250),
       3599: (60, 1500), 3600: (60, 1500), 3601: (61, 1525), 86400: (1440, 36000)}
lignes = []
for secondes, (minutes, montant) in cas.items():
    obtenu_minutes = transactions.calculer_duree_min(numero, debut + secondes)
    obtenu = transactions.calculer_montant(numero, debut + secondes)
    lignes.append([secondes, obtenu_minutes, obtenu, montant, "OK" if obtenu == montant else "ÉCHEC"])
tableau(["durée (s)", "minutes facturées", "montant (¢)", "attendu (¢)", ""], lignes)
for secondes, (minutes, montant) in cas.items():
    verifier(f"{secondes} s -> {minutes} min -> {montant} ¢", (transactions.calculer_duree_min(numero, debut + secondes),
                                                              transactions.calculer_montant(numero, debut + secondes)),
             (minutes, montant))

montant = transactions.calculer_montant(numero, debut + 61)
verifier("Montant de type entier (cents, pas de float)", type(montant).__name__, "int")

etape("Le tarif est un paramètre (pas une valeur codée en dur)")
transactions.tarif = 40
info("tarif changé à 40 ¢/min pour cette transaction")
verifier("10 min à 40 ¢/min", transactions.calculer_montant(numero, debut + 600), 400)
transactions.tarif = config.TARIF_CENTS_PAR_MINUTE

etape("Erreurs")
verifier("Heure avant le début : HorodatageInvalide",
         erreur_de(transactions.calculer_montant, numero, debut - 10), "HorodatageInvalide")
verifier("Transaction inexistante : TransactionInexistante",
         erreur_de(transactions.calculer_montant, 999, debut), "TransactionInexistante")
non_rangee = transactions.creer_transaction("E1.4", CARTE_A)
verifier("Transaction pas encore rangée : 0 ¢", transactions.calculer_montant(non_rangee, debut + 600), 0)

terminer()
