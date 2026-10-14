"""SSH transport for the rehearsed protected-first controller. No provisioning here."""
import json,math,shlex,shutil,subprocess,time,uuid
from pathlib import Path
from extension_state import write,sha
from third_grid_io import unpack_verified,small_snapshot,copy_verified
from third_grid_assessment import validate,checkpoint_at
from third_grid_review import protected_phase_forecast

REMOTE="/opt/spectrans-3d"
PROJECT=REMOTE+"/project"
WORK=PROJECT+"/artifacts/third_grid_run"
PYTHON=REMOTE+"/env/bin/python"

class VastBackend:
    mode="vast"
    minimum_optional_seconds=120
    measured_rate=None
    fine_reserve_seconds=0.
    cleanup_seconds=120
    verification_allowance_seconds=60
    def __init__(self,out,state,authorization):
        self.out=Path(out);self.state=state;self.authorization=authorization
        self.work=self.out/"work";self.work.mkdir()
        self.connection=None
    def remaining(self,cleanup=60):
        value=self.state["deadline_epoch"]-time.time()-cleanup
        if value<=0:raise TimeoutError("provider lifetime exhausted")
        return value
    def remote(self,command,log="remote.log",timeout=None):
        with (self.out/log).open("a") as f:
            subprocess.run(self.connection+[command],stdout=f,stderr=subprocess.STDOUT,check=True,
                timeout=min(timeout or self.remaining(),self.remaining(30)))
    def copy(self,source,destination,download=False):
        host=self.state["ssh_host"];key=self.state["ssh_key_path"]
        cmd=["scp","-q","-P",str(self.state["ssh_port"]),"-i",key,"-o","BatchMode=yes",
             "-o","StrictHostKeyChecking=accept-new","-o","UserKnownHostsFile="+self.state["known_hosts"]]
        src="root@"+host+":"+str(source) if download else str(source)
        dst=str(destination) if download else "root@"+host+":"+str(destination)
        start=time.monotonic()
        with (self.out/"transfers.log").open("a") as f:
            subprocess.run(cmd+[src,dst],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=self.remaining(30))
        return time.monotonic()-start
    def map_path(self,path):
        return WORK+"/"+Path(path).relative_to(self.work).as_posix()
    def checkpoint(self,t):
        return checkpoint_at(self.work/"coarse",t,require_arrays=False)
    def preflight_checkpoint(self,t):
        return checkpoint_at(self.work/"preflight",t,require_arrays=False)
    def complete_coarse(self,p):
        self.remote("cd "+PROJECT+" && "+PYTHON+" scripts/third_grid_remote_io.py join-prefix --source "+WORK+" --output "+WORK+"/continuation_receipt.json")
        self.sync_small()
        return json.loads((self.work/"continuation_receipt.json").read_text())
    def archive(self,operation,source,name,t=None):
        archive=REMOTE+"/"+name+".tar.gz"
        command=[PYTHON,"scripts/third_grid_remote_io.py",operation,"--source",source,"--output",archive]
        if t is not None:command+=["--t",str(t)]
        self.remote("cd "+PROJECT+" && "+shlex.join(command))
        info=self.out/(name+"_source.json");self.copy(archive+".json",info,True)
        return archive,json.loads(info.read_text())
    def sync_small(self):
        archive,metrics=self.archive("small",WORK,"small-"+uuid.uuid4().hex)
        local=self.out/(Path(archive).name+".part")
        self.copy(archive,local,True)
        if sha(local)!=metrics["sha256"]:raise ValueError("small archive compressed hash mismatch")
        target=self.out/("mirror-"+uuid.uuid4().hex)
        unpack_verified(local,target,metrics["files"])
        shutil.copytree(target,self.work,dirs_exist_ok=True)
        self.remote("rm -- "+shlex.quote(archive)+" "+shlex.quote(archive+".json"))
    def phase(self,name,cfg):
        cfg=dict(cfg,authorization=self.authorization,provider_deadline_epoch=self.state["deadline_epoch"],
                 protected_runtime_reserve_s=self.fine_reserve_seconds)
        cfg["output"]=self.map_path(cfg["output"]);cfg["telemetry_path"]=self.map_path(cfg["telemetry_path"])
        if cfg.get("restart"):cfg["restart"]=self.map_path(cfg["restart"])
        local=self.out/(name+"_remote_request.json");write(local,cfg)
        config=REMOTE+"/"+name+"_request.json";self.copy(local,config)
        self.state["phase"]=name;write(self.out/"controller_state.json",self.state)
        error=None
        try:
            self.remote("cd "+PROJECT+" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 "+
                        shlex.join([PYTHON,"-u","scripts/ns_third_grid_worker.py","--configuration",config]),name+".log")
        except Exception as exc:error=exc
        finally:
            try:self.sync_small()
            except Exception:
                if error is None:raise
        if error:raise error
    def freeze_small(self,target):
        return small_snapshot(self.work,target)
    def prepare_checkpoint(self,endpoint):
        archive,metrics=self.archive("checkpoint",WORK+"/coarse","pinned-coarse-1p10",1.1)
        if metrics["bytes"]>10_910_000_000:raise ValueError("checkpoint exceeds egress upper bound")
        self.checkpoint_metrics=metrics
        return archive,metrics["files"],metrics
    def collect(self,source,target,progress,slow=False):
        source=str(source);target=Path(target)
        if source.startswith(REMOTE+"/"):
            temp=target.with_name(target.name+".part")
            elapsed=self.copy(source,temp,True);expected=self.checkpoint_metrics
            if sha(temp)!=expected["sha256"]:raise ValueError("checkpoint compressed hash mismatch")
            temp.rename(target)
            record=dict(copied=target.stat().st_size,total=target.stat().st_size,complete=True,
                        seconds=elapsed,sha256=expected["sha256"])
            write(progress,record);return record
        return copy_verified(source,target,progress)
    def disk_gate(self,name):
        destination=WORK+"/disk_"+name+".json"
        code="import sys; sys.path.insert(0,'scripts'); from third_grid_capacity import check_free_space; from extension_state import write; write("+repr(destination)+",check_free_space("+repr(WORK)+"))"
        self.remote("cd "+PROJECT+" && "+PYTHON+" -c "+shlex.quote(code),"disk.log")
        local=self.out/("disk_"+name+".json")
        self.copy(destination,local,True)
        if not json.loads(local.read_text())["fits"]:
            raise ValueError("insufficient measured free space; see "+local.name)

    def preflight(self,binding):
        from cloud_policy import ROOT
        write(self.work/"authorization.json",self.authorization)
        self.remote("mkdir -p "+WORK)
        self.disk_gate("after_setup")
        self.remote("cd "+PROJECT+" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 "+PYTHON+" -m pytest -q tests","tests.log")
        self.remote("cd "+PROJECT+" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 "+PYTHON+
                    " scripts/verify_h100_reference.py --output "+WORK+"/cpu_h100_reference.json","references.log")
        self.remote("cd "+PROJECT+" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 "+PYTHON+
                    " scripts/third_grid_benchmark.py --output "+WORK+"/N512_benchmark","N512_benchmark.log")
        for phase in ("preflight","reload"):
            restart=None
            if phase=="reload":
                m=json.loads((self.work/"preflight"/"run.json").read_text())
                restart=str(self.work/"preflight"/m["terminal_checkpoint"]["path"])
            cfg=dict(profile="production",phase=phase,output=str(self.work/phase),restart=restart,
                telemetry_path=str(self.work/(phase+"_driver.csv")),wall_seconds=self.remaining(120),
                fingerprint=binding,rehearsal_pause_s=0.)
            self.phase(phase,cfg)
            # Reload makes one terminal .001 interval rather than the regular .01.
            validate(self.work/phase,768,.05 if phase=="preflight" else .051,.01 if phase=="preflight" else .001)
        trials=[]
        for i in range(2):
            remote=REMOTE+"/probe"+str(i)+".bin"
            self.remote("cd "+PROJECT+" && "+PYTHON+" scripts/third_grid_remote_io.py probe --source "+WORK+" --output "+remote)
            record=self.out/("probe"+str(i)+".json");self.copy(remote+".json",record,True)
            data=json.loads(record.read_text());target=self.out/("probe"+str(i)+".bin.part")
            elapsed=self.copy(remote,target,True)
            if sha(target)!=data["sha256"]:raise ValueError("transfer probe checksum mismatch")
            trials.append(dict(bytes=data["bytes"],seconds=elapsed,bytes_per_second=data["bytes"]/elapsed,sha256=data["sha256"]))
            target.unlink();self.remote("rm -- "+remote+" "+remote+".json")
        self.measured_rate=min(r["bytes_per_second"] for r in trials)
        archive,compression=self.archive("checkpoint",WORK+"/preflight","preflight-checkpoint",.05)
        self.remote("cd "+PROJECT+" && "+PYTHON+" scripts/third_grid_remote_io.py verify --source "+
                    shlex.quote(archive)+" --output "+WORK+"/checkpoint_verification.json")
        self.sync_small()
        verification=json.loads((self.work/"checkpoint_verification.json").read_text())
        self.verification_allowance_seconds=max(60.,2*verification["seconds"])
        self.preflight_compression=compression
        write(self.work/"transfer_preflight.json",dict(trials=trials,compression=compression,slowest_bytes_per_second=self.measured_rate))
        # Keep the exact preflight state until the original-IC continuation is joined.
        self.remote("rm -- "+shlex.quote(archive)+" "+shlex.quote(archive+".json"))
        self.disk_gate("after_preflight_retention")
        m=json.loads((self.work/"preflight"/"run.json").read_text());timing=m["timing"]
        seconds=timing["seconds"];calls=timing["calls"]
        integration_rows=__import__("csv").DictReader((self.work/"preflight"/"steps.csv").open())
        samples=list(integration_rows)
        after_warmup=[float(samples[i]["wall_s"])-float(samples[i-1]["wall_s"]) for i in range(20,len(samples))
                      if samples[i]["t_start"]!=samples[i-1]["t_start"]]
        step=max(seconds["integration"]/m["achieved_steps"],__import__("statistics").median(after_warmup))
        write(self.work/"warmup_timing.json",dict(discarded_steps=20,timed_steps=len(samples)-20,
              median_increment_seconds=__import__("statistics").median(after_warmup),
              integration_mean_seconds=seconds["integration"]/m["achieved_steps"]))
        sampling=json.loads((self.work/"preflight"/"sampling_timing.json").read_text())
        if sampling["refinement_calls"]!=2:raise ValueError("preflight must time both declared refined endpoints")
        refined=sampling["refinement_seconds"]/sampling["refinement_calls"]
        callback_base=max(0.,seconds.get("fourier_peak_refinement",0)-sampling["refinement_seconds"])
        diagnostic=(sum(seconds.get(k,0) for k in ("scalar_diagnostics_and_tail","enstrophy_budget","full_spectrum"))+callback_base)/calls["scalar_diagnostics_and_tail"]
        checkpoint=seconds["checkpoint_write_hash_prune"]/calls["checkpoint_write_hash_prune"]
        dt=m["dt_statistics"]["min"]
        if dt<.0005*(1-1e-8):raise ValueError("preflight CFL clipping needs revised runtime forecast")
        from third_grid_sampling import count_remaining
        from ns_third_grid_worker import profile
        counts=count_remaining(profile("production"))
        forecast=protected_phase_forecast(step,diagnostic,checkpoint,self.remaining(120),180,
            coarse_start_t=.05,refinement_seconds=refined,refinement_events=counts["total"])
        self.fine_reserve_seconds=1.25*(400*step+11*diagnostic+counts["fine"]*refined)+180
        forecast.update(step_seconds=step,diagnostic_seconds=diagnostic,checkpoint_seconds=checkpoint,
             achieved_dt_min=dt,fine_reserve_seconds=self.fine_reserve_seconds,
             refinement_seconds_per_call=refined,refinement_counts=counts,
             note="verified original-IC prefix reused; sampled maxima/budgets/spectra every event; only declared Fourier estimates timed separately")
        write(self.work/"runtime_preflight.json",forecast)
        for name in ("tests.log","references.log","N512_benchmark.log"):
            shutil.copyfile(self.out/name,self.work/name)
        self.sync_small()
        if not forecast["fits"]:raise ValueError("protected prefix/fine/collection do not fit measured lifetime")
    def close(self):
        from vast_campaign_api import destroy_owned,owned_instance
        receipt=dict(verified=False,mode="vast",reason="controller_closure",at_epoch=time.time())
        try:
            write(self.out/"destroy_receipt.json",destroy_owned(self.state))
            for _ in range(20):
                if owned_instance(self.state) is None:receipt["verified"]=True;break
                time.sleep(2)
            receipt["at_epoch"]=time.time()
            if not receipt["verified"]:raise ValueError("provider absence unverified; guard stays armed")
        except Exception as exc:
            receipt["error"]=type(exc).__name__
            # A simultaneous watchdog deletion can make the DELETE return
            # an error. Resolve closure through a fresh ownership listing.
            try:
                if owned_instance(self.state) is None:receipt["verified"]=True
            except Exception:pass
        receipt["at_epoch"]=time.time()
        return receipt
