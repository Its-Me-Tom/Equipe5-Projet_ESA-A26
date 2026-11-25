"""PC-04 — Connexion du Raspberry Pi (bandes de connexion).

Essai (énoncé T13, tests 1, 8 et 9, côté PC) : l'app affiche la connexion
du PC au broker et, juste en dessous, celle du Raspberry Pi (topic
rpi/connexion : message conservé + testament MQTT). Inconnu = gris,
connecté = vert, déconnecté = rouge.

Ce que le terminal montre : chaque message de présence reçu et le texte et
la couleur des deux bandes.

Matériel minimal
    MATERIEL_REEL = False : aucun (messages simulés, sans réseau).
    MATERIEL_REEL = True  : broker à config.BROKER_IP et le Raspberry Pi qui
                            roule (main.py). L'opérateur arrête puis relance
                            le programme du RPi quand le test le demande.

Exécution : python test_pc_04_connexion_rpi.py
"""


import json
import os
import re
import sys
import time

from PyQt6.QtCore import pyqtSignal, QObject, QTimer
from PyQt6.QtWidgets import QApplication

import src.controllers.main_controller as module_controleur
import src.network.mqtt_client as module_mqtt
from src import config
from src.mqtt_topics import MqttTopics
from src.views.main_window import MainWindow


# ----------------------------------------------------------------------
# RÉGLAGES DU TEST (modifiez ici)
# ----------------------------------------------------------------------
MATERIEL_REEL = False      # True = vrai broker + vrai Raspberry Pi
MONTRER_FENETRE = False    # True = ouvre aussi la fenêtre pendant le test


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


# ---------- La VRAIE app PC (fenêtre + contrôleur), avec un MQTT simulé ou réel ----------
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")       # Linux sans écran (ex. SSH)


class MqttFactice(QObject):
    """Remplace le client MQTT du PC en simulation : garde ce que l'app publie,
    et permet d'injecter des messages comme s'ils venaient du Raspberry Pi."""

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    message_received = pyqtSignal(str, str)
    connection_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.topics = []
        self.is_connected = False
        self.publies = []           # (topic, dict) publiés par l'app

    def connect_to_broker(self):
        QTimer.singleShot(0, self._connecter)

    def _connecter(self):
        self.is_connected = True
        self.connected.emit()

    def disconnect_from_broker(self):
        self.is_connected = False
        self.disconnected.emit()

    def subscribe(self, topic: str):
        self.topics.append(topic)

    def publish(self, topic: str, payload: str) -> bool:
        if not self.is_connected:
            return False
        self.publies.append((topic, json.loads(payload)))
        print(f"      APP PC -> MQTT  {topic.split('/', 2)[-1]} : {payload}", flush=True)
        return True

    def injecter(self, topic: str, contenu):
        """Simule un message publié par le RPi (contenu : dict ou texte brut)."""
        payload = contenu if isinstance(contenu, str) else json.dumps(contenu, ensure_ascii=False)
        print(f"      RPi simulé -> APP PC  {topic.split('/', 2)[-1]} : {payload[:300]}", flush=True)
        if topic in self.topics:
            self.message_received.emit(topic, payload)
        else:
            print("         (topic non écouté par l'app : message ignoré)")


_APPLICATION = QApplication.instance() or QApplication(sys.argv)


def creer_app_pc(mqtt_reel: bool = False, montrer: bool = False):
    """Crée la fenêtre et le contrôleur de l'app PC.

    mqtt_reel = False : MqttFactice (aucun réseau).
    mqtt_reel = True  : vrai broker config.BROKER_IP, avec un identifiant de
                        client différent de l'app (on peut garder l'app ouverte).
    Le journal de l'app est recopié dans le terminal.
    """
    if mqtt_reel:
        module_mqtt.ID_CLIENT_MQTT = f"esa-pc-test-{config.NUMERO_EQUIPE}-{time.time_ns() % 100000}"
    else:
        module_controleur.MqttClient = MqttFactice

    fenetre = MainWindow()
    ajouter = fenetre.add_log

    def ajouter_et_afficher(texte: str):
        ajouter(texte)
        print(f"      [journal de l'app] {texte}", flush=True)

    fenetre.add_log = ajouter_et_afficher
    controleur = module_controleur.MainController(fenetre)
    if montrer:
        fenetre.show()
    info(f"App PC créée ({'broker réel ' + config.BROKER_IP if mqtt_reel else 'MQTT simulé'})")
    return fenetre, controleur


def traiter_evenements(secondes: float, jusqua=None) -> bool:
    """Laisse tourner l'interface Qt (signaux, minuteries) pendant « secondes »."""
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        _APPLICATION.processEvents()
        if jusqua is not None and jusqua():
            return True
        time.sleep(0.02)
    _APPLICATION.processEvents()
    return False


def couleur_de(widget) -> str:
    """Couleur de fond (#rrggbb) d'un widget, lue dans sa feuille de style."""
    trouve = re.search(r"background-color:\s*(#[0-9a-fA-F]{6})", widget.styleSheet())
    return trouve.group(1).lower() if trouve else ""


def lignes_tableau(tableau) -> list:
    """Contenu d'un QTableWidget : une liste de lignes (textes)."""
    return [[(tableau.item(ligne, colonne).text() if tableau.item(ligne, colonne) else "")
             for colonne in range(tableau.columnCount())] for ligne in range(tableau.rowCount())]


def lire_affichage(fenetre) -> dict:
    """Tout ce que l'app affiche, lu dans les widgets."""
    stationnement = fenetre.page_stationnement
    return {
        "bande_pc": fenetre.etiquette_connexion.text(),
        "bande_rpi": fenetre.etiquette_connexion_rpi.text(),
        "couleur_bande_rpi": couleur_de(fenetre.etiquette_connexion_rpi),
        "etat": fenetre.page_commandes.etiquette_etat.text(),
        "couleur_etat": couleur_de(fenetre.page_commandes.etiquette_etat),
        "detail": fenetre.page_commandes.etiquette_detail.text(),
        "places": {nom: texte.text().replace("\n", " / ") for nom, (temoin, texte) in stationnement._temoins.items()},
        "couleurs_places": {nom: couleur_de(temoin) for nom, (temoin, texte) in stationnement._temoins.items()},
        "rampe": stationnement.etiquette_rampe.text(),
        "anomalies": lignes_tableau(fenetre.page_commandes.tableau_anomalies),
        "reponse_commandes": fenetre.page_commandes.etiquette_reponse.text(),
        "comptes": lignes_tableau(fenetre.page_comptes.tableau),
        "reponse_comptes": fenetre.page_comptes.etiquette_reponse.text(),
        "statistiques": lignes_tableau(fenetre.page_statistiques.tableau_comptes),
        "transactions": lignes_tableau(fenetre.page_statistiques.tableau_transactions),
    }


def afficher_affichage(fenetre, parties=("bandes", "etat", "places", "anomalies", "comptes", "statistiques")):
    """Affiche dans le terminal ce que l'app montre à l'écran."""
    a = lire_affichage(fenetre)
    if "bandes" in parties:
        info(f"Bande PC  : {a['bande_pc']}")
        info(f"Bande RPi : {a['bande_rpi']} ({a['couleur_bande_rpi']})")
    if "etat" in parties:
        info(f"Onglet Commandes : état « {a['etat']} » ({a['couleur_etat']}) {a['detail']}")
    if "places" in parties:
        info("Onglet Stationnement :")
        tableau(["place", "texte affiché", "couleur"],
                [[nom, texte, a["couleurs_places"][nom]] for nom, texte in sorted(a["places"].items())])
        info(a["rampe"])
    if "anomalies" in parties:
        info("Tableau des anomalies :")
        tableau(["heure", "tâche", "code", "message", "place", "critique"], a["anomalies"])
    if "comptes" in parties:
        info("Onglet Comptes RFID :")
        tableau(["carte", "solde"], a["comptes"])
        info(a["reponse_comptes"])
    if "statistiques" in parties:
        info("Onglet Statistiques :")
        tableau(["carte", "solde", "crédits", "total crédité", "paiements", "total payé"], a["statistiques"])
        tableau(["numéro", "place", "état", "carte paiement", "montant", "clôture"], a["transactions"])


# ======================================================================
# ESSAI
# ======================================================================
VERT, ROUGE, GRIS = "#2e7d32", "#c62828", "#757575"
titre("PC-04 — Connexion du Raspberry Pi",
      f"MATÉRIEL RÉEL : broker {config.BROKER_IP} + Raspberry Pi" if MATERIEL_REEL else "SIMULATION : aucun réseau")


def bandes() -> tuple:
    affichage = lire_affichage(fenetre)
    info(f"bande PC  : {affichage['bande_pc']}")
    info(f"bande RPi : {affichage['bande_rpi']} ({affichage['couleur_bande_rpi']})")
    return affichage["bande_pc"], affichage["couleur_bande_rpi"]


fenetre, controleur = creer_app_pc(MATERIEL_REEL, MONTRER_FENETRE)
modele = controleur.modele

etape("0. Avant la connexion")
bandes()
verifier("Bande RPi grise (inconnu)", lire_affichage(fenetre)["couleur_bande_rpi"], GRIS)

if not MATERIEL_REEL:
    mqtt = controleur.mqtt
    traiter_evenements(0.3)

    etape("1. Le PC est connecté, le RPi ne s'est pas encore annoncé")
    pc, couleur = bandes()
    verifier("Bande PC : connecté", pc.startswith("PC → MQTT : connecté"), True)
    verifier("Bande RPi encore grise", couleur, GRIS)
    verifier("L'app écoute rpi/connexion", MqttTopics.CONNEXION_RPI in mqtt.topics, True)

    etape("2. Le RPi s'annonce en ligne")
    mqtt.injecter(MqttTopics.CONNEXION_RPI, {"en_ligne": True, "client": "esa-rpi-equipe-5"})
    verifier("Bande RPi verte", bandes()[1], VERT)
    verifier("Modèle : en ligne", modele.rpi_en_ligne, True)

    etape("3. Le broker publie le testament du RPi (débranché)")
    mqtt.injecter(MqttTopics.CONNEXION_RPI, {"en_ligne": False, "client": "esa-rpi-equipe-5"})
    verifier("Bande RPi rouge", bandes()[1], ROUGE)

    etape("4. Message de présence invalide : ignoré")
    mqtt.injecter(MqttTopics.CONNEXION_RPI, {"en_ligne": "oui"})
    verifier("Bande RPi toujours rouge", bandes()[1], ROUGE)

    etape("5. Le PC perd le broker : l'état du RPi redevient inconnu")
    mqtt.injecter(MqttTopics.CONNEXION_RPI, {"en_ligne": True})
    mqtt.disconnect_from_broker()
    pc, couleur = bandes()
    verifier("Bande PC : déconnecté", pc.startswith("PC → MQTT : déconnecté"), True)
    verifier("Bande RPi grise (on ne peut plus savoir)", couleur, GRIS)
    verifier("Modèle : inconnu", modele.rpi_en_ligne, None)

else:
    etape("1. Connexion au broker et présence du RPi (message conservé)")
    traiter_evenements(10, jusqua=lambda: modele.rpi_en_ligne is True)
    pc, couleur = bandes()
    verifier("Bande PC : connecté", pc.startswith("PC → MQTT : connecté"), True)
    verifier("Bande RPi verte (RPi en ligne)", couleur, VERT)

    etape("2. Arrêt du programme du RPi")
    consigne("Arrêtez le programme du Raspberry Pi (Ctrl+C dans main.py, ou fermez sa fenêtre) — 60 s")
    traiter_evenements(60, jusqua=lambda: modele.rpi_en_ligne is False)
    verifier("Bande RPi rouge après l'arrêt", bandes()[1], ROUGE)

    etape("3. Redémarrage du programme du RPi")
    consigne("Relancez le programme du Raspberry Pi (python3 main.py) — 60 s")
    traiter_evenements(60, jusqua=lambda: modele.rpi_en_ligne is True)
    verifier("Bande RPi de nouveau verte", bandes()[1], VERT)

controleur.shutdown()
terminer()
