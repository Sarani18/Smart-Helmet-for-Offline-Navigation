"""
IDD Dataset Setup Script
-------------------------
Downloads AutoNUE tools and prepares the IDD (India Driving Dataset)
for semantic segmentation model training.

The IDD dataset requires manual registration at:
    https://idd.insaan.iiit.ac.in/

After downloading, place the zip files in data/raw/ and run this script.

Usage:
    python3 setup_dataset.py
    python3 setup_dataset.py --download-sample   # Download a small sample for testing
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import zipfile
import logging
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("idd_setup")

# ===================================================================
#  Paths
# ===================================================================
SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
IDD_DIR = DATA_DIR / "idd"
AUTONUE_DIR = SCRIPT_DIR / "autonue_tools"
MODELS_DIR = SCRIPT_DIR / "models"

# AutoNUE public-code repository (official IIIT-H tools)
AUTONUE_REPO = "https://github.com/AutoNUE/public-code.git"


def create_directory_structure() -> None:
    """Create the expected folder hierarchy."""
    dirs = [
        RAW_DIR,
        IDD_DIR / "leftImg8bit" / "train",
        IDD_DIR / "leftImg8bit" / "val",
        IDD_DIR / "leftImg8bit" / "test",
        IDD_DIR / "gtFine" / "train",
        IDD_DIR / "gtFine" / "val",
        IDD_DIR / "gtFine" / "test",
        MODELS_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.info(f"  📁 {d.relative_to(SCRIPT_DIR)}")


def clone_autonue_tools() -> None:
    """Clone the official AutoNUE public-code repository for label generation."""
    if AUTONUE_DIR.exists() and (AUTONUE_DIR / "preperation").exists():
        logger.info("AutoNUE tools already cloned ✅")
        return

    logger.info(f"Cloning AutoNUE tools from {AUTONUE_REPO}...")
    try:
        subprocess.run(
            ["git", "clone", AUTONUE_REPO, str(AUTONUE_DIR)],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("AutoNUE tools cloned successfully ✅")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone AutoNUE tools: {e.stderr}")
        logger.info("You can manually clone it:")
        logger.info(f"  git clone {AUTONUE_REPO} {AUTONUE_DIR}")


def extract_idd_archives() -> None:
    """Extract any .zip or .tar.gz files found in data/raw/ into data/idd/."""
    import tarfile

    zip_files = list(RAW_DIR.glob("*.zip"))
    tar_files = list(RAW_DIR.glob("*.tar.gz")) + list(RAW_DIR.glob("*.tgz"))
    all_archives = zip_files + tar_files

    if not all_archives:
        logger.warning(
            f"No archive files found in {RAW_DIR.relative_to(SCRIPT_DIR)}/\n"
            f"  Please download the IDD dataset from:\n"
            f"  https://idd.insaan.iiit.ac.in/\n"
            f"  and place the files in {RAW_DIR.relative_to(SCRIPT_DIR)}/"
        )
        return

    for af in all_archives:
        logger.info(f"Extracting {af.name} → {IDD_DIR.relative_to(SCRIPT_DIR)}/")
        if af.suffix == ".zip":
            with zipfile.ZipFile(af, "r") as z:
                z.extractall(IDD_DIR)
        else:
            # tar.gz / tgz
            with tarfile.open(af, "r:gz") as t:
                t.extractall(IDD_DIR)
        logger.info(f"  ✅ Extracted {af.name}")


def generate_label_masks() -> None:
    """
    Run AutoNUE's createLabels.py to convert JSON polygon annotations
    to PNG label masks (level3Id) for training.

    This generates:
        gtFine/{split}/{drive_no}/{img_id}_gtFine_labellevel3Ids.png
    """
    create_labels_script = AUTONUE_DIR / "preperation" / "createLabels.py"

    if not create_labels_script.exists():
        logger.warning(
            "AutoNUE createLabels.py not found. "
            "Skipping label generation. You can run it manually:\n"
            f"  python {create_labels_script} --datadir {IDD_DIR} "
            "--id-type level3Id --num-workers 4"
        )
        return

    # Check if there are JSON annotation files to process
    json_files = list(IDD_DIR.rglob("*_gtFine_polygons.json"))
    if not json_files:
        logger.info("No polygon annotation JSONs found — skipping label generation")
        return

    logger.info(f"Generating label masks from {len(json_files)} annotation files...")

    # Add helpers/ to PYTHONPATH as required by AutoNUE
    env = os.environ.copy()
    helpers_path = str(AUTONUE_DIR / "helpers")
    env["PYTHONPATH"] = f"{helpers_path}:{env.get('PYTHONPATH', '')}"

    try:
        subprocess.run(
            [
                sys.executable,
                str(create_labels_script),
                "--datadir", str(IDD_DIR),
                "--id-type", "level3Id",
                "--num-workers", "4",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        logger.info("Label masks generated successfully ✅")
    except subprocess.CalledProcessError as e:
        logger.error(f"Label generation failed: {e.stderr}")
        logger.info("You can run it manually:")
        logger.info(
            f"  export PYTHONPATH=\"{helpers_path}:$PYTHONPATH\"\n"
            f"  python {create_labels_script} --datadir {IDD_DIR} "
            "--id-type level3Id --num-workers 4"
        )


def create_sample_data() -> None:
    """
    Create a minimal sample dataset for testing the pipeline
    without needing the full 20GB IDD download.

    Generates small dummy images and label masks.
    """
    logger.info("Creating sample dataset for pipeline testing...")

    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        logger.error("Install Pillow and numpy first: pip3 install Pillow numpy")
        return

    sample_size = (1280, 720)  # IDD image resolution
    label_size = (1280, 720)
    num_train = 10
    num_val = 3

    # IDD Level3 class colors (for visualization)
    # 0=road (purple), 9=car (blue), 4=person (red), etc.
    CLASSES = {
        0: "road", 2: "drivable_fallback", 3: "sidewalk",
        4: "person", 5: "rider", 6: "motorcycle",
        8: "autorickshaw", 9: "car", 10: "truck",
        18: "traffic_light", 19: "traffic_sign",
    }

    for split, count in [("train", num_train), ("val", num_val)]:
        drive_dir = f"000"
        img_dir = IDD_DIR / "leftImg8bit" / split / drive_dir
        gt_dir = IDD_DIR / "gtFine" / split / drive_dir
        img_dir.mkdir(parents=True, exist_ok=True)
        gt_dir.mkdir(parents=True, exist_ok=True)

        for i in range(count):
            img_id = f"{i:06d}"

            # Create a synthetic driving scene image
            img = np.random.randint(50, 200, (*sample_size[::-1], 3), dtype=np.uint8)
            # Add sky (top third = blue-ish)
            img[:sample_size[1]//3, :] = [180, 200, 230]
            # Add road (bottom third = dark gray)
            img[2*sample_size[1]//3:, :] = [80, 80, 90]

            Image.fromarray(img).save(
                img_dir / f"{img_id}_leftImg8bit.png"
            )

            # Create label mask (level3Ids)
            label = np.zeros(label_size[::-1], dtype=np.uint8)
            label[:sample_size[1]//3, :] = 14       # sky
            label[sample_size[1]//3:2*sample_size[1]//3, :] = 25  # building
            label[2*sample_size[1]//3:, :] = 0       # road

            Image.fromarray(label).save(
                gt_dir / f"{img_id}_gtFine_labellevel3Ids.png"
            )

        logger.info(
            f"  Created {count} sample images in {split}/ ✅"
        )

    logger.info(
        f"\nSample dataset created at {IDD_DIR.relative_to(SCRIPT_DIR)}/\n"
        f"  Train: {num_train} images | Val: {num_val} images\n"
        f"  Image size: {sample_size} | Label type: level3Ids"
    )


def verify_dataset() -> None:
    """Verify the dataset structure and print statistics."""
    print("\n" + "=" * 60)
    print("  IDD DATASET VERIFICATION")
    print("=" * 60)

    for split in ["train", "val", "test"]:
        img_dir = IDD_DIR / "leftImg8bit" / split
        gt_dir = IDD_DIR / "gtFine" / split

        images = list(img_dir.rglob("*.png")) + list(img_dir.rglob("*.jpg"))
        labels = list(gt_dir.rglob("*level3Ids.png"))
        jsons = list(gt_dir.rglob("*_polygons.json"))

        status = "✅" if len(images) > 0 else "⚠️  empty"
        print(f"\n  {split}/ {status}")
        print(f"    Images:     {len(images)}")
        print(f"    Labels:     {len(labels)} (level3Id masks)")
        print(f"    JSON annot: {len(jsons)}")

    # Check AutoNUE tools
    print(f"\n  AutoNUE tools: ", end="")
    if (AUTONUE_DIR / "preperation").exists():
        print("✅ Ready")
    else:
        print("⚠️  Not cloned yet")

    # Check models directory
    saved_models = list(MODELS_DIR.glob("*.pth")) + list(MODELS_DIR.glob("*.pt"))
    print(f"  Saved models: {len(saved_models)}")

    print("=" * 60)


# ===================================================================
#  Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Setup IDD dataset for CV model training"
    )
    parser.add_argument(
        "--download-sample",
        action="store_true",
        help="Create a small sample dataset for testing the pipeline",
    )
    parser.add_argument(
        "--skip-autonue",
        action="store_true",
        help="Skip cloning AutoNUE tools",
    )
    parser.add_argument(
        "--generate-labels",
        action="store_true",
        help="Generate label masks from JSON annotations",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  IDD DATASET SETUP — Smart Helmet CV Module")
    print("=" * 60)

    # Step 1: Create directory structure
    print("\n📁 Step 1: Creating directory structure...")
    create_directory_structure()

    # Step 2: Clone AutoNUE tools
    if not args.skip_autonue:
        print("\n🔧 Step 2: Setting up AutoNUE tools...")
        clone_autonue_tools()
    else:
        print("\n🔧 Step 2: Skipping AutoNUE tools (--skip-autonue)")

    # Step 3: Extract or create data
    if args.download_sample:
        print("\n📊 Step 3: Creating sample dataset...")
        create_sample_data()
    else:
        print("\n📊 Step 3: Extracting IDD archives...")
        extract_idd_archives()

    # Step 4: Generate label masks (if requested)
    if args.generate_labels:
        print("\n🏷️  Step 4: Generating label masks...")
        generate_label_masks()

    # Step 5: Verify
    print("\n✅ Step 5: Verifying dataset...")
    verify_dataset()

    print("\n📌 Next steps:")
    if args.download_sample:
        print("  1. The sample dataset is ready for pipeline testing")
        print("  2. For the real dataset, register at https://idd.insaan.iiit.ac.in/")
        print(f"  3. Download IDD 20k and place zips in {RAW_DIR.relative_to(SCRIPT_DIR)}/")
        print("  4. Run: python3 setup_dataset.py --generate-labels")
    else:
        print("  1. If no data found, register at https://idd.insaan.iiit.ac.in/")
        print(f"  2. Download IDD 20k zips into {RAW_DIR.relative_to(SCRIPT_DIR)}/")
        print("  3. Run this script again")
        print("  4. Then run: python3 train.py")


if __name__ == "__main__":
    main()
