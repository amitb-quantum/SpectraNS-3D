"""Financial and numerical refusal gates for the bounded N512 comparison."""
from datetime import datetime,timedelta,timezone
import copy
import csv
import json
import os
from pathlib import Path
import pytest
import followup_policy as policy
import launch_timestep_followup as launch
import vast_followup_watchdog as watchdog
from cloud_policy import AUDITED_SOURCES, validate_budget as smoke_budget

def ledger():
    return dict(total_ceiling_usd=30,verified_prior_spend=True,evidence=['synthetic'],
                project_instance_list_complete=True,prior_spend_usd=13.323,
                pending_charges_upper_bound_usd=.25,other_committed_project_spend_usd=0,
                reported_credit_balance_usd=16.77,verified_as_of_utc=datetime.now(timezone.utc).isoformat())

def approval():
    return dict(max_additional_usd=8,hourly_rate_usd=3,noncompute_cost_reserve_usd=.5,
                max_instance_wall_seconds=9000,quoted_costs_verified=True,cost_quote_evidence='synthetic')

def test_budget_and_smoke_remain_separate():
    assert float(policy.validate_budget(ledger(),approval())['project_total_exposure_usd'])==21.573
    with pytest.raises(ValueError,match='1200'):
        smoke_budget(ledger(),approval())

@pytest.mark.parametrize('field,value',[
    ('max_additional_usd',10),('hourly_rate_usd',3.01),
    ('noncompute_cost_reserve_usd',.49),('max_instance_wall_seconds',9001)])
def test_budget_refuses_excess_authority(field,value):
    record=approval();record[field]=value
    with pytest.raises(ValueError): policy.validate_budget(ledger(),record)

def test_total_and_stale_billing_are_refused():
    record=ledger();record['prior_spend_usd']=22
    with pytest.raises(ValueError,match='exposure'): policy.validate_budget(record,approval())
    record=ledger();record['verified_as_of_utc']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    with pytest.raises(ValueError,match='one hour'): policy.validate_budget(record,approval())

def test_plan_never_requests_larger_grids(tmp_path):
    cmd=launch.command(tmp_path,'synthetic',512,.00025,1.)
    assert '--allow_large_grid' not in cmd and '--memory_reference' not in cmd
    assert cmd[cmd.index('--N')+1]=='512'
    assert cmd[cmd.index('--max_dt')+1]=='0.00025'

def synthetic(out,name,dt,steps):
    n=512;target=.01
    memory=dict(peak_allocated_GB=25,peak_reserved_GB=27,total_GB=85)
    params=dict(N=n,case='tubes',nu=.0005,scheme='lsrk4',fp64=True,cfl=.2,max_dt=dt,
                target_t=target,log_dt=.01,spectrum_slab=4,spectrum_stride=1,snapshot_times='')
    manifest=dict(status='completed',t=target,steps=steps,source_sha256=AUDITED_SOURCES,
                  parameters=params,memory=memory,wall_s=20)
    (out/(name+'.csv.json')).write_text(json.dumps(manifest))
    header=['step','t','dt','E','Z','eps','dEdt_fd','budget_resid_rel','wmax','bkm',
            'tail_ratio','div_max','wall_s','peak_mem_GB']
    with (out/(name+'.csv')).open('w') as f:
        writer=csv.writer(f);writer.writerow(header)
        writer.writerow([0,0,0,1,1,.001,'','',10,0,1e-12,1e-14,1,25])
        writer.writerow([steps,.01,dt,.99999,1,.001,-.001,0,10,.1,1e-12,1e-14,20,25])
    with (out/(name+'_spectra.csv')).open('w') as f:
        writer=csv.writer(f);writer.writerow(['t','shell_k','E_shell_mean_density'])
        for t,E in [(0,1),(.01,.99999)]:
            writer.writerows([t,k,E if k==1 else 0] for k in range(int(3**.5*(n//2)+.5)+1))
    with (out/(name+'_enstrophy.csv')).open('w') as f:
        writer=csv.writer(f);writer.writerow(['t','production','grad_omega_sq','dZdt_rhs','residual'])
        writer.writerows([[0,1,2000,0,0],[.01,1,2000,0,0]])
    return launch.check_run(out,name,n,dt,target)

def test_matched_refinement_and_full_spectra(tmp_path):
    left=synthetic(tmp_path,'coarse',.0005,20)
    right=synthetic(tmp_path,'fine',.00025,40)
    result=launch.compare_runs(left,right)
    assert len(result)==10 and max(row['relative_difference'] for row in result)==0

def test_identical_effective_steps_are_refused(tmp_path):
    left=synthetic(tmp_path,'coarse',.0005,40)
    right=synthetic(tmp_path,'fine',.00025,40)
    with pytest.raises(ValueError,match='effective timestep'):
        launch.compare_runs(left,right)

def test_corrupt_spectrum_is_refused(tmp_path):
    synthetic(tmp_path,'coarse',.0005,20)
    path=tmp_path/'coarse_spectra.csv'
    path.write_text(path.read_text().replace('0,1,1','0,1,2'))
    with pytest.raises(ValueError,match='Parseval'):
        launch.check_run(tmp_path,'coarse',512,.0005,.01)

def test_memory_headroom_is_refused(tmp_path):
    synthetic(tmp_path,'coarse',.0005,20)
    path=tmp_path/'coarse.csv.json';value=json.loads(path.read_text())
    value['memory']['peak_reserved_GB']=70;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='headroom'):
        launch.check_run(tmp_path,'coarse',512,.0005,.01)

def test_independent_followup_guard_destroys_at_deadline(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    state=dict(label='SpectraNS-3D-v3-followup-synthetic',instance_id=123,
        provisioning_authorized=True,approval_note='synthetic',controller_pid=os.getpid(),
        provider_started_at_utc=(now-timedelta(seconds=10)).isoformat(),
        termination_deadline_utc=(now-timedelta(seconds=1)).isoformat())
    (tmp_path/'controller_state.json').write_text(json.dumps(state))
    calls=[]
    monkeypatch.setattr(watchdog,'destroy_owned',lambda value:calls.append(value['instance_id']) or {'success':True})
    monkeypatch.setattr(watchdog,'owned_instance',lambda value:None)
    assert watchdog.guard(tmp_path)==0 and calls==[123]

def test_readonly_reconciliation_excludes_unrelated_instances(tmp_path,monkeypatch):
    import reconcile_project_budget as reconcile
    root=tmp_path/'project';(root/'configs').mkdir(parents=True)
    record=ledger();record.update(project_instance_ids=[123],notes=[])
    (root/'configs/project_budget.json').write_text(json.dumps(record))
    snapshot=dict(instances=[],charge_listing_complete=True,instance_listing_complete=True,
        charges=[dict(type='instance',source='instance-123',amount=2.1),
                 dict(type='instance',source='instance-999',amount=100)])
    monkeypatch.setattr(reconcile,'ROOT',root)
    monkeypatch.setattr(reconcile,'read_key',lambda path:'synthetic-local')
    monkeypatch.setattr(reconcile,'discover',lambda key:snapshot)
    monkeypatch.setattr(reconcile,'inspect',lambda:dict(financial_fields=dict(credit=20)))
    result=reconcile.reconcile(root/'artifacts/check')
    assert result['prior_spend_usd']==2.1 and result['pending_charges_upper_bound_usd']==.25
    assert result['evidence'][-1]=='artifacts/check/provider.json'
