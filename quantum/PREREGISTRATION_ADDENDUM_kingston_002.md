# Pre-registration addendum: replication run kingston_002

Written October 14, 2026, after [kingston_001](RESULTS_kingston_001.md) and before any kingston_002 submission. The commit adding this file is its pre-registration record. The runner binds this file's SHA256 into the kingston_002 bundle, alongside the original [PREREGISTRATION.md](PREREGISTRATION.md), and refuses to execute if either has changed.

## Why a replication

In kingston_001, P1 and P3 passed and P2 and P4 failed. The in-job calibration traced the failures largely to physical qubit 1, which misread |0⟩ as |1⟩ 28.1% of the time. That fault may not be isolated: FakeKingston's April 2026 calibration snapshot already lists 16.8% readout error for qubit 1. The question here is narrow. **Do P2 and P4 still fail on a path whose qubits have no such fault?**

This replication was motivated by the first run's outcome. That is disclosed here. To limit the freedom that creates, the path is chosen by a rule fixed before submission, and nothing else changes.

## What changes

Only the physical qubits: **[100, 101, 102, 103]**, a linear chain. The rule is: the best-ranked robust path in AB's v6 backend audit (calibration 2026-10-14 17:27 UTC) that does not contain physical qubit 1. This path ranked second overall (robust, estimated circuit error 11.06%). It shares no qubit with kingston_001's path [1, 2, 3, 16].

## What does not change

Everything else in [PREREGISTRATION.md](PREREGISTRATION.md) applies unchanged:
- the profile, shifts, bases and calibration circuits;
- 10 circuits × 4096 shots;
- optimization level 2, transpiler seed 7, no twirling or dynamical decoupling;
- the 45 s budget guard and 60 s hard cap;
- predictions **P1–P4 with identical thresholds**, scored the same way.

## Additional reporting rule

The assessment records each qubit's in-job readout error. Any qubit misreading more often than 10% in either direction is **flagged**. A flagged run is still reported in full, and its verdicts stand; the flag only marks that a readout fault of the kind seen in kingston_001 recurred, which limits what the run can say about the replication question.

## What would count as an answer

- **P2 passes and no qubit is flagged:** consistent with kingston_001's P2 failure having been driven by the qubit-1 fault.
- **P2 fails again and no qubit is flagged:** the sign-changing local error is not explained by that fault alone.
- **Any qubit flagged:** the run does not cleanly answer the question, and is reported as such.

P4 was uncertain even before kingston_001 (passing in 43% of dry-run resamples), so no outcome for P4 is treated as decisive either way.

## Commitments

- **One submission:** a single job. It is not rerun to obtain a different answer.
- **Reported together:** the results are published alongside kingston_001 in one comparison, whatever they show.
- **Rerun only for a failed job:** if the job itself fails or is cancelled, that is reported. A rerun needs a new bundle, and both are reported.
