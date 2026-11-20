"""Topics MQTT du projet ESA (interface T13, section 12.5).

Même fichier que du côté du Raspberry Pi : les noms sont sensibles à la
casse et doivent être identiques des deux côtés.
"""

from src.config import RACINE_MQTT


class MqttTopics:
    """Regroupe tous les topics pour ne pas les écrire à plusieurs endroits."""

    # RPi -> PC
    ETAT = f"{RACINE_MQTT}/etat"                            # état général
    PLACES = f"{RACINE_MQTT}/places"                        # 14 emplacements
    ANOMALIES = f"{RACINE_MQTT}/anomalies"                  # anomalies et défauts
    TRANSACTIONS = f"{RACINE_MQTT}/transactions"            # transactions + stats
    REPONSE_COMMANDE = f"{RACINE_MQTT}/commande/reponse"    # réponse aux commandes
    REPONSE_COMPTES = f"{RACINE_MQTT}/comptes/reponse"      # réponse sur les comptes
    CONNEXION_RPI = f"{RACINE_MQTT}/rpi/connexion"          # RPi en ligne ou non (retain + testament)

    # PC -> RPi
    COMMANDE = f"{RACINE_MQTT}/commande"                    # commandes générales
    COMMANDE_COMPTES = f"{RACINE_MQTT}/comptes/commande"    # solde et crédit

    # Topics auxquels le PC s'abonne
    DU_RPI = [ETAT, PLACES, ANOMALIES, TRANSACTIONS, REPONSE_COMMANDE, REPONSE_COMPTES, CONNEXION_RPI]
