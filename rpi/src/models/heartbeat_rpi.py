"""Heartbeat CAN du Raspberry Pi (HEARTBEAT_RPI, 0x040, toutes les 500 ms).

COMMUN, fait « au cas où » : si un coéquipier l'émet déjà, mettre
config.HEARTBEAT_ACTIF à False.
"""

from src import config
from src.hardware import protocole_can as proto
from src.models import stationnement as etats


class HeartbeatRPi:
    """Émet périodiquement le compteur et l'état du RPi."""

    def __init__(self, can, stationnement, retrait, horloge):
        self.can = can
        self.stationnement = stationnement
        self.retrait = retrait
        self.horloge = horloge

        self._compteur = 0
        self._prochain_envoi = 0.0

    def mettre_a_jour(self) -> None:
        """Envoie la trame si la période est écoulée. Ne bloque jamais."""
        if not config.HEARTBEAT_ACTIF:
            return

        maintenant = self.horloge.monotone()

        if maintenant < self._prochain_envoi:
            return

        self._prochain_envoi = maintenant + config.PERIODE_HEARTBEAT_S

        if self.stationnement.etat_service == etats.ARRET_VERROUILLE:
            etat = proto.HEARTBEAT_VERROUILLE
        elif self.retrait.est_confirme():
            etat = proto.HEARTBEAT_OCCUPE
        else:
            etat = proto.HEARTBEAT_PRET

        self.can.send(proto.HEARTBEAT_RPI, [self._compteur, etat])
        self._compteur = (self._compteur + 1) % 256
