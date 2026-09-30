"""
merge_datasets.py
-----------------
Merges all 5 downloaded Roboflow YOLOv8 datasets into a single unified dataset.
Run this AFTER downloading datasets in Colab (or locally).

Usage:
    python merge_datasets.py

Output:
    merged_dataset/
        images/train/   images/val/   images/test/
        labels/train/   labels/val/   labels/test/
        data.yaml
"""

import os
import shutil
import yaml
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURE: map each dataset folder → its classes
# ─────────────────────────────────────────────
DATASET_CONFIGS = [
    {
        "path": "railway-crack-detection-19",   # Roboflow download folder name
        "classes": {0: "crack"},
    },
    {
        "path": "rail-track-defect-2",
        "classes": {0: "rail_defect", 1: "crack"},
    },
    {
        "path": "railway-track-defect-detection-xxtlx-1",
        "classes": {0: "rail_defect"},
    },
    {
        "path": "deteccao_fixacoes_trilhos-1",
        "classes": {0: "fastener_defect"},
    },
    {
        "path": "railway-track-obstacle-detection-gca3w-1",
        "classes": {0: "obstacle"},
    },
]

# Unified class list (final labels the model will learn)
UNIFIED_CLASSES = [
    "crack",            # 0
    "rail_defect",      # 1
    "fastener_defect",  # 2
    "obstacle",         # 3
    "broken_rail",      # 4
]

CLASS_TO_ID = {c: i for i, c in enumerate(UNIFIED_CLASSES)}

OUTPUT_DIR = Path("merged_dataset")
SPLITS = ["train", "valid", "test"]


def remap_label_file(src_path, dst_path, class_map: dict):
    """Read a YOLO label file and remap class IDs to unified IDs."""
    with open(src_path, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        old_id = int(parts[0])
        if old_id not in class_map:
            continue  # skip unknown classes
        new_id = CLASS_TO_ID[class_map[old_id]]
        new_lines.append(f"{new_id} " + " ".join(parts[1:]) + "\n")

    if new_lines:
        with open(dst_path, "w") as f:
            f.writelines(new_lines)


def merge():
    print("🔄 Starting dataset merge...")

    # Create output directories
    for split in SPLITS:
        (OUTPUT_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

    total_images = 0

    for cfg in DATASET_CONFIGS:
        dataset_path = Path(cfg["path"])
        class_map = cfg["classes"]  # {old_id: unified_class_name}

        if not dataset_path.exists():
            print(f"  ⚠️  Skipping '{cfg['path']}' — folder not found")
            continue

        print(f"  📦 Merging: {cfg['path']}")

        for split in SPLITS:
            # Roboflow uses "valid" but sometimes "val"
            img_dir = dataset_path / "images" / split
            lbl_dir = dataset_path / "labels" / split

            if not img_dir.exists():
                # Try alternate split name
                alt = "val" if split == "valid" else "valid"
                img_dir = dataset_path / "images" / alt
                lbl_dir = dataset_path / "labels" / alt

            if not img_dir.exists():
                continue

            images = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")) + \
                     list(img_dir.glob("*.jpeg")) + list(img_dir.glob("*.JPG"))

            for img_path in images:
                stem = img_path.stem
                # Unique name: dataset_prefix + original name
                prefix = cfg["path"].replace("/", "_").replace(" ", "_")[:20]
                new_stem = f"{prefix}_{stem}"

                # Copy image
                dst_img = OUTPUT_DIR / "images" / split / (new_stem + img_path.suffix)
                shutil.copy2(img_path, dst_img)

                # Remap and copy label
                lbl_path = lbl_dir / (stem + ".txt")
                dst_lbl = OUTPUT_DIR / "labels" / split / (new_stem + ".txt")
                if lbl_path.exists():
                    remap_label_file(lbl_path, dst_lbl, class_map)
                else:
                    # Create empty label file (background image)
                    dst_lbl.touch()

                total_images += 1

    # Write unified data.yaml
    yaml_content = {
        "path": str(OUTPUT_DIR.resolve()),
        "train": "images/train",
        "val": "images/valid",
        "test": "images/test",
        "nc": len(UNIFIED_CLASSES),
        "names": UNIFIED_CLASSES,
    }

    with open(OUTPUT_DIR / "data.yaml", "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    print(f"\n✅ Merge complete!")
    print(f"   Total images merged : {total_images}")
    print(f"   Classes             : {UNIFIED_CLASSES}")
    print(f"   Output directory    : {OUTPUT_DIR.resolve()}")
    print(f"   data.yaml written   : {(OUTPUT_DIR / 'data.yaml').resolve()}")


if __name__ == "__main__":
    merge()
