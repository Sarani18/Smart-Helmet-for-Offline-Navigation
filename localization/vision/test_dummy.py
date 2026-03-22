import asyncio
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_dummy_pipeline():
    print("Sending nav-hint to dummy vision API...")
    start_time = time.time()
    
    response = client.post("/api/localization/nav-hint", json={
        "session_id": "test_session_999",
        "ts_ms": int(start_time * 1000),
        "expected_next_turn": "LEFT",
        "distance_to_next_turn_m": 50.0
    })
    
    print("nav-hint status:", response.status_code)
    print("nav-hint response:", response.json())
    assert response.status_code == 200
    
    print("\nWaiting 6 seconds to allow the mock background task to fire...")
    # The dummy pipeline sleeps for 5 seconds, so we wait 6 to see the log output.
    time.sleep(6)
    
if __name__ == "__main__":
    test_dummy_pipeline()
    print("Test finished.")
