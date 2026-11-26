/*
 * apa102.h
 *
 *  T07 — pilote d'une chaîne de DEL APA102 (BL-HBGR32L-3-TRB-8, PCB-03).
 *  Responsable : Tom
 *
 *  Le pilote ne sait rien des places ni des niveaux : il garde une couleur
 *  par DEL et envoie toute la chaîne par SPI. La logique de T07 est dans
 *  t07_eclairage.c.
 *
 *  Trame APA102 :
 *    4 octets 0x00                       trame de début
 *    pour chaque DEL : 0xE0 | luminosité (0-31), bleu, vert, rouge
 *    4 octets 0xFF                       trame de fin
 *
 *  Matériel (PCB-12 + PCB-11) :
 *    SPI1 maître, CPOL bas, CPHA 1er front, MSB d'abord.
 *    Le SPI1 est partagé avec l'accéléromètre de la Discovery : sa broche
 *    CS (PE3) doit rester HAUTE pour qu'il ignore nos trames.
 *    PE0 = SS du PMOD = OE du traducteur TXU0102 du PCB-11 (actif haut,
 *    pull-up de 100 kΩ) : ne jamais la mettre à 0, sinon les DEL ne
 *    reçoivent plus rien.
 */

#ifndef INC_APA102_H_
#define INC_APA102_H_

#include "main.h"
#include <stdint.h>

#define APA102_NB_DEL_MAX     32U
#define APA102_LUMINOSITE_MAX 31U

typedef struct
{
    uint8_t rouge;
    uint8_t vert;
    uint8_t bleu;
} APA102_Couleur;

typedef struct
{
    SPI_HandleTypeDef *hspi;
    uint8_t nb_del;
    uint8_t luminosite;                         /* 0 à 31, commune à toutes les DEL */
    APA102_Couleur couleurs[APA102_NB_DEL_MAX]; /* indice 0 = 1re DEL de la chaîne  */
} APA102_HandleTypeDef;

HAL_StatusTypeDef APA102_Init(APA102_HandleTypeDef *dev,
                              SPI_HandleTypeDef *hspi,
                              uint8_t nb_del,
                              uint8_t luminosite);

HAL_StatusTypeDef APA102_DefinirCouleur(APA102_HandleTypeDef *dev,
                                        uint8_t indice,
                                        uint8_t rouge,
                                        uint8_t vert,
                                        uint8_t bleu);

void APA102_ToutEteindre(APA102_HandleTypeDef *dev);

HAL_StatusTypeDef APA102_Envoyer(APA102_HandleTypeDef *dev);

#endif /* INC_APA102_H_ */
