#!/usr/bin/env python3
"""Plan-only by default. Runs N128 then N256 on an ALREADY AUTHORIZED H100.

No provisioning or termination API is called. A separate operator must track
idle charges, collect artifacts, terminate the instance, and verify shutdown.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import threading

from ns_fast_v3 import source_hashes
from cloud_policy import validate_execution, verify_audited_sources, execution_fingerprint
from cloud_records import inventory, utc_now

ROOT = Path(__file__).resolve().parents[1]
CRITERIA_PATH = ROOT/'configs/h100_acceptance.json'


def criteria():
    return json.loads(CRITERIA_PATH.read_text())


def plan(out):
    commands=[]
    for n in (128,256):
        for case in ('tgv','tubes'):
            for scheme in ('ssprk3','lsrk4'):
                name=f'{case}_N{n}_{scheme}'
                commands.append([sys.executable,'-u','-m','ns_fast_v3','--device','cuda',
                    '--fp64',
                    '--case',case,'--N',str(n),'--nu','0.0005','--scheme',scheme,
                    '--target_t','.05','--max_dt','.002','--cfl','.2','--log_dt','.01',
                    '--csv',str(out/(name+'.csv')),'--spectrum_csv',str(out/(name+'_spectra.csv')),
                    '--spectrum_stride','1','--max_divergence','0.0001',
                    '--abort_on_tail','0.000001',
                    '--abort_on_energy_rise','0.0001',
                    '--abort_on_interval_energy_rise','0.00001',
                    '--budget_csv',str(out/(name+'_enstrophy.csv'))])
    return commands


def compare(out,n):
    policy=criteria()
    if n not in policy['allowed_smoke_grids']:
        raise ValueError('cloud smoke supports only N128/N256')
    metrics=[]
    for case in ('tgv','tubes'):
        tables=[]
        for scheme in ('ssprk3','lsrk4'):
            name=f'{case}_N{n}_{scheme}'
            report=json.loads((out/(name+'.csv.json')).read_text())
            if report['status']!='completed' or report['t']!=.05:
                raise ValueError('incomplete smoke run')
            if report['source_sha256']!=verify_audited_sources():
                raise ValueError('run source hashes differ from audited core')
            params=report['parameters']
            expected=dict(N=n,case=case,scheme=scheme,nu=.0005,target_t=.05,max_dt=.002,
                          cfl=.2,log_dt=.01,fp64=policy['smoke_fp64'],spectrum_slab=4,spectrum_stride=1)
            if any(params.get(k)!=v for k,v in expected.items()):
                raise ValueError('run configuration differs from approved smoke matrix')
            mem=report['memory']
            peak=max(mem['peak_allocated_GB'],mem['peak_reserved_GB'])
            if not all(math.isfinite(mem[k]) and mem[k]>0 for k in ('peak_allocated_GB','peak_reserved_GB','total_GB')):
                raise ValueError('missing or nonfinite memory metrics')
            if peak>min(policy['smoke_peak_reserved_GB_max'],policy['memory_fraction_max']*mem['total_GB']):
                raise ValueError('smoke memory gate exceeded')
            with (out/(name+'.csv')).open() as f:
                rows=list(csv.DictReader(f))
            tables.append(rows)
            if [float(row['t']) for row in rows]!=[0.,.01,.02,.03,.04,.05]:
                raise ValueError('expected diagnostic output times are missing')
            E0=float(rows[0]['E']);previous_E=E0
            for i,row in enumerate(rows):
                for key in ('t','dt','E','Z','eps','wmax','bkm','tail_ratio','div_max','wall_s','peak_mem_GB'):
                    value=float(row[key])
                    if not math.isfinite(value) or value<0:
                        raise ValueError(f'nonfinite/negative scalar {key}')
                if E0<=0 or float(row['E'])>E0*(1+policy['energy_initial_rise_fraction_E0']):
                    raise ValueError('initial energy gate exceeded')
                if float(row['E'])>previous_E+policy['energy_interval_rise_fraction_E0']*E0:
                    raise ValueError('interval energy gate exceeded')
                previous_E=float(row['E'])
                if float(row['div_max'])>policy['divergence_absolute_max'] or float(row['tail_ratio'])>policy['tail_ratio_max']:
                    raise ValueError('divergence or spectral tail gate exceeded')
                if i:
                    residual=float(row['budget_resid_rel'])
                    if not math.isfinite(residual) or abs(residual)>policy['energy_fd_budget_relative_tolerance']:
                        raise ValueError('finite-difference energy budget gate exceeded')
            with (out/(name+'_spectra.csv')).open() as f:
                shells=list(csv.DictReader(f))
            sums={}; indices={}
            for row in shells:
                t=float(row['t']);v=float(row['E_shell_mean_density'])
                if not math.isfinite(v) or v<0:
                    raise ValueError('invalid shell energy')
                sums[t]=sums.get(t,0.)+v
                indices.setdefault(t,[]).append(int(row['shell_k']))
            expected_shells=list(range(int(math.sqrt(3)*(n//2)+.5)+1))
            if set(sums)!={float(r['t']) for r in rows} or any(ks!=expected_shells for ks in indices.values()):
                raise ValueError('full spectrum missing shells or matched times')
            for row in rows:
                energy=float(row['E'])
                if abs(sums[float(row['t'])]-energy)>policy['parseval_relative_tolerance']*max(energy,1e-30):
                    raise ValueError('Parseval check failed')
            with (out/(name+'_enstrophy.csv')).open() as f:
                budgets=list(csv.DictReader(f))
            if [float(r['t']) for r in budgets]!=[float(r['t']) for r in rows]:
                raise ValueError('enstrophy output times missing')
            if any(not math.isfinite(float(v)) for r in budgets for v in r.values()):
                raise ValueError('nonfinite enstrophy diagnostic')
        if len(tables[0])!=len(tables[1]):
            raise ValueError('sampling count mismatch')
        for left,right in zip(*tables):
            if float(left['t'])!=float(right['t']):
                raise ValueError('sampling time mismatch')
            for key in ('E','Z','wmax','bkm'):
                x,y=float(left[key]),float(right[key])
                error=abs(x-y)/max(abs(x),abs(y),1e-14)
                if not math.isfinite(error) or error>policy['scheme_scalar_relative_tolerance']:
                    raise ValueError(f'{case} N{n} {key}: scheme mismatch {error}')
                metrics.append(dict(case=case,N=n,t=float(left['t']),metric=key,relative_difference=error))
    return metrics


class GPUTrace:
    """Capture driver-level usage while child processes execute."""
    def __init__(self,path):
        self.path=path;self.stop=threading.Event();self.failure=None
        self.thread=threading.Thread(target=self.capture,daemon=True)

    def capture(self):
        query='index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,driver_version'
        try:
            with self.path.open('x') as f:
                f.write('utc,index,uuid,name,total_MiB,used_MiB,util_percent,power_W,driver\n')
                while not self.stop.is_set():
                    result=subprocess.run(['nvidia-smi','--query-gpu='+query,'--format=csv,noheader,nounits'],
                                          capture_output=True,text=True,check=True,timeout=10)
                    for row in result.stdout.splitlines():
                        f.write(utc_now()+','+row+'\n')
                    f.flush()
                    self.stop.wait(1)
        except Exception as e:
            self.failure=type(e).__name__

    def finish(self):
        self.stop.set();self.thread.join(timeout=12)
        if self.thread.is_alive() or self.failure:
            raise ValueError('driver memory monitoring failed')
        with self.path.open() as f:
            rows=list(csv.DictReader(f))
        if not rows:
            raise ValueError('driver trace is empty')
        worst=0.
        for row in rows:
            fraction=float(row['used_MiB'])/float(row['total_MiB'])
            if not math.isfinite(fraction):
                raise ValueError('driver memory trace nonfinite')
            worst=max(worst,fraction)
        if worst>criteria()['memory_fraction_max']:
            raise ValueError('driver-level memory headroom gate exceeded')
        return worst


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='artifacts/h100_smoke')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--approval-record',help='JSON with approved, approval_note, max_additional_usd, hourly_rate_usd')
    p.add_argument('--budget-ledger',default=str(ROOT/'configs/project_budget.json'))
    a=p.parse_args()
    out=Path(a.output).resolve()
    commands=plan(out)
    if not a.execute:
        print(json.dumps(dict(mode='PLAN ONLY',commands=commands,provisions_cloud=False,
                             source_sha256=verify_audited_sources(),acceptance=criteria(),
                             execution_sha256=execution_fingerprint(),
                             prerequisite='Reconciled $30 ledger, explicit approval, and external termination guard required'),indent=2))
        return 0
    if not a.approval_record:
        p.error('--execute requires an explicit user approval record')
    record=json.loads(Path(a.approval_record).read_text())
    try:
        spending=validate_execution(a.budget_ledger,record)
    except (ValueError,KeyError,TypeError) as e:
        p.error(str(e))
    import torch
    if not torch.cuda.is_available() or 'H100' not in torch.cuda.get_device_name(0):
        p.error('this launcher requires an H100; use verify_gpu.py for small local checks')
    out.mkdir(parents=True,exist_ok=False)
    root=ROOT
    deadline=time.monotonic()+spending['compute_timeout_seconds']
    report=dict(status='running',source_sha256=source_hashes(),approval=record,budget=spending,
                started_at_utc=utc_now(),comparisons=[],commands=commands,
                acceptance_sha256=hashlib.sha256(CRITERIA_PATH.read_bytes()).hexdigest(),
                lifecycle_status='termination_pending')
    (out/'approval.json').write_text(json.dumps(record,indent=2)+'\n')
    (out/'budget_ledger.json').write_bytes(Path(a.budget_ledger).read_bytes())
    (out/'acceptance.json').write_bytes(CRITERIA_PATH.read_bytes())
    termination=dict(instance_id=record['instance_id'],status='termination_pending',
                     provider_started_at_utc=record['provider_started_at_utc'],
                     deadline_utc=record['termination_deadline_utc'],compute_ended_at_utc=None,
                     guard_evidence=record['termination_guard_evidence'])
    (out/'termination.json').write_text(json.dumps(termination,indent=2)+'\n')
    source_inventory={}
    for folder in ('src','scripts','tests','configs'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file() and path.suffix in ('.py','.json') and '__pycache__' not in path.parts:
                source_inventory[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'source_bundle.json').write_text(json.dumps(source_inventory,indent=2)+'\n')
    trace=GPUTrace(out/'nvidia_smi_trace.csv')
    def run(command,log):
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise TimeoutError('authorized active compute deadline reached')
        with log.open('x') as f:
            subprocess.run(command,cwd=root,stdout=f,stderr=subprocess.STDOUT,
                           timeout=remaining,check=True)
    try:
        with (out/'nvidia_smi.txt').open('x') as f:
            subprocess.run(['nvidia-smi','-q'],stdout=f,check=True,timeout=15)
        trace.thread.start()
        run([sys.executable,'-m','pytest','-q','tests'],out/'tests.log')
        run([sys.executable,'scripts/verify_h100_reference.py','--output',str(out/'cpu_h100_reference.json')],
            out/'cpu_h100_reference.log')
        for index,cmd in enumerate(commands):
            run(cmd,out/f'run_{index}.log')
            if index in (3,7):
                report['comparisons'].extend(compare(out,128 if index==3 else 256))
        report['driver_peak_used_fraction']=trace.finish()
        report['status']='passed'
    except Exception as e:
        report.update(status='failed',error=f'{type(e).__name__}: {e}')
    finally:
        if trace.thread.is_alive():
            trace.stop.set();trace.thread.join(timeout=12)
        report['ended_at_utc']=utc_now()
        termination['compute_ended_at_utc']=report['ended_at_utc']
        termination['compute_status']=report['status']
        (out/'termination.json').write_text(json.dumps(termination,indent=2)+'\n')
        report['cleanup_status']='Operator must collect artifacts, terminate instance, and verify externally'
        (out/'campaign.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        inventory(out)
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 2


if __name__=='__main__':
    sys.exit(main())
