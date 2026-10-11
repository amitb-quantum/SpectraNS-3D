# Numerical and reproducibility audit

Prepared for the 2026-10-09 project handoff. This report distinguishes
new local checks from supplied historical H100 records.

> Layout note: this audit records the original validation before repository
> organization. Historical relative source paths below refer to the preserved
> tree in `data/original/ns_regularity_upgrade/` or `artifacts/pre-layout/`.
> Active solver modules are now in `src/`, tools in `scripts/`, and the new
> dedicated-environment validation is in `artifacts/validation/spectrans-env/`.
> The numerical solver files were copied without changes.

## Outcome

Preserve the existing rotational-form architecture. Its signs, projection,
legacy IC, and integrators pass the checks performed here. Use the separate
`ns_fast_v3.py` driver for further validation. It imports the frozen v2 core
and changes validation, event scheduling, spectra, optional diagnostics,
snapshot handling and provenance. Do not claim high-Re grid convergence,
H100 certification, reconnection, or mathematical regularity from this work.

**42 tests passed**, plus a CPU refinement study and eight small local CUDA
comparisons. No cloud instance was provisioned and no paid run was started.
Historical evidence is richer than the upgrade brief states, but still
insufficient for a physical viscosity-scaling fit.

## Preserved sources and provenance

The ZIP, two TGZs and their 43 extracted files are inventoried in
`../original_manifest.json`, hashing the archive member bytes. All 46 files
were checked unchanged and marked read-only on Windows. That attribute is
an accidental-edit guard, not tamper-proof storage. The supplied 18-entry
`SHA256SUMS` also matched on initial inspection.

| Source | SHA256 |
|---|---|
| Original audit solver | `c0bcb9c3f46e8155eb2a643703b1d32b8737dbfc6bff147170c3f9389db55448` |
| Earlier campaign solver | `bff7fad9951215649617602784bdfbf3a0f96ff0fa13e3cfff06189108134213` |
| Frozen candidate v2 | `6f01107b931b80231e27336faeae94b51916d91861473f46e85aedbba0bdaf5d` |

The earlier campaign solver differs from the audit solver in its diagnostics:
it uses float32 reductions instead of float64 reductions. The numerical RHS,
IC and RK methods match. These datasets are kept as separate source families.
Archived source association is not a runtime hash attestation. The original
logs do not record source hashes, so exact historical runtime provenance
cannot be retroactively established.

The historical system log reports PyTorch 2.4.0 / CUDA 12.4 and an H100 80GB.
The new tests used WSL Ubuntu-26.04, Python 3.12.13, PyTorch 2.13.0+cu130,
CUDA build 13.0, NumPy 2.5.1, pytest 9.1.1 and a local RTX 5090. Exact new
source hashes and runtime details are in
`validation_v3/verified/reproducibility.json`. WSL was accessed using the
[provided bridge pattern](https://github.com/amitb-gpu/wsl-agent-bridge),
with explicit distro and interpreter paths. No dependencies were installed.

## Findings and remedies

| Finding | Evidence in original sources | Treatment |
|---|---|---|
| Original viscosity damps the constant mean | `audit/ns_fast.py:30,67-68`: safe K2=1 is also used for diffusion | Fixed in v2; v3 retains it. Both RK methods conserve a constant velocity in tests. |
| Legacy prescribed x-vorticity is not divergence-free when perturbed in x | `audit/ns_fast.py:105-118` | Preserve exact velocity IC. Inverse curl reconstructs the solenoidal projection of the prescribed vector field, not the scalar x-profile alone. |
| v2 accepts some NaN/Inf and missing positive-dt constraints | `ns_fast_v2.py:248-251` | `ns_fast_v3.py:212` validates finite parameters and positive dt before allocation; constructor/get_dt validate independently. |
| v2 initial diagnostics bypass finite/tail/divergence stop checks | `ns_fast_v2.py:315-320` versus checks at `343` onward | Unified v3 record path checks t=0 too (`ns_fast_v3.py:295` onward). |
| Same-scheme memory claim is not actually verified by v2 numeric arguments | `ns_fast_v2.py:260-268` | JSON reference checks source, scheme, precision, configuration, backend and GPU, plus measured allocated/reserved peaks (`ns_fast_v3.py:154`). |
| v2 routine tail diagnostics ignore CLI spectrum slab | `ns_fast_v2.py:169,201` | v3 shared slab setting applies to all spectra (`ns_fast_v3.py:44,74`). |
| v2 snapshot creates all three spectral curl components and can retain full CPU arrays behind strided views | `ns_fast_v2.py:183-186` | v3 computes one component at a time and copies into a compact output (`ns_fast_v3.py:83`). |
| v2 snapshots omit axes/coordinate/requested-time metadata and always downcast to float32 | `ns_fast_v2.py:184-189` | Explicit metadata, preserved precision, unique output index, stride-1 full fields in v3. |
| v2 shell bins clamp high modes to overflow bin | `ns_fast_v2.py:145-149` | v3 represents all Fourier shells; direct full-complex NumPy spectrum comparison covers mean and Nyquist planes. |
| v2 logs on first crossing; one-step increments can miss desired schedule after large steps | `ns_fast_v2.py:341,361` | v3 clips accepted steps to output times (`ns_fast_v3.py:349` onward). Historical trajectories therefore need cautious comparison. |
| Existing analysis can accept nonfinite values and lacks convergence evidence for fits | `analyze_runs.py:13-47,66-82` | Separate strict analyzer rejects malformed/nonfinite data and always withholds the physical fit for these archives. |

## Numerical core audit

* **Sign and projection:** `audit/ns_fast.py:47-69` implements
  `P[u Ã— omega] - nu kÂ² u`. Since `(uÂ·grad)u = grad(|u|Â²/2) - uÃ—omega`,
  the nonlinear sign is correct. An independently written full-complex NumPy
  advective-form RHS agrees in physical space for TGV and legacy tubes
  at N24 to the declared 3e-13 absolute / 2e-11 relative tolerance.
* **Dealiasing and staging:** the strict spherical cutoff `|k| < N/3`
  applies to the IC and nonlinear RHS. Intermediate RK states remain in the
  retained solenoidal subspace in exact arithmetic; the final mask is also
  applied. This is a Galerkin truncation, not evidence that the continuum
  flow is resolved. Arbitrary unmasked input states are outside this solver's
  evolution contract.
* **FFT and spectra:** backward-normalized transforms require `1/N^6`
  for mean squared Fourier amplitudes. Kinetic energy adds the factor 1/2.
  Interior rFFT kz planes carry weight 2; zero/Nyquist planes carry 1 for the
  supported even grids. Independent random full-grid real fields verify every
  shell, including mean and Nyquist modes. Shell index temporaries scale as
  `NÂ² Ã— slab`; no full-grid int64 shell array is cached. The old N1024 shell
  array alone is approximately 4.30 GB.
* **Energy/enstrophy:** `E=.5<|u|Â²>` and `Z=.5<|omega|Â²>`. TGV initial
  values E=1/8 and Z=3/8 pass. The instantaneous energy identity is tested in
  the retained v2 suite. Optional v3 stretching production and
  `dZ/dt = P - nu<|grad omega|Â²>` pass independent NumPy gradient/production
  comparisons on both ICs. The budget is diagnostic and adds memory costs.
* **Integrator order:** exact diffusive shear gives SSPRK3 observed orders
  3.0289 and 3.0144; LSRK4 gives 4.0210 and 4.0105. Coefficients remain those
  attributed to [Carpenter & Kennedy, NASA TM-109112](https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/19940028444.pdf).
  These checks establish the measured linear-test order, not every nonlinear
  or stiff-flow stability property.
* **CFL:** `audit/ns_fast.py:71-76` uses initial-stage maximum speed and
  diffusion limits. These are practical timestep controls, not error
  estimators. v3 rejects nonfinite velocity maxima before updating the state.
  High-Re runs still need independent timestep refinement.
* **Precision:** float64 global reductions reduce summation error but cannot
  recover accuracy lost in float32 fields/FFTs. A separate TGV fp32/fp64 run
  at N24, t=.1 measured max velocity difference 1.835e-6.

## Reproduced tests and outputs

The supplied eight tests and `validate_local.sh` first passed unchanged.
`validation_v3/baseline_validation.log` records that result. Final artifacts
are under `validation_v3/verified/`:

| Evidence | Result |
|---|---|
| `tests.log` | 42 passed; no GPU tests skipped on this machine |
| `convergence.json` | Expected RK orders; N12/N24 velocity errors versus N48 TGV are 6.800e-3 / 9.105e-6 at t=.4, dt=.002 |
| `gpu_checks.json` | Eight N32/N64 Ã— fp32/fp64 Ã— two-scheme CPU/GPU comparisons; ten steps each |
| `ssprk3.csv`, `lsrk4.csv` and companion JSON | Successful CPU N32 runs to t=.05 with spectra, budget output and two snapshots each |
| `archive_summary.json` | Ten historical CSVs summarized, source families separated, physical fit withheld |
| `reproducibility.json` | All original hashes verified, new source hashes and environment recorded |

Small-grid GPU checks found maximum velocity CPU/GPU difference about
5.37e-7 and maximum Parseval relative error about 5.40e-7. Repeated spectra
agreed within about 1.4e-17 absolute shell energy in the recorded checks.
N32/N64 spectrum timing was roughly 2â€“6 ms per call including transfer of
the small output, with warmup. This is not a large-grid performance forecast.
Peak allocations in these checks were below 0.05 GB; reserved memory below
0.08 GB. These numbers cannot serve as N1024 memory references.

PyTorch distinguishes tensor allocations from allocator reservations;
both are recorded in v3. External CUDA allocations and FFT workspace
behavior still require target-device measurement. See
[PyTorch CUDA memory documentation](https://docs.pytorch.org/docs/stable/notes/cuda).
Weighted CUDA `bincount` is a known operation requiring care for deterministic
execution; repeat agreement on these cases does not guarantee bitwise
determinism across runs/hardware. See
[PyTorch deterministic-algorithm documentation](https://docs.pytorch.org/docs/main/generated/torch.use_deterministic_algorithms.html).

Development failures were retained: the initial temporal-order fixture used
a timestep exceeding the diffusion cap; fixing the fixture to N12 restored
the intended dt ratios without changing the integrators. A CUDA CLI check
found that an unindexed `cuda` device needed normalization before the memory
API; that was fixed and regression-tested. The first provenance inventory
accidentally included pytest cache entries; it was rebuilt directly from
archive members. No original source was edited to resolve these failures.

## Historical evidence and fit decision

The four audit N512 runs reproduce sampled peaks approximately 79.16,
99.62, 116.31 and 130.58 as viscosity decreases from 1e-3 to 1e-4.
Only the first two pass the 1e-6 tail heuristic. All four energies decline
at logged times. The unscreened descriptive slope remains about 0.215;
it is not a validated physical scaling exponent.

The earlier campaign archive contains a completed **N1024, nu=5e-4** CSV
and completion log (`../historical/campaign_results/results/out/campaign.log:795`).
It records about 80.09 GB peak allocated and 2261 seconds elapsed. This
corrects the impression that no historical N1024 run exists. It does not
certify a v2/v3 run or give safe future headroom. The supplied monitor log
records historical termination; current account/instance state was not queried.

Within that earlier source family, linear interpolation onto t=0:.01:1
gives maximum sampled wmax differences against N1024 of **12.49% at N256**
and **1.81% at N512**. Adaptive dt changed with N, diagnostic precision is
float32, and only scalar samples are available. This is useful evidence of
improvement, not isolated spatial convergence or a common-band field study.

The audit N768 log ends at **t=0.3309** (`audit/campaign.log`, final line),
without a completion record; no N768 CSV is supplied. A completed N768
result cannot be claimed or used. The full strict archive metrics are saved
in JSON. No viscosity has the required independent grid **and** timestep
convergence evidence here, so a physical power-law fit remains withheld.

## Next decision

Use [experiment_plan_v3.json](../configs/experiment_plan_v3.json) and the plan-only
`launch_h100_smoke.py`. First validate on an authorized H100 at N128/N256,
then recover missing N768 evidence and perform matched-viscosity grid/time
refinement. Only then measure the exact N768 configuration for a possible
N1024 preflight. The launcher supplied here cannot launch N512/N768/N1024.

Keep the current core while evidence accumulates. The independent NumPy
advective reference is useful for small-grid cross-checks; an external
independent DNS implementation would be a next research comparison, not
a necessary rewrite now. Cleaner tube ICs, antialiased/ROI geometry output,
interpolated vorticity maxima, high-grid spectrum benchmarking, uncertainty
on a validated viscosity fit, and target-device memory certification remain
future work. No reconnection or regularity conclusion follows from this audit.
