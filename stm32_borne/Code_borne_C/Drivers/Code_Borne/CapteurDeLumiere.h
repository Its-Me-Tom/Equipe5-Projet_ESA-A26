/*
 * CapteurDeLumiere.h
 *
 *  Created on: 17 nov. 2026
 *      Author: etudiant
 */

#ifndef CODE_BORNE_CAPTEURDELUMIERE_H_
#define CODE_BORNE_CAPTEURDELUMIERE_H_

#include <stdint.h>

/* Lit la photorésistance sur PC5 (ADC1_IN15) et retourne la valeur brute 12 bits (0..4095).
 * Retourne 0 en cas d'erreur de conversion. */
uint16_t LDR_Read(void);

#endif /* CODE_BORNE_CAPTEURDELUMIERE_H_ */
