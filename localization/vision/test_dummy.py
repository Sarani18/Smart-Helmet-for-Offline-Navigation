import asyncio
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_vision_architecture():
    print("--- 1. Sending Navigation Hint ---")
    start_time = time.time()
    
    # 1. Send the hint. This should NOT trigger detections, only adjust weights.
    nav_response = client.post("/api/localization/nav-hint", json={
        "session_id": "test_session_999",
        "ts_ms": int(start_time * 1000),
        "expected_next_turn": "LEFT",
        "distance_to_next_turn_m": 50.0
    })
    
    print("nav-hint status:", nav_response.status_code)
    print("nav-hint response:", nav_response.json())
    assert nav_response.status_code == 200
    
    print("\n--- 2. Sending Camera Frame ---")
    # 2. Send the frame. THIS triggers the actual detections.
    image_bytes = b"dummy_image_data_here"
    frame_response = client.post(
        "/api/localization/frame",
        data={"session_id": "test_session_999", "ts_ms": int(start_time * 1000) + 100},
        files={"image": ("test.jpg", image_bytes, "image/jpeg")}
    )
    
    print("frame status:", frame_response.status_code)
    print("frame response:", frame_response.json())
    assert frame_response.status_code == 200
    
    print("\n--- 3. Waiting for Background Detections ---")
    # The dummy pipeline sleeps for 1.5 seconds total, so we wait 2 to see the log output.
    # Check the console logs to see both unexpected and expected detections being emitted!
    time.sleep(2)
    
if __name__ == "__main__":
    test_vision_architecture()
    print("Test finished.")
