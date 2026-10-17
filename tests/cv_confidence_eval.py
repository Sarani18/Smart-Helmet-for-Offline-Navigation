"""Real-model CV confidence evaluation for the INDICON paper.

Runs the deployed pipeline (LR-ASPP segmentation -> road mask ->
TinySceneCNN scene classifier) on a folder of real road images and reports
top-1 softmax confidence distribution. This replaces the synthetic ramp
generator's numbers with real ones.

Usage
-----
    python3 tests/cv_confidence_eval.py \\
        --images ~/Downloads/bdd100k/images/100k/val \\
        --limit 50 \\
        --out tests/eval_out/cv_confidence.json

Numbers to send back for the paper:
  * top1_confidence_all: mean/std over all N images
  * top1_confidence_turn_classes: same, restricted to turn/junction predictions
  * per-class prediction counts
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
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models.segmentation import lraspp_mobilenet_v3_large

# Make the localization.CV modules importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "localization" / "CV"))
from models import TinySceneCNN, SCENE_CLASSES  # noqa: E402

NUM_SEG_CLASSES = 27          # IDD level3 classes, matches predict.py
SEG_IMG_SIZE = (320, 320)
SCENE_MASK_SIZE = (64, 64)    # TinySceneCNN input
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

SEG_PREPROC = transforms.Compose([
    transforms.Resize(SEG_IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])

TURN_CLASSES = {
    "slight_left", "slight_right", "left_turn", "right_turn",
    "sharp_left", "sharp_right", "junction",
}


def _unwrap(state):
    """Checkpoints in this repo wrap weights under 'model_state_dict'
    (alongside best_acc / epoch / classes). Older ones may use
    'state_dict' or 'model'. Unwrap whichever is present."""
    if isinstance(state, dict):
        for key in ("model_state_dict", "state_dict", "model"):
            if key in state and isinstance(state[key], dict):
                return state[key]
    return state


def _load_strict(model: torch.nn.Module, ckpt: Path, device: str,
                 label: str) -> torch.nn.Module:
    state = _unwrap(torch.load(ckpt, map_location=device, weights_only=False))
    r = model.load_state_dict(state, strict=False)
    loaded = len(model.state_dict()) - len(r.missing_keys)
    if r.missing_keys:
        raise SystemExit(
            f"{label}: only {loaded}/{len(model.state_dict())} weights loaded. "
            f"Missing e.g. {r.missing_keys[:3]}. Refusing to report "
            f"predictions from a partially-initialised model."
        )
    print(f"  {label}: loaded {loaded}/{len(model.state_dict())} weight tensors")
    model.eval().to(device)
    return model


def load_segmentation(ckpt: Path, device: str) -> torch.nn.Module:
    model = lraspp_mobilenet_v3_large(weights=None, num_classes=NUM_SEG_CLASSES)
    return _load_strict(model, ckpt, device, "segmentation")


def load_scene(ckpt: Path, device: str) -> torch.nn.Module:
    model = TinySceneCNN(num_classes=len(SCENE_CLASSES))
    return _load_strict(model, ckpt, device, "scene classifier")


def road_mask_from_image(seg_model: torch.nn.Module, img: Image.Image,
                          device: str) -> np.ndarray:
    x = SEG_PREPROC(img).unsqueeze(0).to(device)
    with torch.no_grad():
        out = seg_model(x)
        logits = out["out"] if isinstance(out, dict) else out
        pred = logits.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
    # IDD class 0 = "road", class 1 = "drivable fallback"
    mask = ((pred == 0) | (pred == 1)).astype(np.uint8) * 255
    mask64 = cv2.resize(mask, SCENE_MASK_SIZE, interpolation=cv2.INTER_NEAREST)
    return mask64


def scene_confidence(scene_model: torch.nn.Module, mask64: np.ndarray,
                     device: str) -> tuple[str, float, list[float]]:
    x = torch.from_numpy(mask64).float().unsqueeze(0).unsqueeze(0) / 255.0
    x = x.to(device)
    with torch.no_grad():
        logits = scene_model(x)
        probs = F.softmax(logits, dim=1)[0].cpu().tolist()
    top = max(range(len(probs)), key=lambda i: probs[i])
    return SCENE_CLASSES[top], probs[top], probs


def summarise(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": round(statistics.fmean(vals), 4),
        "std":  round(statistics.pstdev(vals) if len(vals) > 1 else 0.0, 4),
        "min":  round(min(vals), 4),
        "max":  round(max(vals), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="folder of road images (jpg/png)")
    ap.add_argument("--seg-ckpt", default=str(REPO_ROOT / "localization/CV/models/best.pth"))
    ap.add_argument("--scene-ckpt", default=str(REPO_ROOT / "localization/CV/models/scene_classifier.pth"))
    ap.add_argument("--limit", type=int, default=50, help="max images to evaluate")
    ap.add_argument("--out", default="tests/eval_out/cv_confidence.json")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    img_dir = Path(args.images).expanduser()
    files = sorted(p for p in img_dir.rglob("*")
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not files:
        print(f"No images in {img_dir}", file=sys.stderr)
        return 1
    files = files[:args.limit]
    print(f"Evaluating {len(files)} images on {args.device}")

    print(f"Loading segmentation from {args.seg_ckpt}")
    seg = load_segmentation(Path(args.seg_ckpt), args.device)
    print(f"Loading scene classifier from {args.scene_ckpt}")
    scene = load_scene(Path(args.scene_ckpt), args.device)

    per_image = []
    top1_all: list[float] = []
    top1_turn: list[float] = []
    class_counts = {c: 0 for c in SCENE_CLASSES}

    for i, f in enumerate(files, 1):
        try:
            img = Image.open(f).convert("RGB")
            mask = road_mask_from_image(seg, img, args.device)
            cls, conf, probs = scene_confidence(scene, mask, args.device)
        except Exception as e:
            print(f"  [{i:03d}] {f.name}: ERROR {e}")
            continue
        per_image.append({"file": f.name, "top1_class": cls,
                          "top1_conf": round(conf, 4),
                          "all_probs": {c: round(p, 4)
                                        for c, p in zip(SCENE_CLASSES, probs)}})
        top1_all.append(conf)
        class_counts[cls] += 1
        if cls in TURN_CLASSES:
            top1_turn.append(conf)
        print(f"  [{i:03d}/{len(files)}] {f.name:32}  "
              f"{cls:14}  conf={conf:.3f}")

    result = {
        "n_images": len(top1_all),
        "top1_confidence_all":         summarise(top1_all),
        "top1_confidence_turn_classes": summarise(top1_turn),
        "class_counts": class_counts,
        "per_image": per_image,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print(" PAPER-READY SUMMARY (paste this back)")
    print("=" * 60)
    r = result["top1_confidence_all"]
    print(f"  Images evaluated: {r['n']}")
    print(f"  Top-1 confidence (all):  mean={r['mean']:.3f} std={r['std']:.3f} "
          f"min={r['min']:.3f} max={r['max']:.3f}")
    r = result["top1_confidence_turn_classes"]
    print(f"  Top-1 confidence (turn/junction only, n={r['n']}):", end=" ")
    if r["n"] > 0:
        print(f"mean={r['mean']:.3f} std={r['std']:.3f} "
              f"min={r['min']:.3f} max={r['max']:.3f}")
    else:
        print("no turn/junction predictions")
    print("  Class prediction counts:")
    for c, n in class_counts.items():
        if n > 0:
            print(f"    {c:14}  {n}")
    print(f"\n  JSON written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
