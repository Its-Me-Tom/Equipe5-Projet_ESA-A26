"""T04-10 — Redémarrage.

Essai (énoncé T04) : les transactions et les paiements sont rechargés
après un redémarrage, et leur cohérence avec le journal de T02 est
vérifiée (panne entre le débit de T02 et la sauvegarde de T04).

Ce que le terminal montre : les fichiers avant l'arrêt, les corrections
faites à la reprise (notes_reprise) et le tableau après redémarrage.

Matériel minimal : aucun.

Exécution : python3 test_t04_10_redemarrage.py
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
titre("T04-10 — Redémarrage", "SIMULATION : aucun matériel")

transactions, comptes, horloge, dossier = creer_transactions()
debut = horloge.maintenant()

etape("Avant l'arrêt : quatre transactions dans des états différents")
for place in ("E1.1", "E1.2", "E1.3", "E1.4"):
    transactions.confirmer_rangement(transactions.creer_transaction(place, CARTE_A), debut)
horloge.avancer(10 * 60)

transactions.demander_retrait(2)
transactions.confirmer_paiement(2, CARTE_A)          # 2 : PAYEE
transactions.demander_retrait(3)                     # 3 : paiement en attente, rien de payé
transactions.demander_retrait(4)
comptes.debiter(CARTE_B, 250, 4)                     # 4 : T02 a débité, puis panne avant « PAYEE »
info("1 : en stationnement | 2 : payée | 3 : demande en cours | 4 : débitée par T02, panne avant PAYEE")
afficher_transactions(transactions, horloge)
afficher_fichier(dossier / "operations.csv")

etape("Redémarrage : de nouveaux objets T02 et T04 relisent les fichiers")
del transactions
transactions, comptes, horloge, dossier = creer_transactions(dossier, horloge)
for note in transactions.notes_reprise:
    info(f"reprise : {note}")
afficher_transactions(transactions, horloge)

etats = {t["id"]: t["etat"] for t in transactions.obtenir_transactions()}
verifier("1 : toujours EN_STATIONNEMENT", etats[1], "EN_STATIONNEMENT")
verifier("2 : PAYEE reste PAYEE", etats[2], "PAYEE")
verifier("3 : demande non payée annulée (fenêtre perdue au redémarrage)", etats[3], "EN_STATIONNEMENT")
verifier("4 : débit trouvé dans le journal de T02 -> PAYEE", etats[4], "PAYEE")
verifier("4 : carte de paiement retrouvée", transactions.obtenir_transaction(4)["rfid_paiement"], TXT_B)
verifier("Deux corrections signalées à la reprise", len(transactions.notes_reprise), 2)
verifier("Heure de début conservée", transactions.obtenir_transaction(1)["debut_facturation"], debut)

etape("Aucun paiement n'est refait")
verifier("Paiement rejoué sur la 2", transactions.confirmer_paiement(2, CARTE_A), True)
verifier("Paiement rejoué sur la 4", transactions.confirmer_paiement(4, CARTE_B), True)
afficher_comptes(comptes)
verifier("A débitée une seule fois", comptes.obtenir_solde(CARTE_A), 2250)
verifier("B débitée une seule fois", comptes.obtenir_solde(CARTE_B), 750)

etape("La facturation de la 3 continue depuis le dépôt")
horloge.avancer(5 * 60)
verifier("3 : montant recalculé (15 min)", transactions.demander_retrait(3)["montant_cents"], 375)
verifier("Nouvelle transaction : numéro 5", transactions.creer_transaction("E2.1", CARTE_C), 5)

etape("Fichier de transactions corrompu : erreur signalée, pas de plantage")
(dossier / "transactions.csv").write_text("n'importe quoi\n", encoding="utf-8")
afficher_fichier(dossier / "transactions.csv")
verifier("transactions.csv invalide : ErreurFichier", erreur_de(creer_transactions, dossier, HorlogeTest()),
         "ErreurFichier")

terminer()
