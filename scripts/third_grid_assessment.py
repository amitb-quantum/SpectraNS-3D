"""Independent validation of phase files and matched observable comparisons."""
import csv,json,math
from pathlib import Path
from cloud_policy import ROOT,verify_audited_sources
from extension_state import diagnostic_failure,sha
from third_grid_review import fit_local_peak,compare_fitted_local_peaks

def rows(path):
    with Path(path).open() as f:return list(csv.DictReader(f))

def validate(directory,N,target,log_dt,*,current_driver=True):
    directory=Path(directory);m=json.loads((directory/"run.json").read_text())
    if m["source_sha256"]!=verify_audited_sources() or m["parameters"]["N"]!=N:
        raise ValueError("phase core/grid mismatch")
    if current_driver and m["driver_sha256"]!=sha(ROOT/"scripts/ns_extension.py"):
        raise ValueError("phase wrapper mismatch")
    if m["status"]!="bounded_complete" or m["stop_reason"]!="max_simulated_time" or abs(m["t"]-target)>1e-12:
        raise ValueError("required phase did not reach its accepted endpoint")
    ds=rows(directory/"diagnostics.csv");bs=rows(directory/"enstrophy.csv")
    if not ds or [r["t"] for r in ds]!=[r["t"] for r in bs]:raise ValueError("diagnostic times differ")
    expected=[round(m["start_t"]+i*log_dt,12) for i in range(round((target-m["start_t"])/log_dt)+1)]
    if [round(float(r["t"]),12) for r in ds]!=expected:
        raise ValueError("required event lattice incomplete")
    spectra={}
    for row in rows(directory/"spectra.csv"):
        t=round(float(row["t"]),12);k=int(row["shell_k"]);v=float(row["E_shell_mean_density"])
        if not math.isfinite(v) or v<0 or k in spectra.setdefault(t,{}):raise ValueError("invalid shell")
        spectra[t][k]=v
    shells=set(range(int(math.sqrt(3)*(N//2)+.5)+1))
    if set(spectra)!={round(float(r["t"]),12) for r in ds} or any(set(v)!=shells for v in spectra.values()):
        raise ValueError("missing full spectra")
    gate=json.loads((ROOT/"configs/h100_acceptance.json").read_text())
    E0=m["restart"]["metadata"]["E0"] if m.get("restart") else float(ds[0]["E"])
    previous=None
    for row,raw in zip(ds,bs):
        row={k:float(v) if v!="" else "" for k,v in row.items()}
        budget={k:float(raw[k]) for k in ("production","grad_omega_sq","dZdt_rhs","residual")}
        bins=[spectra[round(row["t"],12)][k] for k in sorted(shells)]
        failure=diagnostic_failure(row,budget,bins,previous,E0,m["parameters"]["nu"],gate)
        if failure:raise ValueError("independent gate: "+failure)
        if previous and abs(row["t"]-previous["t"]-log_dt)>1e-11:raise ValueError("missing event")
        previous=row
    if current_driver:
        ip=rows(directory/"interpolated_vorticity.csv")
        if [r["t"] for r in ip]!=[r["t"] for r in ds]:raise ValueError("missing per-event interpolation")
        exact=json.loads((directory/"exact_configuration.json").read_text())
        from third_grid_sampling import selected
        phase=exact["request"]["phase"];p=exact["profile"]
        for d,v in zip(ds,ip):
            if abs(float(d["wmax"])-float(v["sampled_wmax"]))/max(float(d["wmax"]),1e-30)>2e-11:
                raise ValueError("grid maximum mismatch")
            expected=selected(float(d["t"]),phase,p,continued=phase=="coarse" and m["start_t"]>0)
            if v.get("refinement_performed")!=str(expected):
                raise ValueError("predeclared refinement schedule mismatch")
            keys=("fourier_refined_peak_estimate","sampling_bias_fraction","seed_expansion_relative_change","last_level_relative_increment")
            if expected:
                if not all(math.isfinite(float(v[k])) for k in keys) or v["estimator_stable"] not in ("True","False"):
                    raise ValueError("nonfinite interpolation")
            elif any(v[k]!="" for k in (*keys,"estimator_stable")):
                raise ValueError("unperformed refinement must remain explicitly empty")
        for entry in m["checkpoint_history"]:
            archive=directory/"checkpoint_metadata"/(Path(entry["path"]).name+".json")
            if sha(archive)!=entry["metadata_sha256"]:raise ValueError("checkpoint metadata missing")
    for entry in m["checkpoint_history"]:
        if entry["retained"]:
            p=directory/entry["path"]
            # Small snapshots contain metadata but not arrays. Full validation
            # at the worker/controller backend must additionally hash arrays.
            if (p/"checkpoint.json").exists() and sha(p/"checkpoint.json")!=entry["metadata_sha256"]:
                raise ValueError("checkpoint metadata mismatch")
            for n,h in entry["files"].items():
                if (p/n).exists() and sha(p/n)!=h:raise ValueError("checkpoint field mismatch")
    return dict(manifest=m,rows=ds,budgets=bs,spectra=spectra)

def comparison(left,right,start,end,tolerance,*,temporal=False):
    a={round(float(r["t"]),12):r for r in left["rows"]}
    b={round(float(r["t"]),12):r for r in right["rows"]}
    keys=sorted(t for t in a if start-1e-12<=t<=end+1e-12)
    if keys!=sorted(t for t in b if start-1e-12<=t<=end+1e-12) or not keys or abs(keys[0]-start)>1e-12 or abs(keys[-1]-end)>1e-12:
        raise ValueError("required matched window incomplete")
    ba={round(float(r["t"]),12):r for r in left["budgets"]}
    bb={round(float(r["t"]),12):r for r in right["budgets"]}
    errors={k:0. for k in ("E","Z","wmax","bkm","net_scaled","spectrum_L1_over_E")}
    for t in keys:
        for k in ("E","Z","wmax","bkm"):
            x,y=float(a[t][k]),float(b[t][k])
            errors[k]=max(errors[k],abs(x-y)/max(abs(x),abs(y),1e-14))
        scale=max(abs(float(ba[t]["production"]))+abs(float(ba[t]["viscous_loss"])),
                  abs(float(bb[t]["production"]))+abs(float(bb[t]["viscous_loss"])),1e-14)
        errors["net_scaled"]=max(errors["net_scaled"],abs(float(ba[t]["net_production"])-float(bb[t]["net_production"]))/scale)
        shells=set(left["spectra"][t])|set(right["spectra"][t])
        se=sum(abs(left["spectra"][t].get(k,0)-right["spectra"][t].get(k,0)) for k in shells)/max(float(a[t]["E"]),float(b[t]["E"]),1e-30)
        errors["spectrum_L1_over_E"]=max(errors["spectrum_L1_over_E"],se)
    result=dict(start_t=start,end_t=end,matched_events=len(keys),errors=errors)
    if temporal:
        coarse_steps=int(a[keys[-1]]["step"])-int(a[keys[0]]["step"])
        fine_steps=int(b[keys[-1]]["step"])-int(b[keys[0]]["step"])
        ratio=fine_steps/max(coarse_steps,1)
        result.update(effective_step_ratio=ratio,status="passed" if max(errors.values())<=tolerance and ratio>=1.9 else "failed",
                      scope="local continuation only; inherited prefix time error is common")
    else:
        primary=max(errors["Z"],errors["net_scaled"])
        result.update(status="consistent_at_declared_tolerance" if primary<=tolerance else
                      "material_discretization_sensitivity" if primary>=.01 else "intermediate_sensitivity",
                      scope="two-grid observable comparison; no resolution certificate or convergence order")
    return result

def checkpoint_at(directory,t,require_arrays=True):
    d=Path(directory);m=json.loads((d/"run.json").read_text())
    candidates=[e for e in m["checkpoint_history"] if e["retained"] and abs(e["t"]-t)<1e-12]
    if not candidates:raise ValueError("required checkpoint absent")
    entry=next((e for e in candidates if e["kind"]=="regular"),candidates[0]);path=d/entry["path"]
    if sha(path/"checkpoint.json")!=entry["metadata_sha256"] or any((require_arrays or (path/n).exists()) and sha(path/n)!=h for n,h in entry["files"].items()):
        raise ValueError("checkpoint checksum mismatch")
    return path

def historical_reference():
    """Validate the accepted N512 prefix, excluding its first failing event."""
    d=ROOT/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse"
    m=json.loads((d/"run.json").read_text())
    if m["source_sha256"]!=verify_audited_sources() or m["status"]!="gate_trip" or abs(m["last_accepted"]["t"]-1.1)>1e-12:
        raise ValueError("historical accepted N512 prefix does not match reviewed evidence")
    reference=json.loads((ROOT/"configs/n512_interpolated_peak_reference.json").read_text())
    if any(sha(d/n)!=h for n,h in reference["historical_small_files_sha256"].items()):
        raise ValueError("historical accepted evidence hashes changed")
    ds=[r for r in rows(d/"diagnostics.csv") if float(r["t"])<=1.1+1e-12]
    bs=[r for r in rows(d/"enstrophy.csv") if float(r["t"])<=1.1+1e-12]
    spectra={}
    for r in rows(d/"spectra.csv"):
        if float(r["t"])<=1.1+1e-12:
            spectra.setdefault(round(float(r["t"]),12),{})[int(r["shell_k"])]=float(r["E_shell_mean_density"])
    if len(ds)!=111 or [r["t"] for r in ds]!=[r["t"] for r in bs]:
        raise ValueError("historical prefix missing events")
    gate=json.loads((ROOT/"configs/h100_acceptance.json").read_text())
    previous=None
    for raw,b in zip(ds,bs):
        r={k:float(v) if v!="" else "" for k,v in raw.items()}
        bins=spectra[round(r["t"],12)]
        if set(bins)!=set(range(int(math.sqrt(3)*256+.5)+1)):
            raise ValueError("historical full spectra missing")
        budget={k:float(b[k]) for k in ("production","grad_omega_sq","dZdt_rhs","residual")}
        failure=diagnostic_failure(r,budget,[bins[k] for k in sorted(bins)],previous,float(ds[0]["E"]),.0005,gate)
        if failure:raise ValueError("historical accepted prefix gate failed")
        previous=r
    return dict(manifest=m,rows=ds,budgets=bs,spectra=spectra)

def matched_peak_comparison(coarse,reference):
    from spectral_peak import METHOD
    if reference["status"]!="passed" or reference["method"]!=METHOD or reference["estimator_sha256"]!=sha(ROOT/"scripts/spectral_peak.py"):
        raise ValueError("predeclared interpolated peak reference mismatch")
    actual={round(float(r["t"]),12):r for r in rows(Path(coarse)/"interpolated_vorticity.csv")}
    comparisons=[]
    for r in reference["checkpoints"]:
        value=actual.get(round(r["t"],12))
        if value is None or value.get("refinement_performed")!="True":raise ValueError("matched refined peak event absent")
        a,b=r["peak"]["fourier_refined_peak_estimate"],float(value["fourier_refined_peak_estimate"])
        stable=value["estimator_stable"]=="True" and r["peak"]["estimator_stable"]
        error=abs(a-b)/max(a,b,1e-30)
        comparisons.append(dict(t=r["t"],N512=a,N768=b,relative_difference=error,
             status="inconclusive_estimator" if not stable else "consistent" if error<=.001 else "discretization_sensitive",
             N512_sampling_bias=r["peak"]["sampling_bias_fraction"],
             N768_sampling_bias=float(value["sampling_bias_fraction"])))
    return dict(points=comparisons,tolerance=.001,
                scope="matched Fourier local peak estimates with declared seed/search checks; not a certified global supremum")

def historical_640():
    """Exact published accepted trajectory; never a restart field."""
    ref=json.loads((ROOT/"configs/n768_baseline_reference.json").read_text())
    if ref.get("status")!="passed" or ref.get("accepted_end_t")!=1.1:
        raise ValueError("accepted N640 reference missing")
    if any(sha(ROOT/n)!=h for n,h in ref["files"].items()):
        raise ValueError("published N640 baseline changed")
    return validate(ROOT/ref["N640_directory"],640,1.1,.01,current_driver=False)

def matched_640_peaks(coarse):
    ref=json.loads((ROOT/"configs/n768_baseline_reference.json").read_text())
    baseline={round(float(r["t"]),12):r for r in rows(ROOT/ref["N640_directory"]/"interpolated_vorticity.csv")}
    actual={round(float(r["t"]),12):r for r in rows(Path(coarse)/"interpolated_vorticity.csv")}
    points=[]
    for t in (1.,1.1):
        a,b=baseline[t],actual[t]
        if a["refinement_performed"]!="True" or b["refinement_performed"]!="True":
            raise ValueError("matched Fourier estimate missing")
        left,right=float(a["fourier_refined_peak_estimate"]),float(b["fourier_refined_peak_estimate"])
        stable=a["estimator_stable"]=="True" and b["estimator_stable"]=="True"
        error=abs(left-right)/max(abs(left),abs(right),1e-30)
        points.append(dict(t=t,N640=left,N768=right,relative_difference=error,
            status="inconclusive_estimator" if not stable else "consistent" if error<=.001 else "discretization_sensitive",
            N640_sampling_bias=float(a["sampling_bias_fraction"]),N768_sampling_bias=float(b["sampling_bias_fraction"])))
    return dict(points=points,tolerance=.001,scope="Stable local estimates; not certified global suprema.")

def signed_refinement_trends(a,b,c):
    """Paired signed differences; no Richardson order assumption."""
    maps=[{round(float(r["t"]),12):r for r in x["rows"]} for x in (a,b,c)]
    budgets=[{round(float(r["t"]),12):r for r in x["budgets"]} for x in (a,b,c)]
    records=[]
    for t in sorted(maps[0]):
        for quantity in ("Z","production","viscous_loss","net_production"):
            source=maps if quantity=="Z" else budgets
            values=[float(x[t][quantity]) for x in source]
            d1,d2=values[1]-values[0],values[2]-values[1]
            records.append(dict(t=t,quantity=quantity,N512=values[0],N640=values[1],N768=values[2],
                increment_512_640=d1,increment_640_768=d2,
                same_direction=d1*d2>0,increment_magnitude_shrinks=abs(d2)<abs(d1),
                magnitude_ratio=None if d1==0 else abs(d2/d1)))
    return dict(records=records,scope="Unequal refinement ratios 1.25 and1.2; shrinking increments alone do not establish an order or continuum error.")
