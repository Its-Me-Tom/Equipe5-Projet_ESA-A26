# Projet STM32 — Bas, Haut et Borne

Les trois projets `STM32_Bas`, `STM32_Haut` et `STM32_Borne` ont le même
code et le même `.ioc`. La seule différence est la ligne
`#define CARTE ...` dans `Core/Inc/carte_config.h`.

## Qui fait quoi

| Fichier | Partie | Responsable |
|---|---|---|
| `carte_config.h` | Identité de la carte et réglages de chaque tâche, une section par tâche | Chacun dans sa section |
| `protocole_can.h` | Identifiants du protocole CAN v1.6 | Commun, ne pas modifier seul |
| `can_esa.c/.h` | Gestionnaire CAN unique : filtres, réception, envoi, heartbeat | Commun |
| `apa102.c/.h` | Pilote de la barre de 15 DEL APA102 | T07, Tom |
| `t07_eclairage.c/.h` | DEL des places et éclairage blanc | T07, Tom |
| `main.c` | Appels `..._Init()` et `..._Task()` dans les zones USER CODE | Chacun ajoute sa ligne |

## Ajouter une tâche

1. Créer `tXX_nom.c` et `tXX_nom.h` dans `Core/Src` et `Core/Inc`.
2. Ajouter sa section dans `carte_config.h`.
3. Dans `can_esa.c`, ajouter ses ID dans `ids_acceptes[]` et sa fonction
   de réception dans `recepteurs[]` (les deux « POINT DE BRANCHEMENT »).
4. Dans `main.c`, appeler `XX_Init()` avant `CanEsa_Init()` et `XX_Task()`
   dans la boucle.

Règles : un seul gestionnaire CAN par carte, rien de long sous
interruption, pas de `HAL_Delay()` dans la boucle principale.

## T07 en bref

- Barre de DEL : SPI1 (PA5 = CLOCK, PA7 = DATA) par le PMOD type 2 et le
  PCB-11. PE3 (CS de l'accéléromètre) reste haute. PE0 (OE du PCB-11) ne
  doit jamais être mise à 0.
- DEL paires : places. DEL impaires : éclairage blanc.
- Bas : places 1-7, niveau 0. Haut : places 8-14, niveau 1.
  Borne : niveau 2, DEL paires en décoration (`T07_DISCO`).
- `T07_MODE_DEMO = 1` dans `carte_config.h` : démonstration sans RPi.
- DEL de la Discovery (sauf sur le Haut) : vert = heartbeat,
  orange = RPi présent, rouge = erreur CAN.
