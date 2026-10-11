#!/usr/bin/env python3
"""Exercise real worker/collector processes and independent SIGKILL failure paths."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from cloud_policy import ROOT,verify_audited_sources
from extension_state import write,sha
from refinement_io import fingerprint,verify
from refinement_guard import same

def run_suite(out,cuda=False):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    binding=fingerprint(ROOT);cases=[("success_overlap",None,False),("success_sequential",None,True),
         ("kill_coarse","coarse",False),("kill_fine","fine",False),
         ("kill_protected_collection","protected_collection",False),
         ("kill_checkpoint_collection","checkpoint_collection",True),
         ("kill_exploration","exploration",False)]
    if cuda:cases.append(("success_cuda",None,False))
    results=[]
    for name,inject,sequential in cases:
        directory=out/name
        cmd=[sys.executable,"-u",str(ROOT/"scripts/refinement_controller.py"),"--output",str(directory),
             "--profile","cuda-rehearsal" if name=="success_cuda" else "cpu-rehearsal","--lifetime","600"]
        if inject:cmd+=["--inject",inject]
        if sequential:cmd+=["--sequential"]
        started=time.monotonic()
        with (out/(name+".log")).open("x") as f:
            process=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,
                env=dict(os.environ,OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",PYTHONDONTWRITEBYTECODE="1"),timeout=600,start_new_session=True)
        deadline=time.monotonic()+15
        while not (directory/"termination.json").exists() and time.monotonic()<deadline:time.sleep(.05)
        if not (directory/"termination.json").exists():raise ValueError("guard failed closure in "+name)
        receipt=json.loads((directory/"termination.json").read_text())
        if not receipt["verified"] or receipt["mode"]!="local-rehearsal":raise ValueError("unsafe rehearsal closure")
        state=json.loads((directory/"controller_state.json").read_text())
        protected=(directory/"protected").exists()
        if protected:verify(directory/"protected")
        expected_protected=inject in ("checkpoint_collection","exploration") or inject is None
        if protected!=expected_protected:raise ValueError("unexpected protected evidence in "+name)
        if inject:
            trigger=json.loads((directory/"guard_trigger.json").read_text())
            if trigger["reason"]!="injected_"+inject or process.returncode!=-9:
                raise ValueError("expected real independent SIGKILL in "+name)
            # Registered worker PIDs must be gone or zombies (no execution).
            for child in state["owned_children"]:
                if same(child["pid"],child["birth"]):
                    stat=Path(f"/proc/{child['pid']}/stat").read_text().rsplit(")",1)[1].split()[0]
                    if stat!="Z":raise ValueError("worker still executing after kill")
            campaign=None
        else:
            campaign=json.loads((directory/"campaign.json").read_text())
            if process.returncode or campaign["status"]!="completed" or not campaign["protected_validated"]:
                raise ValueError("success rehearsal failed: "+name)
            decision=json.loads((directory/"overlap_decision.json").read_text())
            if decision["overlap"]==sequential:raise ValueError("overlap branch not exercised")
        result=dict(name=name,status="passed",returncode=process.returncode,
             wall_s=time.monotonic()-started,protected_evidence_verified=protected,
             partial_files=[p.relative_to(directory).as_posix() for p in directory.rglob("*.part")],
             termination=receipt)
        results.append(result);write(out/"progress.json",results);print(json.dumps(result),flush=True)
    if binding!=fingerprint(ROOT):raise ValueError("sources changed during rehearsal")
    summary=dict(status="passed",source_sha256=verify_audited_sources(),fingerprint=binding,cases=results,
                 provider_calls=0,scope="local controller failure paths; not H100/N640 numerical validation")
    write(out/"rehearsal.json",summary)
    return summary
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--cuda",action="store_true")
    a=p.parse_args();run_suite(a.output,a.cuda)
