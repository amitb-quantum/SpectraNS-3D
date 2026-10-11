"""Immutable small-evidence snapshots and verified, interruptible collection."""
import json
import os
from pathlib import Path
import shutil
import tarfile
import time
from extension_state import sha,write

def fingerprint(root):
    root=Path(root)
    names=[p for d in ("src","scripts","tests") for p in (root/d).rglob("*.py")
           if "__pycache__" not in p.parts]
    names += [root/"configs/h100_acceptance.json",root/"configs/n640_refinement_proposal.json",root/"configs/n512_interpolated_peak_reference.json"]
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(names)}

def inventory(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and p.relative_to(root).as_posix()!="collection_manifest.json"}

def verify(root,expected=None):
    root=Path(root)
    expected=expected or json.loads((root/"collection_manifest.json").read_text())["files"]
    actual=inventory(root)
    if actual!=expected: raise ValueError("artifact names/hash mismatch")
    return expected

def small_snapshot(source,destination):
    source,destination=Path(source),Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for p in sorted(source.rglob("*")):
        if not p.is_file() or p.suffix==".npy" or p.suffix==".gz" or p.name.endswith(".tmp"): continue
        # Freeze before exploration; no live logs or mutable controller files.
        target=destination/p.relative_to(source)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    files=inventory(destination)
    write(destination/"collection_manifest.json",dict(files=files))
    return files

def pack(source,archive):
    source,archive=Path(source),Path(archive)
    start=time.monotonic()
    # GNU gzip -1 via subprocess is used by production transport. Local
    # rehearsal uses the same lossless tar container and explicit level 1.
    with tarfile.open(archive,"w:gz",compresslevel=1) as out:
        for p in sorted(source.rglob("*")):
            if p.is_file():out.add(p,arcname=p.relative_to(source).as_posix(),recursive=False)
    return dict(bytes=archive.stat().st_size,seconds=time.monotonic()-start,sha256=sha(archive))

def copy_verified(source,destination,progress=None,delay=0.,chunk=1024*1024):
    source,destination=Path(source),Path(destination)
    temp=destination.with_name(destination.name+".part")
    started=time.monotonic();copied=0
    with source.open("rb") as src,temp.open("xb") as dst:
        while data:=src.read(chunk):
            dst.write(data);dst.flush();copied+=len(data)
            if progress:write(progress,dict(copied=copied,total=source.stat().st_size,complete=False))
            if delay:time.sleep(delay)
        os.fsync(dst.fileno())
    if sha(source)!=sha(temp):raise ValueError("compressed transfer checksum mismatch")
    temp.replace(destination)
    record=dict(copied=copied,total=copied,complete=True,seconds=time.monotonic()-started,sha256=sha(destination))
    if progress:write(progress,record)
    return record

def unpack_verified(archive,destination,expected):
    destination=Path(destination)
    stage=destination.with_name(destination.name+".unverified")
    stage.mkdir(exist_ok=False)
    with tarfile.open(archive,"r:gz") as tar:
        members=tar.getmembers()
        if any(not m.isfile() or Path(m.name).is_absolute() or ".." in Path(m.name).parts for m in members):
            raise ValueError("unsafe archive member")
        names=[m.name for m in members]
        if len(names)!=len(set(names)) or set(names)!=set(expected)|{"collection_manifest.json"}:
            raise ValueError("archive does not match frozen manifest")
        tar.extractall(stage,filter="data")
    verify(stage,expected);stage.rename(destination)
    return dict(verified=True,files=len(expected),archive_sha256=sha(archive))

def overlap_decision(remaining,transfer_seconds,exploration_seconds,cleanup=30,margin=1.25):
    import math
    if not all(math.isfinite(v) and v>=0 for v in (remaining,transfer_seconds,exploration_seconds,cleanup)) or margin<1:
        raise ValueError("invalid overlap forecast")
    joint=margin*max(transfer_seconds,exploration_seconds)+cleanup
    return dict(overlap=joint<=remaining,forecast_seconds=joint,
                sequential_seconds=transfer_seconds+exploration_seconds+cleanup,
                remaining_seconds=remaining,contention_factor=margin)
