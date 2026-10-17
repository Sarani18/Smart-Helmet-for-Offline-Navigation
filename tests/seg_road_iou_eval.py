"""Cross-domain road-segmentation evaluation with real ground truth.

Evaluates the deployed LR-ASPP--MobileNetV3 segmentation checkpoint (trained
on the India Driving Dataset) against BDD100K segmentation val labels, which
the model has never seen. Because the drivable-road mask is what feeds the
downstream topology / route-pointer stage, we score the binary
road-vs-not-road decision rather than full 27-way class agreement:

    prediction  : IDD class 0 (road) or 1 (drivable fallback)  -> road
    ground truth: BDD trainId 0 (road)                          -> road
    ignored     : BDD trainId 255 (unlabelled)

Reports IoU, precision, recall, F1 and pixel accuracy, both micro-averaged
(pooled confusion matrix over all pixels) and per-image mean +/- std.

Usage
-----
    python3 tests/seg_road_iou_eval.py \\
        --bdd-seg ~/Downloads/archive/bdd100k_seg/bdd100k/seg \\
        --limit 200 \\
        --out tests/eval_out/seg_road_iou.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from torchvision.models.segmentation import lraspp_mobilenet_v3_large

NUM_SEG_CLASSES = 27
SEG_IMG_SIZE = (320, 320)
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# IDD level-3 ids that constitute traversable road surface
IDD_ROAD_IDS = (0, 1)          # road, drivable fallback
BDD_ROAD_TRAINID = 0           # Cityscapes-style trainId for road
BDD_IGNORE_TRAINID = 255

PREPROC = transforms.Compose([
    transforms.Resize(SEG_IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])


def load_segmentation(ckpt: Path, device: str) -> torch.nn.Module:
    model = lraspp_mobilenet_v3_large(weights=None, num_classes=NUM_SEG_CLASSES)
    state = torch.load(ckpt, map_location=device, weights_only=False)
    for key in ("model_state_dict", "state_dict", "model"):
        if isinstance(state, dict) and key in state and isinstance(state[key], dict):
            state = state[key]
            break
    r = model.load_state_dict(state, strict=False)
    if r.missing_keys:
        raise SystemExit(
            f"only {len(model.state_dict()) - len(r.missing_keys)}/"
            f"{len(model.state_dict())} weights loaded; refusing to evaluate a "
            f"partially-initialised model. Missing e.g. {r.missing_keys[:3]}"
        )
    print(f"  loaded {len(model.state_dict())} weight tensors")
    model.eval().to(device)
    return model


def predict_road_mask(model, img: Image.Image, out_hw, device: str) -> np.ndarray:
    x = PREPROC(img).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(x)
        logits = out["out"] if isinstance(out, dict) else out
        pred = logits.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
    road = np.isin(pred, IDD_ROAD_IDS).astype(np.uint8)
    # upsample the class map to label resolution with nearest neighbour
    return cv2.resize(road, (out_hw[1], out_hw[0]), interpolation=cv2.INTER_NEAREST)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bdd-seg", required=True,
                    help="path to bdd100k/seg (containing images/val and labels/val)")
    ap.add_argument("--ckpt", default=str(Path(__file__).resolve().parent.parent /
                                          "localization/CV/models/best.pth"))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="tests/eval_out/seg_road_iou.json")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    root = Path(args.bdd_seg).expanduser()
    lab_dir, img_dir = root / "labels" / "val", root / "images" / "val"
    labels = sorted(lab_dir.glob("*_train_id.png"))[:args.limit]
    if not labels:
        print(f"no labels found in {lab_dir}", file=sys.stderr)
        return 1
    print(f"Evaluating {len(labels)} BDD100K val images (model trained on IDD)")

    model = load_segmentation(Path(args.ckpt), args.device)

    # pooled (micro) confusion counts
    TP = FP = FN = TN = 0
    per_img_iou, per_img_f1 = [], []
    skipped = 0

    for i, lab_path in enumerate(labels, 1):
        stem = lab_path.name.replace("_train_id.png", "")
        img_path = img_dir / f"{stem}.jpg"
        if not img_path.exists():
            skipped += 1
            continue
        gt = cv2.imread(str(lab_path), cv2.IMREAD_UNCHANGED)
        img = Image.open(img_path).convert("RGB")
        pred = predict_road_mask(model, img, gt.shape[:2], args.device)

        valid = gt != BDD_IGNORE_TRAINID
        g = (gt == BDD_ROAD_TRAINID) & valid
        p = (pred == 1) & valid

        tp = int(np.logical_and(p, g).sum())
        fp = int(np.logical_and(p, ~g & valid).sum())
        fn = int(np.logical_and(~p & valid, g).sum())
        tn = int(np.logical_and(~p & valid, ~g & valid).sum())
        TP += tp; FP += fp; FN += fn; TN += tn

        denom = tp + fp + fn
        if denom > 0:
            per_img_iou.append(tp / denom)
            prec = tp / (tp + fp) if (tp + fp) else 0.0
            rec = tp / (tp + fn) if (tp + fn) else 0.0
            per_img_f1.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)

        if i % 25 == 0 or i == len(labels):
            run = TP / (TP + FP + FN) if (TP + FP + FN) else 0.0
            print(f"  [{i:04d}/{len(labels)}] running micro road-IoU = {run:.4f}")

    micro_iou = TP / (TP + FP + FN) if (TP + FP + FN) else 0.0
    micro_prec = TP / (TP + FP) if (TP + FP) else 0.0
    micro_rec = TP / (TP + FN) if (TP + FN) else 0.0
    micro_f1 = (2 * micro_prec * micro_rec / (micro_prec + micro_rec)
                if (micro_prec + micro_rec) else 0.0)
    pix_acc = (TP + TN) / (TP + TN + FP + FN) if (TP + TN + FP + FN) else 0.0

    def ms(v):
        return {"mean": round(statistics.fmean(v), 4),
                "std": round(statistics.pstdev(v), 4) if len(v) > 1 else 0.0,
                "n": len(v)} if v else {"n": 0}

    result = {
        "dataset": "BDD100K seg val (cross-domain; model trained on IDD)",
        "images_evaluated": len(per_img_iou),
        "images_skipped": skipped,
        "micro": {"road_IoU": round(micro_iou, 4),
                  "precision": round(micro_prec, 4),
                  "recall": round(micro_rec, 4),
                  "f1": round(micro_f1, 4),
                  "pixel_accuracy": round(pix_acc, 4)},
        "per_image_iou": ms(per_img_iou),
        "per_image_f1": ms(per_img_f1),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    print("\n" + "=" * 62)
    print(" ROAD-SEGMENTATION CROSS-DOMAIN RESULT (real ground truth)")
    print("=" * 62)
    m = result["micro"]
    print(f"  Images            : {result['images_evaluated']}")
    print(f"  Road IoU  (micro) : {m['road_IoU']:.4f}")
    print(f"  Precision (micro) : {m['precision']:.4f}")
    print(f"  Recall    (micro) : {m['recall']:.4f}")
    print(f"  F1        (micro) : {m['f1']:.4f}")
    print(f"  Pixel accuracy    : {m['pixel_accuracy']:.4f}")
    pi = result["per_image_iou"]
    print(f"  Per-image IoU     : {pi['mean']:.4f} +/- {pi['std']:.4f}")
    print(f"\n  JSON: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
