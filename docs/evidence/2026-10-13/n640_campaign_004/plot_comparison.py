#!/usr/bin/env python3
"""Render the protected two-grid comparison; plotting never executes the solver."""
import argparse,csv,json,platform
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

def rows(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))
def mapped(path,start=0.,end=1.1):
    return {round(float(r["t"]),12):r for r in rows(path) if start-1e-12<=float(r["t"])<=end+1e-12}
def spectra(path):
    out={}
    for r in rows(path):
        out.setdefault(round(float(r["t"]),12),{})[int(r["shell_k"])]=float(r["E_shell_mean_density"])
    return out
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=Path,default=Path.cwd())
    p.add_argument("--evidence",type=Path,required=True)
    a=p.parse_args();e=a.evidence.resolve();project=a.project.resolve()
    assert json.loads((e/"protected_receipt.json").read_text())["protected_validated"]
    base=project/"artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse"
    coarse=e/"protected/coarse";fine=e/"protected/fine"
    x=mapped(base/"diagnostics.csv");y=mapped(coarse/"diagnostics.csv");z=mapped(fine/"diagnostics.csv",1.,1.1)
    bx=mapped(base/"enstrophy.csv");by=mapped(coarse/"enstrophy.csv");bz=mapped(fine/"enstrophy.csv",1.,1.1)
    t=np.asarray(sorted(x));tf=np.asarray(sorted(z))
    assert sorted(x)==sorted(y) and len(t)==111 and len(tf)==11
    plt.rcParams.update({"font.size":10,"axes.titlesize":12,"axes.labelsize":11,"legend.fontsize":9,"svg.fonttype":"none"})
    fig,ax=plt.subplots(2,2,figsize=(12.8,8.8),layout="constrained")
    blue="#23679e";orange="#c95d19";green="#27704e"
    ax[0,0].plot(t,[float(x[v]["Z"]) for v in t],color=blue,lw=2,label="N512 accepted")
    ax[0,0].plot(t,[float(y[v]["Z"]) for v in t],color=orange,lw=1.7,ls="--",label="N640 coarse")
    ax[0,0].plot(tf,[float(z[v]["Z"]) for v in tf],color=green,lw=1.2,label="N640 fine window")
    ax[0,0].set(title="A  Enstrophy",xlabel="Simulated time",ylabel="Z")
    ax[0,0].legend(loc="upper left")
    for records,color,label,xx,ls in [(bx,blue,"N512",t,"-"),(by,orange,"N640",t,"--"),(bz,green,"N640 fine",tf,":")]:
        ax[0,1].plot(xx,[float(records[v]["net_production"]) for v in xx],color=color,label=label,ls=ls,lw=1.8)
    ax[0,1].axhline(0,color="0.65",lw=.8)
    ax[0,1].set(title="B  Net enstrophy production",xlabel="Simulated time",ylabel="P - V")
    ax[0,1].legend(loc="upper left")
    ez=[];en=[]
    for v in t:
        a0,b0=float(x[v]["Z"]),float(y[v]["Z"])
        ez.append(100*abs(a0-b0)/max(abs(a0),abs(b0),1e-14))
        scale=max(abs(float(bx[v]["production"]))+abs(float(bx[v]["viscous_loss"])),abs(float(by[v]["production"]))+abs(float(by[v]["viscous_loss"])),1e-14)
        en.append(100*abs(float(bx[v]["net_production"])-float(by[v]["net_production"]))/scale)
    ax[1,0].semilogy(t,np.ma.masked_less_equal(ez,0),color=blue,lw=1.8,label="Relative Z difference")
    ax[1,0].semilogy(t,np.ma.masked_less_equal(en,0),color=orange,lw=1.8,label="Net difference / max(P+V)")
    ax[1,0].axhline(.1,color="#8e3e48",ls=":",lw=1.5,label="0.1% declared criterion")
    ax[1,0].set(title="C  Matched two-grid differences",xlabel="Simulated time",ylabel="Difference (%)")
    ax[1,0].legend(loc="lower right")
    sx,sy=spectra(base/"spectra.csv"),spectra(coarse/"spectra.csv")
    for when,ls in [(1.0,"--"),(1.1,"-")]:
        for data,color,label in [(sx,blue,"N512"),(sy,orange,"N640")]:
            k=np.asarray(sorted(data[when]));energy=np.asarray([data[when][int(v)] for v in k])
            mask=(k>0)&(energy>0)
            ax[1,1].semilogy(k[mask],energy[mask],color=color,ls=ls,lw=1.6,label=f"{label}, t={when:.2f}")
    for n in [512,640]:
        ax[1,1].axvline(n/3,color="0.55",ls=":",lw=.8)
    ax[1,1].set(title="D  Retained energy-shell spectra",xlabel="Shell-center wavenumber",ylabel="Mean-density shell energy",xlim=(0,220))
    ax[1,1].legend(loc="lower left")
    for pane in ax.flat:
        pane.grid(alpha=.18);pane.spines[["top","right"]].set_visible(False)
    for pane in [ax[0,0],ax[0,1],ax[1,0]]:pane.set_xlim(0,1.1)
    fig.suptitle("SpectraNS-3D: protected original-IC comparison through t = 1.10",fontsize=14)
    fig.savefig(e/"comparison.png",dpi=180)
    fig.savefig(e/"comparison.svg")
    plt.close(fig)
    (e/"figure_tool_versions.json").write_text(json.dumps({"python":platform.python_version(),"matplotlib":matplotlib.__version__,"numpy":np.__version__,"scope":"Isolated CPU-only presentation tools. Validated solver environment remains unchanged; no trajectories recomputed."},indent=2)+"\n")
    print("Rendered comparison.png and comparison.svg from hash-verified scientific CSVs.")
if __name__=="__main__":main()
