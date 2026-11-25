"""T04 — Transactions et facturation (« GestionTransactions » du contrat).

T04 est propriétaire des transactions, des tarifs et des montants. Il ne
touche jamais à comptes.csv : il demande le débit à T02 (GestionComptes).

États d'une transaction :

    CREEE ──confirmer_rangement──> EN_STATIONNEMENT ──demander_retrait──┐
                                        ^                               v
                                        └──── délai expiré ──── PAIEMENT_EN_ATTENTE
                                                                        │ confirmer_paiement
    TERMINEE <──confirmer_sortie── RETRAIT_EN_COURS <──commencer_retrait── PAYEE

    ANNULEE : transaction annulée avant le dépôt.
    ERREUR  : anomalie; les informations de paiement sont conservées.

Les méthodes qui retournent un booléen mettent la cause du refus dans
self.derniere_erreur (ex. "SOLDE_INSUFFISANT").
"""

import csv
import math
import os
from pathlib import Path

from src import config
from src.format_carte import carte_vers_texte
from src.horloge import Horloge
from src.models.erreurs import (
    ErreurEsa,
    ErreurFichier,
    HorodatageInvalide,
    OperationRepetee,
    PlaceInvalide,
    TransactionInexistante,
)
from src.models.t02_gestion_comptes import id_operation_debit

# États (valeurs écrites dans transactions.csv et publiées par MQTT)
CREEE = "CREEE"
EN_STATIONNEMENT = "EN_STATIONNEMENT"
PAIEMENT_EN_ATTENTE = "PAIEMENT_EN_ATTENTE"
PAYEE = "PAYEE"
RETRAIT_EN_COURS = "RETRAIT_EN_COURS"
TERMINEE = "TERMINEE"
ANNULEE = "ANNULEE"
ERREUR = "ERREUR"

COLONNES = [
    "id",                  # numéro de transaction (1 à 999999)
    "place",               # ex. "E1.3"
    "rfid_initial",        # carte présentée au dépôt
    "etat",
    "debut_facturation",   # heure de confirmation du rangement (secondes)
    "montant_fige",        # montant figé en cents (demande de retrait)
    "rfid_paiement",       # carte qui a payé
    "fin",                 # heure de clôture (secondes)
    "erreur",              # description si etat = ERREUR
]


class GestionTransactions:
    """Crée, suit et sauvegarde les transactions de stationnement."""

    def __init__(self, comptes, fichier_transactions=None, horloge: Horloge | None = None):
        self.comptes = comptes        # GestionComptes (T02)
        self.fichier = Path(fichier_transactions or config.FICHIER_TRANSACTIONS)
        self.horloge = horloge or Horloge()

        self.tarif = config.TARIF_CENTS_PAR_MINUTE
        self.delai_paiement = config.DELAI_PAIEMENT_S

        self.derniere_erreur = ""     # cause du dernier refus
        self.notes_reprise = []       # corrections faites au redémarrage

        self._transactions = {}       # numéro -> dictionnaire
        self._echeances = {}          # numéro -> échéance du paiement

        self._charger()
        self._reprendre_apres_redemarrage()

    # ------------------------------------------------------------------
    # Création et début de facturation
    # ------------------------------------------------------------------

    def creer_transaction(self, place: str, identifiant_rfid: int) -> int:
        """Crée une transaction et retourne son numéro unique.

        Lève PlaceInvalide si la place n'existe pas.
        """
        if place not in config.PLACES:
            raise PlaceInvalide(f"Place {place!r} invalide")

        # Numéros séquentiels : le plus grand déjà utilisé + 1.
        # Un numéro n'est donc jamais réutilisé.
        numero = max(self._transactions, default=0) + 1

        if numero > config.NUMERO_TRANSACTION_MAX:
            raise ErreurEsa("Plus aucun numéro de transaction disponible")

        self._transactions[numero] = {
            "id": numero,
            "place": place,
            "rfid_initial": carte_vers_texte(identifiant_rfid),
            "etat": CREEE,
            "debut_facturation": None,
            "montant_fige": None,
            "rfid_paiement": "",
            "fin": None,
            "erreur": "",
        }
        self._sauvegarder()

        return numero

    def annuler_transaction(self, transaction_id: int) -> bool:
        """Annule une transaction avant le dépôt (réservation annulée)."""
        transaction = self._exiger_etat(transaction_id, [CREEE])

        if transaction is None:
            return False

        transaction["etat"] = ANNULEE
        self._sauvegarder()
        return True

    def confirmer_rangement(self, transaction_id: int, horodatage: float) -> bool:
        """T11 confirme le rangement : la facturation commence (une seule fois)."""
        transaction = self._exiger_etat(transaction_id, [CREEE])

        if transaction is None:
            return False

        # Absent, pas un nombre, négatif, ou dans le futur : incohérent
        if (not isinstance(horodatage, (int, float)) or isinstance(horodatage, bool)
                or horodatage <= 0 or horodatage > self.horloge.maintenant() + 5):
            return self._refuser("HORODATAGE_INVALIDE")

        transaction["debut_facturation"] = float(horodatage)
        transaction["etat"] = EN_STATIONNEMENT
        self._sauvegarder()
        return True

    # ------------------------------------------------------------------
    # Consultation et calcul
    # ------------------------------------------------------------------

    def obtenir_transaction(self, transaction_id: int) -> dict | None:
        """Retourne une copie de la transaction, ou None si elle n'existe pas."""
        transaction = self._transactions.get(transaction_id)

        return dict(transaction) if transaction is not None else None

    def obtenir_transactions(self) -> list:
        """Retourne une copie de toutes les transactions."""
        return [dict(transaction) for transaction in self._transactions.values()]

    def calculer_duree_min(self, transaction_id: int, maintenant: float) -> int:
        """Nombre de minutes commencées depuis le rangement."""
        transaction = self._transactions.get(transaction_id)

        if transaction is None:
            raise TransactionInexistante(f"Transaction {transaction_id} inexistante")

        debut = transaction["debut_facturation"]

        if debut is None:
            return 0          # pas encore rangé : rien n'est facturé

        if maintenant < debut:
            raise HorodatageInvalide("L'heure actuelle précède le début")

        # Toute minute entamée est facturée : 61 s -> 2 minutes
        return math.ceil((maintenant - debut) / 60)

    def calculer_montant(self, transaction_id: int, maintenant: float) -> int:
        """Montant dû en cents à l'instant « maintenant »."""
        return self.calculer_duree_min(transaction_id, maintenant) * self.tarif

    def est_payee(self, transaction_id: int) -> bool:
        """True si le paiement complet a été confirmé."""
        transaction = self._transactions.get(transaction_id)

        return transaction is not None and transaction["etat"] in (PAYEE, RETRAIT_EN_COURS)

    def secondes_restantes(self, transaction_id: int) -> float:
        """Secondes restantes dans la fenêtre de paiement (0 si aucune)."""
        echeance = self._echeances.get(transaction_id)

        if echeance is None:
            return 0.0

        return max(0.0, echeance - self.horloge.monotone())

    # ------------------------------------------------------------------
    # Demande de retrait et paiement
    # ------------------------------------------------------------------

    def demander_retrait(self, transaction_id: int) -> dict:
        """Fige le montant dû et démarre la fenêtre de paiement.

        Retourne un dictionnaire :
            accepte, erreur, montant_cents, duree_min, secondes_restantes
        Répéter la demande pendant la fenêtre ne change rien (idempotent).
        """
        resultat = {
            "accepte": False,
            "erreur": "",
            "montant_cents": 0,
            "duree_min": 0,
            "secondes_restantes": 0.0,
        }

        transaction = self._exiger_etat(transaction_id, [EN_STATIONNEMENT, PAIEMENT_EN_ATTENTE])

        if transaction is None:
            resultat["erreur"] = self.derniere_erreur
            return resultat

        maintenant = self.horloge.maintenant()

        if transaction["etat"] == EN_STATIONNEMENT:
            try:
                montant = self.calculer_montant(transaction_id, maintenant)
            except HorodatageInvalide as erreur:
                resultat["erreur"] = self.derniere_erreur = erreur.code
                return resultat

            transaction["montant_fige"] = montant
            transaction["etat"] = PAIEMENT_EN_ATTENTE
            self._echeances[transaction_id] = self.horloge.monotone() + self.delai_paiement
            self._sauvegarder()

        resultat["accepte"] = True
        resultat["montant_cents"] = transaction["montant_fige"]
        resultat["duree_min"] = transaction["montant_fige"] // self.tarif
        resultat["secondes_restantes"] = self.secondes_restantes(transaction_id)
        return resultat

    def annuler_demande_retrait(self, transaction_id: int) -> bool:
        """Annule la demande : le véhicule reste stationné.

        L'heure de début n'est pas touchée : la facturation continue depuis
        le dépôt, sans minute gratuite.
        """
        transaction = self._exiger_etat(transaction_id, [PAIEMENT_EN_ATTENTE])

        if transaction is None:
            return False

        transaction["montant_fige"] = None
        transaction["etat"] = EN_STATIONNEMENT
        self._echeances.pop(transaction_id, None)
        self._sauvegarder()
        return True

    def confirmer_paiement(self, transaction_id: int, rfid: int) -> bool:
        """Demande à T02 le débit complet sur UNE carte.

        Retourne True si la transaction est payée. En cas de refus (solde
        insuffisant, carte inconnue), rien n'est débité et une autre carte
        peut être essayée pendant la fenêtre de paiement.
        """
        transaction = self._transactions.get(transaction_id)

        if transaction is None:
            return self._refuser("TRANSACTION_INEXISTANTE")

        # Déjà payée : on ne débite surtout pas une deuxième fois.
        if transaction["etat"] in (PAYEE, RETRAIT_EN_COURS, TERMINEE):
            return True

        if transaction["etat"] != PAIEMENT_EN_ATTENTE:
            return self._refuser("ETAT_INCOMPATIBLE")

        if self.secondes_restantes(transaction_id) <= 0:
            self.annuler_demande_retrait(transaction_id)
            return self._refuser("DELAI_EXPIRE")

        montant = transaction["montant_fige"]

        try:
            if montant > 0:
                self.comptes.debiter(rfid, montant, transaction_id)

        except OperationRepetee:
            # Le débit de cette transaction est déjà dans le journal de T02
            # (ex. panne juste après le débit) : elle est donc payée.
            pass

        except ErreurEsa as erreur:
            # Solde insuffisant, carte inconnue, erreur de fichier...
            return self._refuser(erreur.code)

        transaction["etat"] = PAYEE
        transaction["rfid_paiement"] = carte_vers_texte(rfid)
        self._echeances.pop(transaction_id, None)
        self._sauvegarder()
        return True

    # ------------------------------------------------------------------
    # Retrait physique et clôture
    # ------------------------------------------------------------------

    def commencer_retrait(self, transaction_id: int) -> bool:
        """T12 commence la récupération mécanique (seulement si payée)."""
        transaction = self._exiger_etat(transaction_id, [PAYEE])

        if transaction is None:
            return False

        transaction["etat"] = RETRAIT_EN_COURS
        self._sauvegarder()
        return True

    def confirmer_sortie(self, transaction_id: int) -> bool:
        """T12 confirme le retrait manuel du véhicule : clôture (une seule fois)."""
        transaction = self._exiger_etat(transaction_id, [RETRAIT_EN_COURS])

        if transaction is None:
            return False

        transaction["etat"] = TERMINEE
        transaction["fin"] = self.horloge.maintenant()
        self._sauvegarder()
        return True

    def suspendre(self, transaction_id: int, raison: str) -> bool:
        """Met la transaction en ERREUR sans effacer le paiement."""
        transaction = self._transactions.get(transaction_id)

        if transaction is None:
            return self._refuser("TRANSACTION_INEXISTANTE")

        if transaction["etat"] in (TERMINEE, ANNULEE, ERREUR):
            return self._refuser("ETAT_INCOMPATIBLE")

        transaction["erreur"] = f"{raison} (état précédent : {transaction['etat']})"
        transaction["etat"] = ERREUR
        self._echeances.pop(transaction_id, None)
        self._sauvegarder()
        return True

    # ------------------------------------------------------------------
    # Délai de paiement (non bloquant)
    # ------------------------------------------------------------------

    def mettre_a_jour(self) -> list:
        """Annule les demandes dont le délai est expiré.

        À appeler régulièrement. Retourne les numéros des demandes annulées.
        """
        expirees = []

        for transaction_id in list(self._echeances):
            if self.secondes_restantes(transaction_id) <= 0:
                self.annuler_demande_retrait(transaction_id)
                expirees.append(transaction_id)

        return expirees

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _refuser(self, code: str) -> bool:
        self.derniere_erreur = code
        return False

    def _exiger_etat(self, transaction_id: int, permis: list):
        """Retourne la transaction si elle existe et est dans un état permis."""
        transaction = self._transactions.get(transaction_id)

        if transaction is None:
            self._refuser("TRANSACTION_INEXISTANTE")
            return None

        if transaction["etat"] not in permis:
            self._refuser("ETAT_INCOMPATIBLE")
            return None

        return transaction

    # ------------------------------------------------------------------
    # Fichier transactions.csv
    # ------------------------------------------------------------------

    def _sauvegarder(self):
        """Sauvegarde tout (fichier temporaire, puis os.replace)."""
        fichier_temporaire = self.fichier.with_suffix(".tmp")

        try:
            with open(fichier_temporaire, "w", newline="", encoding="utf-8") as fichier:
                ecrivain = csv.DictWriter(fichier, fieldnames=COLONNES)
                ecrivain.writeheader()

                for transaction in self._transactions.values():
                    ligne = dict(transaction)

                    for colonne in ("debut_facturation", "montant_fige", "fin"):
                        if ligne[colonne] is None:
                            ligne[colonne] = ""      # vide = pas de valeur

                    ecrivain.writerow(ligne)

            os.replace(fichier_temporaire, self.fichier)

        except OSError as erreur:
            raise ErreurFichier(f"Écriture de transactions.csv impossible : {erreur}")

    def _charger(self):
        """Recharge les transactions. Un fichier absent = aucune transaction."""
        if not self.fichier.exists():
            return

        try:
            with open(self.fichier, "r", newline="", encoding="utf-8") as fichier:
                lecteur = csv.DictReader(fichier)

                if lecteur.fieldnames != COLONNES:
                    raise ErreurFichier("transactions.csv : colonnes incorrectes")

                for ligne in lecteur:
                    transaction = {
                        "id": int(ligne["id"]),
                        "place": ligne["place"],
                        "rfid_initial": ligne["rfid_initial"],
                        "etat": ligne["etat"],
                        "debut_facturation": self._nombre(ligne["debut_facturation"], float),
                        "montant_fige": self._nombre(ligne["montant_fige"], int),
                        "rfid_paiement": ligne["rfid_paiement"],
                        "fin": self._nombre(ligne["fin"], float),
                        "erreur": ligne["erreur"],
                    }
                    self._transactions[transaction["id"]] = transaction

        except (OSError, ValueError, TypeError) as erreur:
            raise ErreurFichier(f"transactions.csv illisible : {erreur}")

    @staticmethod
    def _nombre(texte: str, convertir):
        """Convertit une case du CSV; une case vide donne None."""
        return convertir(texte) if texte != "" else None

    def _reprendre_apres_redemarrage(self):
        """Réconcilie les demandes de paiement interrompues par un arrêt.

        La fenêtre de 60 s ne survit pas à un redémarrage. Pour chaque
        transaction restée en PAIEMENT_EN_ATTENTE :
            - si son débit est dans operations.csv de T02 -> PAYEE;
            - sinon -> EN_STATIONNEMENT (la demande est annulée).
        Une transaction PAYEE reste toujours PAYEE.
        """
        en_attente = [
            transaction
            for transaction in self._transactions.values()
            if transaction["etat"] == PAIEMENT_EN_ATTENTE
        ]

        if not en_attente:
            return

        try:
            operations = self.comptes.obtenir_operations()
        except ErreurFichier:
            self.notes_reprise.append(
                "Journal de T02 illisible : paiements en attente non vérifiés"
            )
            return

        debits = {operation["operation_id"]: operation["rfid"] for operation in operations}

        for transaction in en_attente:
            operation_id = id_operation_debit(transaction["id"])

            if operation_id in debits:
                transaction["etat"] = PAYEE
                transaction["rfid_paiement"] = debits[operation_id]
                note = "débit trouvé dans le journal -> PAYEE"
            else:
                transaction["etat"] = EN_STATIONNEMENT
                transaction["montant_fige"] = None
                note = "demande de retrait annulée -> EN_STATIONNEMENT"

            self.notes_reprise.append(f"Transaction {transaction['id']:06d} : {note}")

        self._sauvegarder()
