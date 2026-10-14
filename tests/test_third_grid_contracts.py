import json,subprocess,sys
from pathlib import Path
import pytest
from cloud_policy import ROOT,verify_audited_sources
from third_grid_policy import validate_budget,validate_quote,validate_production_request
from third_grid_capacity import disk_requirement
from third_grid_review import lifetime_seconds
from ns_third_grid_worker import profile
from third_grid_assessment import historical_640
from test_third_grid_cloud_controls import offer,ledger

def test_768_only_profile_and_existing_profiles_are_frozen():
    from ns_refinement_worker import profile as old
    assert old("production")["N"]==640
    p=profile("production")
    assert p["N"]==768 and p["ceiling"]==1.1
    with pytest.raises(ValueError):profile("N1024")
    verify_audited_sources()

def test_new_authority_cannot_be_replayed_or_widened():
    a=ledger();a["third_grid_authorization"]["status"]="consumed"
    with pytest.raises(ValueError):validate_budget(a,validate_quote(offer()))
    a=ledger();a["total_ceiling_usd"]=41
    with pytest.raises(ValueError):validate_budget(a,validate_quote(offer()))
    a=ledger();a["third_grid_authorization"]["allowed_grids"]=[768,1024]
    with pytest.raises(ValueError):validate_budget(a,validate_quote(offer()))

def test_lifetime_cost_and_disk_bounds():
    rate=4.417777777777778
    assert lifetime_seconds(rate)==10800
    assert rate*10800/3600+.5<15
    assert disk_requirement()["required_free_bytes"]>93_000_000_000
    assert disk_requirement()["requested_disk_GB"]==120
    with pytest.raises(ValueError):lifetime_seconds(rate,cap_usd=15)

def test_exact_published_640_baseline_excludes_later_unaccepted_state():
    r=historical_640()
    assert len(r["rows"])==111 and float(r["rows"][-1]["t"])==1.1
    assert r["manifest"]["parameters"]["N"]==640

def test_bound_request_rejects_grid_spending_lifetime_plan_and_deadline_tampering():
    from extension_state import sha
    from third_grid_io import fingerprint
    import copy
    a=dict(allowed_grids=[768],source_sha256=verify_audited_sources(),fingerprint=fingerprint(ROOT),
        provisioning_authorized=True,approval_note="explicit test authority",guard_armed=True,instance_id=123,
        cap_usd=14,lifetime_seconds=10800,reserve_usd=.5,
        plan_sha256=sha(ROOT/"configs/n768_third_grid_proposal.json"),
        started_epoch=1000.,deadline_epoch=11740.)
    cfg=dict(authorization=a,provider_deadline_epoch=a["deadline_epoch"])
    assert validate_production_request(cfg)==a
    for field,value in [("allowed_grids",[1024]),("cap_usd",15),("lifetime_seconds",10801),
                        ("plan_sha256","0"*64),("guard_armed",False),("instance_id",None)]:
        bad=copy.deepcopy(cfg);bad["authorization"][field]=value
        with pytest.raises(ValueError):validate_production_request(bad)
    bad=copy.deepcopy(cfg);bad["provider_deadline_epoch"]+=1
    with pytest.raises(ValueError):validate_production_request(bad)
    bad=copy.deepcopy(cfg);bad["rehearsal_pause_s"]=.2
    with pytest.raises(ValueError):validate_production_request(bad)

def test_machine_spec_and_worker_financial_capacity_are_consistent():
    cfg=json.loads((ROOT/"configs/n768_third_grid_proposal.json").read_text())
    assert cfg["configuration"]["N"]==cfg["preflight"]["N"]==768
    assert cfg["budget"]["total_project_cap_usd"]==40
    assert cfg["budget"]["new_all_in_cap_usd"]==14
    assert cfg["budget"]["maximum_lifetime_seconds"]==10800
    assert cfg["checkpoint_collection"]["full_state_bytes"]==disk_requirement()["full_state_bytes"]
    assert cfg["preflight"]["disk_requirement"]["requested_GB"]==120
    assert cfg["spectral_diagnostics"]["relative_loss_kmin"]==192
    assert cfg["configuration"]["target_t"]==profile("production")["prefix"]==1.1
