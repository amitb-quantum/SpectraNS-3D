"""Restart correctness, operational stopping and $4 lifecycle refusal tests."""
from datetime import datetime,timedelta,timezone
import csv,json
from pathlib import Path
import numpy as np
import pytest
import torch
from ns_fast_v3 import Solver
from extension_state import save_checkpoint,load_checkpoint,Turnover,high_shell_share,diagnostic_failure
from ns_extension import simulate
import extension_policy as policy

def ledger():
    return dict(total_ceiling_usd=30,verified_prior_spend=True,project_instance_list_complete=True,
                evidence=['synthetic'],prior_spend_usd=15.565,pending_charges_upper_bound_usd=.754,
                other_committed_project_spend_usd=0,reported_credit_balance_usd=14,
                verified_as_of_utc=datetime.now(timezone.utc).isoformat())
def approval():
    return dict(max_additional_usd=3,hourly_rate_usd=2.1,noncompute_cost_reserve_usd=.5,
                max_instance_wall_seconds=4200,quoted_costs_verified=True,cost_quote_evidence='synthetic')
def test_extension_cap():
    r=policy.validate_budget(ledger(),approval())
    assert r['lifetime_cost_bound_usd']=='2.95'
    assert float(r['project_total_exposure_usd'])==19.319
@pytest.mark.parametrize('field,value',[('max_additional_usd',3.01),('hourly_rate_usd',2.11),
    ('max_instance_wall_seconds',4201),('noncompute_cost_reserve_usd',.49)])
def test_overspend_refused(field,value):
    a=approval();a[field]=value
    with pytest.raises(ValueError):policy.validate_budget(ledger(),a)
def test_total_credit_staleness():
    for k,v in [('prior_spend_usd',27),('reported_credit_balance_usd',2),
                ('verified_as_of_utc',(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat())]:
        d=ledger();d[k]=v
        with pytest.raises(ValueError):policy.validate_budget(d,approval())
def test_turnover_needs_positive_crossing_then_margin():
    x=Turnover()
    assert x.observe(0,1,-1) is None
    assert x.observe(.1,1,2) is None
    assert x.observe(.2,1.1,-.1) is None
    assert x.crossing['previous_t']==.1 and x.crossing['first_nonpositive_t']==.2
    assert x.observe(.29,1.099,-.1) is None
    assert x.observe(.3,1.099,-.1)=='turnover_margin'
def test_turnover_decline_priority():
    x=Turnover();x.observe(0,1,2);x.observe(.1,1.2,-1)
    assert x.observe(.11,1.18,-1)=='turnover_decline'
def test_high_shell_bounds():
    bins=[0]*130;bins[128]=1
    d=high_shell_share(bins,.0005,2*128**4,128)
    assert d['loss_share_low']<d['loss_share_center']==1<d['loss_share_high']
    assert d['energy_share']==1
def checkpoint(tmp_path):
    s=Solver(16,.0005,.2,.0005,'cpu',torch.float64);u=s.ic_tgv()
    save_checkpoint(tmp_path/'state',u,s,'tgv',.1,200,1,1)
    return s,u
def test_checkpoint_exact_and_grid_rejection(tmp_path):
    s,u=checkpoint(tmp_path);v,m=load_checkpoint(tmp_path/'state',s,'tgv')
    assert m['t']==.1 and all(torch.equal(a,b) for a,b in zip(u,v))
    with pytest.raises(ValueError,match='physics'):
        load_checkpoint(tmp_path/'state',Solver(32,.0005,.2,.0005,'cpu',torch.float64),'tgv')
def test_checkpoint_corruption_refused(tmp_path):
    s,u=checkpoint(tmp_path);p=tmp_path/'state/U1.npy'
    with p.open('r+b') as f:f.seek(-1,2);f.write(b'x')
    with pytest.raises(ValueError,match='checksum'):load_checkpoint(tmp_path/'state',s,'tgv')
def test_checkpoint_runtime_refused(tmp_path):
    s,u=checkpoint(tmp_path);p=tmp_path/'state/checkpoint.json';m=json.loads(p.read_text())
    m['torch']='invalid';p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='runtime'):load_checkpoint(tmp_path/'state',s,'tgv')
def test_split_trajectory_matches_uninterrupted(tmp_path):
    kwargs=dict(N=16,device='cpu',case='tgv',turnover=False,max_wall_seconds=60)
    full=simulate(tmp_path/'full',target=.03,**kwargs)
    first=simulate(tmp_path/'first',target=.01,**kwargs)
    assert full['status']==first['status']=='bounded_complete'
    resume=tmp_path/'first'/first['terminal_checkpoint']['path']
    split=simulate(tmp_path/'split',target=.03,restart=resume,**kwargs)
    assert split['status']=='bounded_complete' and split['achieved_steps']>0
    for i in range(3):
        a=np.load(tmp_path/'full'/full['terminal_checkpoint']['path']/f'U{i}.npy')
        b=np.load(tmp_path/'split'/split['terminal_checkpoint']['path']/f'U{i}.npy')
        assert np.array_equal(a,b)
    assert split['last_accepted']['bkm']==pytest.approx(full['last_accepted']['bkm'],abs=1e-15)
    with (tmp_path/'full/steps.csv').open() as f:steps=list(csv.DictReader(f))
    assert all(float(x['dt'])>0 for x in steps)
    assert {'cap','event'}>=set(x['limiter'] for x in steps)
def test_tail_trip_retains_failed_and_last_accepted(tmp_path):
    import ns_extension
    gates=json.loads((policy.ROOT/'configs/h100_acceptance.json').read_text())
    s=Solver(16,.0005,.2,.0005,'cpu',torch.float64)
    tail=s.diagnostics(s.ic_tgv())[-1]
    gates['tail_ratio_max']=tail/2
    r=simulate(tmp_path/'trip',N=16,device='cpu',case='tgv',target=.01,gate=gates,max_wall_seconds=30)
    assert r['status']=='gate_trip' and r['stop_reason']=='tail_ratio'
    assert r['last_accepted'] is None and r['failing_sample']['t']==0
    assert (tmp_path/'trip'/r['terminal_checkpoint']['path']/'checkpoint.json').exists()
def test_guard_deadline_ownership(tmp_path,monkeypatch):
    import vast_extension_watchdog as guard
    import os
    now=datetime.now(timezone.utc)
    d=dict(label='SpectraNS-3D-v3-extension-synthetic',instance_id=123,provisioning_authorized=True,
           approval_note='synthetic',controller_pid=os.getpid(),provider_started_at_utc=(now-timedelta(seconds=10)).isoformat(),
           termination_deadline_utc=(now-timedelta(seconds=1)).isoformat())
    (tmp_path/'controller_state.json').write_text(json.dumps(d));calls=[]
    monkeypatch.setattr(guard,'destroy_owned',lambda v:calls.append(v['instance_id']) or {'success':True})
    monkeypatch.setattr(guard,'owned_instance',lambda v:None)
    assert guard.guard(tmp_path)==0 and calls==[123]
def test_extension_plan_scope():
    d=policy.plan()
    assert d['N']==512 and d['max_target_t']==3 and d['max_additional_usd']==3
    assert d['retained_regular_checkpoints']==2 and d['transfer_out_GB_upper']==12

def test_bare_cuda_device_resolves_index(monkeypatch):
    from ns_extension import resolve_device
    monkeypatch.setattr(torch.cuda,'current_device',lambda:2)
    assert resolve_device('cuda')==torch.device('cuda:2')
    assert resolve_device('cuda:1')==torch.device('cuda:1')
    assert resolve_device('cpu')==torch.device('cpu')
def test_shared_attempt_budget_refused(monkeypatch):
    original=policy.plan();original['previous_attempt_cost_upper_usd']=1.01
    monkeypatch.setattr(policy,'plan',lambda:original)
    with pytest.raises(ValueError,match='shared'):
        policy.validate_budget(ledger(),approval())

def test_new_campaign_posting_does_not_consume_old_pending(tmp_path,monkeypatch):
    import reconcile_extension_budget as reconcile
    root=tmp_path/'project';(root/'configs').mkdir(parents=True)
    d=ledger();d.update(prior_spend_usd=2.1,pending_charges_upper_bound_usd=.8,
                      project_instance_ids=[123],notes=[])
    (root/'configs/project_budget.json').write_text(json.dumps(d))
    job=root/'campaign';job.mkdir()
    now=datetime.now(timezone.utc)
    state=dict(label='SpectraNS-3D-v3-extension-synthetic',termination_verified=True,instance_id=456,
               provider_started_at_utc=(now-timedelta(seconds=31)).isoformat(),
               ended_at_utc=(now-timedelta(seconds=1)).isoformat())
    (job/'controller_state.json').write_text(json.dumps(state))
    (job/'quote.json').write_text(json.dumps(dict(conservative_hourly_upper_usd=2,campaign_cap_usd=3)))
    snapshot=dict(instances=[],charge_listing_complete=True,instance_listing_complete=True,
                  charges=[dict(type='instance',source='instance-123',amount=2.2),
                           dict(type='instance',source='instance-456',amount=.3)])
    monkeypatch.setattr(reconcile,'ROOT',root);monkeypatch.setattr(reconcile,'read_key',lambda path:'synthetic')
    monkeypatch.setattr(reconcile,'discover',lambda key:snapshot)
    monkeypatch.setattr(reconcile,'inspect',lambda:dict(financial_fields=dict(credit=20)))
    r=reconcile.reconcile(root/'artifacts/check',job)
    assert r['prior_spend_usd']==2.5
    assert r['pending_charges_upper_bound_usd']==pytest.approx(.8-.1+(2*30/3600+.5-.3))
