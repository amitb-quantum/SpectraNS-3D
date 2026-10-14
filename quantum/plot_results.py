#!/usr/bin/env python3
"""Figure for a completed run bundle (needs matplotlib; does not change any result).

    python quantum/plot_results.py --bundle quantum/runs/kingston_001
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spectral_advection as sa  # noqa: E402

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f1f1e", "#6b6a64", "#e4e3de"
RAW, MIT = "#2a78d6", "#eb6834"          # validated categorical slots 1-2
SHIFT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    a = ap.parse_args(argv)
    bundle = Path(a.bundle)
    counts = json.loads((bundle / "counts.json").read_text())["counts"]
    manifest = json.loads((bundle / "manifest.json").read_text())
    meta, path = manifest["meta"], manifest.get("path", list(sa.PATH))
    pos, spec, Minv = sa.split_results(counts, meta)
    ideal = sa.ideal_distributions()
    cells = np.arange(sa.N)

    fig, axes = plt.subplots(2, 3, figsize=(14, 7.2), facecolor=SURFACE)
    panels = [(axes[0, 0], 0.0), (axes[0, 1], 1.5), (axes[0, 2], 3.5), (axes[1, 0], 5.5)]
    for ax, s in panels:
        style(ax)
        ax.bar(cells - 0.2, pos[s], width=0.38, color=RAW, label="measured (raw)")
        ax.bar(cells + 0.2, sa.mitigate(pos[s], Minv), width=0.38, color=MIT, label="readout-corrected")
        ax.step(np.r_[cells - 0.5, 15.5], np.r_[ideal[s]["position"], ideal[s]["position"][-1]],
                where="post", color=INK, linewidth=1.4, label="exact")
        ax.set_ylim(0, 0.36)
        ax.set_xticks(range(0, 16, 2))
        ax.set_title(f"Position basis, shift {s} cells", color=INK, fontsize=10, loc="left")
        ax.set_xlabel("grid cell", color=MUTED, fontsize=8.5)
    axes[0, 0].set_ylabel("probability", color=MUTED, fontsize=8.5)
    axes[1, 0].set_ylabel("probability", color=MUTED, fontsize=8.5)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK)

    ax = axes[1, 1]
    style(ax)
    ax.step(np.r_[cells - 0.5, 15.5], np.r_[ideal[0.0]["spectral"], ideal[0.0]["spectral"][-1]],
            where="post", color=INK, linewidth=1.6, label="exact (all shifts)")
    for color, s in zip(SHIFT_COLORS, sa.SHIFTS):
        ax.plot(cells, spec[s], marker="o", markersize=4, linewidth=1.2, color=color, label=f"measured, shift {s}")
    ax.set_xticks(range(0, 16, 2))
    ax.set_xlabel("QFT output index (mode)", color=MUTED, fontsize=8.5)
    ax.set_title("Spectral basis: runs agree, all wrong", color=INK, fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=7.5, labelcolor=INK)

    ax = axes[1, 2]
    style(ax)
    cal = {m["kind"]: c for c, m in zip(counts, meta) if m["kind"].startswith("readout")}
    e01, e10 = [], []
    for q in range(sa.N_QUBITS):
        n0, n1 = sum(cal["readout_0000"].values()), sum(cal["readout_1111"].values())
        e01.append(100 * sum(v for k, v in cal["readout_0000"].items() if k[::-1][q] == "1") / n0)
        e10.append(100 * sum(v for k, v in cal["readout_1111"].items() if k[::-1][q] == "0") / n1)
    x = np.arange(sa.N_QUBITS)
    ax.bar(x - 0.2, e01, width=0.38, color=RAW, label="read 1 when 0")
    ax.bar(x + 0.2, e10, width=0.38, color=MIT, label="read 0 when 1")
    for xi, v in zip(x, e01):
        ax.annotate(f"{v:.1f}%", (xi - 0.2, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([f"phys {p}" for p in path])
    ax.set_ylabel("readout error (%)", color=MUTED, fontsize=8.5)
    ax.set_title("In-job readout calibration", color=INK, fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)

    fig.tight_layout()
    fig.savefig(bundle / "results.png", dpi=150, facecolor=SURFACE)


if __name__ == "__main__":
    main()
