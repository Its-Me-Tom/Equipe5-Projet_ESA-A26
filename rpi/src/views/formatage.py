"""Mise en forme des valeurs affichées."""


def formater_argent(cents: int | None) -> str:
    """250 -> "2,50 $". Les montants restent des cents entiers partout ailleurs."""
    if cents is None:
        return "---"

    return f"{cents // 100},{cents % 100:02d} $"


def formater_transaction(numero: int | None) -> str:
    """123 -> "000123" (six chiffres, zéros à gauche)."""
    if numero is None:
        return "------"

    return f"{numero:06d}"
