"""Modal Training Script for YOLO v2 Oral Disease Model (Phase 11B-2 / Phase 11B-4.1).

Fine-tunes YOLO11n on the oral disease v2 dataset with Nathan-approved hard negatives.

Key Specifications (Phase 11B-2 / 11B-4.1):
1. Architecture & Base Model:
   - Starts from existing best.pt (/root/best_v1.pt) NOT yolo11n.pt!
   - Uploads dataset/oral-disease-v2.yolov11.zip to /root/oral-disease-v2.zip
   - Uploads services/teeth_analyzer/models/oral_disease/best.pt to /root/best_v1.pt
2. Container Environment:
   - Modal App: 'daantshaant-yolo-v2-training'
   - Output Volume: 'daantshaant-yolo-v2-output'
   - Hardware: GPU A10G, 8 CPUs, 16GB memory
   - System packages: libgl1, libglib2.0-0, ultralytics>=8.3,<9, pyyaml
3. Robust Dataset Root Resolution (Phase 11B-4.1):
   - Extracts ZIP to /root/dataset-v2
   - Recursively resolves dataset root supporting both flat and nested archive layouts
   - Pre-training validation: verifies non-zero counts for all splits (train, valid, test)
   - Rewrites clean /root/daantshaant-v2-data.yaml with absolute paths and 5 classes
4. Fine-Tuning Hyperparameters:
   - epochs: 12
   - imgsz: 640
   - batch: 16
   - device: 0
   - workers: 8
   - patience: 4
   - seed: 42
   - optimizer: 'AdamW'
   - lr0: 0.0005 (conservative fine-tuning rate)
   - close_mosaic: 3
   - save: True, plots: True
5. Output Artifacts:
   - /output/oral-disease-yolo11n-v2/weights/best.pt
   - last.pt, results.csv, results.png, confusion_matrix.png
   - Committed to output volume
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import zipfile
from typing import Any

import yaml

# Prevent Windows multi-drive namespace conflict with pywin32 scripts directory
if __package__ and hasattr(__import__(__package__), "__path__"):
    _pkg = __import__(__package__)
    _this_drive = os.path.splitdrive(os.path.abspath(__file__))[0].lower()
    _pkg.__path__ = [p for p in _pkg.__path__ if os.path.splitdrive(os.path.abspath(p))[0].lower() == _this_drive]

try:
    import modal
except ImportError:
    modal = None  # type: ignore[assignment]


# ------------------------------------------------------------
# Dataset Helpers (Robust path resolution & count verification)
# ------------------------------------------------------------

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

REQUIRED_SPLITS = [
    ("train", "images"),
    ("train", "labels"),
    ("valid", "images"),
    ("valid", "labels"),
    ("test", "images"),
    ("test", "labels"),
]

CLASS_NAMES = {
    0: "calculus",
    1: "caries",
    2: "gingivitis",
    3: "tooth discoloration",
    4: "ulcer",
}


def find_dataset_root(extract_dir: Path | str) -> Path:
    """Recursively locates the dataset root containing train/images, valid/images, test/images,
    and their corresponding labels directories.

    Supports both flat extraction (/root/dataset-v2/train/images) and nested archive
    subdirectories (/root/dataset-v2/<folder>/train/images).
    """
    root_path = Path(extract_dir).resolve()
    if not root_path.exists():
        raise RuntimeError(f"Extraction directory does not exist: {root_path}")

    def is_valid_root(cand: Path) -> bool:
        return all((cand / split / subdir).is_dir() for split, subdir in REQUIRED_SPLITS)

    # 1. Check if extract_dir itself is the dataset root (flat layout)
    if is_valid_root(root_path):
        return root_path

    # 2. Check direct subdirectories first (most common nested archive layout)
    for sub in sorted(root_path.iterdir()):
        if sub.is_dir() and is_valid_root(sub):
            return sub

    # 3. Recursively scan deeper subdirectories
    for cand in sorted(root_path.rglob("*")):
        if cand.is_dir() and is_valid_root(cand):
            return cand

    raise RuntimeError(
        f"Could not locate dataset root inside {root_path}. "
        "A valid dataset root must contain: "
        "train/images, train/labels, valid/images, valid/labels, test/images, and test/labels."
    )


def verify_dataset_counts(dataset_root: Path | str) -> dict[str, dict[str, int]]:
    """Verifies that all splits (train, valid, test) contain non-zero images and labels.

    Prints dataset_root and counts for each split.
    Raises RuntimeError if any split has 0 images or 0 labels.
    """
    dataset_root = Path(dataset_root).resolve()
    print(f"Dataset root: {dataset_root}")

    counts: dict[str, dict[str, int]] = {}

    for split in ["train", "valid", "test"]:
        img_dir = dataset_root / split / "images"
        lbl_dir = dataset_root / split / "labels"

        images = [p for p in img_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS] if img_dir.exists() else []
        labels = [p for p in lbl_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"] if lbl_dir.exists() else []

        img_count = len(images)
        lbl_count = len(labels)
        counts[split] = {"images": img_count, "labels": lbl_count}

        print(f"  {split} image count: {img_count}")
        print(f"  {split} label count: {lbl_count}")

        if img_count == 0 or lbl_count == 0:
            raise RuntimeError(
                f"Split '{split}' has invalid counts: {img_count} images, {lbl_count} labels. "
                f"Cannot proceed with training when any split is empty."
            )

    return counts


def generate_v2_data_yaml(
    dataset_root: Path | str,
    output_yaml_path: Path | str = "/root/daantshaant-v2-data.yaml",
) -> Path:
    """Generates a clean Ultralytics data.yaml with absolute path pointing to resolved dataset_root."""
    if str(dataset_root).startswith("/root"):
        root_path_str = str(dataset_root).replace("\\", "/")
        output_yaml = Path(output_yaml_path)
    else:
        dataset_root = Path(dataset_root).resolve()
        root_path_str = str(dataset_root)
        output_yaml = Path(output_yaml_path).resolve()

    output_yaml.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "path": root_path_str,
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(CLASS_NAMES),
        "names": CLASS_NAMES,
    }

    with output_yaml.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            config,
            f,
            sort_keys=False,
            allow_unicode=True,
        )

    print(f"Generated clean dataset YAML at: {output_yaml}")
    print(f"  path: {config['path']}")
    print(f"  train: {config['train']} (resolves to {Path(root_path_str) / 'train/images'})")
    print(f"  val: {config['val']} (resolves to {Path(root_path_str) / 'valid/images'})")
    print(f"  test: {config['test']} (resolves to {Path(root_path_str) / 'test/images'})")
    print("  names:")
    for idx, cname in CLASS_NAMES.items():
        print(f"    {idx}: {cname}")

    return output_yaml


# ------------------------------------------------------------
# Modal Container Setup
# ------------------------------------------------------------

APP_NAME = "daantshaant-yolo-v2-training"

if modal is not None:
    app = modal.App(APP_NAME)

    output_volume = modal.Volume.from_name(
        "daantshaant-yolo-v2-output",
        create_if_missing=True,
    )

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("libgl1", "libglib2.0-0")
        .pip_install(
            "ultralytics>=8.3,<9",
            "pyyaml",
        )
        .add_local_file(
            "dataset/oral-disease-v2.yolov11.zip",
            "/root/oral-disease-v2.zip",
        )
        .add_local_file(
            "services/teeth_analyzer/models/oral_disease/best.pt",
            "/root/best_v1.pt",
        )
    )
else:
    app = None
    output_volume = None
    image = None


# ------------------------------------------------------------
# Remote Training Function
# ------------------------------------------------------------

def _train_logic():
    import shutil
    import zipfile
    from pathlib import Path
    import torch
    from ultralytics import YOLO

    print("=" * 70)
    print("DaantShaant Dental Pathology YOLO v2 Refinement Training")
    print("=" * 70)

    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    # ------------------------------------------------------------
    # 1. Extraction of confirmed flat v2 dataset
    # ------------------------------------------------------------
    archive = Path("/root/oral-disease-v2.zip")
    extract_dir = Path("/root/dataset-v2")

    if extract_dir.exists():
        shutil.rmtree(extract_dir)

    extract_dir.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        raise RuntimeError(f"Dataset archive missing: {archive}")

    print(f"ZIP exists: {archive.exists()}")
    print(f"ZIP size: {archive.stat().st_size} bytes")

    with zipfile.ZipFile(archive, "r") as zf:
        entries = zf.namelist()

        print(f"ZIP entry count: {len(entries)}")
        print("First 20 ZIP entries:")
        for name in entries[:20]:
            print("  ", name)

        required_prefixes = [
            "train/images/",
            "train/labels/",
            "valid/images/",
            "valid/labels/",
            "test/images/",
            "test/labels/",
        ]

        for prefix in required_prefixes:
            count = sum(1 for n in entries if n.startswith(prefix))
            print(f"Archive {prefix}: {count}")

        zf.extractall(extract_dir)

    dataset_root = extract_dir

    # ------------------------------------------------------------
    # 2. Print actual remote tree after extraction & inspect counts
    # ------------------------------------------------------------
    print("Extraction finished.")
    print(f"dataset_root exists: {dataset_root.exists()}")

    for child in sorted(dataset_root.iterdir()):
        print(
            "ROOT CHILD:",
            child,
            "dir=",
            child.is_dir(),
            "file=",
            child.is_file()
        )

    for split in ["train", "valid", "test"]:
        image_dir = dataset_root / split / "images"
        label_dir = dataset_root / split / "labels"

        image_count = (
            len([p for p in image_dir.iterdir() if p.is_file()])
            if image_dir.exists()
            else 0
        )

        label_count = (
            len([p for p in label_dir.iterdir() if p.is_file()])
            if label_dir.exists()
            else 0
        )

        print(
            f"{split}: "
            f"{image_count} images / "
            f"{label_count} labels "
            f"| image_dir_exists={image_dir.exists()} "
            f"| label_dir_exists={label_dir.exists()}"
        )

    train_img = len([p for p in (dataset_root / "train" / "images").iterdir() if p.is_file()]) if (dataset_root / "train" / "images").exists() else 0
    train_lbl = len([p for p in (dataset_root / "train" / "labels").iterdir() if p.is_file()]) if (dataset_root / "train" / "labels").exists() else 0
    valid_img = len([p for p in (dataset_root / "valid" / "images").iterdir() if p.is_file()]) if (dataset_root / "valid" / "images").exists() else 0
    valid_lbl = len([p for p in (dataset_root / "valid" / "labels").iterdir() if p.is_file()]) if (dataset_root / "valid" / "labels").exists() else 0
    test_img = len([p for p in (dataset_root / "test" / "images").iterdir() if p.is_file()]) if (dataset_root / "test" / "images").exists() else 0
    test_lbl = len([p for p in (dataset_root / "test" / "labels").iterdir() if p.is_file()]) if (dataset_root / "test" / "labels").exists() else 0

    if (
        train_img != 8666
        or train_lbl != 8666
        or valid_img != 1070
        or valid_lbl != 1070
        or test_img != 1070
        or test_lbl != 1070
    ):
        raise RuntimeError(
            "V2 extraction count mismatch. "
            "Training aborted before GPU training."
        )

    counts = {
        "train": {"images": train_img, "labels": train_lbl},
        "valid": {"images": valid_img, "labels": valid_lbl},
        "test": {"images": test_img, "labels": test_lbl},
    }

    # ------------------------------------------------------------
    # 3. Rewrite dataset YAML to absolute Modal-safe paths
    # ------------------------------------------------------------
    modal_yaml = Path("/root/daantshaant-v2-data.yaml")
    generate_v2_data_yaml(
        dataset_root=dataset_root,
        output_yaml_path=modal_yaml,
    )

    print("COMPLETE GENERATED DATA.YAML:")
    print(modal_yaml.read_text(encoding="utf-8"))

    # ------------------------------------------------------------
    # 4. Load current best_v1.pt weights for fine-tuning
    # ------------------------------------------------------------
    v1_model_path = Path("/root/best_v1.pt")
    if not v1_model_path.exists():
        raise RuntimeError(f"Base model weights not found at: {v1_model_path}")

    print(f"Loading base v1 model for fine-tuning: {v1_model_path} ...")
    model = YOLO(str(v1_model_path))

    # ------------------------------------------------------------
    # 6. Fine-Tune on v2 dataset
    # ------------------------------------------------------------
    print("Starting YOLO v2 fine-tuning...")
    results = model.train(
        data=str(modal_yaml),
        epochs=12,
        imgsz=640,
        batch=16,
        device=0,
        workers=8,
        patience=4,
        optimizer="AdamW",
        lr0=0.0005,
        pretrained=True,
        close_mosaic=3,
        save=True,
        save_period=-1,
        plots=True,
        project="/output",
        name="oral-disease-yolo11n-v2",
        exist_ok=True,
        seed=42,
        verbose=True,
    )

    # ------------------------------------------------------------
    # 7. Persist output volume
    # ------------------------------------------------------------
    if output_volume is not None:
        output_volume.commit()

    best_path = Path("/output/oral-disease-yolo11n-v2/weights/best.pt")
    last_path = Path("/output/oral-disease-yolo11n-v2/weights/last.pt")

    if not best_path.exists():
        raise RuntimeError(f"Training completed but best.pt was not found at: {best_path}")

    summary = {
        "status": "complete",
        "best_weights": str(best_path),
        "last_weights": str(last_path),
        "dataset_root": str(dataset_root),
        "dataset_counts": counts,
        "classes": CLASS_NAMES,
        "epochs_requested": 12,
        "base_model": str(v1_model_path),
        "optimizer": "AdamW",
        "lr0": 0.0005,
    }

    print()
    print("=" * 70)
    print("V2 FINE-TUNING COMPLETE")
    print(json.dumps(summary, indent=2))
    print("=" * 70)

    return summary


if modal is not None and app is not None:
    @app.function(
        image=image,
        gpu="A10G",
        cpu=8,
        memory=16384,
        timeout=7200,
        volumes={"/output": output_volume},
    )
    def train():
        return _train_logic()

    @app.local_entrypoint()
    def main():
        result = train.remote()
        print()
        print("Remote result:")
        print(json.dumps(result, indent=2))
else:
    def train():
        return _train_logic()

    def main():
        result = train()
        print()
        print("Result:")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if app is not None:
        app.run()
    else:
        main()
