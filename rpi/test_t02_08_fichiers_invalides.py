"""T02-08 — Fichiers invalides.

Essai (énoncé T02) : un fichier absent, au contenu incorrect ou
inaccessible provoque une erreur signalée (ErreurFichier, avec un message
clair), jamais un plantage incontrôlé. Les données restent cohérentes.

Ce que le terminal montre : pour chaque cas, le contenu du fichier fautif
et le message d'erreur exact retourné par T02.

Matériel minimal : aucun (fichiers temporaires).

Exécution : python3 test_t02_08_fichiers_invalides.py
"""


import atexit
import os
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
titre("T02-08 — Fichiers invalides", "SIMULATION : aucun matériel")


def comptes_avec(contenu: str):
    """T02 avec un comptes.csv au contenu choisi."""
    dossier = creer_dossier_donnees()
    (dossier / "comptes.csv").write_text(contenu, encoding="utf-8")
    return creer_comptes(dossier)[0]


etape("1. Fichier absent")
comptes, dossier = creer_comptes()
(dossier / "comptes.csv").unlink()
info("comptes.csv supprimé")
verifier("Consultation : ErreurFichier", erreur_de(comptes.obtenir_solde, CARTE_A), "ErreurFichier")
verifier("Crédit : ErreurFichier", erreur_de(comptes.ajouter_credit, CARTE_A, 100, "C001"), "ErreurFichier")

etape("2. Contenus incorrects dans comptes.csv")
cas = {
    "Colonnes incorrectes": f"carte,argent\n{TXT_A},2500\n",
    "Solde non numérique": f"rfid,nom,solde\n{TXT_A},A,abc\n",
    "Solde à virgule": f"rfid,nom,solde\n{TXT_A},A,25.00\n",
    "Solde négatif": f"rfid,nom,solde\n{TXT_A},A,-100\n",
    "Identifiant de carte invalide": "rfid,nom,solde\nXYZ,A,100\n",
    "Identifiant trop court": "rfid,nom,solde\n0123,A,100\n",
    "Caractère interdit dans le numéro": "rfid,nom,solde\n00000000Z1,A,100\n",
    "Carte en double": f"rfid,nom,solde\n{TXT_A},A,100\n{TXT_A},B,200\n",
    "Ligne incomplète": f"rfid,nom,solde\n{TXT_A},A\n",
    "Colonne en trop": f"rfid,nom,solde\n{TXT_A},A,100,999\n",
    "Fichier vide": "",
}
if config.FORMAT_CARTE == "DECIMAL":
    cas["Numéro hexadécimal en format DECIMAL"] = "rfid,nom,solde\n00ABCDEF12,A,100\n"
    cas["Numéro plus grand que 4 octets (> 4294967295)"] = "rfid,nom,solde\n9999999999,A,100\n"
for description, contenu in cas.items():
    info(f"{description} — contenu : {contenu!r}")
    verifier(f"{description} : ErreurFichier", erreur_de(comptes_avec(contenu).obtenir_solde, CARTE_A),
             "ErreurFichier")

etape("3. Ancien format « rfid,solde » (sans nom) : encore accepté")
comptes = comptes_avec(f"rfid,solde\n{TXT_A},2500\n")
verifier("Solde lu", comptes.obtenir_solde(CARTE_A), 2500)
verifier("Nom absent : le numéro de la carte sert de nom", comptes.obtenir_nom(CARTE_A), TXT_A)
comptes.ajouter_credit(CARTE_A, 100, "C001")
contenu = comptes.fichier.fichier_comptes.read_text(encoding="utf-8")
info(f"comptes.csv après un crédit : {contenu!r}")
verifier("Réécrit au nouveau format (rfid,nom,solde)", contenu, f"rfid,nom,solde\n{TXT_A},{TXT_A},2600\n")
comptes = comptes_avec(f"rfid,nom,solde\n{TXT_A},,2500\n")
verifier("Nom vide : le numéro de la carte sert de nom", comptes.obtenir_nom(CARTE_A), TXT_A)

etape("4. Contenu incorrect dans operations.csv")
comptes, dossier = creer_comptes()
(dossier / "operations.csv").write_text(f"operation_id,rfid,type,montant\nC001,{TXT_A},credit,beaucoup\n",
                                        encoding="utf-8")
afficher_fichier(dossier / "operations.csv")
verifier("Montant illisible dans le journal : ErreurFichier",
         erreur_de(comptes.ajouter_credit, CARTE_A, 100, "C002"), "ErreurFichier")
verifier("Solde non modifié", f"{TXT_A},Carte A,2500" in (dossier / "comptes.csv").read_text(encoding="utf-8"), True)

etape("5. Fichier inaccessible")
comptes, dossier = creer_comptes()
(dossier / "comptes.csv").unlink()
(dossier / "comptes.csv").mkdir()
info("comptes.csv est un DOSSIER (ouverture impossible)")
verifier("Consultation : ErreurFichier", erreur_de(comptes.obtenir_solde, CARTE_A), "ErreurFichier")

comptes, dossier = creer_comptes()
(dossier / "operations.csv").unlink()
info("operations.csv supprimé : le crédit ne peut pas être journalisé")
verifier("Crédit refusé : ErreurFichier", erreur_de(comptes.ajouter_credit, CARTE_A, 100, "C001"), "ErreurFichier")
verifier("Le solde n'a pas bougé (journal d'abord, solde ensuite)",
         f"{TXT_A},Carte A,2500" in (dossier / "comptes.csv").read_text(encoding="utf-8"), True)

if hasattr(os, "geteuid") and os.geteuid() != 0:
    comptes, dossier = creer_comptes()
    os.chmod(dossier / "comptes.csv", 0)
    info("comptes.csv sans aucune permission (chmod 000)")
    verifier("Lecture interdite : ErreurFichier", erreur_de(comptes.obtenir_solde, CARTE_A), "ErreurFichier")
    os.chmod(dossier / "comptes.csv", 0o644)
else:
    info("(cas chmod 000 sauté : exécuté en root ou sous Windows, les permissions ne bloquent pas)")

etape("6. Incohérence entre les deux fichiers (contrôle au démarrage)")
comptes, dossier = creer_comptes()
with open(dossier / "operations.csv", "a", encoding="utf-8") as fichier:
    fichier.write(f"C001,{TXT_INCONNUE},credit,100\n")
afficher_fichier(dossier / "operations.csv")
problemes = comptes.verifier_coherence()
for probleme in problemes:
    info(f"incohérence signalée : {probleme}")
verifier("Incohérence signalée", problemes, ["Opération C001 : carte inconnue"])

etape("7. Après tous ces cas, un fichier valide fonctionne normalement")
comptes, dossier = creer_comptes()
verifier("Crédit normal accepté", comptes.ajouter_credit(CARTE_A, 100, "C001"), True)
verifier("Solde", comptes.obtenir_solde(CARTE_A), 2600)

terminer()
