import sys

from PyQt6.QtWidgets import QApplication

from src.views.main_window import MainWindow
from src.controllers.main_controller import MainController


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    controller = MainController(window)

    # Arrêter proprement le thread du service à la fermeture
    app.aboutToQuit.connect(controller.shutdown)

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
