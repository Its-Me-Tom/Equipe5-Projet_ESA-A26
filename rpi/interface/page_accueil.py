"""T01 - Page d'accueil (QWidget autonome).

Testable seule :  python3 page_accueil.py
Aucune logique métier (réservation, paiement, billet) : seulement l'affichage
et une demande de navigation.
"""
import sys

from PyQt6.QtCore import QDateTime, QLocale, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

PAGE_DEMARRAGE = "reservation"  # à confirmer avec T03 (section 10, point 4)

COULEURS = {True: "#2ecc71", False: "#e72e1a", None: "#7f8c8d"}  # OK / KO / ?

STYLE = """
#accueil   { background: #0f1b2d; }
QLabel     { color: #e8eef7; }
#titre     { font-size: 80px; font-weight: bold; }
#sous      { font-size: 34px; color: #8fa6c4; }
#bienvenue { font-size: 46px; }
#heure     { font-size: 52px; font-weight: bold; }
#date      { font-size: 24px; color: #8fa6c4; }
#commencer { background: #2f80ed; color: white; font-size: 48px;
             font-weight: bold; border-radius: 28px; padding: 34px 110px; }
#commencer:pressed { background: #1c5fc0; }
#barre     { background: #0a1322; }
#barre QLabel { font-size: 24px; color: #c4d2e6; }
"""


class _Voyant(QLabel):
    """Pastille d'état : vert = disponible, rouge = indisponible, gris = inconnu."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(24, 24) #avant 14
        self.definir(None)

    def definir(self, etat):
        self.setStyleSheet(
            f"background:{COULEURS[etat]}; border-radius:12px;") #avant 7px


class PageAccueil(QWidget):
    navigation_demandee = pyqtSignal(str)  # nom de la page à afficher

    def __init__(self):
        super().__init__()
        self.setObjectName("accueil")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self._locale = QLocale(QLocale.Language.French, QLocale.Country.Canada)

        # --- Heure et date (haut à droite) ---
        self._heure = QLabel(objectName="heure")
        self._date = QLabel(objectName="date")
        for lbl in (self._heure, self._date):
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        haut = QVBoxLayout()
        haut.setSpacing(0)
        haut.addWidget(self._heure)
        haut.addWidget(self._date)

        # --- Centre : titre, message, bouton ---
        titre = QLabel("ESA PARKING", objectName="titre")
        sous = QLabel("Stationnement automatisé", objectName="sous")
        bienvenue = QLabel("Bienvenue", objectName="bienvenue")
        self._bouton = QPushButton("Commencer", objectName="commencer")
        self._bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bouton.clicked.connect(
            lambda: self.navigation_demandee.emit(PAGE_DEMARRAGE))

        centre = QVBoxLayout()
        centre.setSpacing(12)
        centre.addStretch(2)
        for w in (titre, sous, bienvenue, self._bouton):
            centre.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
        centre.addStretch(3)
        centre.insertSpacing(3, 30)  # air avant « Bienvenue »

        # --- Barre d'état (bas) : radar, CAN, luminosité ---
        self._voyant_radar, self._voyant_can = _Voyant(), _Voyant()
        self._txt_radar, self._txt_can = QLabel("Radar"), QLabel("CAN")
        self._txt_lum = QLabel("Luminosité : --")
        barre = QFrame(objectName="barre")
        lb = QHBoxLayout(barre)
        lb.setContentsMargins(24, 14, 24, 14)      # avant : 24, 8, 24, 8
        for w in (self._voyant_radar, self._txt_radar):
            lb.addWidget(w)
        lb.addSpacing(24)
        for w in (self._voyant_can, self._txt_can):
            lb.addWidget(w)
        lb.addStretch(1)
        lb.addWidget(self._txt_lum)

        # --- Assemblage ---
        corps = QVBoxLayout()
        corps.setContentsMargins(24, 16, 24, 8)
        corps.addLayout(haut)
        corps.addLayout(centre, 1)
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addLayout(corps, 1)
        racine.addWidget(barre)

        self._horloge = QTimer(self)
        self._horloge.timeout.connect(self._maj_heure)
        self._horloge.start(1000)
        self._maj_heure()

    # --- Affichage mis à jour par l'application (None = inconnu) ---
    def definir_radar_disponible(self, dispo):
        self._voyant_radar.definir(dispo)
        self._txt_radar.setText("Radar indisponible" if dispo is False else "Radar")

    def definir_can_disponible(self, dispo):
        self._voyant_can.definir(dispo)
        self._txt_can.setText("CAN indisponible" if dispo is False else "CAN")

    def definir_luminosite(self, pourcentage):
        self._txt_lum.setText("Luminosité : --" if pourcentage is None
                              else f"Luminosité : {round(pourcentage)} %")

    def _maj_heure(self):
        maintenant = QDateTime.currentDateTime()
        self._heure.setText(self._locale.toString(maintenant, "HH:mm"))
        self._date.setText(self._locale.toString(maintenant, "dddd d MMMM yyyy"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    page = PageAccueil()
    page.navigation_demandee.connect(lambda nom: print("navigation ->", nom))
    page.definir_radar_disponible(True)
    page.definir_can_disponible(True)
    page.definir_luminosite(70)
    page.resize(1024, 600)
    page.show()
    sys.exit(app.exec())