"""T02-03 — Consultation.

Essai (énoncé T02) : le solde est correct pour plusieurs cartes
préconfigurées. Le nom de chaque compte (colonne « nom ») est aussi lu.

Ce que le terminal montre : le fichier comptes.csv lu, puis pour chaque
carte l'identifiant (format config.FORMAT_CARTE), le nom, le solde retourné
par T02 et le solde attendu. En mode réel : l'ID brut et le numéro imprimé
de chaque puce passée.

Matériel minimal
    MATERIEL_REEL = False : aucun (5 cartes fictives).
    MATERIEL_REEL = True  : lecteur RFID et des VRAIES puces préconfigurées
                            dans data/comptes.csv (le fichier est lu dans une
                            copie, jamais modifié). Une puce absente du
                            fichier fait échouer l'essai : ajoutez-la d'abord.

Exécution : python3 test_t02_03_consultation.py
"""


import atexit
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from src import config
from src.format_carte import carte_vers_texte, decrire_carte, texte_vers_carte
from src.hardware.t02_lecteur_rfid import LecteurRFID
from src.horloge import Horloge
from src.models.t02_fichier_comptes import FichierComptes
from src.models.t02_gestion_comptes import GestionComptes


# ----------------------------------------------------------------------
# RÉGLAGES DU TEST (modifiez ici)
# ----------------------------------------------------------------------
MATERIEL_REEL = True       # True = vraies puces + data/comptes.csv réel | False = simulation
NOMBRE_PUCES = 2           # mode réel : nombre de puces à passer

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
titre("T02-03 — Consultation",
      f"MATÉRIEL RÉEL : lecteur RFID + {config.FICHIER_COMPTES}" if MATERIEL_REEL else "SIMULATION : aucun matériel")

if not MATERIEL_REEL:
    # carte -> (nom, solde). 8580808 = numéro imprimé d'une vraie puce; 4294967295 = plus grand numéro.
    fiches = {carte_txt(CARTE_A): ("Carte A", 2500), carte_txt(CARTE_B): ("Carte B", 1000),
              carte_txt(CARTE_C): ("Carte C", 0), carte_txt(8580808): ("Thomas", 123456),
              carte_txt(4294967295): ("Max", 1)}
    preconfigures = {carte: solde for carte, (nom, solde) in fiches.items()}
    noms = {carte: nom for carte, (nom, solde) in fiches.items()}
    comptes, dossier = creer_comptes(creer_dossier_donnees(preconfigures, noms))
else:
    if not config.FICHIER_COMPTES.exists():
        arreter_test(f"{config.FICHIER_COMPTES} absent")
    dossier = creer_dossier_donnees({})
    shutil.copy(config.FICHIER_COMPTES, dossier / "comptes.csv")      # copie : l'original n'est pas touché
    comptes, dossier = creer_comptes(dossier)
    try:
        preconfigures = comptes.obtenir_comptes()
        noms = comptes.obtenir_noms()
    except Exception as erreur:
        arreter_test(f"{config.FICHIER_COMPTES} illisible en format {config.FORMAT_CARTE} : {erreur}")

etape("Fichier des comptes préconfigurés")
afficher_fichier(dossier / "comptes.csv")
verifier("Aucune incohérence au contrôle de démarrage", comptes.verifier_coherence(), [])
verifier("Nombre de comptes lus par T02", len(comptes.obtenir_comptes()), len(preconfigures))

etape(f"Solde et nom de chaque carte (format {config.FORMAT_CARTE})")
if not MATERIEL_REEL:
    for texte, attendu in preconfigures.items():
        carte = texte_vers_carte(texte)
        obtenu = comptes.obtenir_solde(carte)
        info(f"carte {texte} : T02 retourne {argent(obtenu)}, nom {comptes.obtenir_nom(carte)!r}")
        verifier(f"Solde de {texte}", obtenu, attendu)
        verifier(f"Nom de {texte}", comptes.obtenir_nom(carte), noms[texte])
else:
    lecteur = LecteurRFID(simuler=False, horloge=Horloge())
    if not lecteur.connecter():
        arreter_test(lecteur.derniere_erreur)
    lues = []
    for numero in range(1, NOMBRE_PUCES + 1):
        consigne(f"Passez la puce n° {numero} (une puce différente à chaque fois, 20 s)")
        carte, fin = None, time.monotonic() + 20
        while (carte is None or carte in lues) and time.monotonic() < fin:
            carte = lecteur.lire_identifiant()
            time.sleep(0.05)
        if carte is None or carte in lues:
            verifier(f"Puce n° {numero} lue", False, True)
            continue
        lues.append(carte)
        texte = carte_txt(carte)
        obtenu = comptes.obtenir_solde(carte)
        info(f"puce lue : {decrire_carte(lecteur.dernier_brut)} -> carte {texte} ({config.FORMAT_CARTE})")
        info(f"puce {texte} ({noms.get(texte, 'sans compte')}) : T02 retourne {argent(obtenu)}, "
             f"comptes.csv contient {argent(preconfigures.get(texte))}")
        verifier(f"Puce {texte} préconfigurée dans comptes.csv", texte in preconfigures, True)
        verifier(f"Solde de {texte}", obtenu, preconfigures.get(texte))
    lecteur.deconnecter()

etape("Peut-elle payer ? (vérification sans débit)")
if not MATERIEL_REEL:
    cas = [(CARTE_A, 2500, True), (CARTE_A, 2501, False), (CARTE_B, 999, True),
           (CARTE_C, 1, False), (CARTE_C, 0, True)]
    for carte, montant, attendu in cas:
        verifier(f"{carte_txt(carte)} ({argent(comptes.obtenir_solde(carte))}) peut payer {montant} ¢",
                 comptes.verifier_solde(carte, montant), attendu)

etape("La consultation ne modifie rien")
afficher_fichier(dossier / "operations.csv")
verifier("Aucune opération créée par les consultations", comptes.obtenir_operations(), [])
verifier("Soldes inchangés", comptes.obtenir_comptes(), preconfigures)

terminer()
