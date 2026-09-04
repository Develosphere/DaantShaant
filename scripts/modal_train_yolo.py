import json
import zipfile
from pathlib import Path

import modal

APP_NAME = "daantshaant-yolo-training"

app = modal.App(APP_NAME)

output_volume = modal.Volume.from_name(
    "daantshaant-yolo-output",
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
        "dataset/oral-disease.yolov11.zip",
        "/root/oral-disease.zip",
    )
)


@app.function(
    image=image,
    gpu="A10G",
    cpu=8,
    memory=16384,
    timeout=7200,
    volumes={"/output": output_volume},
)
def train():
    import torch
    import yaml
    from ultralytics import YOLO

    print("=" * 70)
    print("DaantShaant Dental Pathology YOLO Training")
    print("=" * 70)

    print("CUDA available:", torch.cuda.is_available())

    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))

    # ------------------------------------------------------------
    # Extract dataset
    # ------------------------------------------------------------

    dataset_root = Path("/root/dataset")
    dataset_root.mkdir(parents=True, exist_ok=True)

    print("Extracting dataset...")

    with zipfile.ZipFile("/root/oral-disease.zip", "r") as archive:
        archive.extractall(dataset_root)

    original_yaml = dataset_root / "data.yaml"

    if not original_yaml.exists():
        raise RuntimeError(
            f"data.yaml not found at expected path: {original_yaml}"
        )

    # ------------------------------------------------------------
    # Rewrite dataset YAML to absolute Modal-safe paths
    # ------------------------------------------------------------

    with original_yaml.open("r", encoding="utf-8") as file:
        source_config = yaml.safe_load(file)

    names = source_config["names"]

    fixed_config = {
        "path": str(dataset_root),
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(names),
        "names": names,
    }

    modal_yaml = Path("/root/daantshaant-data.yaml")

    with modal_yaml.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            fixed_config,
            file,
            sort_keys=False,
            allow_unicode=True,
        )

    print("Classes:")
    for index, name in enumerate(names):
        print(f"  {index}: {name}")

    # ------------------------------------------------------------
    # Basic dataset sanity checks
    # ------------------------------------------------------------

    for split in ["train", "valid", "test"]:
        images = list((dataset_root / split / "images").glob("*"))
        labels = list((dataset_root / split / "labels").glob("*.txt"))

        print(
            f"{split}: "
            f"{len(images)} images / "
            f"{len(labels)} labels"
        )

    # ------------------------------------------------------------
    # Load pretrained YOLO11 Nano
    # ------------------------------------------------------------

    print("Loading YOLO11n pretrained weights...")

    model = YOLO("yolo11n.pt")

    # ------------------------------------------------------------
    # Train
    # ------------------------------------------------------------

    print("Starting training...")

    results = model.train(
        data=str(modal_yaml),

        epochs=20,
        imgsz=640,
        batch=16,

        device=0,

        workers=8,

        patience=5,

        optimizer="auto",

        pretrained=True,

        close_mosaic=5,

        save=True,
        save_period=-1,

        plots=True,

        project="/output",
        name="oral-disease-yolo11n",
        exist_ok=True,

        seed=42,

        verbose=True,
    )

    # ------------------------------------------------------------
    # Persist output volume
    # ------------------------------------------------------------

    output_volume.commit()

    best_path = Path(
        "/output/oral-disease-yolo11n/weights/best.pt"
    )

    last_path = Path(
        "/output/oral-disease-yolo11n/weights/last.pt"
    )

    if not best_path.exists():
        raise RuntimeError(
            f"Training completed but best.pt was not found: {best_path}"
        )

    summary = {
        "status": "complete",
        "best_weights": str(best_path),
        "last_weights": str(last_path),
        "classes": names,
        "epochs_requested": 20,
    }

    print()
    print("=" * 70)
    print("TRAINING COMPLETE")
    print(json.dumps(summary, indent=2))
    print("=" * 70)

    return summary


@app.local_entrypoint()
def main():
    result = train.remote()

    print()
    print("Remote result:")
    print(json.dumps(result, indent=2))