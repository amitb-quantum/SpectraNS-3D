#!/usr/bin/env python3
"""Bounded trajectory using the immutable audited v3 Solver."""
import argparse
from contextlib import contextmanager
import csv
import json
import math
from pathlib import Path
import shutil
import sys
import time
import torch
from ns_fast_v3 import Solver,source_hashes,memory_state
from cloud_policy import ROOT
from extension_state import write,save_checkpoint,load_checkpoint,Turnover,high_shell_share,diagnostic_failure,sha

def resolve_device(device):
    dev=torch.device(device)
    if dev.type=='cuda' and dev.index is None:dev=torch.device('cuda',torch.cuda.current_device())
    return dev

def advance_event_time(t,dt,end):
    """Snap only accumulated clock roundoff, never a physical-sized remainder."""
    advanced=t+dt
    if not all(math.isfinite(v) for v in (t,dt,end)) or dt<=0 or advanced<=t:
        raise FloatingPointError('nonadvancing timestep')
    tolerance=min(32*math.ulp(max(1.,abs(t),abs(end))),1e-9*dt)
    if advanced>end+tolerance:
        raise FloatingPointError('timestep overshoots diagnostic event')
    if abs(end-advanced)<=tolerance:
        return end,end-advanced
    return advanced,0.


class StageTimings:
    """Disjoint wall intervals; synchronize CUDA at stage boundaries, not each step."""
    def __init__(self,device):
        self.device=device
        self.started=time.monotonic()
        self.seconds={}
        self.calls={}

    def sync(self):
        if self.device.type=='cuda':torch.cuda.synchronize(self.device)

    @contextmanager
    def measure(self,name):
        self.sync()
        started=time.monotonic()
        try:
            yield
        finally:
            self.sync()
            self.seconds[name]=self.seconds.get(name,0.)+time.monotonic()-started
            self.calls[name]=self.calls.get(name,0)+1

    def record(self):
        elapsed=time.monotonic()-self.started
        return dict(process_wall_s=elapsed,seconds=self.seconds.copy(),calls=self.calls.copy(),
                    unattributed_wall_s=max(0.,elapsed-sum(self.seconds.values())),
                    convention='Disjoint synchronized wall stages; integration includes per-step CSV writes. '
                               'Unattributed includes event control, diagnostic CSV, manifest I/O and timer boundary waits.')

def simulate(out,N=512,nu=.0005,device='cuda',max_dt=.0005,target=3.,case='tubes',
             log_dt=.01,checkpoint_dt=.1,max_wall_seconds=2400.,restart=None,
             checkpoint=True,turnover=True,gate=None,kmin=128,event_callback=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    gate=gate or json.loads((ROOT/'configs/h100_acceptance.json').read_text())
    dev=resolve_device(device)
    timing=StageTimings(dev)
    with timing.measure('solver_setup'):
        if dev.type=='cuda':
            torch.cuda.set_device(dev);torch.cuda.reset_peak_memory_stats(dev)
        S=Solver(N,nu,.2,max_dt,dev,torch.float64);S.spectrum_slab=4
    start=time.monotonic()
    with timing.measure('initial_condition_or_restart'):
        U,m=load_checkpoint(restart,S,case) if restart else (S.ic_tubes() if case=='tubes' else S.ic_tgv(),{})
        R=[torch.zeros_like(u) for u in U]
    snap_count=0;snap_max=0.;snap_signed_total=0.
    t=float(m.get('t',0));step=int(m.get('step',0));initial_step=step
    bkm=float(m.get('bkm',0));E0=m.get('E0');prev=None;dt=0.;step_stats=[]
    if target<=t:raise ValueError('target must exceed restart time')
    next_index=round(t/log_dt)+1
    history=[];regular=[];last_accepted=None;tracker=Turnover()
    manifest=dict(status='running',start_t=t,t=t,steps=step,initial_step=step,
        source_sha256=source_hashes(),driver_sha256=sha(__file__),
        parameters=dict(N=N,nu=nu,device=str(dev),case=case,scheme='lsrk4',fp64=True,
                        cfl=.2,max_dt=max_dt,target_t=target,log_dt=log_dt,checkpoint_dt=checkpoint_dt,
                        checkpoint_enabled=checkpoint,turnover_enabled=turnover,high_shell_min_k=kmin),
        restart=None if restart is None else dict(path=str(restart),metadata=m,metadata_sha256=sha(Path(restart)/'checkpoint.json')),
        torch=torch.__version__,cuda=torch.version.cuda,numpy=__import__('numpy').__version__,
        python=sys.version,physical_conventions=dict(domain=2*math.pi,dealias='strict spherical |k|<N/3',
        initial_tubes=dict(gamma=5.,a=.25,sep=.6,pert=.35)),last_accepted=None)
    headers=['step','t','dt','E','Z','eps','dEdt_fd','budget_resid_rel','wmax','bkm','tail_ratio','div_max','wall_s','peak_mem_GB']
    def checkpoint_at(kind):
        with timing.measure('checkpoint_write_hash_prune'):
            path=out/'checkpoints'/f'{kind}_t{t:.8f}'
            data=save_checkpoint(path,U,S,case,t,step,bkm,E0)
            entry=dict(path=path.relative_to(out).as_posix(),kind=kind,t=t,retained=True,
                       metadata_sha256=sha(path/'checkpoint.json'),files=data['files'])
            archive=out/'checkpoint_metadata';archive.mkdir(exist_ok=True)
            (archive/(path.name+'.json')).write_bytes((path/'checkpoint.json').read_bytes())
            history.append(entry)
            if kind=='regular':
                regular.append(entry)
                while len(regular)>2:
                    old=regular.pop(0);shutil.rmtree(out/old['path']);old['retained']=False
            write(out/'checkpoint_history.json',history)
            return entry
    try:
        with (out/'diagnostics.csv').open('x',newline='',buffering=1) as f, (out/'spectra.csv').open('x',newline='',buffering=1) as sf, (out/'enstrophy.csv').open('x',newline='',buffering=1) as bf, (out/'steps.csv').open('x',newline='',buffering=1) as tf:
            W=csv.DictWriter(f,fieldnames=headers);W.writeheader()
            SW=csv.writer(sf);SW.writerow(['t','shell_k','E_shell_mean_density'])
            BH=['t','production','grad_omega_sq','viscous_loss','net_production','dZdt_rhs','residual','loss_share_low','loss_share_center','loss_share_high','energy_share']
            BW=csv.DictWriter(bf,fieldnames=BH);BW.writeheader()
            TW=csv.writer(tf);TW.writerow(['step','t_start','dt','umax','cap_dt','cfl_dt','viscous_dt','limiter','wall_s'])
            while True:
                with timing.measure('scalar_diagnostics_and_tail'):
                    E,Z,wm,div,tail=S.diagnostics(U)
                if E0 is None:E0=E
                with timing.measure('enstrophy_budget'):
                    budget=S.enstrophy_budget(U)
                with timing.measure('full_spectrum'):
                    bins=S.spectrum_shells(U).cpu().tolist()
                net=budget['production']-nu*budget['grad_omega_sq']
                dEdt=resid=''
                if prev:
                    interval=t-prev['t'];bkm+=.5*(prev['wmax']+wm)*interval
                    dEdt=(E-prev['E'])/interval
                    eps_mid=nu*(Z+prev['Z']);resid=(dEdt+eps_mid)/eps_mid if eps_mid>0 else 0.
                mem=memory_state(dev)
                row=dict(zip(headers,[step,t,dt,E,Z,2*nu*Z,dEdt,resid,wm,bkm,tail,div,time.monotonic()-start,mem.get('peak_allocated_GB',0)]))
                W.writerow(row);SW.writerows((t,k,e) for k,e in enumerate(bins))
                BW.writerow(dict(t=t,**budget,viscous_loss=nu*budget['grad_omega_sq'],net_production=net,
                                  **high_shell_share(bins,nu,budget['grad_omega_sq'],kmin)))
                if event_callback:
                    with timing.measure('fourier_peak_refinement'):
                        event_callback(S,U,t,row,budget,bins)
                mem=memory_state(dev)
                failure=diagnostic_failure(row,budget,bins,prev,E0,nu,gate)
                if max(mem.get('peak_allocated_GB',0),mem.get('peak_reserved_GB',0))>.8*mem.get('total_GB',float('inf')):
                    failure='allocator_memory'
                if failure:
                    manifest.update(status='gate_trip',stop_reason=failure,failing_sample=row)
                    print('GATE_TRIP '+failure+' t='+str(t),flush=True);break
                last_accepted=row
                reason=tracker.observe(t,Z,net) if turnover else None
                manifest.update(t=t,steps=step,last_accepted=row,turnover=tracker.crossing)
                if checkpoint and t>0 and abs(t/checkpoint_dt-round(t/checkpoint_dt))<1e-9:checkpoint_at('regular')
                write(out/'progress.json',manifest)
                print(f'EVENT t={t:.6f} Z={Z:.9g} net={net:.9g} tail={tail:.5g}',flush=True)
                if reason or t>=target-1e-12 or time.monotonic()-start>=max_wall_seconds:
                    manifest.update(status='bounded_complete',stop_reason=reason or ('max_simulated_time' if t>=target-1e-12 else 'compute_wall_cap'));break
                prev=row
                end=min(target,next_index*log_dt)
                if end<=t+1e-14:
                    next_index+=1;end=min(target,next_index*log_dt)
                with timing.measure('integration'):
                    while t<end:
                        if time.monotonic()-start>=max_wall_seconds:
                            # End at next diagnostic so instantaneous budgets are preserved.
                            end=min(end,t+max_dt)
                        t0=t
                        dt,umax=S.step_lsrk4(U,R,t,end)
                        if not math.isfinite(dt) or dt<=0 or t+dt<=t:raise FloatingPointError('nonadvancing timestep')
                        cfl_dt=S.cfl*S.dx/max(umax,1e-6)
                        viscous_dt=.25*S.dx**2/nu if nu>0 else float('inf')
                        limiter='event' if end-t0<min(max_dt,cfl_dt,viscous_dt)*(1-1e-10) else ('viscous' if viscous_dt<min(max_dt,cfl_dt) else 'cfl' if cfl_dt<max_dt else 'cap')
                        t,snap=advance_event_time(t,dt,end);step+=1
                        if snap:
                            snap_count+=1;snap_max=max(snap_max,abs(snap));snap_signed_total+=snap
                        TW.writerow([step,t0,dt,umax,max_dt,cfl_dt,viscous_dt,limiter,time.monotonic()-start]);step_stats.append((dt,limiter))
                next_index+=1
        if checkpoint:manifest['terminal_checkpoint']=checkpoint_at('terminal')
    except Exception as exc:
        manifest.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        print(manifest['error'],file=sys.stderr,flush=True)
    finally:
        manifest.update(t=t,steps=step,wall_s=time.monotonic()-start,memory=memory_state(dev),
                        checkpoint_history=history,last_accepted=last_accepted,
                        achieved_steps=step-initial_step,
                        clock_snapping=dict(events=snap_count,max_abs_adjustment=snap_max,
                                            signed_total_adjustment=snap_signed_total,
                                            rule='min(32 ulps at event clock scale, 1e-9 of actual dt)'),
                        dt_statistics=dict(min=min([x[0] for x in step_stats],default=0),
                                           max=max([x[0] for x in step_stats],default=0),
                                           cfl_limited_steps=sum(x[1]=='cfl' for x in step_stats),
                                           event_limited_steps=sum(x[1]=='event' for x in step_stats)))
        profile=timing.record()
        write(out/'timing.json',profile)
        manifest['timing']=profile
        write(out/'run.json',manifest)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True);p.add_argument('--N',type=int,default=512)
    p.add_argument('--device',default='cuda');p.add_argument('--max-dt',type=float,default=.0005)
    p.add_argument('--target-t',type=float,default=3);p.add_argument('--max-wall-seconds',type=float,default=2400)
    p.add_argument('--restart');p.add_argument('--no-checkpoints',action='store_true');p.add_argument('--no-turnover',action='store_true')
    a=p.parse_args()
    if a.N not in (16,32,512) or a.target_t>3 or a.max_dt not in (.0005,.00025) or a.max_wall_seconds<=0:
        p.error('fixed extension limits: N16/N32 tests or N512, target<=3, dt=.0005/.00025, positive wall cap')
    r=simulate(a.output,a.N,device=a.device,max_dt=a.max_dt,target=a.target_t,max_wall_seconds=a.max_wall_seconds,
               restart=a.restart,checkpoint=not a.no_checkpoints,turnover=not a.no_turnover)
    raise SystemExit(0 if r['status'] in ('bounded_complete','gate_trip') else 2)
