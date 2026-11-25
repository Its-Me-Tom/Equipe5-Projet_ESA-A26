"""Contrôleur de la fenêtre de test du Raspberry Pi."""

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from src.controllers.service_rpi import ServiceRPi
from src.controllers.service_worker import ServiceWorker
from src.models import t12_gestion_retrait as etats_retrait
from src.views.formatage import formater_argent, formater_transaction

# Carte sans compte, pour les essais (valide en DECIMAL et en BRUT).
# Avec config.AJOUTER_CARTES_INCONNUES, la présenter lui crée un compte.
CARTE_INCONNUE = "0099999999"

# Couleur de fond d'une place selon son état (mêmes couleurs que les DEL)
COULEURS_PLACES = {
    "LIBRE": "#c8f7c5",         # vert
    "RESERVE": "#c5d8f7",       # bleu
    "OCCUPE": "#f7c5c5",        # rouge
    "MAINTENANCE": "#f7dcc5",   # orange
    "DEFAUT": "#f7f3a0",        # jaune
}

TEXTE_PRESENCE = {True: "présent", False: "absent", None: "inconnu"}
TEXTE_DEL = {True: "appliquée", False: "sans accusé", None: "en attente"}


class MainController:
    """Relie les boutons au service et affiche les états reçus du thread."""

    def __init__(self, view):
        self.view = view
        self.service = None
        self.worker = None

        try:
            self.service = ServiceRPi()
        except Exception as erreur:
            # Ex. comptes.csv absent ou transactions.csv illisible
            QMessageBox.critical(view, "Démarrage impossible", str(erreur))
            return

        self._remplir_liste_cartes()
        self._connecter_boutons()

        # Les boutons de simulation n'ont de sens qu'en simulation
        view.bouton_carte.setEnabled(self.service.lecteur.simuler)
        view.bouton_retirer_vehicule.setEnabled(self.service.can.simulate)

        self.worker = ServiceWorker(self.service)
        self.worker.instantane_pret.connect(self.afficher_instantane)
        self.worker.service_en_erreur.connect(self.afficher_erreur_service)
        self.worker.start()

    def _remplir_liste_cartes(self):
        """Liste les cartes de comptes.csv, plus une carte inconnue."""
        try:
            cartes = list(self.service.comptes.obtenir_comptes())
        except Exception:
            cartes = []

        self.view.liste_cartes.addItems(cartes + [CARTE_INCONNUE])

    def _connecter_boutons(self):
        view = self.view

        view.bouton_carte.clicked.connect(self.simuler_carte)
        view.bouton_depot.clicked.connect(self.simuler_depot)
        view.bouton_retirer_vehicule.clicked.connect(self.simuler_retrait_vehicule)
        view.bouton_demande.clicked.connect(self.demander_retrait)
        view.bouton_en_service.clicked.connect(self.remettre_en_service)

        view.page_tarification.confirmer_clique.connect(self.confirmer_retrait)
        view.page_tarification.annuler_clique.connect(self.annuler_retrait)
        view.page_paiement.annuler_clique.connect(self.annuler_retrait)

        for niveau, curseur in view.curseurs_eclairage.items():
            # sliderReleased : une seule commande CAN quand on lâche le curseur
            curseur.sliderReleased.connect(lambda n=niveau: self.regler_eclairage(n))
            curseur.valueChanged.connect(
                lambda valeur, n=niveau: view.etiquettes_eclairage[n].setText(str(valeur))
            )

    def shutdown(self):
        """Arrête le thread du service avant de fermer l'application."""
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)

    # ------------------------------------------------------------------
    # Boutons : chaque demande est déposée dans le thread du service
    # ------------------------------------------------------------------

    def simuler_carte(self):
        self.service.demander(self.service.simuler_carte, self.view.liste_cartes.currentText())

    def simuler_depot(self):
        self.service.demander(
            self.service.simuler_depot,
            self.view.liste_places.currentText(),
            self.view.liste_cartes.currentText(),
        )

    def simuler_retrait_vehicule(self):
        self.service.demander(self.service.simuler_retrait_vehicule)

    def remettre_en_service(self):
        self.service.demander(self.service.remettre_en_service)

    def regler_eclairage(self, niveau: int):
        intensite = self.view.curseurs_eclairage[niveau].value()
        self.service.demander(self.service.regler_eclairage, niveau, intensite)

    def demander_retrait(self):
        texte = self.view.saisie_transaction.text().strip()

        if not texte.isdigit():
            QMessageBox.warning(self.view, "Numéro invalide", "Entrez un numéro à six chiffres.")
            return

        self.service.demander(self.service.demander_retrait, int(texte))

    def confirmer_retrait(self):
        self.service.demander(self.service.retrait.confirmer_retrait_et_figer_montant)

    def annuler_retrait(self):
        self.service.demander(self.service.retrait.annuler)

    # ------------------------------------------------------------------
    # Affichage des états envoyés par le thread du service
    # ------------------------------------------------------------------

    def afficher_instantane(self, instantane: dict):
        view = self.view

        view.etiquette_service.setText(f"Borne : {instantane['etat_service']}")
        view.etiquette_liens.setText(
            f"MQTT : {'connecté' if instantane['mqtt_connecte'] else 'déconnecté'}"
            f"   CAN : {'ouvert' if instantane['can_connecte'] else 'fermé'}"
            f"   RFID : {'prêt' if instantane['rfid_disponible'] else 'absent'}"
        )

        if instantane["derniere_carte"] is not None:
            solde = instantane["dernier_solde"]
            if solde is None:
                detail = "carte inconnue"
            else:
                detail = f"{instantane['dernier_nom']}, {formater_argent(solde)}"
            view.etiquette_carte.setText(f"Dernière carte : {instantane['derniere_carte']} ({detail})")

        view.etiquette_retrait.setText(
            f"Retrait : {instantane['etat_retrait']} — {instantane['message_retrait']}"
        )
        view.etiquette_rampe.setText(f"IR devant la barrière : {TEXTE_PRESENCE[instantane['rampe']]}")

        self._afficher_pages(instantane)
        self._afficher_places(instantane)
        self._afficher_transactions(instantane["transactions"])

        for ligne in instantane["journal"]:
            view.texte_journal.appendPlainText(ligne)

    def _afficher_pages(self, instantane: dict):
        """Affiche la page de T04 qui correspond à l'état du retrait."""
        view = self.view
        etat = instantane["etat_retrait"]
        transaction = instantane["transaction"]

        if etat == etats_retrait.DEMANDE and instantane["cout"] is not None:
            view.page_tarification.afficher_tarification(
                transaction["id"], transaction["place"], instantane["tarif"],
                instantane["cout"]["duree_min"], instantane["cout"]["montant_cents"],
            )
            view.pages.setCurrentWidget(view.page_tarification)

        elif etat == etats_retrait.PAIEMENT:
            view.page_paiement.afficher_paiement(
                transaction["montant_fige"], instantane["secondes_restantes"],
                instantane["delai_paiement"],
            )
            view.page_paiement.afficher_resultat(instantane["message_retrait"])
            view.pages.setCurrentWidget(view.page_paiement)

        else:
            view.pages.setCurrentWidget(view.page_vide)

    def _afficher_places(self, instantane: dict):
        tableau = self.view.tableau_places

        for ligne, (nom, etat) in enumerate(instantane["places"].items()):
            valeurs = [
                nom,
                etat,
                TEXTE_PRESENCE[instantane["presences"][nom]],
                TEXTE_DEL[instantane["del_confirmees"].get(nom)],
            ]

            for colonne, valeur in enumerate(valeurs):
                case = QTableWidgetItem(valeur)
                case.setBackground(QColor(COULEURS_PLACES.get(etat, "#ffffff")))
                case.setForeground(QColor("#000000"))
                tableau.setItem(ligne, colonne, case)

    def _afficher_transactions(self, transactions: list):
        tableau = self.view.tableau_transactions
        tableau.setRowCount(len(transactions))

        for ligne, transaction in enumerate(transactions):
            valeurs = [
                formater_transaction(transaction["id"]),
                transaction["place"],
                transaction["etat"],
                formater_argent(transaction["montant_fige"]),
            ]

            for colonne, valeur in enumerate(valeurs):
                tableau.setItem(ligne, colonne, QTableWidgetItem(valeur))

    def afficher_erreur_service(self, erreur: str):
        QMessageBox.critical(self.view, "Erreur du service", erreur)
