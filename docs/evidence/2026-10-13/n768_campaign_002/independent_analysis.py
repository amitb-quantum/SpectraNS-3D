#!/usr/bin/env python3
"""Independent CSV arithmetic for the protected three-grid result; no solver execution."""
import argparse,csv,hashlib,json,math
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))
def time_map(rows,start,end):
    return {round(float(r["t"]),12):r for r in rows if start-1e-12<=float(r["t"])<=end+1e-12}
def spectra(path):
    out={}
    for r in read(path):
        out.setdefault(round(float(r["t"]),12),{})[int(r["shell_k"])]=float(r["E_shell_mean_density"])
    return out
def relative(a,b):
    return abs(a-b)/max(abs(a),abs(b),1e-14)
def compare(left,right,start,end):
    a=time_map(read(left/"diagnostics.csv"),start,end)
    b=time_map(read(right/"diagnostics.csv"),start,end)
    assert sorted(a)==sorted(b) and min(a)==start and max(a)==end
    ba=time_map(read(left/"enstrophy.csv"),start,end)
    bb=time_map(read(right/"enstrophy.csv"),start,end)
    sa,sb=spectra(left/"spectra.csv"),spectra(right/"spectra.csv")
    values={k:[] for k in ["E","Z","wmax","bkm","net_scaled","spectrum_L1_over_E"]}
    for t in sorted(a):
        for k in ["E","Z","wmax","bkm"]:
            values[k].append((relative(float(a[t][k]),float(b[t][k])),t))
        scale=max(abs(float(ba[t]["production"]))+abs(float(ba[t]["viscous_loss"])),
                  abs(float(bb[t]["production"]))+abs(float(bb[t]["viscous_loss"])),1e-14)
        values["net_scaled"].append((abs(float(ba[t]["net_production"])-float(bb[t]["net_production"]))/scale,t))
        shells=set(sa[t])|set(sb[t])
        l1=math.fsum(abs(sa[t].get(k,0)-sb[t].get(k,0)) for k in sorted(shells))
        values["spectrum_L1_over_E"].append((l1/max(float(a[t]["E"]),float(b[t]["E"]),1e-30),t))
    maxima={k:{"relative_difference":max(v)[0],"at_t":max(v)[1]} for k,v in values.items()}
    steps=[int(x[end]["step"])-int(x[start]["step"]) for x in [a,b]]
    return {"start_t":start,"end_t":end,"matched_events":len(a),"maxima":maxima,
            "left_steps":steps[0],"right_steps":steps[1],"step_ratio":steps[1]/max(1,steps[0])}
def observed(path):
    manifest=json.loads((path/"run.json").read_text())
    accepted=float(manifest["last_accepted"]["t"])
    rows=[r for r in read(path/"diagnostics.csv") if float(r["t"])<=accepted+1e-12]
    budgets=[r for r in read(path/"enstrophy.csv") if float(r["t"])<=accepted+1e-12]
    peak=max(rows,key=lambda r:float(r["wmax"]))
    zpeak=max(rows,key=lambda r:float(r["Z"]))
    netpeak=max(budgets,key=lambda r:float(r["net_production"]))
    allrows=read(path/"diagnostics.csv")
    failed=[r for r in allrows if float(r["t"])>accepted+1e-12]
    return {"accepted_end_t":accepted,"stop_reason":manifest.get("stop_reason"),
            "sampled_wmax_peak":{"t":float(peak["t"]),"value":float(peak["wmax"])},
            "sampled_Z_peak":{"t":float(zpeak["t"]),"value":float(zpeak["Z"])},
            "sampled_net_peak":{"t":float(netpeak["t"]),"value":float(netpeak["net_production"])},
            "endpoint":{"t":float(rows[-1]["t"]),"E":float(rows[-1]["E"]),"Z":float(rows[-1]["Z"]),"wmax":float(rows[-1]["wmax"]),"tail_ratio":float(rows[-1]["tail_ratio"]),"net_production":float(budgets[-1]["net_production"])},
            "first_excluded_row":failed[0] if failed else None,"memory":manifest["memory"],
            "dt_statistics":manifest.get("dt_statistics",{"recorded":False}),"clock_snapping":manifest.get("clock_snapping",{"recorded":False}),
            "driver":json.loads((path/"driver_memory_summary.json").read_text()) if (path/"driver_memory_summary.json").exists() else None}

def numerical_review(path,gate):
    manifest=json.loads((path/"run.json").read_text())
    nu=float(manifest["parameters"]["nu"]);N=int(manifest["parameters"]["N"])
    rows=read(path/"diagnostics.csv");budgets=read(path/"enstrophy.csv");shells=spectra(path/"spectra.csv")
    assert len(rows)==len(budgets) and [r["t"] for r in rows]==[r["t"] for r in budgets]
    E0=float(manifest["restart"]["metadata"]["E0"]) if manifest.get("restart") else float(rows[0]["E"])
    expected_shells=set(range(int(math.sqrt(3)*(N//2)+.5)+1))
    metrics={"max_tail":0.,"max_divergence":0.,"max_parseval_relative":0.,"max_energy_fd_residual":0.,"max_enstrophy_identity_relative":0.,"max_eps_identity_relative":0.}
    previous=None
    for raw,budget in zip(rows,budgets):
        r={k:float(v) for k,v in raw.items() if v!=""}
        assert all(math.isfinite(v) for v in r.values())
        assert all(math.isfinite(float(v)) for v in budget.values() if v!="")
        t=round(r["t"],12);bins=shells[t]
        assert set(bins)==expected_shells and all(math.isfinite(v) and v>=0 for v in bins.values())
        parseval=abs(math.fsum(bins.values())-r["E"])/max(r["E"],1e-300)
        scale=max(abs(float(budget["production"])),abs(float(budget["dZdt_rhs"])),nu*abs(float(budget["grad_omega_sq"])),1e-300)
        identity=abs(float(budget["dZdt_rhs"])-(float(budget["production"])-nu*float(budget["grad_omega_sq"])))/scale
        metrics["max_tail"]=max(metrics["max_tail"],r["tail_ratio"])
        metrics["max_divergence"]=max(metrics["max_divergence"],r["div_max"])
        metrics["max_parseval_relative"]=max(metrics["max_parseval_relative"],parseval)
        metrics["max_enstrophy_identity_relative"]=max(metrics["max_enstrophy_identity_relative"],identity)
        metrics["max_eps_identity_relative"]=max(metrics["max_eps_identity_relative"],relative(r["eps"],2*nu*r["Z"]))
        assert r["tail_ratio"]<=gate["tail_ratio_max"]
        assert r["div_max"]<=gate["divergence_absolute_max"]
        assert r["E"]<=E0*(1+gate["energy_initial_rise_fraction_E0"])
        assert parseval<=gate["parseval_relative_tolerance"] and identity<=1e-8
        if previous:
            assert abs(r["t"]-previous["t"]-.01)<=1e-11
            assert r["E"]<=previous["E"]+gate["energy_interval_rise_fraction_E0"]*E0
            metrics["max_energy_fd_residual"]=max(metrics["max_energy_fd_residual"],abs(r["budget_resid_rel"]))
            assert abs(r["budget_resid_rel"])<=gate["energy_fd_budget_relative_tolerance"]
        previous=r
    mem=manifest["memory"]
    metrics["allocator_peak_allocated_fraction"]=mem["peak_allocated_GB"]/mem["total_GB"]
    metrics["allocator_peak_reserved_fraction"]=mem["peak_reserved_GB"]/mem["total_GB"]
    driver=json.loads((path/"driver_memory_summary.json").read_text())
    metrics["sampled_driver_peak_fraction"]=driver["peak_driver_used_fraction"]
    assert max(metrics["allocator_peak_allocated_fraction"],metrics["allocator_peak_reserved_fraction"],metrics["sampled_driver_peak_fraction"])<gate["memory_fraction_max"]
    return {"status":"passed","events":len(rows),"metrics":metrics,"driver_sampling_limitation":"Periodic samples cannot bound unobserved transients."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=Path,default=Path.cwd())
    p.add_argument("--campaign",type=Path,required=True)
    a=p.parse_args();project=a.project.resolve();out=a.campaign.resolve()
    receipt=json.loads((out/"protected_receipt.json").read_text())
    assert receipt["protected_validated"] is True
    protected=out/"protected"
    assert digest(protected/"collection_manifest.json")==receipt["protected_manifest_sha256"]
    files=json.loads((protected/"collection_manifest.json").read_text())["files"]
    for name,expected in files.items():assert digest(protected/name)==expected,name
    binding=json.loads((protected/"source_binding.json").read_text())
    for name in ("configs/h100_acceptance.json","configs/n512_interpolated_peak_reference.json","configs/n768_baseline_reference.json","configs/n768_third_grid_proposal.json"):
        assert digest(project/name)==binding[name],name
    ref512=json.loads((project/"configs/n512_interpolated_peak_reference.json").read_text())
    b512=project/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse"
    for name,expected in ref512["historical_small_files_sha256"].items():assert digest(b512/name)==expected,name
    ref640=json.loads((project/"configs/n768_baseline_reference.json").read_text())
    for name,expected in ref640["files"].items():assert digest(project/name)==expected,name
    b640=project/ref640["N640_directory"]
    coarse,fine=protected/"coarse",protected/"fine"
    pairs={}
    for label,left,right in [("N512_N640",b512,b640),("N512_N768",b512,coarse),("N640_N768",b640,coarse)]:
        v=compare(left,right,0.,1.1)
        primary=max(v["maxima"][k]["relative_difference"] for k in ("Z","net_scaled"))
        v["classification"]="consistent_at_declared_tolerance" if primary<=.001 else "material_discretization_sensitivity" if primary>=.01 else "intermediate_sensitivity"
        pairs[label]=v
    temporal=compare(coarse,fine,1.,1.1)
    temporal["status"]="passed" if max(v["relative_difference"] for v in temporal["maxima"].values())<=1e-5 and temporal["step_ratio"]>=1.9 else "failed"
    recorded=json.loads((protected/"assessment.json").read_text())
    for label,key in [("N512_N768","spatial"),("N640_N768","spatial_N640_N768")]:
        for name,value in pairs[label]["maxima"].items():
            assert math.isclose(value["relative_difference"],recorded[key]["errors"][name],rel_tol=1e-10,abs_tol=1e-13),(label,name)
    for name,value in temporal["maxima"].items():
        assert math.isclose(value["relative_difference"],recorded["temporal"]["errors"][name],rel_tol=1e-10,abs_tol=1e-13),name
    tables={N:{round(float(r["t"]),12):r for r in read(folder/"interpolated_vorticity.csv")} for N,folder in [(640,b640),(768,coarse)]}
    matched=[]
    for reference in ref512["checkpoints"]:
        t=reference["t"];actual={512:reference["peak"],**{N:tables[N][round(t,12)] for N in (640,768)}}
        values={N:float(v["fourier_refined_peak_estimate"]) for N,v in actual.items()}
        stable={N:v["estimator_stable"] is True or v["estimator_stable"]=="True" for N,v in actual.items()}
        point={"t":t,"values":values,"stable":stable,"pairs":{}}
        for left,right in [(512,640),(640,768),(512,768)]:
            error=relative(values[left],values[right])
            point["pairs"][str(left)+"_"+str(right)]={"relative_difference":error,"classification":"inconclusive_estimator" if not(stable[left] and stable[right]) else "consistent" if error<=.001 else "discretization_sensitive"}
        matched.append(point)
    ds=[time_map(read(f/"diagnostics.csv"),0.,1.1) for f in [b512,b640,coarse]]
    bs=[time_map(read(f/"enstrophy.csv"),0.,1.1) for f in [b512,b640,coarse]]
    signed=[]
    for t in sorted(ds[0]):
        for quantity in ("Z","production","viscous_loss","net_production"):
            source=ds if quantity=="Z" else bs;values=[float(x[t][quantity]) for x in source]
            d1,d2=values[1]-values[0],values[2]-values[1]
            signed.append({"t":t,"quantity":quantity,"values":values,"increment_512_640":d1,"increment_640_768":d2,"same_direction":d1*d2>0,"increment_magnitude_shrinks":abs(d2)<abs(d1),"magnitude_ratio":None if d1==0 else abs(d2/d1)})
    summary={}
    for quantity in ("Z","production","viscous_loss","net_production"):
        records=[r for r in signed if r["quantity"]==quantity and r["t"]>0]
        summary[quantity]={"events":len(records),"same_direction":sum(r["same_direction"] for r in records),"increment_magnitude_shrinks":sum(r["increment_magnitude_shrinks"] for r in records)}
    gate=json.loads((project/"configs/h100_acceptance.json").read_text())
    numerical={"coarse":numerical_review(coarse,gate),"fine":numerical_review(fine,gate)}
    result={"status":"completed_independent_three_grid_assessment","analysis_sha256":digest(__file__),
        "protected_manifest_verified_files":len(files),"numerical":numerical,"local_temporal":temporal,"pairs":pairs,
        "matched_fourier_peaks":matched,"signed_refinement_records":signed,"signed_trend_summary":summary,
        "N512":observed(b512),"N640":observed(b640),"N768_coarse":observed(coarse),"N768_fine":observed(fine),
        "scope":"Unequal-grid finite-interval observable consistency and local temporal continuation. No automatic order, continuum error bound, turnover, regularity or blowup certificate.",
        "input_sha256":{str(f.relative_to(project)):digest(f) for folder in [b512,b640,coarse,fine] for f in [folder/n for n in ["diagnostics.csv","enstrophy.csv","spectra.csv","run.json"]]}}
    (out/"independent_assessment.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"pairs":pairs,"temporal":temporal,"matched_peaks":matched,"signed_summary":summary},indent=2))
if __name__=="__main__":main()
