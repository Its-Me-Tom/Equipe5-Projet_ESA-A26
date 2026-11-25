/*
 * Types_Communs.h
 *
 *  Created on: 24 nov. 2026
 *      Author: 2461496
 */

#ifndef BSP_INC_TYPES_COMMUNS_H_
#define BSP_INC_TYPES_COMMUNS_H_

#include "main.h"
#include "Types_Communs.h"
#include "Moteur_Step.h"
#include "Module_ROT.h"

typedef enum {
	MVT_REFUSE, MVT_ACCEPTE
} MouvementDemarrage;

typedef enum {
	MVT_INACTIF, MVT_EN_COURS, MVT_TERMINE, MVT_INTERROMPU, MVT_DEFAUT
} MouvementEtat;

typedef enum {
	POSITION_INCONNUE, POSITION_ESTIMEE, REFERENCE_CAPTEUR_DETECTEE
} PositionFiabilite;

#endif /* BSP_INC_TYPES_COMMUNS_H_ */
