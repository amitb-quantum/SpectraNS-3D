#!/usr/bin/env python3
"""Phase worker: fixed N640 production profile or explicit local rehearsal."""
import argparse
import csv
import json
from pathlib import Path
import time
import torch
from ns_extension import simulate
from spectral_peak import refine,METHOD
from refinement_telemetry import Monitor
from extension_state import write,sha,high_shell_share
from cloud_policy import ROOT,verify_audited_sources
from refinement_io import fingerprint

def profile(mode):
    if mode=="production":
        return dict(N=640,case="tubes",device="cuda:0",anchor=1.,prefix=1.1,ceiling=1.5,log_dt=.01,checkpoint_dt=.1)
    if mode=="cpu-rehearsal":
        return dict(N=64,case="tgv",device="cpu",anchor=.010,prefix=.011,ceiling=.015,log_dt=.001,checkpoint_dt=.010)
    if mode=="cuda-rehearsal":
        return dict(N=256,case="tubes",device="cuda:0",anchor=.010,prefix=.011,ceiling=.015,log_dt=.001,checkpoint_dt=.010)
    raise ValueError("unknown profile")

def execute(configuration):
    cfg=configuration;p=profile(cfg["profile"]);out=Path(cfg["output"])
    phase=cfg["phase"]
    if phase not in ("coarse","fine","exploration","preflight","reload"):raise ValueError("unknown phase")
    verify_audited_sources()
    if cfg["fingerprint"]!=fingerprint(ROOT):raise ValueError("worker source/config binding changed")
    if cfg["profile"]=="production":
        from refinement_policy import validate_production_request
        validate_production_request(cfg)
        if "H100" not in torch.cuda.get_device_name():
            raise ValueError("production requires bound authorization and H100")
        if cfg.get("provider_deadline_epoch",0)<=time.time()+30:raise ValueError("expired provider lifetime")
    target={"coarse":p["prefix"],"fine":p["prefix"],"exploration":p["ceiling"],
            "preflight":.05 if p["N"]==640 else .001,
            "reload":.051 if p["N"]==640 else .002}[phase]
    restart=cfg.get("restart")
    if phase in ("fine","exploration","reload") and not restart:raise ValueError("phase requires exact same-grid restart")
    if restart:
        m=json.loads((Path(restart)/"checkpoint.json").read_text())
        expected={"fine":p["anchor"],"exploration":p["prefix"],"reload":.05 if p["N"]==640 else .001}[phase]
        if abs(m["t"]-expected)>1e-12:raise ValueError("wrong restart anchor")
    monitor=Monitor(cfg["telemetry_path"]) if p["device"].startswith("cuda") else None
    if monitor:monitor.start()
    phase_clock={"started":None}
    handles=[]
    def event(S,U,t,row,budget,bins):
        if not handles:
            f=(out/"interpolated_vorticity.csv").open("x",newline="",buffering=1)
            g=(out/"dissipation_shares.csv").open("x",newline="",buffering=1)
            handles.extend((f,g))
            headers=["t","sampled_wmax","fourier_refined_peak_estimate","sampling_bias_fraction",
                     "seed_expansion_relative_change","last_level_relative_increment","estimator_stable"]
            event.writer=csv.DictWriter(f,fieldnames=headers);event.writer.writeheader()
            event.shares=csv.writer(g);event.shares.writerow(["t","kmin","loss_share_low","loss_share_center","loss_share_high","energy_share"])
        if cfg["profile"]=="production":
            remaining=cfg["provider_deadline_epoch"]-time.time()
            write(out/"runtime_remaining.json",dict(t=t,remaining_seconds=remaining,achieved_last_dt=row["dt"]))
            if phase in ("coarse","fine","exploration") and row["dt"]>0 and phase_clock["started"] is not None:
                elapsed=time.monotonic()-phase_clock["started"]
                start_t=p["anchor"] if phase=="fine" else p["prefix"] if phase=="exploration" else 0.
                progress=t-start_t
                if progress>0:
                    # Includes initialization and completed diagnostic/checkpoint
                    # costs, deliberately conservative. Physical clipping is
                    # reflected in elapsed progress rather than assumed cap dt.
                    forecast=1.25*elapsed*max(target-t,0)/progress
                    reserve=cfg.get("protected_runtime_reserve_s",0) if phase=="coarse" else 180.
                    write(out/"runtime_remaining.json",dict(t=t,remaining_seconds=remaining,
                        projected_phase_seconds=forecast,reserve_seconds=reserve,achieved_last_dt=row["dt"]))
                    if forecast+reserve>remaining:
                        raise TimeoutError("measured remaining phase no longer fits protected lifetime")
        value=refine(S,U)
        if phase_clock["started"] is None:phase_clock["started"]=time.monotonic()
        if abs(value["sampled_wmax"]-row["wmax"])/max(row["wmax"],1e-30)>2e-11:
            raise ValueError("sampled interpolation diagnostic inconsistent with audited diagnostics")
        event.writer.writerow(dict(t=t,**{k:value[k] for k in event.writer.fieldnames if k!="t"}))
        for k in sorted({128,int(S.N/4)}):
            event.shares.writerow([t,k,*high_shell_share(bins,S.nu,budget["grad_omega_sq"],k).values()])
        write(out/"peak_last_event.json",dict(t=t,**value))
        # Rehearsal pacing makes independent SIGKILL observable at actual work boundaries.
        if cfg.get("rehearsal_pause_s"):
            if cfg["profile"]=="production":raise ValueError("rehearsal hooks prohibited in production")
            time.sleep(cfg["rehearsal_pause_s"])
    try:
        result=simulate(out,N=p["N"],case=p["case"],device=p["device"],
            max_dt=.00025 if phase=="fine" else .0005,target=target,log_dt=p["log_dt"],
            checkpoint_dt=p["checkpoint_dt"],restart=restart,turnover=False,
            checkpoint=phase not in ("fine","reload"),max_wall_seconds=cfg["wall_seconds"],event_callback=event)
        write(out/"exact_configuration.json",dict(request=cfg,profile=p,method=METHOD,worker_sha256=sha(__file__)))
        if monitor:write(out/"driver_memory_summary.json",monitor.finish())
        return result
    finally:
        for f in handles:f.close()
        if monitor and monitor.thread.is_alive():monitor.finish()

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--configuration",required=True);v=a.parse_args()
    r=execute(json.loads(Path(v.configuration).read_text()))
    raise SystemExit(0 if r["status"]=="bounded_complete" and r["stop_reason"]=="max_simulated_time" else 2)
