/*
 * Module_ROT.h
 *
 *  Created on: 24 nov. 2026
 *      Author: 2461496
 */

#ifndef BSP_INC_MODULE_ROT_H_
#define BSP_INC_MODULE_ROT_H_

#include "main.h"
#include "Types_Communs.h"
#include "Moteur_Step.h"

typedef enum {
	ROT_REF_INCONNUE, ROT_REF_MANUELLE, ROT_REF_CAPTEUR
} RotationReference;



void Rotation_Init(void);
MouvementDemarrage Rotation_DeplacerVers(uint8_t position, uint8_t *Pos_Act); //0 a 7
// bool Rotation_ConfirmerReferenceManuelle(void);
MouvementDemarrage Rotation_ReferencerAuto(void);
void Rotation_Arreter(void);
void Rotation_update(void);
MouvementEtat Rotation_ObtenirEtat(void);
uint8_t Rotation_ObtenirPosition(void); //0..7 ou 0xFF
RotationReference Rotation_ObtenirReference(void);
uint8_t Rotation_ObtenirDefaut(void);


#endif /* BSP_INC_MODULE_ROT_H_ */
