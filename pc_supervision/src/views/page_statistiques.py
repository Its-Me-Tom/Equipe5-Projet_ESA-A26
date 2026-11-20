"""Page Statistiques : historique d'utilisation par compte et graphiques.

Les chiffres viennent du topic « transactions » publié par le Raspberry Pi.
Le tableau donne les valeurs exactes; les graphiques Matplotlib montrent
la comparaison entre les comptes.
"""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from PyQt6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from src.views.formatage import formater_argent, formater_heure, formater_transaction

# Couleurs des graphiques
COULEUR_BARRES = "#2a78d6"     # une seule série (les comptes) : une seule couleur
COULEUR_FOND = "#fcfcfb"
COULEUR_TEXTE = "#0b0b0b"
COULEUR_DISCRETE = "#52514e"
COULEUR_GRILLE = "#e3e2de"


def _construire_tableau(entetes: list) -> QTableWidget:
    tableau = QTableWidget()
    tableau.setColumnCount(len(entetes))
    tableau.setHorizontalHeaderLabels(entetes)
    tableau.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tableau.verticalHeader().setVisible(False)
    tableau.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return tableau


class PageStatistiques(QWidget):
    """Tableau par compte, deux graphiques et historique des transactions."""

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        disposition.addWidget(QLabel("Utilisation par compte"))
        self.tableau_comptes = _construire_tableau([
            "Carte RFID", "Solde", "Crédits", "Total crédité", "Paiements", "Total payé",
        ])
        disposition.addWidget(self.tableau_comptes, stretch=2)

        # Deux graphiques côte à côte : une mesure par graphique, un seul
        # axe vertical chacun (les dollars et les nombres ne se mélangent pas).
        # layout="constrained" : titres et étiquettes replacés au redimensionnement.
        self.figure = Figure(figsize=(9, 3), dpi=100, facecolor=COULEUR_FOND, layout="constrained")
        self.canevas = FigureCanvasQTAgg(self.figure)
        self.axe_paye = self.figure.add_subplot(1, 2, 1)
        self.axe_nombre = self.figure.add_subplot(1, 2, 2)
        disposition.addWidget(self.canevas, stretch=3)

        disposition.addWidget(QLabel("Historique des transactions"))
        self.tableau_transactions = _construire_tableau([
            "Numéro", "Place", "État", "Carte de paiement", "Montant", "Clôture",
        ])
        disposition.addWidget(self.tableau_transactions, stretch=2)

        self.afficher_statistiques([], [])

    def afficher_statistiques(self, statistiques: list, transactions: list):
        """Met à jour les tableaux et les graphiques."""
        self._remplir_comptes(statistiques)
        self._remplir_transactions(transactions)

        # Étiquette courte sous chaque barre : les 4 derniers caractères
        etiquettes = [f"…{compte['rfid'][-4:]}" for compte in statistiques]
        payes = [compte["total_debits"] / 100 for compte in statistiques]
        nombres = [compte["nb_debits"] for compte in statistiques]

        self._dessiner_barres(self.axe_paye, "Total payé ($)", etiquettes, payes, "{:.2f}")
        self._dessiner_barres(self.axe_nombre, "Stationnements payés", etiquettes, nombres, "{:d}")

        self.canevas.draw_idle()

    @staticmethod
    def _dessiner_barres(axe, titre: str, etiquettes: list, valeurs: list, format_valeur: str):
        """Dessine un graphique à barres simple."""
        axe.clear()
        axe.set_facecolor(COULEUR_FOND)
        axe.set_title(titre, color=COULEUR_TEXTE, fontsize=10, loc="left")

        barres = axe.bar(etiquettes, valeurs, color=COULEUR_BARRES, width=0.5, zorder=2)

        # Valeur exacte au-dessus de chaque barre (peu de barres : lisible)
        axe.bar_label(barres, labels=[format_valeur.format(valeur) for valeur in valeurs],
                      color=COULEUR_TEXTE, fontsize=9, padding=2)

        # Grille et axes discrets : les barres restent l'élément principal
        axe.grid(axis="y", color=COULEUR_GRILLE, linewidth=0.8, zorder=1)
        axe.tick_params(colors=COULEUR_DISCRETE, labelsize=9, length=0)
        axe.set_ylim(0, max(valeurs, default=0) * 1.25 or 1)
        axe.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))

        for cote in ("top", "right", "left"):
            axe.spines[cote].set_visible(False)

        axe.spines["bottom"].set_color(COULEUR_GRILLE)

    def _remplir_comptes(self, statistiques: list):
        tableau = self.tableau_comptes
        tableau.setRowCount(len(statistiques))

        for ligne, compte in enumerate(statistiques):
            valeurs = [
                compte["rfid"],
                formater_argent(compte["solde"]),
                str(compte["nb_credits"]),
                formater_argent(compte["total_credits"]),
                str(compte["nb_debits"]),
                formater_argent(compte["total_debits"]),
            ]

            for colonne, valeur in enumerate(valeurs):
                tableau.setItem(ligne, colonne, QTableWidgetItem(valeur))

    def _remplir_transactions(self, transactions: list):
        tableau = self.tableau_transactions
        tableau.setRowCount(len(transactions))

        for ligne, transaction in enumerate(transactions):
            valeurs = [
                formater_transaction(transaction["id"]),
                transaction["place"],
                transaction["etat"],
                transaction["rfid_paiement"],
                formater_argent(transaction["montant_fige"]),
                formater_heure(transaction["fin"]),
            ]

            for colonne, valeur in enumerate(valeurs):
                tableau.setItem(ligne, colonne, QTableWidgetItem(valeur))
