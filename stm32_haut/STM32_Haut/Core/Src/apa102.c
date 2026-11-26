/*
 * apa102.c
 *
 *  T07 — pilote d'une chaîne de DEL APA102 (voir apa102.h).
 *  Responsable : Tom
 */

#include "apa102.h"
#include <string.h>

#define APA102_TIMEOUT_MS   10U

/* Trame complète : début (4) + 4 octets par DEL + fin (4) */
#define APA102_TAILLE_TRAME (4U + 4U * APA102_NB_DEL_MAX + 4U)

static uint8_t trame[APA102_TAILLE_TRAME];


HAL_StatusTypeDef APA102_Init(APA102_HandleTypeDef *dev,
                              SPI_HandleTypeDef *hspi,
                              uint8_t nb_del,
                              uint8_t luminosite)
{
    if (dev == NULL || hspi == NULL || nb_del == 0U || nb_del > APA102_NB_DEL_MAX)
    {
        return HAL_ERROR;
    }

    dev->hspi = hspi;
    dev->nb_del = nb_del;
    dev->luminosite = (luminosite > APA102_LUMINOSITE_MAX) ? APA102_LUMINOSITE_MAX : luminosite;

    APA102_ToutEteindre(dev);

    return APA102_Envoyer(dev);
}


HAL_StatusTypeDef APA102_DefinirCouleur(APA102_HandleTypeDef *dev,
                                        uint8_t indice,
                                        uint8_t rouge,
                                        uint8_t vert,
                                        uint8_t bleu)
{
    if (dev == NULL || indice >= dev->nb_del)
    {
        return HAL_ERROR;
    }

    dev->couleurs[indice].rouge = rouge;
    dev->couleurs[indice].vert = vert;
    dev->couleurs[indice].bleu = bleu;

    return HAL_OK;
}


void APA102_ToutEteindre(APA102_HandleTypeDef *dev)
{
    if (dev != NULL)
    {
        memset(dev->couleurs, 0, sizeof(dev->couleurs));
    }
}


/* Envoie toute la chaîne. Bloquant, mais court : 68 octets pour 15 DEL,
 * environ 1,7 ms avec le SPI1 à 328 kbit/s (prescaler 256). */
HAL_StatusTypeDef APA102_Envoyer(APA102_HandleTypeDef *dev)
{
    uint32_t k = 0;

    if (dev == NULL || dev->hspi == NULL)
    {
        return HAL_ERROR;
    }

    /* Trame de début : 32 bits à 0 */
    for (uint32_t i = 0; i < 4U; i++)
    {
        trame[k++] = 0x00;
    }

    /* Une trame par DEL : 111 + luminosité sur 5 bits, puis B, V, R */
    for (uint32_t i = 0; i < dev->nb_del; i++)
    {
        trame[k++] = (uint8_t)(0xE0U | dev->luminosite);
        trame[k++] = dev->couleurs[i].bleu;
        trame[k++] = dev->couleurs[i].vert;
        trame[k++] = dev->couleurs[i].rouge;
    }

    /* Trame de fin : 32 bits à 1 (assez de fronts d'horloge pour 32 DEL) */
    for (uint32_t i = 0; i < 4U; i++)
    {
        trame[k++] = 0xFF;
    }

    return HAL_SPI_Transmit(dev->hspi, trame, (uint16_t)k, APA102_TIMEOUT_MS);
}
