# Quantum spectral advection on ibm_kingston

A small, pre-registered hardware experiment. It runs the linear part of a SpectraNS-3D-style Fourier step (QFT, a modal phase, inverse QFT) on four qubits and asks which outputs survive real device noise: an integral-type centroid, a local peak, or a conservation check. Read [PREREGISTRATION.md](PREREGISTRATION.md) first; it fixes the circuits, budget and pass criteria before any submission.

This is not a quantum-advantage claim and does not bear on Navier–Stokes regularity. A laptop computes the exact answer.

## Environment

Separate from the locked simulation environment. Tested offline with:

```bash
python -m pip install -r quantum/requirements.txt
python -m pytest -q quantum          # 20 offline tests; no IBM access
```

## Run

```bash
# 1. Read-only: freeze circuits, estimate QPU time, dry-run on current calibration
python quantum/run_qpu.py prepare --backend ibm_kingston --out quantum/runs/kingston_001

# 2. Submit one job (about 15-20 s of QPU time, hard cap 60 s)
python quantum/run_qpu.py execute --bundle quantum/runs/kingston_001 --manifest-sha <printed by prepare>

# 3. Offline re-scoring at any time
python quantum/run_qpu.py analyse --bundle quantum/runs/kingston_001
```

`execute` refuses to submit unless:
- the manifest hash matches,
- `PREREGISTRATION.md` is unchanged since prepare,
- the bundle has never been executed,
- the circuits touch only qubits 1, 2, 3 and 16,
- the time estimate is within 45 s.

It writes `job.json` immediately after submission, then `counts.json` and `assessment.json`. Commit the whole bundle afterwards, whatever the outcome.

Use `prepare --fake` to rehearse offline against the FakeKingston snapshot.
