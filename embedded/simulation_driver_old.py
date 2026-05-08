import requests
import time
import math
import os

# Force UTF-8 encoding for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'

# ── ANSI Colors ──────────────────────────────────────────────────────────
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
RED     = "\033[91m"
PURPLE  = "\033[95m"
DIM     = "\033[90m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

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

def heading_delta(h1, h2):
    """Signed heading change (-180 to +180)."""
    d = ((h2 - h1 + 540) % 360) - 180
    return d

def classify_turn(delta):
    """Classify a heading change strictly into NCS TurnClass enum values."""
    a = abs(delta)
    if a < 5:    return "STRAIGHT"
    if a < 30:   return "SLIGHT_LEFT" if delta < 0 else "SLIGHT_RIGHT"
    if a < 150:  return "LEFT" if delta < 0 else "RIGHT"
    return "U_TURN"

def classify_junction(delta, instr):
    """Detect junction type from heading + instruction text (LandmarkClass)."""
    a = abs(delta)
    lower = (instr or "").lower()
    if "roundabout" in lower or "circle" in lower: return "ROUNDABOUT"
    if "fork" in lower or a > 60 or a > 25:        return "JUNCTION"
    return None

def main():
    session_id = "NATIONAL_FINALS_2026"
    server_url = "http://localhost:8000"
    
    print(f"\n{BOLD}{CYAN}{'='*60}")
    print(f"  SMART HELMET — Navigation Simulation Driver")
    print(f"{'='*60}{RESET}\n")
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        res = requests.post(f"{server_url}/api/navigation/ui/state", json={
            "session_id": session_id,
            "ts_ms": int(time.time() * 1000)
        }, verify=False)
        data = res.json()
        ui = data.get("ui_state", {})
        polyline = ui.get("route_polyline", [])
        
        if not polyline:
            print(f"{RED}ERROR: No route loaded. Click START in the browser first.{RESET}")
            return
            
        print(f"{GREEN}SUCCESS: Route loaded: {len(polyline)} waypoints{RESET}")
        print(f"{CYAN}SIMULATION: Speed ~400 km/h | Tick: 50ms{RESET}\n")
        print(f"{BOLD}{PURPLE}{'─'*60}")
        print(f"  [CV] + [DR] LIVE TELEMETRY LOG")
        print(f"{'─'*60}{RESET}\n")
        
        prev_heading = None
        step_count = 0
        drift_m = 0.0
        last_cv_log = 0
        last_dr_log = 0
        
        for i in range(len(polyline) - 1):
            p1 = polyline[i]
            p2 = polyline[i+1]
            heading = calculate_heading(p1, p2)
            dist = calculate_distance(p1, p2)
            
            # Constant speed: ~111 m/s (approx 400 km/h)
            steps = max(1, int(dist / 5.5))
            
            for s in range(steps):
                step_count += 1
                t = s / steps
                lat = p1[0] + (p2[0] - p1[0]) * t
                lon = p1[1] + (p2[1] - p1[1]) * t
                now = time.time()
                
                payload = {
                    "session_id": session_id,
                    "ts_ms": int(now * 1000),
                    "lat": lat,
                    "lon": lon,
                    "heading": heading,
                    "speed_mps": 10.0
                }
                
                resp = requests.post(
                    f"{server_url}/api/navigation/localization/dead-reckoning-event", 
                    json=payload, verify=False
                )
                
                try:
                    r = resp.json()
                    ui_state = r.get("ui_state", {})
                    instr = ui_state.get("next_instruction_text", "")
                    dist_next = ui_state.get("distance_to_next_m", 0)
                    confidence = ui_state.get("confidence", 0)
                    pos_mode = ui_state.get("position_mode", "GPS")
                    active_step = ui_state.get("active_step_index", 0)
                    drift_m = ui_state.get("uncertainty_m", 0)
                except:
                    instr = ""
                    dist_next = 0
                    confidence = 0
                    pos_mode = "GPS"
                    active_step = 0
                
                # ── DR LOG (every ~1s) ─────────────────────────────────
                if now - last_dr_log > 1.0:
                    last_dr_log = now
                    hdelta = heading_delta(prev_heading, heading) if prev_heading is not None else 0
                    
                    drift_color = RED if drift_m > 20 else YELLOW if drift_m > 5 else GREEN
                    print(f"{YELLOW}[DR] #{step_count:>5} │ Pos({lat:.5f}, {lon:.5f}) │ Hdg: {heading:6.1f}° │ Drift: {drift_color}{drift_m:.1f}m{RESET}")
                    
                    if abs(hdelta) > 5:
                        direction = "RIGHT" if hdelta > 0 else "LEFT"
                        print(f"{CYAN}[DR]        │ Heading Δ: {'+' if hdelta > 0 else ''}{hdelta:.1f}° ({direction} turn detected){RESET}")
                    
                    if instr:
                        print(f"{GREEN}{BOLD}[NAV]       │ NAV: {instr.upper()} (in {dist_next:.0f}m){RESET}")
                    
                    if 0 < dist_next < 80:
                        print(f"{GREEN}{BOLD}[DR]        │ APPROACH: Approaching maneuver in {dist_next:.0f}m — Step #{active_step}{RESET}")
                    
                    conf_pct = int(confidence * 100)
                    print(f"{DIM}[DR]        │ Mode: {pos_mode} │ Conf: {conf_pct}% │ Step: {active_step}{RESET}")
                
                # ── CV LOG (every ~0.8s) ───────────────────────────────
                if now - last_cv_log > 0.8 and prev_heading is not None:
                    last_cv_log = now
                    
                    hdelta = heading_delta(prev_heading, heading)
                    scene = classify_turn(hdelta)
                    junction = classify_junction(hdelta, instr)
                    conf = 85 + (step_count % 12)  # simulated confidence
                    
                    print(f"{PURPLE}[CV] F#{step_count:>5} │ Scene: {scene:<20} │ Δhdg: {hdelta:+.1f}° │ conf: {conf}%{RESET}")
                    
                    # 1. Fire CV Turn Event to NCS
                    cv_payload = {
                        "session_id": session_id,
                        "event_id": f"sim_cv_{step_count}",
                        "ts_ms": int(now * 1000),
                        "event_type": "TURN",
                        "confidence": conf / 100.0,
                        "payload": {
                            "turn_class": scene
                        }
                    }
                    try:
                        requests.post(f"{server_url}/api/navigation/localization/visual-event", json=cv_payload, verify=False)
                    except: pass
                    
                    # 2. Fire CV Landmark Event to NCS if junction detected
                    if junction:
                        print(f"{YELLOW}{BOLD}[CV]        │ JUNCTION: {junction}{RESET}")
                        landmark_payload = {
                            "session_id": session_id,
                            "event_id": f"sim_cv_lm_{step_count}",
                            "ts_ms": int(now * 1000) + 1,
                            "event_type": "LANDMARK",
                            "confidence": 0.9,
                            "payload": {
                                "landmark_class": junction
                            }
                        }
                        try:
                            requests.post(f"{server_url}/api/navigation/localization/visual-event", json=landmark_payload, verify=False)
                        except: pass
                
                prev_heading = heading
                time.sleep(0.05)
                
        print(f"\n{GREEN}{BOLD}{'='*60}")
        print(f"  🏁 Journey Complete!")
        print(f"{'='*60}{RESET}\n")
        
    except KeyboardInterrupt:
        print(f"\n{YELLOW}STOPPED: Simulation stopped by user.{RESET}")
    except Exception as e:
        print(f"{RED}ERROR: Simulation Error: {e}{RESET}")

if __name__ == "__main__":
    main()
