"""Page Commandes : état général, commandes générales et anomalies."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src import config
from src.views.formatage import formater_heure

STYLE_ARRET = "background-color: #c62828; color: white; font-weight: bold; padding: 10px;"


class PageCommandes(QWidget):
    """Envoi des quatre commandes générales et affichage de leur effet."""

    commande_cliquee = pyqtSignal(str)     # nom de la commande

    def __init__(self):
        super().__init__()

        disposition = QVBoxLayout(self)

        # --- État général publié par le Raspberry Pi ---
        self.etiquette_etat = QLabel("INCONNU")
        self.etiquette_etat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disposition.addWidget(self.etiquette_etat)

        self.etiquette_detail = QLabel("")
        self.etiquette_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disposition.addWidget(self.etiquette_detail)

        # --- Commandes générales ---
        ligne_service = QHBoxLayout()
        self.bouton_hors_service = QPushButton("Mettre hors service")
        self.bouton_en_service = QPushButton("Remettre en service")
        ligne_service.addWidget(self.bouton_hors_service)
        ligne_service.addWidget(self.bouton_en_service)
        disposition.addLayout(ligne_service)

        # Arrêt logiciel : ce n'est pas un arrêt d'urgence matériel certifié
        self.bouton_arret = QPushButton("ARRÊT IMMÉDIAT (logiciel)")
        self.bouton_arret.setStyleSheet(STYLE_ARRET)
        disposition.addWidget(self.bouton_arret)

        ligne_reinitialisation = QHBoxLayout()
        self.case_intervention = QCheckBox(
            "Intervention manuelle faite (défauts vérifiés, bras rétracté, références valides)"
        )
        self.bouton_reinitialiser = QPushButton("Réinitialiser")
        ligne_reinitialisation.addWidget(self.case_intervention)
        ligne_reinitialisation.addWidget(self.bouton_reinitialiser)
        disposition.addLayout(ligne_reinitialisation)

        self.etiquette_reponse = QLabel("Réponse : ---")
        self.etiquette_reponse.setWordWrap(True)
        disposition.addWidget(self.etiquette_reponse)

        # --- Anomalies actives ---
        disposition.addWidget(QLabel("Anomalies actives"))
        self.tableau_anomalies = QTableWidget()
        self.tableau_anomalies.setColumnCount(6)
        self.tableau_anomalies.setHorizontalHeaderLabels(
            ["Heure", "Tâche", "Code", "Message", "Place", "Critique"]
        )
        self.tableau_anomalies.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tableau_anomalies.verticalHeader().setVisible(False)

        # Colonnes ajustées à leur contenu; le message prend le reste
        entete = self.tableau_anomalies.horizontalHeader()
        entete.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        entete.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        disposition.addWidget(self.tableau_anomalies)

        self.bouton_hors_service.clicked.connect(lambda: self.commande_cliquee.emit("METTRE_HORS_SERVICE"))
        self.bouton_en_service.clicked.connect(lambda: self.commande_cliquee.emit("REMETTRE_EN_SERVICE"))
        self.bouton_arret.clicked.connect(lambda: self.commande_cliquee.emit("ARRET_IMMEDIAT"))
        self.bouton_reinitialiser.clicked.connect(self._reinitialiser_clique)

        self.afficher_etat("INCONNU", "", "")

    def _reinitialiser_clique(self):
        """Clic sur « Réinitialiser »."""
        # emit() appelle le contrôleur tout de suite : il lit la case et
        # envoie la commande AVANT que la ligne suivante s'exécute.
        self.commande_cliquee.emit("REINITIALISER")

        # Toujours décocher après le clic, que la commande ait marché ou non :
        # l'intervention doit être reconfirmée avant chaque essai.
        self.case_intervention.setChecked(False)

    def intervention_confirmee(self) -> bool:
        return self.case_intervention.isChecked()

    def afficher_etat(self, etat_service: str, etat_retrait: str, message: str):
        """Affiche l'état général publié par le Raspberry Pi."""
        couleur = config.COULEURS_SERVICE.get(etat_service, config.COULEUR_INCONNUE)

        self.etiquette_etat.setText(etat_service)
        self.etiquette_etat.setStyleSheet(
            f"background-color: {couleur}; color: white; font-size: 22px;"
            "font-weight: bold; padding: 12px; border-radius: 6px;"
        )

        if etat_retrait:
            self.etiquette_detail.setText(f"Retrait : {etat_retrait} — {message}")

    def afficher_reponse(self, texte: str):
        self.etiquette_reponse.setText(f"Réponse : {texte}")

    def afficher_anomalies(self, anomalies: list):
        tableau = self.tableau_anomalies
        tableau.setRowCount(len(anomalies))

        for ligne, anomalie in enumerate(anomalies):
            valeurs = [
                formater_heure(anomalie.get("horodatage")),
                anomalie.get("tache", ""),
                anomalie["code"],
                anomalie["message"],
                anomalie.get("place") or "",
                "oui" if anomalie.get("critique") else "non",
            ]

            for colonne, valeur in enumerate(valeurs):
                tableau.setItem(ligne, colonne, QTableWidgetItem(valeur))