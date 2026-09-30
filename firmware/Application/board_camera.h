#ifndef BOARD_CAMERA_H
#define BOARD_CAMERA_H

#include <stdint.h>

/* Camera capture resolution after DCMIPP decimation */
#define CAM_CAPTURE_W   320
#define CAM_CAPTURE_H   320

/* Raw RGB888 frame buffer in PSRAM */
#define CAM_RAW_FB_ADDR  0x90200000UL
#define CAM_RAW_FB_SIZE  (CAM_CAPTURE_W * CAM_CAPTURE_H * 3U)

/* Initialize IMX335 + DCMIPP pipeline. Returns 0 on success. */
int  board_camera_init(void);

/* Capture one 320x320 RGB888 packed frame into buf. Blocks until done. */
void board_camera_capture_frame(uint8_t *buf, uint32_t w, uint32_t h);

/* Returns 1 if real camera OK, 0 if using synthetic fallback */
int  board_camera_is_ready(void);

#endif /* BOARD_CAMERA_H */
