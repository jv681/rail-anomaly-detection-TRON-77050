"""
export_stm32.py
---------------
Stage 1 of STM32N657 deployment pipeline.

Flow:
    best.pt  ->  ONNX (FP32, 320px)   <- primary input to STEdgeAI
                 ONNX (FP32, 256px)   <- smaller footprint option
                 ONNX INT8 (320px)    <- pre-quantized reference

STEdgeAI converts the ONNX to C code targeting the Neural-ART
accelerator on STM32N657. Run on Colab or PC, NOT on the MCU.

Requirements (Colab cell):
    !pip install -q ultralytics onnx onnxruntime onnxsim
"""

import os, shutil, random
from pathlib import Path
import numpy as np

# ─────────────────────────────────────────────────────────────
# CONFIG — update paths after training finishes
# ─────────────────────────────────────────────────────────────
BEST_PT   = "/content/drive/MyDrive/rail_project_v2/v5pro_FINAL.pt"
DATA_YAML = "/content/merged_v5_pro/data.yaml"
CALIB_DIR = "/content/merged_v5_pro/images/train"
OUT       = Path("models_stm32")
OUT.mkdir(exist_ok=True)

CLASS_NAMES = ["crack", "rail_defect", "fastener_defect", "obstacle"]
SIZES       = {"320": 320, "256": 256}

# ─────────────────────────────────────────────────────────────
# STEP 1: ONNX export (FP32) at both sizes
# ─────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1: Exporting to ONNX (FP32)")
print("=" * 60)

from ultralytics import YOLO
model = YOLO(BEST_PT)

onnx_paths = {}
for tag, size in SIZES.items():
    print(f"\n  Exporting {size}x{size}...")
    model.export(
        format   = "onnx",
        imgsz    = size,
        opset    = 12,       # opset 12 = max compatibility with STEdgeAI
        simplify = True,
        dynamic  = False,    # static shape required for STM32
        half     = False,    # FP32 — STEdgeAI quantizes internally
    )
    src  = Path(BEST_PT).with_suffix(".onnx")
    dest = OUT / f"yolov8n_rail_{tag}px.onnx"
    shutil.copy2(src, dest)
    onnx_paths[tag] = dest
    print(f"  OK  Saved: {dest}  ({dest.stat().st_size/1e6:.2f} MB)")

# ─────────────────────────────────────────────────────────────
# STEP 2: Simplify ONNX graphs
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2: Simplifying ONNX graphs (onnxsim)")
print("=" * 60)
try:
    import onnx
    from onnxsim import simplify as onnxsim

    for tag, path in onnx_paths.items():
        m, ok = onnxsim(onnx.load(str(path)))
        if ok:
            sp = OUT / f"yolov8n_rail_{tag}px_sim.onnx"
            onnx.save(m, str(sp))
            onnx_paths[tag] = sp
            print(f"  OK  {tag}px simplified -> {sp.name}")
        else:
            print(f"  WARN  {tag}px simplification failed, using original")
except ImportError:
    print("  SKIP  onnxsim not installed. (pip install onnxsim)")

# ─────────────────────────────────────────────────────────────
# STEP 3: INT8 static quantization with calibration images
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: INT8 static quantization (onnxruntime)")
print("=" * 60)

try:
    from onnxruntime.quantization import (
        quantize_static, CalibrationDataReader,
        QuantFormat, QuantType
    )
    import cv2

    class RailCalibReader(CalibrationDataReader):
        def __init__(self, img_dir, input_name, size, n=200):
            imgs = (list(Path(img_dir).glob("*.jpg")) +
                    list(Path(img_dir).glob("*.png")))
            random.shuffle(imgs)
            self.imgs = imgs[:n]
            self.name = input_name
            self.size = size
            self.idx  = 0

        def get_next(self):
            if self.idx >= len(self.imgs):
                return None
            img = cv2.imread(str(self.imgs[self.idx]))
            img = cv2.resize(img, (self.size, self.size))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = img.astype(np.float32) / 255.0
            img = np.expand_dims(np.transpose(img, (2, 0, 1)), 0)  # NCHW
            self.idx += 1
            return {self.name: img}

    import onnxruntime as ort

    for tag, path in list(onnx_paths.items()):
        size     = SIZES[tag]
        inp_name = ort.InferenceSession(str(path)).get_inputs()[0].name
        qp       = OUT / f"yolov8n_rail_{tag}px_int8.onnx"
        quantize_static(
            str(path), str(qp),
            RailCalibReader(CALIB_DIR, inp_name, size),
            quant_format    = QuantFormat.QOperator,
            per_channel     = False,
            weight_type     = QuantType.QInt8,
            activation_type = QuantType.QInt8,
        )
        print(f"  OK  {tag}px INT8 -> {qp.name}  ({qp.stat().st_size/1e6:.2f} MB)")
except Exception as e:
    print(f"  WARN  INT8 quantization skipped: {e}")
    print("        STEdgeAI will quantize during code generation instead.")

# ─────────────────────────────────────────────────────────────
# STEP 4: Memory footprint estimate
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4: STM32N657 Memory Footprint Estimate")
print("=" * 60)
print(f"  {'Size':>6}  {'Weights(Flash)':>16}  {'ActRAM':>10}  {'InputBuf':>10}  {'TotalSRAM':>12}")
print("  " + "-" * 64)
for tag, size in SIZES.items():
    w_kb   = 3_200                                  # ~3.1 MB INT8 weights (flash)
    act_kb = (size//8) * (size//8) * 128 / 1024    # largest activation (SRAM)
    inp_kb = size * size * 3 / 1024
    tot_kb = act_kb + inp_kb
    flag   = "OK  fits" if tot_kb < 4096 else "WARN tight"
    print(f"  {size}px  {w_kb:>12,} KB  {act_kb:>8.0f} KB  "
          f"{inp_kb:>8.0f} KB  {tot_kb:>8.0f} KB  [{flag}]")

print("""
  Notes:
  - Weights live in external NOR flash (64 MB on DK board).
    Neural-ART fetches layer weights on-demand during inference.
  - Activations + input buffer must fit in 4,200 KB internal SRAM.
  - Estimated inference time: 15-25 ms per frame at 320px INT8.
""")

# ─────────────────────────────────────────────────────────────
# STEP 5: Neural-ART layer compatibility
# ─────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 5: Neural-ART Layer Compatibility")
print("=" * 60)
print("""
  Layer/Op               Neural-ART   CPU fallback  Notes
  ─────────────────────────────────────────────────────────
  Conv2d (all strides)   NPU                        Backbone + neck
  BatchNorm (fused)      NPU                        Fused at export
  C2f blocks             NPU                        Decomposes to Conv+Add
  SPPF (MaxPool)         NPU                        Supported pooling
  Concat                 NPU                        Memory permute
  Upsample (nearest)     partial      Yes           Resize fallback
  SiLU activation        approx       Partial       Approx as HardSwish
  Detect head (DFL)      No           Yes           Decode on Cortex-M55
  NMS                    No           Yes           Implemented in yolo_parser.c

  Expected NPU utilisation: ~85% (backbone+neck on Neural-ART,
  decode+NMS on Cortex-M55 Helium SIMD).
  Use --split-points in STEdgeAI to partition automatically.
""")

# ─────────────────────────────────────────────────────────────
# STEP 6: STEdgeAI CLI commands
# ─────────────────────────────────────────────────────────────
primary = OUT / "yolov8n_rail_320px_sim.onnx"
print("=" * 60)
print("STEP 6: STEdgeAI CLI Commands (run on PC)")
print("=" * 60)
print(f"""
# Download ST Edge AI Core from:
#   https://www.st.com/en/development-tools/stedgeai-core.html
# Add stedgeai to PATH, then:

# -- Analyse model (no code generated) ----------------------
stedgeai analyze \\
    --model {primary} \\
    --target stm32n6 --series n6 \\
    --workspace ./stedgeai_output

# -- Generate C inference library ---------------------------
stedgeai generate \\
    --model {primary} \\
    --target stm32n6 --series n6 \\
    --workspace ./stedgeai_output \\
    --output   ./stedgeai_output/c_code \\
    --compression lossless \\
    --quantize int8 \\
    --calibration-images {CALIB_DIR}

# -- Output files to copy into your uT-Kernel project ------
#   c_code/network.c          <- inference entry point
#   c_code/network.h
#   c_code/network_data.c     <- weights (place in flash section)
#   c_code/network_data.h
#   c_code/ai_platform.h      <- ST runtime types

# -- Key API (called from InferenceTask in main_task.c) ----
#   ai_network_create(NULL, &err)
#   ai_network_run(network_handle, &input_buf, &output_buf)
""")

print(f"Export complete. Output directory: {OUT.resolve()}")
