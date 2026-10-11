"""Safety controls for finance, credential handling, and lifecycle evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import tarfile

import pytest
import cloud_policy as policy
import cloud_records as records
import vast_readonly as vast
from prepare_h100_bundle import build


def ledger():
    return dict(total_ceiling_usd=30,verified_prior_spend=True,evidence=['provider-charge-export'],
                project_instance_list_complete=True,prior_spend_usd=8,
                pending_charges_upper_bound_usd=0,other_committed_project_spend_usd=0,
                reported_credit_balance_usd=17.67,verified_as_of_utc=datetime.now(timezone.utc).isoformat())


def approval():
    now=datetime.now(timezone.utc)
    return dict(approved=True,approval_note='Synthetic test approval, authorizes no provider operation',
                source_sha256=policy.AUDITED_SOURCES,allowed_grids=[128,256],
                execution_sha256=policy.execution_fingerprint(),quoted_costs_verified=True,
                cost_quote_evidence='synthetic quote: <=$2/h, all noncompute charges <=$0.25',
                max_additional_usd=1,hourly_rate_usd=2,noncompute_cost_reserve_usd=.25,
                max_instance_wall_seconds=1200,instance_id=123,termination_guard_armed=True,
                termination_guard_evidence='synthetic-test',provider_started_at_utc=now.isoformat(),
                termination_deadline_utc=(now+timedelta(seconds=1200)).isoformat())


@pytest.mark.parametrize('field,value',[
    ('prior_spend_usd',None),('prior_spend_usd',float('nan')),
    ('pending_charges_upper_bound_usd',float('inf')),('pending_charges_upper_bound_usd',-1),
    ('verified_prior_spend',False),('project_instance_list_complete',False),
    ('total_ceiling_usd',31),('prior_spend_usd',29.5),('pending_charges_upper_bound_usd',22),
    ('evidence',[]),('reported_credit_balance_usd',.5)])
def test_budget_rejects_missing_or_excessive_exposure(field,value):
    data=ledger();data[field]=value
    with pytest.raises(ValueError):
        policy.validate_budget(data,approval())


def test_valid_budget_bounds_lifetime_and_total():
    result=policy.validate_budget(ledger(),approval())
    assert float(result['project_total_exposure_usd'])==9
    assert float(result['lifetime_cost_bound_usd'])<1
    a=approval();a['hourly_rate_usd']=5
    with pytest.raises(ValueError):
        policy.validate_budget(ledger(),a)


def test_current_user_authorization_allows_bounded_two_dollar_smoke():
    a=approval();a.update(max_additional_usd=2,hourly_rate_usd=3)
    assert float(policy.validate_budget(ledger(),a)['lifetime_cost_bound_usd'])==1.25
    a['max_additional_usd']=10
    with pytest.raises(ValueError): policy.validate_budget(ledger(),a)


def test_execution_binds_approval_to_ledger_and_guard(tmp_path):
    path=tmp_path/'ledger.json';path.write_text(json.dumps(ledger()))
    a=approval();a['budget_ledger_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    assert policy.validate_execution(path,a)['compute_timeout_seconds']>1000
    a['termination_guard_armed']=False
    with pytest.raises(ValueError,match='guard'):
        policy.validate_execution(path,a)
    a['termination_guard_armed']=True
    path.write_text(json.dumps(dict(ledger(),prior_spend_usd=9)))
    with pytest.raises(ValueError,match='bound'):
        policy.validate_execution(path,a)


def test_changed_core_cannot_be_approved(monkeypatch):
    monkeypatch.setattr(policy,'source_hashes',lambda:{'ns_fast_v3.py':'changed'})
    with pytest.raises(ValueError,match='re-audit'):
        policy.verify_audited_sources()


def test_readonly_api_refuses_mutation_before_network():
    for method,path in [('DELETE','/api/v0/instances/123'),('PUT','/api/v0/asks/123/')]:
        with pytest.raises(ValueError,match='allowlist'):
            vast.request(method,path,'dummy-unused')


def test_pagination_uses_after_token_and_rejects_repetition(monkeypatch):
    calls=[]
    def request(method,path,key,params=None):
        calls.append(params)
        return {'instances':[{'id':len(calls)}], 'next_token':'cursor' if len(calls)==1 else None}
    monkeypatch.setattr(vast,'request',request)
    assert len(vast.pages('/api/v1/instances','dummy','instances'))==2
    assert calls==[{}, {'after_token':'cursor'}]
    monkeypatch.setattr(vast,'request',lambda *args,**kwargs:{'instances':[],'next_token':'repeated'})
    with pytest.raises(ValueError,match='repeated'):
        vast.pages('/api/v1/instances','dummy','instances')


def test_discovery_redacts_secrets_and_requires_charge_date_filter(monkeypatch):
    def request(method,path,key,params=None,body=None):
        if path.endswith('instances'):
            return {'instances':[{'id':123,'jupyter_token':'SECRET','public_ipaddr':'PRIVATE'}], 'next_token':None}
        assert json.loads(params['select_filters'])['day']['gte']==1
        return {'results':[{'source':'instance-123','amount':8,'metadata':{'token':'SECRET'}}], 'next_token':None}
    monkeypatch.setattr(vast,'request',request)
    result=vast.discover('UNUSED-KEY')
    assert result['instance_listing_complete'] and result['provider_queries_performed']
    assert 'SECRET' not in json.dumps(result) and 'UNUSED-KEY' not in json.dumps(result)


def test_termination_requires_complete_provider_snapshot_and_intact_artifacts(tmp_path):
    now=datetime.now(timezone.utc)
    (tmp_path/'run.csv').write_text('valuable result')
    pending=dict(instance_id=123,status='termination_pending',compute_ended_at_utc=(now-timedelta(seconds=2)).isoformat())
    (tmp_path/'termination.json').write_text(json.dumps(pending))
    records.inventory(tmp_path)
    snapshot=tmp_path.parent/(tmp_path.name+'-snapshot.json')
    data=dict(mode='read-only',as_of_utc=now.isoformat(),instances=[],provider_queries_performed=True)
    snapshot.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='complete'):
        records.record_termination(tmp_path,snapshot,'local download')
    data['instance_listing_complete']=True;data['instances']=[{'id':123}]
    snapshot.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='still exists'):
        records.record_termination(tmp_path,snapshot,'local download')
    data['instances']=[];snapshot.write_text(json.dumps(data))
    (tmp_path/'run.csv').write_text('changed')
    with pytest.raises(ValueError,match='manifest'):
        records.record_termination(tmp_path,snapshot,'local download')
    (tmp_path/'run.csv').write_text('valuable result')
    assert records.record_termination(tmp_path,snapshot,'verified local download')['status']=='provider_destruction_verified'
    assert json.loads((tmp_path/'termination.pending.json').read_text())==pending


def test_payload_excludes_history_and_is_reproducible(tmp_path):
    first=build(tmp_path/'first');second=build(tmp_path/'second')
    assert first['archive_sha256']==second['archive_sha256']
    with tarfile.open(tmp_path/'first/spectrans-3d-h100.tar') as tf:
        names=tf.getnames()
    assert 'src/ns_fast_v3.py' in names and 'payload_manifest.json' in names
    assert not any(name.startswith(('data/','artifacts/','.git/')) for name in names)
