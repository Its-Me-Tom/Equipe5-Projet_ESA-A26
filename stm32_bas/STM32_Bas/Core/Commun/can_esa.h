/*
 * can_esa.h
 *
 *  PARTIE COMMUNE — gestionnaire CAN unique de la carte.
 *
 *  Il y a UN SEUL gestionnaire CAN par STM32 (fiche T07, section 2 :
 *  pas de second gestionnaire, pas d'initialisation CAN en double).
 *  Il s'occupe de :
 *    - démarrer CAN1 et ses filtres (seulement les ID utiles à la carte);
 *    - recevoir les trames sous interruption et les ranger dans une file;
 *    - les distribuer aux tâches dans la boucle principale (CanEsa_Task);
 *    - envoyer les trames des tâches (file d'envoi, jamais bloquant);
 *    - émettre le heartbeat de la carte toutes les 500 ms;
 *    - surveiller le heartbeat du Raspberry Pi.
 *
 *  Une tâche qui veut recevoir des trames :
 *    1. ajoute ses ID dans ids_acceptes[] (can_esa.c);
 *    2. ajoute sa fonction de réception dans recepteurs[] (can_esa.c).
 *  Les deux endroits sont marqués « POINT DE BRANCHEMENT ».
 */

#ifndef INC_CAN_ESA_H_
#define INC_CAN_ESA_H_

#include "main.h"
#include <stdint.h>

/* Une trame CAN reçue ou à envoyer */
typedef struct
{
    uint16_t id;            /* identifiant standard 11 bits */
    uint8_t  dlc;           /* nombre d'octets de données (0 à 8) */
    uint8_t  donnees[8];
} CanTrame;

/* Fonction de réception d'une tâche.
 * Retourne 1 si la trame a été traitée, 0 si elle ne la concerne pas. */
typedef uint8_t (*CanRecepteur)(const CanTrame *trame);

HAL_StatusTypeDef CanEsa_Init(CAN_HandleTypeDef *hcan);
void CanEsa_Task(void);

HAL_StatusTypeDef CanEsa_Envoyer(uint16_t id, const uint8_t *donnees, uint8_t dlc);

void CanEsa_DefinirEtat(uint8_t etat);      /* état publié dans le heartbeat */
uint8_t CanEsa_LireEtat(void);
uint8_t CanEsa_RpiPresent(void);            /* 1 si un heartbeat RPi est récent */

/* Compteurs de diagnostic (lisibles au débogueur) */
uint32_t CanEsa_NbTramesPerdues(void);      /* file de réception pleine */
uint32_t CanEsa_NbEnvoisPerdus(void);       /* file d'envoi pleine */

#endif /* INC_CAN_ESA_H_ */
