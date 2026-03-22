from typing import List, Optional
import time
import asyncio
from fastapi import FastAPI, APIRouter, File, UploadFile, BackgroundTasks, HTTPException, Form
from pydantic import BaseModel
import httpx
import logging

logging.basicConfig(level=logging.INFO)
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

# --- Dummy CV Pipeline ---
async def dummy_vision_pipeline(session_id: str, expected_turn: str):
    """
    Mock pipeline that simulates processing time (e.g. tracking features),
    and then immediately sends a visual-event to navigation indicating
    the expected feature was detected.
    """
    logger.info(f"[Vision Dummy] Processing 'nav-hint': waiting 5 seconds before artificially discovering '{expected_turn}'.")
    await asyncio.sleep(5.0)
    
    # payload as prescribed by INTEGRATION_CONSIDERATIONS.md
    payload = {
        "session_id": session_id,
        "event_id": f"evt_{int(time.time() * 1000)}",
        "ts_ms": int(time.time() * 1000),
        "event_type": "TURN",
        "confidence": 0.95,
        "payload": {
            "turn_class": expected_turn
        }
    }
    
    logger.info(f"[Vision Dummy] Timer expired. Publishing '{expected_turn}' to Navigation.")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(NAV_API_URL, json=payload)
            response.raise_for_status()
            logger.info("[Vision Dummy] Successfully submitted visual-event mock.")
        except Exception as e:
            logger.error(f"[Vision Dummy] Failed to push event to Navigation API: {e}. Is the Navigation API server running at {NAV_API_URL}?")


# --- Endpoints ---
@router.post("/nav-hint", response_model=ActionResponse)
async def receive_nav_hint(hint: NavHintMessage, background_tasks: BackgroundTasks):
    """
    Called by Navigation (Sanskruti) -> Localization (Vijit)
    Sends an expected maneuver alert.
    Triggers the mock CV pipeline in the background.
    """
    # Start the dummy detection logic
    background_tasks.add_task(
        dummy_vision_pipeline, 
        session_id=hint.session_id, 
        expected_turn=hint.expected_next_turn
    )
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
    In this dummy implementation, frames are received and silently ignored.
    """
    if not ts_ms:
        ts_ms = int(time.time() * 1000)
        
    logger.info(f"[Vision Dummy] Received frame for session_id {session_id} but dropping it to /dev/null.")
    return ActionResponse(status="queued", message="Frame processing started (mocked, no-op)")

# Register router
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    # Make sure we avoid collision with navigation module (usually 8000), so we use 8001
    logger.info("Starting Vision Dummy server on port 8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
