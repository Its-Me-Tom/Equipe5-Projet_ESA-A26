import sys

from PyQt6.QtWidgets import QApplication

from src import config
from src.views.main_window import MainWindow
from src.controllers.main_controller import MainController


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    controller = MainController(window)

    app.aboutToQuit.connect(controller.shutdown)

    if config.PLEIN_ECRAN:
        window.showFullScreen()     # tout l'écran, sans barre de titre (F11 ou Échap pour sortir)
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
