"""Exceptions métier des tâches T02, T04 et T07.

Elles permettent à l'appelant de distinguer la cause d'un refus.
Chaque exception a un code texte, repris dans les réponses MQTT.
"""


class ErreurEsa(Exception):
    """Classe de base des erreurs du projet."""

    code = "ERREUR"


# --- T02 : comptes ---

class CarteInconnue(ErreurEsa):
    """La carte n'a aucun compte dans comptes.csv."""

    code = "CARTE_INCONNUE"


class SoldeInsuffisant(ErreurEsa):
    """Le solde ne couvre pas la totalité du montant (aucun débit partiel)."""

    code = "SOLDE_INSUFFISANT"


class OperationRepetee(ErreurEsa):
    """Une opération avec le même identifiant a déjà été enregistrée."""

    code = "OPERATION_REPETEE"


class MontantInvalide(ErreurEsa):
    """Le montant n'est pas un entier strictement positif (en cents)."""

    code = "MONTANT_INVALIDE"


class ErreurFichier(ErreurEsa):
    """Fichier CSV absent, illisible ou au contenu incorrect."""

    code = "ERREUR_FICHIER"


# --- T04 : transactions ---

class PlaceInvalide(ErreurEsa):
    """La place n'existe pas (E1.1 à E2.7)."""

    code = "PLACE_INVALIDE"


class TransactionInexistante(ErreurEsa):
    """Aucune transaction ne porte ce numéro."""

    code = "TRANSACTION_INEXISTANTE"


class HorodatageInvalide(ErreurEsa):
    """Horodatage absent ou incohérent (ex. heure avant le début)."""

    code = "HORODATAGE_INVALIDE"


# --- T07 : DEL et éclairage ---

class ParametreInvalide(ErreurEsa):
    """Place, état, niveau ou intensité hors des valeurs permises."""

    code = "PARAMETRE_INVALIDE"
