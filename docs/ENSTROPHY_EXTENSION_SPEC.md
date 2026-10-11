# Bounded N512 enstrophy extension

This fixed specification uses the immutable audited v2/v3 solver and its legacy tube IC.
The N512 t=1 field was not saved, so the trajectory is recomputed from the original IC.
The last eleven enstrophy budgets show positive late curvature; the final net-production
difference divided by 0.01 is about 1.933264. This is sampled curvature, not a prediction
of the peak location.

N512, float64 LSRK4, nu=0.0005, CFL=0.2, timestep cap 0.0005.
Hard maximum simulated time is 3. Diagnostics and full spectra occur every 0.01.
Each step records actual dt, maximum velocity, cap, CFL/viscous bounds and limiter.
Each diagnostic records instantaneous production minus viscous loss and the k>=128
viscous-enstrophy-loss share using rounded-shell centers plus within-shell bounds.

Stop at the first numerical gate failure. A tail trip is an expected bounded result;
the failed diagnostic is preserved and the previous accepted diagnostic is reported.
Passing a heuristic spectral gate is not a spatial-convergence certificate.
A different failed gate is a campaign failure. There is no automatic retry.
Turnover requires a positive-to-nonpositive instantaneous net-production crossing.
After crossing, continue until a 1% decline from the sampled Z maximum OR 0.1 time
units after the first nonpositive event, subject to every other cap and gate.
Peak time is diagnostic-sampled; the crossing is reported as a bracket.

Full Fourier-state restart checkpoints are written every 0.1. Two latest regular
checkpoints and the terminal state are retained, bounding full-field storage at
about 9.71 GB. Hash records remain for discarded earlier fields. The terminal
checkpoint may contain a gate-failing state and is labelled accordingly; restart
comparisons use an accepted regular checkpoint, never the failing terminal state.
Checkpoints use non-pickle NumPy arrays with component hashes, metadata, physics,
audited sources, checkpoint-driver hash and exact runtime. Residual arrays can be
reset because the first LSRK4 stage has zero residual coefficient. Corruption,
runtime/grid/precision/physics/source mismatches are refused.

Repeat the last accepted 0.05-0.2 time-unit window at cap 0.00025 from the identical
coarse checkpoint. Compare E, Z, sampled maximum vorticity, accumulated BKM, net
production scaled to production/loss, and full spectra. Scalar and spectrum
limits remain 5e-4, effective step-count ratio must be >=1.25. This measures local
continuation error; common inherited pre-window temporal error is not measured.
Fine-grid restart transfer is not implemented. A fine grid from a coarse checkpoint
would be a separate transfer experiment, not full-trajectory grid convergence.

Before billing: all tests; verified prior 89-test N512 campaign; fresh billing;
actual H100 offer, driver compatibility, transfer/disk price; source payload hashes;
validated immutable-image bootstrap; independent local destruction guard.
On GPU: all tests, eight CPU/H100 references, same-stack N512 checkpoint save/reload
preflight and live 1-second driver memory trace at <=80%, followed by the bounded
trajectory and terminal temporal window. Recomputed [0,1] scalar values must match
the preserved baseline at 5e-4.

All-in commitment <=$4, total project exposure <=$30, GPU+80GB disk <=$3/hour,
provider lifetime <=4200 seconds (70 minutes), including setup/collection/cleanup.
Transfer quotes bind <=14GB incoming and <=12GB outgoing to the $0.50 reserve.
The time cap may prevent reaching t=3; reaching turnover is not promised.
No N640/N768/N1024 runs are permitted by this specification.

Results include exact configuration, original IC defaults and spectral conventions,
all commands, runtime versions, source/control hashes, diagnostic/full spectra CSVs,
every achieved dt, checkpoint inventory, driver memory trace, bounded stop reason,
temporal-window agreement, transfer receipts, and provider destruction verification.
Raw evidence remains in native WSL; only selected reports are exported to Windows.

## Deliberate correction after closed attempt 55299122

The first attempt passed 105 GPU tests and backend references but failed before
simulation because the new wrapper passed an unindexed CUDA device to set_device.
Its instance is destroyed and all logs/payload remain preserved. The wrapper now
resolves the current CUDA index; a local mock test covers bare/explicit CUDA and CPU.

The corrected retry is capped at USD 3, GPU+disk <=USD 2.10/hour, and <=4200 seconds.
First-attempt lifetime+noncompute upper bound is USD 0.727427; combined committed
upper bound is USD 3.727427, below the original shared USD 4 extension ceiling.
No programmatic retry mechanism is present and no numerical gate was changed.
