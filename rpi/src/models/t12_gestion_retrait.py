"""T12 — Orchestration du retrait (« GestionRetrait » du contrat).

Machine à états NON BLOQUANTE : aucune méthode n'attend. mettre_a_jour()
est appelée à chaque tour de la boucle du service et fait avancer la
séquence.

    INACTIF -> DEMANDE -> PAIEMENT -> AUTORISE -> MOUVEMENT ...
        ... ATTENTE_PLACE_LIBRE ... ATTENTE_ARRIVEE_SORTIE
        ... ATTENTE_DEPART -> (clôture) -> retour -> INACTIF

    DEFAUT : anomalie. La séquence s'arrête et ne reprend JAMAIS seule.

L'ordre des étapes mécaniques est dans config.SEQUENCE_RETRAIT.
Chaque commande CAN suit la règle du protocole : réponse acceptée/refusée
en 500 ms, puis résultat final distinct (terminée, interrompue ou défaut).
"""

from src import config
from src.hardware import protocole_can as proto
from src.horloge import Horloge
from src.models import stationnement as etats_stationnement
from src.models import t04_gestion_transactions as etats_transaction

# États de la machine (publiés dans le topic « etat »)
INACTIF = "INACTIF"
DEMANDE = "DEMANDE"                                # coût affiché, attend la confirmation
PAIEMENT = "PAIEMENT"                              # fenêtre de 60 s
AUTORISE = "AUTORISE"                              # payé, attend les conditions de sécurité
MOUVEMENT = "MOUVEMENT"                            # une commande CAN est en cours
ATTENTE_PLACE_LIBRE = "ATTENTE_PLACE_LIBRE"        # IR de la place -> absent
ATTENTE_ARRIVEE_SORTIE = "ATTENTE_ARRIVEE_SORTIE"  # IR de la rampe -> présent
ATTENTE_DEPART = "ATTENTE_DEPART"                  # IR de la rampe -> absent
DEFAUT = "DEFAUT"

RAMPE = "RAMPE"    # nom du détecteur IR devant la barrière

# États où le retrait est « confirmé » (paiement complet validé) : une mise
# hors service doit alors laisser la séquence se terminer.
ETATS_CONFIRMES = (AUTORISE, MOUVEMENT, ATTENTE_PLACE_LIBRE, ATTENTE_ARRIVEE_SORTIE, ATTENTE_DEPART)

# Commande d'arrêt de chaque moteur : (ID, cible de DB2 du protocole)
ARRETS = {
    proto.ELEVATION_CMD: 0,
    proto.ROTATION_CMD: 0xFF,
    proto.BRAS_CMD: 0,
}


class GestionRetrait:
    """Coordonne le paiement puis la récupération mécanique d'un véhicule."""

    def __init__(self, can, stationnement, facturation, horloge: Horloge | None = None, journal=None):
        self.can = can                      # CanManager
        self.stationnement = stationnement  # modèle partagé
        self.facturation = facturation      # GestionTransactions (T04)
        self.horloge = horloge or Horloge()
        self.journal = journal or (lambda texte: None)

        self.etat = INACTIF
        self.transaction_id = None
        self.place = None
        self.message = ""          # dernier message à afficher à l'écran

        self.ir = {}               # dernière présence IR connue par capteur

        self._etape = 0            # position dans config.SEQUENCE_RETRAIT
        self._commande = None      # commande CAN en attente de réponse
        self._echeance = None      # échéance de l'attente IR en cours

    # ------------------------------------------------------------------
    # Demande et paiement
    # ------------------------------------------------------------------

    def demander_retrait(self, transaction_id: int) -> bool:
        """Identifie la transaction et sa place (billet scanné ou numéro saisi)."""
        if self.etat != INACTIF:
            return self._refuser("Un retrait est déjà en cours")

        if not self.stationnement.nouvelles_transactions_permises():
            return self._refuser("Borne hors service")

        transaction = self.facturation.obtenir_transaction(transaction_id)

        if transaction is None:
            return self._refuser("Numéro de transaction inconnu")

        if transaction["etat"] != etats_transaction.EN_STATIONNEMENT:
            return self._refuser("Ce véhicule ne peut pas être retiré maintenant")

        self.transaction_id = transaction_id
        self.place = transaction["place"]
        self.etat = DEMANDE
        self.message = "Confirmez le retrait"
        return True

    def obtenir_cout_actuel(self) -> dict:
        """Durée et coût actuels (pas encore figés), pour l'affichage."""
        maintenant = self.horloge.maintenant()

        return {
            "duree_min": self.facturation.calculer_duree_min(self.transaction_id, maintenant),
            "montant_cents": self.facturation.calculer_montant(self.transaction_id, maintenant),
        }

    def confirmer_retrait_et_figer_montant(self) -> bool:
        """L'utilisateur confirme : montant figé, fenêtre de 60 s lancée."""
        if self.etat != DEMANDE:
            return self._refuser("Aucune demande de retrait à confirmer")

        resultat = self.facturation.demander_retrait(self.transaction_id)

        if not resultat["accepte"]:
            self._revenir_inactif(f"Demande refusée : {resultat['erreur']}")
            return False

        self.etat = PAIEMENT
        self.message = "Présentez une carte RFID pour payer"
        return True

    def presenter_carte(self, identifiant_rfid: int) -> bool:
        """Une carte est présentée pendant la fenêtre de paiement.

        Solde insuffisant : rien n'est débité, on reste en PAIEMENT et une
        autre carte peut être essayée. Les soldes ne sont jamais additionnés.
        """
        if self.etat != PAIEMENT:
            return False

        if not self.facturation.confirmer_paiement(self.transaction_id, identifiant_rfid):
            self.message = f"Paiement refusé : {self.facturation.derniere_erreur}"
            return False

        self.etat = AUTORISE
        self.message = "Paiement accepté"
        self.autoriser_apres_paiement()
        return True

    def annuler(self) -> bool:
        """Annule un retrait non confirmé (avant le paiement complet)."""
        if self.etat not in (DEMANDE, PAIEMENT):
            return False

        if self.etat == PAIEMENT:
            self.facturation.annuler_demande_retrait(self.transaction_id)

        self._revenir_inactif("Demande de retrait annulée")
        return True

    def autoriser_apres_paiement(self) -> bool:
        """Démarre la séquence mécanique si toutes les conditions sont réunies.

        Tant qu'une condition manque, on reste en AUTORISE (aucun mouvement)
        et mettre_a_jour() réessaie.
        """
        if self.etat != AUTORISE:
            return False

        if not self.facturation.est_payee(self.transaction_id):
            self.message = "Paiement non confirmé"
            return False

        if self.stationnement.etat_service == etats_stationnement.ARRET_VERROUILLE:
            self.message = "Arrêt verrouillé"
            return False

        if self.ir.get(RAMPE) is not False:
            # Présent ou inconnu : la zone de sortie n'est pas déclarée libre
            self.message = "Zone de sortie occupée ou inconnue"
            return False

        if self.stationnement.barriere_ouverte or self.stationnement.mecanique_occupee:
            self.message = "Barrière ouverte ou ascenseur occupé"
            return False

        self.facturation.commencer_retrait(self.transaction_id)
        self.stationnement.mecanique_occupee = True
        self.message = "Récupération du véhicule en cours"
        self.journal(f"T12 : début du retrait {self.transaction_id:06d} ({self.place})")

        self._etape = 0
        self._lancer_etape()
        return True

    # ------------------------------------------------------------------
    # Boucle non bloquante
    # ------------------------------------------------------------------

    def mettre_a_jour(self) -> None:
        """Fait avancer la machine à états. Ne bloque jamais."""
        maintenant = self.horloge.monotone()

        if self.etat == PAIEMENT:
            # T04 annule la demande quand les 60 s sont écoulées
            self.facturation.mettre_a_jour()
            transaction = self.facturation.obtenir_transaction(self.transaction_id)

            if transaction["etat"] == etats_transaction.EN_STATIONNEMENT:
                self._revenir_inactif("Délai de paiement expiré : véhicule conservé")

        elif self.etat == AUTORISE:
            self.autoriser_apres_paiement()

        elif self.etat == MOUVEMENT:
            if self._commande is not None and maintenant >= self._commande["echeance"]:
                if self._commande["acceptee"]:
                    self._defaut("MOUVEMENT_NON_TERMINE", "Mouvement non terminé à temps")
                else:
                    self._defaut("CAN_SANS_REPONSE", "Aucune réponse CAN à la commande")

        elif self.etat == ATTENTE_PLACE_LIBRE:
            if self.ir.get(self.place) is False:
                self._etape_suivante()
            elif maintenant >= self._echeance:
                self._defaut("PLACE_NON_LIBEREE", "Le véhicule est encore détecté dans la place",
                             place=self.place)

        elif self.etat == ATTENTE_ARRIVEE_SORTIE:
            if self.ir.get(RAMPE) is True:
                self.message = "Retirez votre véhicule devant la barrière"
                self._etape_suivante()
            elif maintenant >= self._echeance:
                self._defaut("SORTIE_NON_DETECTEE", "Véhicule non détecté à la sortie")

        elif self.etat == ATTENTE_DEPART:
            # L'absence prouve le départ : la présence a été confirmée à
            # l'étape précédente. Aucun délai : on attend l'utilisateur.
            if self.ir.get(RAMPE) is False:
                self._etape_suivante()

    # ------------------------------------------------------------------
    # Événements reçus
    # ------------------------------------------------------------------

    def traiter_reponse_can(self, message) -> None:
        """Traite une trame *_ETAT qui répond à la commande en cours."""
        commande = self._commande

        if commande is None or message.arbitration_id != commande["reponse_id"]:
            return

        donnees = message.data

        if len(donnees) < 2 or donnees[0] != commande["sequence"]:
            return      # réponse à une autre commande ou état spontané

        resultat = donnees[1]

        if resultat == proto.RESULTAT_ACCEPTE:
            # Acceptée ne veut pas dire terminée : on attend le résultat final
            commande["acceptee"] = True
            commande["echeance"] = self.horloge.monotone() + config.DELAI_MOUVEMENT_S

        elif resultat == proto.RESULTAT_TERMINE:
            self._commande = None
            self._etape_suivante()

        elif resultat == proto.RESULTAT_REFUSE:
            self._defaut("COMMANDE_REFUSEE", f"Commande refusée ({commande['etape']})")

        else:
            self._defaut("MOUVEMENT_EN_DEFAUT", f"Mouvement interrompu ou en défaut ({commande['etape']})")

    def traiter_presence_ir(self, capteur: str, present: bool) -> None:
        """T06 signale un détecteur IR : nom de place ("E1.3") ou "RAMPE"."""
        self.ir[capteur] = present

    # ------------------------------------------------------------------
    # Arrêt et réinitialisation
    # ------------------------------------------------------------------

    def arreter(self) -> None:
        """Arrêt immédiat : la séquence s'arrête, sans reprise automatique."""
        if self.etat in (DEMANDE, PAIEMENT):
            self.annuler()

        elif self.etat in ETATS_CONFIRMES:
            self._defaut("ARRET_IMMEDIAT", "Séquence de retrait interrompue")

    def reinitialiser(self) -> None:
        """Après une réinitialisation : retour à INACTIF, rien ne redémarre."""
        if self.etat == DEFAUT:
            self.stationnement.mecanique_occupee = False
            self._revenir_inactif("Retrait réinitialisé")

    def obtenir_etat(self) -> str:
        return self.etat

    def est_confirme(self) -> bool:
        """True si un retrait payé est en cours (doit pouvoir se terminer)."""
        return self.etat in ETATS_CONFIRMES

    def secondes_restantes(self) -> float:
        """Secondes restantes pour payer (0 hors de la fenêtre de paiement)."""
        if self.etat != PAIEMENT:
            return 0.0

        return self.facturation.secondes_restantes(self.transaction_id)

    # ------------------------------------------------------------------
    # Séquence mécanique
    # ------------------------------------------------------------------

    def _lancer_etape(self):
        """Lance l'étape courante de config.SEQUENCE_RETRAIT."""
        if self._etape >= len(config.SEQUENCE_RETRAIT):
            self.stationnement.mecanique_occupee = False
            self.journal("T12 : retrait terminé")
            self._revenir_inactif("Retrait terminé")
            return

        etape = config.SEQUENCE_RETRAIT[self._etape]
        maintenant = self.horloge.monotone()

        if etape == "ATTENDRE_PLACE_LIBRE":
            self.etat = ATTENTE_PLACE_LIBRE
            self._echeance = maintenant + config.DELAI_PLACE_LIBRE_S

        elif etape == "ATTENDRE_ARRIVEE_SORTIE":
            self.etat = ATTENTE_ARRIVEE_SORTIE
            self._echeance = maintenant + config.DELAI_RAMPE_S

        elif etape == "ATTENDRE_DEPART":
            self.etat = ATTENTE_DEPART

        elif etape == "CLORE_TRANSACTION":
            self._clore_transaction()
            self._etape_suivante()

        else:
            self._envoyer_commande(etape)

    def _etape_suivante(self):
        self._etape += 1
        self._lancer_etape()

    def _envoyer_commande(self, etape: str):
        """Envoie la commande CAN d'une étape moteur."""
        place = config.PLACES[self.place]

        # étape -> (ID de la commande, ID de la réponse, action, cible)
        commandes = {
            "ELEVATION_VERS_PLACE": (proto.ELEVATION_CMD, proto.ELEVATION_ETAT,
                                     proto.ELEVATION_DEPLACER, place["niveau"]),
            "ELEVATION_VERS_SORTIE": (proto.ELEVATION_CMD, proto.ELEVATION_ETAT,
                                      proto.ELEVATION_DEPLACER, config.NIVEAU_SORTIE),
            "ELEVATION_VERS_DEPART": (proto.ELEVATION_CMD, proto.ELEVATION_ETAT,
                                      proto.ELEVATION_DEPLACER, config.NIVEAU_DEPART),
            "SOULEVER": (proto.ELEVATION_CMD, proto.ELEVATION_ETAT, proto.ELEVATION_SOULEVER, 0),
            "ABAISSER": (proto.ELEVATION_CMD, proto.ELEVATION_ETAT, proto.ELEVATION_ABAISSER, 0),
            "ROTATION_VERS_PLACE": (proto.ROTATION_CMD, proto.ROTATION_ETAT,
                                    proto.ROTATION_DEPLACER, place["angle"]),
            "ROTATION_VERS_SORTIE": (proto.ROTATION_CMD, proto.ROTATION_ETAT,
                                     proto.ROTATION_DEPLACER, config.ANGLE_SORTIE),
            "DEPLOYER_BRAS": (proto.BRAS_CMD, proto.BRAS_ETAT, proto.BRAS_DEPLOYER, 0),
            "RETRACTER_BRAS": (proto.BRAS_CMD, proto.BRAS_ETAT, proto.BRAS_RETRACTER, 0),
        }

        if etape not in commandes:
            self._defaut("ETAPE_INCONNUE", f"Étape inconnue dans la séquence : {etape}")
            return

        commande_id, reponse_id, action, cible = commandes[etape]
        sequence = self.can.next_sequence()

        self.etat = MOUVEMENT
        self._commande = {
            "etape": etape,
            "commande_id": commande_id,
            "reponse_id": reponse_id,
            "sequence": sequence,
            "acceptee": False,
            "echeance": self.horloge.monotone() + config.DELAI_ACCEPTATION_S,
        }
        self.journal(f"T12 : étape {etape}")

        if not self.can.send(commande_id, [sequence, action, cible]):
            self._defaut("CAN_ENVOI_IMPOSSIBLE", "Envoi CAN impossible")

    def _clore_transaction(self):
        """Départ confirmé : T04 clôture et la place redevient libre.

        T07 voit le changement d'état et remet la DEL au vert.
        """
        self.facturation.confirmer_sortie(self.transaction_id)

        if self.stationnement.etats_places[self.place] != etats_stationnement.PLACE_DEFAUT:
            self.stationnement.etats_places[self.place] = etats_stationnement.PLACE_LIBRE

        self.message = "Merci et bonne route"
        self.journal(f"T12 : transaction {self.transaction_id:06d} clôturée")

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _refuser(self, message: str) -> bool:
        self.message = message
        return False

    def _revenir_inactif(self, message: str):
        self.etat = INACTIF
        self.transaction_id = None
        self.place = None
        self.message = message
        self._commande = None
        self._echeance = None

    def _defaut(self, code: str, message: str, place=None):
        """Anomalie : arrêter le moteur, tout garder, attendre une intervention."""
        if self._commande is not None:
            # Action 0 = arrêt, avec la cible prévue par le protocole
            commande_id = self._commande["commande_id"]
            self.can.send(commande_id, [self.can.next_sequence(), 0, ARRETS[commande_id]])
            self._commande = None

        self.etat = DEFAUT
        self.message = message
        self.journal(f"T12 : DÉFAUT {code} — {message}")

        # La transaction garde ses informations de paiement (état ERREUR).
        # mecanique_occupee reste à True : aucun autre mouvement n'est permis.
        self.facturation.suspendre(self.transaction_id, code)

        if place is not None:
            self.stationnement.etats_places[place] = etats_stationnement.PLACE_DEFAUT

        self.stationnement.ajouter_anomalie("T12", code, message, place=place, critique=True)
