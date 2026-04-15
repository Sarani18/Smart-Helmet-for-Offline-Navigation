"""
CV Service 
FastAPI microservice for parallel integration in Smart Helmet.
Listens for START/STOP commands from Navigation. When running, processes
frames (from a video file or webcam) using the scene analyzer and posts
visual events to the Navigation module.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional
from pathlib import Path

import cv2
import httpx
import torch
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel, Field

# Import our inference engine
from scene_analyzer import (
    load_model, preprocess, segment, analyze_scene,
    IMG_SIZE, SCENE_COLORS
)
try:
    from models import TinySceneCNN
except ImportError:
    TinySceneCNN = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cv_service")

# --- Configuration ---
NAV_API_URL = "http://localhost:8000/api/navigation/localization/visual-event"
PORT = 8001
VIDEO_SOURCE = "sample_drive.mp4" # Using sample video for testing

# --- Globals for State and Inference ---
class CVState:
    running: bool = False
    session_id: str = ""
    # Model cache
    device = None
    lraspp_model = None
    cnn_model = None

state = CVState()

# Load models exactly once on startup
logger.info("Initializing CV Inference Models...")
state.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
try:
    state.lraspp_model = load_model("models/best.pth", state.device)
except Exception as e:
    logger.error(f"Failed to load main segmentation model: {e}")

if Path("models/scene_classifier.pth").exists() and TinySceneCNN is not None:
    try:
        state.cnn_model = TinySceneCNN().to(state.device)
        ckpt = torch.load("models/scene_classifier.pth", map_location=state.device, weights_only=False)
        state.cnn_model.load_state_dict(ckpt["model_state_dict"])
        state.cnn_model.eval()
        logger.info("✅ CNN Ensembling loaded.")
    except Exception as e:
        logger.warning(f"Could not load CNN model: {e}")

# --- Pydantic Models for FastAPI ---
class ControlCommand(BaseModel):
    session_id: str
    ts_ms: int
    module: str
    action: str = Field(..., pattern="^(START|STOP)$")
    reason: str = ""

class NavHintMessage(BaseModel):
    session_id: str
    ts_ms: int
    expected_next_turn: str
    distance_to_next_turn_m: float

class ActionResponse(BaseModel):
    status: str
    message: str

# --- FastAPI App ---
app = FastAPI(title="CV Service", version="1.0.0")

@app.post("/api/localization/control", response_model=ActionResponse)
async def control_cv(cmd: ControlCommand, background_tasks: BackgroundTasks):
    """Start or Stop the CV inference loop based on Network status."""
    if cmd.module not in ["VISUAL", "ALL"]:
        return ActionResponse(status="ignored", message="Command not for VISUAL module")

    if cmd.action == "START":
        if not state.running:
            state.running = True
            state.session_id = cmd.session_id
            background_tasks.add_task(cv_inference_loop)
            logger.info(f"CV Engine STARTED (Reason: {cmd.reason})")
        return ActionResponse(status="started", message="CV engine started")
    
    elif cmd.action == "STOP":
        state.running = False
        logger.info(f"CV Engine STOPPED (Reason: {cmd.reason})")
        return ActionResponse(status="stopped", message="CV engine stopped")
    
    return ActionResponse(status="error", message="Unknown action")

@app.post("/api/localization/nav-hint")
async def receive_nav_hint(hint: NavHintMessage):
    """Optional hint from Navigation to prioritize certain detections."""
    logger.info(f"Received Nav Hint: Expected {hint.expected_next_turn} in {hint.distance_to_next_turn_m}m")
    return {"status": "accepted"}

# --- Background Task: Video Processing Loop ---
async def cv_inference_loop():
    """
    Reads the video file, infers frame by frame, and broadcasts events if a turn or junction is detected.
    """
    logger.info(f"Opening video source: {VIDEO_SOURCE}")
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        logger.error(f"Cannot open {VIDEO_SOURCE}")
        state.running = False
        return

    # Throttle inference to simulate real-time processing and save CPU
    TARGET_FPS = 5
    frame_duration = 1.0 / TARGET_FPS

    # Keep track of last emitted to prevent spamming
    last_emitted_turn = "STRAIGHT"
    last_emitted_junction = "none"
    frames_since_event = 0

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            while state.running:
                loop_start = time.time()
                
                ret, frame = cap.read()
                if not ret:
                    # Video ended, loop it
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                # Run Inference
                tensor = preprocess(frame)
                seg = segment(state.lraspp_model, tensor, state.device)
                analysis = analyze_scene(seg, state.cnn_model, state.device)

                # Map turns to Navigation spec
                turn_map = {
                    "slight_left": "SLIGHT_LEFT",
                    "left_turn": "LEFT",
                    "sharp_left": "LEFT",
                    "slight_right": "SLIGHT_RIGHT",
                    "right_turn": "RIGHT",
                    "sharp_right": "RIGHT",
                    "u_turn": "U_TURN",
                    "none": "STRAIGHT"
                }

                current_turn = turn_map.get(analysis.turn_type, "STRAIGHT")
                if current_turn == "STRAIGHT": 
                    # fallback to road_direction if there is no immediate turn
                    dir_map = {"slight_left": "SLIGHT_LEFT", "left_curve": "LEFT", "slight_right": "SLIGHT_RIGHT", "right_curve":"RIGHT"}
                    current_turn = dir_map.get(analysis.road_direction, "STRAIGHT")

                current_junction = analysis.junction_type

                confidence_scale = analysis.confidence / 100.0

                frames_since_event += 1

                # 1. Emit TURN Event if it changed significantly
                if current_turn != "STRAIGHT" and current_turn != last_emitted_turn and frames_since_event > 5:
                    logger.info(f"🛣️ Detected Turn: {current_turn} ({confidence_scale*100:.0f}%)")
                    payload = {
                        "session_id": state.session_id,
                        "event_id": f"evt_cv_{uuid.uuid4().hex[:8]}",
                        "ts_ms": int(time.time() * 1000),
                        "event_type": "TURN",
                        "confidence": confidence_scale,
                        "payload": {"turn_class": current_turn}
                    }
                    try:
                        await client.post(NAV_API_URL, json=payload)
                        last_emitted_turn = current_turn
                        frames_since_event = 0
                    except Exception as e:
                        logger.warning(f"Failed to send TURN event: {e}")

                # 2. Emit LANDMARK (Junction) Event
                if current_junction in ["t_junction", "y_junction", "crossroad"] and current_junction != last_emitted_junction and frames_since_event > 5:
                    logger.info(f"⚠️ Detected Junction: {current_junction} ({confidence_scale*100:.0f}%)")
                    payload = {
                        "session_id": state.session_id,
                        "event_id": f"evt_cv_{uuid.uuid4().hex[:8]}",
                        "ts_ms": int(time.time() * 1000),
                        "event_type": "LANDMARK",
                        "confidence": confidence_scale,
                        "payload": {
                            "landmark_class": "JUNCTION",
                            "map_hint_name": current_junction
                        }
                    }
                    try:
                        await client.post(NAV_API_URL, json=payload)
                        last_emitted_junction = current_junction
                        frames_since_event = 0
                    except Exception as e:
                        logger.warning(f"Failed to send LANDMARK event: {e}")

                # Reset emitting guards when returning to normal
                if current_turn == "STRAIGHT":
                    last_emitted_turn = "STRAIGHT"
                if current_junction == "none":
                    last_emitted_junction = "none"

                # Throttle
                elapsed = time.time() - loop_start
                sleep_time = max(0, frame_duration - elapsed)
                await asyncio.sleep(sleep_time)

    except Exception as e:
        logger.error(f"Inference loop crashed: {e}")
    finally:
        cap.release()
        state.running = False
        logger.info("CV Inference Loop terminated.")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting CV Service on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
