# N640 campaign outcome, October 13, 2026

**The authorized attempt closed after preflight. Numerical, backend, memory and checkpoint checks passed; the measured runtime admission gate refused production. The planned N512/N640 comparison through t=1.10 and its fine timestep window were not completed.**

Instance 55782970 used offer 53446709, a single H100 PCIe with an hourly GPU/storage bound of USD 2.50. It ran from 10:22:09 PDT to 10:32:27 PDT, approximately 10.30 minutes. Owned-instance destruction and absence were independently verified. No automatic billable retry, exploration, N768 or N1024 run followed.

## What ran and what passed

The source-bound cloud suite passed 185 tests in 75.35 seconds; all eight CPU/H100 reference checks passed. Python 3.12.13, PyTorch 2.13.0+cu130, CUDA 13.0, NumPy 2.5.1 and the complete locked package set were verified. Driver 580.159.03 and the full device telemetry are recorded.

The analytic original tubes were evaluated at N640, nu=0.0005 on the periodic 2pi box, using float64/complex128 LSRK4, CFL 0.2, max_dt 0.0005 and strict spherical dealiasing |k|<N/3. The N640 preflight advanced 100 steps from 0 to 0.05. A separate process reloaded that same-grid checkpoint and advanced two steps to 0.051. No N512 field was transplanted onto N640.

Independent checks of the downloaded records passed the declared numerical gates on those short intervals. Maximum divergence was 2.77166e-15; maximum tail ratio was 4.79061e-36; maximum interval energy-budget relative residual was 2.10925e-06. The largest absolute instantaneous enstrophy-budget residual was 1.52656e-16. Energy decreased at every sampled interval. No CFL clipping, tiny corrective timestep or clock snap occurred. The minimum achieved timestep, 0.00049999999999999, reflects ordinary endpoint roundoff.

The reload boundary agrees exactly in E, Z, eps, sampled vorticity maximum and BKM; divergence also agrees exactly. The tail ratio differs by1.34e-51, a last-bit difference at a value near 4.79e-36. Checkpoint component and metadata hashes and verified lossless compression are preserved. This checks checkpoint loading and diagnostics; it does not certify bitwise equality of a later uninterrupted H100 trajectory.

The complete local controller proof remains eleven CPU/CUDA rehearsals, including seven independent SIGKILL cases. Those local checks and the cloud preflight do not replace the missing late-time spatial comparison.

## Memory and performance

| Measurement | Observed value |
|---|---:|
| N512 integration benchmark,5 warmup+20 timed steps |0.680966 s/step|
| N640 synchronized integration mean,100 steps |1.644883 s/step|
| N640 forecast rate,maximum of mean and warmed median |1.644908 s/step|
| Always-on diagnostics per event |1.163523 s|
| Selected Fourier estimator per call |6.408691 s|
| Checkpoint write/hash operation |26.035681 s|
| CUDA peak allocated |47.432884 GB|
| CUDA peak reserved |49.578770 GB|
| Driver sampled peak |50.221548 GB/85.520810 GB|
| Driver sampled fraction |58.7244%|
| Slowest measured transfer trial |11.505858 MB/s|

Both allocator and driver measures pass their 80% limits. Driver samples are separated by 0.25 seconds and cannot bound transients between samples. The driver total is 81559 MiB; CUDA reports 85.017494 decimal GB available to its memory interface. Each ratio must use its matching denominator; multiplying a driver fraction by the CUDA total produces only an approximate GB conversion.

The N640/N512 mean-rate ratio is about 2.42 on this host. These measurements do not isolate a radix-5 penalty or a unique cause of host slowdown. Later-timestep/CFL behavior was not observed.

The preflight checkpoint compressed to 985445751 bytes in 39.52 seconds; decompression/component verification took 30.03 seconds. No full production checkpoint transfer was planned or performed.

## Why production was refused

The forecast retains the declared 25% compute margin, 180-second small-evidence reserve, 2100 remaining coarse steps, 400 fine-window steps, 117 always-on events, 31 remaining Fourier estimates and 12 checkpoint operations.

| Component | Raw seconds | With 25% compute margin |
|---|---:|---:|
| Integration | 4112.27 | 5140.34 |
| Always-on diagnostics | 136.13 | 170.17 |
| Selected Fourier estimates | 198.67 | 248.34 |
| Checkpoint write/hash | 312.43 | 390.54 |
| Small-evidence collection reserve |180.00|180.00|
| **Required protected work** | | **6129.38** |

Required time was **102.16 minutes**, against **94.85 usable minutes** after setup/preflight and cleanup allowances: a **7.30-minute shortfall**.

At USD 2.50/hour, the USD 5 all-in cap with a USD 0.50 noncompute reserve limits rental lifetime to 6480 seconds, 108 minutes. The nominal two-hour maximum does not override that financial bound. This is a failed admission forecast, not an observed production overrun or a numerical failure. Removing the 25% margin, shortening required validation after seeing timings or raising the cap would change the declared plan; none was done.

## Limited scientific comparison and remaining uncertainty

Over the six matched preflight events on [0,0.05], N512/N640 maximum relative differences are 6.28e-16 for E and 6.69e-16 for Z. Net-production difference scaled by production-plus-loss is 2.35e-15; full-spectrum L1/E difference is 9.77e-16. Grid-sampled vorticity maximum differs by at most 0.0641%, and BKM by 0.0419%. These maxima are secondary sampling-sensitive observables.

This near-roundoff integral/spectral agreement describes the smooth initial phase. It does not establish N512 resolution during extreme stretching, compare the historical omega maximum near 0.89, provide Fourier peak comparisons at 1.00/1.10, validate a new fine timestep window, or calibrate the later tail gate. The existing N512 accepted interval still ends at 1.10; its first failed sample at 1.11 remains excluded. Spatial consistency near the stretching episode and a converged enstrophy turnover remain unresolved. Nothing here proves regularity or blowup.

If the research is continued later, the single most informative experiment remains the same original-IC N640 comparison with its protected fine window. A lower-priced host or a faster measured rate may admit it. For example, the current timing scenario would fit a full 120-minute lifetime, attainable under the same USD 5 cap at no more than USD 2.25/hour before the live checks. This is a planning scenario, not a reserved offer, a guarantee of speed or authorization for another attempt. Larger grids should wait for this comparison.

## Cost, evidence and closeout

Posted charges for this instance were USD 0.433 at the final closure snapshot. The conservative all-in bound is **USD 0.929173**, approximately USD 0.93, including the retained USD 0.50 allowance; it is not claimed as the exact final bill. Posting may lag. The private project ledger retains pending allowances and zero active campaign commitment. Account credit and separate-project charges remain private.

[Evidence manifest](evidence/2026-10-13/n640_preflight/evidence_manifest.json) binds the collected diagnostic CSVs, full spectra at every preflight/reload event, exact run/configuration records, source/runtime hashes, GPU telemetry, checkpoint metadata/component hashes, timing/transfer records and local independent assessments. All 40 files in the remote collection manifest matched their hashes. Local derived assessments are identified separately.

Raw checkpoint arrays were not downloaded. Their original manifests truthfully describe remote retention at measurement time; after verified instance destruction only metadata/component hashes remain locally. The terminal restart state cannot now be resumed without recomputation. No protected-validation receipt exists, and the published status remains **comparison incomplete / runtime admission refused**.

Historical sources, earlier manifests and completed validation evidence were preserved. The budgeted single attempt is closed, its outcome is published, and the follow-up will be paused after publication.
