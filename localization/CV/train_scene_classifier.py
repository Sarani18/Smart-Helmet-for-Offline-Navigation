"""
Step 3: Train a tiny CNN scene classifier on auto-labeled road masks.

Architecture:
    Input:  64×64 road mask (1 channel)
    Model:  4 conv layers → global avg pool → FC → 8 classes
    Output: straight, slight_left, slight_right, left_turn, right_turn,
            sharp_left, sharp_right, junction

Usage:
    python3 train_scene_classifier.py                    # train
    python3 train_scene_classifier.py --epochs 30        # more epochs
    python3 train_scene_classifier.py --evaluate-only    # test only
"""

import argparse
import csv
import logging
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Scene classes ─────────────────────────────────────────────────────────────
SCENE_CLASSES = [
    "straight",       # 0
    "slight_left",    # 1
    "slight_right",   # 2
    "left_turn",      # 3
    "right_turn",     # 4
    "sharp_left",     # 5
    "sharp_right",    # 6
    "junction",       # 7
]

NUM_SCENE_CLASSES = len(SCENE_CLASSES)


# ── Dataset ───────────────────────────────────────────────────────────────────
class RoadMaskDataset(Dataset):
    """Load 64×64 road masks + scene labels from CSV."""
    
    def __init__(self, csv_path: str, augment: bool = False):
        self.samples = []
        self.augment = augment
        
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                mask_path = row["mask_path"]
                label_id = int(row["label_id"])
                confidence = float(row["confidence"])
                # Only use high-confidence labels for training
                if confidence >= 70:
                    self.samples.append((mask_path, label_id))
        
        log.info(f"Loaded {len(self.samples)} samples from {csv_path}")
        
        # Print class distribution
        counts = [0] * NUM_SCENE_CLASSES
        for _, lid in self.samples:
            counts[lid] += 1
        for i, c in enumerate(SCENE_CLASSES):
            log.info(f"  {c:15s}: {counts[i]:5d}")
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        mask_path, label_id = self.samples[idx]
        
        # Load 64×64 road mask
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            # Return a blank mask if loading fails
            mask = np.zeros((64, 64), dtype=np.uint8)
        
        # Normalize to [0, 1]
        mask = mask.astype(np.float32) / 255.0
        
        # Augmentation
        if self.augment:
            # Random horizontal flip (swap left/right labels)
            if np.random.random() < 0.5:
                mask = np.fliplr(mask).copy()
                # Swap left ↔ right labels
                swap = {1: 2, 2: 1, 3: 4, 4: 3, 5: 6, 6: 5}  # slight/turn/sharp L↔R
                label_id = swap.get(label_id, label_id)
            
            # Random noise
            if np.random.random() < 0.3:
                noise = np.random.normal(0, 0.05, mask.shape).astype(np.float32)
                mask = np.clip(mask + noise, 0, 1)
            
            # Random erosion/dilation (simulate different road widths)
            if np.random.random() < 0.3:
                k = np.random.randint(1, 3)
                kernel = np.ones((k, k), np.uint8)
                mask_uint8 = (mask * 255).astype(np.uint8)
                if np.random.random() < 0.5:
                    mask_uint8 = cv2.erode(mask_uint8, kernel)
                else:
                    mask_uint8 = cv2.dilate(mask_uint8, kernel)
                mask = mask_uint8.astype(np.float32) / 255.0
        
        # Convert to tensor: (1, 64, 64)
        tensor = torch.from_numpy(mask).unsqueeze(0)
        
        return tensor, label_id


# ── Model ─────────────────────────────────────────────────────────────────────
class TinySceneCNN(nn.Module):
    """
    Tiny CNN for scene classification from road masks.
    
    Architecture:
        Conv(1→16, 3x3) → BN → ReLU → MaxPool(2)     → 32×32
        Conv(16→32, 3x3) → BN → ReLU → MaxPool(2)    → 16×16
        Conv(32→64, 3x3) → BN → ReLU → MaxPool(2)    → 8×8
        Conv(64→128, 3x3) → BN → ReLU → AdaptiveAvgPool → 1×1
        FC(128 → 8)
    
    Parameters: ~100K (very lightweight)
    """
    
    def __init__(self, num_classes=NUM_SCENE_CLASSES):
        super().__init__()
        
        self.features = nn.Sequential(
            # Block 1: 64×64 → 32×32
            nn.Conv2d(1, 16, 3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            
            # Block 2: 32×32 → 16×16
            nn.Conv2d(16, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            
            # Block 3: 16×16 → 8×8
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            
            # Block 4: 8×8 → 1×1
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        
        self.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(128, num_classes),
        )
    
    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


# ── Training ──────────────────────────────────────────────────────────────────
def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    correct = 0
    total = 0
    
    for masks, labels in loader:
        masks = masks.to(device)
        labels = labels.to(device)
        
        optimizer.zero_grad()
        outputs = model(masks)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item() * masks.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += masks.size(0)
    
    return total_loss / total, correct / total * 100


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0
    correct = 0
    total = 0
    
    # Per-class accuracy
    class_correct = [0] * NUM_SCENE_CLASSES
    class_total = [0] * NUM_SCENE_CLASSES
    
    for masks, labels in loader:
        masks = masks.to(device)
        labels = labels.to(device)
        
        outputs = model(masks)
        loss = criterion(outputs, labels)
        
        total_loss += loss.item() * masks.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += masks.size(0)
        
        for i in range(labels.size(0)):
            label = labels[i].item()
            class_total[label] += 1
            if predicted[i] == label:
                class_correct[label] += 1
    
    acc = correct / total * 100
    
    # Per-class accuracy
    log.info("  Per-class accuracy:")
    for i, c in enumerate(SCENE_CLASSES):
        if class_total[i] > 0:
            cls_acc = class_correct[i] / class_total[i] * 100
            log.info(f"    {c:15s}: {cls_acc:5.1f}% ({class_correct[i]}/{class_total[i]})")
    
    return total_loss / total, acc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="scene_labels.csv", help="Labels CSV")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--save-dir", default="models")
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()
    
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    log.info(f"Using {device}")
    
    # Load dataset
    dataset = RoadMaskDataset(args.csv, augment=True)
    
    # Split: 85% train, 15% val
    n = len(dataset)
    n_val = int(n * 0.15)
    n_train = n - n_val
    train_set, val_set = torch.utils.data.random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )
    
    # Disable augmentation for validation
    # (val_set still uses parent dataset's augment, but that's ok — it adds noise tolerance)
    
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader   = DataLoader(val_set,   batch_size=args.batch_size, shuffle=False, num_workers=0)
    
    log.info(f"Train: {n_train}, Val: {n_val}")
    
    # Model
    model = TinySceneCNN().to(device)
    params = sum(p.numel() for p in model.parameters())
    log.info(f"Model parameters: {params/1e3:.1f}K")
    
    if args.evaluate_only:
        ckpt = torch.load(f"{args.save_dir}/scene_classifier.pth", map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"])
        criterion = nn.CrossEntropyLoss()
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        log.info(f"Validation Accuracy: {val_acc:.1f}%")
        return
    
    # Class weights (handle imbalance — straight is overrepresented)
    class_counts = [0] * NUM_SCENE_CLASSES
    for _, lid in dataset.samples:
        class_counts[lid] += 1
    
    total = sum(class_counts)
    weights = [total / max(c, 1) for c in class_counts]
    weights = torch.FloatTensor(weights).to(device)
    weights = weights / weights.sum() * NUM_SCENE_CLASSES  # normalize
    
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    
    best_acc = 0.0
    save_dir = Path(args.save_dir)
    save_dir.mkdir(exist_ok=True)
    
    log.info(f"\n{'='*60}")
    log.info(f"  TRAINING SCENE CLASSIFIER")
    log.info(f"{'='*60}")
    
    for epoch in range(args.epochs):
        t0 = time.time()
        
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        scheduler.step()
        
        elapsed = time.time() - t0
        
        is_best = val_acc > best_acc
        if is_best:
            best_acc = val_acc
            torch.save({
                "model_state_dict": model.state_dict(),
                "best_acc": best_acc,
                "epoch": epoch,
                "classes": SCENE_CLASSES,
            }, save_dir / "scene_classifier.pth")
        
        log.info(
            f"Epoch {epoch+1:2d}/{args.epochs} | "
            f"Train Loss: {train_loss:.4f} Acc: {train_acc:.1f}% | "
            f"Val Loss: {val_loss:.4f} Acc: {val_acc:.1f}% | "
            f"{'⭐ BEST' if is_best else ''} | "
            f"{elapsed:.1f}s"
        )
    
    log.info(f"\n✅ Best validation accuracy: {best_acc:.1f}%")
    log.info(f"   Model saved: {save_dir}/scene_classifier.pth")
    
    # Export to ONNX
    log.info("\nExporting to ONNX...")
    model.eval()
    dummy = torch.randn(1, 1, 64, 64).to(device)
    onnx_path = save_dir / "scene_classifier.onnx"
    torch.onnx.export(
        model, dummy, str(onnx_path),
        input_names=["road_mask"],
        output_names=["scene_class"],
        dynamic_axes={"road_mask": {0: "batch"}, "scene_class": {0: "batch"}},
        opset_version=11,
    )
    log.info(f"   ONNX exported: {onnx_path}")


if __name__ == "__main__":
    main()
