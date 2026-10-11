#!/usr/bin/env python3
"""Deterministic N640 payload: source plus four hash-bound small N512 evidence files."""
import argparse,hashlib,io,json,tarfile,tempfile
from pathlib import Path
from prepare_h100_bundle import build as base_build
from cloud_policy import ROOT,verify_audited_sources
from extension_state import sha

def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="refinement-payload-",dir=output) as temporary:
        base=Path(temporary)/"base";base_build(base)
        with tarfile.open(base/"spectrans-3d-h100.tar") as tar:
            blobs={m.name:tar.extractfile(m).read() for m in tar.getmembers()}
    blobs.pop("payload_manifest.json")
    reference=json.loads((ROOT/"configs/n512_interpolated_peak_reference.json").read_text())
    directory=ROOT/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse"
    for name,digest in reference["historical_small_files_sha256"].items():
        path=directory/name
        if sha(path)!=digest:raise ValueError("historical evidence changed")
        blobs[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    files={name:hashlib.sha256(blob).hexdigest() for name,blob in sorted(blobs.items())}
    blobs["payload_manifest.json"]=(json.dumps(files,indent=2)+"\n").encode()
    archive=output/"spectrans-3d-n640.tar"
    with tarfile.open(archive,"x",format=tarfile.USTAR_FORMAT) as tar:
        for name,blob in sorted(blobs.items()):
            info=tarfile.TarInfo(name);info.size=len(blob);info.mode=0o644
            info.uid=info.gid=0;info.mtime=0;info.uname=info.gname=""
            tar.addfile(info,io.BytesIO(blob))
    report=dict(source_sha256=verify_audited_sources(),files=files,archive_sha256=sha(archive),
                archive_bytes=archive.stat().st_size,cloud_calls_performed=False,
                scope="source, configs, tests, docs and four small historical CSV/JSON files; no checkpoints or credentials")
    (output/"bundle_manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    r=build(a.output);print(json.dumps(dict(files=len(r["files"]),bytes=r["archive_bytes"],sha256=r["archive_sha256"])))
