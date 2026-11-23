
#include "Moteur_Step.h"


// Set motor direction
void Stepper_SetDirection(StepperMotor motor,
                          GPIO_PinState direction)
{
    switch(motor)
    {
        case Moteur_ASC:
            HAL_GPIO_WritePin(MOTEUR_ASC_DIR_PORT,
                              MOTEUR_ASC_DIR_PIN,
                              direction);
            break;

        case Moteur_ROT:
            HAL_GPIO_WritePin(MOTEUR_ROT_DIR_PORT,
                              MOTEUR_ROT_DIR_PIN,
                              direction);
            break;

        default:
            break;
    }
}


// Generate one STEP pulse
void Stepper_Step(StepperMotor motor)
{
    switch(motor)
    {
        case Moteur_ASC:

            HAL_GPIO_WritePin(MOTEUR_ASC_STEP_PORT,
                              MOTEUR_ASC_STEP_PIN,
                              GPIO_PIN_SET);

            HAL_Delay(1);

            HAL_GPIO_WritePin(MOTEUR_ASC_STEP_PORT,
                              MOTEUR_ASC_STEP_PIN,
                              GPIO_PIN_RESET);

            HAL_Delay(1);

            break;


        case Moteur_ROT:

            HAL_GPIO_WritePin(MOTEUR_ROT_STEP_PORT,
                              MOTEUR_ROT_STEP_PIN,
                              GPIO_PIN_SET);

            HAL_Delay(1);

            HAL_GPIO_WritePin(MOTEUR_ROT_STEP_PORT,
                              MOTEUR_ROT_STEP_PIN,
                              GPIO_PIN_RESET);

            HAL_Delay(1);

            break;


        default:
            break;
    }
}


// Move motor a certain number of steps
void Stepper_Move(StepperMotor motor,
                  uint32_t steps,
                  GPIO_PinState direction,
                  uint32_t delay_ms)
{
    Stepper_SetDirection(motor, direction);

    HAL_Delay(1);

    for(uint32_t i = 0; i < steps; i++)
    {
        Stepper_Step(motor);

        HAL_Delay(delay_ms);
    }
}
