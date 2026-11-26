"""Page Stationnement : les 14 places avec leur témoin de couleur, le client
qui tient chaque place et l'historique des stationnements.

Le PC affiche les états transmis par le Raspberry Pi; il ne modifie
jamais une place lui-même.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from src import config

TEXTE_PRESENCE = {True: "véhicule présent", False: "aucun véhicule", None: "IR inconnu"}

TAILLE_TEMOIN = 56     # côté d'un témoin carré, en pixels
ARRONDI_TEMOIN = 8     # coins arrondis, en pixels (0 = coins droits, 28 = cercle)


class PageStationnement(QWidget):
    """Deux rangées de sept témoins : 1er étage et 2e étage."""

    def __init__(self):
        super().__init__()

        self._temoins = {}       # nom de place -> (témoin, texte)
        self._etats = {}         # nom de place -> état logique
        self._presences = {}     # nom de place -> True / False / None (IR)
        self._occupants = {}     # nom de place -> (nom court, description complète)
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

        # Historique des stationnements, dans l'espace sous la légende
        titre_historique = QLabel("Historique des stationnements")
        titre_historique.setStyleSheet("font-weight: bold;")
        disposition.addWidget(titre_historique)

        self.texte_historique = QPlainTextEdit()
        self.texte_historique.setReadOnly(True)
        self.texte_historique.setMaximumBlockCount(500)     # garde les 500 derniers événements
        self.texte_historique.setPlaceholderText("Aucun événement pour l'instant.")
        disposition.addWidget(self.texte_historique, stretch=1)

        # Clignotement des places en DEFAUT (jaune clignotant)
        self._minuterie = QTimer(self)
        self._minuterie.timeout.connect(self._clignoter)
        self._minuterie.start(config.PERIODE_CLIGNOTEMENT_MS)

    def _construire_place(self, nom: str) -> QWidget:
        """Un témoin carré avec le nom de la place et son état en texte."""
        widget = QWidget()
        disposition = QVBoxLayout(widget)

        temoin = QLabel(nom)
        temoin.setFixedSize(TAILLE_TEMOIN, TAILLE_TEMOIN)
        temoin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # L'état est aussi écrit : la couleur n'est jamais la seule information
        texte = QLabel("---")
        texte.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texte.setWordWrap(True)      # un nom long passe à la ligne au lieu d'élargir la grille

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
            f"border-radius: {ARRONDI_TEMOIN}px; border: 1px solid #424242;"
        )

    def afficher_places(self, places: list, rampe):
        """Affiche les états reçus du Raspberry Pi."""
        for place in places:
            nom = place["place"]

            if nom not in self._temoins:
                continue

            self._etats[nom] = place["etat"]
            self._presences[nom] = place["presence"]
            self._ecrire_texte(nom)
            self._peindre(nom, config.COULEURS_PLACES.get(place["etat"], config.COULEUR_INCONNUE))

        self.etiquette_rampe.setText(f"Zone devant la barrière : {TEXTE_PRESENCE[rampe]}")

    def afficher_occupants(self, occupants: dict):
        """Affiche le client de chaque place : {"E2.2": ("Thomas", "Thomas (0008580808)")}.

        Une place absente du dictionnaire n'a pas de client connu.
        """
        self._occupants = dict(occupants)

        for nom in self._temoins:
            if nom in self._etats:
                self._ecrire_texte(nom)

    def ajouter_historique(self, evenements: list):
        """Ajoute des événements (heure, texte) à l'historique, l'heure à gauche."""
        for heure, texte in evenements:
            self.texte_historique.appendPlainText(f"{heure}  {texte}")

    def _ecrire_texte(self, nom: str):
        """Texte sous le témoin : état, client (s'il est connu), présence IR."""
        temoin, texte = self._temoins[nom]
        lignes = [self._etats[nom]]
        occupant = self._occupants.get(nom)

        if occupant is not None:
            lignes.append(occupant[0])
            temoin.setToolTip(f"{nom} : {self._etats[nom]}, {occupant[1]}")
        else:
            temoin.setToolTip(f"{nom} : {self._etats[nom]}")

        lignes.append(TEXTE_PRESENCE.get(self._presences.get(nom), TEXTE_PRESENCE[None]))
        texte.setText("\n".join(lignes))

    def _clignoter(self):
        """Fait clignoter seulement les places en DEFAUT."""
        self._allume = not self._allume

        for nom, etat in self._etats.items():
            if etat == "DEFAUT":
                self._peindre(nom, config.COULEURS_PLACES["DEFAUT"] if self._allume else "#ffffff")