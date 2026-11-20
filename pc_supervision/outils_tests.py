"""Outil commun aux tests du PC (test_pc_*.py).

Les tests du PC vérifient le modèle seul : aucun broker ni interface
graphique n'est nécessaire.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

FICHIER_RESULTATS = Path(__file__).resolve().parent / "resultats_tests.csv"


class RapportTest:
    """Affiche les vérifications et les ajoute à resultats_tests.csv."""

    def __init__(self, numero: int, titre: str):
        self.nom = f"PC-{numero:02d} {titre}"
        self.lignes = []
        self.reussi = True

        print(f"\n=== {self.nom} ===")

    def verifier(self, description: str, obtenu, attendu):
        """Compare une valeur obtenue à la valeur attendue."""
        correct = obtenu == attendu
        self.reussi = self.reussi and correct

        print(f"  [{'OK' if correct else 'ÉCHEC'}] {description} : attendu {attendu!r}, obtenu {obtenu!r}")

        self.lignes.append([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "T13-PC", self.nom, "simule", description,
            repr(attendu), repr(obtenu), "Reussi" if correct else "Echoue",
        ])

    def terminer(self):
        """Affiche le verdict, écrit le CSV et termine le script."""
        print(f"Verdict : {'RÉUSSI' if self.reussi else 'ÉCHOUÉ'}")

        nouveau = not FICHIER_RESULTATS.exists()

        with open(FICHIER_RESULTATS, "a", newline="", encoding="utf-8-sig" if nouveau else "utf-8") as fichier:
            ecrivain = csv.writer(fichier, delimiter=";")

            if nouveau:
                ecrivain.writerow(["Date", "Tache", "Test", "Mode", "Description", "Attendu", "Obtenu", "Etat"])

            ecrivain.writerows(self.lignes)

        sys.exit(0 if self.reussi else 1)
