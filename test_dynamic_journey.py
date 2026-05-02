import requests
import time
import uuid

def send_cv_event(session_id, landmark_name):
    payload = {
        "session_id": session_id,
        "event_id": f"evt_cv_{uuid.uuid4().hex[:6]}",
        "ts_ms": int(time.time() * 1000),
        "event_type": "LANDMARK",
        "confidence": 0.95,
        "payload": {
            "landmark_class": "JUNCTION",
            "map_hint_name": landmark_name,
            "landmark": landmark_name
        }
    }
    try:
        requests.post("http://localhost:8000/api/navigation/localization/visual-event", json=payload)
        print(f"✅ AI Spotted Landmark: {landmark_name}")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    session_id = "test_mobile_session"
    landmarks = ["Shaniwar Wada", "PMC Junction", "COEP Subway", "Pune Station Gate"]
    
    print(f"🚦 Starting Dynamic Journey Simulator...")
    print(f"Connecting to session: {session_id}")
    
    for landmark in landmarks:
        print(f"\nDriving... 🏎️")
        time.sleep(4) # Wait between detections
        send_cv_event(session_id, landmark)
        print("Check your phone/emulator for the Vision alert!")

    print("\n🏁 Journey Simulation Complete.")

if __name__ == "__main__":
    main()
