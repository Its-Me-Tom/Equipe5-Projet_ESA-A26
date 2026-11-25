"""Fenêtre de test du Raspberry Pi.

Ce n'est PAS la fenêtre finale de la borne (celle-là appartient à T01).
Elle sert à faire fonctionner et à démontrer T02, T04, T07, T12 et T13
seuls, avec le matériel réel ou simulé.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src import config
from src.views.t04_pages_paiement import PagePaiement, PageTarification


class MainWindow(QMainWindow):
    """Vue : seulement des widgets, aucune logique."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("ESA — Raspberry Pi — essai de T02, T04, T07, T12 et T13")
        self.resize(1150, 760)

        widget_central = QWidget()
        self.setCentralWidget(widget_central)

        disposition = QHBoxLayout(widget_central)
        disposition.addLayout(self._construire_colonne_gauche(), stretch=2)
        disposition.addLayout(self._construire_colonne_droite(), stretch=3)

    # ------------------------------------------------------------------
    # Colonne de gauche : états, simulation, éclairage et retrait
    # ------------------------------------------------------------------

    def _construire_colonne_gauche(self) -> QVBoxLayout:
        colonne = QVBoxLayout()

        # --- États ---
        groupe_etats = QGroupBox("États")
        disposition_etats = QVBoxLayout(groupe_etats)

        self.etiquette_service = QLabel("Borne : ---")
        self.etiquette_service.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.etiquette_liens = QLabel("MQTT : ---   CAN : ---   RFID : ---")
        self.etiquette_carte = QLabel("Dernière carte : ---")
        self.bouton_en_service = QPushButton("Remettre en service (local)")

        disposition_etats.addWidget(self.etiquette_service)
        disposition_etats.addWidget(self.etiquette_liens)
        disposition_etats.addWidget(self.etiquette_carte)
        disposition_etats.addWidget(self.bouton_en_service)
        colonne.addWidget(groupe_etats)

        # --- Simulation ---
        groupe_simulation = QGroupBox("Simulation du matériel absent")
        disposition_simulation = QVBoxLayout(groupe_simulation)

        ligne_carte = QHBoxLayout()
        self.liste_cartes = QComboBox()
        self.bouton_carte = QPushButton("Présenter la carte")
        ligne_carte.addWidget(self.liste_cartes)
        ligne_carte.addWidget(self.bouton_carte)
        disposition_simulation.addLayout(ligne_carte)

        ligne_depot = QHBoxLayout()
        self.liste_places = QComboBox()
        self.liste_places.addItems(list(config.PLACES))
        self.bouton_depot = QPushButton("Ranger un véhicule")
        ligne_depot.addWidget(self.liste_places)
        ligne_depot.addWidget(self.bouton_depot)
        disposition_simulation.addLayout(ligne_depot)

        self.bouton_retirer_vehicule = QPushButton("Retirer le véhicule devant la barrière")
        disposition_simulation.addWidget(self.bouton_retirer_vehicule)
        colonne.addWidget(groupe_simulation)

        # --- Éclairage (T07) : réglage manuel de l'intensité ---
        groupe_eclairage = QGroupBox("Éclairage blanc (T07)")
        grille_eclairage = QGridLayout(groupe_eclairage)
        self.curseurs_eclairage = {}
        self.etiquettes_eclairage = {}

        for niveau in (0, 1, 2):
            curseur = QSlider(Qt.Orientation.Horizontal)
            curseur.setRange(0, 255)
            curseur.setValue(config.INTENSITE_ECLAIRAGE[niveau])
            etiquette = QLabel(str(config.INTENSITE_ECLAIRAGE[niveau]))

            grille_eclairage.addWidget(QLabel(f"Niveau {niveau}"), niveau, 0)
            grille_eclairage.addWidget(curseur, niveau, 1)
            grille_eclairage.addWidget(etiquette, niveau, 2)

            self.curseurs_eclairage[niveau] = curseur
            self.etiquettes_eclairage[niveau] = etiquette

        colonne.addWidget(groupe_eclairage)

        # --- Retrait ---
        groupe_retrait = QGroupBox("Retrait (T12) et paiement (T04)")
        disposition_retrait = QVBoxLayout(groupe_retrait)

        ligne_demande = QHBoxLayout()
        self.saisie_transaction = QLineEdit()
        self.saisie_transaction.setPlaceholderText("Numéro de transaction (6 chiffres)")
        self.saisie_transaction.setMaxLength(6)
        self.bouton_demande = QPushButton("Demander le retrait")
        ligne_demande.addWidget(self.saisie_transaction)
        ligne_demande.addWidget(self.bouton_demande)
        disposition_retrait.addLayout(ligne_demande)

        self.etiquette_retrait = QLabel("Retrait : ---")
        self.etiquette_retrait.setWordWrap(True)
        disposition_retrait.addWidget(self.etiquette_retrait)

        # Pages de T04 : vide, tarification, paiement
        self.pages = QStackedWidget()
        self.page_vide = QWidget()
        self.page_tarification = PageTarification()
        self.page_paiement = PagePaiement()

        self.pages.addWidget(self.page_vide)
        self.pages.addWidget(self.page_tarification)
        self.pages.addWidget(self.page_paiement)
        disposition_retrait.addWidget(self.pages)

        colonne.addWidget(groupe_retrait)
        colonne.addStretch()

        return colonne

    # ------------------------------------------------------------------
    # Colonne de droite : places, transactions et journal
    # ------------------------------------------------------------------

    def _construire_colonne_droite(self) -> QVBoxLayout:
        colonne = QVBoxLayout()

        colonne.addWidget(QLabel("Places : état logique, détecteur IR et DEL (T07)"))
        self.tableau_places = self._construire_tableau(["Place", "État", "IR", "DEL"])
        self.tableau_places.setRowCount(len(config.PLACES))
        colonne.addWidget(self.tableau_places, stretch=3)

        self.etiquette_rampe = QLabel("IR devant la barrière : ---")
        colonne.addWidget(self.etiquette_rampe)

        colonne.addWidget(QLabel("Transactions"))
        self.tableau_transactions = self._construire_tableau(["Numéro", "Place", "État", "Montant figé"])
        colonne.addWidget(self.tableau_transactions, stretch=2)

        colonne.addWidget(QLabel("Journal"))
        self.texte_journal = QPlainTextEdit()
        self.texte_journal.setReadOnly(True)
        colonne.addWidget(self.texte_journal, stretch=2)

        return colonne

    @staticmethod
    def _construire_tableau(entetes: list) -> QTableWidget:
        tableau = QTableWidget()
        tableau.setColumnCount(len(entetes))
        tableau.setHorizontalHeaderLabels(entetes)
        tableau.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tableau.verticalHeader().setVisible(False)
        tableau.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return tableau
