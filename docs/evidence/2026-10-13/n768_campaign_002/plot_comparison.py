
#!/usr/bin/env python3
"""CPU-only scientific figure from accepted published/protected CSVs."""
import argparse,csv,json,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def rows(p):
    with p.open(newline="") as f:return list(csv.DictReader(f))
def times(p):
    return {round(float(r["t"]),12):r for r in rows(p) if float(r["t"])<=1.1+1e-12}
def spectra(p,t):
    return {int(r["shell_k"]):float(r["E_shell_mean_density"]) for r in rows(p) if abs(float(r["t"])-t)<1e-12}
def main():
    a=argparse.ArgumentParser();a.add_argument("--project",type=Path,default=Path.cwd());a.add_argument("--campaign",type=Path,required=True)
    arg=a.parse_args();root=arg.project.resolve();p=arg.campaign.resolve()
    assert json.loads((p/"protected_receipt.json").read_text())["protected_validated"]
    reference=json.loads((root/"configs/n768_baseline_reference.json").read_text())
    folders={512:root/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse",640:root/reference["N640_directory"],768:p/"protected/coarse"}
    colors={512:"#b65e24",640:"#2378ad",768:"#278050"}
    data={N:times(f/"diagnostics.csv") for N,f in folders.items()}
    budgets={N:times(f/"enstrophy.csv") for N,f in folders.items()}
    T=sorted(data[512]);assert len(T)==111 and all(sorted(v)==T for v in data.values())
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(2,3,figsize=(15,9),layout="constrained")
    for N in folders:
        axes[0,0].plot(T,[float(data[N][t]["Z"]) for t in T],color=colors[N],label=f"N{N}")
        axes[0,1].plot(T,[float(budgets[N][t]["net_production"]) for t in T],color=colors[N],label=f"N{N}")
    axes[0,0].set(title="Enstrophy on the common accepted interval",xlabel="t",ylabel="Z")
    axes[0,1].set(title="Instantaneous stretching minus viscous loss",xlabel="t",ylabel="P - V")
    paircolors={(512,640):"#b65e24",(640,768):"#278050",(512,768):"#6b5b95"}
    for left,right in paircolors:
        z=[];net=[]
        for t in T:
            x,y=[float(data[N][t]["Z"]) for N in (left,right)]
            z.append(100*abs(x-y)/max(abs(x),abs(y),1e-14))
            ba,bb=[budgets[N][t] for N in (left,right)]
            scale=max(abs(float(ba["production"]))+abs(float(ba["viscous_loss"])),abs(float(bb["production"]))+abs(float(bb["viscous_loss"])),1e-14)
            net.append(100*abs(float(ba["net_production"])-float(bb["net_production"]))/scale)
        label=f"N{left}/N{right}"
        axes[0,2].plot(T,z,color=paircolors[left,right],label=label)
        axes[1,0].plot(T,net,color=paircolors[left,right],label=label)
    for ax in [axes[0,2],axes[1,0]]:
        ax.axhline(.1,color="#555555",ls=":",lw=1.2,label="0.1% criterion")
    axes[0,2].set(title="Matched enstrophy differences",xlabel="t",ylabel="Relative difference (%)")
    axes[1,0].set(title="Matched net-production differences",xlabel="t",ylabel="Difference / max(P + V) (%)")
    assessment=json.loads((p/"independent_assessment.json").read_text())
    for N in folders:
        tx=[];ys=[]
        for point in assessment["matched_fourier_peaks"]:
            if point["stable"][str(N)]:
                tx.append(point["t"]);ys.append(point["values"][str(N)])
        axes[1,1].plot(tx,ys,"o--",color=colors[N],label=f"N{N}",lw=1)
    axes[1,1].set(title="Stable local Fourier estimates: two matched times",xlabel="t",ylabel="Local peak estimate")
    for N,f in folders.items():
        bins=spectra(f/"spectra.csv",1.1)
        k=[s for s,v in bins.items() if s>0 and v>0 and s<=math.ceil(N/3)]
        axes[1,2].loglog(k,[bins[s] for s in k],color=colors[N],label=f"N{N}")
        axes[1,2].axvline(N/3,color=colors[N],ls=":",lw=.8)
    axes[1,2].set(title="Full retained shell energy spectra at t=1.10",xlabel="Rounded shell k (dotted: N/3)",ylabel="E_shell")
    for ax in axes.flat:
        ax.grid(alpha=.18);ax.legend(fontsize=8,frameon=False)
    fig.suptitle("SpectraNS-3D: original-IC N512 / N640 / N768, common accepted window 0–1.10",fontsize=15)
    fig.savefig(p/"comparison.png",dpi=160);fig.savefig(p/"comparison.svg")
    (p/"figure_tool_versions.json").write_text(json.dumps({"matplotlib":matplotlib.__version__,"numpy":np.__version__,"simulation_environment_modified":False},indent=2)+"\n")
if __name__=="__main__":main()
