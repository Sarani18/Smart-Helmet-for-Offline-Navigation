import cv2
import time
import os
import sys
import torch
from pathlib import Path

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    # Importing functional components from scene_analyzer
    from scene_analyzer import load_model, preprocess, segment, analyze_scene
    from models import TinySceneCNN
except ImportError as e:
    print(f"Error: Could not import scene_analyzer components: {e}")
    print("Make sure you are in the localization/CV directory.")
    sys.exit(1)

def main():
    print("\n" + "="*70)
    print("       SMART HELMET VISION - DETAILED TECHNICAL DEMO")
    print("="*70)
    
    # Device setup
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
        
    print(f"Using Device: {device}")

    # Initialize Models
    print("Loading AI Models (Ensemble)...")
    try:
        lraspp_model = load_model("models/best.pth", device)
        
        cnn_model = None
        cnn_path = Path("models/scene_classifier.pth")
        if cnn_path.exists():
            try:
                cnn_model = TinySceneCNN().to(device)
                ckpt = torch.load(str(cnn_path), map_location=device, weights_only=False)
                cnn_model.load_state_dict(ckpt["model_state_dict"])
                cnn_model.eval()
                print("Loaded CNN Classifier")
            except Exception as e:
                print(f"Warning: Could not load CNN Classifier: {e}")
                cnn_model = None
        
        print("Models Loaded Successfully!")
    except Exception as e:
        print(f"Failed to load models: {e}")
        return

    video_path = "sample_drive.mp4"
    if not os.path.exists(video_path):
        print(f"Error: {video_path} not found.")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    print(f"Video Location: {os.path.abspath(video_path)}")
    print("Detailed logs starting... Press CTRL+C to stop.\n")

    try:
        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            # Skip frames for readable log speed
            if frame_count % 5 != 0:
                continue

            # --- AI PIPELINE ---
            tensor = preprocess(frame)
            seg_mask = segment(lraspp_model, tensor, device)
            results = analyze_scene(seg_mask, cnn_model, device)

            # --- DETAILED OUTPUT ---
            # 1. Main Instruction
            print(f"--- FRAME {frame_count:04d} ---")
            print(f"INSTRUCTION : {results.nav_instruction}")
            print(f"CONFIDENCE  : {results.confidence:.1f}%")
            
            # 2. Road Geometry Stats
            side = "Center"
            if results.road_center_x < 0.4: side = "Drifting LEFT"
            elif results.road_center_x > 0.6: side = "Drifting RIGHT"
            
            print(f"ROAD STATS  : Coverage: {results.road_coverage_pct:.1f}% | Position: {side} ({results.road_center_x:.2f})")
            
            # 3. Features & Objects
            feat = []
            if results.junction_type != "none": feat.append(f"Junction({results.junction_type})")
            if results.obstacle_ahead: feat.append("CAUTION: Obstacle Ahead")
            
            print(f"FEATURES    : {', '.join(feat) if feat else 'Clear Path'}")
            
            # 4. Obstacle Breakdown
            if results.obstacles:
                obs_list = [f"{o.label}({o.distance})" for o in results.obstacles[:3]]
                print(f"OBSTACLES   : {', '.join(obs_list)}")
            
            print("-" * 40)

            # Small sleep to allow the user to actually read the text
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n\nDemo stopped by user.")
    finally:
        cap.release()
        print("\nFinished processing video.")

if __name__ == "__main__":
    main()
