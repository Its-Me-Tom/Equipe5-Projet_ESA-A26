# CLAUDE.md — Projet ESA, équipe 5 (Tom)

Contexte repris d'une longue discussion avec Claude (claude.ai, nov. 2026).
Claude Code charge ce fichier au début de chaque session. Le code du repo
reste la référence : en cas de doute, lire le code plutôt que ce résumé.

---

## 1. Qui et quoi

- **Tom** : étudiant en électronique programmable, Cégep Limoilou. Pas un
  débutant en électronique : ne pas expliquer les bases.
- **Projet ESA** (Eco Stationnement Automatisé), projet intégrateur A26,
  **équipe 5**. Remise autour du **11 décembre 2026** (à confirmer).
- **Ses tâches** : T02 (RFID et comptes), T04 (transactions et facturation),
  T07 (DEL, côté RPi seulement), T12 (retrait du véhicule), T13 (supervision
  MQTT + application PC).
- Un **coéquipier** fait l'affichage sur l'écran de la borne (code RPi basé
  sur les mêmes labos). Un merge avec son code est prévu (voir section 10).
- Tom **révise tout le code lui-même** : expliquer les changements clairement.

## 2. Comment travailler avec Tom

- Répondre en **français** (il écrit en québécois, mêlé d'anglais). Être
  **direct**, sans flatterie ni flou.
- **Toujours finir une procédure ou une liste d'étapes par une checklist
  courte** (`- [ ] ...`) pour qu'il puisse se situer.
- Code : **en français**, comme les exemples du prof. **Garder les noms des
  classes et méthodes des labos** (`MainWindow`, `MainController`,
  `MqttClient.connect_to_broker/publish/subscribe`, `CanManager.connect/send/
  receive/next_sequence/disconnect`, `add_log`...). Code simple et commenté.
- **App PC** : quand il demande un changement, lui montrer seulement les
  fichiers modifiés (pas tout le projet).
- **Tests** : chaque test doit être autonome (voir section 8) et tout
  afficher dans le terminal, rien sur le disque.
- Ne pas commiter ni pousser sans qu'il le demande.
- **Branches** : ne toucher qu'à la branche `Tom`, à la branche de travail
  de Claude et à `main` (seulement pour ce qui concerne Tom). **Ne jamais
  rien faire sur les branches des coéquipiers** (David, Moonelle, Sam) :
  ni modifier, ni lire, ni merger.
- `main` est protégée : jamais de push direct, tout passe par une pull
  request approuvée par un autre membre. Les actions GitHub de Claude passent
  par le compte de Tom, donc Tom apparaît comme auteur de ses pull requests.

## 3. Règle de sécurité absolue (MQTT partagé du labo)

**Aucune commande ne doit être publiée sous le préfixe MQTT d'une autre
équipe** (`esa/Equipe_N/` avec N ≠ 5). Le broker est partagé : ça briserait
le travail des autres équipes. `test_t13_02_isolation_des_equipes.py` utilise
des équipes **fictives 98 et 99** et refuse de démarrer en mode réel si
`AUTRES_EQUIPES` contient un numéro ≤ 50. Ne jamais changer ça.

## 4. Repo, branches, git

- GitHub : `Its-Me-Tom/Equipe5-Projet_ESA-A26`. Tom travaille sur la
  branche **`Tom`**.
- Structure (vue dans VS Code le 25 nov.) :
  - `pc_supervision/` : app PC PyQt6 (`src/controllers`, `src/models`,
    `src/network`, `src/views`, `config.py`, `mqtt_topics.py`, `main.py`,
    `test_pc_01..04_*.py`, `lancer_tous_les_tests.py`).
  - `rpi/` : code du Raspberry Pi 5 (voir section 6) + 49 tests.
  - `tests/` : outils autonomes (`mqtt_simple.py`, `rfid_simple.py`,
    `test_rfid_vers_pc.py`).
  - `stm32_bas/`, `stm32_haut/`, `stm32_borne/` : code des STM32 (équipe).
    Projets `STM32_Bas`, `STM32_Haut`, `STM32_Borne` identiques : seule la
    ligne `#define CARTE` de `Core/Commun/carte_config.h` change.
    Arborescence à la LitDeClous : `Core/Commun/` (carte_config.h,
    protocole_can.h, can_esa.c/.h = gestionnaire CAN unique et heartbeat),
    `Core/Taches/T07_Eclairage/` (T07 de Tom), `Drivers/BSP/APA102/`
    (pilote). Chaque nouveau dossier va dans les include paths du
    `.cproject`, Debug et Release.
    Voir le `README.md` de chaque projet. Un changement à T07 doit être
    recopié dans les trois projets.
- **T07 STM32** : DEL paires = places (Bas 1-7, Haut 8-14), DEL impaires =
  éclairage blanc (Bas niveau 0, Haut niveau 1, Borne niveau 2). La Borne
  pilote la plaque du toit : DEL paires en déco (`T07_DISCO`).
  - Les docs de la discussion parlent de `pc/` : c'est `pc_supervision/`.
- **État au 25 nov. (midi)** : l'app PC finie est sur GitHub. Le code RPi
  à jour était seulement sur la RPi. Tom a fait `git pull origin Tom` sur la
  RPi (merge, sans conflit) pour pouvoir pousser. Objectif : **`rpi/` et
  `tests/` = version de la RPi, tout le reste = version GitHub**. Procédure
  donnée (vérifier avec `git status` / `git log` si c'est fait) :
  ```
  git status --short                       # doit être vide
  git restore --source=ORIG_HEAD --staged --worktree -- rpi tests
  git restore --source=origin/Tom --staged --worktree -- . ':(exclude)rpi' ':(exclude)tests'
  git diff --stat ORIG_HEAD -- rpi tests                                 # vide
  git diff --stat origin/Tom -- . ':(exclude)rpi' ':(exclude)tests'     # vide
  git commit -m "rpi et tests : version de la RPi; reste : version GitHub"
  git push origin Tom
  ```
- Ne pas commiter : `__pycache__/`, `*.pyc`, `rpi/data/operations.csv`,
  `rpi/data/transactions.csv` (générés à l'exécution).

## 5. Réseau et matériel

- **Broker MQTT** : `10.50.86.13:1883` (`BROKER_IP` dans `rpi/src/config.py`,
  `pc_supervision/src/config.py` et `mqtt_simple.py`). La RPi est en SSH à
  `10.50.86.27`. Le PC de Tom est une VM.
- **RFID ID-12LA** (PCB-07 sur PCB-10) : 9600 8N1 sur `/dev/ttyAMA0`
  (GPIO15 = RX, `dtparam=uart0=on`, console série désactivée). Sortie **D0
  → RX** (broche 3 du PMOD type 3 du HAT/PCB-10), D0 ≤ 3,3 V, GND commun.
  Trame : STX + 10 hexa + 2 hexa checksum (XOR des 5 octets) + CR LF + ETX.
- **CAN** : HAT MCP2515, `can0` à 500 kbit/s
  (`sudo ip link set can0 up type can bitrate 500000`), `python-can`
  socketcan. Vérifier avec `python3 diagnostic_can.py` (heartbeats
  0x041-0x043 des STM32).
- **STM32** : Haut, Bas, Borne. Protocole **ESA CAN v1.6** (section 7).
- **DEL PCB-03** (BL-HBGR32L-3-TRB-8, compatibles APA102) testées avec un
  STM32F407G-DISC1 : SPI2 PB13 SCK / PB15 MOSI (broches FT, tolérantes 5 V),
  open-drain + pull-up 2,2 kΩ au 5 V, CPOL bas, CPHA 1er front, MSB d'abord,
  prescaler 256. Trame : 32 bits à 0, puis par DEL `0xE0|luminosité(0-31)`,
  B, G, R, puis trame de fin. Piège vu : `0xE0` seul = luminosité 0 (éteinte),
  utiliser `0xFF` (= `0xE0|31`).
- **Montage réel des DEL** (PCB-12 + PCB-11) : une barre de 15 DEL par
  carte sur le **PMOD type 2 = SPI1** (PA5 SCK, PA7 MOSI), traducteur
  TXU0102 du PCB-11 (push-pull suffit). **PE3** (CS de l'accéléromètre,
  même SPI1) doit rester haute. **PE0** = OE du PCB-11 (pull-up 100 kΩ) :
  ne jamais la mettre à 0. L'essai SPI2 ci-dessus était sur banc seulement.
- **Radar C4001** (DFRobot) : I2C 0x2B. Registre 0x00 = statut (0x81 = init
  + en marche + mode présence), résultats 0x10-0x16, **repeated start
  obligatoire** (ioctl I2C_RDWR). Changement de mode par CTRL1 0x3B, départ
  0x55. Script autonome `radar.py` fait dans la discussion.

## 6. Architecture du code RPi (`rpi/`)

- **La RPi est le « boss »** : elle garde les soldes (T02 : `data/comptes.csv`,
  `data/operations.csv`) et décide des paiements. Elle fonctionne même sans
  le PC. **Le PC est un superviseur** : il voit des copies publiées et peut
  seulement *demander* (commandes MQTT).
- `src/controllers/service_rpi.py` : **`ServiceRPi`** = tout le métier
  (T02, T04, T07, T12, T13), sans aucun widget. Points de branchement
  marqués « POINT DE BRANCHEMENT » : listes `receveurs_can`,
  `receveurs_carte`, `taches_boucle`.
- `src/controllers/service_worker.py` : thread qui fait tourner le service
  et émet `instantane_pret` (un dict d'état toutes les 200 ms).
- Une interface (fenêtre) **lit** `instantane_pret` et **agit** seulement
  par `service.demander(fonction, arguments)` (exécuté dans le thread du
  service). Jamais d'appel direct aux modules T02/T04/T12 depuis le thread Qt.
- **Un seul propriétaire du matériel : `ServiceRPi`** (port série RFID,
  can0, client MQTT `esa-rpi-equipe-5`). Personne d'autre ne les ouvre.
- `src/hardware/` : `t02_lecteur_rfid.py`, `can_manager.py`,
  `protocole_can.py` (tous les ID CAN). `src/network/mqtt_client.py`.
  `src/models/` : `t02_*`, `t04_*`, `t07_*`, `t12_*`, `t13_*`,
  `stationnement.py`, `heartbeat_rpi.py`, `erreurs.py`.
  `src/simulation/` : `faux_stm32.py` (simule les STM32 fonction par
  fonction, pannes provoquées), `faux_broker.py`, `doublures.py`.
  `src/views/` : fenêtre d'essai + pages T04 (`t04_pages_paiement*.py`,
  écran tactile 1024×600).
- `main.py` suit `SIMULER_RFID`, `SIMULER_CAN`, `SIMULER_MQTT` de
  `config.py` (encore à `True` : les mettre à `False` pour la vraie borne).
- Montants **toujours en cents (int)**. Cartes : `int` dans le code, texte
  de 10 caractères dans les CSV et MQTT (conversion seulement par
  `src/format_carte.py`).

## 7. Protocoles

**Cartes RFID** (`config.FORMAT_CARTE`) :
- `"DECIMAL"` (défaut) = numéro imprimé sur la puce = décimal des **4
  derniers octets**, 10 chiffres. Ex. ID brut `110082EEC8` → `0008580808`.
- `"BRUT"` = les 5 octets en hexa (`110082EEC8`).
- `comptes.csv` = `rfid,nom,solde` dans le même format (l'ancien
  `rfid,solde` est encore lu). Puces réelles : Samuel `0008909278`,
  Thomas `0008580808` (brut `110082EEC8`), David `0008582455`, 25 $ chacun.
- `AJOUTER_CARTES_INCONNUES = True` : une carte inconnue lue au lecteur
  reçoit un compte (nom = son numéro, solde = `SOLDE_NOUVELLE_CARTE_CENTS`,
  1000 ¢), une seule fois.
- Le lecteur garde l'ID brut dans `lecteur.dernier_brut`;
  `decrire_carte(brut)` affiche « ID brut … | numéro imprimé (décimal) … ».

**MQTT** (paho v2, préfixe `esa/Equipe_5/`) :
- Publiés par la RPi : `etat` (au changement + toutes les 5 s), `places`,
  `anomalies`, `transactions` (transactions + statistiques par compte, au
  plus 1×/s), `commande/reponse`, `comptes/reponse`, `rpi/connexion`
  (retenu + testament LWT `{"en_ligne": false}`).
- Reçus : `commande` (METTRE_HORS_SERVICE, REMETTRE_EN_SERVICE,
  ARRET_IMMEDIAT, REINITIALISER — exige `intervention_confirmee: true`) et
  `comptes/commande` (CONSULTER_SOLDE, AJOUTER_CREDIT).
- Chaque commande a un `id` repris dans la réponse. Commande absente ou
  inconnue → `COMMANDE_INCONNUE`.
- Les réponses sur les comptes incluent `nom`. Contrat détaillé :
  `docs/CONTRAT_MQTT.md` (s'il est ajouté au repo), sinon lire
  `src/models/t13_supervision_mqtt.py`.

**CAN ESA v1.6** :
- Commandes moteur ELEVATION/ROTATION/BRAS_CMD `0x100/0x110/0x120`.
  États `0x200/0x210/0x220` : 0 refusé, 1 accepté, 2 terminé, 3 interrompu,
  4 défaut. T12 envoie **une commande à la fois** (bras rentré avant chaque
  rotation ou changement de niveau).
- ARRET `0x001-0x004` (ARRET_RPI `[0x01, 6, 0]`), DEFAUT `0x010-0x012`,
  REARMEMENT_CMD `0x050` (réponses `0x051-0x053`), SYNCHRO_CMD `0x080`.
- Heartbeats `0x040` (RPi, toutes les 500 ms) à `0x043`. États : 0 init,
  1 prêt, 2 occupé, 3 verrouillé, 4 défaut.
- IR : places `0x300/0x301`, lecture `0x302`, rampe `0x310/0x311`.
- Éclairage `0x130` (accusés `0x350-0x352`). DEL_PLACE_CMD `0x340`
  `[seq, place 1-14, R, G, B, mode]`, accusés `0x341` (Bas), `0x342` (Haut).
  Un seul renvoi, puis anomalie non critique.

## 8. Tests

- **`rpi/` : 49 tests** `test_tXX_NN_*.py` (T02 ×9, T04 ×11, T07 ×8,
  T12 ×11, T13 ×10). **Garder les noms actuels** (ceux de Tom, ex.
  `test_t02_01_lecture_simulee.py`, `test_t13_05_gestion_des_comptes.py`).
- **Chaque test est 100 % autonome** : il a seulement besoin de `src/`.
  Les outils communs (affichage, données, faux PC, etc.) sont **recopiés
  dans chaque fichier**. Pour changer un outil commun, il faut le changer
  dans tous les tests qui le contiennent, ou passer par le générateur
  (`outils/generateur_tests/`, s'il a été ajouté au repo :
  `python3 construire.py corps/rpi ../../rpi`).
- Tout s'affiche dans le terminal (trames CAN décodées, messages MQTT,
  fichiers avant/après). Dossiers temporaires effacés à la fin.
- **Interrupteurs en haut de chaque test** : `MATERIEL_REEL = True` par
  défaut (vrai matériel, demande des actions à l'opérateur). Les T13 ont
  aussi `APP_PC_REELLE = True` (l'opérateur clique dans la vraie app PC).
  23 tests de pure logique n'ont pas d'interrupteur.
- `python3 lancer_tous_les_tests.py [t07] [--details]` : lance tout **en
  simulation forcée** (variable `ESA_SIMULATION=1`, sans modifier les
  fichiers). Doit donner **49/49**. Pour le vrai matériel : lancer chaque
  test seul.
- Les cartes de test sont fictives sur 4 octets (`1111111111`,
  `2222222222`, `3333333333`, inconnue `4000000000`), valides dans les deux
  formats. Les tests passent en `DECIMAL`, en `BRUT` et avec
  `AJOUTER_CARTES_INCONNUES = False`.
- `pc_supervision/` : 4 tests (`test_pc_01` réception, `02` commandes et
  réponses, `03` messages invalides, `04` bandes de connexion RPi). Ils
  utilisent la vraie `MainWindow` + `MainController` avec un faux MQTT
  (`MATERIEL_REEL = False` par défaut côté PC).
- Outils : `rfid_simple.py` (ID brut + numéro imprimé de chaque puce),
  `mqtt_simple.py`, `test_rfid_vers_pc.py` (publie chaque lecture sur
  `comptes/reponse` comme `LECTURE_RFID`), `diagnostic_can.py`.
- Seul T13 a été validé sur le vrai matériel (au 24 nov.). Les autres
  passent en simulation.

## 9. App PC (`pc_supervision/`)

- Onglets : **Stationnement** (14 places en **carrés à coins arrondis**,
  `ARRONDI_TEMOIN = 8` dans `page_stationnement.py`), **Comptes RFID**
  (colonnes Carte, **Nom**, Solde), **Commandes** (état général + boutons),
  **Statistiques**. Le journal MQTT est sous les onglets, dans `MainWindow`.
- Deux bandes : connexion **PC → MQTT** et, juste en dessous, **RPi → MQTT**
  (topic `rpi/connexion` retenu + testament).
- Journal MQTT : **heure `HH:MM:SS` à gauche** de chaque ligne (`add_log`).
- Commandes : la case « intervention confirmée » **se décoche après chaque
  clic sur Réinitialiser**, même si la commande échoue.
- Renvoyer une commande garde le même `id`. Sans réponse → avis affiché.
- À vérifier : la version sur GitHub contient-elle bien ces derniers
  changements (carrés arrondis, colonne Nom, heure du journal)?

## 10. Merge prévu avec le coéquipier (écran de la borne)

- Conflits certains sur `main.py`, `src/views/main_window.py`,
  `src/controllers/main_controller.py` (même gabarit de labo) : sa fenêtre
  devient la principale, son contrôleur crée `ServiceRPi` + `ServiceWorker`.
- `config.py` : fusion à la main, une section par personne.
- `mqtt_client.py` / `can_manager.py` : garder ceux de Tom (simulation,
  présence/LWT, séquences CAN).
- Lui dire les deux règles : un seul propriétaire du matériel
  (`ServiceRPi`), et passer par `service.demander(...)`.
- Après le merge : `lancer_tous_les_tests.py` doit rester à 49/49 (les tests
  ne dépendent pas de la fenêtre).

## 11. Bugs déjà corrigés (ne pas les réintroduire)

- T04 `confirmer_rangement` : horodatage texte, négatif ou dans le futur →
  refus `HORODATAGE_INVALIDE` (avant : plantage ou accepté).
- MQTT : au départ propre, attendre que « hors ligne » soit publié avant de
  couper (`wait_for_publish`), sinon il arrivait après « en ligne » à la
  reconnexion.
- T13_10 : commande sans champ `commande` → `COMMANDE_INCONNUE` (contrat).
- Réponses MQTT de paho affichées dans un autre thread : les tests mettent
  les messages en file pour ne pas mélanger l'affichage.

## 12. Points ouverts (à confirmer)

- Ordre mécanique du retrait (`SEQUENCE_RETRAIT`), correspondance IR ↔
  places, délais des mouvements, mappage réel des 14 DEL (E1.x = Bas,
  E2.x = Haut), DEL pendant un arrêt, tarif (25 ¢/min), contrat JSON MQTT
  à valider avec l'équipe, redémarrage pendant un verrouillage.
- Liste complète : `docs/POINTS_A_CONFIRMER.md` (s'il est ajouté au repo).
