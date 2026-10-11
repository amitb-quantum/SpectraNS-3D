#!/usr/bin/env bash
# Run with a Python environment containing torch, numpy and pytest.
# No package installation, provisioning, or cloud access.
set -euo pipefail
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1
PYTHON="${PYTHON:-python3}"
OUT="${OUT:-artifacts/validation/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
"$PYTHON" scripts/verify_provenance.py --output "$OUT/reproducibility.json"
"$PYTHON" -m pytest -q tests | tee "$OUT/tests.log"
"$PYTHON" scripts/verify_convergence.py --output "$OUT/convergence.json" > "$OUT/convergence.log"
"$PYTHON" scripts/analyze_runs_v3.py --output "$OUT/archive_summary.json" | tee "$OUT/analysis.log"
for scheme in ssprk3 lsrk4; do
  "$PYTHON" -m ns_fast_v3 --case tgv --N 32 --nu .00625 --target_t .05 \
    --max_dt .005 --log_dt .01 --fp64 --device cpu --scheme "$scheme" \
    --csv "$OUT/${scheme}.csv" --spectrum_csv "$OUT/${scheme}_spectra.csv" \
    --spectrum_stride 1 --budget_csv "$OUT/${scheme}_budgets.csv" \
    --snapshot_times .03,.05 --snapshot_dir "$OUT/${scheme}_snapshots" \
    > "$OUT/${scheme}.log" 2>&1
done
# Optional local GPU testing: no grid larger than 64.
if [[ "${CHECK_LOCAL_GPU:-0}" == 1 ]]; then
  "$PYTHON" scripts/verify_gpu.py --output "$OUT/gpu_checks.json" | tee "$OUT/gpu_checks.log"
fi
printf 'Validation completed; artifacts: %s\n' "$OUT"
