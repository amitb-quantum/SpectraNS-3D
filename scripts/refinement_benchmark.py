#!/usr/bin/env python3
"""Separate-process N512 integration benchmark, five warmup plus twenty steps."""
import argparse,json,time
from pathlib import Path
import torch
from cloud_policy import ROOT,verify_audited_sources
from ns_fast_v3 import Solver,memory_state
from ns_extension import resolve_device
from extension_state import write
from refinement_telemetry import Monitor
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    out=Path(a.output);out.mkdir(exist_ok=False)
    dev=resolve_device("cuda:0")
    if "H100" not in torch.cuda.get_device_name():raise ValueError("H100 benchmark required")
    monitor=Monitor(out/"driver.csv");monitor.start()
    try:
        S=Solver(512,.0005,.2,.0005,dev,torch.float64)
        U=S.ic_tubes();R=[torch.zeros_like(u) for u in U];t=0.;dts=[]
        for i in range(25):
            if i==5:torch.cuda.synchronize(dev);start=time.monotonic()
            dt,_=S.step_lsrk4(U,R,t,t+.0005);t+=dt;dts.append(dt)
        torch.cuda.synchronize(dev);elapsed=time.monotonic()-start
        write(out/"benchmark.json",dict(N=512,warmup=5,timed=20,seconds=elapsed,seconds_per_step=elapsed/20,
              achieved_dt=dts,source_sha256=verify_audited_sources(),memory=memory_state(dev),driver=monitor.finish()))
    finally:
        if monitor.thread.is_alive():monitor.finish()
if __name__=="__main__":main()
