#ifndef BOARD_LCD_H
#define BOARD_LCD_H

#include <stdint.h>
#include <stdbool.h>
#include "yolo_parser.h"

#define LCD_WIDTH   800
#define LCD_HEIGHT  480
#define LCD_FB_ADDR 0x90400000UL /* Located in 32MB Octal PSRAM */

/* Colors in RGB565 */
#define LCD_COLOR_BLACK       0x0000
#define LCD_COLOR_NAVY        0x000F
#define LCD_COLOR_DARKBLUE    0x0113
#define LCD_COLOR_DARKGREEN   0x03E0
#define LCD_COLOR_DARKCYAN    0x03EF
#define LCD_COLOR_MAROON      0x7800
#define LCD_COLOR_PURPLE      0x780F
#define LCD_COLOR_OLIVE       0x7BE0
#define LCD_COLOR_LIGHTGREY   0xC618
#define LCD_COLOR_DARKGREY    0x39E7
#define LCD_COLOR_BLUE        0x001F
#define LCD_COLOR_GREEN       0x07E0
#define LCD_COLOR_CYAN        0x07FF
#define LCD_COLOR_RED         0xF800
#define LCD_COLOR_MAGENTA     0xF81F
#define LCD_COLOR_YELLOW      0xFFE0
#define LCD_COLOR_WHITE       0xFFFF
#define LCD_COLOR_ORANGE      0xFD20
#define LCD_COLOR_BG_PANEL    0x08A4
#define LCD_COLOR_BG_HEADER   0x01A8

/* Initialize LCD hardware, LTDC controller, GPIOs, and backlight */
int board_lcd_init(void);
int board_lcd_is_ready(void);  /* 1 = LCD initialized OK */

/* Graphics primitives */
void board_lcd_clear(uint16_t color);
void board_lcd_draw_pixel(int x, int y, uint16_t color);
void board_lcd_fill_rect(int x, int y, int w, int h, uint16_t color);
void board_lcd_draw_rect(int x, int y, int w, int h, uint16_t color, int thickness);
void board_lcd_draw_char(int x, int y, char c, uint16_t color, uint16_t bg, int scale);
void board_lcd_draw_string(int x, int y, const char *str, uint16_t color, uint16_t bg, int scale);

/* High-level Railway Inspection Dashboard */
void board_lcd_draw_ui_base(void);
void board_lcd_draw_camera_feed(int x, int y, int w, int h, const float *tensor_f32);
void board_lcd_render_detections(int cam_x, int cam_y, int cam_w, int cam_h, const YoloResult_t *res);
void board_lcd_update_sidebar(uint32_t frame_num, float fps, const YoloResult_t *res);

#endif /* BOARD_LCD_H */
