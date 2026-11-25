"""T03 - Page de choix de l'emplacement de parking (QWidget autonome).

Testable seule :  python3 page_parking.py
Aucune logique métier : affichage des 14 emplacements, de leur état, et
émission de signaux (sélection, navigation).
"""
import sys

from PyQt6.QtGui import QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

NB_EMPLACEMENTS = 14
COLONNES = 7

LIBRE, OCCUPE, RESERVE, MAINTENANCE = "libre", "occupe", "reserve", "maintenance"

LIBELLES = {LIBRE: "Libre", OCCUPE: "Occupé",
            RESERVE: "Réservé", MAINTENANCE: "Maintenance"}

# état : (fond, bordure, texte)
COULEURS = {
    LIBRE:       ("#14452d", "#2ecc71", "#ffffff"),
    OCCUPE:      ("#2a1816", "#7a2a22", "#9a8a88"),
    RESERVE:     ("#2a2415", "#7a6222", "#9a9588"),
    MAINTENANCE: ("#1c2128", "#4a545f", "#7f8c8d"),
}


def _style_emplacements() -> str:
    regles = []
    for etat, (fond, bord, texte) in COULEURS.items():
        regles.append(f"""
        QPushButton[etat="{etat}"] {{
            background: {fond}; color: {texte};
            border: 4px solid {bord}; border-radius: 18px;
            font-weight: bold; }}
        QPushButton[etat="{etat}"]:disabled {{
            background: {fond}; color: {texte}; border-color: {bord}; }}""")
    regles.append('QPushButton[etat="libre"]:pressed { background: #1f6b45; }')
    return "\n".join(regles)


STYLE = """
#parking   { background: #0f1b2d; }
QLabel     { color: #e8eef7; }
#titre     { font-size: 40px; font-weight: bold; }
#gros      { background: #2f80ed; color: white; font-size: 32px;
             font-weight: bold; border-radius: 24px; padding: 20px 30px; }
#gros:pressed { background: #1c5fc0; }
#petit     { background: #34495e; color: white; font-size: 24px;
             font-weight: bold; border-radius: 20px; padding: 20px 30px; }
#petit:pressed { background: #22313f; }
""" + _style_emplacements()


class BoutonTexteAjuste(QPushButton):
    """Bouton dont la taille ne dépend pas du texte : c'est le texte qui
    s'adapte (police réduite au besoin) à la taille du bouton."""

    def __init__(self, taille_max: int = 28):
        super().__init__()
        self._taille_max = taille_max
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Ignored)

    def setText(self, texte: str) -> None:
        super().setText(texte)
        self._ajuster_texte()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajuster_texte()

    def _ajuster_texte(self, marge: int = 24) -> None:
        lignes = self.text().split("\n")
        largeur = self.width() - marge
        hauteur = self.height() - marge
        police = self.font()
        police.setBold(True)
        taille = self._taille_max
        while taille > 8:
            police.setPixelSize(taille)
            fm = QFontMetrics(police)
            if (max(fm.horizontalAdvance(ligne) for ligne in lignes) <= largeur
                    and fm.lineSpacing() * len(lignes) <= hauteur):
                break
            taille -= 1
        police.setPixelSize(taille)
        self.setFont(police)


class _BoutonEmplacement(BoutonTexteAjuste):
    def __init__(self, numero: int):
        super().__init__(taille_max=28)
        self.numero = numero
        self.setMinimumHeight(130)
        self.definir_etat(LIBRE)

    def definir_etat(self, etat: str) -> None:
        self.setProperty("etat", etat)
        self.setText(f"P{self.numero}\n{LIBELLES[etat]}")
        self.setEnabled(etat == LIBRE)       # grisé si pas disponible
        self.style().unpolish(self)          # force Qt à réappliquer le style
        self.style().polish(self)




class PageParking(QWidget):
    navigation_demandee = pyqtSignal(str)    # nom de la page à afficher
    emplacement_choisi = pyqtSignal(int)     # numéro 1..14

    def __init__(self):
        super().__init__()
        self.setObjectName("parking")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)

        titre = QLabel("Choisissez un emplacement", objectName="titre")
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Grille des 14 emplacements ---
        self._boutons: dict[int, _BoutonEmplacement] = {}
        grille = QGridLayout()
        grille.setSpacing(12)
        for c in range(COLONNES):
            grille.setColumnStretch(c, 1)
        for r in range(2):
            grille.setRowStretch(r, 1)
        for i in range(NB_EMPLACEMENTS):
            numero = i + 1
            bouton = _BoutonEmplacement(numero)
            bouton.clicked.connect(
                lambda _=False, n=numero: self._selectionner(n))
            self._boutons[numero] = bouton
            grille.addWidget(bouton, i // COLONNES, i % COLONNES)

        # --- Boutons du bas ---
        accueil = QPushButton("⌂ Accueil", objectName="petit")
        retrait = QPushButton("Retirer ma voiture", objectName="gros")
        test = QPushButton("Page de test", objectName="gros")
        accueil.clicked.connect(lambda: self.navigation_demandee.emit("accueil"))
        retrait.clicked.connect(lambda: self.navigation_demandee.emit("retrait"))
        test.clicked.connect(lambda: self.navigation_demandee.emit("test"))
        bas = QHBoxLayout()
        bas.setSpacing(12)
        bas.addWidget(accueil)
        bas.addWidget(retrait, 1)
        bas.addWidget(test, 1)

        racine = QVBoxLayout(self)
        racine.setContentsMargins(20, 12, 20, 16)
        racine.setSpacing(12)
        racine.addWidget(titre)
        racine.addLayout(grille, 1)
        racine.addLayout(bas)

    # --- API : états mis à jour par l'application ---
    def definir_etat(self, numero: int, etat: str) -> None:
        """numero 1..14 ; etat : LIBRE, OCCUPE, RESERVE ou MAINTENANCE."""
        if numero in self._boutons and etat in LIBELLES:
            self._boutons[numero].definir_etat(etat)

    def definir_etats(self, etats: dict) -> None:
        """Ex. {1: LIBRE, 2: OCCUPE, 3: RESERVE, ...}"""
        for numero, etat in etats.items():
            self.definir_etat(numero, etat)

    def etat(self, numero: int) -> str:
        """État actuel de l'emplacement `numero` (LIBRE, OCCUPE, ...)."""
        return self._boutons[numero].property("etat")

    # --- Sélection ---
    def _selectionner(self, numero: int) -> None:
        self.emplacement_choisi.emit(numero)
        # >>> ICI : mettre le protocole de sélection de l'emplacement `numero`



if __name__ == "__main__":
    app = QApplication(sys.argv)
    page = PageParking()
    page.navigation_demandee.connect(lambda nom: print("navigation ->", nom))
    page.emplacement_choisi.connect(lambda n: print("emplacement ->", n))
    page.definir_etats({2: OCCUPE, 5: RESERVE, 9: MAINTENANCE, 12: OCCUPE})
    page.resize(1024, 600)
    page.show()
    sys.exit(app.exec())