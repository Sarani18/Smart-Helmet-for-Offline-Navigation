"""
Smart Helmet — Segmentation Inference & Visualisation
-------------------------------------------------------
Tests the trained LRASPP model on any image or folder.

Usage:
    # Test on a single image
    python3 predict.py --image path/to/image.jpg

    # Test on a folder of images
    python3 predict.py --folder data/idd/idd20kII/leftImg8bit/val/000

    # Test on webcam (for live demo)
    python3 predict.py --webcam

    # Eval-only mode (metrics on val set)
    python3 predict.py --eval
"""

import sys
import argparse
import numpy as np
from pathlib import Path

import torch
import torch.nn as nn
from torchvision.models.segmentation import (
    lraspp_mobilenet_v3_large,
    LRASPP_MobileNet_V3_Large_Weights,
)
from PIL import Image
import cv2

# ── IDD 27-class colour palette (level3Id) ───────────────────────────────────
IDD_PALETTE = [
    (128, 64, 128),   # 0  road
    (244, 35, 232),   # 1  drivable fallback
    (70,  70,  70),   # 2  building
    (102, 102, 156),  # 3  wall
    (190, 153, 153),  # 4  fence/guard rail
    (153, 153, 153),  # 5  pole
    (250, 170,  30),  # 6  traffic light
    (220, 220,   0),  # 7  traffic sign
    (107, 142,  35),  # 8  vegetation
    (152, 251, 152),  # 9  terrain/fallback
    (70,  130, 180),  # 10 sky
    (220,  20,  60),  # 11 person
    (255,   0,   0),  # 12 rider
    (0,    0, 142),   # 13 car
    (0,    0,  70),   # 14 truck
    (0,   60, 100),   # 15 bus
    (0,   80, 100),   # 16 caravan
    (0,    0, 230),   # 17 motorcycle
    (119,  11,  32),  # 18 bicycle
    (0,  100, 255),   # 19 autorickshaw
    (50,  50, 255),   # 20 animal
    (180, 165, 180),  # 21 misc
    (150, 100, 100),  # 22 truck fallback
    (150, 120,  90),  # 23 vehicle fallback
    (255, 128,   0),  # 24 bridge
    (255, 255, 255),  # 25 unlabeled
    (0,   150, 255),  # 26 unknown
]

IDD_CLASSES = [
    "road", "drivable fallback", "building", "wall", "fence",
    "pole", "traffic light", "traffic sign", "vegetation", "terrain",
    "sky", "person", "rider", "car", "truck", "bus",
    "caravan", "motorcycle", "bicycle", "autorickshaw", "animal",
    "misc", "truck fallback", "vehicle fallback", "bridge",
    "unlabeled", "unknown"
]

NUM_CLASSES = 27
IMG_SIZE    = (320, 320)
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]


# ── Model ─────────────────────────────────────────────────────────────────────
def load_model(checkpoint: str, device: torch.device) -> nn.Module:
    model = lraspp_mobilenet_v3_large(weights=None)
    low_in  = model.classifier.low_classifier.in_channels
    high_in = model.classifier.high_classifier.in_channels
    model.classifier.low_classifier  = nn.Conv2d(low_in,  NUM_CLASSES, 1)
    model.classifier.high_classifier = nn.Conv2d(high_in, NUM_CLASSES, 1)

    ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    print(f"✅ Loaded checkpoint: {checkpoint}")
    print(f"   Best mIoU during training: {ckpt.get('best_miou', 'N/A'):.2f}%")
    return model


# ── Pre/Post-process ───────────────────────────────────────────────────────────
def preprocess(img_path: str) -> torch.Tensor:
    img = Image.open(img_path).convert("RGB").resize((IMG_SIZE[1], IMG_SIZE[0]))
    arr = np.array(img).astype(np.float32) / 255.0
    for c in range(3):
        arr[..., c] = (arr[..., c] - IMAGENET_MEAN[c]) / IMAGENET_STD[c]
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)


def preprocess_frame(frame: np.ndarray) -> torch.Tensor:
    """Pre-process OpenCV BGR frame."""
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resized   = cv2.resize(frame_rgb, (IMG_SIZE[1], IMG_SIZE[0]))
    arr = resized.astype(np.float32) / 255.0
    for c in range(3):
        arr[..., c] = (arr[..., c] - IMAGENET_MEAN[c]) / IMAGENET_STD[c]
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)


def colorise(pred: np.ndarray) -> np.ndarray:
    """Convert class-id mask → RGB colour image."""
    h, w  = pred.shape
    color = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, rgb in enumerate(IDD_PALETTE):
        color[pred == cls_id] = rgb
    return color


def overlay(orig: np.ndarray, seg_color: np.ndarray, alpha: float = 0.55) -> np.ndarray:
    orig_resized = cv2.resize(orig, (IMG_SIZE[1], IMG_SIZE[0]))
    seg_bgr      = cv2.cvtColor(seg_color, cv2.COLOR_RGB2BGR)
    return cv2.addWeighted(orig_resized, 1 - alpha, seg_bgr, alpha, 0)


@torch.no_grad()
def predict(model, tensor: torch.Tensor, device: torch.device) -> np.ndarray:
    tensor = tensor.to(device)
    out    = model(tensor)["out"]
    return out.argmax(dim=1).squeeze(0).cpu().numpy().astype(np.uint8)


# ── Legend helper ──────────────────────────────────────────────────────────────
def draw_legend(img: np.ndarray) -> np.ndarray:
    """Draw class legend on the right side of the image."""
    legend_w = 180
    h, w     = img.shape[:2]
    canvas   = np.ones((h, w + legend_w, 3), dtype=np.uint8) * 30
    canvas[:, :w] = img
    for i, (name, rgb) in enumerate(zip(IDD_CLASSES, IDD_PALETTE)):
        y = 12 + i * 18
        if y + 14 > h:
            break
        cv2.rectangle(canvas, (w + 5, y), (w + 20, y + 12),
                      (int(rgb[2]), int(rgb[1]), int(rgb[0])), -1)
        cv2.putText(canvas, name, (w + 25, y + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (220, 220, 220), 1)
    return canvas


# ── Modes ─────────────────────────────────────────────────────────────────────
def run_image(model, device, img_path: str, out_dir: str):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tensor   = preprocess(img_path)
    pred     = predict(model, tensor, device)
    seg_col  = colorise(pred)

    orig     = cv2.imread(img_path)
    blended  = overlay(orig, seg_col)
    final    = draw_legend(blended)

    out_path = out_dir / (Path(img_path).stem + "_seg.png")
    cv2.imwrite(str(out_path), final)
    print(f"✅ Saved: {out_path}")

    # Show top-5 detected classes
    unique, counts = np.unique(pred, return_counts=True)
    total = pred.size
    print("\n   Top classes detected:")
    for cls_id, cnt in sorted(zip(unique, counts), key=lambda x: -x[1])[:5]:
        pct = cnt / total * 100
        print(f"   {IDD_CLASSES[cls_id]:20s}: {pct:.1f}%")

    cv2.imshow("Smart Helmet — Segmentation", final)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def run_folder(model, device, folder: str, out_dir: str):
    folder  = Path(folder)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    imgs = list(folder.rglob("*.jpg")) + list(folder.rglob("*.png"))
    print(f"Found {len(imgs)} images in {folder}")

    for i, p in enumerate(imgs[:20]):  # limit to 20 for quick demo
        tensor  = preprocess(str(p))
        pred    = predict(model, tensor, device)
        seg_col = colorise(pred)
        orig    = cv2.imread(str(p))
        blended = overlay(orig, seg_col)
        final   = draw_legend(blended)
        out_path = out_dir / (p.stem + "_seg.png")
        cv2.imwrite(str(out_path), final)
        print(f"[{i+1:3d}/{min(20,len(imgs))}] {p.name} → {out_path.name}")

    print(f"\n✅ Done! Results saved to {out_dir}/")


def run_webcam(model, device):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Could not open webcam")
        return

    print("🎥 Webcam running — press Q to quit")
    import time
    fps_list = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        t0     = time.time()
        tensor = preprocess_frame(frame)
        pred   = predict(model, tensor, device)
        seg_col = colorise(pred)
        blended = overlay(frame, seg_col)
        elapsed = time.time() - t0
        fps_list.append(1 / elapsed)

        fps = sum(fps_list[-10:]) / min(len(fps_list), 10)
        cv2.putText(blended, f"FPS: {fps:.1f}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(blended, "Smart Helmet CV", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        cv2.imshow("Smart Helmet — Live Segmentation", blended)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def run_eval(model, device, data_dir: str, data_dir2: str):
    """Quick eval-only on validation set — prints mIoU."""
    sys.path.insert(0, str(Path(__file__).parent))
    from train import IDDSegmentationDataset, CombinedIDDDataset, SegmentationMetrics, IGNORE_INDEX

    val_ds = IDDSegmentationDataset(Path(data_dir), "val", None, IMG_SIZE)
    datasets = [val_ds]
    if data_dir2 and Path(data_dir2).exists():
        val_ds2 = IDDSegmentationDataset(Path(data_dir2), "val", None, IMG_SIZE)
        datasets.append(val_ds2)
    if len(datasets) > 1:
        val_ds = CombinedIDDDataset(datasets)

    from torch.utils.data import DataLoader
    loader  = DataLoader(val_ds, batch_size=8, shuffle=False, num_workers=0)
    metrics = SegmentationMetrics(NUM_CLASSES, IGNORE_INDEX)

    from tqdm import tqdm
    for imgs, labels in tqdm(loader, desc="Evaluating"):
        imgs   = imgs.to(device)
        logits = model(imgs)["out"]
        preds  = logits.argmax(1).cpu().numpy()
        metrics.update(preds, labels.numpy())

    res = metrics.compute()
    print(f"\n{'='*50}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*50}")
    print(f"  mIoU:           {res['mIoU']:.2f}%")
    print(f"  Pixel Accuracy: {res['pixel_accuracy']:.2f}%")
    print(f"\n  Per-class IoU:")
    for cls, iou in sorted(res["per_class_iou"].items(), key=lambda x: -x[1]):
        bar = "█" * int(iou / 5)
        print(f"  {cls:22s}: {iou:5.1f}% {bar}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Smart Helmet segmentation inference")
    parser.add_argument("--checkpoint", default="models/best.pth")
    parser.add_argument("--image",   type=str, help="Path to a single image")
    parser.add_argument("--folder",  type=str, help="Path to folder of images")
    parser.add_argument("--webcam",  action="store_true", help="Run on webcam")
    parser.add_argument("--eval",    action="store_true", help="Eval on val set")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--data-dir",  default="data/idd/idd20kII")
    parser.add_argument("--data-dir2", default="data/idd/IDD_Segmentation")
    args = parser.parse_args()

    # Device
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        print("🍎 Using Apple MPS")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
        print("💻 Using CPU")

    model = load_model(args.checkpoint, device)

    if args.image:
        run_image(model, device, args.image, args.out_dir)
    elif args.folder:
        run_folder(model, device, args.folder, args.out_dir)
    elif args.webcam:
        run_webcam(model, device)
    elif args.eval:
        run_eval(model, device, args.data_dir, args.data_dir2)
    else:
        print("Usage examples:")
        print("  python3 predict.py --image photo.jpg")
        print("  python3 predict.py --folder data/idd/idd20kII/leftImg8bit/val/000")
        print("  python3 predict.py --webcam")
        print("  python3 predict.py --eval")


if __name__ == "__main__":
    main()
