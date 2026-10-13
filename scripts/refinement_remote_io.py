#!/usr/bin/env python3
"""Nonsecret remote artifact operations; no credentials and no provisioning."""
import argparse,json,os,shutil,tempfile,time
from pathlib import Path
from extension_state import write,sha
from refinement_io import small_snapshot,pack,inventory,unpack_verified
from refinement_assessment import checkpoint_at
def main():
    p=argparse.ArgumentParser();p.add_argument("operation",choices=("small","checkpoint","probe","prune","verify","join-prefix"))
    p.add_argument("--source",required=True);p.add_argument("--output",required=True);p.add_argument("--t",type=float)
    a=p.parse_args();source=Path(a.source);output=Path(a.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    if a.operation=="join-prefix":
        if source.name!="refinement_run" or source.parent.name!="artifacts":
            raise ValueError("continuation assembly restricted to new refinement work")
        from ns_refinement_worker import profile
        from refinement_prefix import join_prefix,release_prefix
        exact=json.loads((source/"preflight"/"exact_configuration.json").read_text())
        receipt=join_prefix(source,profile(exact["request"]["profile"]))
        release_prefix(source);write(output,receipt);return
    if a.operation=="prune":
        if source.name!="preflight" or source.parent.name!="refinement_run":
            raise ValueError("prune restricted to new refinement preflight")
        metadata=inventory(source/"checkpoint_metadata")
        if not metadata:raise ValueError("metadata must be archived before pruning")
        shutil.rmtree(source/"checkpoints")
        write(output,dict(pruned="new preflight arrays only",metadata_sha256=metadata))
        return
    if a.operation=="verify":
        info=json.loads(source.with_name(source.name+".json").read_text())
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix="refinement-verify-",dir=output.parent) as temporary:
            unpack_verified(source,Path(temporary)/"recovered",info["files"])
        write(output,dict(verified=True,seconds=time.monotonic()-started,archive_sha256=sha(source)))
        return
    if a.operation=="probe":
        with output.open("xb") as f:
            for _ in range(64):f.write(os.urandom(1024*1024))
        record=dict(bytes=output.stat().st_size,sha256=sha(output),seconds=0)
    else:
        temp=Path(tempfile.mkdtemp(prefix="refinement-archive-",dir=output.parent))
        stage=temp/"snapshot"
        try:
            if a.operation=="small":files=small_snapshot(source,stage)
            else:
                state=checkpoint_at(source,a.t);stage.mkdir()
                for file in state.iterdir():
                    if file.is_file():
                        # Hard links pin arrays without duplicating 6.3GB on disk.
                        os.link(file,stage/file.name)
                files=inventory(stage);write(stage/"collection_manifest.json",dict(files=files))
            record=dict(pack(stage,output),files=files)
        finally:shutil.rmtree(temp)
    write(output.with_name(output.name+".json"),record)
if __name__=="__main__":main()
