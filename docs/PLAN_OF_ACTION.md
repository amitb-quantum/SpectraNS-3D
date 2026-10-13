# Plan of Action — SpectraNS-3D

Version 1.0, October 13, 2026. This is the primary chronological execution plan. The detailed scientific specification remains [n640_refinement_proposal.json](../configs/n640_refinement_proposal.json). [PLAN_STATE.json](PLAN_STATE.json) records the current task and the next task.

## Deliverable and definition of done

The immediate deliverable is a reproducible study of the original unforced, viscous, periodic 3D Navier–Stokes tubes: determine whether the N512 observations through t=1.10 are consistent with N640, and distinguish physical behavior from timestep, grid and sampling effects.

The scientific milestone is complete only when the original-IC N640 trajectory, its required fine timestep window and the matched N512/N640 assessment are available with their declared evidence and limits. Agreement and disagreement are both valid answers. A runtime refusal is an execution blocker; publishing a refusal does not answer the late-time spatial question.

A release can also close with an explicitly incomplete scientific milestone, if you choose that outcome. Such a release must identify what remains unknown. It must not imply regularity, blowup, a convergence order from two grids, or certification of OpenAI's proof claim.

## Current position

- Audit, CPU/H100 backend equivalence, N512 timestep study and bounded N512 extension are complete.
- The latest H100 passed 185 tests and 8 backend checks. The N640 preflight and checkpoint reload passed their short-interval numerical/memory checks.
- N640 production has never reached the requested comparison interval. The October13 attempt was refused because protected work forecast 102.16 minutes versus 94.85 usable minutes.
- Its instance was destroyed and absence verified. The attempt cost USD 0.433 posted at closure, with a conservative USD 0.929173 bound. Its report and evidence are on main at commit d258fcb556e69090454c437454cf7830d897029d.
- The last budget snapshot has USD 20.778741 conservative project exposure, including pending allowances; USD 9.221259 remains below the USD 30 ceiling. These are dated project figures, not current shared account credit.
- No new rental is authorized by this document alone. Fresh shared credit must cover the quote-specific lifetime cost, any separately attributed rental reserve and the USD 1 balance guard floor, independently of project headroom. If funding is insufficient, consult before provisioning. The previous single-attempt authorization is closed. A fresh single-attempt authorization was received; preparation and proof binding precede reactivation of its follow-up.

**Decision received:** one additional USD5 attempt on an H100 at no more than USD2.25/hour. **Current task: P05 — verify the offer and financing.** The [additional-attempt specification](N640_RETRY_SPEC_2026-10-13.md) freezes the scope and discovery deadline; PLAN_STATE.json carries subsequent handoffs.

## Chronological tasks

| Step | Task and purpose | Required output / completion criterion | What follows |
|---|---|---|---|
| P01 | Freeze and audit the baseline, so new results use the audited solver and retained references. | Completed: immutable historical evidence, source hashes, 185 tests, 11 controller rehearsals and the published latest outcome. Record the baseline commit; do not repeat broad tests without a relevant change. | P02 |
| P02 | Decide whether to finish the spatial experiment or close this phase as incomplete. | Your explicit choice among the three options below. Ask immediately; never interpret silence as permission. | Continue: P03. Close: P11. |
| P03 | Freeze the experiment and spending specification before any rental. | A versioned specification stating the original IC, grids, timestep caps, output times, numerical/temporal/spatial criteria, artifact requirements, price screen, lifetime and one-attempt budget. Record approval and source/config hashes. | P04 |
| P04 | Verify implementation and execution readiness. | If code/guard/scientific configuration changed, meaningful tests and all11 source-bound CPU/CUDA rehearsals must pass. Otherwise verify existing proofs. Verify bootstrap, runtime lock, reference data and fresh payload bindings. Private billing stays out of public Git. | P05 |
| P05 | Find an eligible offer and verify financing before spending. | Fresh complete project billing and account-instance attribution; sufficient project headroom and shared credit, including any separately attributed rental reserve and the USD 1 account-credit guard floor. Use the quote-specific maximum lifetime cost plus that floor, not the project ceiling alone. Exact live quote, transfer allowance and verified hardware/driver/disk gates. The recommended USD 5 path adds a selection ceiling of USD 2.25/hour so the full 120-minute lifetime is financially available. | P06. If no qualifying offer within 60 minutes of approval: ask you immediately; no indefinite waiting. |
| P06 | Provision exactly one owned instance and run preflight. | Arm the independent ownership, spending/lifetime and account-credit guards before create. Verify pinned runtime, H100 tests/references, same-host N512 benchmark, N640100-step numerical/memory/disk preflight, checkpoint reload and actual transfer rates. Record all measured timing categories. | If admitted: P07. If refused: destroy/verify absence, preserve evidence and reconcile charges, then return to P02 with an immediate decision request. |
| P07 | Run the original-IC N640 comparison trajectory through 1.10. | Continue the new rental's exact N640 t=0.05 preflight state. Verify and assemble 0–1.10 records; preserve t=1.00 and 1.10 checkpoint metadata/component hashes. All-event diagnostics, budgets, full spectra and fixed gates must pass through the required end. | P08. If a gate trips: preserve accepted prefix/first failing sample, collect evidence, close/reconcile and return to P02. |
| P08 | Check N640 temporal sensitivity where the comparison matters. | From the N640 t=1.00 anchor, run 1.00–1.10 at dt cap0.00025 and compare with coarse cap0.0005. Pass the declared 1e-5 agreement and meaningful-step checks. Keep processes sequential so two GPU states do not coexist. | P09. If it fails: preserve both runs, close/reconcile and return to P02; no exploration. |
| P09 | Independently classify the spatial evidence. | Compare exact matched N512/N640 events, integral curves, full spectra, stable Fourier peaks at 1.00/1.10 and separately labelled sampled maxima. Record consistent / sensitive / inconclusive classifications; disagreement is a useful result and must not trigger silent retuning. Hash-verify all required small evidence in WSL. | P10 |
| P10 | Close the rental and settle its financial record. | Optional exploration to at most1.5 is never required and cannot delay protected evidence or exceed the existing guards. Stop the owned instance, verify absence and reconcile posted/pending charges. Record termination reason, actual accepted interval and any incomplete optional work. | P11 |
| P11 | Write the scientific interpretation and final report. | State what changed with resolution, which numerical gates passed, whether each observation is supported, and what remains unknown. Include the exact evidence and limitations. If closing without the experiment, state that the late-time spatial question is unanswered. | P12 |
| P12 | Publish and close the phase. | Update README/status, commit and push the report plus sanitized small evidence to main, verify published hashes and pause the follow-up. Give you the result, repository link, cost and remaining limitations. Do not create a further billable experiment automatically. | End this phase. A new study requires a separate agreed specification. |

## P02 decision — selected option1

1. **Recommended: one additional USD 5 attempt on an eligible H100 at no more than USD 2.25/hour.** Prefer a measured fast host; keep all scientific and runtime gates. The last host's timing scenario would have fit the full 120-minute lifetime with about 4.70 minutes of slack after the existing 25% compute margin. That is a scenario, not a promise about another host. Discovery is timeboxed to 60 minutes; if no suitable host appears, consult immediately.
2. **One additional attempt with a USD 6 ceiling, retaining the USD 30 project ceiling.** This requires implementing and revalidating the new explicit spending authority, and sufficient fresh shared credit. At the existing hourly screening ceiling of USD 2.60, two hours plus USD 0.50 reserve is USD 5.70. Numerical gates and the 120-minute maximum stay fixed. Do not change the cap or provision until this option is selected and readiness passes.
3. **Close this phase using the current findings.** No further rental. The release contains the validated methodology, N512 observations and N640 preflight, while explicitly leaving late-time spatial consistency and enstrophy turnover unresolved.

## Frozen scientific acceptance specification

These criteria are already declared; do not loosen them after inspecting new results.

| Quantity or check | Criterion and interpretation |
|---|---|
| Configuration | N640, original analytic tubes; nu=0.0005; periodic 2pi; float64/complex128; LSRK4; CFL 0.2; strict spherical magnitude(k)<N/3; coarse dt cap0.0005; event spacing 0.01. No N512 restart transplant. |
| CPU/H100 agreement and reproducibility | All declared backend reference criteria and repeated-spectrum checks in h100_acceptance.json pass. Record exact code/runtime/configuration and any randomness rather than promising bitwise equality across arbitrary GPUs/drivers. |
| Energy, finite values and divergence | Use existing finite, dissipative-energy, budget and divergence gates. Divergence maximum 1e-4; interval energy-budget relative residual1%; Parseval relative tolerance 2e-6. |
| Enstrophy and spectrum | Instantaneous enstrophy-budget relative identity tolerance 1e-8; tail threshold 1e-6. Preserve accepted and first failed samples. The tail gate is a heuristic, not a resolution certificate; record fixed/relative high-k dissipation shares every event. |
| Memory | Driver and allocator peaks each below 80% using their respective matching totals. Preserve sampled-driver limitations. Measured free disk must pass the existing six-state capacity bound. |
| Runtime and money | Protected prefix, fine window and small collection fit the remaining lifetime with 25% compute margin and 180-second collection reserve. Maximum 120 minutes; the per-attempt financial bound may shorten it. Never replace these checks with the advertised GPU name or hourly price. |
| Local temporal agreement | Fine 1.00–1.10 from the same N640 1.00 anchor; dt cap0.00025; all specified comparisons at most1e-5; meaningful step-count ratio at least 1.9. Shared inherited error means this is local continuation validation. |
| Primary spatial curves | Max matched relative Z difference and net-production difference scaled by production-plus-loss at most1e-3 over the common accepted window, capped at 1.10. Intermediate discrepancies are inconclusive; percent-level discrepancies indicate sensitivity. |
| Matched Fourier vorticity peaks | Relative tolerance 1e-3 at 1.00 and 1.10, conditional on estimator stability on both grids. The retained N512 data cannot reconstruct a Fourier maximum at 0.89. |
| Secondary observations | E and spectrum L1/E tolerance 1e-3; grid maximum/BKM screens 1%. Grid sampling makes borderline maxima inconclusive. Supplementary fitted peak estimates cannot override primary curve classifications. |
| Higher grids / later physics | No N768/N1024 run. No claim about a converged turnover or behavior beyond the accepted/common interval. |

The configuration row uses the literal spherical cutoff |k|<N/3; see the JSON scientific specification for machine-readable details and exact source bindings.

## Required evidence from every GPU attempt

Keep the exact configuration, initial-condition definition, source and payload hashes, runtime/package/driver versions, diagnostic and step CSVs, enstrophy budgets, full spectra at declared events, Fourier estimator stability records, driver/allocator memory telemetry, timings/transfer measurements, checkpoint metadata and component hashes, accepted/failing-sample status, verified collection manifest, termination record and reconciled charges.

Full field downloads are not required by the current production specification. If fields were not recovered, say so; checkpoint hashes alone do not provide a restart state. Preserve original sources and historical evidence. Credentials, private account attribution and the live ledger remain local.

## Task handoff and consultation rule

At the end of every task, update PLAN_STATE.json with its result/evidence path, status and successor. Continue the successor immediately when its prerequisites and authorization are satisfied. Report: what completed, what it establishes, what follows and whether anything blocks it.

Consult you immediately when a decision is actually required: a refused preflight, exhausted authorization or discovery timebox, unexpected cost/credit shortage, failed acceptance criterion needing a new scientific design, or proposed changes to viscosity, IC, grid, timestep, gates or spending authority. Do all unaffected work first and present the measured blocker and concrete choices. Do not end with only “waiting” when the next action requires your decision.

A failed task is not complete merely because a failure report was written. Close the owned rental and preserve evidence, mark the scientific dependency blocked, and move directly to the decision task. Silence does not authorize changes. No repeated billing, higher-grid diversion or post-hoc gate relaxation.

## Key records

- [Current outcome and evidence](N640_CAMPAIGN_OUTCOME_2026-10-13.md)
- [N640 controller procedure](N640_CONTROLLER_USAGE.md)
- [Selected diagnostics and same-grid continuation](N640_SAMPLING_CONTINUATION_2026-10-12.md)
- [Bounded N512 extension](ENSTROPHY_EXTENSION_2026-10-10.md)
- [Runtime/budget closeout procedure](ACCOUNT_COEXISTENCE_AND_CLOSEOUT.md)
