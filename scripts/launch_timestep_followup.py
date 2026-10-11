#!/usr/bin/env python3
"""Bounded N512 timestep comparison on an already authorized H100; no provider calls."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from cloud_policy import ROOT, verify_audited_sources
from cloud_records import inventory, utc_now
from followup_policy import PLAN_PATH, plan, fingerprint, validate_execution, validate_prerequisite
from launch_h100_smoke import criteria, GPUTrace

def write(path, data):
    path = Path(path)
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    tmp.replace(path)

def command(out, name, n, dt, target):
    cfg = plan()
    return [sys.executable, '-u', '-m', 'ns_fast_v3', '--device', 'cuda', '--fp64',
        '--case', cfg['case'], '--N', str(n), '--nu', str(cfg['nu']), '--scheme', cfg['scheme'],
        '--target_t', str(target), '--max_dt', str(dt), '--cfl', str(cfg['cfl']),
        '--log_dt', str(cfg['log_dt']), '--csv', str(out/(name+'.csv')),
        '--spectrum_csv', str(out/(name+'_spectra.csv')), '--spectrum_stride', '1',
        '--spectrum_slab', '4', '--budget_csv', str(out/(name+'_enstrophy.csv')),
        '--max_divergence', str(criteria()['divergence_absolute_max']),
        '--abort_on_tail', str(criteria()['tail_ratio_max']),
        '--abort_on_energy_rise', str(criteria()['energy_initial_rise_fraction_E0']),
        '--abort_on_interval_energy_rise', str(criteria()['energy_interval_rise_fraction_E0'])]

def read_csv(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))

def check_run(out, name, n, dt, target):
    cfg, gate = plan(), criteria()
    manifest = json.loads((out/(name+'.csv.json')).read_text())
    if (manifest.get('status') != 'completed' or manifest.get('t') != target
            or manifest.get('source_sha256') != verify_audited_sources()
            or manifest.get('steps',0) < 5):
        raise ValueError('incomplete or unaudited run: '+name)
    expected = dict(N=n, case='tubes', nu=cfg['nu'], scheme='lsrk4', fp64=True,
                    cfl=.2, max_dt=dt, target_t=target, log_dt=.01,
                    spectrum_slab=4, spectrum_stride=1, snapshot_times='')
    if any(manifest['parameters'].get(key) != value for key,value in expected.items()):
        raise ValueError('run configuration differs from fixed plan: '+name)
    memory = manifest['memory']
    if any(not math.isfinite(memory.get(key,0)) or memory.get(key,0)<=0
           for key in ('peak_allocated_GB','peak_reserved_GB','total_GB')):
        raise ValueError('missing memory metrics')
    fraction = max(memory['peak_allocated_GB'],memory['peak_reserved_GB'])/memory['total_GB']
    if fraction > cfg['memory_fraction_max']:
        raise ValueError('allocator memory headroom exceeded')
    rows = read_csv(out/(name+'.csv'))
    times = [float(row['t']) for row in rows]
    expected_times = [i*.01 for i in range(round(target/.01)+1)]
    if len(times)!=len(expected_times) or any(abs(x-y)>1e-12 for x,y in zip(times,expected_times)):
        raise ValueError('missing or duplicate diagnostic times')
    E0 = float(rows[0]['E'])
    if not E0 > 0:
        raise ValueError('nonpositive initial kinetic energy')
    previous = E0
    maxima = dict(divergence=0., tail_ratio=0., energy_budget_relative=0.,
                  parseval_relative=0., enstrophy_identity_relative=0.)
    for i,row in enumerate(rows):
        for key in ('t','dt','E','Z','eps','wmax','bkm','tail_ratio','div_max','wall_s','peak_mem_GB'):
            if not math.isfinite(float(row[key])) or float(row[key])<0:
                raise ValueError('nonfinite/negative diagnostic '+key)
        energy = float(row['E'])
        if energy>E0*(1+gate['energy_initial_rise_fraction_E0']) or energy>previous+gate['energy_interval_rise_fraction_E0']*E0:
            raise ValueError('energy rise gate exceeded')
        previous = energy
        if abs(float(row['eps'])-2*cfg['nu']*float(row['Z']))>1e-12*max(float(row['eps']),1e-30):
            raise ValueError('dissipation definition mismatch')
        maxima['divergence'] = max(maxima['divergence'],float(row['div_max']))
        maxima['tail_ratio'] = max(maxima['tail_ratio'],float(row['tail_ratio']))
        if i:
            residual = abs(float(row['budget_resid_rel']))
            if not math.isfinite(residual):
                raise ValueError('nonfinite energy residual')
            maxima['energy_budget_relative'] = max(maxima['energy_budget_relative'],residual)
    for metric,threshold in [('divergence',gate['divergence_absolute_max']),
                              ('tail_ratio',gate['tail_ratio_max']),
                              ('energy_budget_relative',gate['energy_fd_budget_relative_tolerance'])]:
        if maxima[metric]>threshold:
            raise ValueError(metric+' gate exceeded')
    spectra = {}
    for row in read_csv(out/(name+'_spectra.csv')):
        t, k, value = float(row['t']),int(row['shell_k']),float(row['E_shell_mean_density'])
        if not math.isfinite(value) or value<0 or k in spectra.setdefault(t,{}):
            raise ValueError('invalid or duplicate shell')
        spectra[t][k] = value
    shells = set(range(int(math.sqrt(3)*(n//2)+.5)+1))
    if set(spectra)!=set(times) or any(set(s)!=shells for s in spectra.values()):
        raise ValueError('full spectrum incomplete')
    for row in rows:
        error = abs(sum(spectra[float(row['t'])].values())-float(row['E']))/max(float(row['E']),1e-30)
        maxima['parseval_relative'] = max(maxima['parseval_relative'],error)
    if maxima['parseval_relative']>gate['parseval_relative_tolerance']:
        raise ValueError('Parseval gate exceeded')
    budgets = read_csv(out/(name+'_enstrophy.csv'))
    if [float(r['t']) for r in budgets]!=times:
        raise ValueError('enstrophy diagnostic times differ')
    for row in budgets:
        if any(not math.isfinite(float(value)) for value in row.values()):
            raise ValueError('nonfinite enstrophy budget')
        scale = max(abs(float(row['production'])),abs(float(row['dZdt_rhs'])),
                    cfg['nu']*abs(float(row['grad_omega_sq'])),1e-30)
        error = abs(float(row['residual']))/scale
        maxima['enstrophy_identity_relative'] = max(maxima['enstrophy_identity_relative'],error)
    if maxima['enstrophy_identity_relative']>cfg['enstrophy_identity_relative_tolerance']:
        raise ValueError('enstrophy identity gate exceeded')
    return dict(name=name,N=n,max_dt=dt,target_t=target,manifest=manifest,rows=rows,
                spectra=spectra,maxima=maxima,peak_allocator_fraction=fraction)

def compare_runs(left, right, spatial=False):
    cfg = plan()
    if len(left['rows'])!=len(right['rows']):
        raise ValueError('comparison sampling count differs')
    metrics = []
    for a,b in zip(left['rows'],right['rows']):
        if abs(float(a['t'])-float(b['t']))>1e-12:
            raise ValueError('comparison times differ')
        for key in (('E','Z','wmax') if spatial else ('E','Z','wmax','bkm')):
            error = abs(float(a[key])-float(b[key]))/max(abs(float(a[key])),abs(float(b[key])),1e-14)
            limit = (cfg['preflight_grid_wmax_relative_tolerance'] if spatial and key=='wmax'
                     else cfg['preflight_grid_energy_enstrophy_relative_tolerance'] if spatial
                     else cfg['timestep_scalar_relative_tolerance'])
            if not math.isfinite(error) or error>limit:
                raise ValueError(f'{key} {"early grid" if spatial else "timestep"} comparison failed: {error}')
            metrics.append(dict(t=float(a['t']),metric=key,relative_difference=error,tolerance=limit))
        if not spatial:
            sa,sb = left['spectra'][float(a['t'])],right['spectra'][float(b['t'])]
            if set(sa)!=set(sb):
                raise ValueError('spectrum shells differ')
            error = sum(abs(sa[k]-sb[k]) for k in sa)/max(float(a['E']),float(b['E']),1e-30)
            if error>cfg['timestep_spectrum_L1_fraction_E_tolerance']:
                raise ValueError('full spectrum timestep comparison failed')
            metrics.append(dict(t=float(a['t']),metric='spectrum_L1_fraction_E',
                                relative_difference=error,tolerance=cfg['timestep_spectrum_L1_fraction_E_tolerance']))
    if not spatial:
        ratio = right['manifest']['steps']/left['manifest']['steps']
        if ratio<cfg['minimum_effective_step_ratio']:
            raise ValueError('CFL produced insufficient effective timestep separation')
    return metrics

class LiveGPUTrace(GPUTrace):
    def capture(self):
        query = 'index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,driver_version'
        try:
            with self.path.open('x') as stream:
                stream.write('utc,index,uuid,name,total_MiB,used_MiB,util_percent,power_W,driver\n')
                while not self.stop.is_set():
                    result = subprocess.run(['nvidia-smi','--query-gpu='+query,'--format=csv,noheader,nounits'],
                                            capture_output=True,text=True,check=True,timeout=10)
                    for row in result.stdout.splitlines():
                        columns = [item.strip() for item in row.split(',')]
                        fraction = float(columns[4])/float(columns[3])
                        stream.write(utc_now()+','+row+'\n');stream.flush()
                        if not math.isfinite(fraction) or fraction>plan()['memory_fraction_max']:
                            raise ValueError('live driver memory headroom exceeded')
                    self.stop.wait(1)
        except Exception as exc:
            self.failure = f'{type(exc).__name__}: {exc}'

def run_checked(cmd, log, deadline, trace):
    with log.open('x') as stream:
        child = subprocess.Popen(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while child.poll() is None:
                if trace.failure:
                    raise ValueError(trace.failure)
                if time.monotonic()>=deadline:
                    raise TimeoutError('authorized compute deadline reached')
                time.sleep(.25)
            if child.returncode:
                raise subprocess.CalledProcessError(child.returncode,cmd)
            if trace.failure:
                raise ValueError(trace.failure)
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL);child.wait()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output',required=True)
    parser.add_argument('--approval-record')
    parser.add_argument('--budget-ledger',default=str(ROOT/'configs/project_budget.json'))
    args = parser.parse_args()
    out = Path(args.output).resolve()
    cfg = plan()
    definitions = [('preflight_N256_fine',256,.00025,.01),
                   ('preflight_N512_coarse',512,.0005,.01),
                   ('preflight_N512_fine',512,.00025,.01),
                   ('tubes_N512_coarse',512,.0005,1.),
                   ('tubes_N512_fine',512,.00025,1.)]
    commands = [command(out,*entry) for entry in definitions]
    if not args.execute:
        print(json.dumps(dict(mode='PLAN ONLY',plan=cfg,commands=commands,
                              execution_sha256=fingerprint(),prerequisite=validate_prerequisite()),indent=2))
        return 0
    if not args.approval_record:
        parser.error('execution requires the recorded authorization')
    approval = json.loads(Path(args.approval_record).read_text())
    spending = validate_execution(args.budget_ledger,approval)
    import torch
    if not torch.cuda.is_available() or 'H100' not in torch.cuda.get_device_name(0):
        parser.error('this follow-up requires an H100')
    out.mkdir(parents=True,exist_ok=False)
    deadline = time.monotonic()+spending['compute_timeout_seconds']
    report = dict(status='running',started_at_utc=utc_now(),source_sha256=verify_audited_sources(),
                  execution_sha256=fingerprint(),approval=approval,budget=spending,
                  plan=cfg,commands=commands,completed_checks=[],phase='initializing')
    termination = dict(instance_id=approval['instance_id'],status='termination_pending',
                       provider_started_at_utc=approval['provider_started_at_utc'],
                       deadline_utc=approval['termination_deadline_utc'],compute_ended_at_utc=None,
                       guard_evidence=approval['termination_guard_evidence'])
    for name,path in [('budget_ledger.json',Path(args.budget_ledger)),('plan.json',PLAN_PATH),
                      ('acceptance.json',ROOT/'configs/h100_acceptance.json'),
                      ('prerequisite.json',ROOT/'configs/followup_smoke_evidence.json')]:
        (out/name).write_bytes(path.read_bytes())
    write(out/'approval.json',approval);write(out/'source_bundle.json',fingerprint())
    write(out/'termination.json',termination)
    trace = LiveGPUTrace(out/'nvidia_smi_trace.csv')
    def phase(name):
        report['phase'] = name
        write(out/'campaign_progress.json',report)
        print('PHASE '+name,flush=True)
    try:
        with (out/'nvidia_smi.txt').open('x') as stream:
            subprocess.run(['nvidia-smi','-q'],stdout=stream,check=True,timeout=15)
        trace.thread.start()
        phase('tests')
        run_checked([sys.executable,'-m','pytest','-q','tests'],out/'tests.log',deadline,trace)
        phase('cpu_h100_reference')
        run_checked([sys.executable,'scripts/verify_h100_reference.py','--output',str(out/'cpu_h100_reference.json')],
                    out/'cpu_h100_reference.log',deadline,trace)
        checked = []
        for index in range(3):
            name,n,dt,target = definitions[index]
            phase(name)
            run_checked(commands[index],out/(name+'.log'),deadline,trace)
            checked.append(check_run(out,name,n,dt,target))
            report['completed_checks'].append(dict(name=name,maxima=checked[-1]['maxima'],
                                                  memory=checked[-1]['manifest']['memory']))
        report['early_grid_comparison'] = compare_runs(checked[0],checked[2],spatial=True)
        report['early_timestep_comparison'] = compare_runs(checked[1],checked[2])
        fine = checked[2]
        elapsed = float(fine['rows'][-1]['wall_s'])-float(fine['rows'][0]['wall_s'])
        seconds_per_step = elapsed/fine['manifest']['steps']
        # Includes measured final diagnostics; this deliberately overestimates their frequency.
        minimum_steps = math.ceil(1/.0005)+math.ceil(1/.00025)+202
        forecast = seconds_per_step*minimum_steps*cfg['runtime_safety_factor']+300
        remaining = deadline-time.monotonic()
        report['runtime_preflight'] = dict(seconds_per_step_upper=seconds_per_step,
            forecast_compute_seconds=forecast,remaining_compute_seconds=remaining,
            early_memory_measured=True,early_grid_only=True)
        write(out/'runtime_preflight.json',report['runtime_preflight'])
        if forecast>remaining:
            raise ValueError('measured runtime forecast exceeds remaining authorized lifetime')
        phase('preflight_passed')
        completed = []
        for index in (3,4):
            name,n,dt,target = definitions[index]
            phase(name)
            run_checked(commands[index],out/(name+'.log'),deadline,trace)
            completed.append(check_run(out,name,n,dt,target))
            report['completed_checks'].append(dict(name=name,maxima=completed[-1]['maxima'],
                memory=completed[-1]['manifest']['memory'],steps=completed[-1]['manifest']['steps'],
                wall_s=completed[-1]['manifest']['wall_s']))
        report['timestep_comparison'] = compare_runs(*completed)
        report['driver_peak_used_fraction'] = trace.finish()
        report['status'] = 'passed'
        report['scientific_scope'] = 'N512 timestep agreement; long-time spatial convergence remains unverified'
    except Exception as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    finally:
        if trace.thread.is_alive():
            trace.stop.set();trace.thread.join(timeout=12)
        report['ended_at_utc'] = utc_now()
        termination.update(compute_ended_at_utc=report['ended_at_utc'],compute_status=report['status'])
        write(out/'termination.json',termination)
        write(out/'campaign.json',report)
        write(out/'campaign_progress.json',report)
        inventory(out)
    print('CAMPAIGN '+report['status']+' '+report.get('error',''),flush=True)
    return 0 if report['status']=='passed' else 2

if __name__=='__main__':
    raise SystemExit(main())
