"""Client MQTT de l'application PC (encapsule Paho MQTT) — classe du labo 4.

Aucune classe graphique n'utilise paho.mqtt.client directement.

Les rappels de Paho sont exécutés dans son thread réseau : cette classe
ne touche donc jamais à un widget. Elle émet des signaux Qt, que Qt livre
dans le thread de l'interface.
"""

import paho.mqtt.client as mqtt
from PyQt6.QtCore import QObject, pyqtSignal

from src.config import BROKER_IP, BROKER_PORT, ID_CLIENT_MQTT


class MqttClient(QObject):
    """Gère la communication MQTT de l'application PC."""

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    message_received = pyqtSignal(str, str)      # topic, payload
    connection_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.topics = []          # abonnements, refaits à chaque connexion
        self.is_connected = False

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=ID_CLIENT_MQTT)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Reconnexion automatique après une coupure du réseau
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)

    def connect_to_broker(self) -> None:
        """Lance la connexion en arrière-plan (ne bloque pas l'interface)."""
        try:
            self.client.connect_async(BROKER_IP, BROKER_PORT, keepalive=15)
            self.client.loop_start()
        except Exception as error:
            self.connection_failed.emit(str(error))

    def disconnect_from_broker(self) -> None:
        """Ferme la connexion MQTT."""
        self.client.disconnect()
        self.client.loop_stop()

    def subscribe(self, topic: str) -> None:
        """S'abonne à un topic (immédiatement si déjà connecté)."""
        if topic not in self.topics:
            self.topics.append(topic)

        if self.is_connected:
            self.client.subscribe(topic, qos=1)

    def publish(self, topic: str, payload: str) -> bool:
        """Publie un message. Retourne False si le client est déconnecté."""
        if not self.is_connected:
            return False

        self.client.publish(topic, payload, qos=1)
        return True

    # ------------------------------------------------------------------
    # Rappels de Paho (thread réseau) : seulement des signaux
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.connection_failed.emit(f"Connexion refusée : {reason_code}")
            return

        for topic in self.topics:
            client.subscribe(topic, qos=1)

        self.is_connected = True
        self.connected.emit()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.is_connected = False
        self.disconnected.emit()

    def _on_message(self, client, userdata, message):
        payload = message.payload.decode("utf-8", errors="replace")
        self.message_received.emit(message.topic, payload)
