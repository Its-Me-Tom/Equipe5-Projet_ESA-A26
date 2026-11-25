"""Identifiants et valeurs des trames CAN (protocole ESA v1.6).

Les noms sont ceux du document du protocole pour s'y retrouver facilement.
Seules les trames utilisées par T07, T12 et T13 (et par le simulateur)
sont ici. Les coéquipiers peuvent ajouter les leurs à la suite.
"""

# ----------------------------------------------------------------------
# Arrêts, défauts et surveillance
# ----------------------------------------------------------------------
ARRET_HAUT = 0x001          # DLC 3 : motif, source, détail
ARRET_BAS = 0x002
ARRET_BORNE = 0x003
ARRET_RPI = 0x004

DEFAUT_HAUT = 0x010         # DLC 4 : source, code, gravité, détail
DEFAUT_BAS = 0x011
DEFAUT_BORNE = 0x012

HEARTBEAT_RPI = 0x040       # DLC 2 : compteur, état
HEARTBEAT_HAUT = 0x041
HEARTBEAT_BAS = 0x042
HEARTBEAT_BORNE = 0x043

REARMEMENT_CMD = 0x050      # DLC 2 : séquence, action (0x01)
REARMEMENT_HAUT = 0x051     # DLC 3 : séquence, résultat, motif du refus
REARMEMENT_BAS = 0x052
REARMEMENT_BORNE = 0x053

SYNCHRO_CMD = 0x080         # DLC 1 : 0x01 capteurs, 0x02 moteurs, 0x03 tous

# État d'un contrôleur dans son heartbeat (DB1)
HEARTBEAT_INITIALISATION = 0
HEARTBEAT_PRET = 1
HEARTBEAT_OCCUPE = 2
HEARTBEAT_VERROUILLE = 3
HEARTBEAT_DEFAUT = 4

# ----------------------------------------------------------------------
# Mouvements de l'ascenseur (RPi -> STM32 Haut, puis réponse) — T12
# ----------------------------------------------------------------------
ELEVATION_CMD = 0x100       # DLC 3 : séquence, action, niveau cible
ROTATION_CMD = 0x110        # DLC 3 : séquence, action, angle cible
BRAS_CMD = 0x120            # DLC 3 : séquence, action, réservé

ELEVATION_ETAT = 0x200      # DLC 5 : séquence, résultat, étage, défaut, conf.
ROTATION_ETAT = 0x210       # DLC 4 : séquence, résultat, angle, défaut
BRAS_ETAT = 0x220           # DLC 4 : séquence, résultat, position, défaut

# Actions de ELEVATION_CMD (DB1)
ELEVATION_ARRET = 0
ELEVATION_DEPLACER = 1
ELEVATION_SOULEVER = 3      # petit déplacement vers le haut (prise)
ELEVATION_ABAISSER = 4      # petit déplacement vers le bas (dépôt)

# Actions de ROTATION_CMD (DB1)
ROTATION_ARRET = 0
ROTATION_DEPLACER = 1

# Actions de BRAS_CMD (DB1)
BRAS_ARRET = 0
BRAS_DEPLOYER = 1
BRAS_RETRACTER = 2

# Résultat commun (DB1 des trames *_ETAT)
RESULTAT_REFUSE = 0
RESULTAT_ACCEPTE = 1
RESULTAT_TERMINE = 2
RESULTAT_INTERROMPU = 3
RESULTAT_DEFAUT = 4

# ----------------------------------------------------------------------
# Détecteurs infrarouges (T06, lus par T12)
# ----------------------------------------------------------------------
IR_BAS_CHANGEMENT = 0x300       # Bas  — DLC 3 : indice 0-13, état, compteur
IR_BAS_COMPLET = 0x301          # Bas  — DLC 4 : masque 0-7, masque 8-13, compteur, validité
IR_LECTURE_CMD = 0x302          # RPi  — DLC 1 : cible
IR_ENTREE_CHANGEMENT = 0x310    # Haut — DLC 3 : indice 0, état, compteur
IR_ENTREE_COMPLET = 0x311       # Haut — DLC 3 : état, compteur, validité

# ----------------------------------------------------------------------
# DEL des places et éclairage — T07
# ----------------------------------------------------------------------
ECLAIRAGE_CMD = 0x130           # RPi -> Bas/Haut/Borne, DLC 5 : séq., niveau, R, V, B
DEL_PLACE_CMD = 0x340           # RPi -> Bas/Haut, DLC 6 : séq., place, R, V, B, mode

DEL_BAS_ETAT = 0x341            # Bas  — DLC 3 : séquence, place, résultat
DEL_HAUT_ETAT = 0x342           # Haut — DLC 3 : séquence, place, résultat
ECLAIRAGE_BAS_ETAT = 0x350      # Bas  — DLC 3 : séquence, niveau, résultat
ECLAIRAGE_HAUT_ETAT = 0x351     # Haut
ECLAIRAGE_BORNE_ETAT = 0x352    # Borne

# Résultat des accusés de T07 (DB2)
ACCUSE_REFUSE = 0
ACCUSE_APPLIQUE = 1
