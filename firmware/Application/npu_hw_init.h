/**
 * npu_hw_init.h
 * -------------
 * Neural Processing Unit hardware initialization for STM32N6570-DK.
 * Enables Neural-ART accelerator clocks and configures sleep/power modes.
 * Also provides board-level LED control primitives.
 */

#ifndef NPU_HW_INIT_H
#define NPU_HW_INIT_H

#include "stm32n6xx_hal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize Neural-ART NPU hardware clocks and power domains.
 *        Must be called before stai_network_init().
 *        Also initializes board LEDs (LD1 green = PE3, LD2 red = PE0 on STM32N6570-DK).
 */
void npu_hw_init(void);

/**
 * @brief Toggle the green status LED (LD1, PE3).
 *        Called every inference frame to show NPU is alive.
 */
void board_led_green_toggle(void);

/**
 * @brief Set the red alert LED (LD2, PE0).
 *        Called when an anomaly is detected.
 * @param on  1 = LED on, 0 = LED off
 */
void board_led_red_set(int on);

#ifdef __cplusplus
}
#endif

#endif /* NPU_HW_INIT_H */
