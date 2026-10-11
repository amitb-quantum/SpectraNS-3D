#!/usr/bin/env python3
"""Restore exact build-tool metadata in a preserved minimal bootstrap."""
import argparse
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import sys
import tarfile

EXPECTED={'pip':'26.1.2','setuptools':'83.0.0','wheel':'0.47.0'}
BASE_SHA256='c6e6e89e416f4a435b9b13dea72f9c4d34d7d4f330efdf792b87b6d63c3f2f95'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def prepare(base,output):
    base=Path(base);output=Path(output)
    if sha(base)!=BASE_SHA256:
        raise ValueError('Base archive does not match the preserved bootstrap.')
    output.mkdir(parents=True,exist_ok=False)
    archive=output/'spectrans-3d-bootstrap.tar.gz'
    added={}
    with tarfile.open(base,'r:gz') as source,tarfile.open(archive,'x:gz') as target:
        names=set()
        for member in source:
            names.add(member.name)
            target.addfile(member,source.extractfile(member) if member.isfile() else None)
        for package,version in EXPECTED.items():
            dist=importlib.metadata.distribution(package)
            if dist.version!=version:
                raise ValueError('Build-tool version mismatch: '+package)
            metadata=Path(dist._path)
            for path in sorted(metadata.rglob('*')):
                if not path.is_file():
                    continue
                relative=path.relative_to(Path(sys.prefix)).as_posix()
                if relative in names:
                    continue
                blob=path.read_bytes()
                info=tarfile.TarInfo(relative)
                info.size=len(blob);info.mode=0o644;info.mtime=0
                target.addfile(info,io.BytesIO(blob))
                added[relative]=hashlib.sha256(blob).hexdigest()
    report=dict(base_sha256=sha(base),archive_sha256=sha(archive),
                archive_bytes=archive.stat().st_size,restored_metadata=added,
                required_build_tools=EXPECTED,cloud_calls_performed=False)
    (output/'bootstrap_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Prepared corrected bootstrap; restored metadata files:',len(added))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();prepare(a.base,a.output)
