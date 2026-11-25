"""Horloge du système.

Tous les modules demandent l'heure à un objet Horloge au lieu d'appeler
directement le module time. Les tests peuvent ainsi fournir une fausse
horloge et faire « passer » 60 secondes instantanément.
"""

import time


class Horloge:
    """Horloge réelle."""

    def maintenant(self) -> float:
        """Heure réelle en secondes (celle qui est sauvegardée)."""
        return time.time()

    def monotone(self) -> float:
        """Temps qui ne recule jamais (pour mesurer les délais)."""
        return time.monotonic()
