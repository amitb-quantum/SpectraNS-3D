#!/usr/bin/env python3
"""CPU/CUDA N32 reference checks using fixed, predeclared cloud criteria.

Backend equivalence only. This script never provisions resources. The H100
launcher verifies the GPU model before invoking it; it can also be tested locally.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
import torch
from ns_fast_v3 import Solver, source_hashes


ROOT=Path(__file__).resolve().parents[1]


def trajectory(S,case,scheme,target=.02):
    U=getattr(S,'ic_'+case)()
    R=[torch.zeros_like(u) for u in U]
    t=0.
    while t<target-1e-14:
        dt,_=S.step_ssprk3(U,t,target) if scheme=='ssprk3' else S.step_lsrk4(U,R,t,target)
        t+=dt
    return U


def run(output):
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; reference validation was not performed')
    torch.set_num_threads(2)
    torch.manual_seed(0);np.random.seed(0)
    policy_path=ROOT/'configs/h100_acceptance.json'
    criteria=json.loads(policy_path.read_text())
    report=dict(source_sha256=source_hashes(),criteria_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                parameters=dict(N=32,nu=.0005,cfl=.2,max_dt=.002,target_t=.02,seed=0),
                python=sys.version,platform=platform.platform(),torch=torch.__version__,cuda=torch.version.cuda,
                gpu=torch.cuda.get_device_name(0),checks=[],status='running')
    started=time.perf_counter()
    try:
        for case in ('tgv','tubes'):
            for scheme in ('ssprk3','lsrk4'):
                for dtype,label in ((torch.float32,'float32'),(torch.float64,'float64')):
                    tol=criteria['reference'][label]
                    cpu=Solver(32,.0005,cfl=.2,max_dt=.002,device='cpu',dtype=dtype)
                    gpu=Solver(32,.0005,cfl=.2,max_dt=.002,device='cuda',dtype=dtype)
                    U=trajectory(cpu,case,scheme)
                    V=trajectory(gpu,case,scheme)
                    a=np.stack([cpu.ifft(u).numpy() for u in U])
                    b=np.stack([gpu.ifft(v).cpu().numpy() for v in V])
                    relative_l2=float(np.linalg.norm((a-b).ravel())/max(np.linalg.norm(a.ravel()),1e-30))
                    maximum=float(np.max(np.abs(a-b)))
                    if relative_l2>tol['velocity_relative_l2'] or maximum>tol['velocity_max_absolute']:
                        raise ValueError(f'CPU/CUDA velocity mismatch: {case} {scheme} {label}')
                    dc=cpu.diagnostics(U);dg=gpu.diagnostics(V)
                    scalar_errors={k:abs(x-y)/max(abs(x),abs(y),1e-14)
                                   for k,x,y in zip(('E','Z','wmax'),dc[:3],dg[:3])}
                    if max(scalar_errors.values())>tol['scalar_relative']:
                        raise ValueError('CPU/CUDA scalar mismatch')
                    rhs,_=gpu.rhs(*V)
                    dE=sum((gpu.ifft(v).double()*gpu.ifft(r).double()).mean().item() for v,r in zip(V,rhs))
                    eps=2*gpu.nu*dg[1]
                    residual=abs(dE+eps)
                    allowed=tol['energy_rhs_absolute_fraction_E']*dg[0]+tol['energy_rhs_relative_fraction_dissipation']*eps
                    if residual>allowed:
                        raise ValueError('instantaneous kinetic-energy identity failed')
                    shells=[gpu.spectrum_shells(V).cpu().numpy() for _ in range(3)]
                    spread=float(np.ptp(np.stack(shells),axis=0).max())
                    parseval=abs(float(shells[0].sum())-dg[0])/max(dg[0],1e-30)
                    if parseval>criteria['parseval_relative_tolerance']:
                        raise ValueError('Parseval failed')
                    if spread>criteria['reference']['repeat_shell_absolute_fraction_E']*dg[0]:
                        raise ValueError('repeated spectrum reductions disagree')
                    repeat=trajectory(gpu,case,scheme)
                    repeat_error=max((gpu.ifft(v)-gpu.ifft(w)).abs().max().item() for v,w in zip(V,repeat))
                    if repeat_error>tol['velocity_max_absolute']:
                        raise ValueError('repeated trajectory differs beyond tolerance')
                    report['checks'].append(dict(case=case,scheme=scheme,dtype=label,
                        velocity_relative_l2=relative_l2,velocity_max_absolute=maximum,
                        scalar_relative_errors=scalar_errors,energy_rhs_residual=residual,
                        energy_rhs_allowed=allowed,parseval_relative=parseval,
                        repeat_shell_spread=spread,repeat_velocity_max_absolute=repeat_error))
        report['status']='passed'
    except Exception as e:
        report.update(status='failed',error=f'{type(e).__name__}: {e}')
    finally:
        report['wall_s']=time.perf_counter()-started
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as f:
            json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    print(f'CPU/CUDA reference status={report["status"]}; GPU={report["gpu"]}; checks={len(report["checks"])}')
    return 0 if report['status']=='passed' else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='artifacts/validation/h100_reference.json')
    raise SystemExit(run(p.parse_args().output))
