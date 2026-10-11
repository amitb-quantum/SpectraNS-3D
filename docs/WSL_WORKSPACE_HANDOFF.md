# Native WSL workspace and validation handoff

The authoritative checkout is /home/manager/spectrans-3d.
The dedicated Conda environment is /home/manager/miniforge3/envs/spectrans-3d.
Windows Documents is the preserved baseline and selected-report destination.
All 46 supplied original files verify unchanged; the two audited solver hashes
remain unchanged. Historical sources, manifests and invalid-run evidence remain.

The H100 baseline campaign 55275939 passed the original 76 tests, eight N32
CPU/H100 references and eight N128/N256 smoke runs. Its evidence remains preserved.

The subsequent H100 campaign **55290425** passed all 89 current tests and fresh
backend references. All three short N256/N512 preflights and both N512 full
float64 LSRK4 tube trajectories reached their requested final times and passed.
The full runs used nu=0.0005, CFL=0.2, target t=1, log interval=0.01 and timestep
caps 0.0005/0.00025. The largest scalar relative difference was 5.4357e-8.
All 41 downloaded result-file hashes were independently checked; the exact
configuration, IC defaults, full spectra, conservation budgets, runtime metrics,
driver-memory trace and verified termination record remain in:

artifacts/cloud-preparation/2026-10-10/timestep_campaign_001/

Read docs/TIMESTEP_VALIDATION_2026-10-10.md for the full scientific report.
All cloud instances are destroyed. Provider-posted project spending is
USD 15.565; the pending-charge upper reserve is
USD 0.754. The hard total ceiling is $30.
The user authorized new commitments below $10 without another permission request.

Long-time spatial convergence remains pending. The next recommended experiment
is an N640 run at the existing fine timestep cap, compared with N512 at matched
times. This is a recommendation, not a launched run. Its controls require a new
fixed execution plan, full source fingerprints, the unchanged numerical gates,
an actual same-configuration memory/runtime preflight, fresh quotes and billing,
an independent termination guard, complete collection and verified destruction.
Current follow-up controls authorize only N256/N512. N768/N1024 have not run.

Development and raw evidence stay in native WSL. Selected final reports are
exported to Windows artifacts/wsl-exports/2026-10-10/timestep-followup/.
Do not rebind the editable package to Windows or upload local credentials.

## Latest bounded enstrophy extension (2026-10-10 PT)

Corrected H100 campaign 55300356 completed tests (107 on GPU), backend references
and same-grid checkpoint reload. The original [0,1] scalar samples reproduced
exactly. Its N512 coarse continuation stopped at the unchanged tail gate at
t=1.11 (1.017345e-6 > 1e-6); last accepted diagnostic is t=1.10.
At that endpoint Z=1.948552179 and net production=+1.734723426: no enstrophy
turnover was reached. The sampled net-production maximum is t=1.08.

The identical-checkpoint t=1.00-1.10 cap-0.00025 comparison passed: maximum scalar
difference 2.53003e-8; spectra L1/E difference 4.07482e-12. This tests local
continuation error only, not accumulated temporal error or spatial convergence.
Full restart fields at t=1.00 and 1.10 are accepted regular checkpoints.
The terminal t=1.11 field is preserved as failing-gate evidence. Earlier
checkpoint hashes remain, but discarded earlier fields cannot be restarted.

The first attempt 55299122 failed before simulation due to a new wrapper's
missing CUDA device index; logs, sources and charges are preserved. The corrected
startup is tested. All 46 original supplied files and both audited solver hashes
are unchanged. After a post-run pending-reserve bookkeeping correction, the
current local suite passes 108 tests. This differs from the 107-test GPU snapshot.

Lossless alternative collection secured all 53 original GPU hashes and all nine
retained arrays; the advanced termination inventory contains 54 files. The raw
uncompressed transfer was redundant and interrupted only after exact recovery.
Both instances are destroyed and complete provider listings show no instances.
Posted extension charges total USD 1.777. Project posted total is USD 17.437,
pending upper reserve USD 1.277, uncommitted headroom USD 11.286, ceiling USD 30.

Read docs/ENSTROPHY_EXTENSION_2026-10-10.md and native evidence:
artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/
Selected reports/data are exported to Windows:
artifacts/wsl-exports/2026-10-10/enstrophy-extension/

Next proposal: one N640/H100 run from original IC, cap 0.0005, bounded t=1.5
with unchanged gates and a short cap-0.00025 terminal comparison, suggested
all-in cap USD 5. It requires a separate fixed plan, actual N640 memory/runtime
preflight, fresh quotes/ledger and independent termination guard. Conservative
driver forecast is 56.88GB, using the larger prior driver sample; actual memory
measurement remains mandatory. No N640/N768/N1024 run has been launched.
Current extension execution controls permit N512 only.


## N640 readiness review (2026-10-10 PT)

The wrapper event clock is corrected; immutable core unchanged; 119 local tests pass. Review: docs/N640_READINESS_REVIEW.md and configs/n640_refinement_proposal.json. Prior executed wrapper is archived in artifacts/cloud-preparation/2026-10-10/n640_review_001/source_before_clock_fix and matches the N512 run driver hash. New timing.json records synchronized disjoint stages. N640 remains unlaunched; the existing extension launcher remains N512-only. A separate source/config-bound launcher must enforce the reviewed USD 5 rate/deadline, measured memory/runtime and checkpoint collection controls before provisioning. No N768/N1024 authority. Historical reports and full fields are preserved.


## N640 protected-first revision (2026-10-10 PT)

The latest specification is schema 2 in configs/n640_refinement_proposal.json. Required work is original-IC coarse through 1.10, fine [1.00,1.10], primary Z/net curve assessment and hash-verified small artifacts in WSL; only then optional checkpoint/exploration up to 1.50. Use separate processes and resume the coarse 1.10 state. Grid wmax/BKM are secondary 1% screens. Bracketed 3/5-point net peak fits are supplementary with sensitivity estimates, not confidence intervals. Add same-host N512 benchmark and actual compression/transfer probes. Current 126 local tests pass; all 46 originals and both audited core hashes unchanged. No N640 GPU provisioned. Full record: artifacts/cloud-preparation/2026-10-10/n640_review_002/N640_PROTECTED_FIRST_REVIEW.md. Separate N640 controller still required.
