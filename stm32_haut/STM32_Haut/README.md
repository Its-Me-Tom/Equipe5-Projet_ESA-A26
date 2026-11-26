# Projet STM32 — Bas, Haut et Borne

Les trois projets `STM32_Bas`, `STM32_Haut` et `STM32_Borne` ont le même
code et le même `.ioc`. La seule différence est la ligne
`#define CARTE ...` dans `Core/Commun/carte_config.h`.

## Arborescence

Même organisation que le projet LitDeClous : les pilotes de matériel dans
`Drivers/BSP/<Nom>/`, le code de l'application dans `Core/`.

```
STM32_Xxx/
├── Core/
│   ├── Inc/ Src/ Startup/      Généré par CubeMX. Seul main.c est modifié,
│   │                           dans les zones USER CODE.
│   ├── Commun/                 PARTIE COMMUNE (toute l'équipe)
│   │   ├── carte_config.h      Choix de la carte + une section par tâche
│   │   ├── protocole_can.h     Identifiants du protocole CAN v1.6
│   │   └── can_esa.c/.h        Gestionnaire CAN unique, heartbeat
│   └── Taches/                 UN DOSSIER PAR TÂCHE
│       └── T07_Eclairage/      T07, Tom : DEL des places et éclairage
│           └── t07_eclairage.c/.h
└── Drivers/
    ├── BSP/                    PILOTES DE MATÉRIEL (un dossier par composant)
    │   └── APA102/             T07, Tom : barre de 15 DEL APA102
    │       └── apa102.c/.h
    ├── CMSIS/                  ST, ne pas modifier
    └── STM32F4xx_HAL_Driver/   ST, ne pas modifier
```

Un pilote (`Drivers/BSP`) parle à un composant et ne connaît rien du
projet. Une tâche (`Core/Taches`) contient la logique du projet et
utilise les pilotes.

## Ajouter une tâche

1. Créer `Core/Taches/TXX_Nom/` avec `tXX_nom.c` et `tXX_nom.h`.
   Un nouveau composant va dans `Drivers/BSP/<Composant>/`.
2. Ajouter le dossier aux chemins d'inclusion : clic droit sur le projet >
   Properties > C/C++ Build > Settings > MCU GCC Compiler > Include paths,
   pour **Debug et Release**.
3. Ajouter sa section dans `carte_config.h`.
4. Dans `can_esa.c`, ajouter ses ID dans `ids_acceptes[]` et sa fonction
   de réception dans `recepteurs[]` (les deux « POINT DE BRANCHEMENT »).
5. Dans `main.c`, appeler `XX_Init()` avant `CanEsa_Init()` et `XX_Task()`
   dans la boucle.
6. Recopier les changements dans les trois projets (Bas, Haut, Borne).

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
