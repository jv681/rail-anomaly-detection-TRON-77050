# Rail Anomaly Detection System
## Real-Time Edge AI on STM32N6570-DK | uT-Kernel 3.0 | YOLOv8n INT8 | Neural-ART NPU

A **real-time railway anomaly detection system** running entirely on STM32N6570-DK embedded board.
No PC. No cloud. Fully standalone edge AI inference.

Detects 4 anomaly classes: crack, rail_defect, fastener_defect, obstacle

## Key Specs
- MCU: STM32N6570 (Cortex-M55 + Neural-ART NPU)
- RTOS: uT-Kernel 3.0
- Model: YOLOv8n INT8 - 72% mAP@0.5 - 22-30 ms/frame
- Output: UART JSON alerts + LED indicators + Flask web dashboard

## Quick Flash (PowerShell)
1. Hold black RESET button on board
2. Run: .\flash_output\flash_restore_lcd.ps1
3. Release RESET, open Tera Term COM9 @ 115200 baud

## Web Dashboard
python bridge.py --port COM9 --baud 115200
cd python/dashboard && python app.py
Open: http://localhost:5000

## Structure
- firmware/Application/ - main_task.c, yolo_parser.c, npu_hw_init.c, board_camera.c
- flash_output/         - fsbl-v10.bin, appli-signed.bin, flash script
- python/               - train.py, bridge.py, dashboard/
- docs/                 - operation_manual.md, submission_manual.md, presentation.html
