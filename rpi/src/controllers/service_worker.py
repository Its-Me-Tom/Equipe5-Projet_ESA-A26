"""Thread qui fait tourner le service sans bloquer l'interface graphique
(même principe que le TestWorker de l'application d'exemple)."""

import time

from PyQt6.QtCore import QThread, pyqtSignal

from src import config


class ServiceWorker(QThread):
    """Exécute la boucle du ServiceRPi dans un thread séparé.

    Le thread ne touche jamais aux widgets : il envoie un instantané
    (copie des états) à l'interface par un signal Qt.
    """

    instantane_pret = pyqtSignal(dict)    # états à afficher
    service_en_erreur = pyqtSignal(str)   # erreur inattendue du service

    def __init__(self, service):
        super().__init__()

        self.service = service
        self._arreter = False

    def stop(self):
        """Demande l'arrêt : la boucle se termine à son prochain tour."""
        self._arreter = True

    def run(self):
        try:
            self.service.demarrer()
            prochain_affichage = 0.0

            while not self._arreter:
                self.service.executer_tour()

                if time.monotonic() >= prochain_affichage:
                    prochain_affichage = time.monotonic() + config.PERIODE_AFFICHAGE_S
                    self.instantane_pret.emit(self.service.instantane())

                # Attente dans le thread du service, jamais dans celui de
                # l'interface : les machines à états restent non bloquantes.
                time.sleep(config.PERIODE_BOUCLE_S)

        except Exception as erreur:
            self.service_en_erreur.emit(str(erreur))

        finally:
            self.service.arreter()
