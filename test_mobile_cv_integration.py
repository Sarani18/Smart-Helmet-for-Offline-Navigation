import requests
import time
import uuid

def main():
    session_id = "test_mobile_session"
    print(f"🚀 Starting Mobile-CV Integration Test (Session: {session_id})")
    print("Ensure the Python Navigation Server is running on Port 8000.")
    print("Ensure your Mobile App is connected to the same network.")

    # 1. Simulate a Vision Detection (e.g., PMC Junction)
    print("\n[Step 1] Injecting a Visual Landmark (PMC Junction)...")
    payload = {
        "session_id": session_id,
        "event_id": f"evt_cv_{uuid.uuid4().hex[:6]}",
        "ts_ms": int(time.time() * 1000),
        "event_type": "LANDMARK",
        "confidence": 0.98,
        "payload": {
            "landmark_class": "JUNCTION",
            "map_hint_name": "PMC Junction",
            "landmark": "PMC Main Building"
        }
    }

    try:
        res = requests.post("http://localhost:8000/api/navigation/localization/visual-event", json=payload)
        if res.ok:
            print("✅ Visual Event Injected Successfully.")
        else:
            print(f"❌ Failed to inject: {res.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

    # 2. Instruct the user
    print("\n[Step 2] Verification")
    print("Verify the following on your Mobile App:")
    print("1. Does a 'VISION CONFIRMED' or 'PMC' badge appear?")
    print("2. Does the confidence bar increase?")
    print("3. Check the console logs (Metro Bundler) for '[Coordinator] CV Correction received'.")

if __name__ == "__main__":
    main()
