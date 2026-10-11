"""Ownership and watchdog behavior are tested without a provider request."""
from datetime import datetime,timedelta,timezone
import json
import os

import pytest
import vast_campaign_api as api
import vast_watchdog as watchdog


def test_destroy_is_bound_to_named_instance(monkeypatch):
    state=dict(label='SpectraNS-3D-v3-smoke-test',instance_id=123,
               provisioning_authorized=True,approval_note='synthetic test')
    monkeypatch.setattr(api,'instances',lambda:[{'id':456,'label':state['label']}])
    with pytest.raises(ValueError,match='ownership'): api.destroy_owned(state)
    monkeypatch.setattr(api,'instances',lambda:[{'id':123,'label':state['label']},{'id':456,'label':'unrelated'}])
    calls=[]
    monkeypatch.setattr(api,'api',lambda method,path: calls.append((method,path)) or {'success':True})
    assert api.destroy_owned(state)['instance_id']==123
    assert calls==[('DELETE','/api/v0/instances/123/')]


def test_watchdog_terminates_at_deadline_without_parent_cooperation(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    state=dict(label='SpectraNS-3D-v3-smoke-test',instance_id=123,provisioning_authorized=True,
               approval_note='synthetic test',controller_pid=os.getpid(),
               termination_deadline_utc=(now-timedelta(seconds=1)).isoformat())
    (tmp_path/'controller_state.json').write_text(json.dumps(state))
    calls=[]
    monkeypatch.setattr(watchdog,'destroy_owned',lambda value: calls.append(value['instance_id']) or {'success':True})
    monkeypatch.setattr(watchdog,'owned_instance',lambda value: None)
    assert watchdog.guard(tmp_path)==0
    assert calls==[123] and (tmp_path/'guard_destroy_receipt.json').exists()


def test_unapproved_guard_never_queries_provider(tmp_path):
    (tmp_path/'controller_state.json').write_text(json.dumps({'label':'unrelated','provisioning_authorized':False}))
    with pytest.raises(ValueError,match='unapproved'): watchdog.guard(tmp_path)


def test_ssh_key_attachment_is_bound_to_owned_instance(monkeypatch):
    state=dict(label='SpectraNS-3D-v3-smoke-test',instance_id=123,provisioning_authorized=True)
    monkeypatch.setattr(api,'instances',lambda:[{'id':123,'label':state['label']}])
    calls=[]
    monkeypatch.setattr(api,'api',lambda method,path,body: calls.append((method,path,body)) or {'success':True})
    public='ssh-ed25519 SYNTHETIC-TEST-PUBLIC'
    assert api.attach_owned_ssh(state,public)['success']
    assert calls==[('POST','/api/v0/instances/123/ssh/',{'ssh_key':public})]
    monkeypatch.setattr(api,'instances',lambda:[])
    with pytest.raises(ValueError): api.attach_owned_ssh(state,public)


def test_provisioning_requires_full_bootstrap_validation(tmp_path):
    import hashlib
    import run_vast_smoke as campaign
    archive=tmp_path/'bootstrap.tar.gz';archive.write_bytes(b'synthetic')
    for name in ['pyproject.toml','requirements-linux-64.lock']:
        (tmp_path/name).write_text('synthetic contract')
    proof=dict(status='passed',full_runtime_status='passed',
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        pyproject_sha256=hashlib.sha256((tmp_path/'pyproject.toml').read_bytes()).hexdigest(),
        requirements_sha256=hashlib.sha256((tmp_path/'requirements-linux-64.lock').read_bytes()).hexdigest())
    record=tmp_path/'validation.json';record.write_text(json.dumps(proof))
    assert campaign.validate_bootstrap_evidence(archive,record,root=tmp_path)['status']=='passed'
    proof['full_runtime_status']='not_requested';record.write_text(json.dumps(proof))
    with pytest.raises(ValueError,match='complete local'):
        campaign.validate_bootstrap_evidence(archive,record,root=tmp_path)
    proof['full_runtime_status']='passed';record.write_text(json.dumps(proof))
    archive.write_bytes(b'changed archive')
    with pytest.raises(ValueError,match='complete local'):
        campaign.validate_bootstrap_evidence(archive,record,root=tmp_path)


def test_bootstrap_validation_is_bound_to_dependency_contract(tmp_path):
    import hashlib
    import run_vast_smoke as campaign
    archive=tmp_path/'bootstrap.tar.gz';archive.write_bytes(b'synthetic')
    for name in ['pyproject.toml','requirements-linux-64.lock']:
        (tmp_path/name).write_text('synthetic contract')
    proof=dict(status='passed',full_runtime_status='passed',
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        pyproject_sha256=hashlib.sha256((tmp_path/'pyproject.toml').read_bytes()).hexdigest(),
        requirements_sha256=hashlib.sha256((tmp_path/'requirements-linux-64.lock').read_bytes()).hexdigest())
    record=tmp_path/'validation.json';record.write_text(json.dumps(proof))
    (tmp_path/'requirements-linux-64.lock').write_text('unvalidated dependency change')
    with pytest.raises(ValueError,match='dependency contract'):
        campaign.validate_bootstrap_evidence(archive,record,root=tmp_path)
