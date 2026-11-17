#include "thermal_printer.h"
#include <stdio.h>
#include <string.h>

#define TP_UART_TIMEOUT_MS   1000U
#define TP_BARCODE_MAX_LEN   40U

/* huart3 est defini dans main.c (genere par CubeMX) ; declare extern dans le .h */

/* ---------- Bas niveau ---------- */

static HAL_StatusTypeDef tp_write(const uint8_t *data, uint16_t len)
{
    return HAL_UART_Transmit(&huart3, (uint8_t *)data, len, TP_UART_TIMEOUT_MS);
}

static HAL_StatusTypeDef tp_puts(const char *s)
{
    return tp_write((const uint8_t *)s, (uint16_t)strlen(s));
}

static HAL_StatusTypeDef tp_cmd(uint8_t a, uint8_t b, uint8_t c)
{
    /* commande de 2 ou 3 octets (c = 0 -> ignore si a == 0x1B/0x1D et 2 octets voulus) */
    uint8_t buf[3] = { a, b, c };
    return tp_write(buf, 3);
}

static HAL_StatusTypeDef tp_align(uint8_t n)          /* 0 gauche, 1 centre, 2 droite */
{
    return tp_cmd(0x1B, 'a', n);                      /* ESC a n */
}

static HAL_StatusTypeDef tp_bold(uint8_t on)
{
    return tp_cmd(0x1B, 'E', on);                     /* ESC E n */
}

static HAL_StatusTypeDef tp_size(uint8_t n)           /* 0x00 normal, 0x11 double L+H */
{
    return tp_cmd(0x1D, '!', n);                      /* GS ! n */
}

static HAL_StatusTypeDef tp_feed(uint8_t lines)
{
    return tp_cmd(0x1B, 'd', lines);                  /* ESC d n */
}

/* ---------- Initialisation ---------- */

/* USART3 (PD8 = TX, PB11 = RX, 9600 8N1) est configure par CubeMX :
 * appeler MX_USART3_UART_Init() dans main.c avant TP_Init(). */
HAL_StatusTypeDef TP_Init(void)
{
    HAL_Delay(100);                                   /* laisse l'imprimante demarrer */

    const uint8_t esc_init[2] = { 0x1B, '@' };        /* ESC @ : reset */
    return tp_write(esc_init, 2);
}

/* ---------- Code-barres Code128 ---------- */

static HAL_StatusTypeDef tp_code128(const char *data)
{
    uint8_t buf[8 + TP_BARCODE_MAX_LEN + 2];
    size_t  len = strlen(data);
    HAL_StatusTypeDef st;

    if (len == 0 || len > TP_BARCODE_MAX_LEN) {
        return HAL_ERROR;
    }
    for (size_t i = 0; i < len; i++) {                /* ASCII imprimable seulement */
        if ((uint8_t)data[i] < 0x20 || (uint8_t)data[i] > 0x7E) {
            return HAL_ERROR;
        }
    }

    if ((st = tp_cmd(0x1D, 'h', 80)) != HAL_OK) return st;   /* GS h : hauteur 80 points */
    if ((st = tp_cmd(0x1D, 'w', 2))  != HAL_OK) return st;   /* GS w : largeur module 2   */
    if ((st = tp_cmd(0x1D, 'H', 2))  != HAL_OK) return st;   /* GS H : texte sous le code */

    /* GS k 73 n {B data  (Code128, jeu B : ASCII 32..127) */
    size_t i = 0;
    buf[i++] = 0x1D;
    buf[i++] = 'k';
    buf[i++] = 73;
    buf[i++] = (uint8_t)(len + 2);
    buf[i++] = '{';
    buf[i++] = 'B';
    memcpy(&buf[i], data, len);
    i += len;

    return tp_write(buf, (uint16_t)i);
}

/* ---------- Ticket ---------- */

HAL_StatusTypeDef TP_PrintTicket(uint32_t code6, const char *barcode, const TP_DateTime *dt)
{
    char line[48];
    HAL_StatusTypeDef st;

    if (barcode == NULL || dt == NULL || code6 > 999999UL) {
        return HAL_ERROR;
    }

    /* En-tete */
    if ((st = tp_align(1)) != HAL_OK) return st;
    if ((st = tp_bold(1))  != HAL_OK) return st;
    if ((st = tp_puts("TICKET\n")) != HAL_OK) return st;
    tp_bold(0);
    tp_puts("--------------------------------\n");

    /* Code a 6 chiffres en grand */
    tp_size(0x11);
    snprintf(line, sizeof(line), "%06lu\n", (unsigned long)code6);
    if ((st = tp_puts(line)) != HAL_OK) return st;
    tp_size(0x00);
    tp_puts("\n");

    /* Code-barres Code128 */
    if ((st = tp_code128(barcode)) != HAL_OK) return st;
    tp_puts("\n");

    /* Date et heure */
    tp_puts("--------------------------------\n");
    snprintf(line, sizeof(line), "%04u-%02u-%02u  %02u:%02u\n",
             (unsigned)dt->year, (unsigned)dt->month, (unsigned)dt->day,
             (unsigned)dt->hour, (unsigned)dt->minute);
    if ((st = tp_puts(line)) != HAL_OK) return st;

    /* Avance du papier pour pouvoir dechirer */
    tp_align(0);
    return tp_feed(4);
}
