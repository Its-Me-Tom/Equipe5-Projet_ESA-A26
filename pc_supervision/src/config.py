"""Configuration de l'application de supervision (PC) — T13."""

# ----------------------------------------------------------------------
# MQTT : doit être identique à rpi/src/config.py
# ----------------------------------------------------------------------
NUMERO_EQUIPE = 5
BROKER_IP = "10.50.86.13"       # "localhost" si Mosquitto roule sur ce PC
BROKER_PORT = 1883
RACINE_MQTT = f"esa/Equipe_{NUMERO_EQUIPE}"
ID_CLIENT_MQTT = f"esa-pc-equipe-{NUMERO_EQUIPE}"

# Une commande sans réponse après ce délai est signalée dans l'interface
DELAI_REPONSE_S = 3.0

# ----------------------------------------------------------------------
# Fenêtre
# ----------------------------------------------------------------------
# True = l'app s'ouvre en vrai plein écran : tout l'écran, sans barre de
# titre ni barre des tâches. F11 bascule plein écran / fenêtre, Échap
# revient en fenêtre. False = fenêtre normale.
PLEIN_ECRAN = True

# ----------------------------------------------------------------------
# Affichage des places : mêmes couleurs que les DEL de la maquette (T07)
# ----------------------------------------------------------------------
COULEURS_PLACES = {
    "LIBRE": "#2e9e3f",          # vert
    "RESERVE": "#2a6fd6",        # bleu
    "OCCUPE": "#d03b3b",         # rouge
    "MAINTENANCE": "#f28c28",    # orange
    "DEFAUT": "#f2d21b",         # jaune (clignotant)
}
COULEUR_INCONNUE = "#9e9e9e"     # avant de recevoir le premier état
PERIODE_CLIGNOTEMENT_MS = 500    # clignotement à 1 Hz

# Couleur de fond de l'état général de la borne
COULEURS_SERVICE = {
    "EN_SERVICE": "#2e9e3f",
    "MISE_HORS_SERVICE": "#f28c28",
    "HORS_SERVICE": "#757575",
    "ARRET_VERROUILLE": "#d03b3b",
}
