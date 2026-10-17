"""Paired-difference analysis of the real-ride ablation.

Every configuration is evaluated on the SAME blackout windows, so the correct
comparison is a per-window paired difference rather than a difference of
independent means. This removes between-window variance (which is dominated by
how fast the rider happened to be going) and isolates the effect of the
localisation configuration itself.

Reports, for each contrast:
  * mean paired difference with 95% CI (t-based)
  * win rate (fraction of windows where the contrast improves the estimate)
  * Wilcoxon signed-rank p-value (exact for small n via normal approximation)
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import real_ride_eval as rre  # noqa: E402
import random  # noqa: E402


def wilcoxon_p(diffs: List[float]) -> float:
    """Two-sided Wilcoxon signed-rank via normal approximation."""
    nz = [d for d in diffs if d != 0.0]
    n = len(nz)
    if n < 6:
        return float("nan")
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nz[order[j + 1]]) == abs(nz[order[i]]):
            j += 1
        avg = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, nz) if d > 0)
    mu = n * (n + 1) / 4.0
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sd == 0:
        return float("nan")
    z = (w_plus - mu) / sd
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def ci95(v: List[float]) -> tuple:
    n = len(v)
    m = statistics.fmean(v)
    if n < 2:
        return m, 0.0, 0.0
    sd = statistics.stdev(v)
    sem = sd / math.sqrt(n)
    return m, m - 1.96 * sem, m + 1.96 * sem


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ride", required=True)
    ap.add_argument("--blackout", type=float, default=60.0)
    ap.add_argument("--stride", type=float, default=10.0)
    ap.add_argument("--miss-rate", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--out", default="tests/eval_out/real_ride_paired.json")
    args = ap.parse_args()

    ride = rre.load_ride(Path(args.ride))
    rre.YAW_SIGN = rre.resolve_yaw_sign(ride)
    wp, junctions = rre.build_route(ride)
    print(f"  route: {len(wp)} waypoints, {len(junctions)} junctions")

    starts = []
    t = ride.gps_t[0] + 5.0
    while t + args.blackout <= ride.gps_t[-1] - 5.0:
        starts.append(t)
        t += args.stride

    # collect per-window results keyed by window start, only windows valid for ALL configs
    per_cfg: Dict[str, Dict[float, dict]] = {c.name: {} for c in rre.CONFIGS}
    for cfg in rre.CONFIGS:
        rng = random.Random(args.seed)
        for s in starts:
            r = rre.run_window(ride, wp, junctions, cfg, s, s + args.blackout,
                               rng, args.miss_rate, 25.0, 40.0)
            if r:
                per_cfg[cfg.name][s] = r

    common = set(per_cfg[rre.CONFIGS[0].name])
    for c in rre.CONFIGS[1:]:
        common &= set(per_cfg[c.name])
    common = sorted(common)
    print(f"  paired windows: {len(common)} (blackout {args.blackout:.0f} s)\n")

    names = [c.name for c in rre.CONFIGS]
    A, B, C, D = names

    def series(cfg, key):
        return [per_cfg[cfg][s][key] for s in common]

    out = {"blackout_s": args.blackout, "n_windows": len(common), "contrasts": {}}

    print("=" * 90)
    print(f" PAIRED CONTRASTS — real ride, {args.blackout:.0f}s blackouts, "
          f"n={len(common)} windows".center(90))
    print("=" * 90)
    for key, label in [("peak_error_m", "peak error"),
                       ("mean_error_m", "mean error")]:
        print(f"\n  --- {label} (m), lower is better ---")
        for lhs, rhs in [(B, A), (C, A), (D, A), (D, B), (D, C)]:
            d = [x - y for x, y in zip(series(lhs, key), series(rhs, key))]
            m, lo, hi = ci95(d)
            wins = sum(1 for x in d if x < 0) / len(d)
            p = wilcoxon_p(d)
            base = statistics.fmean(series(rhs, key))
            pct = 100.0 * m / base if base else 0.0
            sig = "*" if (p == p and p < 0.05) else " "
            print(f"    {lhs.split(':')[0]} vs {rhs.split(':')[0]}: "
                  f"{m:+7.1f} m ({pct:+5.1f}%)  95% CI [{lo:+6.1f},{hi:+6.1f}]  "
                  f"win {wins*100:3.0f}%  p={p:.4f}{sig}")
            out["contrasts"][f"{label}|{lhs.split(':')[0]}-{rhs.split(':')[0]}"] = {
                "mean_diff_m": round(m, 2), "pct": round(pct, 1),
                "ci95": [round(lo, 2), round(hi, 2)],
                "win_rate": round(wins, 3),
                "wilcoxon_p": None if p != p else round(p, 5)}

    print(f"\n  --- next-junction correctness (higher is better) ---")
    for cfg in names:
        v = series(cfg, "pointer_correct")
        m, lo, hi = ci95(v)
        print(f"    {cfg:<26} {m*100:5.1f}%   95% CI [{lo*100:5.1f},{hi*100:5.1f}]")
        out.setdefault("pointer_correct", {})[cfg] = {
            "rate": round(m, 3), "ci95": [round(lo, 3), round(hi, 3)]}
    print("=" * 90)

    o = Path(args.out); o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(json.dumps(out, indent=2))
    print(f"\nJSON: {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
