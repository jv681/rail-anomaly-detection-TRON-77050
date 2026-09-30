# Rail Anomaly Detection — Operation Manual
### STM32N657 + µT-Kernel 3.0 + YOLOv8n Neural-ART
**Version 1.0 | Contest Submission Document**

---

## 1. System Overview

This application detects four railway defect classes in real time on the
STM32N657 development board using µT-Kernel 3.0 as the RTOS.

| Component | Role |
|---|---|
| Google Colab | Training (never runs on MCU) |
| STEdgeAI Core | Converts ONNX model to C code for Neural-ART |
| STM32CubeIDE | Builds and flashes the application |
| STM32N657-DK | Target board (Cortex-M55 + Neural-ART NPU) |
| µT-Kernel 3.0 | RTOS — task scheduling and IPC |

**Detected classes:** `crack`, `rail_defect`, `fastener_defect`, `obstacle`

---

## 2. Hardware Requirements

| Item | Specification |
|---|---|
| Board | STM32N657-DK (N6570-DK) |
| Camera | Frame input (320×320 RGB) |
| Flash | 64 MB external NOR (on-board) for model weights |
| SRAM | 4.2 MB internal — activations + buffers |
| Host PC | Windows / Linux with ST tools installed |
| USB cable | ST-LINK USB-C connector on DK board |

---

## 3. Software Prerequisites

Install on your **host PC** (not the MCU):

```
1. STM32CubeIDE >= 1.16
   https://www.st.com/en/development-tools/stm32cubeide.html

2. ST Edge AI Core (stedgeai CLI)
   https://www.st.com/en/development-tools/stedgeai-core.html
   Add to PATH:  export PATH=$PATH:/opt/stedgeai/bin

3. µT-Kernel 3.0 source (TRON Forum)
   https://www.tron.org/dl/en/
   Supports NUCLEO-N657X0 / N6570-DK via Secure Extension pack

4. Python 3.10+ (for training and export scripts)
   pip install ultralytics onnx onnxruntime onnxsim

5. STM32CubeProgrammer (for flashing)
   https://www.st.com/en/development-tools/stm32cubeprog.html
```

---

## 4. Build and Flash Procedure

### Step 1 — Train the model (Google Colab)
```
1. Open Colab: https://colab.research.google.com
2. Mount Google Drive
3. Run cells in order: Install → Download datasets → Merge+Train
4. Training saves best_v5_FINAL.pt to Drive automatically
   (checkpoint every 10 epochs as fallback)
```

### Step 2 — Export to ONNX (Colab or PC)
```python
# In Colab (after training):
!python export_stm32.py

# Outputs:
#   models_stm32/yolov8n_rail_320px_sim.onnx   <- primary
#   models_stm32/yolov8n_rail_256px_sim.onnx   <- smaller footprint
#   models_stm32/yolov8n_rail_320px_int8.onnx  <- pre-quantized reference
```

### Step 3 — Generate C code with STEdgeAI
```bash
# On host PC, after installing STEdgeAI Core:

# Analyse model first
stedgeai analyze \
    --model models_stm32/yolov8n_rail_320px_sim.onnx \
    --target stm32n6 --series n6 \
    --workspace ./stedgeai_output

# Review the analysis output for:
#   - Estimated RAM / Flash usage
#   - Layers mapped to Neural-ART vs CPU fallback
#   - Any unsupported operators

# Generate C inference library
stedgeai generate \
    --model models_stm32/yolov8n_rail_320px_sim.onnx \
    --target stm32n6 --series n6 \
    --workspace ./stedgeai_output \
    --output   ./stedgeai_output/c_code \
    --compression lossless \
    --quantize int8 \
    --calibration-images /path/to/merged_v5_pro/images/train

# Generated files:
#   stedgeai_output/c_code/network.c
#   stedgeai_output/c_code/network.h
#   stedgeai_output/c_code/network_data.c   <- flash weights
#   stedgeai_output/c_code/network_data.h
#   stedgeai_output/c_code/ai_platform.h
```

### Step 4 — Set up µT-Kernel 3.0 project
```
1. Download µT-Kernel 3.0 source from TRON Forum
2. Apply the STM32N657 Secure Extension board support package
3. In STM32CubeIDE:
   - New > C Project > Makefile Project with Existing Code
   - Point to µT-Kernel 3.0 root
4. Add to project:
   - stedgeai_output/c_code/*.c and *.h
   - mtkernel_app/main_task.c
   - mtkernel_app/yolo_parser.c
   - mtkernel_app/yolo_parser.h
5. Linker script: ensure network_data.c section goes to FLASH
   Add to linker script:
       .nn_weights (NOLOAD) : { *network_data.o(.rodata) } > FLASH
```

### Step 5 — Build
```
1. STM32CubeIDE > Project > Build All
2. Expected binary size:
   - Code + data in SRAM: < 200 KB
   - Model weights in Flash: ~3.1 MB
3. Verify no linker errors for SRAM overflow
   (SRAM limit: 4,200 KB)
```

### Step 6 — Flash and Run
```
Method A — STM32CubeIDE:
  Run > Run Configurations > STM32 C/C++ Application
  > Select STM32N657-DK target > Apply > Run

Method B — STM32CubeProgrammer CLI:
  STM32_Programmer_CLI -c port=SWD -d build/rail_detect.elf
  STM32_Programmer_CLI -c port=SWD -startAll

Method C — drag-and-drop (if USB mass storage enabled):
  Copy build/rail_detect.bin to the board's USB drive
```

---

## 5. Runtime Operation

Once flashed, the board operates as follows:

```
Boot
 |
 +--> usermain()        (µT-Kernel entry)
 |      |
 |      +--> Creates mailbox, semaphore
 |      +--> Creates 3 tasks, starts them
 |
 +--> CameraTask        (priority 4, highest)
 |      Generates 320x320 RGB frame
 |      Normalises to float32 [0,1]
 |      Signals InferenceTask
 |
 +--> InferenceTask     (priority 5)
 |      Calls ai_network_run() -> Neural-ART NPU
 |      ~15-25 ms per frame
 |      Calls yolo_decode() on Cortex-M55
 |      Sends detections to AlertTask via mailbox
 |
 +--> AlertTask         (priority 6, lowest)
        Receives detections from mailbox
        Sends JSON over UART at 115200 baud:
          {"class":"crack","conf":0.72,"x1":45.2,...}
        Controls LEDs / buzzer per class
```

### UART Output Format
Connect a USB-UART adapter to USART1 (PA9/PA10 on DK board), 115200 baud:
```json
{"class":"obstacle","conf":0.91,"x1":12.5,"y1":33.0,"x2":180.2,"y2":290.1}
{"class":"crack","conf":0.73,"x1":88.0,"y1":120.5,"x2":210.0,"y2":145.0}
```
The companion `bridge.py` on PC reads this and updates the web dashboard.

---

## 6. Performance Targets

| Metric | Target | How achieved |
|---|---|---|
| Inference latency | < 30 ms/frame | Neural-ART NPU + INT8 |
| SRAM usage | < 4,200 KB | 320px input, layer-by-layer activation reuse |
| Flash usage | < 5 MB | ~3.1 MB INT8 weights + ~200 KB code |
| Power (idle) | < 50 mW | µT-Kernel task sleep between inferences |
| Power (active) | < 300 mW | NPU active only during ai_network_run() |

---

## 7. Attribution and Licensing

All third-party software used in this project:

| Software | Rights Holder | License | How Obtained |
|---|---|---|---|
| µT-Kernel 3.0 | TRON Forum | BSD-3-Clause | https://www.tron.org/dl/en/ |
| YOLOv8n (architecture) | Ultralytics | AGPL-3.0 | pip install ultralytics |
| ST Edge AI Core | STMicroelectronics | SLA0044 (free for ST products) | st.com/stedgeai-core |
| STM32Cube firmware | STMicroelectronics | SLA0044 | STM32CubeMX |
| ONNX Runtime | Microsoft | MIT | pip install onnxruntime |
| onnxsim | daquexian | MIT | pip install onnxsim |

**Datasets used for training:**

| Dataset | Rights Holder | License | Source |
|---|---|---|---|
| Railway Crack Detection v19 | Thesis Group | CC BY 4.0 | Roboflow Universe |
| Railway Track Defect Detection | Model Train NP | CC BY 4.0 | Roboflow Universe |
| Deteccão Fixações Trilhos | TrilhosObjectDetection | CC BY 4.0 | Roboflow Universe |
| Railway Track Obstacle Detection | Railway Research | CC BY 4.0 | Roboflow Universe |

> **Note on YOLOv8n AGPL-3.0:** The AGPL-3.0 licence requires that any
> application using YOLOv8 and distributed publicly must release its source
> code. For a closed contest submission, discuss with organisers whether an
> Ultralytics commercial licence is required. The trained weights (.pt file)
> produced by training are subject to the same licence as the architecture.

---

## 8. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `ai_network_create failed` | Weights not in flash section | Check linker script `.nn_weights` section |
| `No images found` (Colab) | Runtime reset, data lost | Re-run download + merge cells |
| SRAM overflow at link | Activation buffers too large | Switch to 256px export |
| UART output garbled | Baud rate mismatch | Set terminal to 115200 8N1 |
| Low mAP on fastener | Class mapping was wrong | Use v5 training with FASTENER_MAP |
| STEdgeAI unsupported op | SiLU not mapped | Add `--fallback-cpu` flag to generate |

---

*Document generated for contest submission. All training code runs on
Google Colab only. The µT-Kernel 3.0 API is not modified.*
