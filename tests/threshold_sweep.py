"""One-at-a-time sensitivity sweep of the real-ride ablation thresholds.

Each parameter is varied around its default while the others stay fixed; for
every setting we report the paired D-vs-A peak-error reduction and its
Wilcoxon p-value over the common blackout windows.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests"))

import real_ride_eval as rre  # noqa: E402
from real_ride_paired import wilcoxon_p  # noqa: E402

DEFAULTS = dict(accept_m=25.0, match_max_m=40.0, miss_rate=0.05,
                blackout=60.0, turn_deg=35.0)
GRID = {
    "accept_m": [15.0, 20.0, 25.0, 30.0, 40.0],
    "match_max_m": [25.0, 30.0, 40.0, 50.0, 60.0],
    "miss_rate": [0.0, 0.05, 0.10, 0.20, 0.30],
    "blackout": [30.0, 45.0, 60.0, 90.0],
    "turn_deg": [25.0, 30.0, 35.0, 45.0, 60.0],
}


def build_route(ride, turn_deg):
    orig = rre.ang_diff
    wp, junctions = rre.build_route(ride)
    junctions = [i for i in range(1, len(wp) - 1)
                 if abs(orig(rre.bearing(wp[i], wp[i + 1]),
                             rre.bearing(wp[i - 1], wp[i]))) > turn_deg]
    return wp, junctions


def evaluate(ride, p, stride=10.0, seed=1000):
    wp, junctions = build_route(ride, p["turn_deg"])
    starts, t = [], ride.gps_t[0] + 5.0
    while t + p["blackout"] <= ride.gps_t[-1] - 5.0:
        starts.append(t)
        t += stride
    per = {}
    for cfg in rre.CONFIGS:
        rng = random.Random(seed)
        per[cfg.name] = {}
        for s in starts:
            r = rre.run_window(ride, wp, junctions, cfg, s, s + p["blackout"], rng,
                               p["miss_rate"], p["accept_m"], p["match_max_m"])
            if r:
                per[cfg.name][s] = r["peak_error_m"]
    names = [c.name for c in rre.CONFIGS]
    common = sorted(set.intersection(*(set(per[n]) for n in names)))
    a = [per[names[0]][s] for s in common]
    d = [per[names[3]][s] for s in common]
    diffs = [x - y for x, y in zip(d, a)]
    if not diffs:
        return {"n": 0, "junctions": len(junctions), "reduction_pct": None, "p": None}
    pct = 100.0 * statistics.fmean(diffs) / statistics.fmean(a)
    return {"n": len(common), "junctions": len(junctions),
            "reduction_pct": round(-pct, 1), "p": round(wilcoxon_p(diffs), 4)}


def main() -> int:
    ride = rre.load_ride(Path(sys.argv[1]))
    rre.YAW_SIGN = rre.resolve_yaw_sign(ride)
    out = {}
    for name, values in GRID.items():
        out[name] = []
        for v in values:
            p = dict(DEFAULTS, **{name: v})
            r = evaluate(ride, p)
            r["value"] = v
            out[name].append(r)
            print(f"{name:12s} {v:6.2f}  n={r['n']:3d} junc={r['junctions']:2d}  "
                  f"D vs A {r['reduction_pct']:+5.1f}%  p={r['p']:.4f}", flush=True)
    dst = REPO_ROOT / "tests/eval_out/threshold_sweep.json"
    dst.write_text(json.dumps(out, indent=2))
    print(f"JSON: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
