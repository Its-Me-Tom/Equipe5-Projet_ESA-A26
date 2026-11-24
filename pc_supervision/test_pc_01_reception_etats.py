"""PC-01 — Réception et affichage des états.

Essai (énoncé T13, test 3, côté PC) : l'app PC reçoit l'état général, les
14 places, les anomalies et les transactions publiés par le Raspberry Pi,
et les AFFICHE correctement (texte et couleur de chaque place, état de la
borne, tableaux). C'est la vraie app (fenêtre + contrôleur) qui est testée.

Ce que le terminal montre : chaque message reçu, le journal de l'app, puis
tout ce que l'app affiche (lu dans les widgets).

Matériel minimal
    MATERIEL_REEL = False : aucun (messages du RPi simulés, sans réseau).
    MATERIEL_REEL = True  : broker à config.BROKER_IP et le Raspberry Pi qui
                            roule (main.py ou un test T13). Le test attend les
                            vrais messages du RPi et vérifie qu'ils respectent
                            le contrat et s'affichent. L'app PC peut rester
                            ouverte en même temps.

Exécution : python test_pc_01_reception_etats.py
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
from src.views.page_stationnement import ARRONDI_TEMOIN, TAILLE_TEMOIN


# ----------------------------------------------------------------------
# RÉGLAGES DU TEST (modifiez ici)
# ----------------------------------------------------------------------
MATERIEL_REEL = False      # True = vrai broker + vrai Raspberry Pi
MONTRER_FENETRE = False    # True = ouvre aussi la fenêtre pendant le test

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
        tableau(["carte", "nom", "solde"], a["comptes"])
        info(a["reponse_comptes"])
    if "statistiques" in parties:
        info("Onglet Statistiques :")
        tableau(["carte", "solde", "crédits", "total crédité", "paiements", "total payé"], a["statistiques"])
        tableau(["numéro", "place", "état", "carte paiement", "montant", "clôture"], a["transactions"])


# ======================================================================
# ESSAI
# ======================================================================
titre("PC-01 — Réception et affichage des états",
      f"MATÉRIEL RÉEL : broker {config.BROKER_IP} + Raspberry Pi" if MATERIEL_REEL else "SIMULATION : aucun réseau")

fenetre, controleur = creer_app_pc(MATERIEL_REEL, MONTRER_FENETRE)
modele = controleur.modele

if not MATERIEL_REEL:
    mqtt = controleur.mqtt
    traiter_evenements(0.3)

    etape("0. Avant tout message du RPi")
    verifier("État INCONNU", modele.etat_service, "INCONNU")
    verifier("Places grises (couleur inconnue)", set(lire_affichage(fenetre)["couleurs_places"].values()),
             {config.COULEUR_INCONNUE.lower()})
    verifier("Témoins des places : carrés aux coins arrondis (pas des cercles)",
             0 < ARRONDI_TEMOIN < TAILLE_TEMOIN // 2 and all(f"border-radius: {ARRONDI_TEMOIN}px" in temoin.styleSheet()
             for temoin, _ in fenetre.page_stationnement._temoins.values()), True)

    etape("1. État général")
    mqtt.injecter(MqttTopics.ETAT, {"etat_service": "MISE_HORS_SERVICE", "etat_retrait": "MOUVEMENT",
                                    "transaction_active": 12, "message": "Récupération en cours",
                                    "horodatage": 1800000000.0})
    affichage = lire_affichage(fenetre)
    verifier("Modèle : état de service", modele.etat_service, "MISE_HORS_SERVICE")
    verifier("Affiché : état de la borne", affichage["etat"], "MISE_HORS_SERVICE")
    verifier("Affiché : couleur orange", affichage["couleur_etat"], config.COULEURS_SERVICE["MISE_HORS_SERVICE"])
    verifier("Affiché : détail du retrait", affichage["detail"], "Retrait : MOUVEMENT — Récupération en cours")

    etape("2. Les 14 places (les 5 états, présence IR)")
    etats_places = ["LIBRE", "RESERVE", "OCCUPE", "MAINTENANCE", "DEFAUT", "LIBRE", "OCCUPE"] * 2
    places = [{"place": f"E{1 + i // 7}.{1 + i % 7}", "numero": i + 1, "etat": etats_places[i],
               "presence": etats_places[i] == "OCCUPE"} for i in range(14)]
    places[13]["presence"] = None
    mqtt.injecter(MqttTopics.PLACES, {"places": places, "rampe": True, "horodatage": 1800000000.0})
    affichage = lire_affichage(fenetre)
    afficher_affichage(fenetre, ("places",))
    verifier("Modèle : 14 places", len(modele.places), 14)
    for place in places[:5] + [places[13]]:
        nom = place["place"]
        verifier(f"{nom} : couleur {place['etat']}", affichage["couleurs_places"][nom],
                 config.COULEURS_PLACES[place["etat"]].lower())
    verifier("E1.3 : texte (état + présence)", affichage["places"]["E1.3"], "OCCUPE / véhicule présent")
    verifier("E2.7 : présence inconnue affichée", affichage["places"]["E2.7"], "OCCUPE / IR inconnu")
    verifier("Zone devant la barrière", affichage["rampe"], "Zone devant la barrière : véhicule présent")

    etape("3. Anomalies")
    mqtt.injecter(MqttTopics.ANOMALIES, {"anomalies": [
        {"id": 1, "tache": "T12", "code": "CAN_SANS_REPONSE", "message": "Aucune réponse CAN à la commande",
         "place": "E1.3", "critique": True, "horodatage": 1800000000.0},
        {"id": 2, "tache": "T07", "code": "DEL_REFUSEE", "message": "DEL refusée", "place": "E2.2",
         "critique": False, "horodatage": 1800000001.0}], "horodatage": 1800000001.0})
    lignes = lire_affichage(fenetre)["anomalies"]
    afficher_affichage(fenetre, ("anomalies",))
    verifier("Deux anomalies affichées", len(lignes), 2)
    verifier("1re : tâche, code, place, critique", [lignes[0][1], lignes[0][2], lignes[0][4], lignes[0][5]],
             ["T12", "CAN_SANS_REPONSE", "E1.3", "oui"])
    verifier("2e : non critique", lignes[1][5], "non")

    etape("4. Transactions et statistiques")
    mqtt.injecter(MqttTopics.TRANSACTIONS, {
        "tarif_cents_par_minute": 25,
        "transactions": [{"id": 12, "place": "E2.1", "rfid_initial": "0A1B2C3D4E", "etat": "TERMINEE",
                          "debut_facturation": 1800000000.0, "montant_fige": 250, "rfid_paiement": "0A1B2C3D4E",
                          "fin": 1800000900.0, "erreur": ""}],
        "statistiques": {"comptes": [{"rfid": "0A1B2C3D4E", "solde": 2250, "nb_credits": 1, "total_credits": 1000,
                                      "nb_debits": 1, "total_debits": 250}]},
        "horodatage": 1800000900.0})
    affichage = lire_affichage(fenetre)
    afficher_affichage(fenetre, ("statistiques",))
    verifier("Modèle : tarif", modele.tarif, 25)
    verifier("Ligne de statistiques affichée", affichage["statistiques"],
             [["0A1B2C3D4E", "22,50 $", "1", "10,00 $", "1", "2,50 $"]])
    verifier("Transaction affichée (numéro, place, état, carte, montant)", affichage["transactions"][0][:5],
             ["000012", "E2.1", "TERMINEE", "0A1B2C3D4E", "2,50 $"])

    etape("5. Un topic d'une autre équipe n'est pas traité")
    mqtt.topics.append("esa/Equipe_99/etat")           # même s'il arrivait jusqu'à l'app
    mqtt.injecter("esa/Equipe_99/etat", {"etat_service": "ARRET_VERROUILLE"})
    verifier("État de service inchangé", modele.etat_service, "MISE_HORS_SERVICE")
    verifier("Affichage inchangé", lire_affichage(fenetre)["etat"], "MISE_HORS_SERVICE")

else:
    etape("1. Réception des messages conservés du Raspberry Pi")
    recu = traiter_evenements(15, jusqua=lambda: modele.etat_service != "INCONNU" and len(modele.places) == 14
                              and modele.statistiques != [] and modele.rpi_en_ligne is not None)
    if not recu:
        info("Rien (ou pas tout) reçu en 15 s : le RPi roule-t-il? Même BROKER_IP des deux côtés?")
    verifier("Connecté au broker", controleur.mqtt.is_connected, True)
    verifier("Le RPi s'annonce en ligne (rpi/connexion)", modele.rpi_en_ligne, True)
    verifier("État de service connu", modele.etat_service in config.COULEURS_SERVICE, True)
    verifier("14 places reçues", len(modele.places), 14)
    verifier("Numéros des places 1 à 14", sorted(p.get("numero") for p in modele.places), list(range(1, 15)))
    verifier("États des places valides (contrat)", [p["place"] for p in modele.places
                                                    if p.get("etat") not in config.COULEURS_PLACES], [])
    verifier("Statistiques reçues (au moins un compte)", len(modele.statistiques) >= 1, True)
    verifier("Tarif reçu", isinstance(modele.tarif, int), True)

    etape("2. Ce que l'app affiche")
    afficher_affichage(fenetre)
    affichage = lire_affichage(fenetre)
    verifier("Bande RPi verte", affichage["couleur_bande_rpi"], "#2e7d32")
    verifier("Aucune place restée grise", [n for n, c in affichage["couleurs_places"].items()
                                          if c == config.COULEUR_INCONNUE.lower()], [])
    verifier("État de la borne affiché", affichage["etat"], modele.etat_service)

controleur.shutdown()
terminer()