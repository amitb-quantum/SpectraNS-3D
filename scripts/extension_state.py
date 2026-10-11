"""Portable, hashed, full Fourier-state restart records; no pickle."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import torch
from ns_fast_v3 import source_hashes

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def write(path,data):
    path=Path(path); tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');tmp.replace(path)

def physics(solver,case):
    return dict(N=solver.N,nu=solver.nu,case=case,scheme='lsrk4',fp64=solver.dt_==torch.float64,
                domain=2*math.pi,dealias='strict spherical |k|<N/3',
                legacy_tube_parameters=dict(gamma=5.,a=.25,sep=.6,pert=.35))

def save_checkpoint(path,U,solver,case,t,step,bkm,E0):
    path=Path(path);path.mkdir(parents=True,exist_ok=False)
    files={}
    for i,u in enumerate(U):
        target=path/f'U{i}.npy';temporary=path/f'U{i}.npy.tmp'
        with temporary.open('xb') as f:
            np.save(f,u.detach().cpu().numpy(),allow_pickle=False)
        temporary.replace(target);files[target.name]=sha(target)
    metadata=dict(schema_version=1,physics=physics(solver,case),t=t,step=step,bkm=bkm,E0=E0,
                  source_sha256=source_hashes(),checkpoint_driver_sha256=sha(__file__),
                  torch=torch.__version__,cuda=torch.version.cuda,numpy=np.__version__,
                  axes='component,kx,ky,kz_rfft',normalization='unnormalized torch rfftn coefficients',
                  residual_restart='LSRK4 first stage has coefficient zero; residual can be reset',
                  files=files)
    write(path/'checkpoint.json',metadata)
    return metadata

def load_checkpoint(path,solver,case):
    path=Path(path);m=json.loads((path/'checkpoint.json').read_text())
    if m.get('schema_version')!=1 or m.get('physics')!=physics(solver,case):
        raise ValueError('checkpoint physics/grid/precision mismatch; spatial transfer is not implemented')
    if m.get('source_sha256')!=source_hashes() or m.get('checkpoint_driver_sha256')!=sha(__file__):
        raise ValueError('checkpoint source hash mismatch')
    if m.get('torch')!=torch.__version__ or m.get('cuda')!=torch.version.cuda:
        raise ValueError('checkpoint runtime mismatch')
    if not all(math.isfinite(m.get(k,float('nan'))) and m[k]>=0 for k in ('t','step','bkm','E0')):
        raise ValueError('invalid restart scalars')
    if m['E0']<=0 or type(m['step']) is not int: raise ValueError('invalid initial energy/step')
    if set(m.get('files',{}))!={'U0.npy','U1.npy','U2.npy'}: raise ValueError('incomplete checkpoint')
    U=[]
    dtype=np.complex128 if solver.dt_==torch.float64 else np.complex64
    for i in range(3):
        name=f'U{i}.npy'
        if sha(path/name)!=m['files'][name]: raise ValueError('checkpoint checksum mismatch')
        a=np.load(path/name,allow_pickle=False,mmap_mode='r')
        if a.shape!=(solver.N,solver.N,solver.N//2+1) or a.dtype!=dtype:
            raise ValueError('checkpoint field shape/dtype mismatch')
        u=torch.from_numpy(np.array(a,copy=True)).to(solver.dev)
        if not torch.isfinite(u).all().item(): raise ValueError('nonfinite checkpoint')
        U.append(u)
    return U,m

def high_shell_share(bins,nu,grad_omega_sq,kmin):
    denom=nu*grad_omega_sq
    moments=[sum(float(e)*max(k+offset,0)**4 for k,e in enumerate(bins) if k>=kmin)
             for offset in (-.5,0,.5)]
    values=[2*nu*m/denom if denom>0 else 0. for m in moments]
    return dict(loss_share_low=values[0],loss_share_center=values[1],loss_share_high=values[2],
                energy_share=sum(float(e) for k,e in enumerate(bins) if k>=kmin)/max(sum(bins),1e-300))

class Turnover:
    def __init__(self,decline=.01,margin=.1):
        self.decline=decline;self.margin=margin;self.previous=None;self.crossing=None;self.peak_Z=0.
    def observe(self,t,Z,net):
        self.peak_Z=max(self.peak_Z,Z)
        if self.crossing is None and self.previous is not None and self.previous[1]>0 and net<=0:
            self.crossing=dict(previous_t=self.previous[0],first_nonpositive_t=t,peak_Z=self.peak_Z)
        self.previous=t,net
        if self.crossing:
            if Z<=self.peak_Z*(1-self.decline):return 'turnover_decline'
            if t>=self.crossing['first_nonpositive_t']+self.margin-1e-12:return 'turnover_margin'
        return None

def diagnostic_failure(row,budget,bins,previous,E0,nu,gate,identity_tol=1e-8):
    if any(not math.isfinite(float(v)) for v in row.values() if v!=''):
        return 'nonfinite_diagnostic'
    if any(not math.isfinite(float(v)) for v in budget.values()): return 'nonfinite_enstrophy_budget'
    if any(not math.isfinite(e) or e<0 for e in bins):return 'nonfinite_spectrum'
    if row['tail_ratio']>gate['tail_ratio_max']:return 'tail_ratio'
    if row['div_max']>gate['divergence_absolute_max']:return 'divergence'
    if row['E']>E0*(1+gate['energy_initial_rise_fraction_E0']):return 'energy_initial_rise'
    if previous and row['E']>previous['E']+gate['energy_interval_rise_fraction_E0']*E0:return 'energy_interval_rise'
    if previous and abs(row['budget_resid_rel'])>gate['energy_fd_budget_relative_tolerance']:return 'energy_fd_budget'
    if abs(sum(bins)-row['E'])/max(row['E'],1e-300)>gate['parseval_relative_tolerance']:return 'parseval'
    scale=max(abs(budget['production']),abs(budget['dZdt_rhs']),nu*abs(budget['grad_omega_sq']),1e-300)
    if abs(budget['residual'])/scale>identity_tol:return 'enstrophy_identity'
    return None
