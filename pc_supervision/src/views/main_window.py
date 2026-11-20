"""Fenêtre principale de l'application de supervision (PC) — T13."""

from PyQt6.QtWidgets import QLabel, QMainWindow, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from src import config
from src.views.page_commandes import PageCommandes
from src.views.page_comptes import PageComptes
from src.views.page_stationnement import PageStationnement
from src.views.page_statistiques import PageStatistiques


class MainWindow(QMainWindow):
    """Vue : quatre pages en onglets, état de la connexion et journal."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"ESA — Supervision — Équipe {config.NUMERO_EQUIPE}")
        self.resize(1000, 760)

        widget_central = QWidget()
        self.setCentralWidget(widget_central)

        disposition = QVBoxLayout(widget_central)

        # Indicateur de connexion du PC au broker (rouge tant que déconnecté)
        self.etiquette_connexion = QLabel()
        disposition.addWidget(self.etiquette_connexion)
        self.afficher_connexion(False)

        # Juste en dessous : connexion du Raspberry Pi au broker
        self.etiquette_connexion_rpi = QLabel()
        disposition.addWidget(self.etiquette_connexion_rpi)
        self.afficher_connexion_rpi(None)

        self.page_stationnement = PageStationnement()
        self.page_comptes = PageComptes()
        self.page_commandes = PageCommandes()
        self.page_statistiques = PageStatistiques()

        self.onglets = QTabWidget()
        self.onglets.addTab(self.page_stationnement, "Stationnement")
        self.onglets.addTab(self.page_comptes, "Comptes RFID")
        self.onglets.addTab(self.page_commandes, "Commandes")
        self.onglets.addTab(self.page_statistiques, "Statistiques")
        disposition.addWidget(self.onglets, stretch=4)

        disposition.addWidget(QLabel("Journal des communications MQTT"))
        self.texte_journal = QPlainTextEdit()
        self.texte_journal.setReadOnly(True)
        self.texte_journal.setMaximumBlockCount(500)     # garde les 500 dernières lignes
        disposition.addWidget(self.texte_journal, stretch=1)

    def afficher_connexion(self, connecte: bool):
        """Affiche l'état de la connexion du PC au broker MQTT."""
        if connecte:
            texte, couleur = f"PC → MQTT : connecté à {config.BROKER_IP}", "#2e7d32"
        else:
            texte, couleur = f"PC → MQTT : déconnecté ({config.BROKER_IP})", "#c62828"

        self._peindre_bande(self.etiquette_connexion, texte, couleur)

    def afficher_connexion_rpi(self, en_ligne):
        """Affiche l'état de la connexion du Raspberry Pi au broker.

        en_ligne : True, False, ou None (inconnu : le PC n'est pas connecté,
        ou le RPi ne s'est jamais annoncé sur ce broker).
        """
        if en_ligne is True:
            texte, couleur = "Raspberry Pi → MQTT : connecté", "#2e7d32"
        elif en_ligne is False:
            texte, couleur = "Raspberry Pi → MQTT : déconnecté", "#c62828"
        else:
            texte, couleur = "Raspberry Pi → MQTT : inconnu (aucune nouvelle du RPi)", "#757575"

        self._peindre_bande(self.etiquette_connexion_rpi, texte, couleur)

    @staticmethod
    def _peindre_bande(etiquette: QLabel, texte: str, couleur: str):
        etiquette.setText(texte)
        etiquette.setStyleSheet(
            f"color: white; background-color: {couleur}; font-weight: bold; padding: 4px; border-radius: 4px;"
        )

    def add_log(self, texte: str):
        """Ajoute une ligne au journal (même nom que dans le labo 4)."""
        self.texte_journal.appendPlainText(texte)
