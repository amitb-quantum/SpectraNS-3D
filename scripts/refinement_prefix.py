"""Assemble one same-grid original-IC trajectory; preserve both phase records."""
import csv,json,math,shutil
from pathlib import Path
from extension_state import write,sha
from refinement_io import small_snapshot
from refinement_assessment import validate

CSV_KEYS={"diagnostics.csv":("t",),"enstrophy.csv":("t",),"spectra.csv":("t","shell_k"),
          "interpolated_vorticity.csv":("t",),"dissipation_shares.csv":("t","kmin")}
def read_csv(path):
    with path.open(newline="") as f:
        reader=csv.DictReader(f);return reader.fieldnames,list(reader)

def join_prefix(work,p):
    work=Path(work).resolve();left=work/"preflight";right=work/"coarse"
    origin=validate(left,p["N"],p["preflight_t"],p["log_dt"])
    continuation=validate(right,p["N"],p["prefix"],p["log_dt"])
    a,b=origin["manifest"],continuation["manifest"]
    if a.get("restart") or a["start_t"]!=0 or a["initial_step"]!=0:
        raise ValueError("prefix must originate in the analytic initial condition")
    if abs(b["start_t"]-p["preflight_t"])>1e-12 or not b.get("restart"):
        raise ValueError("continuation did not start from preflight")
    for k in ("N","nu","case","scheme","fp64","cfl","max_dt","log_dt","checkpoint_dt"):
        if a["parameters"][k]!=b["parameters"][k]:
            raise ValueError("prefix physics/timestep mismatch: "+k)
    terminal=a["terminal_checkpoint"]
    if b["restart"]["metadata_sha256"]!=terminal["metadata_sha256"] or b["initial_step"]!=a["steps"]:
        raise ValueError("continuation checkpoint identity mismatch")
    if b["restart"]["metadata"]["files"]!=terminal["files"]:
        raise ValueError("continuation field identity mismatch")
    boundary={}
    for key in ("E","Z","eps","wmax","bkm","tail_ratio"):
        x,y=float(origin["rows"][-1][key]),float(continuation["rows"][0][key])
        error=abs(x-y)/max(abs(x),abs(y),1e-14);boundary[key]=error
        if error>2e-11:raise ValueError("restart boundary mismatch: "+key)
    # Exact original files survive the canonical assembled view.
    preserved=work/"coarse_continuation_small"
    small_snapshot(right,preserved)
    sources={name:{"preflight":sha(left/name),"continuation":sha(right/name)} for name in CSV_KEYS}
    staged=[]
    for name,keys in CSV_KEYS.items():
        ha,la=read_csv(left/name);hb,lb=read_csv(right/name)
        if ha!=hb:raise ValueError("prefix CSV schema mismatch: "+name)
        if any(float(r["t"])>p["preflight_t"]+1e-12 for r in la) or any(float(r["t"])<p["preflight_t"]-1e-12 for r in lb):
            raise ValueError("overlapping/off-prefix evidence")
        later=[dict(r) for r in lb if float(r["t"])>p["preflight_t"]+1e-12]
        if name=="diagnostics.csv":
            for r in later:r["wall_s"]=str(float(r["wall_s"])+a["wall_s"])
        combined=la+later
        identity=[tuple(r[k] for k in keys) for r in combined]
        if len(set(identity))!=len(identity):raise ValueError("duplicate prefix event")
        temp=right/(name+".prefix.part")
        with temp.open("x",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=ha);writer.writeheader();writer.writerows(combined)
        staged.append((temp,right/name))
    ha,la=read_csv(left/"steps.csv");hb,lb=read_csv(right/"steps.csv")
    later=[dict(r) for r in lb]
    for r in later:r["wall_s"]=str(float(r["wall_s"])+a["wall_s"])
    combined=la+later
    if ha!=hb or [int(r["step"]) for r in combined]!=list(range(1,b["steps"]+1)):
        raise ValueError("missing/duplicate integrated step")
    temp=right/"steps.csv.prefix.part"
    with temp.open("x",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=ha);writer.writeheader();writer.writerows(combined)
    staged.append((temp,right/"steps.csv"))
    m=dict(b,start_t=0.,initial_step=0,achieved_steps=b["steps"],restart=None,
           continuation_restart=b["restart"],
           prefix_assembly=dict(preflight_manifest_sha256=sha(left/"run.json"),
             continuation_manifest_sha256=sha(preserved/"run.json"),
             checkpoint_metadata_sha256=terminal["metadata_sha256"],boundary_relative_errors=boundary,
             source_csv_sha256=sources,continuation_start_t=p["preflight_t"],
             scope="same N/grid/physics/step cap; original analytic IC through retained preflight state"))
    history=[]
    for entry in a["checkpoint_history"]:
        item=dict(entry,retained=False,path="../preflight/"+entry["path"])
        history.append(item)
        archive=left/"checkpoint_metadata"/(Path(entry["path"]).name+".json")
        (right/"checkpoint_metadata").mkdir(exist_ok=True)
        shutil.copyfile(archive,right/"checkpoint_metadata"/archive.name)
    m["checkpoint_history"]=history+b["checkpoint_history"]
    ta,tb=a["timing"],b["timing"]
    timing={}
    for k in ("seconds","calls"):
        timing[k]={n:ta[k].get(n,0)+tb[k].get(n,0) for n in set(ta[k])|set(tb[k])}
    timing.update(process_wall_s=ta["process_wall_s"]+tb["process_wall_s"],
                  unattributed_wall_s=ta["unattributed_wall_s"]+tb["unattributed_wall_s"],
                  convention="Sum of two disjoint original-IC prefix/continuation processes; phase originals preserved.")
    m["timing"]=timing;m["wall_s"]=a["wall_s"]+b["wall_s"]
    m["last_accepted"]=dict(b["last_accepted"],wall_s=b["last_accepted"]["wall_s"]+a["wall_s"])
    ca,cb=a["clock_snapping"],b["clock_snapping"]
    m["clock_snapping"]=dict(cb,events=ca["events"]+cb["events"],
        max_abs_adjustment=max(ca["max_abs_adjustment"],cb["max_abs_adjustment"]),
        signed_total_adjustment=ca["signed_total_adjustment"]+cb["signed_total_adjustment"])
    for k in ("peak_allocated_GB","peak_reserved_GB"):
        if k in a["memory"] and k in b["memory"]:
            m["memory"][k]=max(a["memory"][k],b["memory"][k])
    dta,dtb=a["dt_statistics"],b["dt_statistics"]
    m["dt_statistics"]=dict(min=min(dta["min"],dtb["min"]),max=max(dta["max"],dtb["max"]),
       cfl_limited_steps=dta["cfl_limited_steps"]+dtb["cfl_limited_steps"],
       event_limited_steps=dta["event_limited_steps"]+dtb["event_limited_steps"])
    for temp,target in staged:temp.replace(target)
    write(right/"checkpoint_history.json",m["checkpoint_history"]);write(right/"timing.json",timing)
    write(right/"run.json",m)
    sampling_a=json.loads((left/"sampling_timing.json").read_text());sampling_b=json.loads((right/"sampling_timing.json").read_text())
    write(right/"sampling_timing.json",dict(events=len(origin["rows"])+len(continuation["rows"])-1,
       refinement_calls=sampling_a["refinement_calls"]+sampling_b["refinement_calls"],
       refinement_seconds=sampling_a["refinement_seconds"]+sampling_b["refinement_seconds"],
       selected_times=sampling_a["selected_times"]+sampling_b["selected_times"],
       qualification="Per-phase totals retained; continuation repeated anchor had no second refinement."))
    driver=json.loads((right/"driver_memory_summary.json").read_text()) if (right/"driver_memory_summary.json").exists() else None
    if driver:
        previous=json.loads((left/"driver_memory_summary.json").read_text())
        driver["peak_driver_used_fraction"]=max(driver["peak_driver_used_fraction"],previous["peak_driver_used_fraction"])
        write(right/"driver_memory_summary.json",driver)
    validate(right,p["N"],p["prefix"],p["log_dt"])
    receipt=dict(verified=True,prefix_end_t=p["preflight_t"],target_t=p["prefix"],
                 boundary_relative_errors=boundary,preflight_manifest_sha256=sha(left/"run.json"),
                 original_continuation_manifest_sha256=sha(preserved/"run.json"),
                 combined_manifest_sha256=sha(right/"run.json"),merged_diagnostic_events=len(origin["rows"])+len(continuation["rows"])-1,
                 integrated_steps=m["achieved_steps"])
    write(work/"continuation_receipt.json",receipt)
    return receipt

def release_prefix(work):
    work=Path(work).resolve()
    receipt=json.loads((work/"continuation_receipt.json").read_text())
    if not receipt.get("verified") or sha(work/"coarse/run.json")!=receipt["combined_manifest_sha256"]:
        raise ValueError("verified assembled trajectory required before pruning anchor")
    source=work/"preflight"
    if sha(source/"run.json")!=receipt["preflight_manifest_sha256"]:
        raise ValueError("verified prefix manifest changed before release")
    if not (source/"checkpoint_metadata").is_dir():raise ValueError("archived metadata required")
    arrays=source/"checkpoints"
    if arrays.is_dir():
        if not arrays.resolve().is_relative_to(source.resolve()) or arrays.is_symlink():
            raise ValueError("preflight array target outside owned directory")
        shutil.rmtree(arrays)
    write(work/"preflight_release.json",dict(released_after_verified_continuation=True,
          checkpoint_metadata_preserved=True,preflight_manifest_sha256=sha(source/"run.json")))
