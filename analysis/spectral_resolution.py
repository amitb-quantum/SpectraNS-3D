#!/usr/bin/env python3
"""Post-hoc spectral resolution analysis of the completed N512/N640/N768 study.

CPU-only, numpy-only and read-only with respect to campaign evidence. It reads
the three accepted coarse shell spectra (0 <= t <= 1.10), verifies each file's
SHA256 against its published binding, and reports:

1. Shell-by-shell agreement between grids: the first shell where a coarser
   grid's shell energy departs from a finer grid's by more than 1% and 10%.
2. Where that disagreement matters: the fraction of enstrophy (k^2 E), viscous
   enstrophy loss (k^4 E) and a peak-vorticity proxy (k^2 sqrt(E)) carried by
   shells where the grids disagree by more than 1%, plus the fraction in shells
   above the coarser grid's cutoff.
3. The conventional analyticity-strip fit E(k) ~ C k^-n exp(-2 delta k), with
   its sensitivity to the fitting window reported alongside every value.

The peak-vorticity proxy follows from |omega|_inf <= sum_k |omega_hat(k)|: a
shell of radius k holding energy E(k) spread over ~4 pi k^2 modes contributes at
most ~k^2 sqrt(E(k)) up to a constant. It is a heuristic weighting that shows
which shells can move a local maximum; it is not a measured error bound.

Spectra files contain shell sums (see Solver.spectrum_shells) despite the
historical column name E_shell_mean_density.

Usage:
    python analysis/spectral_resolution.py --output docs/evidence/2026-10-14/spectral_resolution
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/2026-10-13"

# Accepted coarse spectra and where each file's SHA256 is published.
INPUTS = {
    512: {
        "path": "artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse/spectra.csv",
        "binding": "configs/n512_interpolated_peak_reference.json",
    },
    640: {
        "path": "docs/evidence/2026-10-13/n640_campaign_004/protected/coarse/spectra.csv",
        "binding": "docs/evidence/2026-10-13/n640_campaign_004/protected/collection_manifest.json",
    },
    768: {
        "path": "docs/evidence/2026-10-13/n768_campaign_002/protected/coarse/spectra.csv",
        "binding": "docs/evidence/2026-10-13/n768_campaign_002/protected/collection_manifest.json",
    },
}
T_END = 1.10                      # common accepted interval; N512's failed 1.11 event is excluded
PAIRS = [(512, 640), (512, 768), (640, 768)]
THRESHOLDS = (0.01, 0.10)
DISAGREE = 0.01                   # shell counted as disagreeing above this relative difference
LO_FRACTIONS = (0.3, 0.4, 0.5)    # strip-fit window edges as fractions of k_max
HI_FRACTIONS = (0.8, 0.85, 0.9)
NOMINAL_WINDOW = (0.4, 0.9)
WEIGHTS = {
    "enstrophy": lambda k, E: k**2 * E,
    "viscous_loss": lambda k, E: k**4 * E,
    "peak_proxy": lambda k, E: k**2 * np.sqrt(E),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_hash(binding: dict, name: str = "spectra.csv") -> str:
    """Return the unique SHA256 bound to a spectra file inside a JSON binding."""
    found: list[str] = []

    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and key.endswith(name) and key in (name, f"coarse/{name}"):
            found.append(node)

    walk(binding)
    if len(set(found)) != 1:
        raise ValueError(f"expected exactly one bound hash for {name}, found {sorted(set(found))}")
    return found[0]


def verify_inputs(root: Path = ROOT) -> dict[int, Path]:
    paths = {}
    for N, spec in INPUTS.items():
        path, binding = root / spec["path"], root / spec["binding"]
        expected = find_hash(json.loads(binding.read_text()))
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"N{N} spectra hash mismatch: {actual} != {expected} ({binding})")
        paths[N] = path
    return paths


def load_spectra(path: Path, t_end: float = T_END) -> dict[float, np.ndarray]:
    """Map event time -> shell-sum array indexed by integer shell number."""
    rows: dict[float, dict[int, float]] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            t = round(float(r["t"]), 2)
            if t <= t_end + 1e-9:
                rows.setdefault(t, {})[int(r["shell_k"])] = float(r["E_shell_mean_density"])
    out = {}
    for t, shells in rows.items():
        ks = sorted(shells)
        if ks != list(range(len(ks))):
            raise ValueError(f"{path}: shells at t={t} are not contiguous from 0")
        out[t] = np.array([shells[k] for k in ks])
    return out


def k_max(N: int) -> int:
    """Largest fully populated shell under the strict |k| < N/3 cutoff.

    Shells are rounded to the nearest integer radius, so shell s spans
    [s - 1/2, s + 1/2); it is complete only when s + 1/2 <= N/3. Partially
    filled outer shells are excluded from every comparison here.
    """
    return int(np.floor(N / 3 - 0.5))


def onset(coarse: np.ndarray, fine: np.ndarray, kc: int, threshold: float, k_start: int = 1):
    for k in range(k_start, kc + 1):
        if fine[k] > 0 and abs(coarse[k] / fine[k] - 1) > threshold:
            return k
    return None


def weighted_fractions(coarse: np.ndarray, fine: np.ndarray, kc: int) -> dict:
    k = np.arange(len(fine), dtype=float)
    shells = slice(1, len(fine))
    inside = np.zeros(len(fine), bool)
    inside[1:kc + 1] = True
    ratio = np.ones(len(fine))
    ratio[1:kc + 1] = coarse[1:kc + 1] / fine[1:kc + 1]
    disagree = inside & (np.abs(ratio - 1) > DISAGREE)
    beyond = ~inside
    beyond[0] = False
    out = {}
    for name, w in WEIGHTS.items():
        ww = np.zeros(len(fine))
        ww[shells] = w(k[shells], fine[shells])
        total = ww.sum()
        out[name] = {"disagreeing_shells": float(ww[disagree].sum() / total),
                     "above_coarse_cutoff": float(ww[beyond].sum() / total)}
    return out


def strip_fit(E: np.ndarray, lo: float, hi: float):
    """Least-squares fit of ln E = c - n ln k - 2 delta k over lo <= k <= hi."""
    k = np.arange(len(E), dtype=float)
    m = (k >= lo) & (k <= hi) & (E > 0)
    if m.sum() < 4:
        raise ValueError("strip fit needs at least four positive shells")
    A = np.c_[np.ones(m.sum()), -np.log(k[m]), -2 * k[m]]
    (c, n, delta), *_ = np.linalg.lstsq(A, np.log(E[m]), rcond=None)
    rms = float(np.std(np.log(E[m]) - A @ np.array([c, n, delta])))
    return float(delta), float(n), rms


def strip_summary(E: np.ndarray, N: int) -> dict:
    km = k_max(N)
    delta, n, rms = strip_fit(E, NOMINAL_WINDOW[0] * km, NOMINAL_WINDOW[1] * km)
    spread = [strip_fit(E, lo * km, hi * km)[0] for lo, hi in itertools.product(LO_FRACTIONS, HI_FRACTIONS)]
    return {"delta": delta, "n": n, "log_rms": rms, "kmax_delta": delta * km,
            "delta_window_min": min(spread), "delta_window_max": max(spread)}


def analyse(root: Path = ROOT) -> dict:
    spectra = {N: load_spectra(p) for N, p in verify_inputs(root).items()}
    times = sorted(set.intersection(*(set(s) for s in spectra.values())))
    pairs = []
    for c, f in PAIRS:
        kc = k_max(c)
        for t in times:
            Ec, Ef = spectra[c][t], spectra[f][t]
            row = {"pair": f"N{c}/N{f}", "t": t}
            for thr in THRESHOLDS:
                k = onset(Ec, Ef, kc, thr)
                row[f"onset_{int(thr*100)}pct_k"] = k
                row[f"onset_{int(thr*100)}pct_k_over_kmax"] = None if k is None else k / kc
            for name, frac in weighted_fractions(Ec, Ef, kc).items():
                row[f"{name}_disagreeing"] = frac["disagreeing_shells"]
                row[f"{name}_above_cutoff"] = frac["above_coarse_cutoff"]
            pairs.append(row)
    strips = [{"grid": f"N{N}", "t": t, **strip_summary(spectra[N][t], N)}
              for N in spectra for t in times]
    return {"times": times, "pairs": pairs, "strip": strips,
            "inputs": {f"N{N}": {"path": INPUTS[N]["path"], "sha256": sha256(root / INPUTS[N]["path"]),
                                 "binding": INPUTS[N]["binding"]} for N in INPUTS},
            "settings": {"t_end": T_END, "disagree_threshold": DISAGREE, "onset_thresholds": THRESHOLDS,
                         "strip_nominal_window_over_kmax": NOMINAL_WINDOW,
                         "strip_window_lo_over_kmax": LO_FRACTIONS, "strip_window_hi_over_kmax": HI_FRACTIONS,
                         "k_max": {f"N{N}": k_max(N) for N in INPUTS}}}


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def headline(result: dict, times=(0.88, 1.00, 1.10)) -> dict:
    pick = lambda rows, key, val: {r["t"]: r for r in rows if r[key] == val}
    out = {}
    for pair in ("N512/N768", "N640/N768"):
        rows = pick(result["pairs"], "pair", pair)
        out[pair] = {f"{t:.2f}": {k: rows[t][k] for k in rows[t] if k not in ("pair", "t")} for t in times}
    for grid in ("N512", "N640", "N768"):
        rows = pick(result["strip"], "grid", grid)
        out[f"strip_{grid}"] = {f"{t:.2f}": rows[t] for t in times}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(argv)
    result = analyse()
    a.output.mkdir(parents=True, exist_ok=True)
    write_csv(a.output / "grid_disagreement.csv", result["pairs"])
    write_csv(a.output / "strip_fit.csv", result["strip"])
    summary = {"inputs": result["inputs"], "settings": result["settings"],
               "event_count": len(result["times"]), "headline": headline(result)}
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["headline"]["N640/N768"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
