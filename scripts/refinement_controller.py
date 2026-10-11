#!/usr/bin/env python3
"""Protected-first controller, with identical orchestration for local and SSH backends."""
import argparse,json,os,signal,subprocess,sys,threading,time
from pathlib import Path
import shutil
from cloud_policy import ROOT,verify_audited_sources
from extension_state import write,sha
from refinement_guard import birth,kill_owned
from refinement_io import fingerprint,small_snapshot,pack,copy_verified,unpack_verified,inventory,verify,overlap_decision
from refinement_assessment import validate,comparison,checkpoint_at,historical_reference,matched_peak_comparison
from ns_refinement_worker import profile

class LocalBackend:
    mode="local-rehearsal"
    measured_rate=None
    minimum_optional_seconds=30
    cleanup_seconds=20
    verification_allowance_seconds=10
    def __init__(self,out,state):
        self.out=out;self.state=state;self.work=out/"work";self.work.mkdir()
    def phase(self,name,cfg):
        # Every child is in its own session and registered before waiting.
        configuration=self.out/(name+"_request.json");write(configuration,cfg)
        with (self.out/(name+".log")).open("x") as log:
            p=subprocess.Popen([sys.executable,"-u",str(ROOT/"scripts/ns_refinement_worker.py"),"--configuration",str(configuration)],
                   cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                   env=dict(os.environ,OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",PYTHONDONTWRITEBYTECODE="1"))
            owned=dict(pid=p.pid,birth=birth(p.pid))
            self.state["owned_children"].append(owned)
            write(self.out/"controller_state.json",self.state)
            try:
                while p.poll() is None:
                    if time.time()>=self.state["deadline_epoch"]-10:raise TimeoutError("phase deadline")
                    time.sleep(.05)
                if p.returncode:raise ValueError("worker failed; inspect "+name+".log")
            finally:
                if p.poll() is None:kill_owned(owned);p.wait()
    def checkpoint(self,t):
        return checkpoint_at(self.work/"coarse",t)
    def prepare_checkpoint(self,endpoint):
        target=self.out/"checkpoint_frozen";target.mkdir()
        for file in endpoint.iterdir():
            if file.is_file():shutil.copyfile(file,target/file.name)
        fields=inventory(target);write(target/"collection_manifest.json",dict(files=fields))
        archive=self.out/"checkpoint_source.tar.gz"
        return archive,fields,pack(target,archive)
    def freeze_small(self,target):
        return small_snapshot(self.work,target)
    def collect(self,source,target,progress,slow=False):
        stats=copy_verified(source,target,progress,delay=.015 if slow else 0.,chunk=1024 if slow else 1024*1024)
        return stats
    def close(self):
        return dict(verified=True,mode=self.mode,provider="local mock; no provider API called",reason="normal_closure",at_epoch=time.time())

def run(out,backend,mode,*,inject=None,force_sequential=False):
    out=Path(out);p=profile(mode);state=backend.state
    binding=fingerprint(ROOT);write(backend.work/"source_binding.json",binding)
    write(backend.work/"plan.json",json.loads((ROOT/"configs/n640_refinement_proposal.json").read_text()))
    write(backend.work/"acceptance.json",json.loads((ROOT/"configs/h100_acceptance.json").read_text()))
    result=dict(status="running",protected_validated=False,exploration="not_started",checkpoint_collection="not_started",
                profile=mode,source_sha256=verify_audited_sources())
    def stage(name,progress=None):
        state.update(phase=name)
        if progress:state["transfer_progress"]=str(progress)
        write(out/"controller_state.json",state);print("PHASE "+name,flush=True)
    def worker(name,restart=None):
        stage(name)
        state["worker_progress"]=str(backend.work/name/"peak_last_event.json")
        state["worker_start_t"]=p["anchor"] if name=="fine" else p["prefix"] if name=="exploration" else 0.
        cfg=dict(profile=mode,phase=name,output=str(backend.work/name),restart=None if restart is None else str(restart),
                 wall_seconds=max(1,state["deadline_epoch"]-time.time()-20),fingerprint=binding,
                 rehearsal_pause_s=.2 if inject else 0.,telemetry_path=str(backend.work/(name+"_driver.csv")))
        if mode=="production":
            cfg.update(authorization=backend.authorization,provider_deadline_epoch=state["deadline_epoch"],
                       protected_runtime_reserve_s=backend.fine_reserve_seconds)
        write(out/"controller_state.json",state)
        backend.phase(name,cfg)
    transfer_thread=None;transfer_errors=[]
    try:
        if mode=="production":backend.preflight(binding)
        worker("coarse")
        coarse=validate(backend.work/"coarse",p["N"],p["prefix"],p["log_dt"])
        anchor=backend.checkpoint(p["anchor"])
        endpoint=backend.checkpoint(p["prefix"])
        worker("fine",anchor)
        fine=validate(backend.work/"fine",p["N"],p["prefix"],p["log_dt"])
        temporal=comparison(coarse,fine,p["anchor"],p["prefix"],1e-5,temporal=True)
        if temporal["status"]!="passed":raise ValueError("fine window agreement failed")
        # Rehearsal compares the independently restarted fine trajectory to
        # coarse over its common window; this is NOT an N512/N640 comparison.
        spatial=dict(status="local_rehearsal_only",production_spatial_comparison_performed=False,
                     scope="compressed timeline tests orchestration; no scientific N640 claim")
        if mode=="production":
            baseline=historical_reference()
            spatial=comparison(baseline,coarse,0.,1.1,.001)
            from refinement_review import compare_fitted_local_peaks
            spatial["fitted_net_peak"]=compare_fitted_local_peaks(
                [(float(r["t"]),float(r["net_production"])) for r in baseline["budgets"]],
                [(float(r["t"]),float(r["net_production"])) for r in coarse["budgets"]])
            spatial["secondary_screens"]={k:spatial["errors"][k]<=tol for k,tol in
               {"E":.001,"spectrum_L1_over_E":.001,"wmax":.01,"bkm":.01}.items()}
            spatial["matched_fourier_peaks"]=matched_peak_comparison(backend.work/"coarse",
                json.loads((ROOT/"configs/n512_interpolated_peak_reference.json").read_text()))
            spatial["baseline_files_sha256"]={n:sha(ROOT/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse"/n)
                for n in ("diagnostics.csv","enstrophy.csv","spectra.csv","run.json")}
        result["spatial_comparison"]=spatial
        write(backend.work/"assessment.json",dict(temporal=temporal,spatial=spatial,
              prefix_numerical_gates_passed=True,local_temporal_window_passed=True))
        stage("protected_collection",out/"small_transfer_progress.json")
        frozen=out/"frozen_small";expected=backend.freeze_small(frozen)
        compression=pack(frozen,out/"small_source.tar.gz")
        transfer=backend.collect(out/"small_source.tar.gz",out/"small_recovered.tar.gz",out/"small_transfer_progress.json",bool(inject))
        receipt=unpack_verified(out/"small_recovered.tar.gz",out/"protected",expected)
        result.update(protected_validated=True,protected_manifest_sha256=sha(out/"protected"/"collection_manifest.json"),
                      local_temporal=temporal,protected_receipt=receipt)
        # Receipt is separate from frozen evidence; never overwrite protection.
        write(out/"protected_receipt.json",result.copy())
        if state["deadline_epoch"]-time.time()<backend.minimum_optional_seconds:
            result.update(checkpoint_collection="skipped_lifetime",exploration="skipped_lifetime",status="completed")
            return result
        checkpoint_archive,fields,checkpoint_metrics=backend.prepare_checkpoint(endpoint)
        measured_rate=backend.measured_rate or transfer["copied"]/max(transfer["seconds"],1e-9)
        checkpoint_allowance=1.5*(checkpoint_metrics["bytes"]/measured_rate+checkpoint_metrics["seconds"]+backend.verification_allowance_seconds)+backend.cleanup_seconds
        cm=coarse["manifest"]["timing"]
        elapsed=cm["process_wall_s"]
        explore_seconds=elapsed*(p["ceiling"]-p["prefix"])/p["prefix"]*1.25+10
        decision=overlap_decision(state["deadline_epoch"]-time.time(),checkpoint_allowance,explore_seconds,cleanup=backend.cleanup_seconds)
        if force_sequential:decision["overlap"]=False;decision["rehearsal_override"]="sequential branch coverage"
        write(out/"overlap_decision.json",dict(decision,checkpoint=checkpoint_metrics,
              collection_rate_bytes_per_second=measured_rate,exploration_forecast_seconds=explore_seconds))
        def collect_checkpoint():
            try:
                backend.collect(checkpoint_archive,out/"checkpoint_recovered.tar.gz",
                    out/"checkpoint_transfer_progress.json",bool(inject))
                result["checkpoint_receipt"]=unpack_verified(out/"checkpoint_recovered.tar.gz",out/"checkpoint",fields)
                result["checkpoint_collection"]="verified"
                write(out/"checkpoint_receipt.json",result["checkpoint_receipt"])
            except Exception as exc:
                result["checkpoint_collection"]="incomplete";transfer_errors.append(type(exc).__name__)
        stage("checkpoint_collection",out/"checkpoint_transfer_progress.json")
        if decision["overlap"]:
            transfer_thread=threading.Thread(target=collect_checkpoint,daemon=True);transfer_thread.start()
        elif checkpoint_allowance+backend.cleanup_seconds<state["deadline_epoch"]-time.time():
            collect_checkpoint()
        else:result["checkpoint_collection"]="skipped_lifetime"
        if explore_seconds+backend.cleanup_seconds<state["deadline_epoch"]-time.time():
            try:
                worker("exploration",endpoint);result["exploration"]="completed"
            except Exception as exc:
                result["exploration"]="incomplete";result["exploration_error"]=type(exc).__name__+": "+str(exc)
            # Optional exploration cannot mutate the protected snapshot.
            verify(out/"protected",expected)
            if (backend.work/"exploration"/"run.json").exists():
                final=json.loads((backend.work/"exploration"/"run.json").read_text())
                result["exploration_last_t"]=None if not final.get("last_accepted") else final["last_accepted"]["t"]
        else:result["exploration"]="skipped_lifetime"
        if mode=="production" and (backend.work/"exploration"/"run.json").exists():
            from refinement_assessment import rows
            from refinement_review import compare_fitted_local_peaks
            em=json.loads((backend.work/"exploration"/"run.json").read_text())
            accepted=em.get("last_accepted")
            if accepted:
                later=[(float(r["t"]),float(r["net_production"])) for r in rows(backend.work/"exploration"/"enstrophy.csv")
                       if 1.1<float(r["t"])<=accepted["t"]+1e-12]
                extended=[(float(r["t"]),float(r["net_production"])) for r in coarse["budgets"]]+later
                supplement=compare_fitted_local_peaks(
                    [(float(r["t"]),float(r["net_production"])) for r in baseline["budgets"]],extended)
                write(out/"exploratory_peak_comparison.json",dict(comparison=supplement,
                   qualification="Supplementary separately accepted horizons; temporal check covers only 1.00-1.10; protected assessment unchanged"))
        if transfer_thread:transfer_thread.join(max(0,state["deadline_epoch"]-time.time()-10))
        if transfer_thread and transfer_thread.is_alive():result["checkpoint_collection"]="incomplete_deadline"
        if transfer_errors:result["checkpoint_errors"]=transfer_errors
        result["status"]="completed" if result["protected_validated"] else "incomplete"
    except Exception as exc:
        result.update(status="incomplete",error=type(exc).__name__+": "+str(exc))
    finally:
        result["ended_epoch"]=time.time()
        write(out/"campaign.json",result)
        write(out/"termination.json",backend.close())
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",required=True)
    parser.add_argument("--profile",choices=("cpu-rehearsal","cuda-rehearsal"),required=True)
    parser.add_argument("--inject",choices=("coarse","fine","protected_collection","checkpoint_collection","exploration"))
    parser.add_argument("--sequential",action="store_true");parser.add_argument("--lifetime",type=float,default=600)
    a=parser.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    if not 10<a.lifetime<=1800:parser.error("local lifetime must be 10..1800 seconds")
    state=dict(mode="local-rehearsal",controller_pid=os.getpid(),controller_birth=birth(os.getpid()),
               started_epoch=time.time(),deadline_epoch=time.time()+a.lifetime,phase="startup",owned_children=[],inject=a.inject)
    write(out/"controller_state.json",state)
    with (out/"guard.log").open("x") as log:
        guard=subprocess.Popen([sys.executable,str(ROOT/"scripts/refinement_guard.py"),"--directory",str(out)],
                                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    for _ in range(750):
        if (out/"guard_ready.json").exists():break
        if guard.poll() is not None:raise RuntimeError("independent guard failed to arm")
        time.sleep(.02)
    else:raise TimeoutError("guard startup")
    result=run(out,LocalBackend(out,state),a.profile,inject=a.inject,force_sequential=a.sequential)
    guard.wait(timeout=10)
    return 0 if result["status"]=="completed" else 2

if __name__=="__main__":raise SystemExit(main())
