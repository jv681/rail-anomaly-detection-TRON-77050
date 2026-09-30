import os

# 1. Restore board_camera.c
board_camera_code = r'''/**
 * board_camera.c
 * Real camera capture: IMX335 MIPI-CSI2 -> DCMIPP -> ISP -> RGB565 framebuffer
 * Targets STM32N6570-DK with onboard IMX335 5MP sensor.
 *
 * Pipeline:
 *   IMX335 (2592x1944 RAW10 RGGB via MIPI CSI-2)
 *   -> DCMIPP CSI Pipe1 (RAW10 input)
 *   -> DCMIPP Downsize (2592x1944 -> 320x320)
 *   -> DCMIPP Pixel Packer (RAW10 -> RGB565)
 *   -> DMA -> CAM_RAW_FB_ADDR (PSRAM)
 *
 * Output fed directly into the YOLO NPU input buffer after RGB565->float32 conversion.
 */
#include "board_camera.h"
#include "stm32n6xx_hal.h"
#include <string.h>
#include <stdint.h>
#include <tm/tmonitor.h>

/* ---- IMX335 Camera Control (I2C1 on PB8/PB9) ------------------------------ */
#define CAM_I2C_ADDR       0x34U   /* IMX335 7-bit I2C address */
#define NRST_CAM_PORT      GPIOC
#define NRST_CAM_PIN       GPIO_PIN_8
#define EN_CAM_PORT        GPIOD
#define EN_CAM_PIN         GPIO_PIN_2

static DCMIPP_HandleTypeDef s_hdcmipp;
static I2C_HandleTypeDef    s_hi2c1;
static volatile uint32_t    s_frame_count = 0;
static int                  s_cam_ok      = 0;

/* ---------------------------------------------------------------------------- */
/* IMX335 minimal register write (16-bit address, 8-bit data)                   */
/* ---------------------------------------------------------------------------- */
static int cam_write_reg(uint16_t reg, uint8_t val)
{
    uint8_t buf[3] = { (uint8_t)(reg >> 8), (uint8_t)(reg & 0xFF), val };
    return (HAL_I2C_Master_Transmit(&s_hi2c1, CAM_I2C_ADDR << 1, buf, 3, 100) == HAL_OK) ? 0 : -1;
}

/* ---------------------------------------------------------------------------- */
/* IMX335 register read                                                          */
/* ---------------------------------------------------------------------------- */
static int cam_read_reg(uint16_t reg, uint8_t *val)
{
    uint8_t addr[2] = { (uint8_t)(reg >> 8), (uint8_t)(reg & 0xFF) };
    if (HAL_I2C_Master_Transmit(&s_hi2c1, CAM_I2C_ADDR << 1, addr, 2, 100) != HAL_OK) return -1;
    return (HAL_I2C_Master_Receive(&s_hi2c1, CAM_I2C_ADDR << 1, val, 1, 100) == HAL_OK) ? 0 : -1;
}

/* ---------------------------------------------------------------------------- */
/* I2C1 Init for camera (PB8=SCL, PB9=SDA)                                      */
/* ---------------------------------------------------------------------------- */
static void cam_i2c_init(void)
{
    __HAL_RCC_I2C1_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Pin       = GPIO_PIN_8 | GPIO_PIN_9;
    gpio.Mode      = GPIO_MODE_AF_OD;
    gpio.Pull      = GPIO_NOPULL;
    gpio.Speed     = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = GPIO_AF4_I2C1;
    HAL_GPIO_Init(GPIOB, &gpio);

    s_hi2c1.Instance             = I2C1;
    s_hi2c1.Init.Timing          = 0x10909CEC; /* 100 kHz @ 64 MHz APB */
    s_hi2c1.Init.OwnAddress1     = 0;
    s_hi2c1.Init.AddressingMode  = I2C_ADDRESSINGMODE_7BIT;
    s_hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    s_hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    s_hi2c1.Init.NoStretchMode   = I2C_NOSTRETCH_DISABLE;
    HAL_I2C_Init(&s_hi2c1);
}

/* ---------------------------------------------------------------------------- */
/* IMX335 minimal init: 2592x1944 RAW10 RGGB10, 2-lane MIPI, 1188 Mbps/lane    */
/* ---------------------------------------------------------------------------- */
static int imx335_init(void)
{
    /* Power on camera */
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_OUTPUT_PP;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;

    /* EN_CAM: PD2 = HIGH */
    gpio.Pin = EN_CAM_PIN;
    HAL_GPIO_Init(EN_CAM_PORT, &gpio);
    HAL_GPIO_WritePin(EN_CAM_PORT, EN_CAM_PIN, GPIO_PIN_SET);

    /* NRST_CAM: PC8 = LOW then HIGH */
    gpio.Pin = NRST_CAM_PIN;
    HAL_GPIO_Init(NRST_CAM_PORT, &gpio);
    HAL_GPIO_WritePin(NRST_CAM_PORT, NRST_CAM_PIN, GPIO_PIN_RESET);
    HAL_Delay(10);
    HAL_GPIO_WritePin(NRST_CAM_PORT, NRST_CAM_PIN, GPIO_PIN_SET);
    HAL_Delay(20);

    /* Check chip ID */
    uint8_t id_h = 0, id_l = 0;
    if (cam_read_reg(0x3003, &id_h) != 0) return -1;
    if (cam_read_reg(0x3004, &id_l) != 0) return -1;
    uint16_t chip_id = ((uint16_t)id_h << 8) | id_l;
    tm_printf((UB *)"[Camera] IMX335 Chip ID: 0x%04X\n", chip_id);
    if (chip_id != 0x0800 && chip_id != 0x0816) {
        tm_printf((UB *)"[Camera] WARNING: Unexpected chip ID (expected 0x0800/0x0816)\n");
    }

    /* Standby -> Active sequence per IMX335 datasheet */
    cam_write_reg(0x3000, 0x01); /* standby */
    HAL_Delay(10);

    /* Configure 2-lane MIPI, 1188 Mbps */
    cam_write_reg(0x3001, 0x00); /* Master mode start */
    cam_write_reg(0x3002, 0x00);
    cam_write_reg(0x300C, 0x3B); /* MIPI output format */
    cam_write_reg(0x3030, 0x03); /* INCK = 74.25 MHz */

    /* Full resolution 2592x1944 */
    cam_write_reg(0x3031, 0x01);
    cam_write_reg(0x3032, 0x00);
    cam_write_reg(0x3033, 0x05); /* VMAX[7:0] = 0x05xx */
    cam_write_reg(0x3034, 0xB0); /* HMAX */

    /* Start streaming */
    cam_write_reg(0x3000, 0x00); /* Operating */
    HAL_Delay(30);

    return 0;
}

/* ---------------------------------------------------------------------------- */
/* DCMIPP Init: CSI-2 RAW10 -> Downsize to 320x320 -> RGB565 output             */
/* ---------------------------------------------------------------------------- */
static int dcmipp_init(void)
{
    DCMIPP_PipeConfTypeDef      pipe_cfg   = {0};
    DCMIPP_CSI_PIPE_ConfTypeDef csi_pipe   = {0};
    DCMIPP_CSI_ConfTypeDef      csi_cfg    = {0};
    DCMIPP_DownsizeTypeDef      downsize   = {0};

    __HAL_RCC_DCMIPP_CLK_ENABLE();

    s_hdcmipp.Instance = DCMIPP;
    if (HAL_DCMIPP_Init(&s_hdcmipp) != HAL_OK) return -1;

    /* CSI-2: 2 data lanes, 1188 Mbps bitrate */
    csi_cfg.DataLaneMapping = DCMIPP_CSI_PHYSICAL_DATA_LANES;
    csi_cfg.NumberOfLanes   = DCMIPP_CSI_TWO_DATA_LANES;
    csi_cfg.PHYBitrate      = DCMIPP_CSI_PHY_BT_1600;
    if (HAL_DCMIPP_CSI_SetConfig(&s_hdcmipp, &csi_cfg) != HAL_OK) return -2;

    /* Virtual channel 0: RAW10 */
    if (HAL_DCMIPP_CSI_SetVCConfig(&s_hdcmipp, DCMIPP_VIRTUAL_CHANNEL0, DCMIPP_CSI_DT_BPP10) != HAL_OK) return -3;

    /* CSI Pipe 1: RAW10 input */
    csi_pipe.DataTypeMode = DCMIPP_DTMODE_DTIDA;
    csi_pipe.DataTypeIDA  = DCMIPP_DT_RAW10;
    csi_pipe.DataTypeIDB  = DCMIPP_DT_RAW10;
    if (HAL_DCMIPP_CSI_PIPE_SetConfig(&s_hdcmipp, DCMIPP_PIPE1, &csi_pipe) != HAL_OK) return -4;

    /* Pipe output: RGB565, pitch = 320*2 = 640 bytes */
    pipe_cfg.FrameRate         = DCMIPP_FRAME_RATE_ALL;
    pipe_cfg.PixelPackerFormat = DCMIPP_PIXEL_PACKER_FORMAT_RGB565_1;
    pipe_cfg.PixelPipePitch    = CAM_CAPTURE_W * 2;
    if (HAL_DCMIPP_PIPE_SetConfig(&s_hdcmipp, DCMIPP_PIPE1, &pipe_cfg) != HAL_OK) return -5;

    /* Downsize: 2592x1944 -> 320x320
     * HRatio = (2592 << 16) / 320 = 532480  (but DCMIPP uses fixed-point 1.16 format)
     * Use the ratio values from the reference: HRatio = input/output * 256
     */
    downsize.HRatio     = (uint32_t)((2592UL * 1024UL) / 320UL);  /* ~8294 */
    downsize.VRatio     = (uint32_t)((1944UL * 1024UL) / 320UL);  /* ~6220 */
    downsize.HSize      = CAM_CAPTURE_W;
    downsize.VSize      = CAM_CAPTURE_H;
    downsize.HDivFactor = 1;
    downsize.VDivFactor = 1;
    if (HAL_DCMIPP_PIPE_SetDownsizeConfig(&s_hdcmipp, DCMIPP_PIPE1, &downsize) != HAL_OK) return -6;
    if (HAL_DCMIPP_PIPE_EnableDownsize(&s_hdcmipp, DCMIPP_PIPE1) != HAL_OK) return -7;

    /* Enable DCMIPP frame interrupt */
    NVIC_SetPriority(DCMIPP_IRQn, 5);
    NVIC_EnableIRQ(DCMIPP_IRQn);

    return 0;
}

/* ---------------------------------------------------------------------------- */
/* DCMIPP Frame complete IRQ handler                                              */
/* ---------------------------------------------------------------------------- */
void DCMIPP_IRQHandler(void)
{
    HAL_DCMIPP_IRQHandler(&s_hdcmipp);
}

/* Callback fired when a frame is captured */
void HAL_DCMIPP_PIPE_FrameEventCallback(DCMIPP_HandleTypeDef *hdcmipp, uint32_t Pipe)
{
    (void)hdcmipp; (void)Pipe;
    s_frame_count++;
}

/* ---------------------------------------------------------------------------- */
/* Public API                                                                    */
/* ---------------------------------------------------------------------------- */
int board_camera_init(void)
{
    tm_printf((UB *)"[Camera] Initializing IMX335 + DCMIPP pipeline...\n");

    cam_i2c_init();

    if (imx335_init() != 0) {
        tm_printf((UB *)"[Camera] IMX335 init FAILED — using synthetic frames\n");
        return -1;
    }

    if (dcmipp_init() != 0) {
        tm_printf((UB *)"[Camera] DCMIPP init FAILED — using synthetic frames\n");
        return -2;
    }

    /* Start continuous capture into PSRAM framebuffer */
    if (HAL_DCMIPP_CSI_PIPE_Start(&s_hdcmipp, DCMIPP_PIPE1,
                                   DCMIPP_VIRTUAL_CHANNEL0,
                                   CAM_RAW_FB_ADDR,
                                   DCMIPP_MODE_CONTINUOUS) != HAL_OK) {
        tm_printf((UB *)"[Camera] DCMIPP start FAILED\n");
        return -3;
    }

    /* Wait for first 3 frames to ensure ISP (if any) has settled */
    uint32_t t0 = HAL_GetTick();
    while (s_frame_count < 3 && (HAL_GetTick() - t0) < 500) {
        __WFE();
    }

    s_cam_ok = (s_frame_count >= 3) ? 1 : 0;
    tm_printf((UB *)"[Camera] %s (frames captured: %u)\n",
              s_cam_ok ? "Real camera READY" : "Timeout — synthetic fallback",
              (unsigned)s_frame_count);
    return s_cam_ok ? 0 : -4;
}

int board_camera_is_ready(void)
{
    return s_cam_ok;
}

/**
 * Copy the latest frame from the DCMIPP framebuffer into buf.
 * DCMIPP outputs RGB565 packed (HWC), but our NPU needs RGB888 HWC uint8.
 * We convert RGB565->RGB888 here.
 * If camera failed, fall through to synthetic generator in main_task.c.
 */
void board_camera_capture_frame(uint8_t *buf, uint32_t w, uint32_t h)
{
    if (!s_cam_ok) return; /* synthetic path used in main_task.c */

    /* Invalidate D-Cache so CPU reads fresh pixels written by DCMIPP DMA into PSRAM */
    SCB_InvalidateDCache_by_Addr((volatile void *)CAM_RAW_FB_ADDR, (int32_t)(w * h * sizeof(uint16_t)));

    /* DCMIPP wrote RGB565 into CAM_RAW_FB_ADDR (320x320) */
    const uint16_t *src = (const uint16_t *)CAM_RAW_FB_ADDR;
    uint32_t pixels = (uint32_t)(w * h);

    for (uint32_t i = 0; i < pixels; i++) {
        uint16_t px = src[i];
        /* RGB565 -> RGB888 */
        uint8_t r = (uint8_t)(((px >> 11) & 0x1FU) * 255U / 31U);
        uint8_t g = (uint8_t)(((px >>  5) & 0x3FU) * 255U / 63U);
        uint8_t b = (uint8_t)(((px >>  0) & 0x1FU) * 255U / 31U);
        buf[i * 3 + 0] = r;
        buf[i * 3 + 1] = g;
        buf[i * 3 + 2] = b;
    }
}
'''

for p in [r'C:\Users\hasin\Downloads\mtk3bsp2_stm32n657\Appli\Application\board_camera.c', r'c:\Users\hasin\Downloads\rail anamoly\board_camera.c']:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(board_camera_code)
    print('Restored', p)
