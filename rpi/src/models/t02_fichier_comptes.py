"""T02 — Fichiers CSV des comptes (« FichierComptes » du contrat).

    comptes.csv      rfid,nom,solde                   (un compte par ligne)
    operations.csv   operation_id,rfid,type,montant   (journal des opérations)

Seule cette classe lit et écrit ces deux fichiers. Les montants sont des
entiers en cents. Les identifiants de carte restent du texte dans les CSV,
dans le format de config.FORMAT_CARTE (ex. "0008580808" en DECIMAL).

L'ancien format « rfid,solde » (sans nom) est encore accepté : le nom
devient alors le numéro de la carte. La sauvegarde écrit toujours le
nouveau format.
"""

import csv
import os
from pathlib import Path

from src import config
from src.format_carte import carte_vers_texte, texte_vers_carte
from src.models.erreurs import ErreurFichier

COLONNES_COMPTES = ["rfid", "nom", "solde"]
ANCIENNES_COLONNES_COMPTES = ["rfid", "solde"]        # sans nom : encore accepté
COLONNES_OPERATIONS = ["operation_id", "rfid", "type", "montant"]


class FichierComptes:
    """Lecture et écriture de comptes.csv et operations.csv."""

    def __init__(self, fichier_comptes=None, fichier_operations=None):
        self.fichier_comptes = Path(fichier_comptes or config.FICHIER_COMPTES)
        self.fichier_operations = Path(fichier_operations or config.FICHIER_OPERATIONS)

    # ------------------------------------------------------------------
    # comptes.csv
    # ------------------------------------------------------------------

    def charger_comptes(self) -> dict:
        """Retourne les comptes : {"0008580808": 2500, ...} (solde en cents)."""
        return {carte: fiche["solde"] for carte, fiche in self.charger_fiches().items()}

    def charger_noms(self) -> dict:
        """Retourne les noms : {"0008580808": "Thomas", ...}."""
        return {carte: fiche["nom"] for carte, fiche in self.charger_fiches().items()}

    def charger_fiches(self) -> dict:
        """Retourne {"0008580808": {"nom": "Thomas", "solde": 2500}, ...}."""
        fiches = {}
        lignes = self._lire_lignes(self.fichier_comptes, COLONNES_COMPTES, ANCIENNES_COLONNES_COMPTES)

        for ligne in lignes:
            texte = ligne["rfid"].strip().upper()

            try:
                # Vérifie le format de config.FORMAT_CARTE (10 caractères)
                carte = carte_vers_texte(texte_vers_carte(texte))
                solde = int(ligne["solde"])
            except ValueError:
                raise ErreurFichier(f"Ligne invalide dans comptes.csv : {texte}")

            if solde < 0:
                raise ErreurFichier(f"Solde négatif pour la carte {carte}")

            if carte in fiches:
                raise ErreurFichier(f"Carte {carte} en double dans comptes.csv")

            # Sans nom (ancien format ou case vide) : le numéro de la carte
            nom = (ligne.get("nom") or "").strip() or carte
            fiches[carte] = {"nom": nom, "solde": solde}

        return fiches

    def sauvegarder_comptes(self, comptes: dict, noms: dict | None = None) -> None:
        """Sauvegarde tous les comptes.

        comptes : {carte: solde}. noms : {carte: nom}; si absent, les noms
        déjà dans le fichier sont gardés (une carte sans nom prend son numéro).

        Écrit d'abord un fichier temporaire, puis remplace l'ancien fichier
        d'un seul coup avec os.replace() : comptes.csv n'est jamais à moitié
        écrit, même si le programme est interrompu pendant l'écriture.
        """
        if noms is None:
            try:
                noms = self.charger_noms()
            except ErreurFichier:
                noms = {}

        fichier_temporaire = self.fichier_comptes.with_suffix(".tmp")

        try:
            with open(fichier_temporaire, "w", newline="", encoding="utf-8") as fichier:
                ecrivain = csv.writer(fichier)
                ecrivain.writerow(COLONNES_COMPTES)

                for carte, solde in comptes.items():
                    ecrivain.writerow([carte, noms.get(carte, carte), solde])

            os.replace(fichier_temporaire, self.fichier_comptes)

        except OSError as erreur:
            raise ErreurFichier(f"Écriture de comptes.csv impossible : {erreur}")

    # ------------------------------------------------------------------
    # operations.csv
    # ------------------------------------------------------------------

    def charger_operations(self) -> list:
        """Retourne le journal : une liste de dictionnaires."""
        operations = []

        for ligne in self._lire_lignes(self.fichier_operations, COLONNES_OPERATIONS):
            try:
                ligne["montant"] = int(ligne["montant"])
            except ValueError:
                raise ErreurFichier(
                    f"Montant invalide pour l'opération {ligne['operation_id']}"
                )

            operations.append(ligne)

        return operations

    def operation_existe(self, operation_id: str) -> bool:
        """True si une opération porte déjà cet identifiant."""
        for operation in self.charger_operations():
            if operation["operation_id"] == operation_id:
                return True

        return False

    def enregistrer_operation(self, operation: dict) -> None:
        """Ajoute une ligne à la fin du journal."""
        try:
            with open(self.fichier_operations, "a", newline="", encoding="utf-8") as fichier:
                ecrivain = csv.DictWriter(fichier, fieldnames=COLONNES_OPERATIONS)
                ecrivain.writerow(operation)

        except OSError as erreur:
            raise ErreurFichier(f"Écriture de operations.csv impossible : {erreur}")

    # ------------------------------------------------------------------
    # Utilitaire
    # ------------------------------------------------------------------

    @staticmethod
    def _lire_lignes(chemin: Path, colonnes: list, autres_colonnes: list | None = None) -> list:
        """Lit un CSV et vérifie ses colonnes. Lève ErreurFichier si problème.

        autres_colonnes : un deuxième en-tête accepté (ancien format).
        """
        try:
            with open(chemin, "r", newline="", encoding="utf-8") as fichier:
                lecteur = csv.DictReader(fichier)

                if lecteur.fieldnames not in (colonnes, autres_colonnes):
                    raise ErreurFichier(f"{chemin.name} : colonnes attendues {','.join(colonnes)}")

                lignes = list(lecteur)

        except OSError as erreur:
            raise ErreurFichier(f"{chemin.name} absent ou illisible : {erreur}")

        # Une ligne trop courte donne None dans une colonne
        for ligne in lignes:
            if None in ligne.values() or None in ligne:
                raise ErreurFichier(f"{chemin.name} : ligne incomplète ou trop longue")

        return lignes
