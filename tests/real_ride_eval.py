"""Real-ride ablation: DR / map-matching / junction-correction on recorded sensor data.

Replaces the synthetic route and synthetic motion of the simulator harness with
a real two-wheeler ride logged at 100 Hz (accelerometer, gyroscope, fused
device orientation) plus 1 Hz GPS.

Method
------
* Ground truth      : the recorded 1 Hz GPS trace.
* Route polyline    : the GPS trace decimated to sparse waypoints and joined by
                      straight segments -- a coarse stand-in for what a routing
                      engine returns. Map matching snaps to THIS, and error is
                      measured against the full trace, so map matching cannot
                      trivially recover ground truth.
* Heading           : relative yaw from the device's fused orientation, anchored
                      to the GPS bearing at blackout entry, passed through the
                      repo's own HeadingTracker.
* Speed             : GPS speed while online; held at its last online value
                      through the blackout (constant-velocity DR). No GPS is
                      read by the estimator during a blackout.
* Junction events   : fire when DR passes within an acceptance radius of a route
                      junction waypoint, subject to a per-junction miss rate;
                      an accepted event snaps the estimate to that waypoint.

Configurations (identical blackout windows across all four):
    A  DR only
    B  DR + route map matching
    C  DR + junction correction
    D  DR + map matching + junction correction

Usage
-----
    python3 tests/real_ride_eval.py --ride /tmp/ride --out tests/eval_out/real_ride.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from localization.dead_reckoning import DeadReckoning, MotionSample  # noqa: E402
from localization.heading_tracker import HeadingTracker  # noqa: E402

R_EARTH = 6371000.0


# ----------------------------------------------------------------- geo helpers
def haversine(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def bearing(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dlo = math.radians(b[1] - a[1])
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def ang_diff(a: float, b: float) -> float:
    """Signed smallest difference a-b in (-180, 180]."""
    return (a - b + 540.0) % 360.0 - 180.0


# ----------------------------------------------------------------- data loading
@dataclass
class Ride:
    gps_t: List[float]
    gps_pos: List[Tuple[float, float]]
    gps_speed: List[float]
    gps_acc: List[float]
    ori_t: List[float]
    ori_yaw: List[float]      # degrees, unwrapped, device frame
    mot_t: List[float]        # 1 Hz motion-energy grid
    moving: List[bool]        # IMU-only stationary detector (ZUPT)


def load_ride(d: Path) -> Ride:
    def rows(name):
        with open(d / name) as fh:
            return list(csv.DictReader(fh))

    loc = rows("Location.csv")
    gps_t, gps_pos, gps_sp, gps_ac = [], [], [], []
    for r in loc:
        t = float(r["seconds_elapsed"])
        if t < 0:
            continue                      # pre-roll fixes with negative stamps
        gps_t.append(t)
        gps_pos.append((float(r["latitude"]), float(r["longitude"])))
        s = float(r["speed"])
        gps_sp.append(s if s >= 0 else 0.0)
        gps_ac.append(float(r["horizontalAccuracy"]))

    ori = rows("Orientation.csv")
    ot = [float(r["seconds_elapsed"]) for r in ori]
    raw = [math.degrees(float(r["yaw"])) for r in ori]
    uw = [raw[0]]
    for v in raw[1:]:
        uw.append(uw[-1] + ang_diff(v, uw[-1] % 360.0))

    # --- IMU-only motion detector (zero-velocity update).
    # A stopped two-wheeler still vibrates, but linear-acceleration and
    # angular-rate energy both collapse relative to riding. No GPS is used.
    acc = rows("Accelerometer.csv")
    gyr = rows("Gyroscope.csv")
    mot_t, moving = [], []
    bucket_a: Dict[int, List[float]] = {}
    bucket_g: Dict[int, List[float]] = {}
    for r in acc:
        s = int(float(r["seconds_elapsed"]))
        bucket_a.setdefault(s, []).append(
            math.sqrt(float(r["x"])**2 + float(r["y"])**2 + float(r["z"])**2))
    for r in gyr:
        s = int(float(r["seconds_elapsed"]))
        bucket_g.setdefault(s, []).append(
            math.sqrt(float(r["x"])**2 + float(r["y"])**2 + float(r["z"])**2))
    for s in sorted(bucket_a):
        a_rms = statistics.fmean(bucket_a[s])
        g_rms = statistics.fmean(bucket_g.get(s, [0.0]))
        mot_t.append(float(s))
        moving.append(not (a_rms < 0.35 and g_rms < 0.12))

    return Ride(gps_t, gps_pos, gps_sp, gps_ac, ot, uw, mot_t, moving)


def is_moving(ride: Ride, t: float) -> bool:
    i = bisect_left(ride.mot_t, t)
    i = min(max(i, 0), len(ride.moving) - 1)
    return ride.moving[i]


def interp_yaw(ride: Ride, t: float) -> float:
    i = bisect_left(ride.ori_t, t)
    if i <= 0:
        return ride.ori_yaw[0]
    if i >= len(ride.ori_t):
        return ride.ori_yaw[-1]
    t0, t1 = ride.ori_t[i - 1], ride.ori_t[i]
    y0, y1 = ride.ori_yaw[i - 1], ride.ori_yaw[i]
    f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
    return y0 + f * (y1 - y0)


# ------------------------------------------------------- route + junction build
def build_route(ride: Ride, spacing_m: float = 45.0
                ) -> Tuple[List[Tuple[float, float]], List[int]]:
    """Decimate the GPS trace into sparse waypoints (a coarse routing-engine
    style polyline) and flag waypoints where the route turns."""
    wp = [ride.gps_pos[0]]
    for p in ride.gps_pos[1:]:
        if haversine(wp[-1], p) >= spacing_m:
            wp.append(p)
    if haversine(wp[-1], ride.gps_pos[-1]) > 1.0:
        wp.append(ride.gps_pos[-1])

    junctions = []
    for i in range(1, len(wp) - 1):
        b_in = bearing(wp[i - 1], wp[i])
        b_out = bearing(wp[i], wp[i + 1])
        if abs(ang_diff(b_out, b_in)) > 35.0:
            junctions.append(i)
    return wp, junctions


def project_to_route(pos: Tuple[float, float], wp: List[Tuple[float, float]],
                     seg_lo: int, lookahead: int = 2
                     ) -> Tuple[Tuple[float, float], float, int]:
    """Nearest point on segments [seg_lo, seg_lo+lookahead] of the polyline.
    Look-ahead only: never snap backwards past current progress."""
    lat0 = math.radians(pos[0])
    mlat, mlon = 111320.0, 111320.0 * math.cos(lat0)
    px, py = pos[1] * mlon, pos[0] * mlat
    best = (pos, float("inf"), seg_lo)
    hi = min(len(wp) - 1, seg_lo + lookahead + 1)
    for i in range(seg_lo, hi):
        ax, ay = wp[i][1] * mlon, wp[i][0] * mlat
        bx, by = wp[i + 1][1] * mlon, wp[i + 1][0] * mlat
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 <= 0:
            continue
        u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        qx, qy = ax + u * dx, ay + u * dy
        dist = math.hypot(px - qx, py - qy)
        if dist < best[1]:
            best = ((qy / mlat, qx / mlon), dist, i)
    return best


# ------------------------------------------------------------------- evaluation
@dataclass
class Config:
    name: str
    map_match: bool
    junction: bool


CONFIGS = [
    Config("A: DR only", False, False),
    Config("B: DR + map matching", True, False),
    Config("C: DR + junction corr.", False, True),
    Config("D: full", True, True),
]


def run_window(ride: Ride, wp, junctions, cfg: Config, t0: float, t1: float,
               rng: random.Random, miss_rate: float, accept_m: float,
               match_max_m: float) -> Optional[Dict]:
    """Simulate a GPS blackout on [t0, t1]. Returns error metrics or None."""
    idx = [i for i, t in enumerate(ride.gps_t) if t0 <= t <= t1]
    if len(idx) < 20:
        return None
    i0 = idx[0]

    # --- anchor: last online fix, its bearing and its speed
    if i0 < 2:
        return None
    anchor = ride.gps_pos[i0]
    hdg0 = bearing(ride.gps_pos[i0 - 2], ride.gps_pos[i0])
    speed_hold = statistics.fmean(ride.gps_speed[max(0, i0 - 3):i0 + 1])
    if speed_hold < 0.5:
        return None                       # stationary at blackout entry

    yaw0 = interp_yaw(ride, ride.gps_t[i0])

    dr = DeadReckoning()
    dr.anchor(*anchor)
    ht = HeadingTracker(window_size=5, spike_threshold=180.0)
    ht.update(hdg0)

    seg_lo = 0
    _, _, seg_lo = project_to_route(anchor, wp, 0, lookahead=len(wp))
    fired = set()
    errors, since_corr, max_between = [], 0.0, 0.0
    trace_t, events_t = [], []

    for k in idx[1:]:
        t = ride.gps_t[k]
        dt = t - ride.gps_t[k - 1]
        if dt <= 0:
            continue
        # heading: relative fused-yaw change applied to the entry bearing
        hdg = (hdg0 + YAW_SIGN * (interp_yaw(ride, t) - yaw0)) % 360.0
        hdg = ht.update(hdg)
        # Constant-velocity DR: speed is held at its last online value for the
        # duration of the blackout. (An IMU-only zero-velocity detector was
        # evaluated and rejected: with a torso-mounted phone the stationary and
        # riding distributions overlap -- median gyro RMS is actually higher at
        # a standstill, 0.53 vs 0.47 rad/s, because rider body motion dominates
        # when the vehicle is not moving.)
        dr.update(MotionSample(speed_mps=speed_hold, heading_degrees=hdg,
                               timestamp=t))
        pos = dr.get_position()
        est = (pos.latitude, pos.longitude)

        if cfg.map_match:
            snapped, dist, seg = project_to_route(est, wp, seg_lo, lookahead=2)
            if dist <= match_max_m:
                pos.latitude, pos.longitude = snapped
                est = snapped
                seg_lo = max(seg_lo, seg)

        if cfg.junction:
            for j in junctions:
                if j in fired:
                    continue
                if haversine(est, wp[j]) <= accept_m:
                    if rng.random() >= miss_rate:      # CV detects the junction
                        dr.anchor(*wp[j])
                        est = wp[j]
                        since_corr = 0.0
                        events_t.append(t - ride.gps_t[i0])
                    fired.add(j)
                    break

        err = haversine(est, ride.gps_pos[k])
        errors.append(err)
        trace_t.append(t - ride.gps_t[i0])
        since_corr = max(since_corr, err)
        max_between = max(max_between, since_corr)

    if not errors:
        return None

    # --- maneuver-progression correctness -------------------------------
    # The route pointer is only useful if it still names the right NEXT
    # junction. Compare the next junction ahead of the estimate against the
    # next junction ahead of ground truth at blackout exit.
    def next_junction(p: Tuple[float, float]) -> Optional[int]:
        _, _, seg = project_to_route(p, wp, 0, lookahead=len(wp))
        ahead = [j for j in junctions if j > seg]
        return ahead[0] if ahead else None

    truth_end = ride.gps_pos[idx[-1]]
    j_est, j_true = next_junction(est), next_junction(truth_end)
    pointer_ok = (j_est == j_true)

    return {
        "peak_error_m": max(errors),
        "mean_error_m": statistics.fmean(errors),
        "final_error_m": errors[-1],
        "max_drift_between_corr_m": max_between,
        "corrections": len(fired),
        "pointer_correct": 1.0 if pointer_ok else 0.0,
        "duration_s": ride.gps_t[idx[-1]] - ride.gps_t[i0],
        "trace": list(zip(trace_t, errors)),
        "events_t": events_t,
    }


YAW_SIGN = 1.0  # resolved at runtime


def resolve_yaw_sign(ride: Ride) -> float:
    """Device yaw may increase clockwise or anticlockwise relative to compass
    bearing. Decide empirically by correlating yaw change with GPS bearing
    change over moving segments."""
    agree = 0
    total = 0
    for i in range(4, len(ride.gps_t) - 4):
        if ride.gps_speed[i] < 3.0:
            continue
        b0 = bearing(ride.gps_pos[i - 4], ride.gps_pos[i])
        b1 = bearing(ride.gps_pos[i], ride.gps_pos[i + 4])
        db = ang_diff(b1, b0)
        if abs(db) < 15.0:
            continue
        dy = interp_yaw(ride, ride.gps_t[i + 4]) - interp_yaw(ride, ride.gps_t[i - 4])
        if abs(dy) < 5.0:
            continue
        total += 1
        if (db > 0) == (dy > 0):
            agree += 1
    if total == 0:
        return 1.0
    frac = agree / total
    print(f"  yaw/bearing sign agreement: {frac*100:.0f}% over {total} turns "
          f"-> sign {'+1' if frac >= 0.5 else '-1'}")
    return 1.0 if frac >= 0.5 else -1.0


def mstd(v: List[float]) -> Dict:
    if not v:
        return {"n": 0}
    return {"n": len(v), "mean": round(statistics.fmean(v), 2),
            "std": round(statistics.pstdev(v), 2) if len(v) > 1 else 0.0,
            "min": round(min(v), 2), "max": round(max(v), 2)}


def main() -> int:
    global YAW_SIGN
    ap = argparse.ArgumentParser()
    ap.add_argument("--ride", required=True)
    ap.add_argument("--blackout", type=float, default=60.0,
                    help="blackout duration (s)")
    ap.add_argument("--stride", type=float, default=20.0,
                    help="spacing between blackout window starts (s)")
    ap.add_argument("--miss-rate", type=float, default=0.05)
    ap.add_argument("--accept-m", type=float, default=25.0)
    ap.add_argument("--match-max-m", type=float, default=40.0)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--out", default="tests/eval_out/real_ride.json")
    args = ap.parse_args()

    ride = load_ride(Path(args.ride))
    print(f"Loaded ride: {len(ride.gps_t)} GPS fixes over "
          f"{ride.gps_t[-1]-ride.gps_t[0]:.0f} s, "
          f"{len(ride.ori_t)} orientation samples")
    YAW_SIGN = resolve_yaw_sign(ride)

    wp, junctions = build_route(ride)
    print(f"  route: {len(wp)} waypoints, {len(junctions)} junction waypoints")

    starts = []
    t = ride.gps_t[0] + 5.0
    while t + args.blackout <= ride.gps_t[-1] - 5.0:
        starts.append(t)
        t += args.stride
    print(f"  evaluating {len(starts)} blackout windows of {args.blackout:.0f} s\n")

    results: Dict[str, List[Dict]] = {c.name: [] for c in CONFIGS}
    for cfg in CONFIGS:
        rng = random.Random(args.seed)
        for s in starts:
            r = run_window(ride, wp, junctions, cfg, s, s + args.blackout,
                           rng, args.miss_rate, args.accept_m, args.match_max_m)
            if r:
                results[cfg.name].append(r)

    agg = {}
    for cfg in CONFIGS:
        rs = results[cfg.name]
        agg[cfg.name] = {
            "windows": len(rs),
            "peak_error_m": mstd([r["peak_error_m"] for r in rs]),
            "mean_error_m": mstd([r["mean_error_m"] for r in rs]),
            "max_drift_between_corr_m": mstd([r["max_drift_between_corr_m"] for r in rs]),
            "corrections_per_window": mstd([float(r["corrections"]) for r in rs]),
            "pointer_correct_rate": mstd([r["pointer_correct"] for r in rs]),
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"ride": {"gps_fixes": len(ride.gps_t),
                  "duration_s": round(ride.gps_t[-1] - ride.gps_t[0], 1),
                  "waypoints": len(wp), "junctions": len(junctions)},
         "params": vars(args), "aggregate": agg}, indent=2))

    w = 26
    print("=" * 84)
    print(" REAL-RIDE ABLATION  (recorded two-wheeler IMU + GPS ground truth)".center(84))
    print("=" * 84)
    hdr = f"  {'Metric':<{w}}" + "".join(f"{c.name:<14}" for c in CONFIGS)
    print(hdr); print("-" * 84)
    for key, label in [("peak_error_m", "Peak error (m)"),
                       ("mean_error_m", "Mean error (m)"),
                       ("max_drift_between_corr_m", "Max drift betw. corr (m)"),
                       ("corrections_per_window", "Corrections / window"),
                       ("pointer_correct_rate", "Next-junction correct")]:
        line = f"  {label:<{w}}"
        for c in CONFIGS:
            m = agg[c.name][key]
            line += f"{m['mean']:.1f}±{m['std']:.1f}".ljust(14) if m["n"] else "n/a".ljust(14)
        print(line)
    print("-" * 84)
    print(f"  windows evaluated: {agg[CONFIGS[0].name]['windows']}")
    print("=" * 84)
    print(f"\nJSON: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
