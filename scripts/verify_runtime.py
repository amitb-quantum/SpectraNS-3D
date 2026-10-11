#!/usr/bin/env python3
"""Verify every locked distribution and Python/CUDA version before simulation."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import torch


def verify(output):
    root=Path(__file__).resolve().parents[1]
    packages={}
    for row in (root/'requirements-linux-64.lock').read_text().splitlines():
        if not row or row.startswith('#'): continue
        name,expected=row.split('==')
        actual=importlib.metadata.version(name)
        if actual.split('+')[0]!=expected: raise ValueError(f'Runtime pin mismatch for {name}')
        packages[name]=actual
    for name,expected in [('pip','26.1.2'),('setuptools','83.0.0'),('wheel','0.47.0')]:
        actual=importlib.metadata.version(name)
        if actual!=expected: raise ValueError(f'Bootstrap version mismatch: {name}')
        packages[name]=actual
    if platform.python_version()!='3.12.13' or torch.version.cuda!='13.0':
        raise ValueError('Python or PyTorch CUDA runtime differs from validated versions')
    if torch.__version__!='2.13.0+cu130':
        raise ValueError('PyTorch wheel differs from validated CUDA 13 build')
    result=dict(python=sys.version,platform=platform.platform(),cuda=torch.version.cuda,
                gpu=torch.cuda.get_device_name(0),torch_build=torch.__version__,packages=packages,status='passed')
    with Path(output).open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print('Exact locked Python/package/CUDA versions verified.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    verify(p.parse_args().output)
