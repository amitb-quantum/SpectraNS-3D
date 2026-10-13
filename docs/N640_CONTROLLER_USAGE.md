# SpectraNS-3D N640 controller usage

The authoritative project is /home/manager/spectrans-3d in native WSL, with the spectrans-3d Conda environment. Windows Documents receives selected review exports. The v2/v3 solver sources and historical campaigns remain unchanged. This controller is separate from the earlier grid-restricted smoke and N512 extension launchers.

## What this experiment protects

N640 starts from the original analytic tubes at viscosity 0.0005, float64, LSRK4, CFL 0.2 and a 0.0005 timestep cap. It must reach accepted t=1.10, then rerun 1.00–1.10 from its own coarse t=1.00 checkpoint with cap 0.00025. Those processes run sequentially. The local temporal tolerance is 1e-5; it concerns continuation error from a shared anchor, not accumulated error inherited at the anchor.

The controller compares the accepted N512/N640 Z and scaled net-production curves through 1.10 at the declared 0.1% tolerance. Scientific disagreement is a useful result and is recorded separately from numerical/temporal validation. Energy, full-shell spectra, grid maxima and grid BKM have separate secondary screens. Net-production peak fits are supplementary and may be inconclusive if not bracketed.

Fourier-refined local vorticity peak estimates are compared at matched t=1.00 and 1.10. N512 fields at those times were preserved; there is no field for its historical t=0.89 sampled peak. Sampled maxima are recorded at every event. Refined estimates and sensitivity checks are computed every 0.05, at each coarse event 0.86–0.94, and at the fine endpoints 1.00/1.10. Unselected estimator fields remain explicitly empty. There are 31 coarse estimates and 2 fine estimates;2 coarse estimates are supplied by preflight, leaving 31 future calls. The method searches 8 then 16 sampled candidate neighborhoods with direct separable Fourier evaluation, a four-cell initial radius and nine refinements. The 1e-5 stability checks are empirical sensitivity checks, not rigorous global-maximum error bounds. Matched peak agreement is a primary observable only when both estimators are stable; otherwise it is explicitly inconclusive.

Every event includes the full rounded-shell spectrum and lower/center/upper k^4 dissipation shares for k>=128 and N640 k>=160. Existing finite, energy budget, divergence, Parseval, tail and instantaneous enstrophy-identity gates remain unchanged.

## Protected collection and optional exploration

Exact requests, source/config fingerprints, runtime versions, diagnostic CSVs, all event spectra, interpolation records, GPU telemetry, timing categories, achieved timesteps, checkpoint metadata/component hashes and assessments are frozen together. Every checkpoint.json is archived before any new checkpoint arrays are pruned.

Small artifacts are copied and hash-verified in native WSL before exploration. This protected snapshot is immutable. Full production checkpoint archives/downloads are disabled by default in the current plan; all checkpoint metadata and component hashes are retained. Exploration reloads the coarse t=1.10 state, in a separate process, and can stop anywhere before the optional t=1.50 ceiling. No temporal certification is implied beyond 1.10.

Two actual 64 MiB incompressible downloads measure the rented SSH link. The slowest rate, actual N640 compression time/size, and measured verification time determine collection allowances. Allowances include compression and verification even when some work is already complete. The optional-transfer paths remain available for local rehearsal coverage. If explicitly enabled in a future source-bound plan, background download overlaps exploration only when 1.25 times the larger allowance, plus 120 seconds cleanup, fits the remaining lifetime. Otherwise collection runs sequentially and exploration is shortened or skipped. Missing optional arrays are never labelled recovered.

## Rehearse without renting

From WSL:

```bash
cd /home/manager/spectrans-3d
conda activate spectrans-3d
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m pytest -q tests
python scripts/verify_provenance.py
python scripts/rehearse_refinement.py --cuda --output artifacts/rehearsal_NEW
```

Use a new output directory each time. N64 CPU uses TGV to exercise unchanged gates at a small grid; N256 local CUDA uses the production tubes. Both use a compressed timeline. These test orchestration, restart and evidence survival, not N640 convergence. The harness independently SIGKILLs actual controller/worker processes during preflight advancement, coarse advancement, prefix assembly, fine advancement, small-artifact transfer, checkpoint transfer and exploration advancement. It verifies partial files are not promoted and that protection survives only after verified collection. Sequential, overlap and metadata-only success paths are exercised, plus N256 CUDA success: eleven cases including seven real SIGKILLs.

The proof contains a complete source/config fingerprint. Any change to Python source, tests, acceptance configuration, refinement plan or matched reference invalidates it and requires a new rehearsal. The provider guard additionally handles controller absence and deadlines. Production forbids rehearsal fault hooks.

## Prepare and review the cloud payload

```bash
python scripts/prepare_refinement_bundle.py --output artifacts/payload_NEW
python scripts/run_vast_refinement.py
```

The second command prints the plan only. It does not read a credential, search offers, provision or modify the ledger. The dedicated payload includes source/config/tests/docs and four small hash-bound historical N512 comparison inputs. It excludes original checkpoint arrays, private SSH keys and the Vast credential.

The current restricted credential remains at /home/manager/.config/spectrans-3d/vast-readonly.key, mode 0600. The filename does not determine the actual provider permissions. Only the authorized WSL controller reads it; no credential is sent to the GPU instance or placed in an artifact.

## Billable command and safeguards

The source-bound launcher requires an explicitly selected live offer. It never substitutes another offer automatically. A new run needs the current complete CPU/CUDA rehearsal proof, a verified immutable bootstrap, an immutable image digest, a newly built matching payload, fresh complete billing, and the standing user spending authorization.

Command shape (replace every placeholder with verified local paths or the selected offer ID):

```bash
python scripts/run_vast_refinement.py --execute \
  --job-dir artifacts/cloud-preparation/2026-10-11/N640_RUN_NEW \
  --offer-id VERIFIED_LIVE_OFFER_ID \
  --rehearsal artifacts/REHEARSAL_NEW/rehearsal.json \
  --environment artifacts/cloud-preparation/2026-10-10/bootstrap_repaired/spectrans-3d-bootstrap.tar.gz \
  --bootstrap-validation artifacts/cloud-preparation/2026-10-10/bootstrap_validation_004/validation.json \
  --payload artifacts/PAYLOAD_NEW/spectrans-3d-n640.tar \
  --image vastai/base-image@sha256:82a53405a50901ab7e462a80ddde335a8f927a90bdab5cdea9006f02cb858a3e
```

This command is billable. Its fixed contract is one H100 with at least 80 GB advertised GPU memory, CUDA 13 support, verified host/reliability >=0.99, adequate CPU/RAM/disk, <=USD2.60/hour GPU plus conservative 64 GB disk, USD0.50 transfer/cleanup reserve, <=USD5 new total commitment and <=USD30 project exposure. The provider lifetime bound includes startup. The independent ownership-bound destroy guard arms before creation and triggers 60 seconds before the financial lifetime bound; normal operations reserve 120 seconds cleanup. Source/config and provider deadlines are bound into each worker request.

Preflight reruns the tests and CPU/H100 references, measures a separate-process N512 five-warmup/twenty-step integration benchmark, runs N640 from the original IC for 100 steps with every-event diagnostics and selected Fourier estimates, verifies exact checkpoint reload, retains the t=0.05 state for coarse continuation, measures transfer/compression/verification, and forecasts the required prefix plus fine window with a 25% compute margin. Production is refused if it does not fit. Achieved timing and clipping are reforecast at each event. Continuous driver sampling and allocator peaks must both stay below 80%.

There is no automatic retry, deadline extension, N768 or N1024 path. The controller records owned-instance deletion and verifies provider absence separately from scientific validation. Provider API/network outages can prevent timely deletion; the guard retries and the spending commitment stays reserved until verified closure. Keep WSL/Windows awake and connected. Only one agent should control provisioning and the project ledger; the new launcher holds an exclusive local execution lock.

Reconcile posted parent charges plus conservative unposted bounds after destruction. Credit is a funding check, never cumulative project spend. A new campaign's posted charges cannot consume an older campaign's pending reserve. Ambiguous create responses retain the commitment and require reconciliation rather than an automatic retry.

## Historical implementation evidence

The full implementation/rehearsal report and sealed receipts are in artifacts/cloud-preparation/2026-10-10/n640_implementation_001/. Review N640_IMPLEMENTATION_REHEARSAL_REPORT.md, final test/provenance logs, matched_n512_peaks_003/reference.json and sealed_rehearsal_matrix_004/rehearsal.json. Local and file-transport checks do not establish a live provider's speed, available memory or network reliability; those remain measured preflight gates.


## Offer watch and October 11 policy revision

The maximum combined GPU/storage search price is now USD2.60/hour. This is screening only: a measured forecast of the mandatory original-IC prefix, the fine window and verified small collection must fit the remaining guarded lifetime. No full t=1.5 exploration is required. At USD2.60/hour the financial lifetime is 6,230 seconds; subtract 60 seconds for the early destroy guard and 120 seconds for normal cleanup, leaving 6,050 seconds before accounting for startup/preflight. A 5,600-second forecast inflated by 10% costs USD4.949 with the USD0.50 reserve, but if guard and cleanup are additional its exposure is USD5.079. The preflight's 25% compute margin is retained.

The requested disk is 64 GB. The existing retention schedule can keep six raw states across coarse and exploration, totaling 37,866,703,104 bytes. Compression pinning on the GPU uses hard links, so it does not duplicate a raw state; local compressed-file verification during preflight can temporarily unpack one state but does not coincide with exploration. The conservative runtime bound is 46,186,703,104 bytes, including one 6.32 GB compressed archive and 2 GB of small-artifact allowance. Remote available space must exceed 55,424,043,725 bytes (20% margin) both after setup and after preflight retention. The live check accounts for installed packages/image occupancy via actual available space; its record is copied to WSL before a failed gate raises an error. A quote cannot certify the host's available disk space.

Run one read-only check from native WSL:

```bash
cd /home/manager/spectrans-3d
/home/manager/miniforge3/envs/spectrans-3d/bin/python scripts/poll_refinement_offers.py
```

The attached Codex heartbeat repeats this command every 30 minutes. It only searches the read-only bundles endpoint with the locally stored key, saves sanitized timestamped reports under artifacts/offer-watch, and deduplicates identical offers/prices and repeated errors. A qualifying quote remains provisional until fresh billing, current rehearsal/payload bindings and measured preflight pass. The watch neither provisions/deletes instances nor reserves budget, and does not update scientific sources.

Sampling-sensitive secondary grid maxima remain separate from primary Z/net-production consistency and stable matched Fourier peak estimates. A borderline 1% sampled-maximum screen is sampling-inconclusive, not sufficient evidence of spatial under-resolution. The retained endpoint biases do not determine a physical core width or the historical t=0.89 interpolation bias.

The October 10 implementation report remains historical evidence. Current policy validation and the newly sealed proof/payload are under artifacts/cloud-preparation/2026-10-11/n640_offer_policy_001/.


## October 12 selective sampling and verified continuation

The current scientific/workflow contract is [N640 sampling and continuation](N640_SAMPLING_CONTINUATION_2026-10-12.md). Keep the original 0–0.05 preflight checkpoint until coarse continuation is independently joined with preserved prefix evidence. Production starts at 0.05 on the same grid and cap; its complete assembled comparison still covers 0–1.10. Fine validation remains 1.00–1.10. A previous campaign's deleted fields cannot be reused.

The current local proof is under artifacts/cloud-preparation/2026-10-12/n640_sampling_revision_001/sealed_rehearsal_003/. Older proofs do not bind these revised sources/configuration. Sampled maxima, all numerical gates and full spectra remain at every event. Fourier estimates use the predeclared subset; full production field downloads are off. Fresh measured preflight determines whether the revised protected forecast fits.
