import requests
import time
import math

def calculate_heading(p1, p2):
    """Calculate heading in degrees between two points."""
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    
    dLon = lon2 - lon1
    y = math.sin(dLon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - \
        math.sin(lat1) * math.cos(lat2) * math.cos(dLon)
    
    brng = math.atan2(y, x)
    return (math.degrees(brng) + 360) % 360

def main():
    session_id = "national_finals_google_demo"
    server_url = "http://localhost:8000"
    
    print("🚀 Connecting to Navigation Server (Secure)...")
    
    # Disable SSL warnings for self-signed certificates in dev
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # 1. Fetch current UI state to get the route polyline
    try:
        res = requests.post(f"{server_url}/api/navigation/ui/state", json={
            "session_id": session_id,
            "ts_ms": int(time.time() * 1000)
        }, verify=False)
        data = res.json()
        polyline = data.get("ui_state", {}).get("route_polyline", [])
        
        if not polyline:
            print("❌ Error: No route loaded. Please click 'START PUNE TRIP' in the browser first.")
            return
            
        print(f"✅ Route loaded with {len(polyline)} points.")
        print("🚦 Starting Real-Time Simulation...")
        
        # 2. Iterate through points and send as DR events
        for i in range(len(polyline) - 1):
            p1 = polyline[i]
            p2 = polyline[i+1]
            
            # Calculate heading for the segment
            heading = calculate_heading(p1, p2)
            
            # Sub-divide segment for smooth movement — 30 steps at 80ms = ~2.4s per segment
            steps = 30
            for s in range(steps):
                t = s / steps
                lat = p1[0] + (p2[0] - p1[0]) * t
                lon = p1[1] + (p2[1] - p1[1]) * t
                
                payload = {
                    "session_id": session_id,
                    "ts_ms": int(time.time() * 1000),
                    "lat": lat,
                    "lon": lon,
                    "heading": heading,
                    "speed_mps": 10.0
                }
                
                requests.post(f"{server_url}/api/navigation/localization/dead-reckoning-event", 
                              json=payload, verify=False)
                
                print(f"📍 Pos: {lat:.5f}, {lon:.5f} | Heading: {heading:.1f}°", end="\r")
                time.sleep(0.08)  # 80ms = ~12.5 updates/sec — smooth like Google Maps
                
        print("\n🏁 Journey Complete! Simplified Demo Path finished.")
        
    except Exception as e:
        print(f"❌ Simulation Error: {e}")

if __name__ == "__main__":
    main()
