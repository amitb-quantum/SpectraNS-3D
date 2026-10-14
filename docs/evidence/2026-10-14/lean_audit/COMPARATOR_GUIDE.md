# Running Comparator on OpenAI's Navier–Stokes formalization

The [statement-fidelity audit](../../../LEAN_STATEMENT_AUDIT_2026-10-14.md) checked what OpenAI's Lean theorems *say*. This guide runs [Comparator](https://github.com/leanprover/comparator), at the commit OpenAI pins, to check that the proofs are *accepted*:
- the solution proves exactly the challenge statements,
- it uses only the permitted axioms,
- it passes the Lean kernel, and nanoda as an independent second kernel.

Steps follow Comparator's README at commit `19e111e`. Expect several hours of compute on first run and roughly 10–20 GB of disk.

## Trust rules from Comparator's README

- **Do not build the solution before Comparator does.** Do not run OpenAI's `lake build`; Comparator builds the solution inside its sandbox. `lake exe cache get` (the Mathlib cache) is acceptable.
- **Run as an ordinary user, not root.**
- Comparator sandboxes the build with **landrun**, which needs the Linux **Landlock** security module, and recommends wrapping the run in **`systemd-run`** to guard against a known landrun issue.

## 1. Check the WSL kernel and systemd

```bash
uname -r
cat /sys/kernel/security/lsm            # must include "landlock"
systemctl --user status >/dev/null && echo "user systemd OK"
```

- **No `landlock`:** the WSL2 kernel may not enable it. The trustworthy route is then a Linux VM or cloud box whose kernel does (recent Ubuntu kernels usually do). Comparator ships `scripts/fake-landrun.sh` for development; using it removes the sandbox, so do so only in a disposable environment, and record that you did.
- **No user systemd:** add `[boot]` and `systemd=true` to `/etc/wsl.conf`, run `wsl --shutdown` from Windows, and reopen.

## 2. Install the tools

```bash
# Lean toolchain manager
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y --default-toolchain none
source ~/.elan/env

# Go 1.24+ and Rust (for landrun and nanoda), if not already present
go version || echo "install Go 1.24+ from https://go.dev/dl/"
cargo --version || curl https://sh.rustup.rs -sSf | sh -s -- -y

mkdir -p ~/lean-audit && cd ~/lean-audit

# landrun, built from main as Comparator requires
git clone https://github.com/Zouuup/landrun && (cd landrun && go build -o landrun cmd/landrun/main.go)

# nanoda: the config sets enable_nanoda, so this second kernel is required
git clone https://github.com/ammkrn/nanoda_lib && (cd nanoda_lib && cargo build --release)

export PATH="$HOME/lean-audit/landrun:$HOME/lean-audit/nanoda_lib/target/release:$PATH"
```

## 3. Fetch OpenAI's formalization at the audited commit

```bash
cd ~/lean-audit
git clone https://github.com/openai/NavierStokesAndEuler && cd NavierStokesAndEuler
git checkout f9e8bc5b38b6e212696e8a30e3e91517af887bbd
sha256sum ComparatorChallenges/NavierStokes.lean   # expect 0cd193b8...a7da61, as in the audit
lake exe cache get                                  # Mathlib cache; Lean 4.34.0-rc2 installs automatically
lake build lean4export                              # the export tool pinned in lake-manifest.json (does not build the solution)
export COMPARATOR_LEAN4EXPORT="$(realpath .lake/packages/lean4export/.lake/build/bin/lean4export)"
```

## 4. Run Comparator

From the repository root, as Comparator's README specifies, keeping a log:

```bash
mkdir -p ~/lean-audit/run && LOG=~/lean-audit/run/comparator_navier_stokes.log
{ date -u; uname -r; cat /sys/kernel/security/lsm; lean --version; git rev-parse HEAD
  (cd ~/lean-audit/landrun && git rev-parse HEAD); (cd ~/lean-audit/nanoda_lib && git rev-parse HEAD); } > "$LOG"
systemd-run --property=RestrictAddressFamilies=~AF_UNIX --user --pty -E PATH="$PATH" \
  -E COMPARATOR_LEAN4EXPORT="$COMPARATOR_LEAN4EXPORT" --working-directory "$(pwd)" \
  -- bash -c 'lake exe comparator ComparatorChallenges/NavierStokes.json' 2>&1 | tee -a "$LOG"
echo "exit status: ${PIPESTATUS[0]}" | tee -a "$LOG"
```

A zero exit status means both theorems, `navier_stokes_breakdown_R3` and `navier_stokes_breakdown_periodic`, were accepted: same statements as the challenge, only `propext`, `Quot.sound` and `Classical.choice`, accepted by the Lean kernel and nanoda.

## 5. Record the outcome

Copy the log into this repository at `docs/evidence/2026-10-14/lean_audit/comparator_run/` and commit it, whatever it shows. Record:
- whether landrun ran with real Landlock or the fake script;
- whether `systemd-run` was used;
- any deviation from these steps.

A failure or a refusal is a result too.
