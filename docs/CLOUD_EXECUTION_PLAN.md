# H100 validation and project spending policy

Prepared 2026-10-09 against the completed v3 audit. **No cloud instance has
been created. This document authorizes no billable operation.** The earlier
`experiment_plan_v3.json` is retained as a historical proposal; this plan
governs the next cloud decision.

## Baseline and local evidence

Use WSL `Ubuntu-26.04`, Conda `spectrans-3d` at
`/home/manager/miniforge3/envs/spectrans-3d`, and the checkout at
`/mnt/c/Users/amitb/Documents/SpectraNS-3D`. All original sources, 46 supplied
files, archives, manifests and completed evidence remain preserved. Preparation
evidence is in `artifacts/cloud-preparation/2026-10-09/`, including pre-edit
launcher/configuration copies. Frozen core hashes:

| Source | SHA256 |
| --- | --- |
| ns_fast_v2.py | 6f01107b931b80231e27336faeae94b51916d91861473f46e85aedbba0bdaf5d |
| ns_fast_v3.py | ab9eebda2750c7be019d3c2f54fe7aa5f2be98a0276a55260e35a81989b34842 |

The original 42 tests pass. New tests cover financial refusal, API endpoint
restrictions, pagination, secret redaction, termination evidence, reproducible
payloads and corrupted numerical artifacts. Eight N32 CPU/CUDA reference cases
pass locally: two ICs, two integrators, both precisions. All eight float64
N128/N256 smoke cases pass the artifact gates on the RTX 5090. These are local
implementation checks; **H100 validation remains pending**.

The first float32 N128 attempt failed: SSPRK3 TGV had a 1.23% interval
dissipation residual, above the proposed 1% threshold. Small energy decrements
are sensitive to accumulated state rounding. Failed results and initial policy
are retained. Float64 smoke state resolves this failure with the same energy
gate. Float32 remains in backend reference checks. Do not change thresholds
after seeing H100 results merely to obtain a pass.

## Historical N1024 memory

`tubes_N1024_nu5e-4.csv` contains 101 rows ending at t=1 and wall time
2260.55 seconds. Peak PyTorch **allocated** memory was 80.09129472 decimal GB
=74.59083 GiB. Archived driver output reports 81559 MiB=85.52081 decimal GB.
Allocation alone occupied **93.65%** of capacity, leaving at most **5.42952 GB
/ 5.05663 GiB**, before allocator reservations, CUDA context and external
FFT workspace. The idle driver snapshot was taken after execution and is
not a peak measurement. Peak reserved and driver-used memory are unknown.

This original SSPRK3 run is not an exact v3 reference with new spectra and
enstrophy diagnostics. Completion establishes one historical configuration
worked, not safe future headroom. The 80% limit on that reported device is
68.41665 GB, already below historical allocation. No N1024 run is justified.
Measure allocated, reserved and driver-used peaks for the actual source, GPU,
precision, integrator and complete diagnostics. Cubic extrapolation from a
lower grid is only screening evidence, not certification.

## Spending and approval

The ceiling is **$30 total project expenditure**, including previous/future
GPU, storage, bandwidth and other project charges. The user reports about $8
spent and $17.67 credit. About $22 would remain under the ceiling if the spend
estimate is exact; funding is a separate constraint. The ledger intentionally
leaves exact previous spend and pending-charge bounds unset.

Before provisioning:

1. Identify every project instance and volume, including destroyed resources.
   Archived ID 55132133 is incomplete inventory evidence. Reconcile complete
   per-contract charges over the entire project lifetime, including GPU/disk/
   transfer and conservative bounds on unposted charges. Sum parent totals
   once, not parent plus child breakdowns. Top-ups are not expenditure. Record
   evidence and UTC time in `configs/project_budget.json`.
2. Verify a current single H100 SXM 80 GB offer, GPU+selected disk rate <=$2/h,
   all noncompute charges <=$0.25, sufficient CPU/RAM for references, x86_64,
   and a driver compatible with the pinned CUDA 13 stack. Record offer ID,
   image digest, disk size, transfer rates and cost bounds. The historical
   CUDA 12.4 driver is not a valid current-runtime assumption. No current
   offer has been verified.
3. Obtain explicit user approval for that quote and **at most $1 all-in** for
   the complete smoke campaign. At $2/h, 20 minutes costs $0.66667; with a
   verified $0.25 noncompute bound, total exposure is $0.91667. Setup, idle
   time, downloads and cleanup count toward those 20 minutes. If dependencies
   or transfers cannot fit, do not provision under this plan.
4. Require previous + pending + other commitments + new cap <=$30. Bind
   approval to the ledger hash and all execution sources/tests/criteria.
   `h100_approval.template.json` is not approval.
5. Prepare and test an independent termination controller or attended operator
   procedure before provisioning. Before compute, record an armed external
   guard for the actual instance ID and a destruction deadline no later than
   provider creation +1200 seconds. Compute ends at least 120 seconds earlier
   for artifact collection. No reliable guard/collection path means no run.

`cloud_policy.py` refuses execution on missing, stale, nonfinite, unauthorized
or over-budget inputs. It does not enforce a provider billing cap or create
instances. A subprocess timeout cannot stop provider billing. Download/hash-
verify artifacts before destroying the instance, then verify its absence and
reconcile final charges before another commitment. Stopping alone leaves
storage charges; destruction deletes instance data.
[Vast lifecycle documentation](https://docs.vast.ai/guides/instances/manage-instances).

## Read-only discovery and local key storage

`vast_readonly.py` allows only GET instances, GET charges and optional POST
offer search. There is no provisioning, management, execution or deletion
endpoint. It follows pagination, refuses redirects and outputs selected
nonsecret fields. No credential is currently configured, so live account/API
behavior remains untested. The saved unavailable-credential report is not a
live inventory.

Create a temporary scoped key locally in Vast. Start with `instance_read` and
`billing_read`, and confirm charges access. Offer search belongs to `misc`,
which also includes serverless mutations; granting that entire category is
not strictly read-only. Prefer manual offer discovery or a verified narrowly
scoped search permission. Do not grant write categories to discovery.
[Permission reference](https://docs.vast.ai/api-reference/permissions).

In a WSL terminal, never in chat:

```bash
conda activate spectrans-3d
cd /mnt/c/Users/amitb/Documents/SpectraNS-3D
python scripts/vast_readonly.py --configure-key
python scripts/vast_readonly.py --output artifacts/cloud-preparation/vast-discovery-001.json
# Only with confirmed search permission; use a new output path:
python scripts/vast_readonly.py --include-offers --output artifacts/cloud-preparation/vast-discovery-002.json
```

Configuration uses hidden input and stores the key at
`/home/manager/.config/spectrans-3d/vast-readonly.key`, permissions 0700/0600
for directory/file. It stays outside the repository and GPU payload and is
never a command argument. Revoke it afterward; keys do not expire by default.
[Authentication](https://docs.vast.ai/api-reference/authentication).
Charges default to the full account history. Any `--charges-from YYYY-MM-DD`
must cover the entire project. Review project attribution and unrelated usage;
the utility does not automatically assign costs.
[Charges API](https://docs.vast.ai/api-reference/billing/show-charges).

## Smoke procedure and numerical criteria

Prepare the deterministic tar with `prepare_h100_bundle.py`; verify its SHA256
before transfer and `payload_manifest.json` after extraction. It contains
source, tests, public configs, docs and pinned environment files, excluding
historical archives/results and credentials. Install the exact validated
dependencies and package. Record actual image/driver/runtime; re-audit any
necessary runtime substitution before campaign execution.

Run tests and eight N32 CPU/H100 reference cases, then four N128 cases and
four N256 cases. N128 must pass before N256 starts. Smoke settings: TGV and
legacy tubes, SSPRK3/LSRK4, **float64**, nu=5e-4, t=.05, max_dt=.002, CFL=.2,
diagnostics/full spectra every .01, spectrum_slab=4, enstrophy identity CSV.
No field snapshots are requested; adding them changes the memory signature.

| Gate | Acceptance |
| --- | --- |
| N32 CPU/H100 velocity | Relative L2 <=2e-5 / 2e-11; max absolute <=1e-5 / 2e-12 for float32 / float64 |
| CPU/H100 E,Z,wmax | Relative error <=2e-5 / 2e-11 |
| Instantaneous energy | abs(dE/dt+eps) <=2e-6 E+2e-5 eps / 1e-11 E+2e-10 eps |
| Smoke dissipation | Interval energy rise <=1e-5 E0; total rise <=1e-4 E0; finite-difference dissipation residual <=1% |
| Divergence | Maximum absolute <=1e-4; retain the trajectory |
| Spectra | Tail ratio <=1e-6; all shells at t=0,.01,.02,.03,.04,.05; Parseval relative error <=2e-6 |
| Integrators | Matched E,Z,wmax,BKM relative difference <=5e-4 |
| Repeats | N32 trajectory within precision-specific velocity tolerance; shell spread <=2e-12 E |
| Memory | Smoke allocated/reserved <=8 GB and <=80% capacity; sampled driver-used <=80% |
| Completion | Exact approved config/hashes/times, finite diagnostics, complete manifests; no watchdog/timeout failure |

Criteria are in `configs/h100_acceptance.json`, fixed before H100 data.
N32 is backend equivalence only. Tail is a cutoff-shell heuristic, not grid
convergence. A short smoke cannot certify later stretching peaks or a continuous
BKM integral. Reproducibility means declared tolerances, not guaranteed bitwise
identity across hardware.

On an already explicitly approved H100, with a real approval record:

```bash
python scripts/launch_h100_smoke.py  # plan only
python scripts/launch_h100_smoke.py --execute \
  --approval-record artifacts/approved-h100.json \
  --budget-ledger configs/project_budget.json --output artifacts/h100-smoke-001
```

The launcher saves exact commands/parameters, all source hashes, per-run runtime
and memory manifests, scalar/enstrophy CSVs, full spectra, CPU/H100 comparisons,
one-second driver memory/utilization/power samples, approval/ledger/criteria
copies, failure/timeout evidence, and a SHA256 artifact inventory. A compute
pass remains `termination_pending`. Never populate approval flags without
actual user authorization.

After downloading/verifying artifacts and destroying the provider instance,
take a fresh complete read-only listing and run locally:

```bash
python scripts/record_cloud_termination.py --campaign artifacts/h100-smoke-001 \
  --provider-snapshot artifacts/cloud-preparation/vast-after-destroy.json \
  --artifact-download-evidence 'Local downloaded artifact manifest verified; destruction receipt/time recorded'
```

This verifies instance absence after compute and downloaded hashes, preserving
the pending record. It does not delete resources. Reconcile final charges
separately. This artifact/lifecycle contract applies to every later GPU campaign;
larger grids require a separately reviewed launcher.

## Conditional scientific follow-up

No N512/N768/N1024 simulation is authorized or launched. After successful H100
smoke, use measured throughput, memory and remaining budget for the final
recommendation. The leading single experiment is a **paired time-step
convergence study: legacy tubes, N512, nu=5e-4, LSRK4, t=1, max_dt=.0005 and
.00025**, with matched .01 diagnostics, full spectra and stretching/enstrophy
budgets. This viscosity has historical N512/N1024 comparison evidence and
acceptable historical tails, unlike the more underresolved lower-viscosity
cases. The pair isolates temporal sensitivity of extreme vorticity before
spending on bigger grids or viscosity fits.

Predeclare [0,1], compare E,Z,wmax and sampled cumulative BKM at every matched
time with a <=0.5% temporal screening target, retain the energy/divergence/tail
gates, and assess enstrophy-identity consistency. Historical ~1.81% maximum
matched-time wmax difference at N512/N1024 is context, not same-source grid
certification. Temporal convergence alone cannot distinguish every artifact
or establish spatial convergence, regularity or reconnection.

Propose at most **$2 all-in** only if measured timing/transfer bounds and the
reconciled $30 ledger permit it. A separately approved N512 preflight must
first exercise the exact precision/diagnostics and meet <=80% memory limits;
it is itself an N512 run requiring a separate go decision. If gates fail,
do not run the pair. N768/N1024 remain blocked pending independent spatial
convergence, exact-configuration headroom evidence and new approval.
