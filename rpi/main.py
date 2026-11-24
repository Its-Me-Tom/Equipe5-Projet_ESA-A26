"""Lance la fenêtre T01 pour test / future intégration.

    python3 main.py                 fenêtre 1024x600
    python3 main.py --plein-ecran   plein écran (Raspberry Pi)
    python3 main.py --veille 10     délai de veille en secondes
"""
import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from models.main_interface import InterfacePrincipale
from models.page_parking import PageParking
from models.pages_annexes import PageRetrait, creer_page_test


def main():
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--plein-ecran", action="store_true")
    parseur.add_argument("--veille", type=float, default=30)
    args = parseur.parse_args()

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)

    interface = InterfacePrincipale(delai_veille_s=args.veille)

    page_parking = PageParking()
    page_retrait = PageRetrait()
    page_parking.navigation_demandee.connect(interface.afficher_page)
    page_retrait.navigation_demandee.connect(interface.afficher_page)

    interface.enregistrer_page("reservation", page_parking)  # cible du bouton « Commencer »
    interface.enregistrer_page("retrait", page_retrait)
    interface.enregistrer_page("test", creer_page_test(interface, page_parking))

    # Points d'intégration futurs :
    #   page_parking.definir_etats({1: OCCUPE, 2: RESERVE, ...})   (voir page_parking.py)
    #   interface.enregistrer_page("paiement", PageT04(...))
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