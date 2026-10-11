# N640 readiness revision: protect the comparison before exploration

This revision supersedes the first N640 proposal before any N640 data exist. The previous proposal, analysis helpers, tests and report are archived in artifacts/cloud-preparation/2026-10-10/n640_review_002/before_revision. Historical N512 evidence remains unchanged. No GPU was provisioned or simulated during this revision.

**1. Required scientific result comes first.**

The planned order is now:
1. Fresh billing/quote/source binding, tests and backend references, same-host N512 benchmark, N640 preflight and transfer probe.
2. Run N640 from the original analytic initial condition to t=1.10 at cap 0.0005, under unchanged numerical and memory gates. Save t=1.00 and t=1.10 checkpoints.
3. End the coarse process. Run the fine window [1.00,1.10] from its N640 t=1.00 checkpoint at cap 0.00025. Keep the 1e-5 agreement requirement.
4. Validate the prefix, record matched two-grid comparisons, freeze the protected manifest, and collect/hash-verify all small scientific evidence in native WSL.
5. Prefer collecting the one temporally checked t=1.10 checkpoint if its measured transfer forecast fits.
6. Only then reload the COARSE t=1.10 state in a separate process and explore, possibly only briefly, up to t=1.50.
7. Collect remaining small records, destroy the owned instance at the bound deadline, verify provider absence and reconcile charges.

There are no overlapping coarse/fine/exploration solver processes and no second full trajectory retained on GPU. The t=1.00 anchor is used only for same-grid temporal validation. N640 still begins from the original analytic condition, never an N512 restart.

t=1.50 is an optional ceiling. Protected scientific status is separate from optional exploration and full-checkpoint download status. A late exploratory tail trip, spending cutoff or missing optional array collection cannot erase already verified prefix evidence. It also cannot be concealed: each outcome remains separately recorded. Instance termination and billing closure still require independent final evidence.

An early numerical gate trip before t=1.10 leaves the planned full comparison incomplete. Preserve its accepted samples and first failed diagnostic; do not relax a gate or continue exploration. Unexpected host or infrastructure failures can still interrupt a required phase. The scheduling rule protects the main result from planned optional work; it is not a guarantee that mandatory computation will always finish.

**2. Primary criteria use the integral curves.**

The common accepted comparison remains at most [0,1.10], with identical event times. Its primary metrics are:
- Maximum matched relative Z difference: 0.001 tolerance.
- Maximum matched net-production difference scaled by the larger production-plus-viscous-loss magnitude: 0.001 tolerance.

Record agreement, intermediate sensitivity (0.1–1%), or material discrepancy (at least 1%). A useful, numerically/temporally validated comparison can reveal disagreement; do not label it consistent merely because the campaign executed correctly.

Grid-sampled wmax is demoted to a secondary screen with a predeclared 1% relative tolerance. Its sampled timing is reported without a hard timing gate. Grid-derived BKM is also sampling-sensitive and receives the same secondary screen. Secondary energy and full-spectrum L1/E comparisons retain 0.1% tolerances. The existing dissipation, divergence, parseval, instantaneous-budget, tail and memory gates are unchanged.

A spectral interpolation method would need validation and field snapshots around the peak on both grids. The retained N512 full fields are at t=1.00, 1.10 and failing t=1.11, not at the peak-vorticity sample t=0.89. An interpolated historical maximum at that event cannot be recovered from scalar CSVs. Demotion is therefore the practical option within this campaign. A 1% screen is not a certified sampling-error bound, and passing integral checks does not establish convergence of the vorticity maximum.

**3. Fit net-production peaks, but do not make them decide the protected result.**

A separately bracketed local maximum on each grid can be compared as supplementary evidence using that grid's own accepted observations. Require a five-event neighborhood centered on the sampled maximum, with accepted data on both sides, and also fit its central three events. Refuse extrapolation from an unbracketed endpoint, nonconcave fit or vertex outside the nearest-neighbor bracket.

For the accepted N512 neighborhood:
| Fit | Vertex time | Vertex value |
|---|---:|---:|
| 3 points | 1.08178626 | 1.73918198 |
| 5 points | 1.08064570 | 1.73916970 |

The five-point maximum absolute residual is 0.00026424. The declared heuristic sensitivity radius is the largest of half an event interval, the 3/5-point vertex shift and a residual/curvature time scale. Here it is approximately 0.005 in time; value sensitivity is approximately 0.00027652 (0.0159% of the fitted maximum).

These are model/window sensitivity estimates, not statistical confidence intervals or rigorous bounds on the continuous maximum. The comparison reports within nominal 0.01 time / 0.1% value tolerances, separated estimates, or inconclusive after including the declared sensitivity envelopes. None controls the protected curve classification.

An N640 maximum after t=1.10 may become bracketed during optional accepted exploration and can then be reported as its separately observed local peak. This does not extend the validated N512 trajectory, prove a global maximum, or add N640 temporal certification beyond t=1.10. If exploration is cut short before bracketing, the peak estimate stays inconclusive and the protected curve result remains usable.

**4. Add same-host and transfer measurements.**

Before N640, use a separate N512 tubes process at the identical nu, integrator, precision, CFL and cap. Allow five warmup steps, then time about twenty integration steps with CUDA synchronization at the window boundaries. Report setup/diagnostics separately. End this process before allocating N640.

The old 0.43635 seconds/step included diagnostics and comes from a different physical H100. The extension's 0.5997 ordinary-step median is a closer integration baseline, though still measured from historical timestamps rather than the new exact timing window. The benchmark characterizes the new host and narrows the explanation; it does not uniquely identify the historical slowdown cause.

Retain the N640 100-step production-configuration preflight with twenty warmup steps excluded from timing. Exercise full diagnostics, budgets, spectra, checkpoint save/hash and reload. Observe both allocator and driver peaks continuously, including setup/restart, with the 80% limit unchanged.

Use two approximately 64 MiB incompressible, nonsecret download probes through the actual SSH/SCP endpoint and intended stream strategy. Record bytes, full elapsed time, SHA checks and charged traffic. Also time compression and verification of the actual N640 preflight checkpoint and record its compressed size. The declared egress upper allowance rises from 8 to 8.25 GB to include probes and small snapshots; the quoted total ingress/egress/fees must still fit the USD 0.50 noncompute reserve.

Use the slowest measured trial and 1.5 times transfer plus compression/verification time, then add cleanup. Do not use advertised network bandwidth or assume that 600 seconds suffices. At 4 MB/s, the raw 6.311 GB state needs about 2,427 seconds including the basic transfer allowance and cleanup, before extra compression/hash costs. Its actual lossless compressed size may be much smaller, but must be measured and verified.

Freeze and verify the small protected bundle in WSL BEFORE either a large optional field transfer or exploration. A final controller/provider termination record is added during closure. Later records use new snapshots rather than overwriting the protected copy.

**5. Forecast the protected phase separately.**

The mandatory cap-controlled calculation has 2,200 coarse steps plus 400 fine-window steps, approximately 122 diagnostic events and twelve checkpoint operations. Using the earlier illustrative costs of 0.9 seconds per diagnostic and 20 seconds per checkpoint, 25% compute margin, 600 seconds setup/preflight and 180 seconds small-artifact/cleanup reserve:

| N640 integration scenario | Required phase |
|---|---:|
| 1.2 seconds/step | 5,117 seconds / 85.3 minutes |
| 1.3 seconds/step | 5,442 seconds / 90.7 minutes |

These allowances are scenarios, not measured promises. Before production, replace them with the actual remaining steps/dt, stage timings, transferred sizes/bandwidth and remaining rental lifetime. Test optional checkpoint collection and exploration against the resources remaining after the protected bundle is verified. Reforecast at every event when CFL or speed changes. No automatic retries or deadline extensions.

The N-cubed log-N FFT model multiplies pure cubic scaling by log(640)/log(512)=1.03577, about 3.6% extra for that component. Applying it to the previous ordinary-step cubic estimate yields about 1.213 seconds/step as a rough scenario, not a measured whole-step cost. N640=2^7*5 is an optimized small-prime FFT size. NVIDIA documents that powers of two generally perform best, but does not establish a fixed radix-5 penalty for this specific H100/shape/plan. The actual preflight, not a guessed penalty, decides production. [NVIDIA cuFFT documentation](https://docs.nvidia.com/cuda/cufft/).

The USD 5 campaign cap, USD 30 project ceiling, price-bound lifetime, fresh billing requirement and independent ownership-checked destruction guard are unchanged. No requirement to finish t=1.50 remains. Current project extension launchers remain restricted to N512; a separate N640 execution controller must implement the revised declaration before provisioning.

**6. Validation and evidence.**

126 local tests pass. New regressions cover required-phase forecasts, measured slow transfer, preservation of protected status when exploration/checkpoint collection is incomplete, exact quadratic-vertex recovery, uncertain shifted peaks, and refusal to extrapolate or fit malformed samples. All 46 supplied original files verify unchanged. Audited v2/v3 hashes are unchanged.

The historical N512 peak fit is archived as N512_local_peak_fit.json. The revised declaration is configs/n640_refinement_proposal.json (schema version 2), copied to the review artifact as N640_REVISED_SPEC.json. Local tests, source/config hashes and selected Windows exports are recorded separately. No new GPU run was performed.


## Superseding offer policy, October 11

The scientific gates and protected-first controller ordering remain unchanged. The current executable proposal is configs/n640_refinement_proposal.json, with a USD2.60/hour combined GPU/storage screening ceiling and a 64 GB requested disk backed by a six-state retention model and two live available-space checks. Measured protected runtime still governs production; the USD5 campaign and USD30 project caps remain fixed. This update supersedes earlier USD2.10/80 GB offer-screen statements only. Renewed source-bound rehearsal and payload evidence is in artifacts/cloud-preparation/2026-10-11/n640_offer_policy_001/.
