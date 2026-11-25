"""T04-11 — Simulation.

Essai (énoncé T04) : toutes les transitions d'état sont démontrées avec un
T02 simulé et un T12 simulé, sans mécanique :
    CREEE -> EN_STATIONNEMENT -> PAIEMENT_EN_ATTENTE -> PAYEE
          -> RETRAIT_EN_COURS -> TERMINEE
    CREEE -> ANNULEE        PAIEMENT_EN_ATTENTE -> EN_STATIONNEMENT
    (n'importe quel état actif) -> ERREUR (paiement conservé)

Ce que le terminal montre : chaque transition (état avant -> après) et
chaque appel au T02 simulé.

Matériel minimal : aucun (T02 simulé en mémoire, sans fichier de comptes).

Exécution : python3 test_t04_11_simulation.py
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
from src.models.erreurs import CarteInconnue, OperationRepetee, SoldeInsuffisant
from src.models.t04_gestion_transactions import GestionTransactions


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
titre("T04-11 — Toutes les transitions (T02 et T12 simulés)", "SIMULATION : aucun matériel")


class ComptesSimules:
    """T02 simulé : soldes en mémoire, aucun fichier. Affiche chaque appel."""

    def __init__(self):
        self.soldes = {CARTE_A: 2500, CARTE_B: 50}
        self.debits = []

    def debiter(self, carte, montant, transaction_id):
        info(f"   T02 simulé : debiter({carte_txt(carte)}, {montant} ¢, transaction {transaction_id})")
        if carte not in self.soldes:
            raise CarteInconnue("Carte inconnue")
        if any(t == transaction_id for t, _ in self.debits):
            raise OperationRepetee("Déjà débitée")
        if self.soldes[carte] < montant:
            raise SoldeInsuffisant("Solde insuffisant")
        self.soldes[carte] -= montant
        self.debits.append((transaction_id, montant))
        return True

    def obtenir_operations(self):
        return []


horloge = HorlogeTest()
t02_simule = ComptesSimules()
transactions = GestionTransactions(t02_simule, creer_dossier_donnees() / "transactions.csv", horloge)


def etat(numero: int) -> str:
    return transactions.obtenir_transaction(numero)["etat"]


def transition(texte: str, numero: int, action):
    avant = etat(numero)
    resultat = action()
    info(f"{texte} : {avant} -> {etat(numero)}  (retour {resultat!r})")
    return resultat


etape("Chemin normal complet")
numero = transactions.creer_transaction("E1.3", CARTE_A)
info(f"T03 crée la transaction {numero} : {etat(numero)}")
verifier("Création", etat(numero), "CREEE")
transition("T11 confirme le rangement", numero, lambda: transactions.confirmer_rangement(numero, horloge.maintenant()))
verifier("Rangement", etat(numero), "EN_STATIONNEMENT")
horloge.avancer(4 * 60)
transition("T12 demande le retrait", numero, lambda: transactions.demander_retrait(numero)["accepte"])
verifier("Demande de retrait", etat(numero), "PAIEMENT_EN_ATTENTE")
transition("Carte B insuffisante", numero, lambda: transactions.confirmer_paiement(numero, CARTE_B))
verifier("Toujours en attente après un refus", etat(numero), "PAIEMENT_EN_ATTENTE")
transition("Carte A", numero, lambda: transactions.confirmer_paiement(numero, CARTE_A))
verifier("Paiement", etat(numero), "PAYEE")
verifier("Débit demandé au T02 simulé", t02_simule.debits, [(numero, 100)])
transition("T12 commence le retrait", numero, lambda: transactions.commencer_retrait(numero))
verifier("Retrait mécanique", etat(numero), "RETRAIT_EN_COURS")
transition("T12 confirme la sortie", numero, lambda: transactions.confirmer_sortie(numero))
verifier("Sortie", etat(numero), "TERMINEE")

etape("Annulation avant le dépôt")
annulee = transactions.creer_transaction("E1.4", CARTE_A)
transition("Réservation annulée", annulee, lambda: transactions.annuler_transaction(annulee))
verifier("État ANNULEE", etat(annulee), "ANNULEE")
verifier("Rangement refusé après annulation", transactions.confirmer_rangement(annulee, horloge.maintenant()), False)

etape("Annulation d'une demande de retrait")
autre = transactions.creer_transaction("E1.6", CARTE_A)
transactions.confirmer_rangement(autre, horloge.maintenant())
horloge.avancer(60)
transactions.demander_retrait(autre)
transition("L'utilisateur annule", autre, lambda: transactions.annuler_demande_retrait(autre))
verifier("Retour à EN_STATIONNEMENT", etat(autre), "EN_STATIONNEMENT")

etape("Anomalie pendant un retrait payé : le paiement n'est jamais effacé")
en_erreur = transactions.creer_transaction("E1.5", CARTE_A)
transactions.confirmer_rangement(en_erreur, horloge.maintenant())
horloge.avancer(60)
transactions.demander_retrait(en_erreur)
transactions.confirmer_paiement(en_erreur, CARTE_A)
transition("T12 signale un défaut CAN", en_erreur, lambda: transactions.suspendre(en_erreur, "DEFAUT_CAN"))
transaction = transactions.obtenir_transaction(en_erreur)
info(f"transaction en erreur : {transaction}")
verifier("État ERREUR", transaction["etat"], "ERREUR")
verifier("Paiement conservé (carte)", transaction["rfid_paiement"], TXT_A)
verifier("Montant payé conservé", transaction["montant_fige"], 25)
verifier("État précédent noté dans l'erreur", "PAYEE" in transaction["erreur"], True)
verifier("Aucune nouvelle facturation", transactions.demander_retrait(en_erreur)["accepte"], False)
verifier("Pas de deuxième débit", len(t02_simule.debits), 2)

etape("Transitions interdites")
verifier("Clôture d'une transaction terminée", transactions.confirmer_sortie(numero), False)
verifier("Retrait d'une transaction inexistante", transactions.demander_retrait(999)["erreur"], "TRANSACTION_INEXISTANTE")
verifier("Suspension d'une transaction terminée", transactions.suspendre(numero, "TEST"), False)
verifier("Retrait d'une transaction en ERREUR", transactions.commencer_retrait(en_erreur), False)

terminer()
