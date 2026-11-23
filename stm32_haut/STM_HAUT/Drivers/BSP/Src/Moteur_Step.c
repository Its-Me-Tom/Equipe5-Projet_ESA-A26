
#include "Moteur_Step.h"


typedef struct
{
    uint32_t remaining_steps;
    uint32_t next_tick;
    uint32_t step_period;
    uint8_t active;
    uint8_t pulse_high;

} StepperState;


// One state per motor
static StepperState motor_ASC = {0};
static StepperState motor_ROT = {0};


// Get motor state
static StepperState* GetMotorState(StepperMotor motor)
{
    switch(motor)
    {
        case Moteur_ASC:
            return &motor_ASC;

        case Moteur_ROT:
            return &motor_ROT;

        default:
            return NULL;
    }
}


// Configure motor direction
static void SetDirection(StepperMotor motor,
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


// Configure STEP output
static void SetStepPin(StepperMotor motor,
                       GPIO_PinState state)
{
    switch(motor)
    {
        case Moteur_ASC:
            HAL_GPIO_WritePin(MOTEUR_ASC_STEP_PORT,
                              MOTEUR_ASC_STEP_PIN,
                              state);
            break;

        case Moteur_ROT:
            HAL_GPIO_WritePin(MOTEUR_ROT_STEP_PORT,
                              MOTEUR_ROT_STEP_PIN,
                              state);
            break;

        default:
            break;
    }
}


// Start movement
void Stepper_StartMove(StepperMotor motor,
                       uint32_t steps,
                       GPIO_PinState direction,
                       uint32_t step_period_ms)
{
    StepperState* state = GetMotorState(motor);

    if(state == NULL || state->active || steps == 0)
        return;

    // Minimum 2 ms between rising edges
    if(step_period_ms < 2)
        step_period_ms = 2;

    SetDirection(motor, direction);

    SetStepPin(motor, GPIO_PIN_RESET);

    state->remaining_steps = steps;
    state->step_period = step_period_ms;
    state->pulse_high = 0;
    state->active = 1;

    // First pulse after 1 ms
    state->next_tick = HAL_GetTick() + 1;
}


// Update motor states
void Stepper_Update(void)
{
    uint32_t now = HAL_GetTick();

    for(uint8_t i = 0; i < 2; i++)
    {
        StepperMotor motor = (StepperMotor)i;
        StepperState* state = GetMotorState(motor);

        if(!state->active)
            continue;

        // Check if it is time for the next action
        if((int32_t)(now - state->next_tick) < 0)
            continue;

        if(!state->pulse_high)
        {
            // Generate rising edge
            SetStepPin(motor, GPIO_PIN_SET);

            state->pulse_high = 1;
            state->next_tick = now + STEP_PULSE_WIDTH_MS;
        }
        else
        {
            // Generate falling edge
            SetStepPin(motor, GPIO_PIN_RESET);

            state->pulse_high = 0;
            state->remaining_steps--;

            if(state->remaining_steps == 0)
            {
                state->active = 0;
            }
            else
            {
                state->next_tick = now +
                                   (state->step_period -
                                    STEP_PULSE_WIDTH_MS);
            }
        }
    }
}


// Check if motor is moving
uint8_t Stepper_IsBusy(StepperMotor motor)
{
    StepperState* state = GetMotorState(motor);

    if(state == NULL)
        return 0;

    return state->active;
}
