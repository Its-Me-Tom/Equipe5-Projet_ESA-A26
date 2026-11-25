"""Client MQTT du Raspberry Pi (encapsule Paho MQTT) — classe du labo 4.

Aucune autre classe n'utilise paho.mqtt.client directement.

Différence avec le labo 4 : ce n'est pas un QObject. La logique du RPi
roule dans un thread sans boucle d'événements Qt, où un signal Qt ne serait
jamais livré. Les fonctions on_message, on_connected et on_disconnected
sont donc de simples fonctions, appelées par le thread réseau de Paho :
elles doivent seulement noter l'événement (voir
SupervisionMQTT.recevoir_message_mqtt), jamais faire un long traitement.
"""

import json
import time

from src import config
from src.simulation.faux_broker import BROKER


class MqttClient:
    """Connexion au broker, abonnements et publications."""

    def __init__(self, client_id: str | None = None, simulate: bool | None = None):
        self.simulate = config.SIMULER_MQTT if simulate is None else simulate
        self.client_id = client_id or config.ID_CLIENT_MQTT
        self.topics = []              # topics auxquels on est abonné
        self.last_error = ""
        self._connected = False

        # Fonctions de rappel à fournir par l'utilisateur de la classe
        self.on_message = None        # on_message(topic, payload)
        self.on_connected = None      # on_connected()
        self.on_disconnected = None   # on_disconnected()

        self._client = None

        # Topic de présence (voir definir_presence). None = pas de présence.
        self.topic_presence = None
        self.testament = None         # message publié par le broker si on disparaît

        if not self.simulate:
            import paho.mqtt.client as mqtt   # requis seulement en mode réel

            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.client_id,
            )
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            # Reconnexion automatique après une coupure Wi-Fi
            self._client.reconnect_delay_set(min_delay=1, max_delay=10)

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------

    def definir_presence(self, topic: str):
        """Annonce sur 'topic' si ce client est en ligne. À appeler AVANT connect_to_broker().

        - À la connexion : publie {"en_ligne": true} (conservé, retain).
        - Fermeture normale : publie {"en_ligne": false}.
        - Disparition brutale (Pi débranché, Wi-Fi coupé) : le broker publie
          lui-même le « testament » {"en_ligne": false} après environ
          1,5 x keepalive (≈ 22 s), parce que le client ne répond plus.
        """
        self.topic_presence = topic
        self.testament = json.dumps({"en_ligne": False, "client": self.client_id})

        if not self.simulate:
            self._client.will_set(topic, self.testament, qos=1, retain=True)

    def _publier_presence(self, en_ligne: bool):
        if self.topic_presence is None:
            return

        message = json.dumps({"en_ligne": en_ligne, "client": self.client_id, "horodatage": time.time()})

        if self.simulate:
            BROKER.publier(self.topic_presence, message, True)
            return

        envoi = self._client.publish(self.topic_presence, message, qos=1, retain=True)

        if not en_ligne:
            # Fermeture : attendre que « hors ligne » soit parti AVANT de couper.
            # Sinon Paho le renverrait après la prochaine connexion, APRÈS
            # « en ligne », et le PC verrait le RPi hors ligne alors qu'il est
            # connecté (défaut trouvé par test_t13_09 avec un vrai broker).
            try:
                envoi.wait_for_publish(timeout=1.0)
            except (RuntimeError, ValueError):
                pass

    def connect_to_broker(self):
        """Lance la connexion. Ne bloque pas si le broker est injoignable."""
        if self.simulate:
            BROKER.brancher(self)
            self._set_connected(True)
            self._publier_presence(True)

            for topic in self.topics:
                BROKER.abonner(self, topic)

            return

        try:
            # connect_async + loop_start : Paho se connecte en arrière-plan
            # et réessaie tout seul. La borne continue de fonctionner.
            self._client.connect_async(config.BROKER_IP, config.BROKER_PORT, keepalive=15)
            self._client.loop_start()

        except Exception as error:
            self.last_error = str(error)

    def disconnect_from_broker(self):
        """Ferme la connexion (sert aussi à simuler une perte de Wi-Fi)."""
        if self._connected:
            self._publier_presence(False)     # fermeture normale : on l'annonce

        if self.simulate:
            BROKER.debrancher(self)
            self._set_connected(False)
            return

        self._client.disconnect()
        self._client.loop_stop()
        self._set_connected(False)

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Abonnement et publication
    # ------------------------------------------------------------------

    def subscribe(self, topic: str):
        """S'abonne à un topic (refait automatiquement à la reconnexion)."""
        if topic not in self.topics:
            self.topics.append(topic)

        if not self._connected:
            return

        if self.simulate:
            BROKER.abonner(self, topic)
        else:
            self._client.subscribe(topic, qos=1)

    def publish(self, topic: str, payload: str, retain: bool = False) -> bool:
        """Publie un message. Retourne False si le client est déconnecté."""
        if not self._connected:
            return False

        if self.simulate:
            BROKER.publier(topic, payload, retain)
        else:
            self._client.publish(topic, payload, qos=1, retain=retain)

        return True

    def deliver(self, topic: str, payload: str):
        """Appelée par le faux broker quand un message arrive."""
        if self.on_message is not None:
            self.on_message(topic, payload)

    # ------------------------------------------------------------------
    # Rappels de Paho (exécutés dans le thread réseau)
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.last_error = f"Connexion MQTT refusée : {reason_code}"
            return

        # Les abonnements sont perdus à la déconnexion : on les refait.
        for topic in self.topics:
            client.subscribe(topic, qos=1)

        self._set_connected(True)
        self._publier_presence(True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._set_connected(False)

    def _on_message(self, client, userdata, message):
        payload = message.payload.decode("utf-8", errors="replace")
        self.deliver(message.topic, payload)

    def _set_connected(self, connected: bool):
        changed = connected != self._connected
        self._connected = connected

        if not changed:
            return

        if connected and self.on_connected is not None:
            self.on_connected()

        if not connected and self.on_disconnected is not None:
            self.on_disconnected()
