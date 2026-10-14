# N768 first H200 preflight outcome — October 13, 2026

The authorized H200 attempt is closed, with owned-instance absence independently verified. It produced a numerical/memory/restart preflight through t=0.05 and a separate reload test to0.051. It did **not** run the required original-IC trajectory through1.10 or the fine1.00–1.10 comparison. The third-grid scientific milestone remains incomplete.

## Measured result and admission error

H200 NVL offer45315037, instance55853636, GPU-plus120GB storageUSD4.417778/hour. All229 GPU tests and eight CPU/CUDA references passed. N512 benchmark0.326620seconds/step. N768 integration mean1.529961seconds/step.

N768 ordinary timesteps were CFL-controlled near0.000432–0.000438, with118steps to reach0.05:113CFL steps and5event-alignment steps. The minimum recorded dt3.46242e-5 was an event remainder, not a floating-point corrective step. The ordinary minimum was0.000431534521.

The controller inherited N640's cap-limited planning assumption and refused all clipping before calculating a protected forecast. That assumption should have been checked from retained velocity data before renting. This is an operational predictor error, not evidence of numerical instability. The audited solver, CFL0.2 and declared timestep caps were not changed.

N768 allocated81.915881GB and reserved85.607842GB against matching CUDA total150.111977GB. Sampled driver peak57.2779% against its own matching denominator; periodic telemetry does not bound unsampled transients. All remain below80%. Numerical/reload evidence and actual free-disk records are retained.

A separate read-only CFL-aware scenario uses90% of the minimum ordinary dt as a planning floor, counts remaining coarse steps plus one alignment allowance per event, retains400fine steps if cap-limited, includes measured diagnostics/refinement/checkpoint costs,25%compute margin and180seconds collection. It forecasts7594.52seconds (126.58minutes) for the protected remainder. That was **not** the bound admission implementation and did not authorize continued production.

## Closure, evidence and successor

Posted campaign chargeUSD0.974 at fresh reconciliation, conservative upperUSD1.539336; posting can lag. Project postedUSD22.418 plus pending allowancesUSD3.363326 gives conservative exposureUSD25.781326 under the newly approvedUSD40 ceiling. The user subsequently explicitly approved one correctedUSD14 attempt, retaining theUSD40 total and numerical gates. Fresh financing must still pass before create.

[Curated preflight evidence](evidence/2026-10-13/n768_preflight/evidence_manifest.json) preserves exact configurations, source binding, diagnostics/budgets/full spectra, step records, Fourier records, runtime/driver/allocator measurements, checkpoint metadata/component hashes, tests/references/benchmark, admission review and verified termination/financial summary. Arrays were not recovered; hashes do not provide a restart field.

Next: correct the predictor, verify its real-CFL/event-remainder cases and complete source-bound CPU/CUDA failure-path proof; then fresh offer/funding/payload verification and at most the separately approved corrected rental. No further rental follows automatically after that.
