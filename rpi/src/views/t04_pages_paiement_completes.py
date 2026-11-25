"""T04 — Pages de tarification et de paiement, version complète pour
l'écran tactile (1024 × 600).

PAS ENCORE UTILISÉE par main.py. Pour l'essayer seule :

    python -m src.views.t04_pages_paiement_completes

Pour l'utiliser à la place de la version simple, changer UNE ligne dans
src/views/main_window.py :

    from src.views.t04_pages_paiement import PagePaiement, PageTarification
    devient
    from src.views.t04_pages_paiement_completes import PagePaiement, PageTarification

Les classes ont les mêmes noms, signaux et méthodes que la version simple.
En plus : gros boutons tactiles, décompte coloré, et PageSaisieBillet, un
clavier numérique pour saisir le numéro de transaction à six chiffres.
"""

import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.views.formatage import formater_argent, formater_transaction

# Styles communs aux trois pages
STYLE_TITRE = "font-size: 30px; font-weight: bold;"
STYLE_TEXTE = "font-size: 22px;"
STYLE_MONTANT = "font-size: 64px; font-weight: bold;"
STYLE_BOUTON = "font-size: 24px; padding: 18px; border-radius: 10px;"
STYLE_BOUTON_PRINCIPAL = STYLE_BOUTON + "background-color: #2e7d32; color: white;"
STYLE_BOUTON_ANNULER = STYLE_BOUTON + "background-color: #9e9e9e; color: white;"

SECONDES_URGENTES = 10    # le décompte devient rouge sous ce nombre de secondes


def _etiquette_centree(texte: str, style: str) -> QLabel:
    etiquette = QLabel(texte)
    etiquette.setStyleSheet(style)
    etiquette.setAlignment(Qt.AlignmentFlag.AlignCenter)
    etiquette.setWordWrap(True)
    return etiquette


class PageSaisieBillet(QWidget):
    """Clavier numérique : saisie manuelle du numéro de transaction."""

    numero_saisi = pyqtSignal(int)     # numéro à six chiffres validé

    def __init__(self):
        super().__init__()

        self._chiffres = ""

        disposition = QVBoxLayout(self)
        disposition.addWidget(_etiquette_centree("Scannez votre billet ou entrez le numéro", STYLE_TITRE))

        self.etiquette_numero = _etiquette_centree("", STYLE_MONTANT)
        disposition.addWidget(self.etiquette_numero)

        grille = QGridLayout()
        touches = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Effacer", "0", "OK"]

        for indice, touche in enumerate(touches):
            bouton = QPushButton(touche)
            bouton.setStyleSheet(STYLE_BOUTON_PRINCIPAL if touche == "OK" else STYLE_BOUTON)
            bouton.clicked.connect(lambda coche, t=touche: self.appuyer(t))
            grille.addWidget(bouton, indice // 3, indice % 3)

        disposition.addLayout(grille)
        self._rafraichir()

    def appuyer(self, touche: str):
        if touche == "Effacer":
            self._chiffres = self._chiffres[:-1]

        elif touche == "OK":
            if len(self._chiffres) == 6:
                self.numero_saisi.emit(int(self._chiffres))
                self._chiffres = ""

        elif len(self._chiffres) < 6:
            self._chiffres += touche

        self._rafraichir()

    def _rafraichir(self):
        # Les chiffres manquants sont affichés par des tirets : 12----
        self.etiquette_numero.setText(self._chiffres.ljust(6, "-"))


class PageTarification(QWidget):
    """Tarif, durée et montant calculé, avant la confirmation du retrait."""

    confirmer_clique = pyqtSignal()
    annuler_clique = pyqtSignal()

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        self.etiquette_titre = _etiquette_centree("Retrait du véhicule", STYLE_TITRE)
        self.etiquette_details = _etiquette_centree("", STYLE_TEXTE)
        self.etiquette_montant = _etiquette_centree("", STYLE_MONTANT)
        note = _etiquette_centree("Le montant sera figé pendant 60 secondes après la confirmation.", STYLE_TEXTE)

        disposition.addWidget(self.etiquette_titre)
        disposition.addWidget(self.etiquette_details)
        disposition.addWidget(self.etiquette_montant)
        disposition.addWidget(note)

        boutons = QHBoxLayout()
        self.bouton_annuler = QPushButton("Annuler")
        self.bouton_annuler.setStyleSheet(STYLE_BOUTON_ANNULER)
        self.bouton_confirmer = QPushButton("Confirmer le retrait")
        self.bouton_confirmer.setStyleSheet(STYLE_BOUTON_PRINCIPAL)
        boutons.addWidget(self.bouton_annuler)
        boutons.addWidget(self.bouton_confirmer, stretch=2)
        disposition.addLayout(boutons)

        self.bouton_confirmer.clicked.connect(self.confirmer_clique.emit)
        self.bouton_annuler.clicked.connect(self.annuler_clique.emit)

    def afficher_tarification(self, transaction_id, place, tarif_cents, duree_min, montant_cents):
        self.etiquette_titre.setText(f"Transaction {formater_transaction(transaction_id)} — place {place}")
        self.etiquette_details.setText(
            f"Tarif : {formater_argent(tarif_cents)} par minute commencée"
            f"     •     Durée : {duree_min} min"
        )
        self.etiquette_montant.setText(formater_argent(montant_cents))


class PagePaiement(QWidget):
    """Montant figé, décompte de 60 s et résultat du paiement."""

    annuler_clique = pyqtSignal()

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        disposition.addWidget(_etiquette_centree("Présentez UNE carte RFID qui couvre tout le montant", STYLE_TITRE))

        self.etiquette_montant = _etiquette_centree("", STYLE_MONTANT)
        disposition.addWidget(self.etiquette_montant)

        self.etiquette_delai = _etiquette_centree("", STYLE_TEXTE)
        disposition.addWidget(self.etiquette_delai)

        self.barre_delai = QProgressBar()
        self.barre_delai.setTextVisible(False)
        self.barre_delai.setFixedHeight(30)
        disposition.addWidget(self.barre_delai)

        self.etiquette_resultat = _etiquette_centree("", STYLE_TEXTE)
        disposition.addWidget(self.etiquette_resultat)

        self.bouton_annuler = QPushButton("Annuler le retrait")
        self.bouton_annuler.setStyleSheet(STYLE_BOUTON_ANNULER)
        disposition.addWidget(self.bouton_annuler)

        self.bouton_annuler.clicked.connect(self.annuler_clique.emit)

    def afficher_paiement(self, montant_cents, secondes_restantes, secondes_totales):
        self.etiquette_montant.setText(formater_argent(montant_cents))
        self.etiquette_delai.setText(f"Temps restant : {int(secondes_restantes)} s")
        self.barre_delai.setMaximum(int(secondes_totales))
        self.barre_delai.setValue(int(secondes_restantes))

        # Le décompte passe au rouge quand il reste peu de temps
        couleur = "#c62828" if secondes_restantes <= SECONDES_URGENTES else "#1565c0"
        self.barre_delai.setStyleSheet(f"QProgressBar::chunk {{ background-color: {couleur}; }}")

    def afficher_resultat(self, texte: str):
        """Résultat de la dernière tentative (refus affiché en rouge)."""
        couleur = "#c62828" if "refusé" in texte.lower() else "#2e7d32"

        self.etiquette_resultat.setStyleSheet(STYLE_TEXTE + f"color: {couleur};")
        self.etiquette_resultat.setText(texte)


# ----------------------------------------------------------------------
# Aperçu : affiche les trois pages avec des valeurs d'exemple
# ----------------------------------------------------------------------

def _apercu():
    application = QApplication(sys.argv)

    pages = QStackedWidget()
    pages.setWindowTitle("Aperçu des pages T04")
    pages.resize(1024, 600)

    saisie = PageSaisieBillet()
    tarification = PageTarification()
    paiement = PagePaiement()

    for page in (saisie, tarification, paiement):
        pages.addWidget(page)

    tarification.afficher_tarification(123, "E1.3", 25, 10, 250)
    paiement.afficher_paiement(250, 8, 60)
    paiement.afficher_resultat("Paiement refusé : SOLDE_INSUFFISANT")

    # Navigation de l'aperçu : numéro saisi -> tarification -> paiement
    saisie.numero_saisi.connect(lambda numero: pages.setCurrentWidget(tarification))
    tarification.confirmer_clique.connect(lambda: pages.setCurrentWidget(paiement))
    tarification.annuler_clique.connect(lambda: pages.setCurrentWidget(saisie))
    paiement.annuler_clique.connect(lambda: pages.setCurrentWidget(saisie))

    pages.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    _apercu()
