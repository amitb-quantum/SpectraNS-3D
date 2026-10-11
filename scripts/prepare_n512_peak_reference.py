#!/usr/bin/env python3
"""Postprocess only the two preserved accepted N512 checkpoints, without evolving."""
import argparse,json,sys,time
from pathlib import Path
import torch
from cloud_policy import ROOT,verify_audited_sources
from ns_fast_v3 import Solver,memory_state
from ns_extension import resolve_device
from extension_state import load_checkpoint,sha,write
from spectral_peak import refine,METHOD
from refinement_telemetry import Monitor

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--device",default="cuda:0")
    a=p.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    base=ROOT/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse/checkpoints"
    reference=dict(source_sha256=verify_audited_sources(),method=METHOD,
                   estimator_sha256=sha(ROOT/"scripts/spectral_peak.py"),torch=torch.__version__,cuda=torch.version.cuda,
                   scope="Fourier local peak estimates at accepted matched checkpoints only; no historical t=.89 field exists",
                   checkpoints=[])
    for t in (1.,1.1):
        started=time.monotonic();dev=resolve_device(a.device)
        if dev.type=="cuda":
            torch.cuda.set_device(dev);torch.cuda.reset_peak_memory_stats(dev)
        monitor=Monitor(out/f"t{t:.2f}_driver.csv") if dev.type=="cuda" else None
        if monitor:monitor.start()
        try:
            S=Solver(512,.0005,.2,.0005,dev,torch.float64)
            path=base/f"regular_t{t:.8f}"
            U,m=load_checkpoint(path,S,"tubes")
            result=refine(S,U)
            record=dict(t=t,checkpoint_metadata_sha256=sha(path/"checkpoint.json"),component_sha256=m["files"],
                        peak=result,memory=memory_state(dev),wall_s=time.monotonic()-started)
            if monitor:record["driver"]=monitor.finish()
            reference["checkpoints"].append(record);write(out/f"t{t:.2f}_peak.json",record)
            print(json.dumps(dict(t=t,sampled=result["sampled_wmax"],refined=result["fourier_refined_peak_estimate"],
                       bias=result["sampling_bias_fraction"],stable=result["estimator_stable"],wall_s=record["wall_s"])),flush=True)
        finally:
            if monitor and monitor.thread.is_alive():monitor.finish()
            del U,S
            if dev.type=="cuda":torch.cuda.empty_cache()
    reference["status"]="passed" if all(r["peak"]["estimator_stable"] for r in reference["checkpoints"]) else "estimator_inconclusive"
    write(out/"reference.json",reference)
    return 0 if reference["status"]=="passed" else 2
if __name__=="__main__":raise SystemExit(main())
