# SpectraNS-3D

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23374123.svg)](https://doi.org/10.5281/zenodo.23374123)

**A reproducible numerical methodology for studying vortex stretching, small-scale growth, and numerical reliability in unforced three-dimensional incompressible Navier–Stokes flow.**

SpectraNS-3D asks which features of an intense flow survive changes in timestep, grid resolution, precision and execution backend—and where the available computation stops supporting a physical conclusion. Its immediate output is an auditable experiment, including unsuccessful and under-resolved runs. Its long-term goal is a reproducible research study of the competition between vortex stretching and viscous smoothing.

**Current status, October 13, 2026:** the original-IC **N512 / N640 / N768 study through $t=1.10$ is complete and independently assessed**. The corrected H200 run passed 239 tests, eight backend references, numerical/memory checks and its local finer-timestep comparison (largest difference $1.64\times10^{-8}$). N640/N768 agree within **0.0128% for enstrophy** and **0.0804% for scaled net production**, meeting the declared 0.1% curve criteria. Their stable local Fourier vorticity estimates differ **1.53% at $t=1.00$** and **1.11% at $t=1.10$**: local peaks remain resolution-sensitive, and continuum convergence is not established. Read the [final three-grid report](docs/N768_THREE_GRID_COMPARISON_2026-10-13.md) and [figure/evidence](docs/evidence/2026-10-13/n768_campaign_002/evidence_manifest.json). A post-hoc [spectral resolution addendum](docs/SPECTRAL_RESOLUTION_ADDENDUM_2026-10-14.md) shows why: under 1% of enstrophy, but about a third of a peak-vorticity proxy, sits in shells where the N640 and N768 spectra differ by more than 1%.

**Release and resources:** the owned H200 is destroyed and independently absent. The corrected campaign cost USD 7.162 posted, with a USD 7.539 conservative upper bound, below its USD 14 cap. Total project exposure is USD 33.320 including retained pending allowances, below the USD 40 ceiling. No further rental or later-time simulation is planned. The first N768 preflight refusal and all historical evidence remain intact. This is a completed finite-interval numerical research release; it does not prove regularity, blowup or an enstrophy turnover. [Research contribution and claim boundaries](docs/RESEARCH_CONTRIBUTION.md).

Follow the [Plan of Action](docs/PLAN_OF_ACTION.md) for chronological tasks, acceptance criteria, the current decision and the mandatory next-step handoff.

## Why this project exists

Large vorticity, fast enstrophy growth and a plausible-looking spectrum can all occur in a computation that has become unreliable. Errors in the integrator, insufficient spatial resolution, FFT normalization, grid sampling or a failed run controller can imitate or distort the phenomena we want to study.

Our research questions are:

1. How do stretching production and viscous loss balance during the growth of intense vorticity?
2. Which measured quantities are stable under temporal and spatial refinement?
3. How early do spectral diagnostics warn that a grid is insufficient, and how well do those warnings agree with direct grid comparisons?
4. How much does sampling a continuous peak on a finite grid change the reported maximum?
5. Can another researcher reproduce the result, its acceptance decisions and its limitations from recorded inputs and evidence?

The intended contribution is a validated methodology and carefully bounded observations for specified initial conditions. Any claim of a new physical mechanism or broad scientific novelty will require further experiments and a literature comparison.

## OpenAI's claim and our scope

On September 8, 2026, OpenAI announced a claimed solution to the Navier–Stokes Millennium Prize Problem and released an analytical writeup and Lean formalization. Its announcement identifies the breakdown alternatives C and D of the official problem formulation. [OpenAI announcement](https://openai.com/index/navier-stokes-solution/).

Theorem 1.1 in its paper constructs, for every positive viscosity, a flow starting at rest with a smooth force compactly supported in space and time. Velocity becomes unbounded in finite time while kinetic energy stays bounded. The paper also presents a periodic version. [OpenAI paper, Theorem 1.1](https://cdn.openai.com/pdf/32d9f210-8b73-45e0-91bc-82a30aef8a9a/navier-stokes.pdf).

The distinction about forcing matters: Clay's existence statements A/B specify zero forcing, whereas its breakdown statements C/D permit smooth forcing. [Official problem description](https://www.claymath.org/wp-content/uploads/2022/06/navierstokes.pdf). OpenAI also reports a separate unforced **Euler** result, which concerns zero viscosity. [OpenAI formalization repository](https://github.com/openai/NavierStokesAndEuler).

| Aspect | OpenAI's published Navier–Stokes claim | SpectraNS-3D |
|---|---|---|
| Main product | An analytical singularity construction and formal proof | A tested numerical workflow and reproducible observations |
| External force | Smooth nonzero forcing in the construction | No external force |
| Starting flow | Starts at rest in the stated construction | Prescribed smooth vortex tubes; Taylor–Green vortex for validation |
| Domain | Whole-space result and a periodic counterpart | Periodic cube of side $2\pi$ |
| Evidence | Mathematical construction and Lean certificates | Backend comparisons, identities, refinement studies, diagnostics and provenance |
| Question answered | Existence of a constructed breakdown scenario under its stated assumptions | Reliability and dynamics of particular unforced trajectories over a validated finite interval |

A construction with forcing does not by itself predict the behavior of our unforced vortex tubes. Conversely, a well-behaved finite-grid trajectory cannot establish regularity of the continuum equations. Even the periodic domains overlap in class, so domain choice alone is not our distinction.

We are not reimplementing OpenAI's proof, numerically reproducing its forced construction, or independently certifying its formalization. This README attributes the result as OpenAI's claim and does not make a judgment about independent acceptance or prize status. A separate [statement-fidelity audit](docs/LEAN_STATEMENT_AUDIT_2026-10-14.md) checks whether OpenAI's Lean theorems state Clay's (C) and (D) faithfully; it found no gap, and did not check the proofs themselves. The project's value must come from its own reproducible methodology and evidence.

## Equations and observables

We evolve the unforced incompressible equations with positive viscosity:

$$
\partial_t u+(u\cdot\nabla)u=-\nabla p+\nu\Delta u,
\qquad \nabla\cdot u=0,
\qquad x\in[0,2\pi)^3.
$$

The current tube campaign uses $\nu=5\times10^{-4}$, with the original analytic tube parameters `gamma=5, a=0.25, sep=0.6, pert=0.35`. Taylor–Green flow and exact diffusive shear supply independent validation cases. Initial conditions are projected into the solver's retained divergence-free Fourier space.

With angle brackets denoting the spatial mean and $\omega=\nabla\times u$, we record:

| Quantity | Definition or purpose |
|---|---|
| Kinetic energy | $E=\tfrac12\langle\lvert u\rvert^2\rangle$ |
| Enstrophy | $Z=\tfrac12\langle\lvert\omega\rvert^2\rangle$ |
| Energy dissipation | $\varepsilon=2\nu Z$; unforced energy budget $dE/dt=-\varepsilon$ |
| Stretching production | $P=\langle\omega\cdot S\omega\rangle$, with (S) the symmetric velocity gradient |
| Viscous enstrophy loss | $V=\nu\langle\lvert\nabla\omega\rvert^2\rangle$ |
| Net enstrophy growth | (dZ/dt=P-V) |
| Peak vorticity | Grid-sampled maximum and, where fields exist, a Fourier-refined local estimate |
| Spectra and tails | Full shell energy spectra, Parseval checks and high-wavenumber diagnostics |
| Vorticity time integral | Diagnostic trapezoidal integral of sampled peak vorticity; not a certified continuum BKM criterion |

Energy may decrease while enstrophy increases. These quantities describe different aspects of the flow. Scalar diagnostics alone do not establish sheets, reconnection, a core width or a singularity.

## Numerical method and validation

The solver uses periodic Fourier pseudo-spectral discretization, rFFT storage, solenoidal projection and the strict spherical cutoff `|k| < N/3`. That cutoff reduces aliasing; it does not certify that the physical flow is resolved. Float64/complex128 and the audited low-storage RK4 scheme are used for the current research campaign. SSPRK3 is also tested.

The v2 numerical core and v3 candidate are preserved at their audited hashes. Later controller, event-time and checkpoint work wraps those cores rather than silently changing their equations. The [audit](docs/AUDIT_V3.md) documents FFT normalization, shell weighting, projection, budgets and observed integrator order on independent linear tests.

Validation separates several questions:

- **Algebra and implementation:** independent spectral/physical-space checks, energy and enstrophy identities, normalization and exact-solution tests.
- **Backend agreement:** CPU/CUDA and CPU/H100 comparisons at declared precision-specific tolerances.
- **Temporal sensitivity:** matched-time trajectories with different timestep caps, and short continuations from identical checkpoints.
- **Spatial sensitivity:** original-initial-condition trajectories at different grids, compared only where both runs pass their declared gates.
- **Operational reliability:** real process kills, partial-transfer handling, immutable protected evidence, restart hashes and verified termination.

A diagnostic pass is an operational acceptance decision. It is not a mathematical certificate of continuum accuracy.

## What has been achieved

Test counts below refer to the versions present at each campaign, not to repeated executions of today's entire suite.

| Stage | Verified outcome | Scope |
|---|---|---|
| Original-source preservation and v3 audit | All 46 supplied files hash-verified; 42-test audited baseline | Preserves historical evidence and establishes the numerical baseline |
| H100 smoke campaign | 76 tests, eight CPU/H100 references, eight N128/N256 runs | Backend and small-grid execution validation |
| N512 timestep campaign through (t=1) | Caps 0.0005/0.00025 agree; largest scalar relative difference about $5.44\times10^{-8}$ | Strong temporal agreement on this grid/interval; not spatial convergence or measured nonlinear order |
| Bounded N512 extension | Last accepted (t=1.10); first tail-gate failure (t=1.11) preserved | Bounds the operationally accepted trajectory; no enstrophy turnover reached |
| Endpoint continuation check | Identical-checkpoint window $1.00\rightarrow1.10$, largest scalar difference about $2.53\times10^{-8}$ | Local continuation error; inherited error at the anchor is shared |
| Sampling study | Fourier local estimates at (t=1.00/1.10); sampled-peak biases about 0.927%/0.150% | Peak sampling matters; estimates are not certified global suprema |
| October13 N640 preflight-only attempt 003 | 185 H100 tests and 8 backend checks passed; numerical/memory/restart preflight passed through0.05 | Production forecast 102.16 min exceeded 94.85 min available; comparison incomplete; GPU termination verified |
| Completed N512/N640 comparison | 192 H100 tests; accepted N640 prefix through 1.10; local fine check passed; 111 matched spatial events | Z within 0.1%; scaled net intermediate sensitivity; stable matched local peak sensitive at 1.00 and consistent at 1.10. Full report/evidence published; rental closed |
| Corrected N768/H200 study | 239 local and H200 tests; eleven CPU/CUDA rehearsals including seven real SIGKILLs; extracted payload 235 passed, four CUDA-only skips | Accepted original-IC prefix through 1.10, own-anchor fine check passed, 132 protected entries verified and independently replayed three-grid assessment; rental closed |

The historical N512 observations below now have a predeclared three-grid assessment; derivative-sensitive interpretation remains limited:

- Sampled peak vorticity reached **99.6038 at (t=0.89)**, approximately 3.95 times its initial value, while kinetic energy fell about 1.83% through (t=1).
- The sampled net-enstrophy-production maximum was **1.73915 at (t=1.08)**. At the last accepted event, (Z=1.94855) and (dZ/dt=+1.73472), so enstrophy was still rising.
- Modes in shells $k\ge128$ supplied approximately **16.45%** of viscous enstrophy loss at (t=1), increasing to **18.78%** at (t=1.10). Their energy share is much smaller. Dissipation weighting makes this a useful refinement diagnostic.
- The N512 tail gate tripped before turnover. The accepted endpoint is not a proof of spatial convergence, and the failed event is excluded from physical conclusions.
- No full N512 field was saved at the historical (t=0.89) peak. Its interpolation bias cannot be recovered from endpoint fields.

Historical N1024 output reporting roughly 80.09 GB allocated memory is retained as historical evidence. It came from an earlier invalid source/integration family and is not a validated v3 result or a safe memory-headroom measurement. Historical data are not pooled with accepted results to infer a physical scaling law.

Read the [H100 report](docs/H100_VALIDATION_2026-10-10.md), [timestep report](docs/TIMESTEP_VALIDATION_2026-10-10.md), and [bounded extension report](docs/ENSTROPHY_EXTENSION_2026-10-10.md). Those dated reports preserve the plans and status at their own recording times; the current N640 procedure is below.

## Completed study and remaining questions

The completed study ran **N640 from the original initial condition**, with identical viscosity and a 0.0005 timestep cap. It continued its own verified 0.05 preflight checkpoint, assembled the complete 0–1.10 record, immediately checked the 1.00–1.10 window at cap 0.00025, and hash-verified the small evidence locally before optional exploration. Sampled maxima, budgets, spectra and numerical gates remained at every event; Fourier estimates followed the declared subset. Full N640 fields were not downloaded. The [final report](docs/N640_COMPARISON_2026-10-13.md) records the result and limitations; the [continuation revision](docs/N640_SAMPLING_CONTINUATION_2026-10-12.md) preserves the pre-run design. Reloading N512 fields onto N640 would not establish full-trajectory spatial convergence.

The completed study used these predeclared comparisons:

- Integral (Z(t)) and net-production curves over the common accepted interval, with a 0.1% consistency threshold; the net difference is scaled by production-plus-loss.
- Fourier-refined local peaks at matched (t=1.00/1.10), conditional on estimator stability, with a separately reported 0.1% comparison.
- Energy and full spectra, with sampled peak vorticity/BKM retained as sampling-sensitive secondary screens.
- Supplementary local quadratic net-production peak fits with fit sensitivity, rather than a rigid raw-argmax timing verdict.

Exploration to $t=1.5$ was an optional ceiling. Its updated runtime forecast refused continuation after 20 steps toward 1.11, with no accepted sample after 1.10; the protected result remained intact. There is no later N640 tail-trip time or enstrophy turnover in this campaign. The stable local-peak mismatch at 1.00 occurred while both grids passed their tail gate, demonstrating that the heuristic does not certify every observable at 0.1%.

The completed N768/H200 study tested this sensitivity on a third original-IC grid. N640/N768 integral curves meet their declared criterion, while stable matched local vorticity estimates remain sensitive. The near-agreement of N512/N640 at1.10 did not survive the third-grid comparison. Refinement ratios512→640 and640→768 are unequal; shrinking increments alone do not establish a convergence order or continuum error bound. Enstrophy was still rising at the accepted endpoint, so a converged turnover remains outside the completed study. The [three-grid report](docs/N768_THREE_GRID_COMPARISON_2026-10-13.md) records the exact numerical, local-temporal and observable-specific limits. The [spectral resolution addendum](docs/SPECTRAL_RESOLUTION_ADDENDUM_2026-10-14.md) locates that sensitivity in wavenumber space from the published spectra alone, and records that the conventional analyticity-strip fit is too window-sensitive to serve as a resolution certificate here.

The ultimate deliverable is a reproducible study with uncertainty and resolution limits attached to its claims: validated trajectories, refinement comparisons, calibrated warning diagnostics and enough evidence for independent reanalysis. There is no meaningful percentage-complete estimate toward a mathematical regularity proof; this project is building numerical evidence, and a proof would require additional mathematical work.

## Reproduce locally

The primary development workspace is on the native WSL/Linux filesystem. Windows Documents holds selected exports rather than the active checkout.

For a fresh Linux x86_64 or WSL checkout:

```bash
git clone https://github.com/amitb-quantum/SpectraNS-3D.git spectrans-3d
cd spectrans-3d
conda create -n spectrans-3d --file conda-linux-64.lock
conda activate spectrans-3d

# Select the validated CUDA 13 Torch build before resolving the pinned packages.
python -m pip install --no-deps --index-url https://download.pytorch.org/whl/cu130 torch==2.13.0+cu130
python -m pip install -r requirements-linux-64.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check

OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m pytest -q tests
```

The locked research stack is Python 3.12.13, PyTorch 2.13.0+cu130, NumPy 2.5.1 and pytest 9.1.1. CPU tests run without a GPU; four CUDA-specific tests skip when CUDA is unavailable. Using a different dependency stack is a separate configuration and must be validated. See [environment notes](docs/ENVIRONMENT.md).

A small CPU example:

```bash
python src/ns_fast_v3.py --case tgv --N 32 --device cpu --fp64 \
  --scheme lsrk4 --target_t .05 --max_dt .002 \
  --csv artifacts/example/scalars.csv \
  --spectrum_csv artifacts/example/spectra.csv \
  --budget_csv artifacts/example/enstrophy.csv
```

Use a new output directory for each run. This is an example trajectory, not a research-validation receipt.

The full original archives and multi-gigabyte fields remain preserved locally and are excluded from Git. To re-run archive restoration/provenance verification, supply the three archives identified in [the original manifest](configs/original_manifest.json) under `data/original/`, then run:

```bash
python scripts/restore_inputs.py
python scripts/verify_provenance.py
```

The checked-in tests need no original archives. Four small, hash-bound N512 comparison files are deliberately tracked at their existing historical paths so a clean clone can run the full suite and inspect the accepted prefix. See [evidence inventory](docs/evidence/README.md).

## Cloud execution and evidence contract

Cloud discovery is read-only by default. `python scripts/run_vast_refinement.py` prints the N640 plan; it does not provision anything. Billable execution requires explicit execution arguments, valid authorization, fresh complete billing, a live quote, exact source/payload bindings, the complete rehearsal proof and an ownership-bound termination guard. No credential is committed or copied to the GPU.

The completed dedicated N640 campaign ceiling was **USD 5 all-in** within a **USD30 project ceiling**. The read-only offer screen is a single H100 with CUDA 13 compatibility, at least 80 GB advertised VRAM, verified reliability at least 0.99, 64 GB disk and at most USD2.60/hour including conservative storage. That attempt tightened the fresh GPU-plus-storage quote to **USD2.25/hour** and funded the existing shared-account guard floor. See the [additional-attempt specification](docs/N640_RETRY_SPEC_2026-10-13.md). Actual protected runtime and available disk must pass measured preflight; advertised specifications are insufficient. The live budget ledger is local and ignored by Git. [Budget setup template](configs/project_budget.template.json).

The new dedicated N768/H200 path retains the numerical criteria and uses a separately authorized **USD14 corrected-attempt cap / USD40 total project ceiling**, single H200>=140GB advertised VRAM,120GB disk, quote<=USD4.50/hour and at most three hours. The CFL-aware correction passed239local tests, eleven CPU/CUDA controller rehearsals including seven real SIGKILLs and extracted235-test CPU proof. The original229-test readiness remains historical evidence. Old launchers retain their original grid/budget restrictions. No later-time exploration or automatic retry is part of this phase. [Frozen N768 specification](docs/N768_THIRD_GRID_SPEC_2026-10-13.md).

Every research GPU run must retain:

- Exact initial condition, configuration, command and source/config hashes.
- Runtime/package versions, device identity and CPU/H100 reference results.
- Diagnostic CSVs, energy/enstrophy budgets and full spectra at declared output times.
- Achieved timestep history, driver/allocator memory, stage timings and device telemetry.
- Checkpoint metadata and component hashes, plus separately labelled field recovery status.
- First failing diagnostics, protected-data collection receipts and verified termination/billing records.

The rehearsals exercise real controller/worker SIGKILLs during main evolution, the fine window, protected collection, field collection and exploration. No phase before protected collection can leave a validated receipt, and incomplete `.part` transfers cannot be promoted. The main comparison is protected before exploration or large-file collection.

Read [N640 controller usage](docs/N640_CONTROLLER_USAGE.md) and [Vast.ai handoff](docs/VAST_AI_CLAUDE_HANDOFF.md). No N768/N1024 experiment is authorized by the N640 procedure.

## Repository layout

```text
src/          Audited numerical core, v3 driver and analysis modules
analysis/     Post-hoc, CPU-only analyses of published evidence (outside the campaign fingerprint)
scripts/      Validation, provenance, checkpoints, controllers and read-only discovery
tests/        Independent numerical checks and operational regressions
configs/      Fixed scientific plans, reference hashes and budget template
docs/         Audit, campaign reports, figures, methodology and selected validation evidence
data/         Archive instructions; original archives remain local
artifacts/    Generated runs remain local except four explicit comparison inputs
```

Original sources, historical results and completed evidence are preserved. A Git clone is the curated reproducibility package, not a backup of every local archive, field, billing record or environment.

## Attribution and project status

The original supplied source families remain separately identifiable; audited code is retained and hash-bound. Low-storage RK4 coefficients are attributed in the audit to [Carpenter and Kennedy, NASA TM-109112](https://ntrs.nasa.gov/citations/19940028444). Links to OpenAI identify external mathematical work; there is no affiliation, endorsement or independently verified reproduction of that work implied here.

Code and tests are licensed under [Apache-2.0](LICENSE). Documentation, reports, figures and published evidence under `docs/` are licensed under [CC-BY-4.0](LICENSE-docs). See [NOTICE](NOTICE). Scientific conclusions are bounded by the validated configurations and accepted intervals described above.

## How to cite

Citation metadata is in [CITATION.cff](CITATION.cff); GitHub's "Cite this repository" button uses it. Each tagged release is archived on Zenodo. Cite all versions with [doi:10.5281/zenodo.23374123](https://doi.org/10.5281/zenodo.23374123); each release also has its own version DOI, listed on the Zenodo record (v1.0.0: [doi:10.5281/zenodo.23374124](https://doi.org/10.5281/zenodo.23374124)).

The [closeout procedure](docs/ACCOUNT_COEXISTENCE_AND_CLOSEOUT.md), [preflight-only outcome](docs/N640_CAMPAIGN_OUTCOME_2026-10-13.md) and [completed comparison](docs/N640_COMPARISON_2026-10-13.md) preserve the chronological record. The N640 and corrected N768 phases are closed with their finite-interval assessments and explicit sensitivity limits. The [plan state](docs/PLAN_STATE.json) records the release closeout. The broader mathematical question, continuum peak accuracy and a converged turnover remain open; none is claimed as a completed result.
