#ifndef THERMAL_PRINTER_H
#define THERMAL_PRINTER_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>

/* Imprimante MC206H (ESC/POS) sur USART3 : PD8 = TX, PB11 = RX, 9600 bauds 8N1 */

typedef struct {
    uint16_t year;    /* ex : 2026 */
    uint8_t  month;   /* 1..12 */
    uint8_t  day;     /* 1..31 */
    uint8_t  hour;    /* 0..23 */
    uint8_t  minute;  /* 0..59 */
} TP_DateTime;

extern UART_HandleTypeDef huart3;

/* Reinitialise l'imprimante (ESC @). USART3 doit deja etre initialise par CubeMX
 * (MX_USART3_UART_Init(), PD8 = TX, PB11 = RX, 9600 8N1) avant cet appel. */
HAL_StatusTypeDef TP_Init(void);

/*
 * Imprime un ticket :
 *   code6   : code a 6 chiffres (0..999999), affiche avec zeros devant
 *   barcode : texte ASCII imprimable (max 40 caracteres) encode en Code128
 *   dt      : date et heure d'impression
 */
HAL_StatusTypeDef TP_PrintTicket(uint32_t code6, const char *barcode, const TP_DateTime *dt);

#ifdef __cplusplus
}
#endif

#endif /* THERMAL_PRINTER_H */
