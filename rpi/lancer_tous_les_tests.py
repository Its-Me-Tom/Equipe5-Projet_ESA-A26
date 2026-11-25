"""Lance tous les tests un par un EN SIMULATION et affiche un résumé (optionnel).

    python3 lancer_tous_les_tests.py             tous les tests (T02, T04, T07, T12, T13)
    python3 lancer_tous_les_tests.py t07         seulement les tests de T07
    python3 lancer_tous_les_tests.py t07 --details   affiche aussi tout ce que chaque test écrit

Chaque test est un script AUTONOME qu'on peut lancer seul : ce lanceur ne
fait que les exécuter l'un après l'autre. Rien n'est écrit sur le disque.

Les tests commencent avec MATERIEL_REEL = True (vrai matériel) : lancés à
la main, ils utilisent le matériel. Ce lanceur, lui, les fait tous tourner
en simulation (variable ESA_SIMULATION=1) sans modifier les fichiers : il
sert à vérifier vite que le code n'a rien cassé.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

dossier = Path(__file__).resolve().parent
arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
details = "--details" in sys.argv
tache = arguments[0].lower() if arguments else "t"

# Seulement les tests numérotés : test_t02_01_..., test_t13_10_...
tests = sorted(test for test in dossier.glob(f"test_{tache}*.py") if re.match(r"test_t\d\d_\d\d_", test.name))
echecs = []
environnement = dict(os.environ, ESA_SIMULATION="1")     # force MATERIEL_REEL = False dans chaque test
print("Mode : SIMULATION forcée (pour le vrai matériel, lancer chaque test seul)\n")

for test in tests:
    resultat = subprocess.run([sys.executable, test.name], cwd=dossier, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=environnement)
    bilan = next((ligne for ligne in resultat.stdout.splitlines() if ligne.startswith("RÉSULTAT")), "")

    if details:
        print(resultat.stdout + resultat.stderr)

    if resultat.returncode == 0:
        print(f"RÉUSSI   {test.name}   {bilan.replace('RÉSULTAT : RÉUSSI — ', '')}")
    else:
        print(f"ÉCHOUÉ   {test.name}")
        echecs.append(test.name)
        for ligne in (resultat.stdout + resultat.stderr).splitlines():
            if "ÉCHEC" in ligne or "Error" in ligne or "IMPOSSIBLE" in ligne or "attendu" in ligne or "obtenu" in ligne:
                print(f"         {ligne.strip()}")

print(f"\n{len(tests) - len(echecs)} tests réussis sur {len(tests)}")
sys.exit(1 if echecs else 0)
