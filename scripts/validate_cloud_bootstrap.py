#!/usr/bin/env python3
"""Exercise bootstrap relocation, tool metadata, and editable installation locally."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]

def validate(archive,output,full_runtime=False):
    archive=Path(archive).resolve();output=Path(output).resolve()
    manifest=json.loads(archive.with_name('bootstrap_manifest.json').read_text())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=manifest['archive_sha256']:
        raise ValueError('Corrected bootstrap hash mismatch.')
    output.mkdir(parents=True,exist_ok=False)
    env=output/'env';env.mkdir()
    with tarfile.open(archive,'r:gz') as tf:
        tf.extractall(env,filter='data')
    python=env/'bin/python'
    check="import importlib.metadata as m; expected="+repr(manifest['required_build_tools'])+"; assert all(m.version(k)==v for k,v in expected.items()); from setuptools.dist import Distribution; Distribution().get_command_class('dist_info'); print('Build-tool versions, metadata and dist_info entry point verified.')"
    with (output/'validation.log').open('x') as log:
        for command in [
            [str(python),str(env/'bin/conda-unpack')],
            [str(python),'-c',check],
            [str(python),'-m','pip','install','--no-deps','--no-build-isolation','-e',str(ROOT)],
            [str(python),'-m','pip','show','spectrans-3d']]:
            subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    if full_runtime:
        with (output/'full_runtime.log').open('x') as log:
            for command in [
                [str(python),'-m','pip','install','--no-deps','--index-url','https://download.pytorch.org/whl/cu130','torch==2.13.0+cu130'],
                [str(python),'-m','pip','install','--no-deps','-r',str(ROOT/'requirements-linux-64.lock')],
                [str(python),'-m','pip','check'],
                [str(python),str(ROOT/'scripts/verify_runtime.py'),'--output',str(output/'runtime_packages.json')],
                [str(python),'-m','pytest','-q','tests']]:
                subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    result=dict(status='passed',validated_at_utc=datetime.now(timezone.utc).isoformat(),
                archive_sha256=digest,editable_install_source=str(ROOT),
                pyproject_sha256=hashlib.sha256((ROOT/'pyproject.toml').read_bytes()).hexdigest(),
                requirements_sha256=hashlib.sha256((ROOT/'requirements-linux-64.lock').read_bytes()).hexdigest(),
                full_runtime_status='passed' if full_runtime else 'not_requested',
                checks=['relocation','build-tool exact versions','metadata registration','editable project installation'],
                cloud_calls_performed=False)
    (output/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Corrected bootstrap passed local editable-install integration validation.')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True);p.add_argument('--output',required=True)
    p.add_argument('--full-runtime',action='store_true')
    a=p.parse_args();validate(a.archive,a.output,a.full_runtime)
