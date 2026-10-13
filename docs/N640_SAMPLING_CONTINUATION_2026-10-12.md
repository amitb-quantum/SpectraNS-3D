# N640 selective diagnostics and preflight continuation — October 12, 2026

The first H100 N640 preflight completed its numerical, backend, memory, disk and restart checks. Production was refused because the protected result needed 6,165.00 seconds while only 5,943.59 usable seconds remained. The rental was destroyed and its absence verified. This revision changes diagnostic sampling and reuses the same-grid preflight trajectory; it does not change the audited equations, integrator, viscosity, precision, timestep caps, spectral mask, scientific tolerances, 25% runtime margin or two-hour lifetime.

## Declared sampling

Sampled grid vorticity maximum, BKM, energy/enstrophy, instantaneous budgets, divergence, tail checks, achieved timesteps, full event spectra and dissipation shares remain at every diagnostic event (0.01).

Fourier local peak estimates are computed at:

- Coarse times 0, 0.05, ..., 1.10.
- Every coarse event from 0.86 through 0.94, including 0.89.
- Fine-window endpoints 1.00 and 1.10.

There are 31 coarse estimates and two fine estimates. Preflight supplies the estimates at 0 and 0.05. The continuation does not refine its repeated 0.05 anchor again, leaving 29 continuation estimates plus two fine estimates to forecast.

Unselected CSV rows keep the sampled maximum and explicitly record refinement_performed=False, with all uncomputed estimator fields empty. Independent assessment checks both the event coverage and the declared selected times. Matched estimates at 1.00 and 1.10 must exist and be stable for their primary interpretation. The Fourier estimator and the N512 reference hashes remain unchanged. No N512 field exists for its historical sampled maximum at 0.89.

## One original-IC trajectory

Preflight integrates the original analytic initial condition on N640 from 0 to 0.05 at cap 0.0005. The separate reload check advances a copy from 0.05 to 0.051, but its evolved state is not used for production.

After preflight passes, production loads the retained original t=0.05 checkpoint and continues to 1.10. Before assembling the complete trajectory, the controller verifies:

- Identical grid, viscosity, case, scheme, precision, CFL, timestep cap and event/checkpoint intervals.
- Exact checkpoint metadata/component-hash identity and global step number.
- Matched boundary diagnostics.
- Full diagnostic/spectral coverage and continuous step numbering.

Original preflight and continuation files remain preserved. The canonical comparison view combines every diagnostic from 0 to 1.10, preserves the boundary event once and records the source manifests/hashes. Only after this assembly passes independent validation and receives a verified receipt are the preflight arrays released. Their metadata and hashes remain.

This is continuation of the same original-IC N640 trajectory, not an N512-to-N640 transfer experiment. A CPU regression compares its final fields to an uninterrupted run and obtains bit-for-bit equality. That test does not itself prove H100 equivalence; cloud backend, restart and numerical checks remain required.

The existing six-state disk allowance remains conservative: retained preflight plus up to three coarse states coexist, and preflight is released before fine/exploration. Actual free space is measured after setup and after preflight retention.

## Runtime accounting

Fresh preflight times always-on diagnostics separately from the two selected endpoint refinements. The protected forecast includes:

| Remaining work | Count |
|---|---:|
| Coarse steps from 0.05 to 1.10 | 2,100 |
| Fine-window steps | 400 |
| Always-on diagnostic events, including phase anchors | 117 |
| Selected Fourier refinements | 31 |
| Checkpoint writes/hash/prunes | 12 |

The same 25% compute margin and 180-second small-artifact allowance apply. Per-event runtime/CFL reforecasting remains active.

Using the previous host's measurements as planning inputs:

| Plan | Required minutes | Slack against its 99.06 usable minutes |
|---|---:|---:|
| Original | 102.75 | -3.69 min |
| Selective refinement only | 93.23 | 5.83 min |
| Preflight continuation only | 99.055 | 0.28 seconds |
| Both changes | 89.86 | 9.20 min |

Continuation alone barely clears that numerical forecast and offers no useful additional slack. Both changes are implemented. These are historical-rate scenarios, not a promise about the next host. The old callback category includes a small amount of bookkeeping; the new preflight explicitly measures refinement calls rather than treating that entire category as interpolation.

N640 mean integration / N512 timed-step ratio was about 2.45. The timing scopes differ (N640 includes per-step bookkeeping and the full diagnostic/checkpoint workflow, N512 is a separate warmed integration benchmark). The observation is useful empirically but does not uniquely identify a radix-5 FFT penalty. Future forecasts use measured rates.

## Field custody and verification

Full production checkpoint compression/download is disabled by default. Every checkpoint's exact metadata and per-component hashes remain mandatory, together with diagnostic CSVs, full event spectra, source/configuration records, runtime metrics and verified termination. Small evidence must be hash-verified in WSL before optional exploration.

The early preflight archive was 0.985 GB and the slower actual transfer probe was 3.43 MB/s. Raw 6.311 GB would take about 31 minutes at that rate; later compressed sizes have not been measured. No later transfer time is inferred from the early compression ratio.

The revised local suite passes 168 tests. Eleven real-process rehearsal cases include seven independent SIGKILLs (preflight, coarse, prefix assembly, fine, protected collection, checkpoint collection, exploration), sequential/overlap success, metadata-only success and N256 CUDA success. No protected receipt is issued before protected evidence verification; partial transfers are not promoted. The rehearsals use no provider calls and are not N640 convergence evidence.

A new billable attempt still requires fresh complete billing, a live qualifying quote, the current source-bound rehearsal, the verified bootstrap/image and a newly bound payload. The USD5 campaign and USD30 project caps remain. There is no automatic retry, deadline extension or N768/N1024 path.
