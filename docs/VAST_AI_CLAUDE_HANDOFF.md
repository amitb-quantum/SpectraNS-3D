# Vast.ai operations handoff for Claude Cowork

Prepared from the SpectraNS-3D scripts and preserved rental records on 2026-10-10 PT. This is an operational handoff, not a request to create an instance. No offer search, rental or job was executed to prepare it.

We used Python REST helpers, then SSH/SCP. The Vast CLI is optional. "Reserve" here means rent an on-demand offer; we did not buy a reserved-term product or use interruptible bids.

**1. Enter the authoritative workspace.**

From Windows PowerShell, open WSL:

```powershell
wsl.exe -d Ubuntu-26.04 -u manager --cd /home/manager/spectrans-3d
```

Then in the WSL shell:

```bash
source /home/manager/miniforge3/etc/profile.d/conda.sh
conda activate spectrans-3d
cd /home/manager/spectrans-3d
RUN_DIR="artifacts/cloud-preparation/$(date -u +%Y-%m-%d)/claude-handoff-$(date -u +%H%M%S)"
mkdir -p "$RUN_DIR"
```

Active development, run data and controller processes belong on the native WSL filesystem. Windows Documents contains preserved baseline files and selected exports. Do not rebind the editable package to /mnt/c. Use the existing authorized terminal/WSL bridge capability; these commands assume an actual WSL shell, not Cowork's unrelated sandbox.

Only one agent should provision at a time. Coordinate the run directory, campaign label, instance ID and budget ledger with the primary development agent before a campaign. Two independent agents must not each commit against the same available budget.

**2. Use the locally stored credential without displaying it.**

The existing key is /home/manager/.config/spectrans-3d/vast-readonly.key. Do not copy it to chat, Windows exports, Git, logs, command-line arguments or the rented host. The helpers read it internally and use an Authorization header. Do not print raw account/key metadata; those responses can contain credentials.

Check permissions and inspect only the helper's sanitized output:

```bash
stat -c '%a %n' /home/manager/.config/spectrans-3d/vast-readonly.key
python scripts/vast_execution_access.py --output "$RUN_DIR/access.json"
```

The file should be mode 600. The filename does not establish provider permissions: the previously inspected key supported broad instance write, while vast_readonly.py itself enforces a read-only endpoint allowlist. A truly read-only key cannot create instances, attach SSH keys or destroy rentals. Reinspect permissions when credentials change. Provider permission categories are described in the [Vast permissions documentation](https://docs.vast.ai/api-reference/permissions).

The one-time --configure-key command exists, but the key is already configured. It refuses to overwrite an existing credential. Do not reconfigure it for this handoff.

**3. Search offers and capture billing evidence. These commands are read-only.**

H100 SXM search:

```bash
python scripts/vast_readonly.py \
  --include-offers \
  --offer-max-hourly 2.1 \
  --output "$RUN_DIR/h100-discovery.json"
```

Broader comparison of H100/H200 variants:

```bash
python scripts/vast_readonly.py \
  --include-offers \
  --broad-hopper \
  --offer-max-hourly 5 \
  --output "$RUN_DIR/hopper-discovery.json"
```

The second number is only a discovery filter, not authority to spend at that rate. Search outputs are created exclusively; use a new filename for every snapshot.

The helper sends POST /api/v0/bundles/ with type="on-demand", one GPU, verified=true, rentable=true, rented=false, reliability2>=0.99, and ascending dph_total. The default GPU filter is H100 SXM; --broad-hopper accepts listed H100/H200 variants with gpu_ram>=80000. It also retrieves all paginated instances and account charges. The [official search API](https://docs.vast.ai/api-reference/search/search-offers) documents the operation and filter operators. Its examples and schema differ in places; retain the exact working query and recorded response rather than guessing field aliases.

The search response does not by itself certify a usable host. Before selection require AMD64, CUDA-driver compatibility for the pinned CUDA 13.0 runtime, adequate actual GPU RAM, at least four effective CPU cores, at least 16 GB host RAM, enough disk for the environment and outputs (we used 80 GB), and transfer charges within reserve. The old helpers filter cuda_max_good>=13; independently verify the real driver with nvidia-smi after connecting. A cheap H200 listing previously had only about 10.86 GB disk capacity and was rejected.

Inspect sanitized offers:

```bash
python - "$RUN_DIR/hopper-discovery.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
for offer in report.get("offers", []):
    raw, storage = offer.get("dph_total"), offer.get("storage_cost")
    upper = None if raw is None or storage is None else raw + 80 * storage / 720
    print({
        "offer_id": offer.get("id"), "gpu": offer.get("gpu_name"),
        "VRAM_reported": offer.get("gpu_ram"),
        "raw_hourly": raw, "conservative_80GB_hourly": upper,
        "cuda_max_good": offer.get("cuda_max_good"),
        "architecture": offer.get("cpu_arch"),
        "host_RAM_reported": offer.get("cpu_ram"),
        "disk_capacity_GB": offer.get("disk_space"),
        "reliability": offer.get("reliability2"),
        "ingress_rate": offer.get("inet_down_cost"),
        "egress_rate": offer.get("inet_up_cost"),
    })
PY
```

Our conservative hourly quote adds 80*storage_cost/720 to dph_total, even if the latter already contains a default disk charge. That may overestimate cost; it avoids omitting the requested allocation. Verify current units before reusing this convention. Ingress means data downloaded by the rented host; egress means data uploaded by the host, including results copied back to WSL.

Refresh the same family query immediately before creating a rental and find its current purchasable offer id locally. Direct id-filter searches were unreliable in our runs. Offer ID, machine ID, host ID and resulting instance ID are different identifiers. Never reuse a historical ID as a current offer. Historical example: offer 50262229 produced instance 55300356; that instance is destroyed and is not available for reuse.

**4. Reconcile the budget and prepare locally before the meter starts.**

Read configs/project_budget.json and the current experiment specification. Account credit is funding, not cumulative spending. Deposits are not expenditure. Reconcile project instance IDs against parent charges, without adding nested component charges again, and retain pending-charge reserves because provider posting can lag. Our invoice CLI output was not useful; the charge API and complete pagination supplied the reconciliation evidence.

The current reconciler can refresh the native ledger before a new run:

```bash
python scripts/reconcile_extension_budget.py --output "$RUN_DIR/budget-refresh"
```

This performs provider reads and writes the local ledger; it does not provision a rental. It expects active instances to have been accounted for and currently refuses an account with active instances. Do not clear commitments or pending reserves to bypass it.

The project ceiling is USD 30. The user's standing instruction permits commitments strictly below USD 10 without a repeated permission request, within the agreed scientific scope. The proposed N640 campaign has its own USD 5 ceiling. This handoff does not enlarge either scope. Use fresh quotes and billing, not the last balance printed in a report.

For cap C, noncompute reserve R and verified GPU-plus-disk rate H, bind the full rental lifetime to floor((C-R)*3600/H), also respecting the experiment's maximum lifetime. For C=5 and R=0.50: 7,200 seconds maximum at USD 2.10/hour; 5,625 seconds at USD 2.88/hour. Include setup, installation, preflight, computation, compression, collection and cleanup. Verify quoted transfer costs fit R; do not assume this reserve is sufficient on every offer.

Prepare the payload locally and do not modify packaged files afterward:

```bash
python -m pytest -q tests
python scripts/verify_provenance.py --output "$RUN_DIR/provenance.json"
python scripts/prepare_h100_bundle.py --output "$RUN_DIR/payload"
```

As of the readiness review, 119 local tests pass and all 46 supplied original files are unchanged. Test counts can grow; record the exact result from the newly packaged source version.

Reusable bootstrap:
- /home/manager/spectrans-3d/artifacts/cloud-preparation/2026-10-10/bootstrap_repaired/spectrans-3d-bootstrap.tar.gz
- /home/manager/spectrans-3d/artifacts/cloud-preparation/2026-10-10/bootstrap_validation_004/validation.json

The validation has both status="passed" and full_runtime_status="passed". Existing controllers verify its archive hash, pyproject hash and dependency-lock hash. If those contracts change, validate the new bootstrap locally with scripts/validate_cloud_bootstrap.py --archive ARCHIVE --output NEW_DIRECTORY --full-runtime before paying for setup.

The previous image was pinned by digest:
vastai/base-image@sha256:82a53405a50901ab7e462a80ddde335a8f927a90bdab5cdea9006f02cb858a3e
This is a historical reproducibility reference, not a claim that it is the latest image. Confirm availability and compatibility.

**5. Rent through a reviewed controller, with a guard already armed.**

Our local controller writes quote.json, approval.json, the ledger snapshot and controller_state.json, creates a unique Ed25519 key and campaign label, then starts an independent WSL watchdog. It waits for guard_ready.json before making the billable call.

The reservation operation inside the controller is:

```python
receipt = api("PUT", f"/api/v0/asks/{offer_id}/", {
    "image": pinned_image_digest,
    "label": unique_campaign_label,
    "disk": 80,
    "runtype": "ssh",
    "target_state": "running",
    "cancel_unavail": True,
    "onstart": install_public_ssh_key_command,
})
instance_id = receipt["new_contract"]
```

This is an explanatory fragment, not a standalone budget-safe launcher. The [create-instance API](https://docs.vast.ai/api-reference/instances/create-instance) uses an offer ID and returns new_contract. Save the receipt and instance ID immediately. If creation times out, look for the unique label before retrying: the provider may have created the instance even though the response was lost.

Current project controllers are restricted:
- scripts/run_vast_smoke.py and launch_h100_smoke.py: the fixed N128/N256 smoke campaign.
- scripts/run_vast_followup.py and launch_timestep_followup.py: the fixed N256/N512 temporal campaign.
- scripts/run_vast_extension.py and launch_enstrophy_extension.py: the fixed N512 bounded extension.

Read each controller's --help and its policy before any --execute command. They require --job-dir, --offer-id, --environment, --payload, --image and --bootstrap-validation. A controller job directory must not already exist.

The old extension controller is a USD 3 corrected-retry controller with a 4,200-second guard; it is NOT a generic USD 5/N640 runner. Its --offer-id is a preference: it may select another currently eligible offer when that ID is absent. Do not mistake that parameter for a hard offer lock.

N640 currently has a reviewed proposal, not a completed provisioning launcher. Read docs/N640_READINESS_REVIEW.md and configs/n640_refinement_proposal.json. A separate source/config-bound N640 controller must implement that plan. Do not loosen the old launcher's limits, change audited solver bytes, or assume changing an N value establishes authorization. N768/N1024 are outside this handoff.

**6. Connect, bootstrap, verify, then execute.**

The controller attaches the generated PUBLIC key with POST /api/v0/instances/{instance_id}/ssh/ and polls its uniquely owned instance for ssh_host and ssh_port. A provider "running" flag alone is insufficient: verify a real SSH command succeeds. The [SSH attachment API](https://docs.vast.ai/api-reference/instances/attach-ssh-key) documents the public-key operation.

Connection shape (substitute the recorded endpoint, not a guessed direct port):

```bash
ssh -p SSH_PORT -i LOCAL_PRIVATE_KEY \
  -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=LOCAL_CAMPAIGN_KNOWN_HOSTS \
  root@SSH_HOST 'nvidia-smi'
```

Keep host checking and a dedicated known-hosts file. accept-new accepts the first observed key, not independent host attestation; do not disable changed-key checking.

Upload the verified bootstrap/source archive and nonsecret approval/ledger records. The remote layout was:
- /opt/spectrans-3d/env
- /opt/spectrans-3d/project
- /opt/spectrans-3d/results

Remote setup verifies archive SHA256, extracts safely, runs conda-unpack, installs exact pinned dependencies and the editable project, runs pip check, and records scripts/verify_runtime.py output. We used torch==2.13.0+cu130 from the official cu130 wheel index plus requirements-linux-64.lock; use the project lock and bootstrap contract rather than "latest". The Vast host supplies the NVIDIA driver.

Run the full tests and eight CPU/H100 reference checks before a small production-configuration preflight. Capture allocator memory AND nvidia-smi driver usage; both must remain under 80%. The N640 plan requires actual timings for all diagnostics, spectrum and checkpoint/reload operations, then a remaining-runtime forecast with safety margin. A job timeout is not an instance-lifetime control.

For a generic job, the remote command shape is an explicit pinned Python executable, a reviewed command/config, a fresh output directory, and a controller-enforced timeout:

```bash
cd /opt/spectrans-3d/project
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  /opt/spectrans-3d/env/bin/python REVIEWED_JOB.py REVIEWED_ARGUMENTS
```

The actual project launchers invoke controlled jobs; do not substitute a raw solver invocation that bypasses their financial, numerical or memory checks. Preserve the precise command and exit status.

**7. Collect promptly, destroy, verify absence, then reconcile.**

Copy diagnostic CSVs, full spectra, manifests, runtime package records, step/stage timings and GPU telemetry first. Collect only approved full-field checkpoints; archive all checkpoint metadata and hashes before pruning new campaign arrays. Never prune existing historical evidence.

Use lossless gzip level 1 rather than a huge raw archive:

```bash
tar -I 'gzip -1' -cf /opt/spectrans-3d/results.tar.gz \
  -C /opt/spectrans-3d results runtime_packages.json
```

For N640, enforce the one-accepted-checkpoint collection plan before archiving. Download with SCP (uppercase -P selects its port), extract with a safe tar filter, and verify each decompressed file against its recorded SHA256. SSH uses lowercase -p.

The N512 extension's approximately 9.7 GB raw transfer was too slow through the relay. Lossless parallel component compression reduced transfer to approximately 1.51 GB, and all original file hashes were recovered. Original collection errors remain recorded alongside the verified alternative collection. A nonzero parent controller exit is not scientific failure by itself, and is not proof of success either: inspect computation, collection, verification and termination independently.

Finally call destroy_owned(state), which matches the unique campaign label and instance ID before DELETE /api/v0/instances/{id}/. Never delete all account instances. Downloaded state files carry the ownership evidence. Do not trust the deletion receipt alone: retrieve the complete paginated instance list and verify this instance is absent, then save the after-destruction snapshot and termination record. The [destroy API](https://docs.vast.ai/api-reference/instances/destroy-instance) deletes the rental permanently; the [instance-list API](https://docs.vast.ai/api-reference/instances/show-instances) is paginated.

Stopping Python, disconnecting SSH or stopping an instance is not cleanup. Container storage continues billing while stopped and disappears on instance destruction. Persistent volumes have separate lifetimes and billing. See [Vast storage behavior](https://docs.vast.ai/guides/instances/storage/types).

If collection cannot finish by the spending deadline, secure small records first, label missing fields/partial collection accurately, and let the owned-instance guard terminate on time. Do not extend the rental to rescue collection without a new bounded commitment.

The watchdog is independent of the controller PROCESS, not of the Windows machine, WSL, network or API. Keep the machine awake and WSL running; there is no provider-enforced expiration in these creation calls. If local cleanup/verification fails, use the Vast console to destroy the exact recorded rental and verify it is gone.

After closure, refresh provider charges using the campaign-aware reconciler:
```bash
python scripts/reconcile_extension_budget.py \
  --output "$RUN_DIR/budget-after" \
  --campaign "$RUN_DIR/campaign"
```
Use this only for the corresponding supported campaign state/quote format; adapt the new N640 closure policy explicitly. Do not count new campaign postings as settlement of unrelated old pending charges.

**8. Gotchas to remember.**

- Search is not rental: POST /bundles is discovery; PUT /asks/{offer_id} starts the billable commitment.
- API URLs in our helpers include trailing slashes. Redirects are refused so authorization headers cannot accidentally follow a redirect. Use the canonical working URL.
- Paginate both instances and charges. Epoch zero was rejected by the charge endpoint, so the helper uses a positive lower bound.
- Raw responses can include keys/tokens. Use the sanitized helpers, not indiscriminate JSON dumps.
- Environment packing originally omitted build-tool metadata, breaking editable installation. Use the repaired bootstrap with its full-runtime validation proof.
- CUDA devices must resolve to an explicit index for set_device; bare "cuda" caused the first extension startup failure and is now corrected.
- Host speed varies even for the same H100 name. Record UUID, driver, clocks, power, throttle state and measured stage timings.
- Allocator-reserved memory does not include every driver allocation. Plan and monitor using driver memory as well.
- All setup, idle, compression and collection time consumes rental lifetime.
- "Verified" and reliability scores are filters, not numerical or performance validation.
- A completed solver exit does not prove gates passed, complete data collection, or rental termination.
- Never run concurrent spending controllers, silently retry an ambiguous create, reuse stale payload hashes, or overwrite previous result directories.

The official [Vast CLI repository](https://github.com/vast-ai/vast-cli) offers search/create/show/stop/destroy commands. It is an alternative interface, not an additional requirement for our REST workflow. Avoid installing it into the locked solver environment just to follow this guide, and never paste a key into a command example.

Suggested instruction to Claude: "Read this guide, the native WSL handoff, current budget ledger and N640 specification. Use read-only discovery first and report eligible offers with full costs. Preserve all prior evidence. Reuse the local credential without displaying it. Coordinate one controller with Codex. Do not provision until the reviewed experiment has a source/config-bound launcher, fresh budget/quote, armed ownership-checked watchdog, and complete collection/termination plan. Respect the USD 30 project ceiling and USD 5 N640 cap."
