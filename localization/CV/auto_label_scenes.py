"""
Step 1: Auto-label all IDD images using skeleton-based scene analyzer.
Outputs a CSV with: image_path, label, confidence, curvature, angle

Usage:
    python3 auto_label_scenes.py
"""

import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from scene_analyzer import (
    load_model, preprocess, segment,
    _make_class_mask, _extract_road_skeleton,
    ROAD_CLASSES, NUM_CLASSES, IMG_SIZE,
    analyze_scene,
)

# Scene classes for the classifier
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

CLASS_TO_ID = {c: i for i, c in enumerate(SCENE_CLASSES)}


def classify_scene_label(analysis) -> tuple:
    """Convert SceneAnalysis to a single class label + confidence."""
    # Priority: junction > turn > direction
    if analysis.junction_type in ("t_junction", "crossroad", "y_junction"):
        return "junction", analysis.confidence
    
    if analysis.turn_type == "sharp_left":
        return "sharp_left", analysis.confidence
    elif analysis.turn_type == "sharp_right":
        return "sharp_right", analysis.confidence
    elif analysis.turn_type == "left_turn":
        return "left_turn", analysis.confidence
    elif analysis.turn_type == "right_turn":
        return "right_turn", analysis.confidence
    elif analysis.turn_type == "slight_left":
        return "slight_left", analysis.confidence
    elif analysis.turn_type == "slight_right":
        return "slight_right", analysis.confidence
    
    if "left" in analysis.road_direction:
        return "slight_left", analysis.confidence
    elif "right" in analysis.road_direction:
        return "slight_right", analysis.confidence
    
    return "straight", analysis.confidence


def main():
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using {device}")
    
    model = load_model("models/best.pth", device)
    
    # Find all training + validation images
    data_dir = Path("data/idd/idd20kII/leftImg8bit")
    all_imgs = sorted(list(data_dir.rglob("*.jpg")) + list(data_dir.rglob("*.png")))
    
    # Also include Part I if available
    data_dir2 = Path("data/idd/IDD_Segmentation/leftImg8bit")
    if data_dir2.exists():
        all_imgs += sorted(list(data_dir2.rglob("*.jpg")) + list(data_dir2.rglob("*.png")))
    
    print(f"Found {len(all_imgs)} images to label")
    
    output_csv = Path("scene_labels.csv")
    road_masks_dir = Path("road_masks")
    road_masks_dir.mkdir(exist_ok=True)
    
    labeled = 0
    stats = {c: 0 for c in SCENE_CLASSES}
    
    t0 = time.time()
    
    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image_path", "mask_path", "label", "label_id", "confidence",
                         "road_pct", "curvature", "angle_deg"])
        
        for i, img_path in enumerate(all_imgs):
            try:
                frame = cv2.imread(str(img_path))
                if frame is None:
                    continue
                
                tensor = preprocess(frame)
                seg = segment(model, tensor, device)
                
                # Save road mask (64x64 for tiny CNN input)
                road_mask = _make_class_mask(seg, ROAD_CLASSES).astype(np.uint8) * 255
                road_mask_small = cv2.resize(road_mask, (64, 64), interpolation=cv2.INTER_NEAREST)
                
                mask_name = img_path.stem + "_road.png"
                mask_path = road_masks_dir / mask_name
                cv2.imwrite(str(mask_path), road_mask_small)
                
                # Scene analysis
                analysis = analyze_scene(seg)
                label, confidence = classify_scene_label(analysis)
                
                # Get skeleton data for CSV
                skel = _extract_road_skeleton(_make_class_mask(seg, ROAD_CLASSES))
                curvature = skel["curvature"] if skel["is_valid"] else 0.0
                angle_deg = skel["angle_deg"] if skel["is_valid"] else 0.0
                
                writer.writerow([
                    str(img_path),
                    str(mask_path),
                    label,
                    CLASS_TO_ID[label],
                    f"{confidence:.1f}",
                    f"{analysis.road_coverage_pct:.1f}",
                    f"{curvature:.4f}",
                    f"{angle_deg:.1f}",
                ])
                
                stats[label] += 1
                labeled += 1
                
                if (i + 1) % 100 == 0:
                    elapsed = time.time() - t0
                    speed = (i + 1) / elapsed
                    eta = (len(all_imgs) - i - 1) / speed
                    print(f"[{i+1:5d}/{len(all_imgs)}] {speed:.1f} img/s | "
                          f"ETA: {eta/60:.0f} min | Last: {label:15s} | {img_path.name}")
            
            except Exception as e:
                print(f"[SKIP] {img_path.name}: {e}", file=sys.stderr)
                continue
    
    elapsed = time.time() - t0
    
    print(f"\n{'='*50}")
    print(f"  AUTO-LABELING COMPLETE")
    print(f"{'='*50}")
    print(f"  Images labeled: {labeled}")
    print(f"  Time: {elapsed/60:.1f} minutes")
    print(f"  Speed: {labeled/elapsed:.1f} images/sec")
    print(f"\n  Label distribution:")
    for label, count in sorted(stats.items(), key=lambda x: -x[1]):
        pct = count / max(labeled, 1) * 100
        bar = "█" * int(pct / 2)
        print(f"    {label:15s}: {count:5d} ({pct:4.1f}%) {bar}")
    print(f"\n  Output: {output_csv}")
    print(f"  Road masks: {road_masks_dir}/")


if __name__ == "__main__":
    main()
