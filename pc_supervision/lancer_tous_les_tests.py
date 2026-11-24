"""Lance tous les tests du PC un par un et affiche un résumé (optionnel).

    python lancer_tous_les_tests.py              les 4 tests du PC
    python lancer_tous_les_tests.py --details    affiche aussi tout ce que chaque test écrit

Chaque test est un script AUTONOME qu'on peut lancer seul : ce lanceur ne
fait que les exécuter l'un après l'autre. Rien n'est écrit sur le disque.
Un test dont l'interrupteur est à MATERIEL_REEL = True est sauté : il
demande des actions à l'opérateur, il faut le lancer seul.
"""

import re
import subprocess
import sys
from pathlib import Path

dossier = Path(__file__).resolve().parent
arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
details = "--details" in sys.argv

# Seulement les tests numérotés : test_t02_01_..., test_t13_10_...
tests = sorted(test for test in dossier.glob("test_pc*.py") if re.match(r"test_pc_\d\d_", test.name))
echecs, sautes = [], []

for test in tests:
    if re.search(r"^MATERIEL_REEL = True", test.read_text(encoding="utf-8"), flags=re.M):
        print(f"SAUTÉ    {test.name} (MATERIEL_REEL = True : le lancer seul)")
        sautes.append(test.name)
        continue

    resultat = subprocess.run([sys.executable, test.name], cwd=dossier, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
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

lances = len(tests) - len(sautes)
print(f"\n{lances - len(echecs)} tests réussis sur {lances}" + (f" ({len(sautes)} sautés)" if sautes else ""))
sys.exit(1 if echecs else 0)
