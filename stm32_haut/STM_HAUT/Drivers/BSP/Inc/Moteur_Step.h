/*
 * Moteur_Step.h
 *
 *  Created on: 23 nov. 2026
 *      Author: 2461496
 */

#ifndef BSP_INC_MOTEUR_STEP_H_
#define BSP_INC_MOTEUR_STEP_H_

#include "main.h"

// Moteur ASC (PD12 / PD13)
#define MOTEUR_ASC_STEP_PORT    GPIOD
#define MOTEUR_ASC_STEP_PIN     GPIO_PIN_12

#define MOTEUR_ASC_DIR_PORT     GPIOD
#define MOTEUR_ASC_DIR_PIN      GPIO_PIN_13

// Moteur ROT (PC4 / PB0)
#define MOTEUR_ROT_STEP_PORT    GPIOC
#define MOTEUR_ROT_STEP_PIN     GPIO_PIN_4

#define MOTEUR_ROT_DIR_PORT     GPIOB
#define MOTEUR_ROT_DIR_PIN      GPIO_PIN_0

// STEP pulse duration
#define STEP_PULSE_WIDTH_MS     1

typedef enum
{
    Moteur_ASC = 0,
    Moteur_ROT
} StepperMotor;


// Start a non-blocking movement
void Stepper_StartMove(StepperMotor motor,
                       uint32_t steps,
                       GPIO_PinState direction,
                       uint32_t step_period_ms);

// Update motor states (call continuously in main)
void Stepper_Update(void);

// Check whether a motor is moving
uint8_t Stepper_IsBusy(StepperMotor motor);


#endif /* BSP_INC_MOTEUR_STEP_H_ */
