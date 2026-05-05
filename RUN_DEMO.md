# Smart Helmet — Demo Runbook

End-to-end run for the finals demo at `http://localhost:8000/demo/index.html`.

You need **four terminals**, one per service. Open them in this order.

---

## Prerequisites (one-time)

```bash
cd /path/to/Smart-Helmet-for-Offline-Navigation
pip install -r requirements.txt              # repo root deps
pip install -r localization/CV/requirements.txt
```

Allow the browser to use your speakers (the UI uses `speechSynthesis` for turn-by-turn voice).

---

## Terminal 1 — Navigation Server (port 8000)

The brain. Serves the demo UI and the `/api/navigation/*` endpoints.

```bash
python3 -m uvicorn navigation.server:app --port 8000
```

Wait for: `Uvicorn running on http://0.0.0.0:8000`.

---

## Terminal 2 — Dead Reckoning Module (port 8002)

Provides the IMU/heading fallback when GPS dies.

```bash
python3 localization/DR/main.py
```

Wait for: `Starting Dead Reckoning service on port 8002`.

---

## Terminal 3 — Computer Vision Module (port 8001)

Landmark + scene classifier that recovers position when GPS is lost.

```bash
python3 localization/CV/main.py
```

Wait for: `Uvicorn running on http://0.0.0.0:8001`.

---

## Terminal 4 — Simulation Driver

Pumps simulated rider movement (~900 km/h scaled, 50 ms ticks) into the nav server.

> **Important:** before running this, open `http://localhost:8000/demo/index.html`,
> click **▶ START**, fill in origin/destination (default: *Shaniwar Wada → Pune Station*),
> and confirm. That locks the route on the server. Then run:

```bash
python3 simulation_driver.py
```

The terminal will start logging `[CV]`, `[DR]`, and `[NAV]` lines. Pos counts down,
distances drop, instruction switches inside the 60 m announce window.

---

## What you should see in the UI

| Trigger | UI feedback |
|---|---|
| START + simulation running | 🟢 `ONLINE · GPS` pill, route polyline blue/green |
| Click **KILL GPS** | 🔴 `OFFLINE · VISUAL` pill, route + arrow recolor red, mission banner slides in |
| CV landmark event arrives | 🔵 brief `ONLINE · VISUAL` pulse, "VISUAL FIX APPLIED" toast |
| Approach a turn (≤ 60 m) | Instruction bar glows blue, voice speaks "In N meters, turn …" |
| Click **🚨 CRASH** | SOS overlay, voice broadcast |

Mission counters (DR fixes, CV rescues, offline time) and the 60-second connectivity
timeline track the run live.

---

## Quick health check

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8001/health  2>/dev/null || echo "CV down"
curl -s http://localhost:8002/health  2>/dev/null || echo "DR down"
```

---

## Common gotchas

- **Demo shows "AWAITING ROUTE" forever** → you haven't clicked START yet, or the
  server can't reach OSRM/Nominatim for geocoding. Check Terminal 1 logs.
- **Route loaded but simulation_driver.py exits with "No route loaded"** → click
  START in the browser *first*, then run the driver.
- **Voice silent** → some browsers block `speechSynthesis` until the user has
  interacted with the page. Click anywhere on the demo first.
- **`KILL GPS` doesn't recolor the pill** → hard-refresh the browser (Cmd-Shift-R)
  to pick up the latest `demo_engine.js`.
- **Port already in use** → `lsof -i :8000` (or 8001/8002) and kill the stale process.

---

## Stopping

`Ctrl-C` in each terminal, in any order. The demo cleans up on browser close.
