# Pre-registration: a quantum spectral advection step on ibm_kingston

Written October 14, 2026, before any hardware submission. The commit that adds this file is the pre-registration record. The runner binds this file's SHA256 into every bundle and refuses to execute if the file has changed since the bundle was prepared. Results will be published whether or not the predictions hold.

## Question

SpectraNS-3D found that integral quantities survive grid refinement while local vorticity peaks do not, and that two runs agreeing with each other can still both be wrong. This experiment asks the same question with a different error source: **on real quantum hardware, which outputs of a Fourier spectral step survive the noise?**

## What this does and does not claim

This is a small methodology experiment. It runs one linear advection step on a 16-point periodic grid, which a laptop computes exactly. It demonstrates no quantum advantage and says nothing about Navier–Stokes regularity, blowup, nonlinearity or three-dimensional flow. It is not a response to, or a test of, OpenAI's analytical result, which no hardware experiment could test. Its value is limited to an honest, reproducible measurement of how observable types degrade on a current device, scored against predictions fixed in advance.

## Circuit

Four qubits amplitude-encode a 16-point profile ψ_j ∝ exp(2 cos(x_j − π)) on x_j = 2πj/16. This von Mises bump is well resolved on the grid: modes with |k| ≥ 6 carry 4.6×10⁻⁷ of its norm. One pseudo-spectral advection step is a quantum Fourier transform, then a phase exp(ikφ) on each mode with φ = 2πs/16 (applied as four single-qubit phase gates, since k is linear in the bits), then the inverse transform. This is the structure SpectraNS-3D uses for linear terms, and pure advection is unitary.

| Item | Value |
|---|---|
| Shifts s (grid cells) | 0, 1.5, 3.5, 5.5. Half-integer shifts make the result genuine Fourier interpolation, not a relabelling of grid points |
| Measurement bases | Position (gives \|ψ_j\|²) and spectral (one more QFT before readout, gives \|a_k\|², which advection must leave unchanged) |
| Readout calibration | \|0000⟩ and \|1111⟩, for a tensored per-qubit correction |
| Circuits | 4 shifts × 2 bases + 2 calibration = 10 |
| Shots | 4096 per circuit, 40,960 total |
| Backend and qubits | ibm_kingston, physical qubits 1–2–3–16 (a linear chain), chosen by the v6 backend audit before this design |
| Transpilation | optimization level 2, seed 7; barriers prevent cancelling QFT against its inverse; circuits must touch only qubits 1, 2, 3 and 16 |
| Error suppression | None: no dynamical decoupling, no twirling. Only the tensored readout correction, used solely in P4 |
| QPU time | Estimated about 15–20 s. The runner refuses to submit if its estimate exceeds 45 s, and the job carries a hard 60 s max_execution_time |

## Observables

- **Centroid** (integral-type): circular mean of the position distribution, in cells. Exact values are 8.0, 9.5, 11.5 and 13.5. Depolarizing noise cannot move it, but readout bit-flips permute outcomes and can. P1 is scored on raw counts, so it includes that effect.
- **Peak height** (local): the largest position probability. At half-integer shifts the true peak lies between two cells; peak *location* is therefore not scored.
- **Spectral distribution**: the four spectral-basis measurements should be identical in exact arithmetic.
- **Noise-calibrated peak**: the shift-0 circuit has a known answer and the same gate structure as the others. Fit a single depolarizing parameter ε to it (after readout correction), p_noisy = (1 − ε)p_exact + ε/16, then use that ε alone to correct the other three peaks. No exact answer for shifts 1.5, 3.5 or 5.5 enters the correction.

## Predictions and pass criteria

Each is scored on point estimates from the raw counts, except P4 as stated. 95% multinomial bootstrap intervals (2000 resamples, fixed seed) and the fraction of resamples passing each criterion are reported alongside.

| | Prediction | Pass criterion |
|---|---|---|
| **P1** | The integral observable survives | Centroid error ≤ 0.25 cell at every shift |
| **P2** | The local observable is biased | Raw peak height at least 5% below exact at every shift |
| **P3** | Runs agree with each other more than with the truth | Smallest spectral TVD from exact exceeds the largest TVD between any two shifts, and is at least 0.05 (so the inaccuracy is material, not rounding) |
| **P4** | A known-answer twin calibrates the local bias away | Corrected peak within 7.5% of exact at shifts 1.5, 3.5 and 5.5 |

P1–P3 restate the SpectraNS-3D pattern under hardware noise. P4 is the one that could plausibly fail: real devices have coherent and correlated errors that a single depolarizing parameter cannot capture.

## How the thresholds were chosen (disclosure)

The thresholds were set after a noisy simulation using the FakeKingston calibration snapshot shipped with qiskit-ibm-runtime 0.50.0, over five sampling seeds on this exact circuit set. In simulation:

- Centroid error was at most 0.084 cell.
- Raw peaks were 11–18% low.
- Twin-calibrated peaks were within 6% of exact.
- Spectral runs agreed with each other within TVD 0.043 while sitting at least 0.139 from exact.

Each threshold leaves margin over those values. P4 is marginal even so: in the offline FakeKingston dry run through the final runner, it passed on the point estimate but in only 67% of bootstrap resamples, while P1–P3 passed in all of them. It is kept as pre-registered rather than loosened. One criterion changed during offline testing, before any hardware access: P3 gained its 0.05 floor after a noiseless synthetic test showed that the bare inequality could be decided by rounding. That snapshot is not today's calibration, and simulated noise omits effects the hardware has, which is why the hardware outcome remains open. The runner repeats this dry run with the backend's current calibration before submission and records it.

## Procedure

1. `prepare` (read-only): transpile, freeze circuits as QPY with a manifest, estimate QPU time, run the noisy-simulator dry run from current calibration. No job is submitted.
2. `execute`: AB submits one job, only if the manifest hash matches, the bundle is unexecuted and the estimate is within budget.
3. `analyse`: offline scoring against exact references and P1–P4.

The bundle, job ID, counts, QPU usage, dry run and assessment are all committed afterwards, including any failed prediction. A failed or cancelled job is reported as such; any rerun needs a new bundle, and both are reported.
