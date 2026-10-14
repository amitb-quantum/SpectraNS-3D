#!/usr/bin/env python3
"""Phase worker: fixed N768 production profile or explicit local rehearsal."""
import argparse,csv,json,time
from pathlib import Path
import torch
from ns_extension import simulate
from spectral_peak import refine,METHOD
from third_grid_sampling import selected
from refinement_telemetry import Monitor
from extension_state import write,sha,high_shell_share
from cloud_policy import ROOT,verify_audited_sources
from third_grid_io import fingerprint

def profile(mode):
    if mode=="production":
        return dict(N=768,case="tubes",device="cuda:0",anchor=1.,prefix=1.1,ceiling=1.1,
                    log_dt=.01,checkpoint_dt=.1,preflight_t=.05,reload_t=.051)
    if mode in ("cpu-rehearsal","cuda-rehearsal"):
        cuda=mode=="cuda-rehearsal"
        return dict(N=256 if cuda else 64,case="tubes" if cuda else "tgv",
                    device="cuda:0" if cuda else "cpu",anchor=.010,prefix=.011,ceiling=.015,
                    log_dt=.001,checkpoint_dt=.010,preflight_t=.001,reload_t=.002)
    raise ValueError("unknown profile")

def execute(configuration):
    cfg=configuration;p=profile(cfg["profile"]);out=Path(cfg["output"]);phase=cfg["phase"]
    if phase not in ("coarse","fine","exploration","preflight","reload"):raise ValueError("unknown phase")
    verify_audited_sources()
    if cfg["fingerprint"]!=fingerprint(ROOT):raise ValueError("worker source/config binding changed")
    if cfg["profile"]=="production":
        from third_grid_policy import validate_production_request
        validate_production_request(cfg)
        if "H200" not in torch.cuda.get_device_name():raise ValueError("production requires bound H200")
        if cfg.get("provider_deadline_epoch",0)<=time.time()+30:raise ValueError("expired provider lifetime")
    target={"coarse":p["prefix"],"fine":p["prefix"],"exploration":p["ceiling"],
            "preflight":p["preflight_t"],"reload":p["reload_t"]}[phase]
    restart=cfg.get("restart")
    if phase in ("coarse","fine","exploration","reload") and not restart:
        raise ValueError("phase requires exact same-grid restart")
    if restart:
        m=json.loads((Path(restart)/"checkpoint.json").read_text())
        expected={"coarse":p["preflight_t"],"fine":p["anchor"],"exploration":p["prefix"],
                  "reload":p["preflight_t"]}[phase]
        if abs(m["t"]-expected)>1e-12:raise ValueError("wrong restart anchor")
    monitor=Monitor(cfg["telemetry_path"]) if p["device"].startswith("cuda") else None
    if monitor:monitor.start()
    phase_clock={"started":None};handles=[]
    sampling=dict(events=0,refinement_calls=0,refinement_seconds=0.,selected_times=[])
    def event(S,U,t,row,budget,bins):
        if not handles:
            f=(out/"interpolated_vorticity.csv").open("x",newline="",buffering=1)
            g=(out/"dissipation_shares.csv").open("x",newline="",buffering=1)
            handles.extend((f,g))
            headers=["t","sampled_wmax","fourier_refined_peak_estimate","sampling_bias_fraction",
                     "seed_expansion_relative_change","last_level_relative_increment","estimator_stable",
                     "refinement_performed"]
            event.writer=csv.DictWriter(f,fieldnames=headers);event.writer.writeheader()
            event.shares=csv.writer(g)
            event.shares.writerow(["t","kmin","loss_share_low","loss_share_center","loss_share_high","energy_share"])
        if cfg["profile"]=="production":
            remaining=cfg["provider_deadline_epoch"]-time.time()
            write(out/"runtime_remaining.json",dict(t=t,remaining_seconds=remaining,achieved_last_dt=row["dt"]))
            if phase in ("coarse","fine","exploration") and row["dt"]>0 and phase_clock["started"] is not None:
                elapsed=time.monotonic()-phase_clock["started"]
                start_t=p["anchor"] if phase=="fine" else p["prefix"] if phase=="exploration" else p["preflight_t"]
                progress=t-start_t
                if progress>0:
                    forecast=1.25*elapsed*max(target-t,0)/progress
                    reserve=cfg.get("protected_runtime_reserve_s",0) if phase=="coarse" else 180.
                    write(out/"runtime_remaining.json",dict(t=t,remaining_seconds=remaining,
                        projected_phase_seconds=forecast,reserve_seconds=reserve,achieved_last_dt=row["dt"]))
                    if forecast+reserve>remaining:
                        raise TimeoutError("measured remaining phase no longer fits protected lifetime")
        perform=selected(t,phase,p,continued=phase=="coarse")
        value={}
        if perform:
            if U[0].device.type=="cuda":torch.cuda.synchronize(U[0].device)
            started=time.monotonic();value=refine(S,U)
            if U[0].device.type=="cuda":torch.cuda.synchronize(U[0].device)
            sampling["refinement_seconds"]+=time.monotonic()-started
            sampling["refinement_calls"]+=1;sampling["selected_times"].append(t)
            if abs(value["sampled_wmax"]-row["wmax"])/max(row["wmax"],1e-30)>2e-11:
                raise ValueError("sampled interpolation diagnostic inconsistent with audited diagnostics")
        if phase_clock["started"] is None:phase_clock["started"]=time.monotonic()
        event.writer.writerow(dict(t=t,sampled_wmax=row["wmax"],refinement_performed=perform,
                                  **{k:value[k] for k in event.writer.fieldnames if k in value and k!="sampled_wmax"}))
        for k in sorted({128,int(S.N/4)}):
            event.shares.writerow([t,k,*high_shell_share(bins,S.nu,budget["grad_omega_sq"],k).values()])
        sampling["events"]+=1;write(out/"sampling_timing.json",sampling)
        write(out/"peak_last_event.json",dict(t=t,refinement_performed=perform,**({"sampled_wmax":row["wmax"]}|value)))
        if cfg.get("rehearsal_pause_s"):
            if cfg["profile"]=="production":raise ValueError("rehearsal hooks prohibited in production")
            time.sleep(cfg["rehearsal_pause_s"])
    try:
        result=simulate(out,N=p["N"],case=p["case"],device=p["device"],
            max_dt=.00025 if phase=="fine" else .0005,target=target,log_dt=p["log_dt"],
            checkpoint_dt=p["checkpoint_dt"],restart=restart,turnover=False,
            checkpoint=phase not in ("fine","reload"),max_wall_seconds=cfg["wall_seconds"],event_callback=event)
        write(out/"exact_configuration.json",dict(request=cfg,profile=p,method=METHOD,worker_sha256=sha(__file__),
             refinement_schedule="periodic 0.05; coarse 0.86-0.94; fine endpoints; verified preflight prefix"))
        if monitor:write(out/"driver_memory_summary.json",monitor.finish())
        return result
    finally:
        for f in handles:f.close()
        if monitor and monitor.thread.is_alive():monitor.finish()

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--configuration",required=True);v=a.parse_args()
    r=execute(json.loads(Path(v.configuration).read_text()))
    raise SystemExit(0 if r["status"]=="bounded_complete" and r["stop_reason"]=="max_simulated_time" else 2)
