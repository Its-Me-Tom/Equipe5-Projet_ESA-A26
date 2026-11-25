"""Modèle partagé du stationnement (objet « stationnement » des contrats).

COMMUN À TOUTE L'ÉQUIPE : T03, T06, T07, T11, T12 et T13 le lisent ou le
modifient. Version minimale en attendant le code commun de l'équipe.

Il garde séparément, comme le demande l'énoncé :
    - l'état LOGIQUE de chaque place (libre, réservée, occupée...);
    - la présence PHYSIQUE mesurée par les détecteurs IR.
"""

from src import config

# États logiques d'une place (T07 les traduit en couleurs de DEL)
PLACE_LIBRE = "LIBRE"                # DEL verte
PLACE_RESERVEE = "RESERVE"           # DEL bleue
PLACE_OCCUPEE = "OCCUPE"             # DEL rouge
PLACE_MAINTENANCE = "MAINTENANCE"    # DEL orange
PLACE_DEFAUT = "DEFAUT"              # DEL jaune clignotante

# États de service de la borne (interface T13, section 12.2)
EN_SERVICE = "EN_SERVICE"
MISE_HORS_SERVICE = "MISE_HORS_SERVICE"    # la transaction confirmée se termine
HORS_SERVICE = "HORS_SERVICE"
ARRET_VERROUILLE = "ARRET_VERROUILLE"      # intervention requise


class Stationnement:
    """États des 14 places, des détecteurs IR et de la borne."""

    def __init__(self, horloge):
        self.horloge = horloge

        self.etats_places = {nom: PLACE_LIBRE for nom in config.PLACES}

        # Présence IR : True, False, ou None si inconnue / non fiable
        self.presence_places = {nom: None for nom in config.PLACES}
        self.presence_rampe = None

        self.etat_service = config.ETAT_SERVICE_INITIAL

        self.mecanique_occupee = False   # un seul mouvement mécanique à la fois
        self.barriere_ouverte = False    # barrière d'entrée (pilotée par T03)

        self.anomalies = []              # anomalies actives
        self._prochain_id_anomalie = 1

    def nouvelles_transactions_permises(self) -> bool:
        """Les nouvelles transactions ne sont permises qu'EN_SERVICE."""
        return self.etat_service == EN_SERVICE

    def ajouter_anomalie(self, tache: str, code: str, message: str,
                         place=None, critique=True) -> dict:
        """Enregistre une anomalie. T13 la publie vers le PC.

        Une anomalie critique verrouille la borne (ARRET_VERROUILLE).
        tache : "T07", "T12", "T13"... (sert à filtrer et à afficher).
        """
        anomalie = {
            "id": self._prochain_id_anomalie,
            "tache": tache,
            "code": code,
            "message": message,
            "place": place,
            "critique": critique,
            "horodatage": self.horloge.maintenant(),
        }
        self._prochain_id_anomalie += 1
        self.anomalies.append(anomalie)

        return anomalie

    def reconstruire_places(self, transactions: list):
        """Recalcule l'état logique des places à partir des transactions.

        Utilisé au démarrage et après une réinitialisation.
        Les places en maintenance ne sont pas touchées.
        """
        etats_ouverts = {
            "CREEE": PLACE_RESERVEE,
            "EN_STATIONNEMENT": PLACE_OCCUPEE,
            "PAIEMENT_EN_ATTENTE": PLACE_OCCUPEE,
            "PAYEE": PLACE_OCCUPEE,
            "RETRAIT_EN_COURS": PLACE_OCCUPEE,
            "ERREUR": PLACE_DEFAUT,
        }

        for nom, etat in self.etats_places.items():
            if etat != PLACE_MAINTENANCE:
                self.etats_places[nom] = PLACE_LIBRE

        for transaction in transactions:
            etat = etats_ouverts.get(transaction["etat"])
            place = transaction["place"]

            if etat is not None and self.etats_places.get(place) != PLACE_MAINTENANCE:
                self.etats_places[place] = etat
