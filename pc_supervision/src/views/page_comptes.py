"""Page Comptes RFID : consultation des soldes et ajout de crédit.

Les comptes appartiennent au Raspberry Pi (T02). Cette page ne fait
qu'envoyer des demandes et afficher les réponses.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.views.formatage import formater_argent


class PageComptes(QWidget):
    """Tableau des comptes et formulaire d'ajout de crédit."""

    actualiser_clique = pyqtSignal()             # CONSULTER_SOLDE (tous)
    crediter_clique = pyqtSignal(str, int)       # carte, montant en cents
    renvoyer_clique = pyqtSignal()               # renvoyer la même commande

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        self.bouton_actualiser = QPushButton("Consulter les soldes")
        disposition.addWidget(self.bouton_actualiser)

        self.tableau = QTableWidget()
        self.tableau.setColumnCount(2)
        self.tableau.setHorizontalHeaderLabels(["Carte RFID", "Solde"])
        self.tableau.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableau.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tableau.verticalHeader().setVisible(False)
        self.tableau.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        disposition.addWidget(self.tableau)

        # --- Ajout de crédit au compte sélectionné ---
        ligne_credit = QHBoxLayout()
        ligne_credit.addWidget(QLabel("Crédit à ajouter au compte sélectionné :"))

        self.saisie_montant = QDoubleSpinBox()
        self.saisie_montant.setRange(0.01, 500.00)
        self.saisie_montant.setValue(5.00)
        self.saisie_montant.setSuffix(" $")
        ligne_credit.addWidget(self.saisie_montant)

        self.bouton_crediter = QPushButton("Ajouter le crédit")
        ligne_credit.addWidget(self.bouton_crediter)
        disposition.addLayout(ligne_credit)

        # Sert à démontrer qu'une commande répétée ne crédite pas deux fois
        self.bouton_renvoyer = QPushButton("Renvoyer la dernière commande (même id_commande)")
        disposition.addWidget(self.bouton_renvoyer)

        self.etiquette_reponse = QLabel("Réponse : ---")
        self.etiquette_reponse.setWordWrap(True)
        disposition.addWidget(self.etiquette_reponse)

        self.bouton_actualiser.clicked.connect(self.actualiser_clique.emit)
        self.bouton_crediter.clicked.connect(self._crediter)
        self.bouton_renvoyer.clicked.connect(self.renvoyer_clique.emit)

    def _crediter(self):
        ligne = self.tableau.currentRow()

        if ligne < 0:
            self.etiquette_reponse.setText("Réponse : sélectionner d'abord un compte.")
            return

        carte = self.tableau.item(ligne, 0).text()

        # Le PC envoie des cents entiers : 5,00 $ -> 500
        cents = round(self.saisie_montant.value() * 100)
        self.crediter_clique.emit(carte, cents)

    def afficher_comptes(self, comptes: dict):
        """Affiche les soldes reçus (carte -> solde en cents)."""
        selection = self.tableau.currentRow()
        self.tableau.setRowCount(len(comptes))

        for ligne, (carte, solde) in enumerate(comptes.items()):
            self.tableau.setItem(ligne, 0, QTableWidgetItem(carte))
            self.tableau.setItem(ligne, 1, QTableWidgetItem(formater_argent(solde)))

        if 0 <= selection < len(comptes):
            self.tableau.selectRow(selection)

    def afficher_reponse(self, texte: str):
        self.etiquette_reponse.setText(f"Réponse : {texte}")
