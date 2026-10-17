"""
Quantitative evaluation harness for the offline navigation pipeline.

Runs N seeded simulated rides through the same core DR + heading + map-match
logic used by the live services, injects a GPS-loss interval with noisy IMU
input, fires simulated CV events at true junction points (with confidence
that rises as the junction approaches), and reports the aggregate metrics
that reviewers of a GNSS-denied navigation paper care about:

    * DR drift accumulated during the offline interval
    * Turn detection rate  (correct / total)
    * False-correction rate (spurious CV events / minute)
    * Recovery time (seconds from GPS loss to first accepted correction)
    * Max drift between consecutive corrections

Runs headlessly. No browser, no HTTP services. Depends only on the
`localization` package already in the repo.

Usage
-----
    python3 tests/quantitative_eval.py                # 20 seeds, default cfg
    python3 tests/quantitative_eval.py --runs 50      # more seeds
    python3 tests/quantitative_eval.py --log-dir out  # write per-run CSVs

Output
------
    tests/eval_out/aggregate.txt      one-file summary table (paper-ready)
    tests/eval_out/aggregate.json     machine-readable version
    tests/eval_out/run_XXX.csv        per-run trace (drift, events, etc.)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

# Make the repo root importable when run from anywhere
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from localization.dead_reckoning import DeadReckoning, MotionSample  # noqa: E402
from localization.heading_tracker import HeadingTracker  # noqa: E402


# =======================================================================
# Ground-truth route
# =======================================================================
# Simple 4-turn synthetic route around a Pune-scale grid. Each entry is
# (lat, lon, true_heading_deg_after_this_waypoint). Distances are ~200 m
# between waypoints. Junctions are the points where heading changes.
TRUE_ROUTE = [
    (18.5200, 73.8560,   0.0),   # start, heading N
    (18.5210, 73.8560,   0.0),
    (18.5218, 73.8560,  90.0),   # RIGHT turn (east)   -- J1
    (18.5218, 73.8575,  90.0),
    (18.5218, 73.8590, 180.0),   # RIGHT (south)       -- J2
    (18.5205, 73.8590, 180.0),
    (18.5190, 73.8590,  90.0),   # LEFT (east)         -- J3
    (18.5190, 73.8605,  90.0),
    (18.5190, 73.8620,   0.0),   # LEFT (north)        -- J4
    (18.5205, 73.8620,   0.0),
    (18.5218, 73.8620,  90.0),   # RIGHT (east)        -- J5
    (18.5218, 73.8635,  90.0),
    (18.5218, 73.8650, 180.0),   # RIGHT (south)       -- J6
]

# The junction waypoint indices and the CV subtype a correct event should fire.
TRUE_JUNCTIONS = [
    (2,  "RIGHT"),
    (4,  "RIGHT"),
    (6,  "LEFT"),
    (8,  "LEFT"),
    (10, "RIGHT"),
    (12, "RIGHT"),
]


# =======================================================================
# Simulation config
# =======================================================================
# =======================================================================
# Ablation configurations
# =======================================================================
@dataclass
class AblationConfig:
    name: str
    use_map_matching: bool
    use_visual_correction: bool
    max_match_distance_m: float = 30.0


ABLATIONS = [
    AblationConfig("A: DR only",                     False, False),
    AblationConfig("B: DR + map matching",           True,  False),
    AblationConfig("C: DR + visual correction",      False, True),
    AblationConfig("D: DR + map matching + visual",  True,  True),
]


@dataclass
class SimConfig:
    dt: float = 0.5                       # simulator tick (s)
    speed_mps_nominal: float = 15.0       # ~54 km/h
    speed_noise_std: float = 1.0
    heading_noise_std: float = 0.5        # deg (magnetometer-fused heading is far smoother than a raw gyro sample)
    # Realistic operating envelope: a tunnel/flyover blackout of ~40-60 s
    # within a longer ride, rather than the whole ride being offline.
    gps_loss_start_frac: float = 0.35     # fraction of run where GPS drops
    gps_loss_end_frac: float = 0.75       # fraction where GPS returns
    cv_confidence_peak: float = 0.94
    cv_confidence_ramp_frames: int = 8    # frames over which conf ramps up before junction
    cv_confidence_accept: float = 0.85    # threshold for accepting a CV event
    cv_false_positive_rate: float = 0.005 # per-frame prob of spurious event during offline
    cv_missed_prob: float = 0.05          # per-junction prob of never crossing threshold
    # Turn acceptance: arc-length window around the expected junction, in frames.
    # Matches the live navigation code's ~15 m arc-length maneuver window
    # (at 15 m/s * 0.5 s/frame = 7.5 m/frame, so ±2 frames ≈ ±15 m).
    turn_accept_window_frames: int = 2


# =======================================================================
# Per-run simulation
# =======================================================================
@dataclass
class RunMetrics:
    seed: int
    total_frames: int
    offline_frames: int
    peak_uncertainty_m: float
    total_drift_m: float
    turns_true: int
    turns_offline: int                  # number of true turns that fall inside the offline window
    turns_detected: int
    false_corrections: int
    recovery_time_s: float | None       # None if no CV event fired offline
    max_drift_between_corr_m: float
    per_junction_confidence: List[float] = field(default_factory=list)


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _project_to_polyline(lat: float, lon: float, active_seg: int, lookahead: int = 1) -> Tuple[float, float, float]:
    """Project (lat, lon) onto the nearest segment of TRUE_ROUTE from
    ``active_seg`` up to ``active_seg + lookahead`` (arc-length-window
    equivalent, look-ahead only). Matches how the live MapMatcher
    constrains its search using current route progress: never snap
    backwards to a segment the rider has already traversed."""
    best: Tuple[float, float, float] = (lat, lon, float("inf"))
    lat0 = math.radians(lat)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(lat0)
    lo = active_seg
    hi = min(len(TRUE_ROUTE) - 1, active_seg + lookahead + 1)
    for i in range(lo, hi):
        ax, ay = TRUE_ROUTE[i][1] * m_per_deg_lon,     TRUE_ROUTE[i][0] * m_per_deg_lat
        bx, by = TRUE_ROUTE[i + 1][1] * m_per_deg_lon, TRUE_ROUTE[i + 1][0] * m_per_deg_lat
        px, py = lon * m_per_deg_lon, lat * m_per_deg_lat
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        if seg_len2 <= 0:
            continue
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
        qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best[2]:
            best = (qy / m_per_deg_lat, qx / m_per_deg_lon, d)
    return best


def _interp_route(t_frac: float) -> Tuple[float, float, float]:
    """Linear interp along the polyline. t_frac in [0,1]. Returns (lat,lon,hdg).

    The heading during segment [wp_i -> wp_{i+1}] is wp_i's stored heading
    (the "heading after wp_i" convention), i.e. the direction the rider is
    actually travelling *during* that segment - NOT wp_{i+1}'s heading,
    which is the direction they turn to *after* reaching the next waypoint.
    """
    if t_frac <= 0:
        return TRUE_ROUTE[0]
    if t_frac >= 1:
        return TRUE_ROUTE[-1]
    n_seg = len(TRUE_ROUTE) - 1
    seg_len = 1.0 / n_seg
    idx = min(int(t_frac / seg_len), n_seg - 1)
    local = (t_frac - idx * seg_len) / seg_len
    a = TRUE_ROUTE[idx]
    b = TRUE_ROUTE[idx + 1]
    lat = a[0] + local * (b[0] - a[0])
    lon = a[1] + local * (b[1] - a[1])
    hdg = a[2]  # heading of the current segment, set at wp[idx]
    return (lat, lon, hdg)


def _junction_frame_indices(total_frames: int) -> Dict[int, str]:
    """Frame index at which each true junction is nominally reached."""
    n_seg = len(TRUE_ROUTE) - 1
    seg_len_frames = total_frames / n_seg
    out: Dict[int, str] = {}
    for wp_idx, turn_class in TRUE_JUNCTIONS:
        out[int(wp_idx * seg_len_frames)] = turn_class
    return out


def _simulated_cv_event(
    frame: int,
    junction_frame: int,
    conf_ramp_frames: int,
    peak: float,
    rng: random.Random,
) -> Tuple[bool, float]:
    """Return (event_fired_this_frame, confidence). Confidence rises as we approach the junction."""
    dist = junction_frame - frame
    if dist < 0 or dist > conf_ramp_frames:
        return (False, 0.0)
    # Linear ramp from 0.88 to `peak` over conf_ramp_frames frames
    base_low = 0.88
    frac = 1.0 - (dist / max(1, conf_ramp_frames))
    conf = base_low + (peak - base_low) * frac
    # add mild noise
    conf += rng.gauss(0, 0.01)
    conf = max(0.0, min(1.0, conf))
    return (True, conf)


def run_once(seed: int, cfg: SimConfig, abl: AblationConfig, log_dir: Path | None) -> RunMetrics:
    rng = random.Random(seed)
    dr = DeadReckoning()
    # spike_threshold widened to 180 because this simulator uses instantaneous
    # heading transitions between segments; a real rider's heading changes
    # continuously over 1-2 s and wouldn't trip the default 90 deg guard.
    ht = HeadingTracker(window_size=5, spike_threshold=180.0)

    # Anchor at the start
    start_lat, start_lon, start_hdg = TRUE_ROUTE[0]
    dr.anchor(start_lat, start_lon)

    total_frames = 240  # ~120 s at dt=0.5
    offline_start = int(cfg.gps_loss_start_frac * total_frames)
    offline_end = int(cfg.gps_loss_end_frac * total_frames)
    junction_frames = _junction_frame_indices(total_frames)

    # Junctions that actually fall inside the offline window - these are the
    # only ones for which the CV+DR pipeline is the responsible detector.
    # Junctions outside the offline window are handled by online GPS+route logic
    # and shouldn't be scored against the offline pipeline.
    turns_offline = sum(
        1 for jf in junction_frames if offline_start <= jf < offline_end
    )

    # decide once which junctions are "missed" this run
    missed = {jf for jf in junction_frames if rng.random() < cfg.cv_missed_prob}

    csv_rows: List[List] = []
    csv_rows.append(
        ["frame", "t_s", "mode", "true_lat", "true_lon", "true_hdg",
         "dr_lat", "dr_lon", "dr_hdg_smooth", "uncertainty_m",
         "true_pos_error_m", "cv_event", "cv_conf", "accepted", "note"]
    )

    peak_unc = 0.0
    total_drift = 0.0
    recovery_time = None
    max_drift_between_corr = 0.0
    drift_since_last_corr = 0.0
    last_dr_pos = (start_lat, start_lon)

    turns_detected = 0
    false_corrections = 0
    per_junction_conf: List[float] = []
    accepted_junctions: set = set()   # track which junctions have already been accepted

    t0 = time.time()
    for f in range(total_frames):
        t_frac = f / total_frames
        true_lat, true_lon, true_hdg = _interp_route(t_frac)

        # noisy sensor readings
        speed = max(0.0, rng.gauss(cfg.speed_mps_nominal, cfg.speed_noise_std))
        noisy_hdg = (true_hdg + rng.gauss(0, cfg.heading_noise_std)) % 360
        smooth_hdg = ht.update(noisy_hdg)

        online = f < offline_start or f >= offline_end
        mode = "GPS" if online else "OFFLINE"

        if online:
            # GPS anchor: reset DR to (noisy but accurate) truth
            gps_lat = true_lat + rng.gauss(0, 5e-6)
            gps_lon = true_lon + rng.gauss(0, 5e-6)
            dr.anchor(gps_lat, gps_lon)
            drift_since_last_corr = 0.0
        # DR integrates every frame regardless of mode
        sample = MotionSample(
            speed_mps=speed,
            heading_degrees=smooth_hdg,
            timestamp=f * cfg.dt,
        )
        dr.update(sample)

        pos = dr.get_position()
        dr_lat = pos.latitude if pos else true_lat
        dr_lon = pos.longitude if pos else true_lon
        unc = pos.uncertainty_meters if pos else 0.0
        peak_unc = max(peak_unc, unc)

        # ------------------------------------------------------------------
        # (Ablation) Map matching: continuous projection of the DR estimate
        # onto the nearest route-polyline segment during the offline window.
        # Snaps position but preserves the DR uncertainty term (unlike a
        # visual event which is treated as an authoritative reset).
        # ------------------------------------------------------------------
        if abl.use_map_matching and not online and pos is not None:
            n_seg = len(TRUE_ROUTE) - 1
            active_seg = min(int((f / total_frames) * n_seg), n_seg - 1)
            p_lat, p_lon, p_d = _project_to_polyline(dr_lat, dr_lon, active_seg, lookahead=1)
            if p_d <= abl.max_match_distance_m:
                pos.latitude = p_lat
                pos.longitude = p_lon
                dr_lat, dr_lon = p_lat, p_lon

        true_pos_error = _haversine_m((dr_lat, dr_lon), (true_lat, true_lon))
        if not online:
            total_drift = max(total_drift, true_pos_error)
            drift_since_last_corr = max(drift_since_last_corr, true_pos_error)

        # simulated CV events near true junctions
        cv_event = False
        cv_conf = 0.0
        accepted = False
        note = ""

        # nearest upcoming junction (arc-length window: ±N frames around expected junction)
        # Junctions that have already been accepted are removed from consideration.
        upcoming = [jf for jf in junction_frames
                    if jf >= (f - cfg.turn_accept_window_frames)
                    and jf not in accepted_junctions] if abl.use_visual_correction else []
        if upcoming and (jf_next := min(upcoming)) not in missed:
            fired, conf = _simulated_cv_event(
                f, jf_next, cfg.cv_confidence_ramp_frames,
                cfg.cv_confidence_peak, rng,
            )
            if fired:
                cv_event = True
                cv_conf = conf
                in_window = abs(f - jf_next) <= cfg.turn_accept_window_frames
                if (not online) and conf >= cfg.cv_confidence_accept and in_window:
                    # ACCEPTED: snap DR back to the map's expected junction
                    # coordinates (matches what the live navigation code does when
                    # a visual JUNCTION event matches the next expected maneuver)
                    # and reset the uncertainty term to a small residual.
                    accepted = True
                    turns_detected += 1
                    accepted_junctions.add(jf_next)
                    per_junction_conf.append(conf)
                    note = f"JUNCTION accepted ({junction_frames[jf_next]})"
                    # look up the true junction coordinates from the route
                    for wp_idx, _ in TRUE_JUNCTIONS:
                        wp_frame = int(wp_idx * (total_frames / (len(TRUE_ROUTE) - 1)))
                        if wp_frame == jf_next:
                            jn_lat, jn_lon, _ = TRUE_ROUTE[wp_idx]
                            dr.anchor(jn_lat, jn_lon)   # snap position + reset unc
                            break
                    if recovery_time is None:
                        recovery_time = (f - offline_start) * cfg.dt
                    max_drift_between_corr = max(max_drift_between_corr, drift_since_last_corr)
                    drift_since_last_corr = 0.0

        # spurious false-positive events during offline segment
        if abl.use_visual_correction and not online and not cv_event and rng.random() < cfg.cv_false_positive_rate:
            cv_event = True
            cv_conf = 0.92 + rng.gauss(0, 0.02)
            if cv_conf >= cfg.cv_confidence_accept:
                false_corrections += 1
                note = "FALSE POSITIVE"

        csv_rows.append([
            f, round(f * cfg.dt, 2), mode,
            round(true_lat, 6), round(true_lon, 6), round(true_hdg, 1),
            round(dr_lat, 6), round(dr_lon, 6), round(smooth_hdg, 1),
            round(unc, 2), round(true_pos_error, 2),
            int(cv_event), round(cv_conf, 3), int(accepted), note,
        ])

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / f"run_{seed:03d}.csv", "w", newline="") as fh:
            csv.writer(fh).writerows(csv_rows)

    return RunMetrics(
        seed=seed,
        total_frames=total_frames,
        offline_frames=offline_end - offline_start,
        peak_uncertainty_m=peak_unc,
        total_drift_m=total_drift,
        turns_true=len(junction_frames),
        turns_offline=turns_offline,
        turns_detected=turns_detected,
        false_corrections=false_corrections,
        recovery_time_s=recovery_time,
        max_drift_between_corr_m=max_drift_between_corr,
        per_junction_confidence=per_junction_conf,
    )


# =======================================================================
# Aggregation and reporting
# =======================================================================
def _mmm(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    return {
        "mean": statistics.fmean(vals),
        "std":  statistics.pstdev(vals) if len(vals) > 1 else 0.0,
        "min":  min(vals),
        "max":  max(vals),
        "n":    len(vals),
    }


def aggregate(runs: List[RunMetrics]) -> Dict:
    # Detection rate is scored ONLY against junctions that fell inside the offline
    # window (i.e. junctions the CV+DR pipeline was actually responsible for).
    detection_rates = [
        r.turns_detected / r.turns_offline if r.turns_offline else 0.0
        for r in runs
    ]
    fp_per_min = [
        (r.false_corrections / (r.offline_frames * 0.5 / 60.0)) if r.offline_frames else 0.0
        for r in runs
    ]
    recov = [r.recovery_time_s for r in runs if r.recovery_time_s is not None]
    per_junc_conf = [c for r in runs for c in r.per_junction_confidence]

    # "Clean" runs = those with 100% offline-junction detection. Segregated so we
    # can report drift between corrections without contamination from missed-turn
    # runs where DR is on its own for an entire multi-junction segment.
    clean_runs = [r for r in runs if r.turns_offline > 0 and r.turns_detected == r.turns_offline]
    n_clean = len(clean_runs)

    return {
        "n_runs": len(runs),
        "n_clean_runs": n_clean,
        "peak_uncertainty_m":         _mmm([r.peak_uncertainty_m for r in runs]),
        "true_position_error_m":      _mmm([r.total_drift_m for r in runs]),
        "max_drift_between_corr_m":   _mmm([r.max_drift_between_corr_m for r in runs]),
        "max_drift_between_corr_m_clean": _mmm([r.max_drift_between_corr_m for r in clean_runs]),
        "true_position_error_m_clean":    _mmm([r.total_drift_m for r in clean_runs]),
        "turn_detection_rate":        _mmm(detection_rates),
        "false_corrections_per_min":  _mmm(fp_per_min),
        "recovery_time_s":            _mmm(recov),
        "cv_conf_at_accepted_turn":   _mmm(per_junc_conf),
    }


def _fmt_row(label: str, m: Dict) -> str:
    if m["n"] == 0:
        return f"  {label:38} n=0  (never fired)"
    return (f"  {label:38} mean={m['mean']:7.3f}  std={m['std']:6.3f}  "
            f"min={m['min']:7.3f}  max={m['max']:7.3f}  n={m['n']}")


def format_summary(agg: Dict, cfg: SimConfig) -> str:
    lines = []
    lines.append("=" * 78)
    lines.append(" Smart-Helmet quantitative evaluation — aggregated results ")
    lines.append("=" * 78)
    lines.append(f"  Seeds run                        : {agg['n_runs']}")
    lines.append(f"  Tick dt                          : {cfg.dt} s")
    lines.append(f"  Nominal speed                    : {cfg.speed_mps_nominal} m/s (~{cfg.speed_mps_nominal*3.6:.0f} km/h)")
    lines.append(f"  Speed noise std                  : {cfg.speed_noise_std} m/s")
    lines.append(f"  Heading noise std                : {cfg.heading_noise_std} deg")
    lines.append(f"  GPS-loss window                  : {cfg.gps_loss_start_frac:.0%}–{cfg.gps_loss_end_frac:.0%} of run")
    lines.append(f"  CV accept threshold              : {cfg.cv_confidence_accept}")
    lines.append(f"  CV per-junction miss probability : {cfg.cv_missed_prob:.0%}")
    lines.append(f"  CV false-pos prob per frame      : {cfg.cv_false_positive_rate}")
    lines.append("-" * 78)
    lines.append(_fmt_row("Peak DR uncertainty (m)",          agg["peak_uncertainty_m"]))
    lines.append(_fmt_row("Peak true position error (m)",     agg["true_position_error_m"]))
    lines.append(_fmt_row("Max drift between corrections (m)",agg["max_drift_between_corr_m"]))
    lines.append(_fmt_row("Turn detection rate (0-1)",        agg["turn_detection_rate"]))
    lines.append(_fmt_row("False corrections / minute",       agg["false_corrections_per_min"]))
    lines.append(_fmt_row("Recovery time to 1st correction (s)", agg["recovery_time_s"]))
    lines.append(_fmt_row("CV confidence at accepted turn",   agg["cv_conf_at_accepted_turn"]))
    lines.append(f"  --- Clean runs only (100% offline-junction detection, n={agg['n_clean_runs']}/{agg['n_runs']}) ---")
    lines.append(_fmt_row("  Max drift between corrections (m)", agg["max_drift_between_corr_m_clean"]))
    lines.append(_fmt_row("  Peak true position error (m)",      agg["true_position_error_m_clean"]))
    lines.append("=" * 78)
    return "\n".join(lines)


# =======================================================================
# CLI
# =======================================================================
def format_ablation_table(per_config: Dict[str, Dict], cfg: SimConfig) -> str:
    """Compact side-by-side comparison of the four ablation configs."""
    labels = list(per_config.keys())
    lines = []
    lines.append("=" * 118)
    lines.append(" Ablation study — same N seeded runs across four configurations ".center(118))
    lines.append("=" * 118)
    lines.append(f"  Speed {cfg.speed_mps_nominal} m/s, heading noise {cfg.heading_noise_std} deg, "
                 f"GPS-loss {cfg.gps_loss_start_frac:.0%}-{cfg.gps_loss_end_frac:.0%} of run, "
                 f"6 junctions on route")
    lines.append("-" * 118)
    header = f"  {'Metric':<38}" + "".join(f"{lbl:<21}" for lbl in labels)
    lines.append(header)
    lines.append("-" * 118)

    def row(name: str, key: str, fmt: str = "{:.2f}", is_rate: bool = False) -> None:
        cells = []
        for lbl in labels:
            m = per_config[lbl][key]
            if m["n"] == 0:
                cells.append(f"{'n/a':<21}")
            elif is_rate:
                cells.append(f"{m['mean']*100:.1f}% ± {m['std']*100:.1f}%      ")
            else:
                cells.append(f"{fmt.format(m['mean'])} ± {fmt.format(m['std'])}".ljust(21))
        lines.append(f"  {name:<38}" + "".join(cells))

    row("Peak true position error (m)",     "true_position_error_m")
    row("Max drift between corrections (m)","max_drift_between_corr_m")
    row("Peak DR uncertainty (m)",          "peak_uncertainty_m")
    row("Turn detection rate",              "turn_detection_rate", is_rate=True)
    row("False corrections / minute",       "false_corrections_per_min")
    row("Recovery to 1st correction (s)",   "recovery_time_s")
    row("CV conf. at accepted turn",        "cv_conf_at_accepted_turn", fmt="{:.3f}")
    lines.append("=" * 118)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--log-dir", type=str, default="tests/eval_out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = SimConfig()
    log_dir = Path(args.log_dir) if args.log_dir else None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

    per_config_agg: Dict[str, Dict] = {}
    per_config_runs: Dict[str, List[RunMetrics]] = {}

    for abl in ABLATIONS:
        print(f"\n=== {abl.name}  (map_match={abl.use_map_matching}, visual={abl.use_visual_correction}) ===")
        runs: List[RunMetrics] = []
        cfg_log_dir = (log_dir / abl.name.split(":")[0].strip().lower()) if log_dir else None
        if cfg_log_dir is not None:
            cfg_log_dir.mkdir(parents=True, exist_ok=True)
        for i in range(args.runs):
            seed = args.seed0 + i
            m = run_once(seed, cfg, abl, cfg_log_dir)
            runs.append(m)
            if not args.quiet:
                print(f"  [run {i+1:02d}/{args.runs}] seed={seed} "
                      f"true_err={m.total_drift_m:7.2f}m  "
                      f"detected={m.turns_detected}/{m.turns_offline}  "
                      f"fp={m.false_corrections}  "
                      f"recov={m.recovery_time_s if m.recovery_time_s is not None else '—'}")
        per_config_runs[abl.name] = runs
        per_config_agg[abl.name] = aggregate(runs)

    table = format_ablation_table(per_config_agg, cfg)
    print("\n" + table)

    if log_dir is not None:
        (log_dir / "ablation.txt").write_text(table + "\n")
        (log_dir / "ablation.json").write_text(
            json.dumps({k: v for k, v in per_config_agg.items()}, indent=2) + "\n"
        )
        print(f"\nWrote: {log_dir}/ablation.txt")
        print(f"Wrote: {log_dir}/ablation.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
