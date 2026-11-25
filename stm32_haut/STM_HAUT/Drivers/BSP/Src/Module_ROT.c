#include "Module_ROT.h"
#include "Types_Communs.h"
#include "Moteur_Step.h"
#include "main.h"

void Rotation_Init(void)
{

}

MouvementDemarrage Rotation_DeplacerVers(uint8_t position, uint8_t *Pos_Act)
{
    // Vérification des paramètres
    if (Pos_Act == NULL || position > 7 || *Pos_Act > 7)
    {
        return MVT_REFUSE;
    }

    // Vérification de l'état du moteur
    if (Stepper_IsBusy(Moteur_ROT))
    {
        return MVT_REFUSE;
    }

    uint8_t position_calcul;
    uint32_t steps;
    GPIO_PinState direction;

    // Départ depuis l'origine
    if (*Pos_Act == 0)
    {
        if (position == 0)
        {
            return MVT_ACCEPTE;
        }

        position_calcul = position;

        if (position <= 4)
        {
            direction = GPIO_PIN_RESET;
        }
        else
        {
            direction = GPIO_PIN_SET;
        }
    }

    // Retour vers l'origine
    else
    {
        // On doit obligatoirement retourner à 0
        if (position != 0)
        {
            return MVT_REFUSE;
        }

        position_calcul = *Pos_Act;

        if (position_calcul <= 4)
        {
            direction = GPIO_PIN_SET;
        }
        else
        {
            direction = GPIO_PIN_RESET;
        }
    }

    // Calcul du nombre de pas
    if (position_calcul <= 4)
    {
        steps = position_calcul * 25;
    }
    else
    {
        steps = (8 - position_calcul) * 25;
    }

    // Démarrage du moteur
    Stepper_StartMove(
        Moteur_ROT,
        steps,
        direction,
        4
    );

    // Mise à jour de la position logique
    *Pos_Act = position;

    return MVT_ACCEPTE;
}
/*
bool Rotation_ConfirmerReferenceManuelle(void)
{

}

MouvementDemarrage Rotation_ReferencerAuto(void)
{

}

void Rotation_Arreter(void)
{

}

void Rotation_update(void)
{

}

MouvementEtat Rotation_ObtenirEtat(void)
{

}

uint8_t Rotation_ObtenirPosition(void) //0..7 ou 0xFF
{

}

RotationReference Rotation_ObtenirReference(void)
{

}

uint8_t Rotation_ObtenirDefaut(void)
{

}
*/


