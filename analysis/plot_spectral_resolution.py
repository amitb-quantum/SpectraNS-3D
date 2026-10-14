#!/usr/bin/env python3
"""Figure for the spectral resolution addendum (optional; needs matplotlib).

Matplotlib is not part of the locked simulation environment. The figure was
made with matplotlib 3.11.2 and numpy; plotting never changes the analysis.

Usage:
    python analysis/plot_spectral_resolution.py --output docs/evidence/2026-10-14/spectral_resolution
"""
import argparse
import csv
import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("spectral_resolution", HERE / "spectral_resolution.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f1f1e", "#6b6a64", "#e4e3de"
SERIES = {  # validated categorical slots 1-3, plus line style as secondary encoding
    "enstrophy": ("#2a78d6", "-", "Enstrophy  (k²E)"),
    "viscous_loss": ("#eb6834", "--", "Viscous loss  (k⁴E)"),
    "peak_proxy": ("#1baf7a", ":", "Peak-vorticity proxy  (k²√E)"),
}
PAIR_COLOR = {"N512/N768": "#2a78d6", "N640/N768": "#eb6834"}
MATCHED = (1.00, 1.10)


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(argv)
    rows = list(csv.DictReader(open(a.output / "grid_disagreement.csv")))
    spectra = {N: sr.load_spectra(p) for N, p in sr.verify_inputs().items()}

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [1, 1, 1.1]})
    for ax, pair in zip(axes[:2], ("N640/N768", "N512/N768")):
        style(ax)
        R = [r for r in rows if r["pair"] == pair]
        t = np.array([float(r["t"]) for r in R])
        ends = []
        for key, (color, ls, label) in SERIES.items():
            y = 100 * np.array([float(r[f"{key}_disagreeing"]) for r in R])
            ax.plot(t, y, color=color, linestyle=ls, linewidth=2)
            ends.append([y[-1], label.split("  ")[0]])
        ends.sort()
        for i in range(1, len(ends)):  # keep direct labels at least 3.5 units apart
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + 3.5)
        for y_end, label in ends:
            ax.annotate(label, (t[-1], y_end), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=8.5, color=INK)
        for tm in MATCHED:
            ax.axvline(tm, color=MUTED, linewidth=0.8, linestyle=(0, (2, 3)))
        ax.set_ylim(0, 50)
        ax.set_xlim(0, 1.32)
        ax.set_xlabel("simulated time t", color=MUTED, fontsize=9)
        ax.set_title(f"{pair}: share in shells differing > 1%", color=INK, fontsize=10.5, loc="left")
    axes[0].set_ylabel("% of quantity (finer-grid spectrum)", color=MUTED, fontsize=9)
    axes[0].text(1.00, 48, "matched local-peak\ntimes 1.00, 1.10", fontsize=7.5, color=MUTED, ha="right", va="top")

    ax = axes[2]
    style(ax)
    for pair, (c, f) in (("N512/N768", (512, 768)), ("N640/N768", (640, 768))):
        kc = sr.k_max(c)
        k = np.arange(1, kc + 1)
        ratio = spectra[c][1.0][1:kc + 1] / spectra[f][1.0][1:kc + 1]
        ax.plot(k / kc, ratio, color=PAIR_COLOR[pair], linewidth=1.6, label=pair)
    ax.axhspan(0.99, 1.01, color=GRID, linewidth=0)
    ax.axhline(1.0, color=MUTED, linewidth=0.8)
    ax.set_xlim(0, 1.0)
    ax.set_yscale("log")
    ax.set_ylim(0.8, 8.0)
    ax.set_yticks([0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 5.0, 8.0])
    ax.set_yticklabels(["0.9", "1.0", "1.1", "1.25", "1.5", "2", "3", "5", "8"])
    ax.minorticks_off()
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", labelcolor=INK)
    ax.set_xlabel("shell k / coarser grid's last full shell", color=MUTED, fontsize=9)
    ax.set_ylabel("coarse / fine shell energy", color=MUTED, fontsize=9)
    ax.set_title("Shell energy ratio at t = 1.00 (band = ±1%)", color=INK, fontsize=10.5, loc="left")

    fig.tight_layout()
    fig.savefig(a.output / "spectral_resolution.png", dpi=160, facecolor=SURFACE)


if __name__ == "__main__":
    main()
