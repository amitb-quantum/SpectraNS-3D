# Selected reproducibility evidence

The October 11 snapshot contains the native 160-test result, isolated packaged CPU result (156 passed, four CUDA tests skipped), the eight-case CPU/CUDA real-process rehearsal receipt, its exact Python/config source binding, audited numerical hashes, measured disk assumptions and 46-original-file provenance confirmation.

These are recorded local checks, not a live H100/N640 validation. Rehearsal termination entries use the local mock provider; five cases actually killed the local controller/process groups. A fresh checkout can rerun the suite and the rehearsal harness. Full original archive verification requires the locally preserved original inputs.

Four small original N512 campaign files are intentionally tracked under artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse/: diagnostics.csv, enstrophy.csv, spectra.csv and run.json. Their SHA256 values are bound in configs/n512_interpolated_peak_reference.json. They preserve accepted samples and the first failing event; historical_reference() independently excludes the failure from its comparison. run.json identifies fields that were retained locally; their multi-gigabyte arrays are not included in Git.

All other generated artifacts, source payload archives, restart arrays, API credentials, private SSH keys and the live financial ledger stay local. Figures and dated reports are under docs/. The project preserves the complete local evidence rather than replacing it with these selected exports.

Run the following in your checkout with the validated environment:

    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m pytest -q tests
    python scripts/rehearse_refinement.py --cuda --output artifacts/rehearsal_NEW

The CUDA rehearsal requires a compatible local GPU. The existing rehearsal fingerprint binds all Python sources/tests and the three specified scientific configuration/reference files. Documentation-only changes do not invalidate that fingerprint, but any changed cloud-payload member requires a fresh payload manifest before provisioning.
