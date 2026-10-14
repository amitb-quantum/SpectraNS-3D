# Selected reproducibility evidence

The October 11 snapshot contains the native 160-test result, isolated packaged CPU result (156 passed, four CUDA tests skipped), the eight-case CPU/CUDA real-process rehearsal receipt, its exact Python/config source binding, audited numerical hashes, measured disk assumptions and 46-original-file provenance confirmation.

These are recorded local checks, not a live H100/N640 validation. Rehearsal termination entries use the local mock provider; five cases actually killed the local controller/process groups. A fresh checkout can rerun the suite and the rehearsal harness. Full original archive verification requires the locally preserved original inputs.

Four small original N512 campaign files are intentionally tracked under artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse/: diagnostics.csv, enstrophy.csv, spectra.csv and run.json. Their SHA256 values are bound in configs/n512_interpolated_peak_reference.json. They preserve accepted samples and the first failing event; historical_reference() independently excludes the failure from its comparison. run.json identifies fields that were retained locally; their multi-gigabyte arrays are not included in Git.

Beyond the explicit dated evidence folders, generated artifacts, source payload archives, restart arrays, API credentials, private SSH keys and the live financial ledger stay local. Figures and dated reports are under docs/. The project preserves the complete local evidence rather than replacing it with these selected exports.

Run the following in your checkout with the validated environment:

    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m pytest -q tests
    python scripts/rehearse_refinement.py --cuda --output artifacts/rehearsal_NEW

The CUDA rehearsal requires a compatible local GPU. The existing rehearsal fingerprint binds all Python sources/tests and the three specified scientific configuration/reference files. Documentation-only changes do not invalidate that fingerprint, but any changed cloud-payload member requires a fresh payload manifest before provisioning.

## October 13 completed comparison

The [N640 report](../N640_COMPARISON_2026-10-13.md) and [curated manifest](2026-10-13/n640_campaign_004/evidence_manifest.json) preserve the completed original-IC comparison through 1.10 and its fine 1.00–1.10 window. 192 H100 tests and eight backend references passed; the protected 131-file manifest and independent numerical/temporal/spatial arithmetic are replayable from the public data. Enstrophy met 0.1% agreement, while net-production curves showed intermediate sensitivity and the stable matched local peak at 1.00 was discretization-sensitive. Neither two-grid consistency nor a passing tail gate certifies continuum resolution.

The new readiness snapshot retained 192 local tests, 188 packaged passes with four CUDA-only skips, and eleven CPU/CUDA rehearsals including seven real SIGKILL phases. Earlier dated 160/185-test and preflight-only snapshots remain historical evidence. Full N640 arrays were not downloaded; metadata/component hashes cannot replace a restart field. The only new rental is destroyed, billing reconciled and follow-up paused.


## October 13 completed three-grid release

The [N768 report](../N768_THREE_GRID_COMPARISON_2026-10-13.md) and [148-file curated package](2026-10-13/n768_campaign_002/evidence_manifest.json) retain all 132 original protected manifest entries, original phase CSVs, full spectra, checkpoint metadata/component hashes, source/runtime bindings, independent assessment, figure and sanitized financial/termination records. The corrected run passed 239 H200 tests and eight backend references; local temporal sensitivity passed. N640/N768 integral curves meet 0.1%, while matched stable local peaks remain sensitive. No continuum error bound or turnover is claimed.

Reanalysis is CPU-only and makes no cloud request:

    python docs/evidence/2026-10-13/n768_campaign_002/independent_analysis.py --campaign docs/evidence/2026-10-13/n768_campaign_002

The raw N768/N640 arrays were not recovered. Metadata hashes are identity evidence, not restartable fields or independently repeatable field interpolation. All original histories remain preserved locally; credentials, private account attribution and the live ledger are excluded.


## October 14 spectral resolution addendum

[The addendum](../SPECTRAL_RESOLUTION_ADDENDUM_2026-10-14.md) is a post-hoc analysis of the three accepted coarse spectra already published here; it runs no simulation and modifies no campaign evidence. Its outputs under [2026-10-14/spectral_resolution/](2026-10-14/spectral_resolution/) are `grid_disagreement.csv`, `strip_fit.csv`, `summary.json` and the figure. The script verifies every input hash before use:

    python analysis/spectral_resolution.py --output docs/evidence/2026-10-14/spectral_resolution
    python -m pytest -q analysis

