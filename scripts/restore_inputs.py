#!/usr/bin/env python3
"""Restore only expected, hash-verified regular files from supplied archives."""
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile


def restore(root=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parents[1]
    target=(root/'data/original').resolve()
    manifest=json.loads((root/'configs/original_manifest.json').read_text())
    archives={
        'ns_regularity_upgrade_v1.zip': '',
        'ns_audit_package.tgz': 'historical/audit_package/',
        'ns_campaign_results.tgz': 'historical/campaign_results/',
    }
    for name in archives:
        if hashlib.sha256((target/name).read_bytes()).hexdigest()!=manifest[name]:
            raise ValueError(f'Archive checksum mismatch: {name}')
    def write(name, data):
        path=(target/name).resolve()
        if not path.is_relative_to(target) or name not in manifest:
            raise ValueError(f'Unexpected archive member: {name}')
        if hashlib.sha256(data).hexdigest()!=manifest[name]:
            raise ValueError(f'Member checksum mismatch: {name}')
        if path.exists():
            if path.read_bytes()!=data:
                raise ValueError(f'Refusing to overwrite differing file: {name}')
            return
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:
            f.write(data)
        path.chmod(0o444)
    for archive,prefix in archives.items():
        if archive.endswith('.zip'):
            with zipfile.ZipFile(target/archive) as z:
                for info in z.infolist():
                    if not info.is_dir():
                        write(prefix+info.filename,z.read(info))
        else:
            with tarfile.open(target/archive) as tar:
                for member in tar.getmembers():
                    if member.isdir():
                        continue
                    if not member.isfile():
                        raise ValueError(f'Non-regular archive member: {member.name}')
                    with tar.extractfile(member) as f:
                        write(prefix+member.name,f.read())
    for name,expected in manifest.items():
        if hashlib.sha256((target/name).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Restored file mismatch: {name}')
    print(f'{len(manifest)} original files verified and available in {target}')


if __name__=='__main__':
    restore()
