"""Accès au bus CAN du Raspberry Pi (python-can) — classe du labo 5."""

import can

from src import config


class CanManager:
    """Ouvre le bus CAN, envoie et reçoit des trames.

    En simulation, le bus est un bus virtuel de python-can : le faux STM32
    (simulation/faux_stm32.py) y est branché lui aussi. Le reste du
    programme ne voit aucune différence avec le vrai bus can0.

    C'est le gestionnaire CAN UNIQUE du Raspberry Pi : les modules des
    coéquipiers doivent l'utiliser au lieu d'ouvrir leur propre bus.
    """

    def __init__(self, simulate: bool | None = None):
        self.simulate = config.SIMULER_CAN if simulate is None else simulate
        self.bus = None
        self.last_error = ""
        self._sequence = 0

    def connect(self) -> bool:
        """Ouvre le bus. Retourne False si l'interface n'est pas disponible."""
        try:
            if self.simulate:
                self.bus = can.Bus(interface="virtual", channel=config.CAN_CANAL_SIMULE)
            else:
                self.bus = can.Bus(interface=config.CAN_INTERFACE, channel=config.CAN_CANAL)

            return True

        except Exception as error:   # can0 absent, interface down, etc.
            self.bus = None
            self.last_error = str(error)
            return False

    def disconnect(self):
        """Ferme le bus."""
        if self.bus is not None:
            self.bus.shutdown()
            self.bus = None

    def is_connected(self) -> bool:
        return self.bus is not None

    def next_sequence(self) -> int:
        """Retourne un numéro de séquence de 0 à 254.

        0xFF est réservé aux états spontanés des STM32.
        """
        self._sequence = (self._sequence + 1) % 255
        return self._sequence

    def send(self, can_id: int, data: list) -> bool:
        """Envoie une trame standard (11 bits). Retourne False si échec."""
        if self.bus is None:
            self.last_error = "Bus CAN non connecté"
            return False

        message = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)

        try:
            self.bus.send(message)
            return True

        except can.CanError as error:
            self.last_error = str(error)
            return False

    def receive(self):
        """Retourne la prochaine trame reçue, ou None s'il n'y en a pas.

        Ne bloque jamais : la boucle du service l'appelle à chaque tour.
        """
        if self.bus is None:
            return None

        return self.bus.recv(timeout=0)
