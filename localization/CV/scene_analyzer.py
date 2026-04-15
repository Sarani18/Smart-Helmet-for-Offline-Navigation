"""
Smart Helmet — Scene & Turn Detection from Segmentation
---------------------------------------------------------
Analyzes the segmentation mask output to detect:
  - Road direction (straight, left curve, right curve)
  - Junctions & intersections (T-junction, crossroad)
  - Obstacles ahead (vehicles, pedestrians)
  - Scene type (highway, urban, residential)

This is a GEOMETRY-BASED approach — no extra training needed.
Uses the road mask shape from the existing LRASPP segmentation model.

Usage:
    # Analyze a single image
    python3 scene_analyzer.py --image data/idd/idd20kII/leftImg8bit/val/000/frame0019_leftImg8bit.jpg

    # Live webcam with turn detection overlay
    python3 scene_analyzer.py --webcam

    # Batch analyze validation images
    python3 scene_analyzer.py --folder data/idd/idd20kII/leftImg8bit/val --out-dir scene_outputs
"""

from __future__ import annotations
import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision.models.segmentation import lraspp_mobilenet_v3_large

try:
    from models import TinySceneCNN, SCENE_CLASSES
except ImportError:
    TinySceneCNN, SCENE_CLASSES = None, None

# ── Constants ─────────────────────────────────────────────────────────────────
NUM_CLASSES   = 27
IMG_SIZE      = (320, 320)
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

# Class IDs from IDD level3
ROAD_CLASSES      = {0, 1}        # road, drivable fallback
VEHICLE_CLASSES   = {13, 14, 15, 16, 17, 19, 22, 23}  # car, truck, bus, caravan, motorcycle, auto, fallbacks
PERSON_CLASSES    = {11, 12}      # person, rider
BUILDING_CLASSES  = {2, 3}        # building, wall
VEGETATION_CLASSES = {8, 9}       # vegetation, terrain
SKY_CLASSES       = {10}          # sky
SIGN_CLASSES      = {6, 7}        # traffic light, traffic sign

# Colour palette for visualization
SCENE_COLORS = {
    "straight":     (0, 200, 0),     # green
    "slight_left":  (0, 200, 200),   # yellow-ish
    "slight_right": (0, 200, 200),
    "left_turn":    (0, 140, 255),   # orange
    "right_turn":   (0, 140, 255),
    "left_curve":   (255, 200, 0),   # cyan
    "right_curve":  (255, 200, 0),
    "sharp_left":   (0, 0, 255),     # red
    "sharp_right":  (0, 0, 255),
    "u_turn":       (255, 0, 255),   # magenta
    "junction":     (0, 0, 255),     # red
    "intersection": (0, 0, 255),
    "dead_end":     (128, 128, 128), # grey
    "unknown":      (128, 128, 128),
}


# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class Obstacle:
    """An obstacle detected in the scene."""
    label: str          # "vehicle", "person", "animal"
    position: str       # "left", "center", "right"
    distance: str       # "near", "mid", "far"
    area_pct: float     # percentage of image area


@dataclass
class SceneAnalysis:
    """Complete analysis of a road scene."""
    # Road geometry
    road_direction: str       # "straight", "left_curve", "right_curve"
    turn_type: str            # "none", "slight_left", "left_turn", "slight_right", "right_turn"
    junction_type: str        # "none", "t_junction", "y_junction", "crossroad"
    
    # Quantitative
    road_coverage_pct: float  # % of image that is road
    road_center_x: float      # normalized x center of road (0=left, 1=right)
    road_width_ratio: float   # road width at bottom vs top (>1 = narrowing = straight)
    
    # Scene context
    scene_type: str           # "highway", "urban", "residential", "rural"
    
    # Obstacles
    obstacles: List[Obstacle] = field(default_factory=list)
    obstacle_ahead: bool = False
    
    # Navigation instruction
    nav_instruction: str = ""
    confidence: float = 0.0

    def summary(self) -> str:
        parts = [f"🧭 {self.nav_instruction}"]
        parts.append(f"   Scene: {self.scene_type} | Road: {self.road_direction}")
        if self.junction_type != "none":
            parts.append(f"   ⚠️  Junction: {self.junction_type}")
        if self.obstacle_ahead:
            for obs in self.obstacles:
                parts.append(f"   🚨 {obs.label} ({obs.distance}) on {obs.position}")
        parts.append(f"   Confidence: {self.confidence:.0f}%")
        return "\n".join(parts)


# ── Core Analysis ─────────────────────────────────────────────────────────────
def _make_class_mask(seg: np.ndarray, class_ids: set) -> np.ndarray:
    """Create binary mask for a set of class IDs."""
    mask = np.zeros_like(seg, dtype=bool)
    for cid in class_ids:
        mask |= (seg == cid)
    return mask


def _extract_road_skeleton(road_mask: np.ndarray) -> dict:
    """
    Extract the road centerline via morphological skeletonization,
    then fit a polynomial to measure curvature.
    
    This is robust to vehicles blocking one side of the road because
    the skeleton traces the TRUE centerline, not the center-of-mass.
    
    Returns:
        skeleton_points: list of (row, col) along the centerline
        curvature: float — positive = curves right, negative = curves left
        angle_deg: float — road heading angle in degrees (0=straight up)
        is_valid: bool — whether enough skeleton points were found
    """
    h, w = road_mask.shape
    
    # Step 1: Clean the road mask (remove small blobs, fill holes)
    mask_uint8 = road_mask.astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel)
    mask_uint8 = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel)
    
    # Step 2: Skeletonize using iterative thinning
    skeleton = np.zeros_like(mask_uint8)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    temp = mask_uint8.copy()
    while True:
        eroded = cv2.erode(temp, element)
        opened = cv2.dilate(eroded, element)
        diff = cv2.subtract(temp, opened)
        skeleton = cv2.bitwise_or(skeleton, diff)
        temp = eroded.copy()
        if cv2.countNonZero(temp) == 0:
            break
    
    # Step 3: Extract skeleton points, sampled row by row
    # For each row, take the median x-coordinate of skeleton pixels
    centerline = []
    for row in range(h):
        cols = np.where(skeleton[row, :] > 0)[0]
        if len(cols) > 0:
            centerline.append((row, int(np.median(cols))))
    
    if len(centerline) < 10:
        # Not enough points — fall back
        # Try using road mask directly (column median per row)
        centerline = []
        for row in range(h):
            cols = np.where(road_mask[row, :] > 0)[0]
            if len(cols) > 0:
                centerline.append((row, int(np.median(cols))))
    
    if len(centerline) < 10:
        return {
            "centerline": [],
            "curvature": 0.0,
            "angle_deg": 0.0,
            "is_valid": False,
        }
    
    # Step 4: Compute road direction using STABLE linear slope
    # Instead of noisy polynomial curvature, compare road center
    # in bottom half vs top half of the visible road region
    rows = np.array([p[0] for p in centerline], dtype=np.float64)
    cols = np.array([p[1] for p in centerline], dtype=np.float64)
    
    # Split centerline into bottom half and top half
    mid_row = (rows.min() + rows.max()) / 2
    bottom_pts = cols[rows >= mid_row]
    top_pts    = cols[rows < mid_row]
    
    if len(bottom_pts) > 3 and len(top_pts) > 3:
        bottom_cx = np.median(bottom_pts)
        top_cx    = np.median(top_pts)
        
        # Shift = how much the road moves from bottom to top
        # Normalized by image width
        shift = (top_cx - bottom_cx) / w
        
        # Angle: arctan of shift over vertical distance
        vert_dist = (rows.max() - rows.min()) / h
        angle_deg = np.degrees(np.arctan2(shift, max(vert_dist, 0.1)))
        
        # Curvature: compare left-right shift in 3 segments
        third = len(centerline) // 3
        if third > 2:
            seg1_cx = np.median(cols[:third])
            seg2_cx = np.median(cols[third:2*third])
            seg3_cx = np.median(cols[2*third:])
            # Curvature = (seg3 - seg2) - (seg2 - seg1) normalized
            curvature = ((seg3_cx - seg2_cx) - (seg2_cx - seg1_cx)) / w
        else:
            curvature = 0.0
    else:
        angle_deg = 0.0
        curvature = 0.0
    
    return {
        "centerline": centerline,
        "curvature": float(curvature),
        "angle_deg": float(angle_deg),
        "is_valid": True,
    }

def analyze_road_geometry(road_mask: np.ndarray) -> dict:
    """
    Analyze road mask to determine direction, turns, junctions.
    
    Calibrated on 50 IDD validation images:
      - Dashcam has a +0.025 right bias -> corrected
      - Straight threshold: +/-0.12 (was +/-0.08, caused false turns)
      - Added: sharp_left, sharp_right, u_turn
    """
    h, w = road_mask.shape
    
    # Camera bias correction (dashcam slightly right-mounted)
    CAMERA_BIAS = 0.025
    
    # Define horizontal bands
    near_band   = road_mask[int(h*0.70):, :]
    mid_band    = road_mask[int(h*0.40):int(h*0.70), :]
    ahead_band  = road_mask[int(h*0.15):int(h*0.40), :]
    far_band    = road_mask[:int(h*0.15), :]
    
    third_w = w // 3
    
    def region_density(band):
        if band.size == 0:
            return 0.0, 0.0, 0.0
        left   = band[:, :third_w].sum() / max(band[:, :third_w].size, 1)
        center = band[:, third_w:2*third_w].sum() / max(band[:, third_w:2*third_w].size, 1)
        right  = band[:, 2*third_w:].sum() / max(band[:, 2*third_w:].size, 1)
        return left, center, right
    
    def band_center_x(band):
        if band.sum() == 0:
            return None
        cols = np.where(band.any(axis=0))[0]
        return cols.mean() / w if len(cols) > 0 else None
    
    near_cx  = band_center_x(near_band)
    mid_cx   = band_center_x(mid_band)
    ahead_cx = band_center_x(ahead_band)
    far_cx   = band_center_x(far_band)
    
    mid_l, mid_c, mid_r       = region_density(mid_band)
    near_l, near_c, near_r    = region_density(near_band)
    ahead_l, ahead_c, ahead_r = region_density(ahead_band)
    
    total_road = road_mask.sum()
    road_pct   = total_road / road_mask.size * 100
    
    if total_road > 0:
        cols = np.where(road_mask.any(axis=0))[0]
        road_center_x = cols.mean() / w if len(cols) > 0 else 0.5
    else:
        road_center_x = 0.5
    
    near_cols  = np.where(near_band.any(axis=0))[0]
    ahead_cols = np.where(ahead_band.any(axis=0))[0]
    near_width  = (near_cols.max() - near_cols.min()) / w if len(near_cols) > 1 else 0
    ahead_width = (ahead_cols.max() - ahead_cols.min()) / w if len(ahead_cols) > 1 else 0
    width_ratio = near_width / max(ahead_width, 0.01)
    
    # ── Direction detection: Use SKELETON as primary signal ──
    skel = _extract_road_skeleton(road_mask)
    
    if road_pct < 3.0 or near_cx is None:
        direction = "dead_end"
        turn = "none"
    elif skel["is_valid"]:
        # PRIMARY: Skeleton-based direction (robust to vehicle occlusion)
        curv = skel["curvature"]
        angle = skel["angle_deg"]
        
        # Direction from curvature
        # Calibrated: std=0.26, |curv|<0.05 = straight (38% of images)
        if abs(curv) < 0.08:
            direction = "straight"
        elif curv < -0.30:
            direction = "left_curve"
        elif curv > 0.30:
            direction = "right_curve"
        elif curv < -0.08:
            direction = "slight_left"
        elif curv > 0.08:
            direction = "slight_right"
        else:
            direction = "straight"
        
        # Turn severity from road heading angle
        # Calibrated: std=21°, |angle|<15 = straight (58% of images)
        if abs(angle) < 15.0:
            turn = "none"
        elif angle < -45.0:
            turn = "sharp_left"
        elif angle < -30.0:
            turn = "left_turn"
        elif angle < -15.0:
            turn = "slight_left"
        elif angle > 45.0:
            turn = "sharp_right"
        elif angle > 30.0:
            turn = "right_turn"
        elif angle > 15.0:
            turn = "slight_right"
        else:
            turn = "none"
        
        # U-turn: very high curvature (road doubles back)
        if abs(curv) > 0.70:
            turn = "u_turn"
            direction = "u_turn"
        
    else:
        # FALLBACK: Band-shift method (when skeleton fails)
        if mid_cx is not None:
            shift = (mid_cx - near_cx) - CAMERA_BIAS
        elif ahead_cx is not None:
            shift = (ahead_cx - near_cx) - CAMERA_BIAS
        else:
            shift = 0.0
        
        overall_shift = (road_center_x - 0.5) - CAMERA_BIAS
        
        if abs(shift) < 0.05:
            direction = "straight"
        elif shift < -0.15:
            direction = "left_curve"
        elif shift > 0.15:
            direction = "right_curve"
        elif shift < -0.05:
            direction = "slight_left"
        elif shift > 0.05:
            direction = "slight_right"
        else:
            direction = "straight"
        
        if abs(overall_shift) < 0.12:
            turn = "none"
        elif overall_shift < -0.30:
            turn = "sharp_left"
        elif overall_shift < -0.20:
            turn = "left_turn"
        elif overall_shift < -0.12:
            turn = "slight_left"
        elif overall_shift > 0.30:
            turn = "sharp_right"
        elif overall_shift > 0.20:
            turn = "right_turn"
        elif overall_shift > 0.12:
            turn = "slight_right"
        else:
            turn = "none"
    
    # Junction detection
    junction = "none"
    total_mid = mid_l + mid_c + mid_r
    if total_mid > 0.01:
        ml = mid_l / total_mid
        mr = mid_r / total_mid
        mc = mid_c / total_mid
        
        mid_cols_arr = np.where(mid_band.any(axis=0))[0]
        mid_width = (mid_cols_arr.max() - mid_cols_arr.min()) / w if len(mid_cols_arr) > 1 else 0
        
        if ml > 0.25 and mr > 0.25 and mc < 0.40:
            junction = "t_junction"
        elif ml > 0.20 and mr > 0.20 and mc > 0.20 and mid_width > 0.75:
            junction = "crossroad"
        elif (ml > 0.30 or mr > 0.30) and mc > 0.20 and mid_width > 0.65:
            junction = "y_junction"
    
    return {
        "direction": direction,
        "turn": turn,
        "junction": junction,
        "road_pct": road_pct,
        "road_center_x": road_center_x,
        "width_ratio": width_ratio,
        "top_distribution": (ahead_l, ahead_c, ahead_r),
        "skeleton": skel if skel["is_valid"] else None,
    }


def detect_obstacles(seg: np.ndarray) -> List[Obstacle]:
    """Detect vehicles and pedestrians, estimate position and rough distance."""
    h, w = seg.shape
    third_w = w // 3
    obstacles = []
    
    for class_ids, label in [(VEHICLE_CLASSES, "vehicle"), (PERSON_CLASSES, "pedestrian")]:
        mask = _make_class_mask(seg, class_ids)
        if mask.sum() == 0:
            continue
        
        # Find connected components (rough)
        rows, cols = np.where(mask)
        if len(rows) == 0:
            continue
        
        # Position (left/center/right)
        mean_col = cols.mean()
        if mean_col < third_w:
            position = "left"
        elif mean_col < 2 * third_w:
            position = "center"
        else:
            position = "right"
        
        # Distance estimate (higher in image = further away)
        mean_row = rows.mean()
        if mean_row < h * 0.33:
            distance = "far"
        elif mean_row < h * 0.66:
            distance = "mid"
        else:
            distance = "near"
        
        area_pct = mask.sum() / mask.size * 100
        
        obstacles.append(Obstacle(
            label=label,
            position=position,
            distance=distance,
            area_pct=area_pct,
        ))
    
    return obstacles


def classify_scene(seg: np.ndarray, road_geom: dict) -> str:
    """Classify scene type: highway, urban, residential, rural."""
    total_pixels = seg.size
    
    building_pct   = _make_class_mask(seg, BUILDING_CLASSES).sum() / total_pixels
    vegetation_pct = _make_class_mask(seg, VEGETATION_CLASSES).sum() / total_pixels
    sky_pct        = _make_class_mask(seg, SKY_CLASSES).sum() / total_pixels
    vehicle_pct    = _make_class_mask(seg, VEHICLE_CLASSES).sum() / total_pixels
    road_pct       = road_geom["road_pct"] / 100
    
    # Highway: wide road, lots of sky, few buildings
    if road_pct > 0.35 and sky_pct > 0.15 and building_pct < 0.10:
        return "highway"
    # Urban: lots of buildings and vehicles
    elif building_pct > 0.15 and vehicle_pct > 0.05:
        return "urban"
    # Rural: lots of vegetation, little building
    elif vegetation_pct > 0.30 and building_pct < 0.10:
        return "rural"
    # Residential: moderate buildings, some vegetation
    else:
        return "residential"

def generate_nav_instruction(geom: dict, obstacles: List[Obstacle], scene: str, cnn_class: str = None, cnn_conf: float = 0.0) -> tuple[str, float]:
    """Generate a human-readable instruction based on geometry, CNN, and obstacles."""
    parts = []
    confidence = 50
    
    junction = geom["junction"]
    turn = geom["turn"]
    direction = geom["direction"]
    
    # ENSEMBLE: CNN specializes in Junctions
    if cnn_class == "junction" and cnn_conf > 70:
        if junction == "none":
            junction = "crossroad"  # CNN override
    
    # ENSEMBLE: CNN specializes in Sharp Turns
    if cnn_class in ["sharp_left", "sharp_right", "left_turn", "right_turn"] and cnn_conf > 70:
        if turn == "none" and direction == "straight":
            turn = cnn_class
            
    # Junction takes priority
    if junction == "t_junction":
        parts.append("T-junction ahead")
        confidence += 10
    elif junction == "crossroad":
        parts.append("Intersection ahead")
        confidence += 10
    elif junction == "y_junction":
        parts.append("Y-fork ahead")
        confidence += 5
    
    # Direction/turn — turn takes priority over direction
    if turn == "u_turn":
        parts.append("U-TURN detected")
        confidence += 20
    elif turn == "sharp_left":
        parts.append("SHARP LEFT turn")
        confidence += 18
    elif turn == "sharp_right":
        parts.append("SHARP RIGHT turn")
        confidence += 18
    elif turn == "left_turn":
        parts.append("Turn LEFT")
        confidence += 15
    elif turn == "right_turn":
        parts.append("Turn RIGHT")
        confidence += 15
    elif turn == "slight_left":
        parts.append("Bear left")
        confidence += 10
    elif turn == "slight_right":
        parts.append("Bear right")
        confidence += 10
    elif direction == "left_curve":
        parts.append("Road curves LEFT")
        confidence += 10
    elif direction == "right_curve":
        parts.append("Road curves RIGHT")
        confidence += 10
    elif direction == "slight_left":
        parts.append("Road drifts left")
        confidence += 8
    elif direction == "slight_right":
        parts.append("Road drifts right")
        confidence += 8
    elif direction == "straight":
        parts.append("Continue straight")
        confidence += 20
    elif direction == "dead_end":
        parts.append("No road ahead")
        confidence -= 20
    else:
        parts.append("Continue straight")
        confidence += 10
    
    # Obstacle warnings
    center_obstacles = [o for o in obstacles if o.position == "center" and o.distance in ("near", "mid")]
    if center_obstacles:
        for obs in center_obstacles:
            parts.append(f"Caution: {obs.label} ahead")
        confidence += 5
    
    instruction = " | ".join(parts) if parts else "Analyzing..."
    confidence = min(max(confidence, 10), 99)
    
    return instruction, confidence


# ── Main analysis entry point ─────────────────────────────────────────────────
def analyze_scene(seg_mask: np.ndarray, cnn_model=None, device=None) -> SceneAnalysis:
    """
    Full scene analysis from a segmentation mask.
    
    Args:
        seg_mask: (H, W) numpy array of class IDs from the segmentation model
        cnn_model: TinySceneCNN model for turning intention overriding
    
    Returns:
        SceneAnalysis with direction, turns, junctions, obstacles
    """
    road_mask = _make_class_mask(seg_mask, ROAD_CLASSES)
    
    # CNN Inference
    cnn_class, cnn_conf = None, 0.0
    if cnn_model is not None and device is not None and SCENE_CLASSES is not None:
        road_mask_small = cv2.resize((road_mask.astype(np.uint8) * 255), (64, 64), interpolation=cv2.INTER_NEAREST)
        tensor = torch.from_numpy(road_mask_small.astype(np.float32) / 255.0).unsqueeze(0).unsqueeze(0).to(device)
        with torch.no_grad():
            out = cnn_model(tensor)
            probs = torch.nn.functional.softmax(out, dim=1)
            conf, pred = probs.max(1)
            cnn_class = SCENE_CLASSES[pred.item()]
            cnn_conf = conf.item() * 100
            
    # Road geometry
    geom = analyze_road_geometry(road_mask)
    
    # Obstacles
    obstacles = detect_obstacles(seg_mask)
    obstacle_ahead = any(o.position == "center" and o.distance in ("near", "mid") for o in obstacles)
    
    # Scene type
    scene = classify_scene(seg_mask, geom)
    
    # Navigation instruction (Ensemble: Geometry + CNN)
    instruction, confidence = generate_nav_instruction(geom, obstacles, scene, cnn_class, cnn_conf)
    
    return SceneAnalysis(
        road_direction=geom["direction"],
        turn_type=geom["turn"],
        junction_type=geom["junction"],
        road_coverage_pct=geom["road_pct"],
        road_center_x=geom["road_center_x"],
        road_width_ratio=geom["width_ratio"],
        scene_type=scene,
        obstacles=obstacles,
        obstacle_ahead=obstacle_ahead,
        nav_instruction=instruction,
        confidence=confidence,
    )


# ── Visualization ─────────────────────────────────────────────────────────────
def draw_analysis(frame: np.ndarray, analysis: SceneAnalysis) -> np.ndarray:
    """Draw scene analysis overlay on the frame."""
    out = frame.copy()
    h, w = out.shape[:2]
    
    # Semi-transparent overlay panel at top
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, 95), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, out, 0.4, 0, out)
    
    # Navigation instruction (large, colored)
    direction_key = analysis.turn_type if analysis.turn_type != "none" else analysis.road_direction
    color = SCENE_COLORS.get(direction_key, (200, 200, 200))
    cv2.putText(out, analysis.nav_instruction, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    
    # Scene info
    info = f"Scene: {analysis.scene_type} | Road: {analysis.road_coverage_pct:.0f}%"
    cv2.putText(out, info, (10, 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1)
    
    # Junction warning
    if analysis.junction_type != "none":
        cv2.putText(out, f"Junction: {analysis.junction_type}", (10, 72),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 255), 1)
    
    # Confidence bar
    bar_w = int(analysis.confidence * 1.5)
    bar_color = (0, 200, 0) if analysis.confidence > 60 else (0, 200, 200)
    cv2.rectangle(out, (10, 80), (10 + bar_w, 90), bar_color, -1)
    cv2.putText(out, f"{analysis.confidence:.0f}%", (10 + bar_w + 5, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
    
    # Direction arrow
    cx, cy = w // 2, h - 40
    arrow_len = 50
    if "left" in direction_key:
        end = (cx - arrow_len, cy - arrow_len // 2)
    elif "right" in direction_key:
        end = (cx + arrow_len, cy - arrow_len // 2)
    else:
        end = (cx, cy - arrow_len)
    cv2.arrowedLine(out, (cx, cy), end, color, 3, tipLength=0.3)
    
    # Obstacle markers
    for obs in analysis.obstacles:
        if obs.distance == "near":
            obs_color = (0, 0, 255)  # red = danger
        elif obs.distance == "mid":
            obs_color = (0, 165, 255)  # orange
        else:
            obs_color = (0, 255, 255)  # yellow
        
        text = f"{obs.label} ({obs.distance})"
        x_pos = 10 if obs.position == "left" else (w - 180 if obs.position == "right" else w // 2 - 60)
        cv2.putText(out, text, (x_pos, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, obs_color, 1)
    
    return out


# ── Model loading (same as predict.py) ────────────────────────────────────────
def load_model(checkpoint: str, device: torch.device) -> nn.Module:
    model = lraspp_mobilenet_v3_large(weights=None)
    low_in  = model.classifier.low_classifier.in_channels
    high_in = model.classifier.high_classifier.in_channels
    model.classifier.low_classifier  = nn.Conv2d(low_in,  NUM_CLASSES, 1)
    model.classifier.high_classifier = nn.Conv2d(high_in, NUM_CLASSES, 1)

    ckpt = torch.load(checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    print(f"✅ Model loaded: {checkpoint}")
    return model


def preprocess(img: np.ndarray) -> torch.Tensor:
    resized = cv2.resize(img, (IMG_SIZE[1], IMG_SIZE[0]))
    rgb     = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    for c in range(3):
        rgb[..., c] = (rgb[..., c] - IMAGENET_MEAN[c]) / IMAGENET_STD[c]
    return torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0)


@torch.no_grad()
def segment(model, tensor, device):
    out = model(tensor.to(device))["out"]
    return out.argmax(1).squeeze(0).cpu().numpy().astype(np.uint8)


# ── CLI modes ─────────────────────────────────────────────────────────────────
def run_image(model, cnn_model, device, img_path: str, out_dir: str):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame   = cv2.imread(img_path)
    tensor  = preprocess(frame)
    seg     = segment(model, tensor, device)

    t0       = time.time()
    analysis = analyze_scene(seg, cnn_model, device)
    elapsed  = time.time() - t0

    print(f"\nProcessing {Path(img_path).name} — {elapsed*1000:.1f}ms")
    print("-" * 50)
    print(analysis.summary())

    resized = cv2.resize(frame, (IMG_SIZE[1], IMG_SIZE[0]))
    result  = draw_analysis(resized, analysis)

    out_path = out_dir / (Path(img_path).stem + "_scene.png")
    cv2.imwrite(str(out_path), result)
    print(f"Saved: {out_path}")

    cv2.imshow("Smart Helmet — Scene Analysis", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def run_folder(model, cnn_model, device, folder: str, out_dir: str):
    folder  = Path(folder)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    imgs = sorted(list(folder.rglob("*.jpg")) + list(folder.rglob("*.png")))[:100]
    print(f"Analyzing {len(imgs)} images...\n")

    stats = {"straight": 0, "left": 0, "right": 0, "junction": 0}

    for i, p in enumerate(imgs):
        frame    = cv2.imread(str(p))
        tensor   = preprocess(frame)
        seg      = segment(model, tensor, device)
        analysis = analyze_scene(seg)

        resized = cv2.resize(frame, (IMG_SIZE[1], IMG_SIZE[0]))
        result  = draw_analysis(resized, analysis)
        out_path = out_dir / (p.stem + "_scene.png")
        cv2.imwrite(str(out_path), result)

        direction = analysis.road_direction
        if "left" in direction:
            stats["left"] += 1
        elif "right" in direction:
            stats["right"] += 1
        elif "junction" in analysis.junction_type or "junction" in direction:
            stats["junction"] += 1
        else:
            stats["straight"] += 1

        print(f"[{i+1:3d}/{len(imgs)}] {p.name:40s} → {analysis.nav_instruction}")

    print(f"\n{'='*50}")
    print(f"  SCENE STATISTICS")
    print(f"{'='*50}")
    for k, v in stats.items():
        print(f"  {k:15s}: {v:3d} ({v/len(imgs)*100:.0f}%)")
    print(f"\n✅ Results saved to {out_dir}/")


def run_webcam(model, cnn_model, device):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Could not open webcam")
        return

    print("🎥 Live scene analysis — press Q to quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        t0       = time.time()
        tensor   = preprocess(frame)
        seg      = segment(model, tensor, device)
        analysis = analyze_scene(seg, cnn_model, device)
        elapsed  = time.time() - t0

        resized = cv2.resize(frame, (IMG_SIZE[1], IMG_SIZE[0]))
        result  = draw_analysis(resized, analysis)

        fps_text = f"FPS: {1/elapsed:.1f}"
        cv2.putText(result, fps_text, (IMG_SIZE[1] - 90, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        cv2.imshow("Smart Helmet — Scene Analysis", result)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Smart Helmet scene & turn detection")
    parser.add_argument("--checkpoint", default="models/best.pth")
    parser.add_argument("--cnn-checkpoint", default="models/scene_classifier.pth", help="Optional CNN model for scene overrides")
    parser.add_argument("--image",   type=str, help="Single image path")
    parser.add_argument("--folder",  type=str, help="Folder of images")
    parser.add_argument("--webcam",  action="store_true", help="Live webcam")
    parser.add_argument("--out-dir", default="scene_outputs")
    args = parser.parse_args()

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model  = load_model(args.checkpoint, device)
    
    cnn_model = None
    if Path(args.cnn_checkpoint).exists() and TinySceneCNN is not None:
        try:
            cnn_model = TinySceneCNN().to(device)
            ckpt = torch.load(args.cnn_checkpoint, map_location=device, weights_only=False)
            cnn_model.load_state_dict(ckpt["model_state_dict"])
            cnn_model.eval()
            print(f"✅ CNN Ensembling enabled: {args.cnn_checkpoint}")
        except Exception as e:
            print(f"⚠️ Could not load CNN model, using pure geometry: {e}")

    if args.image:
        run_image(model, cnn_model, device, args.image, args.out_dir)
    elif args.folder:
        run_folder(model, cnn_model, device, args.folder, args.out_dir)
    elif args.webcam:
        run_webcam(model, cnn_model, device)
    else:
        print("Usage:")
        print("  python3 scene_analyzer.py --image photo.jpg")
        print("  python3 scene_analyzer.py --folder val_images/")
        print("  python3 scene_analyzer.py --webcam")


if __name__ == "__main__":
    main()
