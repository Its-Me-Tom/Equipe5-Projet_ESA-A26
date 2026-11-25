"""T12-10 — Sortie occupée.

Essai (énoncé T12) : si un véhicule est déjà devant la barrière, aucun
mouvement ne commence, même après le paiement. La séquence démarre toute
seule quand la zone est libérée. Un seul retrait à la fois.

Ce que le terminal montre : l'IR de la rampe, l'état AUTORISE en attente,
l'absence de commande moteur, puis le démarrage.

Matériel minimal
    MATERIEL_REEL = False : aucun.
    MATERIEL_REEL = True  : HAT CAN + STM32 Haut pour l'IR de la rampe
                            seulement et un véhicule. Le faux STM32 simule
                            les moteurs (code MOTEUR du Haut inactif, ou
                            ajouter "moteurs" à FONCTIONS_REELLES).

Exécution : python3 test_t12_10_sortie_occupee.py
"""


import atexit
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from src import config
from src.controllers.service_rpi import ServiceRPi
from src.format_carte import carte_vers_texte, decrire_carte
from src.horloge import Horloge
from src.simulation.faux_broker import BROKER


# ----------------------------------------------------------------------
# RÉGLAGES DU TEST (modifiez ici)
# ----------------------------------------------------------------------
MATERIEL_REEL = True       # True = vrai bus can0 + vrai IR de la rampe (STM32 Haut) | False = simulation
FONCTIONS_REELLES = {"ir_rampe"}

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


# ---------- Décodage lisible des trames CAN (protocole ESA v1.6) ----------
NOMS_CAN = {
    0x001: "ARRET_HAUT", 0x002: "ARRET_BAS", 0x003: "ARRET_BORNE", 0x004: "ARRET_RPI",
    0x010: "DEFAUT_HAUT", 0x011: "DEFAUT_BAS", 0x012: "DEFAUT_BORNE",
    0x040: "HEARTBEAT_RPI", 0x041: "HEARTBEAT_HAUT", 0x042: "HEARTBEAT_BAS", 0x043: "HEARTBEAT_BORNE",
    0x050: "REARMEMENT_CMD", 0x051: "REARMEMENT_HAUT", 0x052: "REARMEMENT_BAS", 0x053: "REARMEMENT_BORNE",
    0x080: "SYNCHRO_CMD",
    0x100: "ELEVATION_CMD", 0x110: "ROTATION_CMD", 0x120: "BRAS_CMD", 0x130: "ECLAIRAGE_CMD",
    0x200: "ELEVATION_ETAT", 0x210: "ROTATION_ETAT", 0x220: "BRAS_ETAT",
    0x300: "IR_BAS_CHANGEMENT", 0x301: "IR_BAS_COMPLET", 0x302: "IR_LECTURE_CMD",
    0x310: "IR_ENTREE_CHANGEMENT", 0x311: "IR_ENTREE_COMPLET",
    0x340: "DEL_PLACE_CMD", 0x341: "DEL_BAS_ETAT", 0x342: "DEL_HAUT_ETAT",
    0x350: "ECLAIRAGE_BAS_ETAT", 0x351: "ECLAIRAGE_HAUT_ETAT", 0x352: "ECLAIRAGE_BORNE_ETAT",
}
ACTIONS_CAN = {
    0x100: {0: "arrêt", 1: "déplacer", 3: "soulever", 4: "abaisser"},
    0x110: {0: "arrêt", 1: "déplacer"},
    0x120: {0: "arrêt", 1: "déployer", 2: "rétracter"},
}
RESULTATS_CAN = {0: "refusé", 1: "accepté", 2: "terminé", 3: "interrompu", 4: "défaut"}
ETATS_HEARTBEAT = {0: "initialisation", 1: "prêt", 2: "occupé", 3: "verrouillé", 4: "défaut"}
HEARTBEATS = (0x040, 0x041, 0x042, 0x043)


def decoder_trame(can_id: int, donnees) -> str:
    """Une trame CAN en texte : identifiant, nom, octets bruts et champs."""
    d = list(donnees)
    brut = " ".join(f"{octet:02X}" for octet in d)

    try:
        if can_id in ACTIONS_CAN:
            cible = {0x100: "niveau", 0x110: "angle", 0x120: "réservé"}[can_id]
            champs = f"séq={d[0]} action={ACTIONS_CAN[can_id].get(d[1], d[1])} {cible}={d[2]}"
        elif can_id in (0x200, 0x210, 0x220):
            champs = f"séq={d[0]} résultat={RESULTATS_CAN.get(d[1], d[1])} position={d[2]} défaut={d[3]}"
        elif can_id == 0x340:
            mode = "clignotant 1 Hz" if d[5] else "fixe"
            champs = f"séq={d[0]} place={d[1]} R={d[2]} V={d[3]} B={d[4]} mode={mode}"
        elif can_id in (0x341, 0x342):
            champs = f"séq={d[0]} place={d[1]} résultat={'appliqué' if d[2] == 1 else 'REFUSÉ'}"
        elif can_id == 0x130:
            champs = f"séq={d[0]} niveau={d[1]} R={d[2]} V={d[3]} B={d[4]}"
        elif can_id in (0x350, 0x351, 0x352):
            champs = f"séq={d[0]} niveau={d[1]} résultat={'appliqué' if d[2] == 1 else 'REFUSÉ'}"
        elif can_id in (0x001, 0x002, 0x003, 0x004):
            champs = f"motif={d[0]} source={d[1]} détail={d[2]}"
        elif can_id in (0x010, 0x011, 0x012):
            champs = f"source={d[0]} code={d[1]} gravité={d[2]} détail={d[3]}"
        elif can_id in HEARTBEATS:
            champs = f"compteur={d[0]} état={ETATS_HEARTBEAT.get(d[1], d[1])}"
        elif can_id == 0x050:
            champs = f"séq={d[0]} action={d[1]}"
        elif can_id in (0x051, 0x052, 0x053):
            champs = f"séq={d[0]} résultat={'accepté' if d[1] == 1 else 'REFUSÉ'} motif={d[2]}"
        elif can_id == 0x080:
            champs = f"cible={ {1: 'capteurs', 2: 'moteurs', 3: 'tous'}.get(d[0], d[0]) }"
        elif can_id == 0x300:
            champs = f"IR place {d[0]} -> {'présent' if d[1] else 'absent'} compteur={d[2]}"
        elif can_id == 0x301:
            masque = d[0] | (d[1] << 8)
            presents = [indice for indice in range(14) if masque & (1 << indice)]
            champs = f"IR présents={presents} compteur={d[2]} valide={d[3] == 1}"
        elif can_id == 0x310:
            champs = f"IR rampe -> {'présent' if d[1] else 'absent'} compteur={d[2]}"
        elif can_id == 0x311:
            champs = f"IR rampe={'présent' if d[0] else 'absent'} compteur={d[1]} valide={d[2] == 1}"
        else:
            champs = ""
    except IndexError:
        champs = "(trame trop courte)"

    return f"0x{can_id:03X} {NOMS_CAN.get(can_id, '?'):<20} [{brut}]  {champs}"


# ---------- Service complet du RPi (T12, T13) avec trace de tout ce qui se passe ----------
def creer_service(dossier: Path | None = None, rfid_reel: bool = False, mqtt_reel: bool = False,
                  fonctions_reelles=None, duree_mouvement: float = 0.2,
                  trace_can: bool = True, trace_mqtt: bool = False) -> ServiceRPi:
    """Construit et démarre un ServiceRPi : tout simulé, sauf ce qui est demandé.

    rfid_reel         : vrai lecteur RFID (config.PORT_RFID)
    mqtt_reel         : vrai broker (config.BROKER_IP)
    fonctions_reelles : fonctions de vrais STM32 sur le vrai bus can0,
                        ex. {"ir_places"}; None = CAN entièrement simulé
    trace_can / trace_mqtt : afficher chaque trame CAN / message MQTT
    """
    temps_reel = rfid_reel or mqtt_reel or fonctions_reelles is not None
    BROKER.vider()

    service = ServiceRPi(
        HorlogeTest(temps_reel),
        dossier or creer_dossier_donnees(),
        simuler_rfid=not rfid_reel,
        simuler_can=fonctions_reelles is None,
        simuler_mqtt=not mqtt_reel,
        fonctions_reelles=fonctions_reelles,
    )
    service.trace = {"actif": False, "can": trace_can, "mqtt": trace_mqtt, "publies": {}}
    service.envoyees = []               # trames envoyées par le RPi : (identifiant, données)
    service.trames = []                 # toutes les trames, dans l'ordre : (sens, identifiant, données)
    service.commandes_recues = []       # commandes MQTT reçues par le RPi (dict)
    service.topics_publies = set()      # tous les topics où le RPi a publié
    _installer_trace(service)

    info("Démarrage du service RPi : "
         f"RFID {'RÉEL' if rfid_reel else 'simulé'}, "
         f"MQTT {'RÉEL (' + config.BROKER_IP + ')' if mqtt_reel else 'simulé'}, "
         f"CAN {'RÉEL ' + str(sorted(fonctions_reelles)) if fonctions_reelles is not None else 'simulé'}")
    service.demarrer()

    # Le matériel réel demandé doit répondre, sinon le test n'a pas de sens
    if rfid_reel and not service.lecteur.est_disponible():
        arreter_test(service.lecteur.derniere_erreur)

    if fonctions_reelles is not None and not service.can.is_connected():
        arreter_test(f"Bus CAN inaccessible : {service.can.last_error}")

    if mqtt_reel and not executer(service, 5, jusqua=service.mqtt.is_connected):
        arreter_test(f"Broker {config.BROKER_IP}:{config.BROKER_PORT} injoignable")

    service.faux_stm32.duree_mouvement = duree_mouvement
    executer(service, 0.3)                  # synchronisation de départ (DEL, éclairage, IR)

    if fonctions_reelles is not None:
        if "ir_places" in fonctions_reelles and not executer(
                service, 3, jusqua=lambda: None not in service.stationnement.presence_places.values()):
            arreter_test("Le STM32 Bas n'a pas envoyé l'état des IR des places (0x301)")

        if "ir_rampe" in fonctions_reelles and not executer(
                service, 3, jusqua=lambda: service.stationnement.presence_rampe is not None):
            arreter_test("Le STM32 Haut n'a pas envoyé l'état de l'IR de la rampe (0x311)")

    info(f"Service prêt ({len(service.envoyees)} trames CAN de démarrage : éclairage, DEL, synchro)")
    service.journal.clear()
    service.trace["instantane"] = _instantane(service)
    service.trace["actif"] = True
    return service


def _temps(service) -> str:
    return f"[t={service.horloge.monotone() - 1000.0:7.2f} s]"


def _installer_trace(service):
    """Affiche les trames CAN et les messages MQTT au moment où ils passent."""
    can, mqtt = service.can, service.mqtt
    envoyer, recevoir, publier = can.send, can.receive, mqtt.publish

    def envoyer_et_afficher(can_id, donnees):
        resultat = envoyer(can_id, donnees)
        service.envoyees.append((can_id, list(donnees)))
        service.trames.append(("envoyée", can_id, list(donnees)))
        if service.trace["actif"] and service.trace["can"] and can_id not in HEARTBEATS:
            print(f"      {_temps(service)} RPi -> CAN {decoder_trame(can_id, donnees)}")
        return resultat

    def recevoir_et_afficher():
        message = recevoir()
        if message is not None:
            service.trames.append(("reçue", message.arbitration_id, list(message.data)))
        if (message is not None and service.trace["actif"] and service.trace["can"]
                and message.arbitration_id not in HEARTBEATS):
            print(f"      {_temps(service)} CAN -> RPi {decoder_trame(message.arbitration_id, message.data)}")
        return message

    def publier_et_afficher(topic, payload, retain=False):
        service.topics_publies.add(topic)
        if service.trace["actif"] and service.trace["mqtt"]:
            contenu = _sans_horodatage(payload)
            if service.trace["publies"].get(topic) != contenu:      # republication identique : rien
                service.trace["publies"][topic] = contenu
                court = topic.split("/", 2)[-1]
                etat = "publié" if mqtt.is_connected() else "NON PUBLIÉ (RPi déconnecté)"
                print(f"      {_temps(service)} RPi -> MQTT {court} : {etat}, {len(payload)} octets"
                      f"{' (conservé)' if retain else ''}")
        return publier(topic, payload, retain)

    can.send, can.receive, mqtt.publish = envoyer_et_afficher, recevoir_et_afficher, publier_et_afficher

    for nom in ("traiter_commande", "traiter_commande_compte"):
        traiter = getattr(service.supervision, nom)

        def traiter_et_afficher(message, traiter=traiter):
            service.commandes_recues.append(message)
            if service.trace["mqtt"]:
                print(f"      {_temps(service)} MQTT -> RPi commande reçue : {json.dumps(message, ensure_ascii=False)}")
            traiter(message)

        setattr(service.supervision, nom, traiter_et_afficher)


def _sans_horodatage(payload: str):
    try:
        contenu = json.loads(payload)
        if isinstance(contenu, dict):
            contenu.pop("horodatage", None)
        return contenu
    except ValueError:
        return payload


def _abrege(payload: str, longueur: int = 230) -> str:
    return payload if len(payload) <= longueur else payload[:longueur] + f"... ({len(payload)} caractères)"


def _instantane(service) -> dict:
    """Ce qu'on surveille pour afficher les changements."""
    return {
        "borne": service.stationnement.etat_service,
        "T12": service.retrait.etat,
        "écran T12": service.retrait.message,
        "places": dict(service.stationnement.etats_places),
        "IR places": dict(service.stationnement.presence_places),
        "IR rampe": service.stationnement.presence_rampe,
        "transactions": {t["id"]: t["etat"] for t in service.transactions.obtenir_transactions()},
        "anomalies": len(service.stationnement.anomalies),
    }


def _afficher_changements(service):
    """Affiche le journal du service et ce qui a changé depuis le dernier tour."""
    for ligne in service.journal:
        print(f"      {_temps(service)} journal : {ligne}")
    service.journal.clear()

    avant, apres = service.trace["instantane"], _instantane(service)
    t = _temps(service)

    for cle in ("borne", "T12", "écran T12", "IR rampe"):
        if avant[cle] != apres[cle]:
            print(f"      {t} {cle} : {avant[cle]!r} -> {apres[cle]!r}")

    for place, etat in apres["places"].items():
        if avant["places"].get(place) != etat:
            print(f"      {t} place {place} : {avant['places'].get(place)} -> {etat}")

    for place, present in apres["IR places"].items():
        if avant["IR places"].get(place) != present:
            print(f"      {t} IR de la place {place} : {avant['IR places'].get(place)} -> {present}")

    for numero, etat in apres["transactions"].items():
        if avant["transactions"].get(numero) != etat:
            print(f"      {t} transaction {numero:06d} : {avant['transactions'].get(numero)} -> {etat}")

    for anomalie in service.stationnement.anomalies[avant["anomalies"]:]:
        gravite = "CRITIQUE" if anomalie["critique"] else "non critique"
        print(f"      {t} ANOMALIE {anomalie['tache']} {anomalie['code']} ({gravite}) : {anomalie['message']}")

    service.trace["instantane"] = apres


def executer(service, secondes: float, jusqua=None) -> bool:
    """Fait tourner la boucle du service pendant « secondes ».

    S'arrête dès que « jusqua() » est vrai. Retourne True si atteint.
    """
    for _ in range(max(1, int(secondes / config.PERIODE_BOUCLE_S))):
        service.executer_tour()
        afficher_en_attente()

        if service.trace["actif"]:
            _afficher_changements(service)

        un_tour_de_temps(service.horloge)

        if jusqua is not None and jusqua():
            return True

    return False


def garer_vehicule(service, place: str, carte: int, minutes: float = 0) -> int:
    """Range un véhicule (doublure de T03 + T11), puis fait passer du temps."""
    transaction_id = service.depot.deposer(place, carte)
    info(f"Véhicule garé sur {place} avec la carte {carte_txt(carte)} : transaction {transaction_id:06d}")
    executer(service, 0.2)

    if minutes:
        service.horloge.avancer(minutes * 60)
        info(f"... {minutes} min de stationnement passent (horloge du test)")

    return transaction_id


def presenter_carte(service, carte: int, texte: str = "Passez la puce") -> bool:
    """Présente une carte : injectée en simulation, vraie puce en mode réel."""
    if not hasattr(service, "lectures"):
        service.lectures = []
        service.receveurs_carte.insert(0, service.lectures.append)   # POINT DE BRANCHEMENT

    avant = len(service.lectures)

    if service.lecteur.simuler:
        info(f"Carte {carte_txt(carte)} présentée au lecteur (simulée)")
        service.lecteur.simuler_carte(carte)
        executer(service, 0.2)
    else:
        consigne(f"{texte} ({carte_txt(carte)}) — 30 s")
        executer(service, 30, jusqua=lambda: len(service.lectures) > avant)
        executer(service, 0.2)

    lue = len(service.lectures) > avant
    if lue:
        info(f"Carte lue par le RPi : {decrire_carte(service.lecteur.dernier_brut)}")
        info(f"   -> carte {carte_txt(service.lectures[-1])} ({config.FORMAT_CARTE}), "
             f"nom {service.dernier_nom!r}, solde {argent(service.dernier_solde)}")
    else:
        info("Aucune carte lue")
    return lue


def payer_retrait(service, transaction_id: int, carte: int, texte: str = "Passez la puce pour payer"):
    """Demande le retrait, confirme le montant, puis présente une carte."""
    if not service.retrait.demander_retrait(transaction_id):
        info(f"Retrait REFUSÉ : {service.retrait.message}")
        return

    info(f"Retrait demandé, coût affiché : {service.retrait.obtenir_cout_actuel()}")
    service.retrait.confirmer_retrait_et_figer_montant()
    montant = service.transactions.obtenir_transaction(transaction_id)["montant_fige"]
    info(f"Montant figé : {argent(montant)}, délai de paiement {service.retrait.secondes_restantes():.0f} s")
    presenter_carte(service, carte, texte)


def trames_envoyees(service, can_id: int) -> list:
    """Données des trames de cet identifiant envoyées par le RPi."""
    return [donnees for identifiant, donnees in service.envoyees if identifiant == can_id]


def commandes_moteur(service) -> list:
    """Commandes moteur envoyées par le RPi : (moteur, action, cible)."""
    noms = {0x100: "ELEVATION", 0x110: "ROTATION", 0x120: "BRAS"}
    return [(noms[identifiant], donnees[1], donnees[2])
            for identifiant, donnees in service.envoyees if identifiant in noms]


def codes_anomalies(service, tache: str | None = None) -> list:
    """Codes des anomalies actives, d'une tâche ou de toutes."""
    return [anomalie["code"] for anomalie in service.stationnement.anomalies
            if tache is None or anomalie["tache"] == tache]


def afficher_bilan(service, cartes=None):
    """Affiche les transactions, les soldes et les anomalies du service."""
    info("Transactions :")
    tableau(["n°", "place", "état", "carte départ", "montant figé", "carte paiement", "erreur"],
            [[f"{t['id']:06d}", t["place"], t["etat"], t["rfid_initial"], t["montant_fige"],
              t["rfid_paiement"], t["erreur"]] for t in service.transactions.obtenir_transactions()])
    info("Comptes (T02) :")
    noms = service.comptes.obtenir_noms()
    tableau(["carte", "nom", "solde (¢)"],
            [[carte, noms.get(carte, ""), solde] for carte, solde in sorted(service.comptes.obtenir_comptes().items())])
    info("Anomalies actives :")
    tableau(["tâche", "code", "critique", "message"],
            [[a["tache"], a["code"], a["critique"], a["message"]] for a in service.stationnement.anomalies])


# ======================================================================
# ESSAI
# ======================================================================
titre("T12-10 — Sortie occupée",
      f"MATÉRIEL RÉEL : can0 + {sorted(FONCTIONS_REELLES)}" if MATERIEL_REEL else "SIMULATION : aucun matériel")

service = creer_service(fonctions_reelles=FONCTIONS_REELLES if MATERIEL_REEL else None)
numero = garer_vehicule(service, "E1.3", CARTE_A, minutes=9.5)
autre = garer_vehicule(service, "E2.1", CARTE_B)

etape("1. Un véhicule occupe déjà la zone devant la barrière")
if MATERIEL_REEL:
    consigne("Posez un véhicule devant la barrière et LAISSEZ-LE (30 s)")
    executer(service, 30, jusqua=lambda: service.stationnement.presence_rampe is True)
else:
    service.faux_stm32.definir_ir_rampe(True)
    executer(service, 0.2)
verifier("IR devant la barrière : présent", service.stationnement.presence_rampe, True)

etape("2. Paiement : autorisé, mais aucun mouvement")
payer_retrait(service, numero, CARTE_A)
verifier("Paiement validé", service.transactions.est_payee(numero), True)
verifier("État AUTORISE (attend les conditions de sécurité)", service.retrait.obtenir_etat(), "AUTORISE")
verifier("Message à l'écran", service.retrait.message, "Zone de sortie occupée ou inconnue")
executer(service, 5 if MATERIEL_REEL else 10)
verifier("Aucun mouvement tant que la sortie est occupée", commandes_moteur(service), [])
verifier("Transaction PAYEE, pas encore en retrait", service.transactions.obtenir_transaction(numero)["etat"], "PAYEE")

etape("3. Un seul retrait à la fois")
verifier("Deuxième demande de retrait refusée", service.retrait.demander_retrait(autre), False)
info(f"écran : {service.retrait.message!r}")

etape("4. La zone se libère : la séquence démarre toute seule")
if MATERIEL_REEL:
    consigne("Enlevez le véhicule de devant la barrière (30 s)")
else:
    service.faux_stm32.definir_ir_rampe(False)
    info("IR de la rampe -> absent (simulé)")
executer(service, 30, jusqua=lambda: len(commandes_moteur(service)) > 0)
verifier("La séquence démarre", service.retrait.obtenir_etat(), "MOUVEMENT")
verifier("Première commande envoyée", commandes_moteur(service)[0], ("ELEVATION", 1, 1))
verifier("Carte débitée une seule fois", service.comptes.obtenir_solde(CARTE_A), 2250)

afficher_bilan(service)
service.arreter()
terminer()
