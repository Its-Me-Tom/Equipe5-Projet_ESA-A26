"""Mise en forme des valeurs affichées."""

from datetime import datetime


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


def formater_heure(horodatage: float | None) -> str:
    """Heure en secondes -> "2026-11-16 15:07:42"."""
    if horodatage is None:
        return "---"

    return datetime.fromtimestamp(horodatage).strftime("%Y-%m-%d %H:%M:%S")
