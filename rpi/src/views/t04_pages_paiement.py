"""T04 — Pages de tarification et de paiement, version simple
(celle qui est utilisée par main.py).

    PageTarification : tarif, durée et montant calculé
    PagePaiement     : montant figé, délai restant, résultat du paiement

Ce sont des QWidget autonomes, à enregistrer plus tard dans
InterfacePrincipale (T01). Ils ne calculent rien : les valeurs viennent
de GestionTransactions par le contrôleur.

Une version plus complète pour l'écran tactile existe dans
t04_pages_paiement_completes.py (mêmes classes, mêmes méthodes).
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from src.views.formatage import formater_argent, formater_transaction


class PageTarification(QWidget):
    """Affiche le tarif, la durée et le montant avant la confirmation."""

    confirmer_clique = pyqtSignal()    # l'utilisateur confirme le retrait
    annuler_clique = pyqtSignal()

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        self.etiquette_titre = QLabel("Retrait du véhicule")
        self.etiquette_titre.setStyleSheet("font-size: 16px; font-weight: bold;")
        disposition.addWidget(self.etiquette_titre)

        self.etiquette_details = QLabel("")
        disposition.addWidget(self.etiquette_details)

        self.etiquette_montant = QLabel("")
        self.etiquette_montant.setStyleSheet("font-size: 22px; font-weight: bold;")
        disposition.addWidget(self.etiquette_montant)

        boutons = QHBoxLayout()
        self.bouton_confirmer = QPushButton("Confirmer le retrait")
        self.bouton_annuler = QPushButton("Annuler")
        boutons.addWidget(self.bouton_confirmer)
        boutons.addWidget(self.bouton_annuler)
        disposition.addLayout(boutons)

        self.bouton_confirmer.clicked.connect(self.confirmer_clique.emit)
        self.bouton_annuler.clicked.connect(self.annuler_clique.emit)

    def afficher_tarification(self, transaction_id, place, tarif_cents, duree_min, montant_cents):
        """Met à jour les valeurs affichées."""
        self.etiquette_titre.setText(f"Transaction {formater_transaction(transaction_id)} — place {place}")
        self.etiquette_details.setText(
            f"Tarif : {formater_argent(tarif_cents)} par minute commencée\n"
            f"Durée : {duree_min} min"
        )
        self.etiquette_montant.setText(f"Montant dû : {formater_argent(montant_cents)}")


class PagePaiement(QWidget):
    """Affiche le montant figé, le délai restant et le résultat du paiement."""

    annuler_clique = pyqtSignal()

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        self.etiquette_montant = QLabel("")
        self.etiquette_montant.setStyleSheet("font-size: 22px; font-weight: bold;")
        disposition.addWidget(self.etiquette_montant)

        self.etiquette_delai = QLabel("")
        disposition.addWidget(self.etiquette_delai)

        self.barre_delai = QProgressBar()
        self.barre_delai.setTextVisible(False)
        disposition.addWidget(self.barre_delai)

        self.etiquette_resultat = QLabel("")
        self.etiquette_resultat.setWordWrap(True)
        disposition.addWidget(self.etiquette_resultat)

        self.bouton_annuler = QPushButton("Annuler")
        disposition.addWidget(self.bouton_annuler)

        self.bouton_annuler.clicked.connect(self.annuler_clique.emit)

    def afficher_paiement(self, montant_cents, secondes_restantes, secondes_totales):
        """Met à jour le montant figé et le délai restant."""
        self.etiquette_montant.setText(f"À payer : {formater_argent(montant_cents)}")
        self.etiquette_delai.setText(f"Temps restant : {int(secondes_restantes)} s")
        self.barre_delai.setMaximum(int(secondes_totales))
        self.barre_delai.setValue(int(secondes_restantes))

    def afficher_resultat(self, texte: str):
        """Affiche le résultat de la dernière tentative de paiement."""
        self.etiquette_resultat.setText(texte)
