/*
 * CapteurDeLumiere.c
 *
 *  Created on: 17 nov. 2026
 *      Author: etudiant
 */
/* ldr.c
 * Driver photorésistance NORPS-12 sur PC5 (ADC1_IN15) - STM32F407G-DISC1
 * Utilise hadc1 généré par CubeMX (le canal IN15 est déjà configuré dans le .ioc).
 */

#include "CapteurDeLumiere.h"
#include "main.h"

extern ADC_HandleTypeDef hadc1;


/* ================= DEBUT CODE DE TEST (USB) =================
 * Pour tout enlever :
 *   1) mettre LDR_TEST_USB à 0, ou
 *   2) supprimer ce bloc complet + la ligne "LDR_Test_SendUSB(raw);" dans LDR_Read()
 */
#define LDR_TEST_USB   1

#if LDR_TEST_USB
#include "usbd_cdc_if.h"
#include <stdio.h>

static void LDR_Test_SendUSB(uint16_t raw)
{
    char buf[32];
    int len = snprintf(buf, sizeof(buf), "LDR raw=%u\r\n", (unsigned)raw);
    if (len > 0)
    {
        CDC_Transmit_FS((uint8_t *)buf, (uint16_t)len);
    }
}
#else
#define LDR_Test_SendUSB(raw)   ((void)(raw))
#endif
/* ================= FIN CODE DE TEST (USB) ================= */


uint16_t LDR_Read(void)
{
    uint16_t raw = 0;

    HAL_ADC_Start(&hadc1);
    if (HAL_ADC_PollForConversion(&hadc1, 10) == HAL_OK)
    {
        raw = (uint16_t)HAL_ADC_GetValue(&hadc1);
    }
    HAL_ADC_Stop(&hadc1);

    LDR_Test_SendUSB(raw);   /* TEST : à supprimer avec le bloc ci-dessus */

    return raw;
}

