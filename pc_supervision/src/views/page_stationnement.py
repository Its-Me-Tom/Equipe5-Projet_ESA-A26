"""Page Stationnement : les 14 places avec leur témoin de couleur.

Le PC affiche les états transmis par le Raspberry Pi; il ne modifie
jamais une place lui-même.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src import config

TEXTE_PRESENCE = {True: "véhicule présent", False: "aucun véhicule", None: "IR inconnu"}

TAILLE_TEMOIN = 56     # diamètre d'un témoin, en pixels


class PageStationnement(QWidget):
    """Deux rangées de sept témoins : 1er étage et 2e étage."""

    def __init__(self):
        super().__init__()

        self._temoins = {}       # nom de place -> (témoin, texte)
        self._etats = {}         # nom de place -> état logique
        self._allume = True

        disposition = QVBoxLayout(self)

        grille = QGridLayout()

        for niveau in (2, 1):                 # le 2e étage est affiché en haut
            ligne = 0 if niveau == 2 else 1
            titre = QLabel(f"Étage {niveau}")
            titre.setStyleSheet("font-weight: bold;")
            grille.addWidget(titre, ligne, 0)

            for angle in range(1, 8):
                nom = f"E{niveau}.{angle}"
                grille.addWidget(self._construire_place(nom), ligne, angle)

        disposition.addLayout(grille)

        self.etiquette_rampe = QLabel("Zone devant la barrière : ---")
        disposition.addWidget(self.etiquette_rampe)

        disposition.addLayout(self._construire_legende())
        disposition.addStretch()

        # Clignotement des places en DEFAUT (jaune clignotant)
        self._minuterie = QTimer(self)
        self._minuterie.timeout.connect(self._clignoter)
        self._minuterie.start(config.PERIODE_CLIGNOTEMENT_MS)

    def _construire_place(self, nom: str) -> QWidget:
        """Un témoin rond avec le nom de la place et son état en texte."""
        widget = QWidget()
        disposition = QVBoxLayout(widget)

        temoin = QLabel(nom)
        temoin.setFixedSize(TAILLE_TEMOIN, TAILLE_TEMOIN)
        temoin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # L'état est aussi écrit : la couleur n'est jamais la seule information
        texte = QLabel("---")
        texte.setAlignment(Qt.AlignmentFlag.AlignCenter)

        disposition.addWidget(temoin, alignment=Qt.AlignmentFlag.AlignCenter)
        disposition.addWidget(texte)

        self._temoins[nom] = (temoin, texte)
        self._peindre(nom, config.COULEUR_INCONNUE)

        return widget

    @staticmethod
    def _construire_legende() -> QHBoxLayout:
        legende = QHBoxLayout()

        for etat, couleur in config.COULEURS_PLACES.items():
            exemple = QLabel(f"  {etat}  ")
            exemple.setStyleSheet(f"background-color: {couleur}; color: black; border-radius: 4px;")
            legende.addWidget(exemple)

        legende.addStretch()
        return legende

    def _peindre(self, nom: str, couleur: str):
        temoin, texte = self._temoins[nom]
        temoin.setStyleSheet(
            f"background-color: {couleur}; color: black; font-weight: bold;"
            f"border-radius: {TAILLE_TEMOIN // 2}px; border: 1px solid #424242;"
        )

    def afficher_places(self, places: list, rampe):
        """Affiche les états reçus du Raspberry Pi."""
        for place in places:
            nom = place["place"]

            if nom not in self._temoins:
                continue

            self._etats[nom] = place["etat"]
            self._temoins[nom][1].setText(f"{place['etat']}\n{TEXTE_PRESENCE[place['presence']]}")
            self._peindre(nom, config.COULEURS_PLACES.get(place["etat"], config.COULEUR_INCONNUE))

        self.etiquette_rampe.setText(f"Zone devant la barrière : {TEXTE_PRESENCE[rampe]}")

    def _clignoter(self):
        """Fait clignoter seulement les places en DEFAUT."""
        self._allume = not self._allume

        for nom, etat in self._etats.items():
            if etat == "DEFAUT":
                self._peindre(nom, config.COULEURS_PLACES["DEFAUT"] if self._allume else "#ffffff")
