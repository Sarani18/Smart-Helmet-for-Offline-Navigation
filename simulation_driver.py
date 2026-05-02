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

def calculate_distance(p1, p2):
    R = 6371000
    phi1, phi2 = math.radians(p1[0]), math.radians(p2[0])
    dphi = math.radians(p2[0] - p1[0])
    dlam = math.radians(p2[1] - p1[1])
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def main():
    session_id = "NATIONAL_FINALS_2026"
    server_url = "http://localhost:8000"
    
    print("🚀 Connecting to Navigation Server (Secure)...")
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
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
        print("🚦 Starting Real-Time Simulation at 900 km/h...")
        
        for i in range(len(polyline) - 1):
            p1 = polyline[i]
            p2 = polyline[i+1]
            heading = calculate_heading(p1, p2)
            dist = calculate_distance(p1, p2)
            
            # Constant speed: 250 m/s (approx 900 km/h)
            # Update interval: 50ms (0.05s) -> distance per step = 250 * 0.05 = 12.5m
            steps = max(1, int(dist / 12.5))
            
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
                time.sleep(0.05)  # 80ms = ~12.5 updates/sec — smooth like Google Maps
                
        print("\n🏁 Journey Complete! Simplified Demo Path finished.")
        
    except Exception as e:
        print(f"❌ Simulation Error: {e}")

if __name__ == "__main__":
    main()
