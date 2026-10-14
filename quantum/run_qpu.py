#!/usr/bin/env python3
"""Prepare, execute and analyse the pre-registered QPU spectral advection run.

    prepare   Read-only. Transpiles onto the pre-registered path, freezes the
              exact circuits (QPY) and a manifest, estimates QPU time, and runs
              a noisy-simulator dry run from the backend's current calibration.
              Never submits a job.
    execute   Submits the frozen circuits as ONE SamplerV2 job, only when
              --manifest-sha matches the frozen bundle, the circuits use only
              the pre-registered qubits, and the time estimate is within the
              budget. The job carries a hard max_execution_time cap.
    analyse   Offline. Scores counts against exact references and the
              pre-registered predictions P1-P4.

Examples (from a checkout, in an environment with qiskit, qiskit-aer and
qiskit-ibm-runtime):

    python quantum/run_qpu.py prepare --backend ibm_kingston --out quantum/runs/kingston_001
    python quantum/run_qpu.py execute --bundle quantum/runs/kingston_001 --manifest-sha <sha printed by prepare>
    python quantum/run_qpu.py analyse --bundle quantum/runs/kingston_001

Use --fake instead of --backend to prepare offline against FakeKingston.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spectral_advection as sa  # noqa: E402

PREREG = HERE / "PREREGISTRATION.md"
JOB_OVERHEAD_S = 5.0          # conservative fixed allowance per job in the estimate


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def write_json(path: Path, obj) -> str:
    data = (json.dumps(obj, indent=2, sort_keys=True, default=_jsonable) + "\n").encode()
    path.write_bytes(data)
    return sha256_bytes(data)


def _jsonable(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))


def versions() -> dict:
    out = {"python": platform.python_version()}
    for mod in ("qiskit", "qiskit_aer", "qiskit_ibm_runtime", "numpy"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:  # pragma: no cover - reported, not fatal
            out[mod] = None
    return out


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(HERE), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def get_backend(args):
    if args.fake:
        from qiskit_ibm_runtime.fake_provider import FakeKingston
        return FakeKingston()
    from qiskit_ibm_runtime import QiskitRuntimeService
    service = QiskitRuntimeService(instance=args.instance) if args.instance else QiskitRuntimeService()
    return service.backend(args.backend)


def calibration_stamp(backend) -> str | None:
    try:
        props = backend.properties()
        return props.last_update_date.isoformat() if props is not None else None
    except Exception:
        return None


def active_qubits(circuits) -> set[int]:
    used = set()
    for qc in circuits:
        for ins in qc.data:
            if ins.operation.name == "barrier":
                continue
            used |= {qc.find_bit(q).index for q in ins.qubits}
    return used


def duration_s(qc, backend) -> float:
    try:
        return float(qc.estimate_duration(backend.target, unit="s"))
    except Exception:
        return 100e-9 * qc.depth()      # coarse fallback: 100 ns per layer


def rep_delay_s(backend) -> float:
    try:
        return float(backend.configuration().default_rep_delay)
    except Exception:
        return 250e-6


def budget(circuits, backend, shots: int) -> dict:
    rep = rep_delay_s(backend)
    per_shot = [rep + duration_s(qc, backend) for qc in circuits]
    estimate = shots * float(np.sum(per_shot)) + JOB_OVERHEAD_S
    return {"shots_per_circuit": shots, "circuits": len(circuits), "total_shots": shots * len(circuits),
            "rep_delay_s": rep, "max_circuit_duration_s": max(duration_s(qc, backend) for qc in circuits),
            "job_overhead_allowance_s": JOB_OVERHEAD_S, "estimated_qpu_seconds": estimate,
            "budget_limit_s": sa.BUDGET_LIMIT_S, "max_execution_time_s": sa.MAX_EXECUTION_TIME_S}


def guard(circuits, bud: dict) -> None:
    extra = active_qubits(circuits) - set(sa.PATH)
    if extra:
        raise SystemExit(f"REFUSED: circuits touch qubits outside the pre-registered path: {sorted(extra)}")
    if bud["estimated_qpu_seconds"] > sa.BUDGET_LIMIT_S:
        raise SystemExit(f"REFUSED: estimated {bud['estimated_qpu_seconds']:.1f} s exceeds {sa.BUDGET_LIMIT_S} s budget")


def counts_from_aer(result, circuits) -> list[dict]:
    return [dict(result.get_counts(qc)) for qc in circuits]


def simulate(circuits, backend, shots: int, seed: int) -> list[dict]:
    from qiskit_aer import AerSimulator
    sim = AerSimulator.from_backend(backend)
    return counts_from_aer(sim.run(circuits, shots=shots, seed_simulator=seed).result(), circuits)


def load_bundle(bundle: Path):
    from qiskit import qpy
    manifest = json.loads((bundle / "manifest.json").read_text())
    if sha256_file(bundle / "circuits.qpy") != manifest["circuits_qpy_sha256"]:
        raise SystemExit("REFUSED: circuits.qpy does not match its manifest hash")
    with open(bundle / "circuits.qpy", "rb") as f:
        circuits = qpy.load(f)
    return manifest, circuits


# ---------------------------------------------------------------- commands

def cmd_prepare(args) -> int:
    from qiskit import qpy, transpile
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"REFUSED: {out} is not empty; use a new directory for each bundle")
    out.mkdir(parents=True, exist_ok=True)
    backend = get_backend(args)
    logical, meta = sa.experiment()
    circuits = transpile(logical, backend=backend, initial_layout=list(sa.PATH),
                         optimization_level=sa.OPTIMIZATION_LEVEL, seed_transpiler=sa.SEED_TRANSPILER)
    bud = budget(circuits, backend, sa.SHOTS)
    guard(circuits, bud)
    with open(out / "circuits.qpy", "wb") as f:
        qpy.dump(circuits, f)
    manifest = {
        "experiment": "spectral_advection_v1",
        "preregistration_sha256": sha256_file(PREREG),
        "git_commit_at_prepare": git_commit(),
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "backend": backend.name, "fake_backend": bool(args.fake),
        "calibration_at_prepare": calibration_stamp(backend),
        "path": list(sa.PATH), "optimization_level": sa.OPTIMIZATION_LEVEL,
        "seed_transpiler": sa.SEED_TRANSPILER, "meta": meta,
        "cz_counts": [qc.count_ops().get("cz", 0) for qc in circuits],
        "depths": [qc.depth() for qc in circuits],
        "circuits_qpy_sha256": sha256_file(out / "circuits.qpy"),
        "budget": bud, "versions": versions(),
        "settings": {"kappa": sa.KAPPA, "shifts": list(sa.SHIFTS), "shots": sa.SHOTS,
                     "twirling": False, "dynamical_decoupling": False},
    }
    manifest_sha = write_json(out / "manifest.json", manifest)

    sim_counts = simulate(circuits, backend, sa.SHOTS, seed=args.sim_seed)
    write_json(out / "dryrun_counts.json", {"simulated": True, "seed_simulator": args.sim_seed,
                                            "noise_model_from": backend.name, "counts": sim_counts})
    dry = sa.analyse_counts(sim_counts, meta)
    write_json(out / "dryrun_assessment.json", dry)

    print(f"Bundle: {out}")
    print(f"Backend: {backend.name}  calibration: {manifest['calibration_at_prepare']}")
    print(f"CZ per circuit: {manifest['cz_counts']}")
    print(f"Estimated QPU time: {bud['estimated_qpu_seconds']:.1f} s  (budget {sa.BUDGET_LIMIT_S} s, "
          f"hard cap {sa.MAX_EXECUTION_TIME_S} s)")
    print(f"Dry run (noisy simulator, {backend.name} calibration {manifest['calibration_at_prepare']}):")
    for name, v in dry["verdicts"].items():
        print(f"  {name}: {'PASS' if v['pass'] else 'FAIL'}  (bootstrap pass fraction "
              f"{dry['bootstrap_pass_fraction'][name]:.2f})")
    print(f"\nNo job was submitted. To run on hardware:\n  python quantum/run_qpu.py execute "
          f"--bundle {out} --manifest-sha {manifest_sha}")
    return 0


def cmd_execute(args, sampler_factory=None) -> int:
    bundle = Path(args.bundle)
    if (bundle / "job.json").exists():
        raise SystemExit("REFUSED: this bundle already has a submitted job; prepare a new bundle to rerun")
    actual = sha256_file(bundle / "manifest.json")
    if actual != args.manifest_sha:
        raise SystemExit(f"REFUSED: manifest sha {actual} does not match --manifest-sha")
    manifest, circuits = load_bundle(bundle)
    if manifest["fake_backend"]:
        raise SystemExit("REFUSED: bundle was prepared against a fake backend")
    if manifest["preregistration_sha256"] != sha256_file(PREREG):
        raise SystemExit("REFUSED: PREREGISTRATION.md changed since this bundle was prepared")
    guard(circuits, manifest["budget"])

    backend = get_backend(argparse.Namespace(fake=False, instance=args.instance, backend=manifest["backend"]))
    cal_now = calibration_stamp(backend)
    if cal_now != manifest["calibration_at_prepare"]:
        print(f"NOTE: calibration changed since prepare ({manifest['calibration_at_prepare']} -> {cal_now}); "
              "the dry run used the earlier one. Proceeding; this is recorded.")

    if sampler_factory is None:
        from qiskit_ibm_runtime import SamplerV2
        sampler_factory = SamplerV2
    sampler = sampler_factory(mode=backend)
    sampler.options.default_shots = sa.SHOTS
    sampler.options.max_execution_time = sa.MAX_EXECUTION_TIME_S
    sampler.options.dynamical_decoupling.enable = False
    sampler.options.twirling.enable_gates = False
    sampler.options.twirling.enable_measure = False

    job = sampler.run(list(circuits))
    record = {"job_id": job.job_id(), "backend": backend.name, "submitted_utc": datetime.now(timezone.utc).isoformat(),
              "calibration_at_submit": cal_now, "manifest_sha256": actual}
    write_json(bundle / "job.json", record)
    print(f"Submitted job {record['job_id']} on {backend.name}; waiting for results...")

    result = job.result()
    counts = [dict(pub.data.meas.get_counts()) for pub in result]
    usage = None
    try:
        usage = job.metrics().get("usage")
    except Exception:
        pass
    write_json(bundle / "counts.json", {"simulated": False, "job_id": record["job_id"], "usage": usage,
                                        "completed_utc": datetime.now(timezone.utc).isoformat(), "counts": counts})
    assessment = sa.analyse_counts(counts, manifest["meta"])
    write_json(bundle / "assessment.json", assessment)
    print(f"Done. QPU usage: {usage}")
    for name, v in assessment["verdicts"].items():
        print(f"  {name}: {'PASS' if v['pass'] else 'FAIL'}")
    return 0


def cmd_analyse(args) -> int:
    bundle = Path(args.bundle)
    manifest, _ = load_bundle(bundle)
    src = bundle / ("counts.json" if (bundle / "counts.json").exists() else "dryrun_counts.json")
    data = json.loads(src.read_text())
    assessment = sa.analyse_counts(data["counts"], manifest["meta"])
    name = "assessment.json" if src.name == "counts.json" else "dryrun_assessment.json"
    write_json(bundle / name, assessment)
    print(f"Analysed {src.name} -> {name}")
    for k, v in assessment["verdicts"].items():
        print(f"  {k}: {'PASS' if v['pass'] else 'FAIL'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--backend")
    g.add_argument("--fake", action="store_true", help="offline: FakeKingston snapshot")
    p.add_argument("--instance")
    p.add_argument("--out", required=True)
    p.add_argument("--sim-seed", type=int, default=20261014)
    e = sub.add_parser("execute")
    e.add_argument("--bundle", required=True)
    e.add_argument("--manifest-sha", required=True)
    e.add_argument("--instance")
    a = sub.add_parser("analyse")
    a.add_argument("--bundle", required=True)
    args = ap.parse_args(argv)
    return {"prepare": cmd_prepare, "execute": cmd_execute, "analyse": cmd_analyse}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
