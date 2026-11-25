"""T02-04 — Crédit.

Essai (énoncé T02) : le montant est ajouté et sauvegardé; répéter le même
operation_id ne crédite pas une deuxième fois.

Ce que le terminal montre : comptes.csv et operations.csv avant et après
chaque crédit, l'operation_id utilisé et le nouveau solde.

Matériel minimal : aucun (T02 seul, fichiers temporaires).

Exécution : python3 test_t02_04_credit.py
"""


import atexit
import shutil
import sys
import tempfile
import time
from pathlib import Path

from src import config
from src.format_carte import carte_vers_texte
from src.models.t02_fichier_comptes import FichierComptes
from src.models.t02_gestion_comptes import GestionComptes


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


# ======================================================================
# ESSAI
# ======================================================================
titre("T02-04 — Crédit", "SIMULATION : aucun matériel")

comptes, dossier = creer_comptes()

etape("Données de départ")
afficher_comptes(comptes)

etape("Crédit de 1000 ¢ sur la carte A (operation_id C001)")
verifier("Crédit accepté", comptes.ajouter_credit(CARTE_A, 1000, "C001"), True)
verifier("Nouveau solde de A (2500 + 1000)", comptes.obtenir_solde(CARTE_A), 3500)
afficher_fichier(dossier / "comptes.csv")
afficher_fichier(dossier / "operations.csv")
verifier("Solde sauvegardé dans comptes.csv",
         f"{TXT_A},Carte A,3500" in (dossier / "comptes.csv").read_text(encoding="utf-8"), True)
verifier("Opération notée dans operations.csv",
         f"C001,{TXT_A},credit,1000" in (dossier / "operations.csv").read_text(encoding="utf-8"), True)

etape("Même operation_id C001 retransmis (ex. message MQTT répété)")
verifier("Répétition refusée", erreur_de(comptes.ajouter_credit, CARTE_A, 1000, "C001"), "OperationRepetee")
verifier("Aucun deuxième crédit", comptes.obtenir_solde(CARTE_A), 3500)
verifier("Toujours une seule ligne C001 dans le journal",
         [o["operation_id"] for o in comptes.obtenir_operations()].count("C001"), 1)

etape("Le même operation_id ne peut pas servir pour une autre carte")
verifier("C001 sur la carte C refusé", erreur_de(comptes.ajouter_credit, CARTE_C, 1000, "C001"), "OperationRepetee")
verifier("Carte C non créditée", comptes.obtenir_solde(CARTE_C), 0)

etape("Nouveaux operation_id : nouveaux crédits")
verifier("C002 : +250 ¢ sur A", comptes.ajouter_credit(CARTE_A, 250, "C002"), True)
verifier("Solde de A", comptes.obtenir_solde(CARTE_A), 3750)
verifier("C003 : +1 ¢ sur C (solde 0)", comptes.ajouter_credit(CARTE_C, 1, "C003"), True)
verifier("Solde de C", comptes.obtenir_solde(CARTE_C), 1)

etape("Montants invalides : refusés avant toute écriture")
for montant in (0, -500, 12.5, "100", True, None):
    verifier(f"Montant {montant!r} refusé", erreur_de(comptes.ajouter_credit, CARTE_A, montant, "C999"),
             "MontantInvalide")
verifier("Solde de A inchangé après les refus", comptes.obtenir_solde(CARTE_A), 3750)
verifier("Aucune opération C999 dans le journal",
         "C999" in [o["operation_id"] for o in comptes.obtenir_operations()], False)

etape("État final")
afficher_comptes(comptes)
verifier("Journal complet", [(o["operation_id"], o["montant"]) for o in comptes.obtenir_operations()],
         [("C001", 1000), ("C002", 250), ("C003", 1)])

terminer()
