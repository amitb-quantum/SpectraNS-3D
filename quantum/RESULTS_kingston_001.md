# Results: kingston_001 on ibm_kingston

October 14, 2026. Job `db7s9kor1c5c738l705g`, submitted 18:07 UTC, **13 s of QPU time** (estimate 15.6 s, cap 60 s). The bundle in this folder is unedited: circuits, manifest, job record, counts, dry run and assessment exactly as the runner wrote them. The predictions were fixed in [PREREGISTRATION.md](../../PREREGISTRATION.md) before submission.

![Measured versus exact distributions and in-job readout calibration](results.png)

## Verdicts

| | Prediction | Result | Value (95% bootstrap interval) | Threshold |
|---|---|---|---|---|
| **P1** | Integral centroid survives | **PASS** | max error 0.080 cell, at shift 5.5 (0.017–0.144) | ≤ 0.25 |
| **P2** | Local peak biased low | **FAIL** | least-low peak **+7.6%** at shift 1.5 (+2.7% to +12.6%) | ≤ −5% |
| **P3** | Runs agree more with each other than with truth | **PASS** | pairwise TVD 0.027 vs 0.253 from exact | min TVD from exact > max pairwise, and ≥ 0.05 |
| **P4** | Twin calibration recovers the peak | **FAIL** | worst corrected peak **+31.6%** at shift 1.5 (+22% to +42%) | within ±7.5% |

All four verdicts are the same in every bootstrap resample (P1 and P3 in 100%, P2 and P4 in 0%).

## What happened

**Physical qubit 1 had a severe readout fault during the job.** The in-job calibration circuits measured it reading |1⟩ for a prepared |0⟩ **28.1%** of the time, and |0⟩ for |1⟩ 11.7%. The other three qubits were at 0.2–3.5%. The pre-run backend audit, using the 17:27 UTC calibration, had estimated the readout contribution for the *whole* four-qubit path at about 5.5%. The dry run, which builds its noise model from that same calibration, could not have anticipated a fault of this size.

Qubit 1 holds the lowest bit of the cell index, so the fault moves probability from even-numbered cells into odd-numbered ones. At every half-integer shift, the two cells that should be equal (0.280 each) came out lopsided, with the odd cell winning: 0.301 vs 0.170 at shift 1.5, 0.254 vs 0.177 at 3.5, 0.278 vs 0.163 at 5.5. At shift 0, the argmax moved from cell 8 to cell 9. A rigid displacement plus uniform depolarizing noise cannot produce this: that model predicts every peak about 13–15% low, including +7.6% → −13.9% at shift 1.5.

**P2 failed because the error was structured, not because the device was cleaner.** The fitted depolarizing strength was *higher* than in the dry run (ε = 0.19, interval 0.16–0.22, vs 0.14). The local peak was not merely biased low. Its error took either sign depending on where the fault pushed probability: −22.7% at shift 0, +7.6% at 1.5, −9.0% at 3.5, −0.7% at 5.5.

**P4 failed because a one-parameter correction amplified structured error.** Tensored readout correction restores qubit 1's balance (its marginal returns to 0.476–0.511, against an exact 0.50). But the twin cells stay lopsided afterwards (0.310 vs 0.236 at shift 1.5), so some asymmetric error is gate-level or correlated readout, not captured by a per-qubit model. Fitting one depolarizing ε to the shift-0 circuit and dividing it out then inflates an already high peak: +11% after readout correction becomes +32%. The correction does not reproduce even its own calibration circuit's peak (+7.4%).

**P1 and P3 held despite the fault.** The centroid stayed within 0.08 cell at every shift, as it was predicted to: a whole-profile average is insensitive to how probability is redistributed locally. The four spectral-basis runs agreed with one another to a TVD of 0.027, yet each was 0.25 from the exact distribution. The noise was reproducible, so the runs were consistent, but they were consistently wrong.

## What this shows, and what it does not

The SpectraNS-3D three-grid study found that integral quantities converge while local peaks do not, and that two agreeing runs can share the same error. This run reproduces that pattern under a different error source, and adds one thing the grid study could not show: **a local observable's error can change sign, and a correction calibrated on a known-answer twin can make it worse when the error model is wrong.**

It does not demonstrate quantum advantage; a laptop computes every exact value here. It says nothing about Navier–Stokes regularity or blowup, and nothing about OpenAI's analytical result. It characterizes one device, one path and one job. Whether P2 and P4 fail on a path without a faulty qubit is an open question this run cannot answer.

## Disclosures

- Before seeing the numbers, I guessed in conversation that P2 had failed because the device was cleaner than the dry run assumed. The data show the opposite. The guess is recorded here because it was wrong.
- The bootstrap interval for the maximum pairwise spectral TVD (0.034–0.059) lies above its point estimate (0.027). Resampling adds sampling noise to each distribution, and a maximum of TVDs is biased upward by it. P3 passes in every resample regardless.
- The dry run passed all four predictions, with P2 in 84% and P4 in 43% of resamples. The pre-registration noted both as uncertain; neither threshold was changed after the bundle was frozen.

## Reproduce

```bash
python quantum/run_qpu.py analyse --bundle quantum/runs/kingston_001   # re-scores counts.json offline
python quantum/plot_results.py --bundle quantum/runs/kingston_001      # this figure; needs matplotlib
```

A replication on another path would be a new experiment: a new bundle, an addendum to the pre-registration naming the path before submission, and both runs reported together.
