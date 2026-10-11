# Dedicated WSL environment

Environment: `spectrans-3d`, located at
`/home/manager/miniforge3/envs/spectrans-3d` on this machine.
Project: `/home/manager/spectrans-3d`.

The previous `kernelproof` environment was inspected but not modified.
The new environment was built separately without unrelated project packages.
It uses Python 3.12.13, PyTorch 2.13.0 (CUDA 13 build), NumPy 2.5.1 and
pytest 9.1.1. Exact Conda builds are in `conda-linux-64.lock`; pip versions
are in `requirements-linux-64.lock`. `environment.yml` is the readable
recreation entry point. See the official
[Conda environment guide](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html).

```bash
conda activate spectrans-3d
cd /home/manager/spectrans-3d
python -m pip check
python -m pytest -q
```

From a noninteractive Windows shell:

```powershell
wsl.exe -d Ubuntu-26.04 -u manager -e bash -lc 'cd /home/manager/spectrans-3d && /home/manager/miniforge3/envs/spectrans-3d/bin/python -m pytest -q'
```

The editable installation points at `src/`. Solver edits take effect without
reinstallation. Metadata changes require rerunning
`python -m pip install --no-deps --no-build-isolation -e .`.
The [Python packaging guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
documents the `pyproject.toml` format.

The earlier audit's runtime description is historical. New environment
validation is in `artifacts/validation/spectrans-env/`. All new work should
use this dedicated environment.

For historical analysis in a fresh checkout, place the three supplied
archives in `data/original/` and run `python scripts/restore_inputs.py`.
Restoration verifies archive and member hashes and refuses to overwrite
differing content. Unit tests need no historical archives.
