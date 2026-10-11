#!/usr/bin/env python3
"""Run the fixed bounded extension, checkpoint restart test, and local temporal window."""
import argparse,csv,json,math,sys,time
from pathlib import Path
import torch
from cloud_policy import ROOT,verify_audited_sources
from extension_records import inventory,utc_now
from extension_policy import PLAN_PATH,plan,fingerprint,prerequisite,validate_execution
from extension_state import sha,write,diagnostic_failure
from launch_timestep_followup import LiveGPUTrace,run_checked

def rows(path):
    with Path(path).open() as f:return list(csv.DictReader(f))
def cmd(out,name,target,dt=.0005,restart=None,wall=2400,checkpoints=True,turnover=False):
    c=[sys.executable,'-u','scripts/ns_extension.py','--output',str(out/name),'--target-t',str(target),'--max-dt',str(dt),'--max-wall-seconds',str(wall)]
    if restart:c+=['--restart',str(restart)]
    if not checkpoints:c+=['--no-checkpoints']
    if not turnover:c+=['--no-turnover']
    return c
def validate_run(directory,allow_tail=False):
    m=json.loads((directory/'run.json').read_text())
    if m['source_sha256']!=verify_audited_sources() or m.get('driver_sha256')!=sha(ROOT/'scripts/ns_extension.py') or m['parameters']['N']!=512 or m['parameters']['max_dt'] not in (.0005,.00025):
        raise ValueError('unaudited source or unexpected extension configuration')
    if m['status']=='failed':raise ValueError('extension driver failed')
    if m['status']=='gate_trip' and not (allow_tail and m['stop_reason']=='tail_ratio'):
        raise ValueError('numerical gate failed: '+m.get('stop_reason','unknown'))
    if m['status'] not in ('gate_trip','bounded_complete'):raise ValueError('incomplete extension')
    ds=rows(directory/'diagnostics.csv');bs=rows(directory/'enstrophy.csv');ss=rows(directory/'spectra.csv')
    if not ds or [r['t'] for r in ds]!=[r['t'] for r in bs]:raise ValueError('diagnostic sampling mismatch')
    spectra={}
    for r in ss:
        t=float(r['t']);k=int(r['shell_k']);v=float(r['E_shell_mean_density'])
        if not math.isfinite(v) or v<0 or k in spectra.setdefault(t,{}):raise ValueError('invalid spectrum')
        spectra[t][k]=v
    shells=set(range(int(math.sqrt(3)*256+.5)+1))
    if set(spectra)!={float(r['t']) for r in ds} or any(set(v)!=shells for v in spectra.values()):raise ValueError('incomplete spectra')
    gate=json.loads((ROOT/'configs/h100_acceptance.json').read_text())
    previous=None;E0=m.get('restart',{}).get('metadata',{}).get('E0') if m.get('restart') else float(ds[0]['E'])
    for i,(raw,braw) in enumerate(zip(ds,bs)):
        row={k:float(v) if v!='' else '' for k,v in raw.items()}
        budget={k:float(braw[k]) for k in ('production','grad_omega_sq','dZdt_rhs','residual')}
        t=row['t'];bins=[spectra[t][k] for k in sorted(spectra[t])]
        failure=diagnostic_failure(row,budget,bins,previous,E0,.0005,gate)
        if failure and not (i==len(ds)-1 and allow_tail and failure=='tail_ratio' and m['status']=='gate_trip'):
            raise ValueError('independent diagnostic gate failed: '+str(failure))
        if i and not 0<row['t']-previous['t']<=.010000000001:raise ValueError('missing diagnostic event')
        previous=row
    for entry in m['checkpoint_history']:
        if entry['retained']:
            base=directory/entry['path']
            if sha(base/'checkpoint.json')!=entry['metadata_sha256'] or any(sha(base/n)!=h for n,h in entry['files'].items()):
                raise ValueError('checkpoint hash verification failed')
    return dict(manifest=m,rows=ds,budgets=bs,spectra=spectra)
def compare(a,b,start,end):
    cfg=plan();left={float(r['t']):r for r in a['rows']};right={float(r['t']):r for r in b['rows']}
    times=sorted(t for t in left if start-1e-12<=t<=end+1e-12)
    if times!=sorted(right):raise ValueError('temporal window event times differ')
    maximum={k:0. for k in ('E','Z','wmax','bkm','spectrum_L1_fraction_E')}
    for t in times:
        x,y=left[t],right[t]
        for k in ('E','Z','wmax','bkm'):
            e=abs(float(x[k])-float(y[k]))/max(abs(float(x[k])),abs(float(y[k])),1e-14)
            maximum[k]=max(maximum[k],e)
            if not math.isfinite(e) or e>cfg['timestep_scalar_relative_tolerance']:raise ValueError('temporal '+k+' agreement failed')
        e=sum(abs(a['spectra'][t][k]-b['spectra'][t][k]) for k in a['spectra'][t])/max(float(x['E']),float(y['E']),1e-30)
        maximum['spectrum_L1_fraction_E']=max(maximum['spectrum_L1_fraction_E'],e)
        if e>cfg['timestep_spectrum_L1_fraction_E_tolerance']:raise ValueError('temporal spectra agreement failed')
    coarse_steps=int(left[times[-1]]['step'])-int(left[times[0]]['step'])
    fine_steps=b['manifest']['achieved_steps']
    if coarse_steps<=0 or fine_steps/coarse_steps<cfg['minimum_effective_step_ratio']:raise ValueError('insufficient effective timestep separation')
    # Compare signed net growth against production/loss scale, avoiding singular relative error at turnover.
    ba={float(r['t']):r for r in a['budgets']};bb={float(r['t']):r for r in b['budgets']}
    net_error=max(abs(float(ba[t]['net_production'])-float(bb[t]['net_production']))/
                  max(abs(float(ba[t]['production'])),abs(float(bb[t]['production'])),
                      float(ba[t]['viscous_loss']),float(bb[t]['viscous_loss']),1e-30) for t in times)
    if net_error>cfg['timestep_scalar_relative_tolerance']:raise ValueError('temporal enstrophy budget agreement failed')
    return dict(status='passed',start_t=start,end_t=end,matched_events=len(times),maximum_relative=maximum,
                net_production_scaled_error=net_error,effective_step_ratio=fine_steps/coarse_steps,
                scope='local continuation error from identical coarse checkpoint; no accumulated-error or spatial claim')
def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--output',required=True)
    p.add_argument('--approval-record');p.add_argument('--budget-ledger',required=True);a=p.parse_args()
    if not a.execute:print(json.dumps(plan(),indent=2));return 0
    approval=json.loads(Path(a.approval_record).read_text());bound=validate_execution(a.budget_ledger,approval);cfg=plan()
    if not torch.cuda.is_available() or 'H100' not in torch.cuda.get_device_name():raise ValueError('H100 required')
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False);deadline=time.monotonic()+bound['compute_timeout_seconds']
    report=dict(status='running',started_at_utc=utc_now(),plan=cfg,source_sha256=verify_audited_sources(),
                execution_sha256=fingerprint(),approval=approval,budget=bound,commands=[])
    termination=dict(instance_id=approval['instance_id'],status='termination_pending',provider_started_at_utc=approval['provider_started_at_utc'],
                     deadline_utc=approval['termination_deadline_utc'],guard_evidence=approval['termination_guard_evidence'])
    write(out/'termination.json',termination);write(out/'plan.json',cfg);write(out/'source_bundle.json',fingerprint())
    write(out/'acceptance.json',json.loads((ROOT/'configs/h100_acceptance.json').read_text()))
    trace=LiveGPUTrace(out/'nvidia_smi_trace.csv')
    def phase(name):report['phase']=name;write(out/'campaign_progress.json',report);print('PHASE '+name,flush=True)
    def execute(command,name):
        report['commands'].append(command);phase(name)
        run_checked(command,out/(name+'.log'),deadline,trace)
    try:
        trace.thread.start()
        execute([sys.executable,'-m','pytest','-q','tests'],'tests')
        execute([sys.executable,'scripts/verify_h100_reference.py','--output',str(out/'cpu_h100_reference.json')],'cpu_h100_reference')
        execute(cmd(out,'preflight',.01,wall=120),'preflight')
        pre=validate_run(out/'preflight')
        restart=out/'preflight'/pre['manifest']['terminal_checkpoint']['path']
        # Exercise exact N512 checkpoint reload and the normal diagnostic stack before the trajectory.
        execute(cmd(out,'restart_preflight',.02,.00025,restart,120,False),'restart_preflight')
        validate_run(out/'restart_preflight')
        elapsed=pre['manifest']['wall_s']
        remaining=deadline-time.monotonic()
        write(out/'runtime_preflight.json',dict(preflight_wall_s=elapsed,memory=pre['manifest']['memory'],
                                               remaining_compute_seconds=remaining,checkpoint_reload_passed=True))
        if remaining<1800:raise ValueError('insufficient lifetime for baseline rerun, temporal window and collection')
        # Remove tested preflight field after retaining its hash; only production restart fields are collected.
        import shutil
        shutil.rmtree(out/'preflight'/'checkpoints')
        report['preflight_checkpoints_removed_after_reload']=True
        coarse_wall=remaining-600
        execute(cmd(out,'coarse',3.,wall=coarse_wall,turnover=True),'coarse')
        coarse=validate_run(out/'coarse',allow_tail=True);cm=coarse['manifest']
        report['extension_outcome']=dict(status=cm['status'],stop_reason=cm['stop_reason'],last_accepted=cm['last_accepted'],
                                         failing_sample=cm.get('failing_sample'),turnover=cm.get('turnover'),dt_statistics=cm['dt_statistics'])
        baseline=prerequisite()['baseline_rows'];cr={round(float(r['t']),10):r for r in coarse['rows']}
        for r in baseline:
            if float(r['t'])>cm['last_accepted']['t']+1e-12:break
            actual=cr.get(round(float(r['t']),10))
            if actual is None:raise ValueError('missing baseline anchor time')
            for k in ('E','Z','wmax','bkm'):
                error=abs(float(r[k])-float(actual[k]))/max(abs(float(r[k])),abs(float(actual[k])),1e-14)
                if error>cfg['timestep_scalar_relative_tolerance']:raise ValueError('rerun baseline anchor failed: '+k)
        phase('extension_closed')
        endpoint=cm['last_accepted']['t']
        eligible=[e for e in cm['checkpoint_history'] if e['retained'] and
                  cfg['temporal_window_min_t']-1e-12<=endpoint-e['t']<=cfg['temporal_window_max_t']+1e-12]
        if endpoint<=1.:raise ValueError('no extension beyond validated baseline')
        if not eligible:raise ValueError('no retained checkpoint supports the required terminal window')
        chosen=min(eligible,key=lambda e:e['t']);start=chosen['t']
        execute(cmd(out,'fine_window',endpoint,.00025,out/'coarse'/chosen['path'],deadline-time.monotonic()-30,False),'fine_window')
        fine=validate_run(out/'fine_window')
        report['temporal_window']=compare(coarse,fine,start,endpoint)
        report['driver_peak_used_fraction']=trace.finish()
        report['status']='bounded_evidence_collected'
        report['scientific_scope']='Enstrophy endpoint exploration with operational gates; spatial convergence unverified.'
    except Exception as exc:report.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    finally:
        if trace.thread.is_alive():trace.stop.set();trace.thread.join(timeout=12)
        report['ended_at_utc']=utc_now();termination.update(compute_ended_at_utc=report['ended_at_utc'],compute_status=report['status'])
        write(out/'termination.json',termination);write(out/'campaign.json',report);write(out/'campaign_progress.json',report);inventory(out)
    print('CAMPAIGN '+report['status']+' '+report.get('error',''),flush=True)
    return 0 if report['status']=='bounded_evidence_collected' else 2
if __name__=='__main__':raise SystemExit(main())
