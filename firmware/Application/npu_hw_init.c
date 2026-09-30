/**
 * npu_hw_init.c
 * -------------
 * Neural-ART NPU hardware initialization for STM32N6570-DK (STM32N657X0H3Q).
 *
 * The LL-ATON runtime requires:
 *   1. Neural-ART accelerator clock enabled
 *   2. AXISRAM clock enabled (input/output tensor DMA)
 *   3. Sleep/stop clock support configured
 *
 * Board LEDs on STM32N6570-DK:
 *   LD1 (Green)  = PE3  (active HIGH)
 *   LD2 (Red)    = PE0  (active HIGH)  -- schematic: J10 LED connector
 *
 * License: MIT | Rail Anomaly Detection Project
 */

#include "npu_hw_init.h"
#include <tm/tmonitor.h>

/* ── LED GPIO definitions (STM32N6570-DK schematic verified) ──────────────── */
#define LED_GREEN_PORT   GPIOE
#define LED_GREEN_PIN    GPIO_PIN_3
#define LED_RED_PORT     GPIOE
#define LED_RED_PIN      GPIO_PIN_0

/* ── npu_hw_init ─────────────────────────────────────────────────────────── */
void npu_hw_init(void)
{
    /* 1. Enable Neural-ART (LTDC/NPU bus) clock ----------------------------- */
    __HAL_RCC_NPU_CLK_ENABLE();
    __HAL_RCC_NPU_FORCE_RESET();
    __HAL_RCC_NPU_RELEASE_RESET();

    /* 2. Enable AXISRAM for NPU DMA tensors --------------------------------- */
    __HAL_RCC_AXISRAM1_MEM_CLK_ENABLE();
    __HAL_RCC_AXISRAM2_MEM_CLK_ENABLE();
    __HAL_RCC_AXISRAM3_MEM_CLK_ENABLE();

    /* 3. Enable sleep/stop clocks so NPU finishes during WFI --------------- */
    __HAL_RCC_NPU_CLK_SLEEP_ENABLE();
    __HAL_RCC_AXISRAM1_MEM_CLK_SLEEP_ENABLE();
    __HAL_RCC_AXISRAM2_MEM_CLK_SLEEP_ENABLE();
    __HAL_RCC_AXISRAM3_MEM_CLK_SLEEP_ENABLE();
    SCB->SCR |= SCB_SCR_SEVONPEND_Msk; /* Ensure pending events wake CPU */

    /* 4. Initialize LEDs ---------------------------------------------------- */
    __HAL_RCC_GPIOE_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_OUTPUT_PP;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;

    gpio.Pin = LED_GREEN_PIN;
    HAL_GPIO_Init(LED_GREEN_PORT, &gpio);
    HAL_GPIO_WritePin(LED_GREEN_PORT, LED_GREEN_PIN, GPIO_PIN_RESET);

    gpio.Pin = LED_RED_PIN;
    HAL_GPIO_Init(LED_RED_PORT, &gpio);
    HAL_GPIO_WritePin(LED_RED_PORT, LED_RED_PIN, GPIO_PIN_RESET);

    /* 5. Brief LED flash to show NPU init succeeded ------------------------- */
    HAL_GPIO_WritePin(LED_GREEN_PORT, LED_GREEN_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(LED_RED_PORT,   LED_RED_PIN,   GPIO_PIN_SET);
    HAL_Delay(200);
    HAL_GPIO_WritePin(LED_GREEN_PORT, LED_GREEN_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(LED_RED_PORT,   LED_RED_PIN,   GPIO_PIN_RESET);
}

/* ── board_led_green_toggle ─────────────────────────────────────────────── */
void board_led_green_toggle(void)
{
    HAL_GPIO_TogglePin(LED_GREEN_PORT, LED_GREEN_PIN);
}

/* ── board_led_red_set ──────────────────────────────────────────────────── */
void board_led_red_set(int on)
{
    HAL_GPIO_WritePin(LED_RED_PORT, LED_RED_PIN,
                      on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
