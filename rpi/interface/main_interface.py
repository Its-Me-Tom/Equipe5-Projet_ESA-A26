"""T01 - Interface principale : fenêtre unique, navigation et veille logicielle.

Section 4 du document T01 v1.1. Une seule QApplication : les pages de T03/T04/T05
sont de simples QWidget enregistrés ici.

Luminosité : un voile noir semi-transparent assombrit l'affichage. Même
comportement sur PC et sur Raspberry Pi (aucune dépendance au matériel).
"""
import logging
import math

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget

from .page_accueil import PageAccueil

log = logging.getLogger("t01")

DELAI_VEILLE_S = 30  # configurable

# --- Luminosité ---
LUMINOSITE_MIN = 10   # %, évite un écran complètement noir
LUX_MIN = 5           # en dessous : luminosité minimale (nuit)
LUX_MAX = 1000        # au-dessus : 100 % (plein jour)
LISSAGE = 0.2         # 0..1 : plus petit = plus doux
SEUIL_CHANGEMENT = 3  # % minimum d'écart avant de changer l'écran


class _FiltreTactile(QObject):
    """Signale chaque toucher à l'interface, sans jamais consommer l'événement."""

    def __init__(self, interface):
        super().__init__(interface)
        self._interface = interface

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseButtonPress,
                            QEvent.Type.TouchBegin):
            self._interface.signaler_activite()
        return False


class _VoileLuminosite(QWidget):
    """Voile noir semi-transparent par-dessus toute la fenêtre.
    Transparent aux clics : les touchers passent au travers."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._alpha = 0
        self.hide()

    def definir(self, pourcentage: int) -> None:
        self._alpha = round(255 * (100 - pourcentage) / 100)
        self.setVisible(self._alpha > 0)
        self.raise_()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, self._alpha))


class InterfacePrincipale(QMainWindow):
    def __init__(self, delai_veille_s: float = DELAI_VEILLE_S):
        super().__init__()
        self.setWindowTitle("ESA Parking")

        self._delai_ms = int(delai_veille_s * 1000)
        self._transaction_active = False
        self._en_veille = False
        self._page_courante = "accueil"
        self._pages: dict[str, QWidget] = {}

        # Pile de pages : page noire de veille + pages enregistrées.
        self._pile = QStackedWidget()
        self.setCentralWidget(self._pile)
        self._page_veille = QWidget()
        self._page_veille.setStyleSheet("background:black;")
        self._pile.addWidget(self._page_veille)

        # Luminosité : voile par-dessus toute la fenêtre.
        self._luminosite = 100
        self._auto = False
        self._lux_lisse = None
        self._voile = _VoileLuminosite(self)

        # Page d'accueil (fournie par T01).
        self.page_accueil = PageAccueil()
        self.page_accueil.navigation_demandee.connect(self.afficher_page)
        self.enregistrer_page("accueil", self.page_accueil)

        # Minuterie de veille et détection du tactile.
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.timeout.connect(self._delai_ecoule)
        QApplication.instance().installEventFilter(_FiltreTactile(self))
        self._minuterie.start(self._delai_ms)

    # ------------------------------------------------------------------
    # API publique (section 4.2)
    # ------------------------------------------------------------------
    def enregistrer_page(self, nom: str, page: QWidget) -> None:
        """Ajoute (ou remplace) une page. `page` doit être un QWidget."""
        if not isinstance(page, QWidget):
            log.warning("enregistrer_page('%s') : QWidget attendu, ignoré", nom)
            return
        ancienne = self._pages.get(nom)
        if ancienne is not None:
            self._pile.removeWidget(ancienne)
        self._pages[nom] = page
        self._pile.addWidget(page)
        if nom == self._page_courante and not self._en_veille:
            self._pile.setCurrentWidget(page)

    def afficher_page(self, nom: str) -> None:
        """Affiche la page `nom`. Un nom inconnu est signalé mais sans effet."""
        if nom not in self._pages:
            log.warning("Page inconnue : '%s' (ignorée)", nom)
            return
        self._page_courante = nom
        self.signaler_activite()  # affiche la page et remet le délai à zéro

    def afficher_accueil(self) -> None:
        self.afficher_page("accueil")

    def definir_transaction_active(self, active: bool) -> None:
        """Fournie par les modules de transaction : bloque la mise en veille."""
        self._transaction_active = bool(active)
        self.signaler_activite()

    def signaler_activite(self) -> None:
        """Toucher ou présence radar : réveille l'écran et relance le délai."""
        self._en_veille = False
        self.unsetCursor()
        self._pile.setCurrentWidget(self._pages[self._page_courante])
        self._minuterie.start(self._delai_ms)

    # ------------------------------------------------------------------
    # Ajouts utiles à l'intégration
    # ------------------------------------------------------------------
    def signaler_presence(self, presente: bool) -> None:
        """À appeler avec le résultat de RadarPresence.lire_presence()."""
        if presente:
            self.signaler_activite()

    def definir_delai_veille(self, secondes: float) -> None:
        self._delai_ms = int(secondes * 1000)
        self._minuterie.start(self._delai_ms)

    @property
    def en_veille(self) -> bool:
        return self._en_veille

    @property
    def transaction_active(self) -> bool:
        return self._transaction_active

    # ------------------------------------------------------------------
    # Luminosité (voile logiciel : identique sur PC et Raspberry Pi)
    # ------------------------------------------------------------------
    def definir_luminosite_ecran(self, pourcentage: float) -> int:
        """Règle la luminosité (LUMINOSITE_MIN..100 %) et met à jour l'accueil.

        Retourne la valeur réellement appliquée.
        """
        pct = max(LUMINOSITE_MIN, min(100, round(pourcentage)))
        self._luminosite = pct
        self._voile.definir(pct)
        self.page_accueil.definir_luminosite(pct)
        return pct

    @property
    def luminosite(self) -> int:
        return self._luminosite

    # --- Mode automatique (capteur de lumière ambiante) ---
    def definir_luminosite_auto(self, active: bool) -> None:
        """Active/désactive le réglage automatique par capteur."""
        self._auto = bool(active)
        self._lux_lisse = None

    @property
    def luminosite_auto(self) -> bool:
        return self._auto

    def signaler_lumiere_ambiante(self, lux) -> None:
        """À appeler avec la lecture du capteur (en lux). None = lecture échouée.

        Sans effet si le mode auto est désactivé. Ne réveille pas l'écran.
        """
        if not self._auto or lux is None:
            return
        lux = max(0.0, float(lux))
        if self._lux_lisse is None:
            self._lux_lisse = lux
        else:  # moyenne mobile : évite le clignotement si la lecture saute
            self._lux_lisse += LISSAGE * (lux - self._lux_lisse)

        cible = self._lux_vers_pourcentage(self._lux_lisse)
        if abs(cible - self._luminosite) >= SEUIL_CHANGEMENT:  # hystérésis
            self.definir_luminosite_ecran(cible)

    @staticmethod
    def _lux_vers_pourcentage(lux: float) -> int:
        """Échelle logarithmique : l'œil perçoit la lumière ainsi."""
        lux = max(LUX_MIN, min(LUX_MAX, lux))
        ratio = math.log(lux / LUX_MIN) / math.log(LUX_MAX / LUX_MIN)
        return round(LUMINOSITE_MIN + ratio * (100 - LUMINOSITE_MIN))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._voile.setGeometry(self.rect())
        self._voile.raise_()

    # ------------------------------------------------------------------
    # Veille
    # ------------------------------------------------------------------
    def _delai_ecoule(self):
        if self._transaction_active:        # jamais de veille en transaction
            self._minuterie.start(self._delai_ms)
            return
        self._en_veille = True
        self._pile.setCurrentWidget(self._page_veille)
        self.setCursor(Qt.CursorShape.BlankCursor)