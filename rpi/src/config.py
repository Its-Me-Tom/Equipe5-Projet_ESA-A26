"""Configuration générale du Raspberry Pi (tâches T02, T04, T07, T12 et T13).

Tout ce qui peut changer d'un banc à l'autre est ici. Les autres fichiers
ne contiennent aucune valeur « magique » : ils lisent ce fichier.

Les tests (test_*.py) ne lisent PAS les trois SIMULER_... ci-dessous :
chacun a son propre interrupteur MATERIEL_REEL en haut du fichier.
"""

from pathlib import Path


# ----------------------------------------------------------------------
# Application (main.py) : True = faux matériel, False = vrai matériel
# ----------------------------------------------------------------------
# Chaque interface se règle séparément. Exemple pour essayer seulement le
# vrai lecteur RFID : SIMULER_RFID = False et les deux autres à True.
SIMULER_RFID = True     # False = vrai lecteur ID-12LA sur l'UART
SIMULER_CAN = True      # False = vrai bus can0 (HAT MCP2515)
SIMULER_MQTT = True     # False = vrai broker Mosquitto


# ----------------------------------------------------------------------
# MQTT (T13)
# ----------------------------------------------------------------------
NUMERO_EQUIPE = 5
BROKER_IP = "10.50.86.13"
BROKER_PORT = 1883
RACINE_MQTT = f"esa/Equipe_{NUMERO_EQUIPE}"          # préfixe imposé
ID_CLIENT_MQTT = f"esa-rpi-equipe-{NUMERO_EQUIPE}"

PERIODE_PUBLICATION_ETAT_S = 5.0     # « etat » est republié même sans changement
PERIODE_PUBLICATION_DONNEES_S = 1.0  # vérification des transactions/statistiques


# ----------------------------------------------------------------------
# Lecteur RFID ID-12LA (T02)
# ----------------------------------------------------------------------
# UART du PMOD type 3 du PCB-10 : GPIO14 (TX) / GPIO15 (RX) du Pi.
# Sortie D0 du PCB-07 branchée sur RX (broche 3 du PMOD).
PORT_RFID = "/dev/ttyAMA0"
VITESSE_RFID = 9600
DELAI_REPETITION_RFID_S = 3.0    # la même carte est ignorée pendant ce délai

# Numéro de carte utilisé partout (comptes.csv, MQTT, affichage) :
#   "DECIMAL" : numéro imprimé sur la puce, 10 chiffres     ex. "0008580808"
#               (= les 4 derniers octets de l'ID brut, en décimal)
#   "BRUT"    : ID brut envoyé par le lecteur, 10 hexa     ex. "110082EEC8"
# ATTENTION : data/comptes.csv doit être écrit dans le MÊME format.
# Les deux écritures d'une puce s'affichent avec : python3 rfid_simple.py
FORMAT_CARTE = "DECIMAL"

# Carte inconnue lue au lecteur : True = un compte est créé tout de suite,
# avec le numéro de la carte comme nom et ce solde de départ.
AJOUTER_CARTES_INCONNUES = True
SOLDE_NOUVELLE_CARTE_CENTS = 1000    # X $ de départ, en cents (1000 = 10,00 $)


# ----------------------------------------------------------------------
# Fichiers de données (T02 et T04)
# ----------------------------------------------------------------------
DOSSIER_DONNEES = Path(__file__).resolve().parent.parent / "data"
FICHIER_COMPTES = DOSSIER_DONNEES / "comptes.csv"            # propriétaire : T02
FICHIER_OPERATIONS = DOSSIER_DONNEES / "operations.csv"      # propriétaire : T02
FICHIER_TRANSACTIONS = DOSSIER_DONNEES / "transactions.csv"  # propriétaire : T04


# ----------------------------------------------------------------------
# Transactions et facturation (T04)
# ----------------------------------------------------------------------
TARIF_CENTS_PAR_MINUTE = 25      # tarif, en cents par minute commencée
DELAI_PAIEMENT_S = 60.0          # fenêtre de paiement
NUMERO_TRANSACTION_MAX = 999999  # numéro à six chiffres


# ----------------------------------------------------------------------
# Bus CAN
# ----------------------------------------------------------------------
CAN_INTERFACE = "socketcan"
CAN_CANAL = "can0"               # 500 kbit/s, réglé avec « ip link »
CAN_CANAL_SIMULE = "esa_sim"     # nom du bus virtuel en simulation

DELAI_ACCEPTATION_S = 0.5        # réponse acceptée/refusée (protocole v1.6)
DELAI_MOUVEMENT_S = 30.0         # fin d'un mouvement
DELAI_PLACE_LIBRE_S = 5.0        # l'IR de la place doit devenir absent
DELAI_RAMPE_S = 15.0             # arrivée du véhicule devant la barrière

# Heartbeat du RPi (0x040). Mettre False si un coéquipier l'émet déjà.
HEARTBEAT_ACTIF = True
PERIODE_HEARTBEAT_S = 0.5

# Contenu de la trame ARRET_RPI (0x004)
ARRET_MOTIF = 0x01               # DB0 : 0x01 = arrêt logiciel
ARRET_SOURCE = 6                 # DB1 : 6 = RPi
ARRET_DETAIL = 0                 # DB2 : détail

# Réarmement (REINITIALISER) : STM32 qui doivent accepter, et délai
REARMEMENT_CARTES_REQUISES = ["HAUT", "BAS", "BORNE"]
DELAI_REARMEMENT_S = 2.0


# ----------------------------------------------------------------------
# Places de stationnement
# ----------------------------------------------------------------------
# numero    : numéro global 1 à 14 des trames CAN (DEL, impression)
# niveau    : niveau de l'ascenseur (1 ou 2)
# angle     : position angulaire (1 à 7)
# indice_ir : indice du détecteur IR (0 à 13) des trames 0x300 / 0x301
#
# Le protocole dit de ne pas inventer la correspondance des IR : celle-ci
# est une hypothèse (indice = numéro - 1). Pour corriger une place après
# le câblage : PLACES["E1.3"]["indice_ir"] = 5
PLACES = {}

for _niveau in (1, 2):
    for _angle in range(1, 8):
        _numero = (_niveau - 1) * 7 + _angle

        PLACES[f"E{_niveau}.{_angle}"] = {
            "numero": _numero,
            "niveau": _niveau,
            "angle": _angle,
            "indice_ir": _numero - 1,
        }

NIVEAU_DEPART = 0      # position initiale de l'ascenseur
NIVEAU_SORTIE = 1      # niveau de la rampe de sortie
ANGLE_SORTIE = 0       # orientation de la rampe de sortie


# ----------------------------------------------------------------------
# Séquence mécanique du retrait (T12)
# ----------------------------------------------------------------------
# Les étapes sont exécutées dans l'ordre de la liste. L'ordre du transport
# vers la sortie n'est pas encore validé sur la maquette : pour le changer,
# il suffit de déplacer les lignes.
SEQUENCE_RETRAIT = [
    # Accès à la place
    "ELEVATION_VERS_PLACE",
    "ROTATION_VERS_PLACE",
    # Prise du véhicule
    "DEPLOYER_BRAS",
    "SOULEVER",
    "RETRACTER_BRAS",
    "ATTENDRE_PLACE_LIBRE",       # l'IR de la place doit devenir absent
    # Transport vers la sortie (ordre à valider)
    "ROTATION_VERS_SORTIE",
    "ELEVATION_VERS_SORTIE",
    # Restitution sur la rampe
    "DEPLOYER_BRAS",
    "ABAISSER",
    "RETRACTER_BRAS",
    "ATTENDRE_ARRIVEE_SORTIE",    # IR devant la barrière : présent
    "ATTENDRE_DEPART",            # IR devant la barrière : absent (retrait manuel)
    "CLORE_TRANSACTION",          # T04 clôture, la place redevient libre
    # Retour à la position initiale
    "ELEVATION_VERS_DEPART",
]


# ----------------------------------------------------------------------
# DEL des places et éclairage (T07)
# ----------------------------------------------------------------------
# État logique -> (rouge, vert, bleu, mode). Mode 0 = fixe, 1 = clignotant 1 Hz
COULEURS_DEL = {
    "LIBRE": (0, 255, 0, 0),           # vert
    "RESERVE": (0, 0, 255, 0),         # bleu
    "OCCUPE": (255, 0, 0, 0),          # rouge
    "MAINTENANCE": (255, 165, 0, 0),   # orange
    "DEFAUT": (255, 255, 0, 1),        # jaune clignotant
}

# Intensité du blanc envoyée au démarrage, par niveau (0 = éteint, 255 = max)
INTENSITE_ECLAIRAGE = {0: 128, 1: 128, 2: 128}

DELAI_ACCUSE_S = 0.5             # accusé de réception d'une commande T07
ESSAIS_ENVOI_T07 = 2             # 1 envoi + 1 retransmission, puis anomalie
DELAI_PERTE_HEARTBEAT_S = 1.5    # 3 heartbeats manqués = STM32 perdu


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------
ETAT_SERVICE_INITIAL = "EN_SERVICE"    # état de la borne au démarrage
PERIODE_BOUCLE_S = 0.05                # période de la boucle du service
PERIODE_AFFICHAGE_S = 0.2              # rafraîchissement de l'interface

# Durée d'un mouvement du faux STM32 (simulation seulement)
DUREE_MOUVEMENT_SIMULE_S = 1.0
