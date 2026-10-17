"""Regenerate the INDICON paper's ride-trace and ablation figures as vector PDFs.

Both figures are drawn at their printed width (one IEEE column, 3.5 in) so
font sizes in the PDF match the page.

    python3 tests/make_paper_figures.py <ride_dir> <out_dir>
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import real_ride_eval as rre  # noqa: E402

COL_W = 3.5
TRACE_START_S = 185.05847485351563
plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
    "axes.spines.top": False, "axes.spines.right": False,
})
COLORS = ["#7f7f7f", "#3b6ea8", "#c0392b", "#1e7a46"]


def windows(ride, wp, junctions, blackout=60.0, stride=10.0, seed=1000):
    starts, t = [], ride.gps_t[0] + 5.0
    while t + blackout <= ride.gps_t[-1] - 5.0:
        starts.append(t)
        t += stride
    res = {}
    for cfg in rre.CONFIGS:
        rng = random.Random(seed)
        res[cfg.name] = {s: rre.run_window(ride, wp, junctions, cfg, s, s + blackout,
                                           rng, 0.05, 25.0, 40.0) for s in starts}
    common = [s for s in starts if all(res[c.name][s] for c in rre.CONFIGS)]
    return res, common


def trace_figure(res, out: Path):
    a = res[rre.CONFIGS[0].name][TRACE_START_S]
    d = res[rre.CONFIGS[3].name][TRACE_START_S]
    fig, ax = plt.subplots(figsize=(COL_W, 1.25))
    ax.plot(*zip(*a["trace"]), color=COLORS[2], lw=1.4, label="A: dead reckoning only")
    ax.plot(*zip(*d["trace"]), color=COLORS[3], lw=1.4, label="D: complete system")
    for i, et in enumerate(d["events_t"]):
        ax.axvline(et, color="#555555", ls="--", lw=0.8,
                   label="accepted junction event" if i == 0 else None)
    ax.set_xlabel("Time since GNSS loss (s)")
    ax.set_ylabel("Position error (m)")
    ax.set_xlim(0, 60)
    ax.set_ylim(0, None)
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.42), frameon=False, handlelength=1.8)
    fig.tight_layout(pad=0.3)
    fig.savefig(out)
    plt.close(fig)


def ablation_figure(res, common, out: Path):
    labels = ["A: DR\nonly", "B: DR +\nmap match", "C: DR +\njunction", "D: complete\nsystem"]
    means, cis = [], []
    for cfg in rre.CONFIGS:
        v = [res[cfg.name][s]["peak_error_m"] for s in common]
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        means.append(m)
        cis.append(1.96 * sd / math.sqrt(len(v)))
    fig, ax = plt.subplots(figsize=(COL_W, 1.25))
    x = range(len(means))
    ax.bar(x, means, yerr=cis, capsize=3, width=0.62, color=COLORS,
           error_kw={"elinewidth": 0.9, "ecolor": "#333333"})
    for i, (m, c) in enumerate(zip(means, cis)):
        ax.text(i, m + c + 4, f"{m:.0f}", ha="center", fontsize=7.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Peak position error (m)")
    ax.set_ylim(0, max(m + c for m, c in zip(means, cis)) * 1.15)
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    fig.tight_layout(pad=0.3)
    fig.savefig(out)
    plt.close(fig)
    return means


def main() -> int:
    ride = rre.load_ride(Path(sys.argv[1]))
    out_dir = Path(sys.argv[2])
    rre.YAW_SIGN = rre.resolve_yaw_sign(ride)
    wp, junctions = rre.build_route(ride)
    res, common = windows(ride, wp, junctions)
    trace_figure(res, out_dir / "real_ride_trace.pdf")
    means = ablation_figure(res, common, out_dir / "ablation_bar.pdf")
    print(f"windows={len(common)} means={[round(m, 1) for m in means]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
