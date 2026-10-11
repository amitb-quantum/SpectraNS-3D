#!/usr/bin/env python3
"""Prepare a deterministic source payload locally, without cloud calls or secrets."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

from cloud_policy import verify_audited_sources

ROOT=Path(__file__).resolve().parents[1]


def build(output,root=ROOT):
    verify_audited_sources()
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    paths=[root/name for name in ('pyproject.toml','environment.yml','conda-linux-64.lock',
                                  'requirements-linux-64.lock','README.md')]
    for folder in ('src','scripts','tests','configs','docs'):
        paths.extend(p for p in (root/folder).rglob('*')
                     if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts
                     and p.suffix in ('.py','.sh','.json','.md'))
    blobs={p.relative_to(root).as_posix():p.read_bytes() for p in sorted(set(paths))}
    manifest={name:hashlib.sha256(blob).hexdigest() for name,blob in blobs.items()}
    blobs['payload_manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=output/'spectrans-3d-h100.tar'
    with tarfile.open(archive,'x',format=tarfile.USTAR_FORMAT) as tf:
        for name,blob in sorted(blobs.items()):
            info=tarfile.TarInfo(name);info.size=len(blob);info.mode=0o644
            info.uid=info.gid=0;info.mtime=0;info.uname=info.gname=''
            tf.addfile(info,io.BytesIO(blob))
    report=dict(source_sha256=verify_audited_sources(),files=manifest,
                archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                archive_bytes=archive.stat().st_size,cloud_calls_performed=False)
    (output/'bundle_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    report=build(p.parse_args().output)
    print(f'Local payload prepared: {len(report["files"])} files, SHA256 {report["archive_sha256"]}')
