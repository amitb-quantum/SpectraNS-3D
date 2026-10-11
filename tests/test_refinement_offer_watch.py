import json,types
from decimal import Decimal
import pytest
from refinement_capacity import check_free_space,disk_requirement,STATE_BYTES
from refinement_policy import validate_quote,validate_budget,offer_query
from refinement_review import lifetime_seconds,protected_phase_forecast
from poll_refinement_offers import poll_once
from test_refinement_cloud_controls import offer,ledger

def test_price_screen_is_not_a_runtime_approval():
    o=offer();o.update(dph_total=2.6,storage_cost=0,disk_space=64)
    q=validate_quote(o);b=validate_budget(ledger(),q)
    assert b["lifetime_seconds"]==6230
    usable=b["lifetime_seconds"]-60-120
    assert not protected_phase_forecast(1.5,1.,30.,usable,180,setup_preflight_seconds=600)["fits"]
    assert protected_phase_forecast(1.3,.9,20,usable,180,setup_preflight_seconds=600)["fits"]
    assert 5600*1.1*2.6/3600+.5<5
    assert (5600*1.1+60+120)*2.6/3600+.5>5

def test_storage_price_included_at_screen_boundary():
    o=offer();o.update(dph_total=2.59,storage_cost=.2,disk_space=64)
    with pytest.raises(ValueError):validate_quote(o)
    o["dph_total"]=2.58
    assert Decimal(validate_quote(o)["rate_usd"])<=Decimal("2.6")
    o["disk_space"]=63.99
    with pytest.raises(ValueError):validate_quote(o)

def test_disk_peak_includes_both_trajectories_and_checks_actual_available_space(tmp_path,monkeypatch):
    import refinement_capacity as module
    requirement=disk_requirement()
    assert requirement["runtime_bytes_upper"]>=6*STATE_BYTES+6320000000+2000000000
    needed=requirement["required_free_bytes"]
    monkeypatch.setattr(module.os,"statvfs",lambda path:types.SimpleNamespace(f_bavail=needed-1,f_frsize=1,f_blocks=64000000000))
    assert not check_free_space(tmp_path)["fits"]
    monkeypatch.setattr(module.os,"statvfs",lambda path:types.SimpleNamespace(f_bavail=needed,f_frsize=1,f_blocks=64000000000))
    assert check_free_space(tmp_path)["fits"]

def test_provider_query_filters_incompatible_hosts_before_result_limit():
    q=offer_query()
    assert q["cuda_max_good"]=={"gte":13}
    assert q["disk_space"]=={"gte":64}
    assert q["dph_total"]=={"lte":2.6}

def test_readonly_watch_deduplicates_and_sanitizes(tmp_path):
    calls=[]
    def query(method,path,key,body):
        calls.append((method,path))
        return dict(offers=[dict(offer(),jupyter_token="SECRET",private_key="SECRET")])
    def run():return poll_once(tmp_path,query_fn=query,key_fn=lambda:"LOCAL_SECRET")
    a,p=run();assert a["alert"]
    b,p=run();assert not b["alert"]
    assert calls==[("POST","/api/v0/bundles")]*2
    assert all("SECRET" not in x.read_text() for x in tmp_path.glob("*.json"))
    assert a["instance_mutations_performed"] is False and a["budget_mutations_performed"] is False
    assert all("jupyter_token" not in x["offer"] for x in a["eligible"])

def test_watch_alerts_on_new_price_after_absence_and_suppresses_repeat_errors(tmp_path):
    def run(response):return poll_once(tmp_path,query_fn=lambda *a,**k:response,key_fn=lambda:"unused")[0]
    assert not run(dict(offers=[]))["alert"]
    assert run(dict(offers=[offer()]))["alert"]
    changed=offer();changed["dph_total"]=.6
    assert run(dict(offers=[changed]))["alert"]
    assert not run(dict(offers=[changed]))["alert"]
    def fail(*a,**k):raise ValueError("credential SECRET and response SECRET")
    a,p=poll_once(tmp_path,query_fn=fail,key_fn=lambda:"SECRET")
    assert a["status"]=="error" and a["alert"] and "SECRET" not in p.read_text()
    a,p=poll_once(tmp_path,query_fn=fail,key_fn=lambda:"SECRET")
    assert not a["alert"]
    assert run(dict(offers=[changed]))["alert"]

def test_missing_key_never_calls_provider(tmp_path):
    def forbidden(*a,**k):raise AssertionError("no request allowed")
    a,p=poll_once(tmp_path,query_fn=forbidden,key_fn=lambda:None)
    assert a["status"]=="error" and a["error_kind"]=="ValueError"
