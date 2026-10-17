"""Run the paired real-ride ablation on several rides and pool the results.

Each argument is a Sensor Logger export (a folder or a .zip). For every ride
we report the route summary, the paired D-vs-A and other contrasts, and the
threshold sweep; then all windows are pooled into one paired analysis.

    python3 tests/multi_ride.py ride1/ ride2.zip ride3.zip
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests"))

import real_ride_eval as rre  # noqa: E402
import threshold_sweep as sweep  # noqa: E402
from real_ride_paired import ci95, wilcoxon_p  # noqa: E402

CONTRASTS = [("B", "A"), ("C", "A"), ("D", "A"), ("D", "B"), ("D", "C")]


def open_ride(arg: str) -> Path:
    p = Path(arg).expanduser()
    if p.suffix == ".zip":
        out = Path(tempfile.mkdtemp(prefix="ride_"))
        with zipfile.ZipFile(p) as z:
            z.extractall(out)
        hits = list(out.rglob("Location.csv"))
        if not hits:
            raise SystemExit(f"{arg}: no Location.csv inside")
        return hits[0].parent
    return p


def summary(ride, wp, junctions):
    dist = sum(rre.haversine(a, b) for a, b in zip(ride.gps_pos, ride.gps_pos[1:]))
    dur = ride.gps_t[-1] - ride.gps_t[0]
    return {"duration_min": round(dur / 60, 1), "distance_km": round(dist / 1000, 2),
            "mean_speed_kmh": round(3.6 * dist / dur, 1) if dur else 0.0,
            "median_gnss_acc_m": round(statistics.median(ride.gps_acc), 1),
            "waypoints": len(wp), "junctions": len(junctions)}


def windows(ride, wp, junctions, blackout=60.0, stride=10.0, seed=1000):
    starts, t = [], ride.gps_t[0] + 5.0
    while t + blackout <= ride.gps_t[-1] - 5.0:
        starts.append(t)
        t += stride
    per = {}
    for cfg in rre.CONFIGS:
        rng = random.Random(seed)
        per[cfg.name[0]] = {}
        for s in starts:
            r = rre.run_window(ride, wp, junctions, cfg, s, s + blackout, rng, 0.05, 25.0, 40.0)
            if r:
                per[cfg.name[0]][s] = r["peak_error_m"]
    common = sorted(set.intersection(*(set(v) for v in per.values())))
    return {k: [per[k][s] for s in common] for k in per}


def contrasts(series):
    out = {}
    if len(series["A"]) < 2:
        return out
    for lhs, rhs in CONTRASTS:
        d = [x - y for x, y in zip(series[lhs], series[rhs])]
        m, lo, hi = ci95(d)
        base = statistics.fmean(series[rhs])
        out[f"{lhs}-{rhs}"] = {"pct": round(100 * m / base, 1), "mean_diff_m": round(m, 1),
                               "ci95": [round(lo, 1), round(hi, 1)],
                               "win_rate": round(sum(x < 0 for x in d) / len(d), 2),
                               "p": round(wilcoxon_p(d), 4)}
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    report, pooled = {"rides": []}, {k: [] for k in "ABCD"}
    for arg in sys.argv[1:]:
        d = open_ride(arg)
        ride = rre.load_ride(d)
        rre.YAW_SIGN = rre.resolve_yaw_sign(ride)
        wp, junctions = rre.build_route(ride)
        s = windows(ride, wp, junctions)
        for k in s:
            pooled[k] += s[k]
        sw = {name: [sweep.evaluate(ride, dict(sweep.DEFAULTS, **{name: v}))
                     for v in vals] for name, vals in sweep.GRID.items()}
        n_sig = sum(r["p"] is not None and r["p"] < 0.05 for rows in sw.values() for r in rows)
        n_all = sum(len(rows) for rows in sw.values())
        entry = {"ride": Path(arg).name, **summary(ride, wp, junctions), "windows": len(s["A"]),
                 "peak_mean_m": {k: round(statistics.fmean(v), 1) for k, v in s.items() if v},
                 "contrasts": contrasts(s), "sweep_significant": f"{n_sig}/{n_all}",
                 "sweep": sw}
        report["rides"].append(entry)
        c = entry["contrasts"].get("D-A")
        res = f"D vs A {-c['pct']:+.1f}% p={c['p']:.4f}" if c else "too few windows to test"
        print(f"{arg}: {entry['distance_km']} km, {entry['windows']} windows, {res}, "
              f"sweep {entry['sweep_significant']}", flush=True)

    report["pooled"] = {"windows": len(pooled["A"]),
                        "peak_mean_m": {k: round(statistics.fmean(v), 1) for k, v in pooled.items()},
                        "contrasts": contrasts(pooled)}
    c = report["pooled"]["contrasts"]
    print(f"\nPOOLED ({report['pooled']['windows']} windows over {len(report['rides'])} rides)")
    for k, v in c.items():
        print(f"  {k}: {v['pct']:+.1f}%  CI {v['ci95']}  win {v['win_rate']:.0%}  p={v['p']:.4f}")
    dst = REPO_ROOT / "tests/eval_out/multi_ride.json"
    dst.write_text(json.dumps(report, indent=2))
    print(f"JSON: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
