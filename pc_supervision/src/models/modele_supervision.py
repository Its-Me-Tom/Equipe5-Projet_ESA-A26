"""Modèle de l'application de supervision (PC) — T13.

Le PC ne décide de rien : il garde seulement la dernière copie de ce que
le Raspberry Pi a publié et la liste des commandes en attente de réponse.
Aucun PyQt ici : le modèle se teste seul (voir test_pc_*.py).
"""

import json
import time
from datetime import datetime

from src import config
from src.mqtt_topics import MqttTopics

COMMANDES_GENERALES = ("METTRE_HORS_SERVICE", "REMETTRE_EN_SERVICE", "ARRET_IMMEDIAT", "REINITIALISER")
COMMANDES_COMPTES = ("CONSULTER_SOLDE", "AJOUTER_CREDIT")

# Transactions qui « tiennent » encore une place (le client n'est pas reparti)
ETATS_TRANSACTION_ACTIFS = ("CREEE", "EN_STATIONNEMENT", "PAIEMENT_EN_ATTENTE",
                            "PAYEE", "RETRAIT_EN_COURS", "ERREUR")

TAILLE_HISTORIQUE = 500    # nombre d'événements gardés en mémoire

# Nom d'un état de place dans une phrase (« E2.2 réservée »)
ETATS_EN_MOTS = {
    "LIBRE": "libre",
    "RESERVE": "réservée",
    "OCCUPE": "occupée",
    "MAINTENANCE": "en maintenance",
    "DEFAUT": "en défaut",
}


class ModeleSupervision:
    """Dernier état connu du stationnement et suivi des commandes."""

    def __init__(self):
        # Données publiées par le Raspberry Pi
        self.etat_service = "INCONNU"
        self.etat_retrait = ""
        self.message = ""
        self.places = []           # 14 dictionnaires : place, numero, etat, presence
        self.rampe = None          # présence devant la barrière
        self.anomalies = []
        self.transactions = []
        self.statistiques = []     # un dictionnaire par compte
        self.tarif = None          # tarif en cents par minute
        self.comptes = {}          # carte -> solde (réponses sur les comptes)
        self.noms = {}             # carte -> nom du compte (s'il est fourni par le RPi)
        self.rpi_en_ligne = None   # None = inconnu, True / False = annoncé par le RPi

        # Historique des stationnements (construit par le PC en comparant
        # chaque nouvel état reçu avec le précédent)
        self.historique = []             # (heure "HH:MM:SS", texte), du plus ancien au plus récent
        self.nouveaux_evenements = []    # pas encore affichés (voir prendre_nouveaux_evenements)
        self._etats_places_vus = None    # place -> état; None = aucun état reçu
        self._etats_transactions_vus = None   # numéro -> état; None = rien reçu

        # Suivi des commandes
        self.en_attente = {}       # id_commande -> heure d'envoi
        self.derniere_commande = None   # dernière commande envoyée (pour la renvoyer)
        self.derniere_reponse = None    # dernière réponse reçue
        self._compteur = 0

    # ------------------------------------------------------------------
    # Commandes PC -> RPi
    # ------------------------------------------------------------------

    def construire_commande(self, nom: str, **champs) -> dict:
        """Construit une commande avec un id_commande unique."""
        self._compteur += 1

        # L'heure en millisecondes rend l'identifiant unique même après un
        # redémarrage du PC (important pour ne pas bloquer un vrai crédit).
        id_commande = f"PC{config.NUMERO_EQUIPE}-{int(time.time() * 1000)}-{self._compteur}"

        commande = {"id_commande": id_commande, "commande": nom}
        commande.update(champs)

        return commande

    def noter_envoi(self, commande: dict):
        """Note qu'une commande vient d'être envoyée."""
        self.en_attente[commande["id_commande"]] = time.monotonic()
        self.derniere_commande = commande

    @staticmethod
    def topic_de(commande: dict) -> str:
        """Topic sur lequel une commande doit être publiée."""
        if commande["commande"] in COMMANDES_COMPTES:
            return MqttTopics.COMMANDE_COMPTES

        return MqttTopics.COMMANDE

    def commandes_en_retard(self) -> list:
        """id_commande des commandes sans réponse après le délai."""
        maintenant = time.monotonic()

        return [
            id_commande
            for id_commande, envoi in self.en_attente.items()
            if maintenant - envoi > config.DELAI_REPONSE_S
        ]

    # ------------------------------------------------------------------
    # Messages RPi -> PC
    # ------------------------------------------------------------------

    def traiter_message(self, topic: str, payload: str) -> str:
        """Met le modèle à jour. Retourne ce qui a changé :

        "etat", "places", "anomalies", "transactions", "reponse", "connexion_rpi",
        "invalide" (JSON incorrect) ou "inconnu" (topic non prévu).
        """
        try:
            message = json.loads(payload)

            if topic == MqttTopics.CONNEXION_RPI:
                en_ligne = message["en_ligne"]
                if not isinstance(en_ligne, bool):
                    return "invalide"
                self.rpi_en_ligne = en_ligne
                return "connexion_rpi"

            if topic == MqttTopics.ETAT:
                self.etat_service = message["etat_service"]
                self.etat_retrait = message.get("etat_retrait", "")
                self.message = message.get("message", "")
                return "etat"

            if topic == MqttTopics.PLACES:
                places = message["places"]
                etats = {place["place"]: place["etat"] for place in places}   # KeyError : invalide

                self.places = places
                self.rampe = message.get("rampe")
                self._noter_changements_places(etats)
                return "places"

            if topic == MqttTopics.ANOMALIES:
                self.anomalies = message["anomalies"]
                return "anomalies"

            if topic == MqttTopics.TRANSACTIONS:
                transactions = message["transactions"]
                statistiques = message["statistiques"]["comptes"]
                etats = {transaction["id"]: transaction["etat"] for transaction in transactions}

                self.transactions = transactions
                self.statistiques = statistiques
                self.tarif = message.get("tarif_cents_par_minute")

                # Les statistiques donnent le nom de chaque carte
                for compte in statistiques:
                    if compte.get("rfid") and compte.get("nom"):
                        self.noms[compte["rfid"]] = compte["nom"]

                self._noter_changements_transactions(etats)
                return "transactions"

            if topic in (MqttTopics.REPONSE_COMMANDE, MqttTopics.REPONSE_COMPTES):
                self._traiter_reponse(message)
                return "reponse"

        except (ValueError, KeyError, TypeError):
            # JSON incorrect ou champ manquant : le modèle n'est pas modifié
            return "invalide"

        return "inconnu"

    def _traiter_reponse(self, reponse: dict):
        """Associe une réponse à sa commande grâce à id_commande."""
        id_commande = reponse["id_commande"]        # KeyError si absent : invalide

        self.derniere_reponse = reponse
        self.en_attente.pop(id_commande, None)

        # Les réponses sur les comptes contiennent des soldes à jour
        for compte in reponse.get("comptes", []):
            self.comptes[compte["rfid"]] = compte["solde"]

            if compte.get("nom"):
                self.noms[compte["rfid"]] = compte["nom"]

        if "rfid" in reponse and reponse.get("solde") is not None:
            self.comptes[reponse["rfid"]] = reponse["solde"]

            if reponse.get("nom"):
                self.noms[reponse["rfid"]] = reponse["nom"]
    # ------------------------------------------------------------------
    # Qui est sur chaque place
    # ------------------------------------------------------------------

    def decrire_carte(self, carte: str) -> str:
        """« Thomas (0008580808) », ou seulement le numéro si le nom est inconnu."""
        if not carte:
            return "client inconnu"

        nom = self.noms.get(carte)

        if nom and nom != carte:
            return f"{nom} ({carte})"

        return carte

    def nom_court(self, carte: str) -> str:
        """« Thomas », ou le numéro de la carte si le nom est inconnu."""
        return self.noms.get(carte) or carte

    def transaction_de(self, place: str) -> dict | None:
        """Transaction active d'une place (la plus récente), ou None."""
        actives = [
            transaction for transaction in self.transactions
            if transaction.get("place") == place and transaction.get("etat") in ETATS_TRANSACTION_ACTIFS
        ]

        if not actives:
            return None

        return max(actives, key=lambda transaction: transaction.get("id", 0))

    def occupants(self) -> dict:
        """place -> carte du client qui la tient (transaction active), pour chaque place tenue."""
        occupants = {}

        for place in {transaction.get("place") for transaction in self.transactions}:
            transaction = self.transaction_de(place)

            if transaction is not None and transaction.get("rfid_initial"):
                occupants[place] = transaction["rfid_initial"]

        return occupants

    # ------------------------------------------------------------------
    # Historique des stationnements
    # ------------------------------------------------------------------

    def prendre_nouveaux_evenements(self) -> list:
        """Retourne les événements pas encore affichés et vide la liste."""
        evenements, self.nouveaux_evenements = self.nouveaux_evenements, []
        return evenements

    def _ajouter_evenement(self, texte: str):
        evenement = (datetime.now().strftime("%H:%M:%S"), texte)

        self.historique.append(evenement)
        self.nouveaux_evenements.append(evenement)

        if len(self.historique) > TAILLE_HISTORIQUE:
            del self.historique[0]

    def _client_de(self, place: str) -> str:
        """« Thomas (0008580808) » si la place a une transaction active, sinon ""."""
        transaction = self.transaction_de(place)

        if transaction is None or not transaction.get("rfid_initial"):
            return ""

        return self.decrire_carte(transaction["rfid_initial"])

    def _noter_changements_places(self, etats: dict):
        """Compare les états reçus avec les précédents et note chaque changement."""
        if self._etats_places_vus is None:
            # Premier message : un résumé plutôt que 14 lignes
            compte = {}
            for etat in etats.values():
                compte[etat] = compte.get(etat, 0) + 1

            def en_mots(etat, nombre):
                mots = ETATS_EN_MOTS.get(etat, etat.lower())
                # « 13 libres », « 2 occupées », mais « 2 en maintenance »
                return mots + "s" if nombre > 1 and not mots.startswith("en ") else mots

            resume = ", ".join(f"{nombre} {en_mots(etat, nombre)}"
                               for etat, nombre in sorted(compte.items()))
            self._ajouter_evenement(f"État reçu du Raspberry Pi : {resume}")
            self._etats_places_vus = dict(etats)
            return

        for place, etat in etats.items():
            avant = self._etats_places_vus.get(place)

            if avant is None or avant == etat:
                continue

            client = self._client_de(place)

            if etat == "RESERVE":
                texte = f"{place} réservée par {client}" if client else f"{place} réservée"
            elif etat == "OCCUPE":
                texte = f"{place} occupée par le véhicule de {client}" if client else f"{place} occupée"
            elif etat == "LIBRE":
                texte = f"{place} de nouveau libre (était {ETATS_EN_MOTS.get(avant, avant)})"
            elif etat == "MAINTENANCE":
                texte = f"{place} mise en maintenance"
            elif etat == "DEFAUT":
                texte = f"{place} en DÉFAUT (était {ETATS_EN_MOTS.get(avant, avant)})"
            else:
                texte = f"{place} : {avant} -> {etat}"

            self._ajouter_evenement(texte)

        self._etats_places_vus = dict(etats)

    def _noter_changements_transactions(self, etats: dict):
        """Note l'ouverture et chaque changement d'état d'une transaction."""
        if self._etats_transactions_vus is None:
            en_cours = sum(1 for etat in etats.values() if etat in ETATS_TRANSACTION_ACTIFS)

            if en_cours:
                self._ajouter_evenement(f"{en_cours} transaction(s) en cours au démarrage du PC")

            self._etats_transactions_vus = dict(etats)
            return

        for transaction in self.transactions:
            numero = transaction.get("id")
            etat = transaction.get("etat")
            avant = self._etats_transactions_vus.get(numero)

            if avant == etat:
                continue

            texte = self._decrire_transaction(transaction, avant)

            if texte:
                self._ajouter_evenement(texte)

        self._etats_transactions_vus = dict(etats)

    def _decrire_transaction(self, transaction: dict, avant: str | None) -> str:
        """Phrase de l'historique pour une transaction qui vient de changer."""
        numero = f"{transaction.get('id', 0):06d}"
        place = transaction.get("place", "?")
        etat = transaction.get("etat")
        client = self.decrire_carte(transaction.get("rfid_initial", ""))
        montant = transaction.get("montant_fige")
        montant_texte = f"{montant // 100},{montant % 100:02d} $" if isinstance(montant, int) else "montant inconnu"

        if avant is None:
            debut = f"Transaction {numero} ouverte pour {client}, place {place}"

            if etat == "CREEE":
                return debut

            return f"{debut} (état {etat})"

        if etat == "EN_STATIONNEMENT" and avant == "PAIEMENT_EN_ATTENTE":
            return f"{place} : délai de paiement expiré, le véhicule de {client} reste stationné"

        if etat == "EN_STATIONNEMENT":
            return f"Véhicule de {client} rangé en {place} : début de la facturation"

        if etat == "PAIEMENT_EN_ATTENTE":
            return f"{client} demande son véhicule ({place}) : {montant_texte} à payer"

        if etat == "PAYEE":
            payeur = transaction.get("rfid_paiement") or transaction.get("rfid_initial", "")
            return f"Paiement accepté pour {place} : {montant_texte} débités à {self.decrire_carte(payeur)}"

        if etat == "RETRAIT_EN_COURS":
            return f"Retrait du véhicule de {client} en cours ({place})"

        if etat == "TERMINEE":
            return f"{client} est reparti de {place} : transaction {numero} terminée"

        if etat == "ANNULEE":
            return f"Transaction {numero} annulée ({place}, {client})"

        if etat == "ERREUR":
            detail = transaction.get("erreur") or "sans détail"
            return f"Transaction {numero} en ERREUR ({place}, {client}) : {detail}"

        return f"Transaction {numero} ({place}) : {avant} -> {etat}"
