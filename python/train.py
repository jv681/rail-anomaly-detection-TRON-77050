"""
train.py
--------
Train YOLOv8n on the merged rail defect dataset.
Optimized for STM32N657-DK deployment.

Run in Google Colab or on a PC with GPU:
    python train.py

Requirements:
    pip install ultralytics
"""

from ultralytics import YOLO
import torch
import os

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DATA_YAML   = "merged_dataset/data.yaml"   # path to your merged dataset yaml
MODEL       = "yolov8n.pt"                 # YOLOv8 nano — smallest, best for STM32
IMG_SIZE    = 320                          # 320x320 required for STM32 deployment
EPOCHS      = 100
BATCH       = 16
PROJECT     = "runs/rail_detect"
NAME        = "yolov8n_rail_v1"
DEVICE      = 0 if torch.cuda.is_available() else "cpu"

print(f"🖥️  Using device: {'GPU ✅' if DEVICE == 0 else 'CPU ⚠️ (slow)'}")
print(f"📊  Dataset: {DATA_YAML}")
print(f"🧠  Model  : {MODEL} | Size: {IMG_SIZE}x{IMG_SIZE}")

# ─────────────────────────────────────────────
# TRAIN
# ─────────────────────────────────────────────
model = YOLO(MODEL)

results = model.train(
    data        = DATA_YAML,
    epochs      = EPOCHS,
    imgsz       = IMG_SIZE,
    batch       = BATCH,
    device      = DEVICE,
    project     = PROJECT,
    name        = NAME,
    # Augmentation (improves robustness on rail imagery)
    mosaic      = 1.0,
    flipud      = 0.3,
    fliplr      = 0.5,
    hsv_h       = 0.015,
    hsv_s       = 0.7,
    hsv_v       = 0.4,
    # Regularization
    dropout     = 0.0,
    weight_decay= 0.0005,
    # Logging
    plots       = True,
    save        = True,
    save_period = 10,
    verbose     = True,
)

print("\n✅ Training complete!")
best_model_path = f"{PROJECT}/{NAME}/weights/best.pt"
print(f"   Best model saved at: {best_model_path}")

# ─────────────────────────────────────────────
# VALIDATE
# ─────────────────────────────────────────────
print("\n🔍 Validating best model...")
model = YOLO(best_model_path)
metrics = model.val(data=DATA_YAML, imgsz=IMG_SIZE)

print(f"\n📈 Validation Results:")
print(f"   mAP50     : {metrics.box.map50:.3f}")
print(f"   mAP50-95  : {metrics.box.map:.3f}")
print(f"   Precision : {metrics.box.mp:.3f}")
print(f"   Recall    : {metrics.box.mr:.3f}")

print("\n➡️  Next step: run export_stm32.py to export for STM32 deployment")
