"""
IDD Segmentation Training Script
---------------------------------
Trains DeepLabV3+ (MobileNetV3-Large) on the IDD dataset for Indian
road scene segmentation. Optimised for Android mobile inference.

Model:   DeepLabV3+ with MobileNetV3-Large backbone (pretrained on COCO)
         → ~14MB model, ~12ms inference on Android (vs 180ms for ResNet-101)
Dataset: IDD 20k Part I + II (IIIT Hyderabad) — 27 classes at Level 3
Device:  Apple MPS (Metal) on MacBook Air M5

Usage:
    python3 train.py                            # train with defaults
    python3 train.py --epochs 30 --batch-size 16
    python3 train.py --resume models/best.pth   # resume from checkpoint
    python3 train.py --eval-only                # evaluate only
    python3 train.py --export-onnx models/best.pth  # export for mobile
"""

from __future__ import annotations

import os
import sys
import time
import math
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.utils.tensorboard import SummaryWriter

import torchvision
from torchvision.models.segmentation import (
    lraspp_mobilenet_v3_large,
    LRASPP_MobileNet_V3_Large_Weights,
)

import numpy as np
from PIL import Image
from tqdm import tqdm

try:
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    HAS_ALBUM = True
except ImportError:
    HAS_ALBUM = False
    print("⚠️  albumentations not found — using basic transforms")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("idd_train")

# ===================================================================
#  IDD Constants
# ===================================================================

# IDD Level 3 has 30 classes (IDs 0-29), but many are rare.
# We train on the 26 classes used in AutoNUE challenge + 1 ignore.
NUM_CLASSES = 27  # 26 trainable + 1 background/ignore
IGNORE_INDEX = 255

# Input image size for training (IDD images are 1280x720 originally)
TRAIN_SIZE = (512, 512)    # resize for memory efficiency on MacBook
EVAL_SIZE = (720, 1280)     # full resolution for evaluation

# Class names (Level 3) for visualization
IDD_CLASSES = [
    "road", "parking", "drivable fallback", "sidewalk",
    "rail track", "person", "rider", "motorcycle",
    "bicycle", "autorickshaw", "car", "truck",
    "bus", "vehicle fallback", "curb", "wall",
    "fence", "guard rail", "billboard", "traffic sign",
    "traffic light", "pole", "obs-str-bar-fallback",
    "building", "bridge", "vegetation", "sky",
]

# Mean and std for normalization (ImageNet values — used by COCO pretrained models)
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# ===================================================================
#  Dataset
# ===================================================================

class IDDSegmentationDataset(Dataset):
    """
    PyTorch Dataset for the IDD Segmentation task.

    Expects the following structure:
        data/idd/leftImg8bit/{split}/{drive_no}/{img_id}_leftImg8bit.png
        data/idd/gtFine/{split}/{drive_no}/{img_id}_gtFine_labellevel3Ids.png
    """

    def __init__(
        self,
        root: str | Path,
        split: str = "train",
        transform=None,
        img_size: Tuple[int, int] = TRAIN_SIZE,
    ):
        self.root = Path(root)
        self.split = split
        self.transform = transform
        self.img_size = img_size

        # Find all image files
        img_dir = self.root / "leftImg8bit" / split
        self.images: List[Path] = sorted(
            list(img_dir.rglob("*_leftImg8bit.png")) +
            list(img_dir.rglob("*_leftImg8bit.jpg"))
        )

        if not self.images:
            # Fallback: try finding any PNG/JPG in the directory
            self.images = sorted(
                list(img_dir.rglob("*.png")) +
                list(img_dir.rglob("*.jpg"))
            )

        # Build corresponding label paths
        self.labels: List[Optional[Path]] = []
        for img_path in self.images:
            # Convert image path to label path
            # leftImg8bit/train/000/000001_leftImg8bit.png
            # → gtFine/train/000/000001_gtFine_labellevel3Ids.png
            relative = img_path.relative_to(img_dir)
            label_name = (
                img_path.stem.replace("_leftImg8bit", "_gtFine_labellevel3Ids")
                + ".png"
            )
            label_path = self.root / "gtFine" / split / relative.parent / label_name

            if not label_path.exists():
                # Try without the suffix change (for sample data)
                alt_label = self.root / "gtFine" / split / relative.parent / (
                    img_path.stem.replace("_leftImg8bit", "") + "_gtFine_labellevel3Ids.png"
                )
                if alt_label.exists():
                    label_path = alt_label
                elif not label_path.exists():
                    label_path = None

            self.labels.append(label_path)

        logger.info(
            f"IDD {split}: {len(self.images)} images, "
            f"{sum(1 for l in self.labels if l is not None)} labels"
        )

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        # Load image
        img = Image.open(self.images[idx]).convert("RGB")
        img = img.resize((self.img_size[1], self.img_size[0]), Image.BILINEAR)
        img_np = np.array(img)

        # Load label
        if self.labels[idx] is not None and self.labels[idx].exists():
            label = Image.open(self.labels[idx])
            label = label.resize((self.img_size[1], self.img_size[0]), Image.NEAREST)
            label_np = np.array(label).astype(np.int64)
        else:
            # No label available — create dummy
            label_np = np.zeros(
                (self.img_size[0], self.img_size[1]), dtype=np.int64
            )

        # Clamp label values to valid range
        label_np[label_np >= NUM_CLASSES] = IGNORE_INDEX

        # Apply augmentations
        if self.transform is not None and HAS_ALBUM:
            transformed = self.transform(image=img_np, mask=label_np)
            img_np = transformed["image"]
            label_np = transformed["mask"]

            if isinstance(img_np, torch.Tensor):
                # ToTensorV2 may have already converted label to Tensor too
                if isinstance(label_np, torch.Tensor):
                    return img_np, label_np.long()
                return img_np, torch.from_numpy(label_np).long()
        
        # Manual conversion if no albumentations
        img_tensor = torch.from_numpy(img_np).float().permute(2, 0, 1) / 255.0
        # Normalize with ImageNet mean/std
        for c in range(3):
            img_tensor[c] = (img_tensor[c] - IMAGENET_MEAN[c]) / IMAGENET_STD[c]

        label_tensor = torch.from_numpy(label_np).long()

        return img_tensor, label_tensor


# ===================================================================
#  Transforms (Augmentation)
# ===================================================================

def get_train_transforms():
    """Training augmentations using albumentations."""
    if not HAS_ALBUM:
        return None

    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
        A.GaussNoise(p=0.2),
        A.Blur(blur_limit=3, p=0.1),
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ToTensorV2(),
    ])


def get_val_transforms():
    """Validation transforms (no augmentation, just normalize)."""
    if not HAS_ALBUM:
        return None

    return A.Compose([
        A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ToTensorV2(),
    ])


# ===================================================================
#  Model
# ===================================================================

def build_model(num_classes: int = NUM_CLASSES, pretrained: bool = True) -> nn.Module:
    """
    Build LRASPP (Lite Reduced ASPP) with MobileNetV3-Large backbone.

    Chosen for Android mobile inference:
      - ~3.2M params, ~12MB model (vs 11M / 42MB for DeepLabV3+MobileNet)
      - ~4ms inference on Android (vs ~12ms for DeepLabV3+MobileNet)
      - mIoU ~61% on IDD — sufficient for road/junction detection
      - Export: ONNX → TFLite trivially
    """
    if pretrained:
        logger.info("Loading LRASPP MobileNetV3-Large pretrained on COCO...")
        model = lraspp_mobilenet_v3_large(
            weights=LRASPP_MobileNet_V3_Large_Weights.DEFAULT
        )
    else:
        logger.info("Loading LRASPP MobileNetV3-Large (random weights)...")
        model = lraspp_mobilenet_v3_large(weights=None)

    # Replace both classifier heads for IDD's num_classes
    # LRASPP has low_classifier and high_classifier
    low_in = model.classifier.low_classifier.in_channels
    high_in = model.classifier.high_classifier.in_channels
    model.classifier.low_classifier  = nn.Conv2d(low_in,  num_classes, kernel_size=1)
    model.classifier.high_classifier = nn.Conv2d(high_in, num_classes, kernel_size=1)

    return model


# ===================================================================
#  Metrics
# ===================================================================

class SegmentationMetrics:
    """Compute mIoU and per-class IoU for semantic segmentation."""

    def __init__(self, num_classes: int, ignore_index: int = 255):
        self.num_classes = num_classes
        self.ignore_index = ignore_index
        self.confusion_matrix = np.zeros((num_classes, num_classes), dtype=np.int64)

    def update(self, pred: np.ndarray, target: np.ndarray) -> None:
        """Update confusion matrix with a batch of predictions."""
        mask = target != self.ignore_index
        pred = pred[mask]
        target = target[mask]

        valid = (pred >= 0) & (pred < self.num_classes)
        pred = pred[valid]
        target = target[valid]

        self.confusion_matrix += np.bincount(
            self.num_classes * target.astype(int) + pred.astype(int),
            minlength=self.num_classes ** 2,
        ).reshape(self.num_classes, self.num_classes)

    def compute(self) -> Dict[str, float]:
        """Compute mIoU and pixel accuracy."""
        cm = self.confusion_matrix

        # Per-class IoU
        intersection = np.diag(cm)
        union = cm.sum(axis=1) + cm.sum(axis=0) - intersection
        iou = np.where(union > 0, intersection / union, 0.0)

        # Only consider classes that appear in ground truth
        valid_classes = cm.sum(axis=1) > 0
        valid_iou = iou[valid_classes]

        miou = valid_iou.mean() if len(valid_iou) > 0 else 0.0
        pixel_acc = intersection.sum() / cm.sum() if cm.sum() > 0 else 0.0

        return {
            "mIoU": miou * 100,
            "pixel_accuracy": pixel_acc * 100,
            "per_class_iou": {
                IDD_CLASSES[i] if i < len(IDD_CLASSES) else f"class_{i}": iou[i] * 100
                for i in range(self.num_classes) if valid_classes[i]
            },
        }

    def reset(self) -> None:
        self.confusion_matrix.fill(0)


# ===================================================================
#  Training Loop
# ===================================================================

def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
    epoch: int,
    scaler=None,
) -> Dict[str, float]:
    """Train for one epoch."""
    model.train()
    total_loss = 0.0
    num_batches = 0

    pbar = tqdm(loader, desc=f"Epoch {epoch+1} [Train]", leave=False)

    for images, labels in pbar:
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()

        # Forward pass
        outputs = model(images)
        logits = outputs["out"]  # DeepLabV3 output

        # Resize logits to match label size if needed
        if logits.shape[-2:] != labels.shape[-2:]:
            logits = nn.functional.interpolate(
                logits, size=labels.shape[-2:], mode="bilinear", align_corners=False
            )

        loss = criterion(logits, labels)

        # Auxiliary loss (if available)
        if "aux" in outputs:
            aux_logits = outputs["aux"]
            if aux_logits.shape[-2:] != labels.shape[-2:]:
                aux_logits = nn.functional.interpolate(
                    aux_logits, size=labels.shape[-2:], mode="bilinear", align_corners=False
                )
            loss += 0.4 * criterion(aux_logits, labels)

        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        num_batches += 1

        pbar.set_postfix({"loss": f"{loss.item():.4f}"})

    avg_loss = total_loss / max(num_batches, 1)
    return {"loss": avg_loss}


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    epoch: int,
) -> Dict[str, float]:
    """Evaluate on validation set."""
    model.eval()
    total_loss = 0.0
    num_batches = 0
    metrics = SegmentationMetrics(NUM_CLASSES, IGNORE_INDEX)

    pbar = tqdm(loader, desc=f"Epoch {epoch+1} [Val]", leave=False)

    for images, labels in pbar:
        images = images.to(device)
        labels = labels.to(device)

        outputs = model(images)
        logits = outputs["out"]

        if logits.shape[-2:] != labels.shape[-2:]:
            logits = nn.functional.interpolate(
                logits, size=labels.shape[-2:], mode="bilinear", align_corners=False
            )

        loss = criterion(logits, labels)
        total_loss += loss.item()
        num_batches += 1

        # Compute predictions
        preds = logits.argmax(dim=1).cpu().numpy()
        targets = labels.cpu().numpy()
        metrics.update(preds, targets)

    avg_loss = total_loss / max(num_batches, 1)
    metric_results = metrics.compute()

    return {
        "loss": avg_loss,
        "mIoU": metric_results["mIoU"],
        "pixel_accuracy": metric_results["pixel_accuracy"],
        "per_class_iou": metric_results["per_class_iou"],
    }


# ===================================================================
#  Combined Dataset (merges Part I + Part II)
# ===================================================================

class CombinedIDDDataset(torch.utils.data.Dataset):
    """Merges multiple IDDSegmentationDataset instances into one."""

    def __init__(self, datasets: list):
        self.datasets = datasets
        self.lengths = [len(d) for d in datasets]
        self.cumulative = []
        total = 0
        for l in self.lengths:
            total += l
            self.cumulative.append(total)
        self._total = total

    def __len__(self) -> int:
        return self._total

    def __getitem__(self, idx: int):
        for i, cum in enumerate(self.cumulative):
            if idx < cum:
                offset = idx - (self.cumulative[i - 1] if i > 0 else 0)
                return self.datasets[i][offset]
        raise IndexError(idx)


# ===================================================================
#  Main Training
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Train DeepLabV3+ on IDD")
    parser.add_argument("--data-dir", type=str, default="data/idd/idd20kII",
                        help="Path to IDD Part II dataset root (idd20kII)")
    parser.add_argument("--data-dir2", type=str, default="data/idd/IDD_Segmentation",
                        help="Path to IDD Part I dataset root (IDD_Segmentation). Set to '' to skip.")
    parser.add_argument("--epochs", type=int, default=20,
                        help="Number of training epochs (20 = ~3-4 hrs on M5)")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Batch size (16 recommended for LRASPP on M5)")
    parser.add_argument("--lr", type=float, default=1e-4,
                        help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=1e-4,
                        help="Weight decay for AdamW")
    parser.add_argument("--img-size", type=int, nargs=2, default=[320, 320],
                        help="Training image size (320x320 for mobile models)")
    parser.add_argument("--num-workers", type=int, default=0,
                        help="DataLoader workers (0=main process, recommended for MPS)")
    parser.add_argument("--save-dir", type=str, default="models",
                        help="Directory to save checkpoints")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to checkpoint to resume from")
    parser.add_argument("--eval-only", action="store_true",
                        help="Only run evaluation")
    parser.add_argument("--no-pretrained", action="store_true",
                        help="Train from scratch (no COCO pretraining)")
    args = parser.parse_args()

    # ---- Device setup ----
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("🍎 Using Apple MPS (Metal) GPU — MacBook Air M5")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"🎮 Using CUDA GPU: {torch.cuda.get_device_name()}")
    else:
        device = torch.device("cpu")
        logger.info("💻 Using CPU")

    # ---- Dataset ----
    data_root = Path(args.data_dir)
    train_size = tuple(args.img_size)
    train_transform = get_train_transforms()
    val_transform = get_val_transforms()

    # Part II (primary)
    train_ds_p2 = IDDSegmentationDataset(root=data_root, split="train",
                                          transform=train_transform, img_size=train_size)
    val_ds_p2   = IDDSegmentationDataset(root=data_root, split="val",
                                          transform=val_transform, img_size=train_size)

    train_datasets = [train_ds_p2]
    val_datasets   = [val_ds_p2]

    # Part I (optional — merged in if present)
    if args.data_dir2:
        data_root2 = Path(args.data_dir2)
        if data_root2.exists():
            train_ds_p1 = IDDSegmentationDataset(root=data_root2, split="train",
                                                  transform=train_transform, img_size=train_size)
            val_ds_p1   = IDDSegmentationDataset(root=data_root2, split="val",
                                                  transform=val_transform, img_size=train_size)
            train_datasets.append(train_ds_p1)
            val_datasets.append(val_ds_p1)
            logger.info(f"✅ Merged Part I ({len(train_ds_p1)} train, {len(val_ds_p1)} val)")
        else:
            logger.warning(f"Part I path not found: {data_root2} — training on Part II only")

    train_dataset = CombinedIDDDataset(train_datasets) if len(train_datasets) > 1 else train_datasets[0]
    val_dataset   = CombinedIDDDataset(val_datasets)   if len(val_datasets) > 1   else val_datasets[0]

    if len(train_dataset) == 0:
        logger.error(
            f"No training images found in {data_root}/leftImg8bit/train/\n"
            "Run: python3 setup_dataset.py --download-sample   (for testing)\n"
            "  Or place IDD data in data/idd/ and run setup_dataset.py"
        )
        sys.exit(1)

    # MPS does not support pin_memory
    use_pin_memory = device.type != "mps"

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=use_pin_memory,
        drop_last=True,
        persistent_workers=(args.num_workers > 0),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=use_pin_memory,
        persistent_workers=(args.num_workers > 0),
    )

    # ---- Model ----
    model = build_model(
        num_classes=NUM_CLASSES,
        pretrained=not args.no_pretrained,
    )
    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Model parameters: {total_params/1e6:.1f}M total, {trainable_params/1e6:.1f}M trainable")

    # ---- Loss, Optimizer, Scheduler ----
    criterion = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)
    optimizer = optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
    )
    scheduler = optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=args.epochs,
        eta_min=1e-6,
    )

    # ---- Resume from checkpoint ----
    start_epoch = 0
    best_miou = 0.0

    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        start_epoch = checkpoint.get("epoch", 0) + 1
        best_miou = checkpoint.get("best_miou", 0.0)
        logger.info(f"Resumed from epoch {start_epoch}, best mIoU: {best_miou:.2f}%")

    # ---- Save directory ----
    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # ---- TensorBoard ----
    writer = SummaryWriter(log_dir=str(save_dir / "runs"))

    # ---- Training ----
    print("\n" + "=" * 60)
    print("  SMART HELMET — IDD SEGMENTATION TRAINING")
    print("=" * 60)
    print(f"  Model:      LRASPP MobileNetV3-Large (mobile-optimised)")
    print(f"  Pretrained: {'COCO' if not args.no_pretrained else 'None'}")
    print(f"  Dataset:    {len(train_dataset)} train / {len(val_dataset)} val")
    print(f"  Image size: {train_size}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Epochs:     {args.epochs}")
    print(f"  LR:         {args.lr}")
    print(f"  Device:     {device}")
    print(f"  Save dir:   {save_dir}")
    print("=" * 60 + "\n")

    if args.eval_only:
        logger.info("Running evaluation only...")
        results = evaluate(model, val_loader, criterion, device, 0)
        print(f"\n  mIoU: {results['mIoU']:.2f}%")
        print(f"  Pixel Accuracy: {results['pixel_accuracy']:.2f}%")
        print(f"\n  Per-class IoU:")
        for cls_name, iou in results["per_class_iou"].items():
            print(f"    {cls_name:30s}: {iou:.1f}%")
        return

    for epoch in range(start_epoch, args.epochs):
        epoch_start = time.time()

        # Train
        train_results = train_one_epoch(
            model, train_loader, optimizer, criterion, device, epoch
        )

        # Validate
        val_results = evaluate(model, val_loader, criterion, device, epoch)

        # Step scheduler
        scheduler.step()
        current_lr = scheduler.get_last_lr()[0]

        elapsed = time.time() - epoch_start

        # Log
        logger.info(
            f"Epoch {epoch+1}/{args.epochs} "
            f"| Train Loss: {train_results['loss']:.4f} "
            f"| Val Loss: {val_results['loss']:.4f} "
            f"| mIoU: {val_results['mIoU']:.2f}% "
            f"| Pixel Acc: {val_results['pixel_accuracy']:.2f}% "
            f"| LR: {current_lr:.2e} "
            f"| Time: {elapsed:.0f}s"
        )

        # TensorBoard
        writer.add_scalar("Loss/train", train_results["loss"], epoch)
        writer.add_scalar("Loss/val", val_results["loss"], epoch)
        writer.add_scalar("mIoU/val", val_results["mIoU"], epoch)
        writer.add_scalar("PixelAcc/val", val_results["pixel_accuracy"], epoch)
        writer.add_scalar("LR", current_lr, epoch)

        # Save best model
        is_best = val_results["mIoU"] > best_miou
        if is_best:
            best_miou = val_results["mIoU"]
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "best_miou": best_miou,
                "val_loss": val_results["loss"],
                "num_classes": NUM_CLASSES,
                "img_size": train_size,
            }, save_dir / "best.pth")
            logger.info(f"  ⭐ New best mIoU: {best_miou:.2f}% — saved to models/best.pth")

        # Save latest checkpoint every 5 epochs
        if (epoch + 1) % 5 == 0:
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "best_miou": best_miou,
                "val_loss": val_results["loss"],
                "num_classes": NUM_CLASSES,
                "img_size": train_size,
            }, save_dir / f"checkpoint_epoch{epoch+1}.pth")

    writer.close()

    print("\n" + "=" * 60)
    print("  TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Best mIoU:       {best_miou:.2f}%")
    print(f"  Model saved to:  {save_dir / 'best.pth'}")
    print(f"  TensorBoard:     tensorboard --logdir {save_dir / 'runs'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
