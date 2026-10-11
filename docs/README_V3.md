# Candidate v3 usage

Original files are preserved under `data/original/`. The active frozen v2
core is copied byte-for-byte into `src/`; v3 imports it from there.
Read [AUDIT_V3.md](AUDIT_V3.md) for findings and limits. This candidate is
validated locally on small grids; H100 and high-Re studies are pending.

## Reproduce the local checks

In the user's WSL Ubuntu-26.04 environment:

```bash
cd /home/manager/spectrans-3d
conda activate spectrans-3d
export PYTHON=python
CHECK_LOCAL_GPU=1 bash scripts/validate_v3.sh
```

Use any Python environment with PyTorch, NumPy and pytest, by changing
`PYTHON`. Install this project into the environment with `python -m pip install
--no-deps --no-build-isolation -e .` before running scripts. Validation
scripts do not install packages.
Omit `CHECK_LOCAL_GPU=1` to omit the extra N32/N64 GPU study; pytest still
runs tiny CUDA tests when CUDA is present and reports skips otherwise.
Set `CUDA_VISIBLE_DEVICES=""` for strictly CPU-only tests.

Each script run gets a fresh timestamped output directory. Solver output files
must not already exist; reruns must use a fresh directory. Baseline v2 tests
are included. `scripts/verify_provenance.py` checks the 46 original supplied files.
`artifacts/pre-layout/validation_v3/verified/` contains the final recorded run; earlier logs are
retained for traceability.

## A CPU experiment

```bash
"$PYTHON" -m ns_fast_v3 --case tgv --N 32 --nu .00625 --fp64 \
  --device cpu --scheme lsrk4 --target_t .05 --max_dt .005 --log_dt .01 \
  --csv my_run/scalars.csv --spectrum_csv my_run/spectrum.csv \
  --spectrum_stride 1 --budget_csv my_run/enstrophy.csv \
  --snapshot_times .03,.05 --snapshot_dir my_run/snapshots
```

Scalar CSV columns retain v2 order and definitions. Each run adds a
`<csv>.json` manifest with source hashes, parameters, runtime, status,
memory peaks and snapshot count. `--max_steps` stops early with exit code 2
and `stopped_max_steps`, unless the target time is also reached.
Watchdog failures and exceptions also return a nonzero code and retain a
failure manifest. Existing output files are never silently overwritten.

v3 defaults to CPU. It clips timesteps to diagnostic and snapshot events so
schemes can be compared at identical physical times. This changes adaptive
step histories relative to historical v1/v2 runs. BKM still uses diagnostic
samples, not every accepted step. Blank energy residuals denote an undefined
relative residual when dissipation is zero.

Spectra contain mean kinetic-energy **shell sums**, including all shells up
to the full grid diagonal; the inherited column name is retained for
compatibility. They are not averages over the number of modes in a shell.
The `--spectrum_slab` setting applies to both tail and complete spectra.

Snapshots store `omega[component,x,y,z]`, explicit coordinates, original and
sample spacing, source grid size, requested and actual accepted times, and
the original state precision. Use stride 1 for complete fields. Larger
strides use unfiltered sampling and can alias geometry. They do not certify
topology. Optional enstrophy budgets require extra memory and compute.

## H100 preparation (not executed)

```bash
"$PYTHON" scripts/launch_h100_smoke.py > h100_plan.json
```

This only prints the eight planned N128/N256 commands. The launcher has no
cloud provisioning API. On an already authorized H100, execution requires
`--execute --approval-record <json>`. The approval record must document the
actual user's approval and contain `approved: true`, `approval_note`,
`max_additional_usd`, and `hourly_rate_usd`. No approved record is supplied.
The launcher runs tests, compares both integrators at N128, and advances to
N256 only if the declared gates pass. It reserves 20% of the approved amount
for cleanup in its active-compute timeout calculation. The operator remains
responsible for tracking idle charges, collecting artifacts, terminating the
instance and verifying termination externally.

See [experiment_plan_v3.json](../configs/experiment_plan_v3.json) for the ranked next
experiments, proposed ceilings and predeclared thresholds. Its historical
$30 total ceiling is provisional; exact prior spend and the current hourly
rate must be confirmed before approving a new run.

N>=768 requires `--allow_large_grid`. N>=1024 additionally requires a v3
`--memory_reference` JSON manifest from a same-source N>=768 run with at
least five steps, matching scheme, precision, GPU model, runtime, IC and
enabled diagnostics. Requested snapshots must have been exercised. The
scaled maximum allocated/reserved memory must fit within 80% of both total
and currently free GPU memory. `--preflight_only` checks without constructing
a solver. A passed extrapolation is still not an OOM guarantee. The old
33.8 GB SSPRK3 observation and historical 80.09 GB N1024 result are not valid
v3 memory references. A separate approved go decision is required for the
planned N1024 stage; the provided smoke launcher never launches that grid.
