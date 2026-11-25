"""Faux broker MQTT en mémoire (simulation seulement).

Remplace Mosquitto quand on simule MQTT : les clients d'un même programme
s'échangent leurs messages sans réseau. Il garde aussi les messages
« retain », comme un vrai broker.
"""


class FauxBroker:
    """Distribue les messages entre les clients simulés."""

    def __init__(self):
        self.clients = []
        self.conserves = {}    # topic -> dernier message conservé (retain)

    def brancher(self, client):
        if client not in self.clients:
            self.clients.append(client)

    def debrancher(self, client):
        if client in self.clients:
            self.clients.remove(client)

    def perte_brutale(self, client):
        """Simule un client qui disparaît sans prévenir : le broker publie son testament."""
        self.debrancher(client)
        client._set_connected(False)

        if getattr(client, "testament", None) and client.topic_presence:
            self.publier(client.topic_presence, client.testament, True)

    def abonner(self, client, topic: str):
        """Un nouvel abonné reçoit tout de suite le message conservé."""
        if client in self.clients and topic in self.conserves:
            client.deliver(topic, self.conserves[topic])

    def publier(self, topic: str, payload: str, retain: bool):
        if retain:
            self.conserves[topic] = payload

        for client in list(self.clients):
            if topic in client.topics:
                client.deliver(topic, payload)

    def vider(self):
        """Oublie tout (utilisé entre deux tests)."""
        self.clients.clear()
        self.conserves.clear()


# Un seul faux broker pour tout le programme
BROKER = FauxBroker()
