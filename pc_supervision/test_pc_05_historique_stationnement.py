"""PC-05 — Historique des stationnements et client de chaque place.

Essai : l'onglet Stationnement de la vraie app PC
  - note chaque changement de place et de transaction dans l'historique,
    avec l'heure à gauche et des phrases claires (qui, quelle place, montant);
  - écrit sous chaque témoin le nom du client qui tient la place
    (transaction active), et rien quand la place est libre;
  - n'ajoute rien quand un message ne change rien ou est invalide.
Le PC construit l'historique lui-même en comparant chaque message reçu avec
le précédent : le Raspberry Pi n'a rien de nouveau à publier.

Ce que le terminal montre : chaque message du RPi simulé, puis le contenu
de l'historique et le texte de chaque place, lus dans les widgets.

Matériel minimal
    MATERIEL_REEL = False : aucun (messages du RPi simulés, sans réseau).
    MATERIEL_REEL = True  : broker à config.BROKER_IP et le Raspberry Pi qui
                            roule. Le test écoute 30 s et affiche ce que
                            l'historique a noté (faites bouger des places
                            pendant ce temps pour en voir plus).

Exécution : python test_pc_05_historique_stationnement.py
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


def lire_historique(fenetre) -> list:
    """Lignes de l'historique, sans l'heure (« E2.2 réservée ... »)."""
    texte = fenetre.page_stationnement.texte_historique.toPlainText()
    return [ligne[10:] for ligne in texte.split("\n") if ligne.strip()]


def afficher_historique(fenetre):
    info("Historique affiché dans l'onglet Stationnement :")
    for ligne in fenetre.page_stationnement.texte_historique.toPlainText().split("\n"):
        if ligne.strip():
            info(f"   {ligne}")


def places_avec(etats: dict, presences: dict = None) -> dict:
    """Message « places » : toutes LIBRE sauf celles données dans etats."""
    presences = presences or {}
    places = []
    for i in range(14):
        nom = f"E{1 + i // 7}.{1 + i % 7}"
        places.append({"place": nom, "numero": i + 1, "etat": etats.get(nom, "LIBRE"),
                       "presence": presences.get(nom, etats.get(nom) == "OCCUPE")})
    return {"places": places, "rampe": False, "horodatage": 1800000000.0}


THOMAS, SAMUEL = "0008580808", "0008909278"
STATISTIQUES = {"comptes": [
    {"rfid": THOMAS, "nom": "Thomas", "solde": 2500, "nb_credits": 0, "total_credits": 0, "nb_debits": 0, "total_debits": 0},
    {"rfid": SAMUEL, "nom": "Samuel", "solde": 2500, "nb_credits": 0, "total_credits": 0, "nb_debits": 0, "total_debits": 0}]}


def transaction(numero: int, place: str, carte: str, etat: str, montant=None) -> dict:
    return {"id": numero, "place": place, "rfid_initial": carte, "etat": etat,
            "debut_facturation": 1800000000.0 if etat != "CREEE" else None, "montant_fige": montant,
            "rfid_paiement": carte if etat in ("PAYEE", "RETRAIT_EN_COURS", "TERMINEE") else "",
            "fin": None, "erreur": ""}


def transactions(*liste) -> dict:
    return {"tarif_cents_par_minute": 25, "transactions": list(liste), "statistiques": STATISTIQUES,
            "horodatage": 1800000000.0}


titre("PC-05 — Historique des stationnements et clients des places",
      "BROKER RÉEL + Raspberry Pi" if MATERIEL_REEL else "SIMULATION : messages du RPi simulés")
fenetre, controleur = creer_app_pc(MATERIEL_REEL, MONTRER_FENETRE)
modele = controleur.modele

if not MATERIEL_REEL:
    mqtt = controleur.mqtt
    traiter_evenements(0.3)

    etape("0. Avant tout message du RPi")
    verifier("Historique vide", lire_historique(fenetre), [])

    etape("1. Premier état : un résumé, pas 14 lignes")
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE"}))
    mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "EN_STATIONNEMENT")))
    afficher_historique(fenetre)
    verifier("Résumé des places", lire_historique(fenetre)[0], "État reçu du Raspberry Pi : 13 libres, 1 occupée")
    verifier("Transactions déjà en cours", lire_historique(fenetre)[1], "1 transaction(s) en cours au démarrage du PC")
    afficher_affichage(fenetre, ("places",))
    verifier("E1.3 : état, client, présence", lire_affichage(fenetre)["places"]["E1.3"], "OCCUPE / Samuel / véhicule présent")
    verifier("E1.1 libre : pas de client", lire_affichage(fenetre)["places"]["E1.1"], "LIBRE / aucun véhicule")
    verifier("Infobulle de E1.3 : nom et carte",
             fenetre.page_stationnement._temoins["E1.3"][0].toolTip(), f"E1.3 : OCCUPE, Samuel ({SAMUEL})")

    etape("2. Thomas réserve E2.2")
    avant = len(lire_historique(fenetre))
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE", "E2.2": "RESERVE"}))
    mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "EN_STATIONNEMENT"),
                                                        transaction(8, "E2.2", THOMAS, "CREEE")))
    nouvelles = lire_historique(fenetre)[avant:]
    afficher_historique(fenetre)
    verifier("Place réservée notée", nouvelles[0], "E2.2 réservée")
    verifier("Transaction ouverte : qui et où", nouvelles[1], f"Transaction 000008 ouverte pour Thomas ({THOMAS}), place E2.2")
    verifier("E2.2 : client affiché", lire_affichage(fenetre)["places"]["E2.2"], "RESERVE / Thomas / aucun véhicule")

    etape("3. Le véhicule de Thomas est rangé")
    avant = len(lire_historique(fenetre))
    mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "EN_STATIONNEMENT"),
                                                        transaction(8, "E2.2", THOMAS, "EN_STATIONNEMENT")))
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE", "E2.2": "OCCUPE"}))
    nouvelles = lire_historique(fenetre)[avant:]
    verifier("Rangement", nouvelles[0], f"Véhicule de Thomas ({THOMAS}) rangé en E2.2 : début de la facturation")
    verifier("Place occupée par qui", nouvelles[1], f"E2.2 occupée par le véhicule de Thomas ({THOMAS})")
    verifier("E2.2 : client affiché", lire_affichage(fenetre)["places"]["E2.2"], "OCCUPE / Thomas / véhicule présent")

    etape("4. Retrait : demande, paiement, départ")
    avant = len(lire_historique(fenetre))
    for etat in ("PAIEMENT_EN_ATTENTE", "PAYEE", "RETRAIT_EN_COURS", "TERMINEE"):
        mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "EN_STATIONNEMENT"),
                                                            transaction(8, "E2.2", THOMAS, etat, 125)))
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE"}))
    nouvelles = lire_historique(fenetre)[avant:]
    afficher_historique(fenetre)
    verifier("Les 5 étapes du retrait sont notées", nouvelles, [
        f"Thomas ({THOMAS}) demande son véhicule (E2.2) : 1,25 $ à payer",
        f"Paiement accepté pour E2.2 : 1,25 $ débités à Thomas ({THOMAS})",
        f"Retrait du véhicule de Thomas ({THOMAS}) en cours (E2.2)",
        f"Thomas ({THOMAS}) est reparti de E2.2 : transaction 000008 terminée",
        "E2.2 de nouveau libre (était occupée)"])
    verifier("E2.2 libre : plus de client", lire_affichage(fenetre)["places"]["E2.2"], "LIBRE / aucun véhicule")
    verifier("E1.3 : toujours Samuel", lire_affichage(fenetre)["places"]["E1.3"], "OCCUPE / Samuel / véhicule présent")

    etape("5. Délai de paiement expiré")
    avant = len(lire_historique(fenetre))
    mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "PAIEMENT_EN_ATTENTE", 300)))
    mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "EN_STATIONNEMENT")))
    verifier("Expiration notée", lire_historique(fenetre)[-1],
             f"E1.3 : délai de paiement expiré, le véhicule de Samuel ({SAMUEL}) reste stationné")

    etape("6. Maintenance et défaut")
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE", "E1.7": "MAINTENANCE"}))
    verifier("Maintenance", lire_historique(fenetre)[-1], "E1.7 mise en maintenance")
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE", "E1.7": "DEFAUT"}))
    verifier("Défaut", lire_historique(fenetre)[-1], "E1.7 en DÉFAUT (était en maintenance)")

    etape("7. Rien de nouveau : rien n'est ajouté")
    avant = len(lire_historique(fenetre))
    mqtt.injecter(MqttTopics.PLACES, places_avec({"E1.3": "OCCUPE", "E1.7": "DEFAUT"}))
    mqtt.injecter(MqttTopics.TRANSACTIONS, transactions(transaction(7, "E1.3", SAMUEL, "EN_STATIONNEMENT")))
    verifier("Message identique : aucune ligne", len(lire_historique(fenetre)), avant)
    mqtt.injecter(MqttTopics.PLACES, json.dumps({"places": [{"place": "E1.1"}]}))
    verifier("Message invalide : aucune ligne", len(lire_historique(fenetre)), avant)
    verifier("Message invalide : E1.7 toujours en défaut", lire_affichage(fenetre)["places"]["E1.7"],
             "DEFAUT / aucun véhicule")

else:
    etape("1. Écoute du vrai Raspberry Pi pendant 30 s")
    consigne("Faites changer des places pendant ce temps (réservation, dépôt, retrait) pour remplir l'historique.")
    traiter_evenements(30)
    afficher_historique(fenetre)
    afficher_affichage(fenetre, ("places",))
    verifier("Au moins le résumé du premier état", len(lire_historique(fenetre)) >= 1, True)

controleur.shutdown()
terminer()
