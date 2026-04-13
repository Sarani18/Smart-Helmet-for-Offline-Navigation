from typing import List, Optional
import time
import asyncio
from fastapi import FastAPI, APIRouter, File, UploadFile, BackgroundTasks, HTTPException, Form
from pydantic import BaseModel
import httpx
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- API Models ---
class NavHintMessage(BaseModel):
    session_id: str
    ts_ms: int
    expected_next_turn: str
    distance_to_next_turn_m: float
    upcoming_features: Optional[List[str]] = None

class ActionResponse(BaseModel):
    status: str
    message: str

app = FastAPI(title="Dummy Vision API", version="1.0.0")
router = APIRouter(prefix="/api/localization", tags=["Localization"])

# Mock navigation API endpoint. If needed, the actual URL can be provided here.
NAV_API_URL = "http://127.0.0.1:8000/api/navigation/localization/visual-event"

# Global state to simulate internal weighting for CV detection modules
# The 'distance_m' helps the module know how soon the turn should be appearing 
# (e.g. at 50m we expect it to start entering the frame, at 10m it should be very prominent).
current_nav_hint = "STRAIGHT"
current_distance_m = 0.0

# --- Dummy CV Pipeline ---
async def process_frame_pipeline(session_id: str, ts_ms: int):
    """
    Mock pipeline that simulates processing a camera frame sequentially.
    Actual CV code would run inferences here like:
      - Scene Detection (Turns, Intersections)
      - Object Detection (Traffic Lights, Stop Signs, Potholes)
      - Depth / Distance Estimation
      
    This function will report everything it detects, irrespective of the hint,
    giving the Navigation controller all the data it needs to reason about the environment.
    """
    logger.debug(
        f"[Vision] Processing frame at ts={ts_ms}. Internal CV thresholds adjusted for "
        f"'{current_nav_hint}' expected in {current_distance_m}m."
    )
    await asyncio.sleep(1.0) # simulate inference time
    
    # 1. Simulate finding an unexpected feature first (e.g., an intersection)
    unexpected = "LEFT" if current_nav_hint != "LEFT" else "RIGHT"
    payload1 = {
        "session_id": session_id,
        "event_id": f"evt_{int(time.time() * 1000)}_1",
        "ts_ms": int(time.time() * 1000),
        "event_type": "TURN",
        "confidence": 0.60, # Lower confidence because it wasn't hinted
        "payload": {
            "turn_class": unexpected
        }
    }
    
    # 2. Simulate finding the expected feature a moment later
    payload2 = {
        "session_id": session_id,
        "event_id": f"evt_{int(time.time() * 1000)}_2",
        "ts_ms": int(time.time() * 1000),
        "event_type": "TURN",
        "confidence": 0.95, # Higher confidence because it was hinted
        "payload": {
            "turn_class": current_nav_hint
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"[Vision Dummy] Emitting unexpected detection: {unexpected}")
            await client.post(NAV_API_URL, json=payload1)
            
            await asyncio.sleep(0.5) # Slight delay between detections
            
            logger.info(f"[Vision Dummy] Emitting expected detection: {current_nav_hint}")
            await client.post(NAV_API_URL, json=payload2)
            
        except Exception as e:
            logger.error(f"[Vision Dummy] Failed to push event to Navigation API: {e}")



# --- Endpoints ---
@router.post("/nav-hint", response_model=ActionResponse)
async def receive_nav_hint(hint: NavHintMessage):
    """
    Called by Navigation System. Provides context regarding what map feature is approaching.
    
    IMPORTANT: The Vision module uses this data strictly to alter detection sensitivity 
    (e.g., lower the confidence threshold required to confirm a 'LEFT' turn).
    It does NOT restrict the Vision module to ONLY return the expected turn.
    """
    global current_nav_hint, current_distance_m
    current_nav_hint = hint.expected_next_turn
    current_distance_m = hint.distance_to_next_turn_m
    
    logger.debug(
        f"[Vision] Received /nav-hint. Internal state updated: "
        f"Prioritize '{current_nav_hint}' at {current_distance_m} meters."
    )
    
    # Note: No pipeline is triggered here. The CV runs continuously on frames.
    return ActionResponse(status="success", message="Navigation hints updated")


@router.post("/frame", response_model=ActionResponse)
async def receive_camera_frame(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    ts_ms: Optional[int] = Form(None),
    image: UploadFile = File(...)
):
    """
    Called by MCU/Camera bridge -> Localization (Vijit)
    This triggers the actual vision pipelines (e.g., scene detection, object detection).
    """
    if not ts_ms:
        ts_ms = int(time.time() * 1000)
        
    # Start the dummy detection processing for this frame
    background_tasks.add_task(
        process_frame_pipeline, 
        session_id=session_id, 
        ts_ms=ts_ms
    )
    
    return ActionResponse(status="queued", message="Frame processing started")

# Register router
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    # Make sure we avoid collision with navigation module (usually 8000), so we use 8001
    logger.info("Starting Vision Dummy server on port 8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
