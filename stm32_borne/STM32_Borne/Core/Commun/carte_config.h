/*
 * carte_config.h
 *
 *  Identité de la carte et réglages propres à chaque STM32.
 *
 *  Les trois projets (STM32_Haut, STM32_Bas, STM32_Borne) ont le même code.
 *  Ce fichier est le SEUL qui change d'une carte à l'autre : la ligne
 *  « #define CARTE ... » choisit la carte, et tout le reste en découle.
 *
 *  Chaque tâche a sa propre section, avec le nom de son responsable.
 *  Pour ajouter une tâche : copier une section et changer son contenu.
 */

#ifndef INC_CARTE_CONFIG_H_
#define INC_CARTE_CONFIG_H_

#include "protocole_can.h"

/* ========================================================================= */
/* PARTIE COMMUNE — identité de la carte                                     */
/* ========================================================================= */

#define CARTE_HAUT    1
#define CARTE_BAS     2
#define CARTE_BORNE   3

#define CARTE         CARTE_BORNE          /* <-- LA ligne à changer par carte */

/* Identifiants CAN propres à la carte (déduits de CARTE) */
#if CARTE == CARTE_HAUT
  #define CARTE_NOM               "HAUT"
  #define CAN_ID_HEARTBEAT        HEARTBEAT_HAUT
  #define CAN_ID_ARRET            ARRET_HAUT
  #define CAN_ID_DEFAUT           DEFAUT_HAUT
  #define CAN_ID_REARMEMENT       REARMEMENT_HAUT
#elif CARTE == CARTE_BAS
  #define CARTE_NOM               "BAS"
  #define CAN_ID_HEARTBEAT        HEARTBEAT_BAS
  #define CAN_ID_ARRET            ARRET_BAS
  #define CAN_ID_DEFAUT           DEFAUT_BAS
  #define CAN_ID_REARMEMENT       REARMEMENT_BAS
#elif CARTE == CARTE_BORNE
  #define CARTE_NOM               "BORNE"
  #define CAN_ID_HEARTBEAT        HEARTBEAT_BORNE
  #define CAN_ID_ARRET            ARRET_BORNE
  #define CAN_ID_DEFAUT           DEFAUT_BORNE
  #define CAN_ID_REARMEMENT       REARMEMENT_BORNE
#else
  #error "CARTE doit valoir CARTE_HAUT, CARTE_BAS ou CARTE_BORNE"
#endif

/* Réglages du gestionnaire CAN commun (can_esa.c) */
#define CAN_PERIODE_HEARTBEAT_MS  500U   /* protocole v1.6 : toutes les 500 ms  */
#define CAN_DELAI_PERTE_RPI_MS    1500U  /* 3 heartbeats du RPi manqués         */
#define CAN_ACCEPTER_TOUT         0      /* 1 = aucun filtre matériel (diagnostic) */

/* DEL de la Discovery utilisées pour le diagnostic du CAN :
 *   PD12 vert = clignote à chaque heartbeat (la carte vit);
 *   PD13 orange = heartbeat du RPi reçu;
 *   PD14 rouge = contrôleur CAN en erreur (bus absent, débit, terminaison).
 * Désactivées sur le Haut : sur le PCB-12, PD12 à PD15 sont aussi les
 * broches EN, DIR, SenseB et SenseA du PMOD des moteurs. */
#if CARTE == CARTE_HAUT
  #define CAN_DEL_DIAGNOSTIC      0
#else
  #define CAN_DEL_DIAGNOSTIC      1
#endif

/* ========================================================================= */
/* T07 — DEL des places et éclairage blanc          Responsable : Tom        */
/* ========================================================================= */
/*
 * Barre de 15 DEL APA102 (PCB-03), branchée sur le PMOD type 2 du PCB-12
 * à travers le PCB-11 (traducteur 3,3 V -> 5 V) :
 *   SPI1 : PA5 = SCK -> CLOCK, PA7 = MOSI -> DATA.
 *   DEL numérotées de 1 à 15 dans l'ordre de la chaîne :
 *     paires   (2, 4 ... 14) = dessus de la plaque -> témoins RGB des places;
 *     impaires (1, 3 ... 15) = dessous de la plaque -> éclairage blanc du
 *                              niveau situé sous la plaque.
 */

#define T07_SPI_HANDLE            hspi1  /* SPI de la barre de DEL            */
#define T07_NB_DEL                15U    /* DEL dans la chaîne                */

/* Luminosité globale APA102 (0 à 31) appliquée à toutes les DEL.
 * 16 = valeur du code de test qui fonctionne. Monter vers 31 seulement si
 * l'alimentation 5 V du PCB-11 supporte le courant (15 DEL à pleine
 * puissance ≈ 0,9 A). */
#define T07_LUMINOSITE_GLOBALE    16U

/* Calibration du blanc en % par canal (point 2 de la fiche T07).
 * Le bleu des DEL RGB est très efficace : R = V = B donne un blanc bleuté.
 * On baisse donc le bleu, et un peu le vert, pour un blanc plus chaud.
 * Plus de jaune : baisser T07_CALIB_BLEU_PCT. Trop jaune : le remonter.
 * 100 / 100 / 100 = aucune correction. */
#define T07_CALIB_ROUGE_PCT       100U
#define T07_CALIB_VERT_PCT        90U
#define T07_CALIB_BLEU_PCT        75U

/* Correction gamma des couleurs des places : 1 = l'orange paraît orange
 * au lieu de jaune; 0 = couleurs envoyées telles quelles. */
#define T07_GAMMA_PLACES          1

/* Démonstration sans RPi : 1 = les places défilent dans tous les états et
 * l'éclairage varie tout seul; les commandes CAN sont ignorées. */
#define T07_MODE_DEMO             0

/* Perte des heartbeats du RPi : 1 = toutes les places passent en « défaut »
 * (jaune clignotant), 0 = les DEL gardent leur dernier état (décision
 * actuelle de l'équipe, à confirmer : point 3 de la fiche T07). */
#define T07_ETAT_SUR_PERTE_RPI    0

/* Rôle de la plaque pilotée par cette carte (fiche T07, section 2) */
#if CARTE == CARTE_BAS
  /* Plaque du niveau 1 : places 1 à 7 dessus, éclairage du niveau 0 dessous */
  #define T07_A_DES_PLACES        1
  #define T07_PREMIERE_PLACE      1U
  #define T07_NIVEAU_ECLAIRAGE    0U
  #define T07_ID_ACCUSE_DEL       DEL_BAS_ETAT
  #define T07_ID_ACCUSE_ECLAIRAGE ECLAIRAGE_BAS_ETAT
  #define T07_DISCO               0      /* inutilisé : les DEL paires sont des places */
#elif CARTE == CARTE_HAUT
  /* Plaque du niveau 2 : places 8 à 14 dessus, éclairage du niveau 1 dessous */
  #define T07_A_DES_PLACES        1
  #define T07_PREMIERE_PLACE      8U
  #define T07_NIVEAU_ECLAIRAGE    1U
  #define T07_ID_ACCUSE_DEL       DEL_HAUT_ETAT
  #define T07_ID_ACCUSE_ECLAIRAGE ECLAIRAGE_HAUT_ETAT
  #define T07_DISCO               0      /* inutilisé : les DEL paires sont des places */
#elif CARTE == CARTE_BORNE
  /* Plaque du toit : aucune place dessus, éclairage du niveau 2 dessous.
   * Les DEL paires ne servent qu'à la décoration. */
  #define T07_A_DES_PLACES        0
  #define T07_PREMIERE_PLACE      0U
  #define T07_NIVEAU_ECLAIRAGE    2U
  #define T07_ID_ACCUSE_DEL       0U     /* la Borne ne répond pas à DEL_PLACE_CMD */
  #define T07_ID_ACCUSE_ECLAIRAGE ECLAIRAGE_BORNE_ETAT
  #define T07_DISCO               1      /* 1 = arc-en-ciel sur les DEL paires, 0 = éteintes */
#endif

#define T07_NB_PLACES             7U     /* places par plaque */

/* ========================================================================= */
/* Autres tâches : ajouter ici leur section (T01, T05, T06, T08, T09, T10)   */
/* ========================================================================= */

#endif /* INC_CARTE_CONFIG_H_ */
