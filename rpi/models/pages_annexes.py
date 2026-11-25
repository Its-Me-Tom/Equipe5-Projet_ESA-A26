"""Pages annexes : retrait de voiture et page de test."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QVBoxLayout, QWidget)

from .main_interface import LUMINOSITE_MIN
from .page_parking import (COULEURS, LIBELLES, LIBRE, MAINTENANCE, OCCUPE,
                           RESERVE, BoutonTexteAjuste)

STYLE_RETOUR = """
    QPushButton { background: #2f80ed; color: white; font-size: 26px;
                  font-weight: bold; border-radius: 20px; }
    QPushButton:pressed { background: #1c5fc0; }
"""


class PageRetrait(QWidget):
    navigation_demandee = pyqtSignal(str)
    retrait_demande = pyqtSignal()           # le client veut récupérer sa voiture

    def __init__(self):
        super().__init__()
        racine = QHBoxLayout(self)
        racine.setContentsMargins(20, 20, 20, 20)

        # --- Colonne gauche : bouton arrière ---
        retour = QPushButton("←\nRetour")
        retour.setFixedSize(140, 140)
        retour.setStyleSheet(STYLE_RETOUR)
        retour.clicked.connect(lambda: self.navigation_demandee.emit("reservation"))
        gauche = QVBoxLayout()
        gauche.addWidget(retour)
        gauche.addStretch(1)
        racine.addLayout(gauche)

        # --- Centre ---
        titre = QLabel("Retrait de la voiture")
        titre.setStyleSheet("font-size: 40px; font-weight: bold;")
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)

        confirmer = QPushButton("Récupérer ma voiture")
        confirmer.setStyleSheet("""
            QPushButton { background: #2ecc71; color: white; font-size: 36px;
                          font-weight: bold; border-radius: 28px; padding: 30px 80px; }
            QPushButton:pressed { background: #239b56; }""")
        confirmer.clicked.connect(self._demander_retrait)

        centre = QVBoxLayout()
        centre.addStretch(1)
        centre.addWidget(titre)
        centre.addSpacing(30)
        centre.addWidget(confirmer, 0, Qt.AlignmentFlag.AlignHCenter)
        centre.addStretch(2)
        racine.addLayout(centre, 1)
        racine.addSpacing(140)  # équilibre visuel avec la colonne de gauche

    def _demander_retrait(self) -> None:
        self.retrait_demande.emit()
        # >>> ICI : mettre le protocole de retrait de la voiture


ORDRE_ETATS = [LIBRE, OCCUPE, RESERVE, MAINTENANCE]


def _style_bouton_etat(etat: str) -> str:
    fond, bord, texte = COULEURS[etat]
    return (f"QPushButton {{ background: {fond}; color: {texte};"
            f" border: 3px solid {bord}; border-radius: 12px;"
            f" font-weight: bold; }}"
            f"QPushButton:pressed {{ background: {bord}; }}")


class _PageTest(QWidget):
    """QWidget qui rafraîchit les boutons d'état chaque fois qu'il s'affiche."""

    def __init__(self):
        super().__init__()
        self.a_l_affichage = lambda: None

    def showEvent(self, event):
        super().showEvent(event)
        self.a_l_affichage()


def creer_page_test(interface, page_parking) -> QWidget:
    """Page de test : luminosité + contrôle de l'état des 14 emplacements."""
    page = _PageTest()
    racine = QHBoxLayout(page)
    racine.setContentsMargins(20, 20, 20, 20)

    # --- Colonne gauche : retour ---
    retour = QPushButton("←\nRetour")
    retour.setFixedSize(140, 140)
    retour.setStyleSheet(STYLE_RETOUR)
    retour.clicked.connect(lambda: interface.afficher_page("reservation"))
    gauche = QVBoxLayout()
    gauche.addWidget(retour)
    gauche.addStretch(1)
    racine.addLayout(gauche)

    # --- Centre : titre + 14 boutons d'état ---
    titre = QLabel("Page de test")
    titre.setStyleSheet("font-size: 40px; font-weight: bold;")
    titre.setAlignment(Qt.AlignmentFlag.AlignCenter)

    aide = QLabel("Touchez un emplacement pour changer son état")
    aide.setStyleSheet("font-size: 20px; color: #8fa6c4;")
    aide.setAlignment(Qt.AlignmentFlag.AlignCenter)

    boutons: dict[int, QPushButton] = {}
    grille = QGridLayout()
    grille.setSpacing(8)
    for c in range(7):
        grille.setColumnStretch(c, 1)
    for r in range(2):
        grille.setRowStretch(r, 1)

    def rafraichir():
        for n, b in boutons.items():
            etat = page_parking.etat(n)
            b.setText(f"P{n}\n{LIBELLES[etat]}")
            b.setStyleSheet(_style_bouton_etat(etat))

    def etat_suivant(n: int):
        etat = page_parking.etat(n)
        suivant = ORDRE_ETATS[(ORDRE_ETATS.index(etat) + 1) % len(ORDRE_ETATS)]
        page_parking.definir_etat(n, suivant)
        rafraichir()

    def tout_libre():
        for n in boutons:
            page_parking.definir_etat(n, LIBRE)
        rafraichir()

    for i in range(14):
        n = i + 1
        b = BoutonTexteAjuste(taille_max=20)
        b.setMinimumHeight(80)
        b.clicked.connect(lambda _=False, n=n: etat_suivant(n))
        boutons[n] = b
        grille.addWidget(b, i // 7, i % 7)      # sans cette ligne, les boutons s'empilent

    bouton_libre = QPushButton("Tout remettre libre")
    bouton_libre.setStyleSheet("""
        QPushButton { background: #34495e; color: white; font-size: 22px;
                      font-weight: bold; border-radius: 16px; padding: 14px; }
        QPushButton:pressed { background: #22313f; }""")
    bouton_libre.clicked.connect(tout_libre)

    centre = QVBoxLayout()
    centre.addWidget(titre)
    centre.addWidget(aide)
    centre.addSpacing(10)
    centre.addLayout(grille, 1)
    centre.addSpacing(10)
    centre.addWidget(bouton_libre)
    racine.addLayout(centre, 1)

    page.a_l_affichage = rafraichir
    rafraichir()

    # --- Colonne droite : curseur de luminosité ---
    valeur = QLabel("100 %")
    valeur.setStyleSheet("font-size: 34px; font-weight: bold;")
    valeur.setAlignment(Qt.AlignmentFlag.AlignCenter)

    icone = QLabel("☀")
    icone.setStyleSheet("font-size: 44px;")
    icone.setAlignment(Qt.AlignmentFlag.AlignCenter)

    curseur = QSlider(Qt.Orientation.Vertical)
    curseur.setRange(LUMINOSITE_MIN, 100)
    curseur.setValue(interface.luminosite)
    curseur.setMinimumHeight(300)
    curseur.setFixedWidth(90)
    curseur.setStyleSheet("""
        QSlider::groove:vertical { width: 24px; background: #8fa6c4;
                                   border-radius: 12px; }
        QSlider::handle:vertical { background: #2f80ed; height: 70px;
                                   margin: 0 -23px; border-radius: 18px; }
        QSlider::handle:vertical:pressed { background: #1c5fc0; }
    """)

    def changer_luminosite(v: int):
        valeur.setText(f"{v} %")
        interface.definir_luminosite_ecran(v)

    curseur.valueChanged.connect(changer_luminosite)
    changer_luminosite(curseur.value())

    droite = QVBoxLayout()
    droite.addWidget(icone)
    droite.addWidget(curseur, 1, Qt.AlignmentFlag.AlignHCenter)
    droite.addWidget(valeur)
    racine.addLayout(droite)

    return page