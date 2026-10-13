import json,time
from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
import account_coexistence as account

def context():
    return dict(nonproject_instances=[dict(id=900,label="digital-brain-exact",
        remaining_seconds=3600,user_attribution="User identified separate work")])

def snapshot(instances=None):
    return dict(instance_listing_complete=True,charge_listing_complete=True,
        instances=instances if instances is not None else [dict(id=900,label="digital-brain-exact",
            dph_total=3,storage_total_cost=.05,actual_status="running")],
        charges=[dict(type="instance",source="instance-123",amount=2.2),
                 dict(type="instance",source="instance-900",amount=40)])

def test_exact_attributed_foreign_instance_reserves_account_credit_only():
    result=account.account_instances(snapshot(),{123},context())
    assert result["project_instances_active"]==0
    assert result["account_instances_active"]==1
    assert float(result["nonproject_credit_reserve_usd"])==3.05
    assert account.account_instances(snapshot([]),{123},context())["nonproject_credit_reserve_usd"]=="0"

@pytest.mark.parametrize("mutation",["unknown","label_changed","project","duplicate","unattributed",
    "missing_rate","negative_rate","incomplete","invalid_runtime"])
def test_account_attribution_fails_closed(mutation):
    s=snapshot();c=context()
    if mutation=="unknown":s["instances"][0]["id"]=901
    elif mutation=="label_changed":s["instances"][0]["label"]="digital-brain-another"
    elif mutation=="project":s["instances"][0]["id"]=123
    elif mutation=="duplicate":s["instances"]*=2
    elif mutation=="unattributed":c["nonproject_instances"][0]["user_attribution"]=""
    elif mutation=="missing_rate":s["instances"][0].pop("storage_total_cost")
    elif mutation=="negative_rate":s["instances"][0]["dph_total"]=-1
    elif mutation=="incomplete":s["instance_listing_complete"]=False
    elif mutation=="invalid_runtime":c["nonproject_instances"][0]["remaining_seconds"]=0
    with pytest.raises(ValueError):account.account_instances(s,{123},c)
    with pytest.raises(ValueError):account.account_instances(snapshot(),{123},None)

def test_project_id_cannot_be_excluded_even_when_currently_absent():
    c=context();c["nonproject_instances"][0]["id"]=123
    with pytest.raises(ValueError):account.account_instances(snapshot([]),{123},c)

def test_reconciliation_keeps_foreign_charges_out_of_project(tmp_path,monkeypatch):
    import reconcile_extension_budget as reconcile
    root=tmp_path;(root/"configs").mkdir()
    ledger=dict(prior_spend_usd=2.1,pending_charges_upper_bound_usd=.8,
        project_instance_ids=[123],evidence=[],notes=[])
    (root/"configs/project_budget.json").write_text(json.dumps(ledger))
    monkeypatch.setattr(reconcile,"ROOT",root)
    monkeypatch.setattr(reconcile,"read_key",lambda path:"synthetic")
    monkeypatch.setattr(reconcile,"discover",lambda key:snapshot())
    monkeypatch.setattr(reconcile,"inspect",lambda:dict(financial_fields=dict(credit=9.5)))
    r=reconcile.reconcile(root/"artifacts/billing",account_context=context())
    assert r["prior_spend_usd"]==2.2 and r["project_instance_ids"]==[123]
    assert r["nonproject_credit_reserve_usd"]==3.05
    assert r["pending_charges_upper_bound_usd"]==pytest.approx(.7)

def test_credit_reserve_required_without_reducing_project_budget():
    from test_refinement_cloud_controls import ledger,offer
    from refinement_policy import validate_budget,validate_quote
    l=ledger();l["nonproject_credit_reserve_usd"]=3.05
    l["reported_credit_balance_usd"]=8.04
    with pytest.raises(ValueError):validate_budget(l,validate_quote(offer()))
    l["reported_credit_balance_usd"]=8.06
    b=validate_budget(l,validate_quote(offer()))
    assert b["project_exposure_usd"]=="24"
    assert float(b["nonproject_credit_reserve_usd"])==3.05

def test_low_credit_guard_destroys_only_owned_instance(tmp_path,monkeypatch):
    import refinement_guard as guard
    import vast_campaign_api as api
    out=tmp_path;now=time.time()
    state=dict(mode="vast",provisioning_authorized=True,
        label="SpectraNS-3D-v3-refinement-test",instance_id=123,
        controller_pid=42,controller_birth="test",started_epoch=now,
        deadline_epoch=now+600,phase="coarse",account_credit_floor_usd=1.0,
        account_context=context())
    (out/"controller_state.json").write_text(json.dumps(state))
    monkeypatch.setattr(guard,"same",lambda *a:True)
    monkeypatch.setattr(account,"read_account_credit",lambda:.8)
    destroyed=[]
    monkeypatch.setattr(api,"destroy_owned",lambda s:destroyed.append(s["instance_id"]) or dict(verified=True))
    monkeypatch.setattr(api,"owned_instance",lambda s:None)
    guard.main(out)
    assert destroyed==[123]
    assert json.loads((out/"guard_trigger.json").read_text())["reason"]=="account_credit_low"
    assert json.loads((out/"termination.json").read_text())["verified"]
    assert json.loads((out/"account_credit_watch.json").read_text())["credit_usd"]==.8

def test_credit_monitor_limits_reads_and_sanitizes_failures(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(account,"read_account_credit",lambda:calls.append(1) or 9)
    state=dict(account_credit_floor_usd=1)
    assert account.monitor_credit(tmp_path,state,10) is None
    assert account.monitor_credit(tmp_path,state,20) is None
    assert len(calls)==1
    def fail():raise ValueError("synthetic credential text must never be logged")
    monkeypatch.setattr(account,"read_account_credit",fail)
    assert account.monitor_credit(tmp_path,state,71)=="account_credit_unavailable"
    record=(tmp_path/"account_credit_watch.json").read_text()
    assert "synthetic credential" not in record
    assert json.loads(record)["error_kind"]=="ValueError"

def test_budget_closure_allows_exact_foreign_instance_but_refuses_owned(tmp_path,monkeypatch):
    import run_vast_refinement as launcher
    import vast_readonly as readonly
    import vast_execution_access as access
    root=tmp_path;(root/"configs").mkdir()
    ledger=dict(prior_spend_usd=2.1,pending_charges_upper_bound_usd=.8,
        project_instance_ids=[123],evidence=[],other_committed_project_spend_usd=5)
    path=root/"configs/project_budget.json";path.write_text(json.dumps(ledger))
    out=root/"job";out.mkdir()
    state=dict(instance_id=456,started_epoch=1000,account_context=context())
    (out/"controller_state.json").write_text(json.dumps(state))
    (out/"quote.json").write_text(json.dumps(dict(rate_usd="2")))
    (out/"termination.json").write_text(json.dumps(dict(at_epoch=1030,verified=True)))
    s=snapshot();s["charges"].append(dict(type="instance",source="instance-456",amount=.3))
    monkeypatch.setattr(launcher,"ROOT",root)
    monkeypatch.setattr(readonly,"read_key",lambda p:"synthetic")
    monkeypatch.setattr(readonly,"discover",lambda key:s)
    monkeypatch.setattr(access,"inspect",lambda:dict(financial_fields=dict(credit=9)))
    launcher.close_budget(out)
    result=json.loads(path.read_text())
    assert result["project_instance_ids"]==[123,456] and result["prior_spend_usd"]==2.5
    assert result["other_committed_project_spend_usd"]==0
    before=path.read_bytes()
    s["instances"].append(dict(id=456,label="SpectraNS-3D-v3-refinement-test"))
    with pytest.raises(ValueError):launcher.close_budget(out)
    assert path.read_bytes()==before

def test_credit_monitor_cannot_disarm_guard_before_instance_creation(tmp_path,monkeypatch):
    import refinement_guard as guard
    now=time.time()
    state=dict(mode="vast",provisioning_authorized=True,
        label="SpectraNS-3D-v3-refinement-test",instance_id=None,
        controller_pid=42,controller_birth="test",started_epoch=now,
        deadline_epoch=now+600,phase="prepared",account_credit_floor_usd=1.0)
    (tmp_path/"controller_state.json").write_text(json.dumps(state))
    monkeypatch.setattr(guard,"same",lambda *a:True)
    def forbidden(*a):pytest.fail("credit failure must not disarm guard before create")
    monkeypatch.setattr(account,"monitor_credit",forbidden)
    def complete(*a):
        (tmp_path/"termination.json").write_text(json.dumps(dict(verified=True)))
    monkeypatch.setattr(guard.time,"sleep",complete)
    guard.main(tmp_path)
    assert not (tmp_path/"guard_trigger.json").exists()
