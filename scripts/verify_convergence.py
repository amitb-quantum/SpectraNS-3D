#!/usr/bin/env python3
"""Small, reproducible CPU refinement evidence; never a high-Re convergence claim."""
import argparse
import json
import math
from pathlib import Path
import time

import numpy as np
import torch
from ns_fast_v3 import Solver, source_hashes


def evolve(n, dt, scheme, target=.4, dtype=torch.float64, shear=False):
    S=Solver(n,.5 if shear else .02,cfl=1.,max_dt=dt,device='cpu',dtype=dtype)
    if shear:
        y=torch.arange(n,dtype=dtype)*S.dx
        real=torch.sin(y)[None,:,None].expand(S.s).contiguous()
        U=[S.fft(real),S.fft(torch.zeros_like(real)),S.fft(torch.zeros_like(real))]
    else:
        U=S.ic_tgv()
    R=[torch.zeros_like(u) for u in U]
    t=0.
    while t<target-1e-14:
        used,_=S.step_ssprk3(U,t,target) if scheme=='ssprk3' else S.step_lsrk4(U,R,t,target)
        t+=used
    fields=np.stack([S.ifft(u).numpy() for u in U])
    return fields, S.diagnostics(U)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='artifacts/validation/convergence.json')
    a=p.parse_args()
    torch.set_num_threads(2)
    start=time.perf_counter()
    report=dict(source_sha256=source_hashes(),temporal={},spatial={},precision={})
    for scheme,order in [('ssprk3',3),('lsrk4',4)]:
        errors=[]
        for dt in (.1,.05,.025):
            fields,_=evolve(12,dt,scheme,shear=True)
            y=np.arange(12)*2*np.pi/12
            exact=np.sin(y)[None,:,None]*math.exp(-.2)
            errors.append(float(np.max(np.abs(fields[0]-exact))))
        rates=[math.log2(x/y) for x,y in zip(errors,errors[1:])]
        assert min(rates)>order-.12, (scheme,errors,rates)
        report['temporal'][scheme]=dict(N=12,nu=.5,target_t=.4,dt=[.1,.05,.025],max_errors=errors,observed_orders=rates)
    # Nested grids compare velocity on common collocation nodes of a TGV IC.
    fine,_=evolve(48,.002,'lsrk4',target=.4)
    previous=float('inf')
    for n in (12,24):
        fields,diag=evolve(n,.002,'lsrk4',target=.4)
        error=float(np.max(np.abs(fields-fine[:,::48//n,::48//n,::48//n])))
        assert error<previous
        previous=error
        report['spatial'][str(n)]=dict(max_velocity_error_vs_N48=error,E=diag[0],Z=diag[1],wmax=diag[2],tail=diag[4])
    assert report['spatial']['24']['max_velocity_error_vs_N48'] < report['spatial']['12']['max_velocity_error_vs_N48']/10
    a64,d64=evolve(24,.002,'ssprk3',target=.1)
    a32,d32=evolve(24,.002,'ssprk3',target=.1,dtype=torch.float32)
    report['precision']=dict(N=24,scheme='ssprk3',target_t=.1,max_velocity_fp32_fp64=float(np.max(np.abs(a32-a64))),
                             diagnostics_fp64=list(d64),diagnostics_fp32=list(d32))
    assert report['precision']['max_velocity_fp32_fp64']<1e-5
    report['limitations']='Short smooth TGV and exact shear only. Spatial reference N48 is finite; no tube/high-Re convergence certification.'
    report['wall_s']=time.perf_counter()-start
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
