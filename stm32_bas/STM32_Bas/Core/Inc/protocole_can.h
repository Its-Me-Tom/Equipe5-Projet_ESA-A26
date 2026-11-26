/*
 * protocole_can.h
 *
 *  PARTIE COMMUNE — identifiants et valeurs du protocole CAN ESA v1.6
 *  (document « ESA_Protocole_CAN_243-557_A2026_v1.6 », section 3 :
 *  registre unique des identifiants).
 *
 *  Ce fichier est identique sur les trois STM32 (Haut, Bas, Borne).
 *  Ne pas changer un identifiant sans l'accord de toutes les équipes :
 *  le Raspberry Pi utilise les mêmes valeurs (rpi/src/hardware/protocole_can.py).
 *
 *  Les noms sont ceux du document pour s'y retrouver facilement.
 */

#ifndef INC_PROTOCOLE_CAN_H_
#define INC_PROTOCOLE_CAN_H_

/* ------------------------------------------------------------------------- */
/* Arrêts, défauts et surveillance (commun à toutes les cartes)              */
/* ------------------------------------------------------------------------- */
#define ARRET_HAUT              0x001U  /* DLC 3 : motif, source, détail      */
#define ARRET_BAS               0x002U
#define ARRET_BORNE             0x003U
#define ARRET_RPI               0x004U

#define DEFAUT_HAUT             0x010U  /* DLC 4 : source, code, gravité, détail */
#define DEFAUT_BAS              0x011U
#define DEFAUT_BORNE            0x012U
#define DEFAUT_RPI              0x013U

#define HEARTBEAT_RPI           0x040U  /* DLC 2 : compteur, état              */
#define HEARTBEAT_HAUT          0x041U
#define HEARTBEAT_BAS           0x042U
#define HEARTBEAT_BORNE         0x043U

#define REARMEMENT_CMD          0x050U  /* DLC 2 : séquence, action (0x01)     */
#define REARMEMENT_HAUT         0x051U  /* DLC 3 : séquence, résultat, motif   */
#define REARMEMENT_BAS          0x052U
#define REARMEMENT_BORNE        0x053U

#define SYNCHRO_CMD             0x080U  /* DLC 1 : 0x01 capteurs, 0x02 moteurs, 0x03 tous */

/* État d'un contrôleur dans son heartbeat (DB1) */
#define HEARTBEAT_INITIALISATION 0U
#define HEARTBEAT_PRET           1U
#define HEARTBEAT_OCCUPE         2U
#define HEARTBEAT_VERROUILLE     3U
#define HEARTBEAT_DEFAUT         4U

/* ------------------------------------------------------------------------- */
/* Mouvements de l'ascenseur — T08, T09, T10 (STM32 Haut)                     */
/* ------------------------------------------------------------------------- */
#define ELEVATION_CMD           0x100U  /* DLC 3 */
#define ROTATION_CMD            0x110U  /* DLC 3 */
#define BRAS_CMD                0x120U  /* DLC 3 */
#define ELEVATION_ETAT          0x200U  /* DLC 5 */
#define ROTATION_ETAT           0x210U  /* DLC 4 */
#define BRAS_ETAT               0x220U  /* DLC 4 */

/* Résultat commun des états moteurs (DB1) */
#define RESULTAT_REFUSE         0U
#define RESULTAT_ACCEPTE        1U
#define RESULTAT_TERMINE        2U
#define RESULTAT_INTERROMPU     3U
#define RESULTAT_DEFAUT         4U

/* ------------------------------------------------------------------------- */
/* Imprimante — T05 (STM32 Borne)                                             */
/* ------------------------------------------------------------------------- */
#define IMPRESSION_ETAT         0x230U  /* DLC 3 */
#define IMPRESSION_CMD          0x360U  /* DLC 8 */
#define IMPRESSION_DATE         0x361U  /* DLC 7 */

/* ------------------------------------------------------------------------- */
/* Détecteurs infrarouges — T06                                               */
/* ------------------------------------------------------------------------- */
#define IR_BAS_CHANGEMENT       0x300U  /* Bas  — DLC 3 */
#define IR_BAS_COMPLET          0x301U  /* Bas  — DLC 4 */
#define IR_LECTURE_CMD          0x302U  /* RPi  — DLC 1 */
#define IR_ENTREE_CHANGEMENT    0x310U  /* Haut — DLC 3 */
#define IR_ENTREE_COMPLET       0x311U  /* Haut — DLC 3 */

/* ------------------------------------------------------------------------- */
/* Luminosité — T01 (STM32 Borne)                                             */
/* ------------------------------------------------------------------------- */
#define LUMINOSITE_ETAT         0x320U  /* DLC 2 */

/* ------------------------------------------------------------------------- */
/* Détecteurs d'étage — T08 (STM32 Haut)                                      */
/* ------------------------------------------------------------------------- */
#define ETAGE_DETECTE           0x330U  /* DLC 3 */
#define ETAGE_ETAT              0x331U  /* DLC 3 */
#define ETAGE_LECTURE_CMD       0x332U  /* DLC 1 */

/* ------------------------------------------------------------------------- */
/* DEL des places et éclairage — T07 (Bas, Haut, Borne)                       */
/* ------------------------------------------------------------------------- */
#define ECLAIRAGE_CMD           0x130U  /* RPi -> Bas/Haut/Borne, DLC 5 : séq., niveau, R, V, B */
#define DEL_PLACE_CMD           0x340U  /* RPi -> Bas/Haut, DLC 6 : séq., place, R, V, B, mode   */
#define DEL_BAS_ETAT            0x341U  /* Bas  — DLC 3 : séquence, place, résultat  */
#define DEL_HAUT_ETAT           0x342U  /* Haut — DLC 3 : séquence, place, résultat  */
#define ECLAIRAGE_BAS_ETAT      0x350U  /* Bas  — DLC 3 : séquence, niveau, résultat */
#define ECLAIRAGE_HAUT_ETAT     0x351U  /* Haut */
#define ECLAIRAGE_BORNE_ETAT    0x352U  /* Borne */

/* Mode d'une DEL de place (DB5 de DEL_PLACE_CMD) */
#define DEL_MODE_FIXE           0U
#define DEL_MODE_CLIGNOTANT     1U      /* 1 Hz */

/* Résultat des accusés de T07 (DB2) */
#define ACCUSE_REFUSE           0U
#define ACCUSE_APPLIQUE         1U

/* Séquence d'une trame spontanée (sans commande associée) */
#define SEQUENCE_SPONTANEE      0xFFU

#endif /* INC_PROTOCOLE_CAN_H_ */
