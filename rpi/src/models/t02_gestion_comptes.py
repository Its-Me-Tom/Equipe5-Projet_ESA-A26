"""T02 — Gestion des comptes RFID (« GestionComptes » du contrat).

Règles :
    - montants en cents entiers, strictement positifs;
    - un débit est fait en totalité ou refusé : le solde ne devient jamais
      négatif;
    - chaque opération a un identifiant unique : la répéter ne change rien
      (pas de double crédit ni de double débit).

Une carte inconnue peut recevoir un compte avec creer_compte() : son nom
est alors le numéro de la carte et son solde config.SOLDE_NOUVELLE_CARTE_CENTS.

Les refus sont signalés par des exceptions (voir erreurs.py) : l'appelant
connaît ainsi la cause exacte (carte inconnue, solde insuffisant...).
"""

import threading

from src import config
from src.format_carte import carte_vers_texte
from src.models.erreurs import CarteInconnue, MontantInvalide, OperationRepetee, SoldeInsuffisant
from src.models.t02_fichier_comptes import FichierComptes


def id_operation_debit(transaction_id: int) -> str:
    """Identifiant stable du débit d'une transaction : 123 -> "T000123"."""
    return f"T{transaction_id:06d}"


class GestionComptes:
    """Consultation, crédit et débit des comptes."""

    def __init__(self, fichier: FichierComptes | None = None):
        self.fichier = fichier or FichierComptes()

        # Empêche deux demandes de modifier les fichiers en même temps
        self._verrou = threading.Lock()

    # ------------------------------------------------------------------
    # Consultation
    # ------------------------------------------------------------------

    def obtenir_solde(self, identifiant_rfid: int) -> int | None:
        """Retourne le solde en cents, ou None si la carte est inconnue."""
        with self._verrou:
            comptes = self.fichier.charger_comptes()

        return comptes.get(carte_vers_texte(identifiant_rfid))

    def verifier_solde(self, identifiant_rfid: int, montant_cents: int) -> bool:
        """True si la carte peut payer ce montant à elle seule."""
        solde = self.obtenir_solde(identifiant_rfid)

        return solde is not None and solde >= montant_cents

    def obtenir_comptes(self) -> dict:
        """Retourne tous les comptes : {"0008580808": 2500, ...}."""
        with self._verrou:
            return self.fichier.charger_comptes()

    def obtenir_nom(self, identifiant_rfid: int) -> str | None:
        """Retourne le nom du compte, ou None si la carte est inconnue."""
        with self._verrou:
            noms = self.fichier.charger_noms()

        return noms.get(carte_vers_texte(identifiant_rfid))

    def obtenir_noms(self) -> dict:
        """Retourne tous les noms : {"0008580808": "Thomas", ...}."""
        with self._verrou:
            return self.fichier.charger_noms()

    # ------------------------------------------------------------------
    # Nouveau compte
    # ------------------------------------------------------------------

    def creer_compte(self, identifiant_rfid: int, nom: str | None = None,
                     solde_cents: int | None = None) -> bool:
        """Crée le compte d'une carte inconnue.

        Par défaut : nom = numéro de la carte, solde = config.SOLDE_NOUVELLE_CARTE_CENTS.
        Retourne False (rien ne change) si la carte a déjà un compte.
        Lève MontantInvalide ou ErreurFichier.
        """
        carte = carte_vers_texte(identifiant_rfid)
        solde = config.SOLDE_NOUVELLE_CARTE_CENTS if solde_cents is None else solde_cents

        if type(solde) is not int or solde < 0:
            raise MontantInvalide("Le solde de départ doit être un entier positif ou nul en cents")

        with self._verrou:
            fiches = self.fichier.charger_fiches()

            if carte in fiches:
                return False

            comptes = {c: fiche["solde"] for c, fiche in fiches.items()}
            noms = {c: fiche["nom"] for c, fiche in fiches.items()}
            comptes[carte] = solde
            noms[carte] = (nom or "").strip() or carte

            self.fichier.sauvegarder_comptes(comptes, noms)

        return True

    def obtenir_operations(self) -> list:
        """Retourne tout le journal des opérations."""
        with self._verrou:
            return self.fichier.charger_operations()

    # ------------------------------------------------------------------
    # Crédit et débit
    # ------------------------------------------------------------------

    def ajouter_credit(self, identifiant_rfid: int, montant_cents: int, operation_id: str) -> bool:
        """Ajoute du crédit. Retourne True quand l'opération est enregistrée.

        Lève MontantInvalide, CarteInconnue, OperationRepetee ou ErreurFichier.
        """
        return self._appliquer(identifiant_rfid, montant_cents, operation_id, "credit")

    def debiter(self, identifiant_rfid: int, montant_cents: int, transaction_id: int) -> bool:
        """Débite la totalité du montant. Retourne True si c'est enregistré.

        Lève MontantInvalide, CarteInconnue, OperationRepetee,
        SoldeInsuffisant ou ErreurFichier.
        """
        operation_id = id_operation_debit(transaction_id)

        return self._appliquer(identifiant_rfid, montant_cents, operation_id, "debit")

    def _appliquer(self, identifiant_rfid, montant_cents, operation_id, sorte) -> bool:
        """Applique un crédit ou un débit (code commun aux deux)."""
        # bool est refusé : True compterait pour 1 cent
        if type(montant_cents) is not int or montant_cents <= 0:
            raise MontantInvalide("Le montant doit être un entier positif en cents")

        carte = carte_vers_texte(identifiant_rfid)

        with self._verrou:
            comptes = self.fichier.charger_comptes()

            if carte not in comptes:
                raise CarteInconnue(f"Carte {carte} inconnue")

            if self.fichier.operation_existe(operation_id):
                raise OperationRepetee(f"Opération {operation_id} déjà traitée")

            if sorte == "debit" and comptes[carte] < montant_cents:
                raise SoldeInsuffisant(
                    f"Solde {comptes[carte]} ¢ insuffisant pour {montant_cents} ¢"
                )

            # 1) Le journal d'abord : si le programme s'arrête juste après,
            #    l'opération ne pourra pas être appliquée une deuxième fois.
            self.fichier.enregistrer_operation({
                "operation_id": operation_id,
                "rfid": carte,
                "type": sorte,
                "montant": montant_cents,
            })

            # 2) Ensuite le solde.
            if sorte == "credit":
                comptes[carte] += montant_cents
            else:
                comptes[carte] -= montant_cents

            self.fichier.sauvegarder_comptes(comptes)

        return True

    # ------------------------------------------------------------------
    # Contrôle au démarrage
    # ------------------------------------------------------------------

    def verifier_coherence(self) -> list:
        """Retourne la liste des incohérences trouvées dans les deux CSV.

        Limite connue : les deux fichiers ne forment pas une transaction
        atomique. Une coupure entre l'écriture du journal et celle du solde
        ne peut pas être détectée avec ces seuls fichiers.
        """
        problemes = []

        with self._verrou:
            comptes = self.fichier.charger_comptes()
            operations = self.fichier.charger_operations()

        deja_vues = set()

        for operation in operations:
            operation_id = operation["operation_id"]

            if operation_id in deja_vues:
                problemes.append(f"Opération {operation_id} en double")

            deja_vues.add(operation_id)

            if operation["rfid"] not in comptes:
                problemes.append(f"Opération {operation_id} : carte inconnue")

            if operation["type"] not in ("credit", "debit"):
                problemes.append(f"Opération {operation_id} : type invalide")

            if operation["montant"] <= 0:
                problemes.append(f"Opération {operation_id} : montant invalide")

        return problemes
