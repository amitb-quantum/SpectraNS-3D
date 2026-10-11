#!/usr/bin/env python3
"""Check every supplied file, and write a reproducibility manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='artifacts/validation/reproducibility.json')
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    inputs=root/'data/original'
    inventory=root/'configs/original_manifest.json'
    original=json.loads(inventory.read_text())
    errors=[name for name,expected in original.items()
            if not (inputs/name).is_file() or sha(inputs/name)!=expected]
    if errors:
        raise SystemExit('Original files changed or missing: '+', '.join(errors))
    candidates=list(root.glob('*'))
    for folder in ('src','scripts','tests','docs','configs'):
        candidates.extend((root/folder).rglob('*'))
    sources={path.relative_to(root).as_posix():sha(path) for path in sorted(candidates)
             if path.is_file() and path.suffix in ('.py','.sh','.md','.json','.yml','.toml','.lock')
             and '__pycache__' not in path.parts}
    import torch
    import numpy
    import pytest
    result=dict(original_files_verified=len(original),original_manifest_sha256=sha(inventory),
                sources=sources,python=sys.version,executable=sys.executable,platform=platform.platform(),
                torch=torch.__version__,cuda=torch.version.cuda,numpy=numpy.__version__,pytest=pytest.__version__,
                gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                note='Archive hashes authenticate the supplied bytes, not historical runtime provenance.')
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(original)} supplied files verified unchanged')


if __name__=='__main__':
    main()
