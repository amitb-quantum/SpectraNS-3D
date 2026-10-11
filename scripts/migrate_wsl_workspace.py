#!/usr/bin/env python3
"""Copy preserved Windows baseline to native WSL; never delete either tree."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys


SOURCE=Path(__file__).resolve().parents[1]
DESTINATION=Path('/home/manager/spectrans-3d')
PYTHON=Path('/home/manager/miniforge3/envs/spectrans-3d/bin/python')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if platform.system()!='Linux' or not str(SOURCE).startswith('/mnt/c/'):
        raise SystemExit('Run this migration from the Windows baseline through WSL.')
    if not PYTHON.is_file(): raise SystemExit('Dedicated spectrans-3d environment is missing.')
    if DESTINATION.exists():
        raise SystemExit('Destination already exists; review it before merging. Nothing was overwritten.')
    originals=json.loads((SOURCE/'configs/original_manifest.json').read_text())
    core={name:sha(SOURCE/'src'/name) for name in ('ns_fast_v2.py','ns_fast_v3.py')}
    print('Copying the preserved baseline to '+str(DESTINATION),flush=True)
    shutil.copytree(SOURCE,DESTINATION,symlinks=True,
        ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','*.egg-info','bootstrap_check'))
    for name,digest in originals.items():
        if sha(DESTINATION/'data/original'/name)!=digest:
            raise SystemExit('Original-file verification failed; both trees retained: '+name)
    for name,digest in core.items():
        if sha(DESTINATION/'src'/name)!=digest:
            raise SystemExit('Candidate copy verification failed: '+name)
    evidence=DESTINATION/'artifacts/workspace-migration';evidence.mkdir(parents=True,exist_ok=True)
    result=dict(status='copied_and_hash_verified',source=str(SOURCE),destination=str(DESTINATION),
        at_utc=datetime.now(timezone.utc).isoformat(),original_files_verified=len(originals),
        source_sha256=core,windows_baseline_preserved=True,cloud_resources_created=False)
    (evidence/'migration.json').write_text(json.dumps(result,indent=2)+'\n')
    with (evidence/'editable_install.log').open('x') as log:
        subprocess.run([str(PYTHON),'-m','pip','install','--no-deps','--no-build-isolation','-e',str(DESTINATION)],
                       cwd=DESTINATION,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (evidence/'tests.log').open('x') as log:
        subprocess.run([str(PYTHON),'-m','pytest','-q','tests'],cwd=DESTINATION,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    result['status']='native_workspace_validated'
    (evidence/'migration.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Native WSL workspace validated. Windows baseline remains preserved.',flush=True)


if __name__=='__main__': main()
