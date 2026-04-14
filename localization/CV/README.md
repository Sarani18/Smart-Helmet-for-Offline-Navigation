# Computer Vision (CV) Module — Smart Helmet Navigation

This module provides real-time semantic segmentation and scene analysis for the Smart Helmet, enabling offline navigation through visual road understanding and turn detection.

---

## 🏗 System Architecture

The vision system uses a **Two-Layer Pipeline** to transition from raw pixels to navigation instructions:

### Layer 1: Semantic Segmentation (Deep Learning)
- **Model:** LRASPP MobileNetV3-Large
- **Dataset:** IDD (India Driving Dataset) — 20,000+ images of Indian road scenes.
- **Output:** Pixel-level classification (Road, Vehicles, Pedestrians, Buildings, etc.)

### Layer 2: Scene Analyzer (Ensemble Logic)
Analyzes the road mask from Layer 1 using two complementary methods:
1.  **Skeletonization (Geometry):** Uses morphological thinning to extract the road centerline. Calculates curvature and heading angles. Robust against road occlusions (e.g., vehicles blocking the view).
2.  **Tiny Scene CNN (Student Model):** A lightweight 100K parameter CNN trained on 20,000+ auto-labeled road masks. Specializes in recognizing complex patterns like **Junctions (T-junction, Crossroad)** and **Sharp Turns**.
3.  **Ensemble Merger:** Prioritizes CNN classification for junctions and sharp turns when confidence is high (>70%), falling back to robust skeleton geometry for exact steering and road drifts.

---

## 🚀 Execution Instructions

### 1. Training the Segmentation Model
Train the main segmentation model on the IDD dataset:
```bash
python3 train.py --data-dir data/idd/idd20kII --data-dir2 data/idd/IDD_Segmentation
```

### 2. Auto-Labeling for Scene Analysis
Generate training data for the Scene Classifier by auto-labeling the dataset using the current skeleton logic:
```bash
python3 auto_label_scenes.py
```
*Outputs `scene_labels.csv` and 64x64 road masks in `road_masks/`.*

### 3. Training the Scene Classifier CNN
Train the lightweight ensemble CNN on the auto-labeled masks:
```bash
python3 train_scene_classifier.py --epochs 20
```
*Outputs `models/scene_classifier.pth` and `models/scene_classifier.onnx`.*

### 4. Running Scene Analysis
Execute the full analyzer on a folder of images or a single file:
```bash
# Analyze validation folder
python3 scene_analyzer.py --folder data/idd/idd20kII/leftImg8bit/val --out-dir scene_outputs

# Single image analysis
python3 scene_analyzer.py --image path/to/frame.jpg
```

### 5. Mobile Deployment (ONNX Export)
Export the main segmentation model for Android integration:
```bash
python3 export_onnx.py --checkpoint models/best.pth --output models/helmet_model.onnx
```

---

## 📂 Key Files

- `scene_analyzer.py`: The main inference engine and ensemble merger.
- `auto_label_scenes.py`: Self-supervised data generation for scene analysis.
- `train_scene_classifier.py`: Training script for the tiny 100K param CNN.
- `export_onnx.py`: Tool for mobile model conversion.
- `train.py`: Segmentation training script for LRASPP MobileNetV3.

---

## 🛠 Features

- **Robust Road Detection:** Morphological skeletonization ensures stable centerline tracking even with vehicle occlusions.
- **Junction Awareness:** CNN-powered recognition of T-junctions, Y-forks, and Intersections.
- **Turn Detection:** Classified into Sharp, Normal, and Slight turns for precise voice navigation.
- **Obstacle Warning:** Real-time distance estimation for vehicles and pedestrians in the camera's center path.
- **Mobile-First Design:** All models are highly optimized (LRASPP + Tiny CNN) for low-latency execution on mobile hardware via ONNX.
