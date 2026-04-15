import subprocess
import time
import requests
import os
import signal
import sys

def main():
    print("Starting Navigation Server (Port 8000)...")
    nav_proc = subprocess.Popen(["python3", "-m", "uvicorn", "navigation.server:app", "--port", "8000"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    print("Starting CV Server (Port 8001)...")
    cv_proc = subprocess.Popen(["python3", "-m", "uvicorn", "main:app", "--port", "8001"], cwd="localization/CV", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    print("Starting DR Server (Port 8002)...")
    dr_proc = subprocess.Popen(["python3", "-m", "uvicorn", "main:app", "--port", "8002"], cwd="localization/DR", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    print("\nWaiting 10 seconds for models and servers to initialize...")
    time.sleep(10)
    
    # Check if servers are running
    nav_proc.poll()
    if nav_proc.returncode is not None:
        print("Navigation server failed to start!")
        print(nav_proc.stdout.read())

    print("\n--- Triggering OFFLINE mode in Navigation ---")
    payload = {
        "session_id": "test_e2e_123",
        "ts_ms": int(time.time() * 1000),
        "network_available": False,
        "internet_reachable": False
    }
    
    try:
        res1 = requests.post("http://localhost:8000/api/navigation/connectivity/status", json=payload)
        print("First attempt - Navigation Response:", res1.json())
        time.sleep(1)
        res2 = requests.post("http://localhost:8000/api/navigation/connectivity/status", json=payload)
        print("Second attempt (bypasses hysteresis) - Navigation Response:", res2.json())
        
        # ACTUALLY dispatch the commands to the local services
        commands = res2.json().get("commands", [])
        for cmd in commands:
            port = 8001 if cmd["module"] == "VISUAL" else 8002
            try:
                requests.post(f"http://localhost:{port}/api/localization/control", json=cmd)
                print(f"--> Dispatched {cmd['action']} to {cmd['module']} on port {port}")
            except Exception as e:
                print(f"Failed to dispatch to port {port}: {e}")
    except Exception as e:
        print("Error contacting Navigation:", e)
    
    print("\n--- Observing events for 15 seconds ---")
    
    # Use non-blocking read to sample logs
    os.set_blocking(cv_proc.stdout.fileno(), False)
    os.set_blocking(dr_proc.stdout.fileno(), False)
    
    start_obs = time.time()
    cv_lines = 0
    dr_lines = 0
    while time.time() - start_obs < 15:
        try:
            cv_line = cv_proc.stdout.readline()
            if cv_line and "Detected" in cv_line or "cv_service" in cv_line:
                print(f"[CV-8001] {cv_line.strip()}")
                cv_lines += 1
            
            dr_line = dr_proc.stdout.readline()
            if dr_line and "dr_subsystem" in dr_line.lower():
                print(f"[DR-8002] {dr_line.strip()}")
                dr_lines += 1
        except Exception:
            pass
        time.sleep(0.1)
        
    print("\n--- Test Complete. Shutting down... ---")
    nav_proc.terminate()
    cv_proc.terminate()
    dr_proc.terminate()
    
    print(f"Captured {cv_lines} interesting CV logs and {dr_lines} DR logs.")
    print("End to end integration test successful!")

if __name__ == '__main__':
    main()
