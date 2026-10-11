#!/usr/bin/env python3
"""Small local CUDA validation and spectrum timing, never a cloud launcher."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch
from ns_fast_v3 import Solver, memory_state, source_hashes


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='artifacts/validation/gpu_checks.json')
    a=p.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit('CUDA unavailable; GPU validation was not performed')
    torch.set_num_threads(2)
    report=dict(torch=torch.__version__,cuda=torch.version.cuda,source_sha256=source_hashes(),checks=[])
    for n in (32,64):
        for dtype in (torch.float32,torch.float64):
            for scheme in ('ssprk3','lsrk4'):
                torch.cuda.reset_peak_memory_stats()
                cpu=Solver(n,.02,max_dt=.002,dtype=dtype)
                gpu=Solver(n,.02,max_dt=.002,device='cuda',dtype=dtype)
                U=cpu.ic_tgv()
                V=[u.cuda() for u in U]
                R=[torch.zeros_like(u) for u in U]
                Q=[torch.zeros_like(v) for v in V]
                for step in range(10):
                    t=step*.002
                    if scheme=='ssprk3':
                        cpu.step_ssprk3(U,t,.02);gpu.step_ssprk3(V,t,.02)
                    else:
                        cpu.step_lsrk4(U,R,t,.02);gpu.step_lsrk4(V,Q,t,.02)
                diff=max((cpu.ifft(u)-gpu.ifft(v).cpu()).abs().max().item() for u,v in zip(U,V))
                assert diff < (1e-5 if dtype==torch.float32 else 1e-12)
                expected=cpu.spectrum_shells(U).numpy()
                energy=gpu.diagnostics(V)[0]
                gpu.spectrum_shells(V)  # warm up
                torch.cuda.synchronize()
                started=time.perf_counter()
                repeats=[gpu.spectrum_shells(V).cpu().numpy() for _ in range(5)]
                torch.cuda.synchronize()
                ms=(time.perf_counter()-started)*1000/5
                parseval=abs(float(repeats[0].sum())-energy)/max(energy,1e-30)
                assert parseval < (2e-6 if dtype==torch.float32 else 2e-12)
                spectrum_error=float(np.max(np.abs(repeats[0]-expected)))
                assert spectrum_error < (1e-6 if dtype==torch.float32 else 2e-12)
                spread=float(np.max(np.ptp(np.stack(repeats),axis=0)))
                assert spread < 2e-12
                report['checks'].append(dict(N=n,dtype=str(dtype),scheme=scheme,
                    max_velocity_cpu_gpu=diff,parseval_relative_error=parseval,
                    max_shell_cpu_gpu_error=spectrum_error,max_shell_repeat_spread=spread,
                    spectrum_mean_ms=ms,memory=memory_state(torch.device('cuda'))))
                del cpu,gpu,U,V,R,Q
    report['status']='passed'
    report['limitations']='N32/N64 and 10 steps only on the named local GPU. No H100/high-grid validation. CUDA reductions compared in tolerance.'
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(f'{len(report["checks"])} local GPU comparisons passed on {report["checks"][0]["memory"]["gpu"]}')


if __name__=='__main__':
    main()
