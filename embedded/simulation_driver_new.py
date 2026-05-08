import time
import math
import os
import xml.etree.ElementTree as ET
import sys

# Force UTF-8 encoding for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'

# ── ANSI Colors ──────────────────────────────────────────────────────────
CYAN    = ""
YELLOW  = ""
GREEN   = ""
RED     = ""
PURPLE  = ""
DIM     = ""
BOLD    = ""
RESET   = ""

def parse_kml_route(kml_file):
    """Parse KML file and return list of (lat, lon) tuples."""
    tree = ET.parse(kml_file)
    root = tree.getroot()
    
    # Find coordinates in LineString
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    coordinates_elem = root.find('.//kml:coordinates', ns)
    
    if coordinates_elem is None:
        raise ValueError("No coordinates found in KML")
    
    coords_text = coordinates_elem.text.strip()
    coords = []
    for line in coords_text.split():
        parts = line.split(',')
        if len(parts) >= 2:
            lon, lat = float(parts[0]), float(parts[1])
            coords.append((lat, lon))
    
    return coords

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

def main():
    print(f"\n{BOLD}{CYAN}{'='*60}")
    print(f"  SMART HELMET - Navigation Simulation Driver")
    print(f"{'='*60}{RESET}\n")
    
    try:
        # Load route from KML
        polyline = parse_kml_route("MITnavigation_route.kml")
        print(f"{GREEN}SUCCESS: Route loaded: {len(polyline)} waypoints{RESET}")
        print(f"{CYAN}SIMULATION: Speed ~400 km/h | Tick: 50ms{RESET}\n")
        print(f"{BOLD}{PURPLE}{'-'*60}")
        print(f"  [CV] + [DR] LIVE TELEMETRY LOG")
        print(f"{'-'*60}{RESET}\n")
        
        prev_heading = None
        step_count = 0
        drift_m = 0.0
        last_cv_log = 0
        last_dr_log = 0
        
        # Pre-calculate turns and distances
        turns = []
        for i in range(len(polyline) - 2):
            p1 = polyline[i]
            p2 = polyline[i+1]
            p3 = polyline[i+2]
            h1 = calculate_heading(p1, p2)
            h2 = calculate_heading(p2, p3)
            delta = heading_delta(h1, h2)
            dist_to_turn = calculate_distance(p1, p2)
            if abs(delta) > 10:  # Significant turn
                turns.append({
                    'index': i+1,
                    'turn': classify_turn(delta),
                    'distance': dist_to_turn,
                    'heading_delta': delta
                })
        
        current_turn_idx = 0
        
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
                
                # Calculate distance to next turn
                dist_next = 0
                instr = "CONTINUE STRAIGHT"
                if current_turn_idx < len(turns):
                    turn_info = turns[current_turn_idx]
                    if i < turn_info['index']:
                        dist_next = sum(calculate_distance(polyline[j], polyline[j+1]) for j in range(i, turn_info['index']))
                        instr = f"{turn_info['turn']} TURN"
                    elif i == turn_info['index']:
                        dist_next = dist * (1 - t)
                        instr = f"{turn_info['turn']} TURN"
                        if dist_next < 10:  # Close enough, move to next
                            current_turn_idx += 1
                
                # ── DR LOG (every ~1s) ─────────────────────────────────
                if now - last_dr_log > 1.0:
                    last_dr_log = now
                    hdelta = heading_delta(prev_heading, heading) if prev_heading is not None else 0
                    
                    drift_color = RED if drift_m > 20 else YELLOW if drift_m > 5 else GREEN
                    print(f"{YELLOW}[DR] #{step_count:>5} | Pos({lat:.5f}, {lon:.5f}) | Hdg: {heading:6.1f}° | Drift: {drift_color}{drift_m:.1f}m{RESET}")
                    
                    if abs(hdelta) > 5:
                        direction = "RIGHT" if hdelta > 0 else "LEFT"
                        print(f"{CYAN}[DR]        | Heading D: {'+' if hdelta > 0 else ''}{hdelta:.1f}° ({direction} turn detected){RESET}")
                    
                    if instr:
                        print(f"{GREEN}{BOLD}[NAV]       | NAV: {instr.upper()} (in {dist_next:.0f}m){RESET}")
                    
                    if 0 < dist_next < 80:
                        print(f"{GREEN}{BOLD}[DR]        | APPROACH: Approaching maneuver in {dist_next:.0f}m - Step #{current_turn_idx}{RESET}")
                    
                    conf_pct = 70
                    print(f"{DIM}[DR]        | Mode: GPS | Conf: {conf_pct}% | Step: {current_turn_idx}{RESET}")
                
                # ── CV LOG (every ~0.8s) ───────────────────────────────
                if now - last_cv_log > 0.8 and prev_heading is not None:
                    last_cv_log = now
                    
                    hdelta = heading_delta(prev_heading, heading)
                    scene = classify_turn(hdelta)
                    conf = 85 + (step_count % 12)  # simulated confidence
                    
                    print(f"{PURPLE}[CV] F#{step_count:>5} | Scene: {scene:<20} | Dhdg: {hdelta:+.1f}° | conf: {conf}%{RESET}")
                
                prev_heading = heading
                time.sleep(0.05)
                sys.stdout.flush()
                
        print(f"\n{GREEN}{BOLD}{'='*60}")
        print(f"  Journey Complete!")
        print(f"{'='*60}{RESET}\n")
        
    except KeyboardInterrupt:
        print(f"\n{YELLOW}STOPPED: Simulation stopped by user.{RESET}")
    except Exception as e:
        print(f"{RED}ERROR: Simulation Error: {e}{RESET}")

if __name__ == "__main__":
    main()
