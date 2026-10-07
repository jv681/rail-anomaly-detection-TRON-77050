# Rail Anomaly Detection System
## Real-Time Edge AI on STM32N6570-DK | muT-Kernel 3.0 | YOLOv8n INT8 | Neural-ART NPU

> **TRON Programming Contest 2026 Submission - Team ID: 77050**

---

## Project Overview

This project implements a real-time, fully standalone railway anomaly detection system
running entirely on the STM32N6570-DK discovery board using the Neural-ART NPU and
muT-Kernel 3.0 RTOS. No PC or cloud connection is required during inference.

**Detected Anomaly Classes:**
- Fastener Defect (missing/loose rail fasteners)
- Rail Crack (surface cracks and micro-fractures)
- Rail Defect (structural deformations)
- Obstacle (debris or foreign objects on track)

---

## Repository Structure

    firmware/
      Application/
        main_task.c         <- KEY: 3-task muT-Kernel application
        board_camera.c      <- Sony IMX335 + DCMIPP camera driver
        yolo_parser.c       <- YOLOv8 decoder + NMS
        npu_hw_init.c       <- Neural-ART NPU hardware initialization
        ll_aton*.c          <- ST LL-ATON NPU runtime files
        imx335/             <- IMX335 sensor register driver
      Core/
        Src/main.c          <- STM32 HAL + muT-Kernel startup
      STM32N657X0HXQ_ROMxspi1.ld  (linker script)
      mtk3bsp2_stm32n657.ioc       (STM32CubeMX project config)

    FSBL/                   <- First-Stage Bootloader project
    Middlewares/            <- ST External Memory Manager
    flash_output/           <- Pre-built flash binaries (ready to use)
      fsbl-v10.bin          (flash to 0x70000000)
      appli-v16-lcd.bin     (flash to 0x70100000)
      unlock.bin            (run first - unlocks flash write protection)

    python/
      train.py              <- YOLOv8n training script
      export_stm32.py       <- ONNX export for ST Edge AI Core
      merge_datasets.py     <- 4-dataset merger
      bridge.py             <- UART to HTTP serial bridge
      dashboard/app.py      <- Flask web dashboard

    docs/
      operation_manual.md / .docx
      submission_manual.md / .docx
      presentation.html / .pptx

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Board | STM32N6570-DK Discovery Kit |
| MCU | Arm Cortex-M55 at 800 MHz |
| NPU | Neural-ART (dedicated on-chip AI accelerator) |
| RTOS | muT-Kernel 3.0 (TRON Forum) |
| AI Model | YOLOv8n INT8 quantized via ST Edge AI Core |
| AI Runtime | LL-ATON (ST low-level Neural-ART runtime) |
| Camera | Sony IMX335 5MP RAW10 via MIPI CSI-2 |
| Flash | 128 MB OctoSPI NOR (MX66UW1G45G) |
| PSRAM | 8 MB OctoSPI PSRAM |

---

## Software Architecture (3 muT-Kernel Tasks)

    CameraTask (priority 4 - highest)
      Acquires 320x320 RGB frame
      Normalizes to float32 [0.0, 1.0]
      -> signals InferenceTask via semaphore

    InferenceTask (priority 5)
      stai_network_run() on Neural-ART NPU (~22ms)
      Decodes 8400 detection boxes on Cortex-M55
      Runs IoU Non-Maximum Suppression
      -> enqueues result to AlertTask via mailbox

    AlertTask (priority 6)
      Streams structured JSON via UART at 115200 baud
      Controls onboard alert LEDs

---

## Flash Procedure (PowerShell)

    $cli = "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"
    $el  = "...bin\ExternalLoader\MX66UW1G45G_STM32N6570-DK.stldr"
    $out = ".\flash_output"

    # 1. Unlock flash write protection
    & $cli -c port=SWD freq=480 reset=HWrst -w "$out\unlock.bin" 0x20000200

    # 2. Flash FSBL bootloader
    & $cli -c port=SWD freq=480 reset=HWrst -el "$el" -d "$out\fsbl-v10.bin" 0x70000000 -v

    # 3. Flash Application
    & $cli -c port=SWD freq=480 reset=HWrst -el "$el" -d "$out\appli-v16-lcd.bin" 0x70100000 -v

    # 4. Flash NPU model weights (obtain separately - see note)
    & $cli -c port=SWD freq=480 reset=HWrst -el "$el" -d "network_atonbuf.xSPI2.bin" 0x71000000 -v

NOTE: network_atonbuf.xSPI2.bin (11.5 MB NPU weights) is not in this repo due to
GitHub 100 MB file limit. It is included in the submission Google Drive package.

---

## Expected UART Output (115200 baud, 8N1)

    [FSBL] PSRAM 0x90000000: Mapped & Tested OK!
    FSBL v10-ready
    Jumping to application...
    microT-Kernel Version 3.00
    === Rail Anomaly Detection v1.2 ===
    [Camera] Task started
    [NPU] Hardware initialized successfully
    [Inference] LL-ATON Ready. Starting live loop...
    {"class":"crack","conf":0.93,"x1":45.2,"y1":120.0,"x2":180.5,"y2":145.0}

---

## Performance Results

| Metric | Result |
|--------|--------|
| Inference Latency | 22 to 30 ms per frame |
| Throughput | more than 20 FPS |
| Overall mAP@0.5 | 72.3% |
| SRAM Usage | approx 1.5 MB (of 4.2 MB limit) |
| Model Size (INT8) | 11.5 MB |
| Boot to Inference | less than 3 seconds |

---

## Web Dashboard

    # Terminal 1 - Serial bridge
    python python/bridge.py --port COM9 --baud 115200

    # Terminal 2 - Dashboard
    cd python/dashboard && python app.py

    # Open browser: http://localhost:5000

---

## Training the AI Model

    pip install -r python/requirements.txt
    python python/merge_datasets.py     # merge 4 Roboflow datasets
    python python/train.py              # train YOLOv8n (100 epochs, 320x320)
    python python/export_stm32.py       # ONNX export for ST Edge AI Core

---

## Dataset

| Dataset | Images | Class |
|---------|--------|-------|
| Railway Crack Detection v19 | 2847 | crack |
| Track Defect Detection | 1923 | rail_defect |
| Fixacoes Trilhos | 1204 | fastener_defect |
| Obstacle Detection | 1521 | obstacle |
| Total | 7495 | 4 classes |

All datasets licensed CC BY 4.0 via Roboflow Universe.

---

## License
- Application source code (main_task.c, yolo_parser.c, board_camera.c, npu_hw_init.c): MIT
- muT-Kernel 3.0 BSP: TRON Forum Software License
- ST HAL Drivers and LL-ATON Runtime: BSD-3-Clause (STMicroelectronics)
- YOLOv8 model architecture: AGPL-3.0 (Ultralytics)

---
TRON Programming Contest 2026 | Submission 77050
