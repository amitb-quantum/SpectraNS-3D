"""Quantum spectral advection step: circuits, exact references and analysis.

A 4-qubit register holds a 16-point periodic profile psi_j (amplitude
encoding). One pseudo-spectral advection step is

    QFT  ->  multiply mode k by exp(i k phi)  ->  inverse QFT,

the same structure SpectraNS-3D uses for the linear part of its solver.
Pure advection is unitary, so it runs natively. Shifts are half-integer
numbers of grid cells, so the result is genuine Fourier (band-limited)
interpolation rather than a relabelling of grid points.

Measured in the position basis the circuit returns p_j = |psi_j|^2; with
one extra QFT before readout it returns the modal distribution |a_k|^2,
which pure advection must leave unchanged.

Everything here is offline and deterministic. See PREREGISTRATION.md.
"""
from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFTGate, StatePreparation

N_QUBITS = 4
N = 2**N_QUBITS
KAPPA = 2.0                       # von Mises profile width; |k| >= 6 carries 4.6e-7 of the norm
SHIFTS = (0.0, 1.5, 3.5, 5.5)     # grid cells
SHOTS = 4096
PATH = (1, 2, 3, 16)              # ibm_kingston path from AB's v6 backend audit
OPTIMIZATION_LEVEL = 2
SEED_TRANSPILER = 7
MAX_EXECUTION_TIME_S = 60         # hard runtime cap passed to the job
BUDGET_LIMIT_S = 45.0             # execute refuses if the estimate exceeds this

# Pre-registered thresholds (see PREREGISTRATION.md)
P1_CENTROID_MAX_CELLS = 0.25
P2_RAW_PEAK_MIN_DEFICIT = 0.05
P4_CORRECTED_PEAK_MAX_REL = 0.075
P3_MIN_INACCURACY_TVD = 0.05
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20261014

X = 2 * np.pi * np.arange(N) / N


def profile(kappa: float = KAPPA) -> np.ndarray:
    """Normalised real, positive von Mises bump centred on cell 8."""
    u = np.exp(kappa * np.cos(X - np.pi))
    return u / np.linalg.norm(u)


def signed_modes() -> np.ndarray:
    """Mode number attached to each QFT output index in the circuit convention.

    Index m in 0..15 is read as a 4-bit two's-complement integer, so 8..15
    map to -8..-1. The circuit's linear phase uses exactly these values.
    """
    m = np.arange(N)
    return np.where(m < N // 2, m, m - N)


def exact_shift(psi: np.ndarray, shift: float) -> np.ndarray:
    """Exact band-limited translation psi(x - shift*dx) with the circuit's mode convention.

    Qiskit's QFT uses exp(+2 pi i j m / N), the conjugate of numpy's FFT, so
    QFT index m carries numpy frequency -m. Matching the circuit's signed
    mode for index m therefore means numpy frequency -signed_modes()[m],
    which differs from numpy's default only at the Nyquist mode.
    """
    freq = np.zeros(N)
    freq[(-np.arange(N)) % N] = -signed_modes()
    return np.fft.ifft(np.fft.fft(psi) * np.exp(-2j * np.pi * freq * shift / N))


def logical_circuit(psi: np.ndarray, shift: float, spectral: bool) -> QuantumCircuit:
    """State preparation, QFT, linear phase, inverse QFT [, QFT], then measure.

    Barriers keep the transpiler from cancelling QFT with its inverse (which
    would otherwise happen exactly at shift 0) so every circuit carries the
    same spectral step.
    """
    qc = QuantumCircuit(N_QUBITS, name=f"advect_s{shift}_{'spectral' if spectral else 'position'}")
    qc.append(StatePreparation(psi), range(N_QUBITS))
    qc.barrier()
    qc.append(QFTGate(N_QUBITS), range(N_QUBITS))
    qc.barrier()
    phi = 2 * np.pi * shift / N
    for q in range(N_QUBITS):
        weight = 2**q if q < N_QUBITS - 1 else -(2**q)   # two's-complement bit weights
        qc.p(phi * weight, q)
    qc.barrier()
    qc.append(QFTGate(N_QUBITS).inverse(), range(N_QUBITS))
    if spectral:
        qc.barrier()
        qc.append(QFTGate(N_QUBITS), range(N_QUBITS))
    qc.measure_all()
    return qc


def readout_circuits() -> list[QuantumCircuit]:
    """Prepare |0000> and |1111> for tensored (per-qubit) readout calibration."""
    out = []
    for name, flip in (("readout_0000", False), ("readout_1111", True)):
        qc = QuantumCircuit(N_QUBITS, name=name)
        if flip:
            qc.x(range(N_QUBITS))
        qc.measure_all()
        out.append(qc)
    return out


def experiment(psi: np.ndarray | None = None):
    """Ordered circuit list and a matching metadata list."""
    psi = profile() if psi is None else psi
    circuits, meta = [], []
    for s in SHIFTS:
        for spectral in (False, True):
            circuits.append(logical_circuit(psi, s, spectral))
            meta.append({"kind": "spectral" if spectral else "position", "shift": s})
    for qc in readout_circuits():
        circuits.append(qc)
        meta.append({"kind": qc.name})
    return circuits, meta


def ideal_distributions(psi: np.ndarray | None = None) -> dict:
    """Exact position and modal distributions for every shift."""
    psi = profile() if psi is None else psi
    out = {}
    for s in SHIFTS:
        shifted = exact_shift(psi, s)
        modal = np.fft.ifft(shifted) * np.sqrt(N)       # Qiskit QFT amplitudes
        out[s] = {"position": np.abs(shifted) ** 2, "spectral": np.abs(modal) ** 2}
    return out


# ---------------------------------------------------------------- analysis

def counts_to_probs(counts: dict[str, int]) -> np.ndarray:
    p = np.zeros(N)
    for key, value in counts.items():
        p[int(key.replace(" ", ""), 2)] += value
    return p / p.sum()


def tensored_inverse(counts0: dict, counts1: dict) -> np.ndarray:
    """Inverse of the per-qubit assignment matrix built from |0000> and |1111> runs."""
    inverses = []
    for q in range(N_QUBITS):
        n0, n1 = sum(counts0.values()), sum(counts1.values())
        e01 = sum(v for k, v in counts0.items() if k.replace(" ", "")[::-1][q] == "1") / n0  # read 1 | prep 0
        e10 = sum(v for k, v in counts1.items() if k.replace(" ", "")[::-1][q] == "0") / n1  # read 0 | prep 1
        inverses.append(np.linalg.inv(np.array([[1 - e01, e10], [e01, 1 - e10]])))
    M = inverses[N_QUBITS - 1]
    for q in range(N_QUBITS - 2, -1, -1):
        M = np.kron(M, inverses[q])
    return M


def mitigate(p: np.ndarray, Minv: np.ndarray) -> np.ndarray:
    q = np.clip(Minv @ p, 0, None)
    return q / q.sum()


def centroid_cells(p: np.ndarray) -> float:
    return float((np.angle(np.sum(p * np.exp(1j * X))) % (2 * np.pi)) / (2 * np.pi / N))


def circular_cell_error(a: float, b: float) -> float:
    return float(abs((a - b + N / 2) % N - N / 2))


def tvd(p: np.ndarray, q: np.ndarray) -> float:
    return float(0.5 * np.abs(p - q).sum())


def depolarizing_epsilon(p_noisy: np.ndarray, p_exact: np.ndarray) -> float:
    """Least-squares eps in p_noisy = (1 - eps) p_exact + eps / N."""
    A = p_exact - 1 / N
    return float(-np.dot(p_noisy - p_exact, A) / np.dot(A, A))


def depolarizing_correct(p: np.ndarray, eps: float) -> np.ndarray:
    return (p - eps / N) / (1 - eps)


def observables(position: dict, spectral: dict, Minv: np.ndarray, ideal: dict) -> dict:
    """Every pre-registered quantity from one set of distributions."""
    ref0 = ideal[0.0]["position"]
    eps = depolarizing_epsilon(mitigate(position[0.0], Minv), ref0)
    out = {"epsilon_from_shift0_twin": eps, "shifts": {}}
    for s in SHIFTS:
        pe, qe = ideal[s]["position"], ideal[s]["spectral"]
        raw = position[s]
        row = {
            "centroid_exact": centroid_cells(pe),
            "centroid_raw": centroid_cells(raw),
            "centroid_error_cells": circular_cell_error(centroid_cells(raw), centroid_cells(pe)),
            "peak_exact": float(pe.max()),
            "peak_raw": float(raw.max()),
            "peak_raw_rel": float(raw.max() / pe.max() - 1),
            "position_tvd_raw": tvd(raw, pe),
            "spectral_tvd_vs_exact": tvd(spectral[s], qe),
        }
        if s != 0.0:
            corr = depolarizing_correct(mitigate(raw, Minv), eps)
            row["peak_corrected"] = float(corr.max())
            row["peak_corrected_rel"] = float(corr.max() / pe.max() - 1)
        out["shifts"][f"{s}"] = row
    out["spectral_max_pairwise_tvd"] = max(
        tvd(spectral[a], spectral[b]) for i, a in enumerate(SHIFTS) for b in SHIFTS[i + 1:])
    out["spectral_min_tvd_vs_exact"] = min(r["spectral_tvd_vs_exact"] for r in out["shifts"].values())
    return out


def assess(obs: dict) -> dict:
    """Evaluate predictions P1-P4 exactly as pre-registered."""
    rows = obs["shifts"]
    moved = [k for k in rows if float(k) != 0.0]
    p1 = max(r["centroid_error_cells"] for r in rows.values())
    p2 = max(r["peak_raw_rel"] for r in rows.values())          # least negative deficit
    p4 = max(abs(rows[k]["peak_corrected_rel"]) for k in moved)
    return {
        "P1_integral_centroid_survives": {"value": p1, "threshold": P1_CENTROID_MAX_CELLS,
                                          "pass": p1 <= P1_CENTROID_MAX_CELLS},
        "P2_local_peak_biased_low": {"value": p2, "threshold": -P2_RAW_PEAK_MIN_DEFICIT,
                                     "pass": p2 <= -P2_RAW_PEAK_MIN_DEFICIT},
        "P3_consistent_but_inaccurate": {"max_pairwise_tvd": obs["spectral_max_pairwise_tvd"],
                                         "min_tvd_vs_exact": obs["spectral_min_tvd_vs_exact"],
                                         "inaccuracy_floor": P3_MIN_INACCURACY_TVD,
                                         "pass": (obs["spectral_min_tvd_vs_exact"] > obs["spectral_max_pairwise_tvd"]
                                                  and obs["spectral_min_tvd_vs_exact"] >= P3_MIN_INACCURACY_TVD)},
        "P4_twin_calibrated_peak_recovers": {"value": p4, "threshold": P4_CORRECTED_PEAK_MAX_REL,
                                             "pass": p4 <= P4_CORRECTED_PEAK_MAX_REL},
    }


def split_results(counts: list[dict], meta: list[dict]):
    position, spectral, cal = {}, {}, {}
    for c, m in zip(counts, meta):
        if m["kind"] == "position":
            position[m["shift"]] = counts_to_probs(c)
        elif m["kind"] == "spectral":
            spectral[m["shift"]] = counts_to_probs(c)
        else:
            cal[m["kind"]] = c
    return position, spectral, tensored_inverse(cal["readout_0000"], cal["readout_1111"])


def analyse_counts(counts: list[dict], meta: list[dict], psi: np.ndarray | None = None) -> dict:
    """Point estimates, multinomial bootstrap intervals and the P1-P4 verdicts."""
    ideal = ideal_distributions(psi)
    position, spectral, Minv = split_results(counts, meta)
    point = observables(position, spectral, Minv, ideal)

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    def resample(c):
        keys = list(c)
        draw = rng.multinomial(sum(c.values()), np.array([c[k] for k in keys]) / sum(c.values()))
        return dict(zip(keys, draw))
    samples = []
    for _ in range(BOOTSTRAP_SAMPLES):
        boot = [resample(c) for c in counts]
        bp, bs, bM = split_results(boot, meta)
        samples.append(observables(bp, bs, bM, ideal))

    def interval(path):
        vals = np.array([path(s) for s in samples])
        return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]
    ci = {"epsilon_from_shift0_twin": interval(lambda s: s["epsilon_from_shift0_twin"]),
          "spectral_max_pairwise_tvd": interval(lambda s: s["spectral_max_pairwise_tvd"]),
          "spectral_min_tvd_vs_exact": interval(lambda s: s["spectral_min_tvd_vs_exact"]),
          "shifts": {}}
    for k, row in point["shifts"].items():
        ci["shifts"][k] = {f: interval(lambda s, k=k, f=f: s["shifts"][k][f])
                           for f in row if not f.endswith("_exact")}
    verdicts = assess(point)
    boot_pass = {name: float(np.mean([assess(s)[name]["pass"] for s in samples])) for name in verdicts}
    return {"point": point, "bootstrap_95ci": ci, "verdicts": verdicts,
            "bootstrap_pass_fraction": boot_pass,
            "bootstrap": {"samples": BOOTSTRAP_SAMPLES, "seed": BOOTSTRAP_SEED}}
