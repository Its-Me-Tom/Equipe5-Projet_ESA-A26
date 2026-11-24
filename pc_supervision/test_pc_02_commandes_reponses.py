"""PC-02 — Commandes et réponses.

Essai (énoncé T13, tests 4 à 6, côté PC) : chaque bouton de l'app envoie
la bonne commande (bon topic, id_commande unique, champs), la réponse du
RPi est associée à sa commande par id_commande et affichée, le renvoi garde
le même id_commande, et une commande sans réponse est signalée.

Ce que le terminal montre : chaque commande publiée par l'app (JSON), chaque
réponse reçue, le journal de l'app et les textes affichés.

Matériel minimal
    MATERIEL_REEL = False : aucun (clics simulés, réponses simulées).
    MATERIEL_REEL = True  : broker à config.BROKER_IP et le Raspberry Pi qui
                            roule. Seules des commandes SANS EFFET sont
                            envoyées (consulter les soldes, réinitialiser sans
                            confirmation) : aucun compte n'est modifié.

Exécution : python test_pc_02_commandes_reponses.py
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
titre("PC-02 — Commandes et réponses",
      f"MATÉRIEL RÉEL : broker {config.BROKER_IP} + Raspberry Pi" if MATERIEL_REEL else "SIMULATION : aucun réseau")

fenetre, controleur = creer_app_pc(MATERIEL_REEL, MONTRER_FENETRE)
modele = controleur.modele

if not MATERIEL_REEL:
    mqtt = controleur.mqtt
    traiter_evenements(0.3)

    def reponse(commande: dict, topic: str, **champs):
        contenu = {"id_commande": commande["id_commande"], "commande": commande["commande"], "resultat": "ACCEPTEE",
                   "code": "OK", "message": "", "horodatage": 1800000000.0}
        contenu.update(champs)
        mqtt.injecter(topic, contenu)

    etape("1. À la connexion, l'app demande les soldes")
    topic, commande = mqtt.publies[0]
    verifier("Commande envoyée automatiquement", commande["commande"], "CONSULTER_SOLDE")
    verifier("Sur le topic comptes/commande", topic, MqttTopics.COMMANDE_COMPTES)
    reponse(commande, MqttTopics.REPONSE_COMPTES,
            comptes=[{"rfid": "0A1B2C3D4E", "solde": 2500}, {"rfid": "1F00AA5501", "solde": 1000}])
    afficher_affichage(fenetre, ("comptes",))
    verifier("Tableau des comptes", lire_affichage(fenetre)["comptes"], [["0A1B2C3D4E", "25,00 $"],
                                                                         ["1F00AA5501", "10,00 $"]])
    verifier("Plus en attente de réponse", modele.en_attente, {})

    etape("2. Boutons de l'onglet Commandes")
    page = fenetre.page_commandes
    boutons = [(page.bouton_hors_service, "METTRE_HORS_SERVICE"), (page.bouton_en_service, "REMETTRE_EN_SERVICE"),
               (page.bouton_arret, "ARRET_IMMEDIAT")]
    for bouton, nom in boutons:
        bouton.click()
        topic, commande = mqtt.publies[-1]
        verifier(f"« {bouton.text()} » -> {nom} sur commande", (commande["commande"], topic), (nom, MqttTopics.COMMANDE))
    page.case_intervention.setChecked(False)
    page.bouton_reinitialiser.click()
    verifier("Réinitialiser, case décochée : intervention_confirmee = False",
             mqtt.publies[-1][1].get("intervention_confirmee"), False)
    page.case_intervention.setChecked(True)
    page.bouton_reinitialiser.click()
    verifier("Réinitialiser, case cochée : intervention_confirmee = True",
             mqtt.publies[-1][1].get("intervention_confirmee"), True)
    identifiants = [commande["id_commande"] for _, commande in mqtt.publies]
    info(f"id_commande utilisés : {identifiants}")
    verifier("Tous les id_commande sont différents", len(set(identifiants)), len(identifiants))

    etape("3. Une réponse est associée à SA commande (par id_commande)")
    arret = mqtt.publies[3][1]
    verifier("5 commandes en attente de réponse", len(modele.en_attente), 5)
    reponse(arret, MqttTopics.REPONSE_COMMANDE, message="Arrêt logiciel : borne verrouillée")
    verifier("La commande ARRET_IMMEDIAT n'est plus en attente", arret["id_commande"] in modele.en_attente, False)
    verifier("Les autres attendent toujours", len(modele.en_attente), 4)
    verifier("Réponse affichée dans l'onglet Commandes", lire_affichage(fenetre)["reponse_commandes"],
             "Réponse : ARRET_IMMEDIAT -> ACCEPTEE (OK) Arrêt logiciel : borne verrouillée")
    refusee = mqtt.publies[4][1]
    reponse(refusee, MqttTopics.REPONSE_COMMANDE, resultat="REFUSEE", code="INTERVENTION_NON_CONFIRMEE",
            message="Confirmer l'intervention manuelle")
    verifier("Une réponse refusée est affichée aussi", lire_affichage(fenetre)["reponse_commandes"],
             "Réponse : REINITIALISER -> REFUSEE (INTERVENTION_NON_CONFIRMEE) Confirmer l'intervention manuelle")

    etape("4. Crédit et renvoi (même id_commande)")
    comptes = fenetre.page_comptes
    comptes.tableau.clearSelection()
    comptes.tableau.setCurrentCell(-1, -1)
    nombre = len(mqtt.publies)
    comptes.bouton_crediter.click()
    verifier("Sans compte sélectionné : rien n'est envoyé", len(mqtt.publies), nombre)
    verifier("Message à l'utilisateur", lire_affichage(fenetre)["reponse_comptes"],
             "Réponse : sélectionner d'abord un compte.")
    comptes.tableau.selectRow(0)
    comptes.saisie_montant.setValue(10.00)
    comptes.bouton_crediter.click()
    topic, credit = mqtt.publies[-1]
    verifier("Crédit : topic, commande, carte, montant en cents",
             (topic, credit["commande"], credit["rfid"], credit["montant"]),
             (MqttTopics.COMMANDE_COMPTES, "AJOUTER_CREDIT", "0A1B2C3D4E", 1000))
    comptes.bouton_renvoyer.click()
    verifier("Renvoi : MÊME id_commande", mqtt.publies[-1][1]["id_commande"], credit["id_commande"])
    reponse(credit, MqttTopics.REPONSE_COMPTES, rfid="0A1B2C3D4E", solde=3500, message="Crédit ajouté")
    verifier("Solde mis à jour dans le tableau", lire_affichage(fenetre)["comptes"][0], ["0A1B2C3D4E", "35,00 $"])

    etape(f"5. Commande sans réponse : signalée après {config.DELAI_REPONSE_S} s")
    page.bouton_en_service.click()
    oubliee = mqtt.publies[-1][1]["id_commande"]
    signalee = traiter_evenements(config.DELAI_REPONSE_S + 2, jusqua=lambda: oubliee not in modele.en_attente)
    verifier("Commande retirée de l'attente et signalée dans le journal", signalee, True)
    verifier("Message dans le journal de l'app",
             f"Aucune réponse du Raspberry Pi à la commande {oubliee}" in fenetre.texte_journal.toPlainText(), True)

    etape("6. Sans connexion, rien n'est envoyé")
    mqtt.disconnect_from_broker()
    nombre = len(mqtt.publies)
    page.bouton_hors_service.click()
    verifier("Aucune publication", len(mqtt.publies), nombre)
    verifier("Message « Non envoyée » dans le journal", "Non envoyée (déconnecté)" in fenetre.texte_journal.toPlainText(),
             True)

else:
    traiter_evenements(10, jusqua=lambda: controleur.mqtt.is_connected and modele.rpi_en_ligne is not None)
    verifier("Connecté au broker", controleur.mqtt.is_connected, True)
    verifier("Le RPi est en ligne", modele.rpi_en_ligne, True)

    etape("1. Consulter les soldes : le vrai RPi répond")
    fenetre.page_comptes.bouton_actualiser.click()
    id_commande = modele.derniere_commande["id_commande"]
    traiter_evenements(10, jusqua=lambda: (modele.derniere_reponse or {}).get("id_commande") == id_commande)
    reponse = modele.derniere_reponse or {}
    info(f"réponse du RPi : {reponse}")
    verifier("Réponse associée à la commande", reponse.get("id_commande"), id_commande)
    verifier("Consultation acceptée", reponse.get("resultat"), "ACCEPTEE")
    afficher_affichage(fenetre, ("comptes",))
    verifier("Tableau des comptes rempli", len(lire_affichage(fenetre)["comptes"]) >= 1, True)

    etape("2. Une commande refusée reçoit aussi sa réponse (sans effet sur la borne)")
    if modele.etat_service == "ARRET_VERROUILLE":
        info("La borne est verrouillée : étape sautée pour ne pas la réinitialiser par erreur")
    else:
        fenetre.page_commandes.case_intervention.setChecked(False)
        fenetre.page_commandes.bouton_reinitialiser.click()
        id_commande = modele.derniere_commande["id_commande"]
        traiter_evenements(10, jusqua=lambda: (modele.derniere_reponse or {}).get("id_commande") == id_commande)
        reponse = modele.derniere_reponse or {}
        info(f"réponse du RPi : {reponse}")
        verifier("Réponse associée à la commande", reponse.get("id_commande"), id_commande)
        verifier("Refusée", reponse.get("resultat"), "REFUSEE")
        verifier("Affichée dans l'onglet Commandes", lire_affichage(fenetre)["reponse_commandes"].startswith(
            "Réponse : REINITIALISER -> REFUSEE"), True)

controleur.shutdown()
terminer()
