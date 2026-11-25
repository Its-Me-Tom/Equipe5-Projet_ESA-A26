"""Doublures des tâches des coéquipiers (PAS mes tâches).

Ces classes remplacent le strict minimum de T06 (détecteurs IR, partie
RPi), T03 et T11 (dépôt) pour pouvoir faire fonctionner T02, T04, T07,
T12 et T13 seuls. À l'intégration, chaque coéquipier remplace la doublure
par son vrai module dans controllers/service_rpi.py.
"""

from src import config
from src.hardware import protocole_can as proto
from src.models import stationnement as etats


class RecepteurIRSimule:
    """Doublure de T06 (partie RPi) : décode les trames IR.

    Met à jour le modèle partagé et prévient T12 SEULEMENT quand un état
    change : une resynchronisation ne crée pas de fausse transition.
    """

    def __init__(self, stationnement, signaler_presence):
        self.stationnement = stationnement
        self.signaler_presence = signaler_presence   # fonction(capteur, présent)

        # indice IR (0 à 13) -> nom de la place
        self._noms = {place["indice_ir"]: nom for nom, place in config.PLACES.items()}

    def traiter_trame_can(self, message):
        can_id, donnees = message.arbitration_id, message.data

        if can_id == proto.IR_BAS_CHANGEMENT:
            self._changer_place(donnees[0], bool(donnees[1]))

        elif can_id == proto.IR_BAS_COMPLET and donnees[3] == 1:   # 1 = valide
            masque = donnees[0] | (donnees[1] << 8)

            for indice in range(14):
                self._changer_place(indice, bool(masque & (1 << indice)))

        elif can_id == proto.IR_ENTREE_CHANGEMENT:
            self._changer_rampe(bool(donnees[1]))

        elif can_id == proto.IR_ENTREE_COMPLET and donnees[2] == 1:
            self._changer_rampe(bool(donnees[0]))

    def _changer_place(self, indice: int, present: bool):
        nom = self._noms.get(indice)

        if nom is not None and self.stationnement.presence_places[nom] != present:
            self.stationnement.presence_places[nom] = present
            self.signaler_presence(nom, present)

    def _changer_rampe(self, present: bool):
        if self.stationnement.presence_rampe != present:
            self.stationnement.presence_rampe = present
            self.signaler_presence("RAMPE", present)


class DepotSimule:
    """Doublure de T03 + T11 : crée une transaction déjà rangée.

    Permet d'avoir un véhicule « stationné » pour tester le retrait.
    """

    def __init__(self, stationnement, transactions, horloge, faux_stm32=None):
        self.stationnement = stationnement
        self.transactions = transactions
        self.horloge = horloge
        self.faux_stm32 = faux_stm32      # pour allumer l'IR simulé de la place

    def deposer(self, place: str, identifiant_rfid: int) -> int | None:
        """Simule un dépôt complet. Retourne le numéro de transaction."""
        if not self.stationnement.nouvelles_transactions_permises():
            return None

        if self.stationnement.etats_places.get(place) != etats.PLACE_LIBRE:
            return None

        # T03 : réservation confirmée -> T04 crée la transaction
        transaction_id = self.transactions.creer_transaction(place, identifiant_rfid)

        # T11 : rangement confirmé par l'IR -> la facturation commence
        self.transactions.confirmer_rangement(transaction_id, self.horloge.maintenant())
        self.stationnement.etats_places[place] = etats.PLACE_OCCUPEE

        if self.faux_stm32 is not None:
            self.faux_stm32.definir_ir_place(config.PLACES[place]["indice_ir"], True)

        return transaction_id
