# Rail Anomaly Detection System
## Real-Time Edge AI on STM32N6570-DK | μT-Kernel 3.0 | YOLOv8n INT8 | Neural-ART™ NPU

> **TRON Programming Contest 2026 Submission — Team ID: 77050**  
> **Repository:** [https://github.com/jv681/rail-anomaly-detection-TRON-77050](https://github.com/jv681/rail-anomaly-detection-TRON-77050)

---

## 📌 Project Overview

This project implements an autonomous, real-time edge AI railway track anomaly detection system running entirely on the **STM32N6570-DK** discovery board under **μT-Kernel 3.0 (TRON RTOS)** with hardware acceleration from the **Neural-ART™ NPU (600 MHz)**.

The system performs zero-cloud, on-device detection of critical rail safety hazards:
1. **Fastener Defect** (missing, loosened, or broken fasteners)
2. **Rail Crack** (surface fractures and structural cracks)
3. **Rail Defect** (squats, head checks, deformations)
4. **Obstacle** (foreign objects or debris on the track)

Visual overlays and real-time bounding boxes are rendered directly to the on-board **RK050HR18 5-inch DSI LCD (800×480)**, with telemetry streamed over UART to an optional remote web dashboard.

---

## 🗂️ Complete Source Code Structure

This repository contains the complete source code, drivers, RTOS BSP, bootloader, training scripts, tools, and documentation required to build, flash, and operate the project.

```
├── Appli/                                # Main Application Project (STM32CubeIDE)
│   ├── Application/                      # Core Application Source Code
│   │   ├── main_task.c                   # 3-task μT-Kernel Real-Time pipeline (Capture -> NPU -> Render)
│   │   ├── board_camera.c & .h           # Sony IMX335 (5MP MIPI CSI-2) + DCMIPP driver
│   │   ├── board_lcd.c & .h              # DSI LCD framebuffer rendering + bounding box overlay
│   │   ├── yolo_parser.c & .h            # YOLOv8n INT8 dequantization, box decoding, and NMS
│   │   ├── npu_hw_init.c & .h            # Neural-ART™ NPU hardware initialization & clock gating
│   │   ├── ll_aton*.c                    # ST LL-ATON NPU runtime engine & layer dispatchers
│   │   ├── imx335/                       # Sony IMX335 sensor I2C register configuration
│   │   └── isp/                          # DCMIPP Image Signal Processor configuration
│   ├── Core/                             # Application Core & System Initialization
│   │   ├── Inc/                          # Header files (main.h, stai_network.h, etc.)
│   │   ├── Src/                          # Source files (main.c, stm32n6xx_it.c, etc.)
│   │   └── Startup/                      # Startup assembly (startup_stm32n657x0hxq.s)
│   ├── Drivers/                          # Board drivers and peripheral support
│   ├── mtk3_bsp2/                        # μT-Kernel 3.0 Board Support Package & RTOS Kernel
│   │   ├── mtkernel/                     # μT-Kernel 3.0 core kernel source code
│   │   └── sysdepend/                    # STM32N657 Cortex-M55 CPU and BSP dependencies
│   ├── STM32N657X0HXQ_LRUN.ld            # Linker scripts for external memory execution
│   ├── mtk3bsp2_stm32n657_Appli.launch   # STM32CubeIDE Debug & Run configuration
│   ├── .project & .cproject              # STM32CubeIDE project definition
│   └── .settings/                        # Project IDE settings
│
├── FSBL/                                 # First Stage Boot Loader (FSBL) Project
│   ├── Core/                             # FSBL clock, MPU, and external memory initializers
│   ├── STM32N657X0HXQ_AXISRAM2_fsbl.ld   # FSBL linker script
│   └── .project & .cproject              # FSBL project files
│
├── Drivers/                              # Hardware Abstraction Layer & CMSIS Drivers
│   ├── CMSIS/                            # ARM CMSIS-Core (Cortex-M55)
│   └── STM32N6xx_HAL_Driver/             # ST HAL drivers for peripherals, NPU, DCMIPP, DSI
│
├── Middlewares/                          # ST External Memory Manager (STM32_ExtMem_Manager)
│   └── ST/STM32_ExtMem_Manager/          # XSPI Flash & PSRAM drivers (SFDP NOR, PSRAM)
│
├── Secure_nsclib/                        # Secure / Non-Secure callable interface definitions
│
├── flash_output/                         # Pre-built Flashable Binaries & Flash Scripts
│   ├── unlock.bin                        # Flash unlock utility (clears hardware write protection)
│   ├── fsbl-v10.bin                      # Pre-compiled FSBL binary (Target: 0x70000000)
│   ├── network_atonbuf.xSPI2.bin         # Neural-ART™ NPU model weights (Target: 0x70400000)
│   ├── appli-v16-lcd.bin                 # Application firmware with LCD display (Target: 0x70100000)
│   ├── appli-signed.bin                  # Signed application binary for secure boot
│   ├── flash_restore_lcd.ps1             # PowerShell script to flash all components in one step
│   └── recovery.ps1                      # Recovery script for board reset
│
├── python/                               # Model Training, Dataset, & Dashboard Scripts
│   ├── train.py                          # YOLOv8n training pipeline on combined rail anomaly dataset
│   ├── export_stm32.py                   # Export trained PyTorch model to ONNX & INT8 quantization
│   ├── merge_datasets.py                 # Multi-class rail dataset aggregation and augmentation
│   ├── bridge.py                         # UART serial to WebSocket/HTTP telemetry bridge
│   ├── requirements.txt                  # Python dependencies
│   └── dashboard/                        # Web telemetry dashboard (Flask + real-time charts)
│
├── docs/                                 # Documentation & Presentation Materials
│   ├── operation_manual.md & .docx       # Complete step-by-step Operation Manual
│   ├── submission_manual.md & .docx      # Official TRON Contest Submission Form & Document
│   └── presentation.html & .pptx         # Presentation slides (HTML format and PowerPoint PPTX)
│
├── mtk3bsp2_stm32n657.ioc                # STM32CubeMX Project Configuration file
├── .project & .mxproject                 # Root STM32CubeIDE multi-project workspace files
└── README.md                             # This documentation
```

---

## ⚡ Quick Flashing Guide (No Rebuild Required)

To flash the working firmware directly to the STM32N6570-DK board:

1. Connect the STM32N6570-DK discovery board via the **ST-LINK USB-C port (CN1)**.
2. Open PowerShell in the `flash_output/` directory:
   ```powershell
   cd flash_output
   .\flash_restore_lcd.ps1
   ```
3. The script automatically executes STM32CubeProgrammer:
   - **Step 1:** Erases external flash and uploads `unlock.bin` to remove write protection.
   - **Step 2:** Programs FSBL (`fsbl-v10.bin`) to external flash base `0x70000000`.
   - **Step 3:** Programs NPU model weights (`network_atonbuf.xSPI2.bin`) to `0x70400000`.
   - **Step 4:** Programs Application firmware (`appli-v16-lcd.bin`) to `0x70100000`.
4. Press the **Black Reset Button (B2)** on the board.
   - The on-board LCD will display camera initialization followed by the live 800×480 inspection view with real-time bounding boxes.

---

## 🛠️ Building with STM32CubeIDE

To build the source code from scratch:

1. Launch **STM32CubeIDE** (v1.17.0 or newer).
2. Click **File -> Open Projects from File System...**
3. Select this repository directory (`rail-anomaly-detection-TRON-77050`).
4. STM32CubeIDE will detect the root project and its subprojects:
   - `mtk3bsp2_stm32n657` (Workspace root)
   - `mtk3bsp2_stm32n657_Appli` (`Appli/`)
   - `mtk3bsp2_stm32n657_FSBL` (`FSBL/`)
5. Right-click `mtk3bsp2_stm32n657_FSBL` -> **Build Project**.
6. Right-click `mtk3bsp2_stm32n657_Appli` -> **Build Project**.
7. The output ELF/BIN files will be generated in `Appli/Debug/` and `FSBL/Debug/`.

---

## ⚙️ RTOS Architecture (μT-Kernel 3.0)

The application utilizes the **μT-Kernel 3.0** real-time kernel (`Appli/mtk3_bsp2/`) to manage concurrent real-time processing tasks:

| Task Name | Priority | Stack Size | Function |
|---|---|---|---|
| `tsk_camera` | High (10) | 4 KB | Captures 1080p frames from Sony IMX335 via DCMIPP ISP hardware resizing |
| `tsk_npu` | Medium (12) | 16 KB | Feeds preprocessed 320×320 frame into Neural-ART™ NPU; runs INT8 inference |
| `tsk_display` | Normal (14) | 8 KB | Post-processes YOLO detections (NMS) and updates DSI LCD framebuffer & UART |

Synchronized via μT-Kernel event flags and mailboxes to guarantee deterministic latency under 33 ms per frame (>30 FPS).

---

## 📄 License & Attribution

- Application code, YOLO parser, and pipeline: **TRON Contest 2026 Submission (Team ID: 77050)**.
- Operating System: **μT-Kernel 3.0** — Licensed under the T-License 2.0 / TRON Forum.
- Hardware Drivers & NPU Runtime: **STMicroelectronics** — BSD 3-Clause / ST Liberty License.
