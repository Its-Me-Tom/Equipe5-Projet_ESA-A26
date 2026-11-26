/*
 * t07_eclairage.h
 *
 *  T07 — DEL d'état des places et éclairage blanc, partie STM32.
 *  Responsable : Tom
 *
 *  Contrat : « ESA_Interfaces_logicielles_T07_Éclairage_v1.1 », section 4.
 *  Le Raspberry Pi décide seul des états et des intensités; le STM32 ne fait
 *  qu'appliquer ce qu'il reçoit par CAN et répondre par un accusé.
 *
 *  Une plaque PCB-03 = une chaîne de 15 DEL, numérotées de 1 à 15 :
 *    - DEL paires (dessus) : témoins RGB des 7 places de la plaque;
 *    - DEL impaires (dessous) : éclairage blanc du niveau sous la plaque.
 *  Le rôle de la plaque dépend de la carte (voir carte_config.h) :
 *    Bas   : places 1 à 7,  éclairage du niveau 0;
 *    Haut  : places 8 à 14, éclairage du niveau 1;
 *    Borne : toit sans places (DEL paires en déco), éclairage du niveau 2.
 *
 *  Utilisation dans main.c :
 *    LED_Init();               une fois, avant CanEsa_Init()
 *    LED_Task();               à chaque tour de la boucle principale
 *  Les trames CAN arrivent par T07_TraiterTrameCan(), branchée dans
 *  can_esa.c.
 */

#ifndef INC_T07_ECLAIRAGE_H_
#define INC_T07_ECLAIRAGE_H_

#include "can_esa.h"
#include <stdbool.h>
#include <stdint.h>

/* États logiques d'une place : mêmes couleurs que COULEURS_DEL du RPi.
 * Servent aux essais locaux (mode démo); par CAN, le RPi envoie
 * directement la couleur et le mode. */
typedef enum
{
    T07_ETAT_LIBRE = 0,         /* vert                */
    T07_ETAT_RESERVE,           /* bleu                */
    T07_ETAT_OCCUPE,            /* rouge               */
    T07_ETAT_MAINTENANCE,       /* orange              */
    T07_ETAT_DEFAUT,            /* jaune clignotant    */
    T07_ETAT_ETEINT,            /* aucune consigne     */
    T07_NB_ETATS
} T07_EtatPlace;

/* Interface du contrat T07 */
void LED_Init(void);
void LED_Task(void);
bool LED_DefinirEtatPlace(uint8_t place, uint8_t etat);   /* place locale 0 à 6 */
bool RGB_DefinirIntensite(uint8_t intensite);             /* 0 = éteint, 255 = max */
void LED_AppliquerEtatSur(void);

/* Compléments utilisés par la couche CAN */
bool LED_DefinirCouleurPlace(uint8_t place, uint8_t rouge, uint8_t vert, uint8_t bleu, uint8_t mode);
bool RGB_DefinirCouleur(uint8_t rouge, uint8_t vert, uint8_t bleu);

/* Réception CAN (branchée dans recepteurs[] de can_esa.c) */
uint8_t T07_TraiterTrameCan(const CanTrame *trame);

#endif /* INC_T07_ECLAIRAGE_H_ */
