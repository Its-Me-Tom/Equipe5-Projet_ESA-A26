"""Lance la fenêtre T01 pour test / future intégration.

    python3 main.py                 fenêtre 1024x600
    python3 main.py --plein-ecran   plein écran (Raspberry Pi)
    python3 main.py --veille 10     délai de veille en secondes
"""
import argparse
import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QVBoxLayout, QWidget)

from interface.main_interface import LUMINOSITE_MIN, InterfacePrincipale


def creer_page_fictive(interface) -> QWidget:
    """Remplace temporairement la page T03 (avec curseur de luminosité de test)."""
    page = QWidget()
    racine = QHBoxLayout(page)
    racine.setContentsMargins(20, 20, 20, 20)

    # --- Colonne gauche : bouton retour carré en haut à gauche ---
    retour = QPushButton("⌂\nAccueil")
    retour.setFixedSize(140, 140)
    retour.setStyleSheet("""
        QPushButton { background: #2f80ed; color: white; font-size: 26px;
                      font-weight: bold; border-radius: 20px; }
        QPushButton:pressed { background: #1c5fc0; }
    """)
    retour.clicked.connect(interface.afficher_accueil)
    gauche = QVBoxLayout()
    gauche.addWidget(retour)
    gauche.addStretch(1)
    racine.addLayout(gauche)

    # --- Centre : titre ---
    titre = QLabel("Page fictive (T03)")
    titre.setStyleSheet("font-size: 40px; font-weight: bold;")
    titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
    racine.addWidget(titre, 1)

    # --- Colonne droite : curseur de luminosité (vertical) ---
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
    changer_luminosite(curseur.value())  # synchronise l'accueil au démarrage

    droite = QVBoxLayout()
    droite.addWidget(icone)
    droite.addWidget(curseur, 1, Qt.AlignmentFlag.AlignHCenter)
    droite.addWidget(valeur)
    racine.addLayout(droite)

    return page


def main():
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--plein-ecran", action="store_true")
    parseur.add_argument("--veille", type=float, default=30)
    args = parseur.parse_args()

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)

    interface = InterfacePrincipale(delai_veille_s=args.veille)
    interface.enregistrer_page("reservation", creer_page_fictive(interface))

    # Points d'intégration futurs :
    #   interface.enregistrer_page("paiement", PageT04(...))
    #   interface.signaler_presence(radar.lire_presence())
    #   interface.definir_transaction_active(True / False)
    #   interface.definir_luminosite_auto(True)
    #   interface.signaler_lumiere_ambiante(capteur.lire_lux())
    #   interface.page_accueil.definir_can_disponible(True / False)

    if args.plein_ecran:
        interface.showFullScreen()
    else:
        interface.resize(1024, 600)
        interface.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()