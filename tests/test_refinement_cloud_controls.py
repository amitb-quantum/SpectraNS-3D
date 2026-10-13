import json,os,shutil,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
import pytest
from cloud_policy import ROOT
from extension_state import write,sha
from refinement_io import fingerprint,unpack_verified
from refinement_policy import validate_quote,validate_budget,validate_rehearsal,validate_production_request
from refinement_assessment import validate,historical_reference,checkpoint_at
from refinement_vast_backend import VastBackend

def offer():
    return dict(id=123,gpu_name="H100_SXM",gpu_ram=81920,num_gpus=1,dph_total=.5,storage_cost=.1,
         inet_up_cost=.001,inet_down_cost=.001,reliability2=.999,verification="verified",
         cuda_max_good=13,cpu_arch="amd64",cpu_cores_effective=8,cpu_ram=32000,disk_space=120)

def ledger():
    return dict(total_ceiling_usd=30,verified_prior_spend=True,project_instance_list_complete=True,
          evidence=["test"],verified_as_of_utc=datetime.now(timezone.utc).isoformat(),
          autonomous_authorization=dict(authorized=True,exclusive_additional_cap_usd=10),
          prior_spend_usd=18,pending_charges_upper_bound_usd=1,other_committed_project_spend_usd=0,
          reported_credit_balance_usd=10)

def test_quote_and_budget_keep_distinct_hourly_and_total_caps():
    q=validate_quote(offer());b=validate_budget(ledger(),q)
    assert b["cap_usd"]==5 and float(b["project_exposure_usd"])==24
    assert b["lifetime_seconds"]<=7200 and float(b["lifetime_cost_bound_usd"])<=5

@pytest.mark.parametrize("field,value",[("gpu_name","H200"),("gpu_ram",79000),("num_gpus",2),
       ("dph_total",3),("inet_up_cost",.2),("cpu_arch","arm64"),("dph_total",float("nan"))])
def test_unsupported_or_costly_offer_refused(field,value):
    o=offer();o[field]=value
    with pytest.raises(ValueError):validate_quote(o)

def test_unreconciled_or_exhausted_finances_refused():
    a=ledger();a["prior_spend_usd"]=25
    with pytest.raises(ValueError):validate_budget(a,validate_quote(offer()))
    a=ledger();a["verified_as_of_utc"]="2020-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):validate_budget(a,validate_quote(offer()))
    with pytest.raises(ValueError):validate_budget(ledger(),dict(rate_usd=3))

def test_stale_rehearsals_refused_before_provider_access(tmp_path):
    p=tmp_path/"rehearsal.json"
    write(p,dict(status="passed",provider_calls=0,fingerprint={},cases=[]))
    with pytest.raises(ValueError):validate_rehearsal(p)

def test_production_worker_rejects_unbound_requests():
    with pytest.raises(ValueError):validate_production_request(dict(profile="production"))
    with pytest.raises(ValueError):validate_production_request(dict(authorization=dict(allowed_grids=[768])))

def test_historical_prefix_is_hash_bound_and_excludes_failed_sample():
    r=historical_reference()
    assert len(r["rows"])==111 and float(r["rows"][-1]["t"])==1.1
    assert r["manifest"]["failing_sample"]["t"]==1.11

def test_default_launcher_prints_plan_without_credentials(tmp_path):
    p=subprocess.run([sys.executable,str(ROOT/"scripts/run_vast_refinement.py")],cwd=ROOT,
            check=True,capture_output=True,text=True,env=dict(os.environ,HOME=str(tmp_path)),timeout=10)
    assert json.loads(p.stdout)["configuration"]["N"]==640

def test_actual_remote_pack_restart_and_collection_on_local_transport(tmp_path,monkeypatch):
    """Exercise SSH adapter's protocol locally, without mocking solver/artifacts."""
    import refinement_vast_backend as module
    remote=tmp_path/"remote";remote.mkdir()
    remote_work=remote/"project"/"artifacts"/"refinement_run";remote_work.mkdir(parents=True)
    monkeypatch.setattr(module,"REMOTE",str(remote))
    monkeypatch.setattr(module,"PROJECT",str(ROOT))
    monkeypatch.setattr(module,"WORK",str(remote_work))
    monkeypatch.setattr(module,"PYTHON",sys.executable)
    out=tmp_path/"controller";out.mkdir()
    state=dict(deadline_epoch=time.time()+180,phase="test")
    class Transport(VastBackend):
        def remote(self,command,log="remote.log",timeout=None):
            with (self.out/log).open("a") as f:
                subprocess.run(command,shell=True,cwd=ROOT,check=True,stdout=f,stderr=subprocess.STDOUT,
                    env=dict(os.environ,OMP_NUM_THREADS="2",MKL_NUM_THREADS="2"),timeout=60)
        def copy(self,source,destination,download=False):
            start=time.monotonic();shutil.copyfile(source,destination)
            return max(time.monotonic()-start,1e-9)
    b=Transport(out,state,{})
    # Exercise the real remote command and receipt copy even when this local
    # machine lacks the N640 cloud disk allowance.
    from refinement_capacity import check_free_space
    expected_disk=check_free_space(remote_work)
    if expected_disk["fits"]:
        b.disk_gate("local_transport")
    else:
        with pytest.raises(ValueError,match="insufficient measured free space"):
            b.disk_gate("local_transport")
    measured=json.loads((out/"disk_local_transport.json").read_text())
    assert measured["fits"]==expected_disk["fits"]
    assert measured["required_free_bytes"]==expected_disk["required_free_bytes"]
    binding=fingerprint(ROOT)
    for name in ("coarse","fine"):
        restart=None if name=="coarse" else str(checkpoint_at(b.work/"coarse",.01,require_arrays=False))
        cfg=dict(profile="cpu-rehearsal",phase=name,output=str(b.work/name),restart=restart,
              fingerprint=binding,wall_seconds=120,rehearsal_pause_s=0,telemetry_path=str(b.work/(name+"_driver.csv")))
        b.phase(name,cfg);validate(b.work/name,64,.011,.001)
    assert not list(b.work.rglob("*.npy"))
    archive,record=b.archive("checkpoint",str(remote_work/"coarse"),"pinned-test",.011)
    b.checkpoint_metrics=record
    b.collect(archive,out/"downloaded.gz",out/"progress.json")
    assert unpack_verified(out/"downloaded.gz",out/"collected",record["files"])["verified"]
    assert len(list((out/"collected").glob("U*.npy")))==3

def test_provider_offer_names_use_api_spelling():
    from refinement_policy import offer_query
    names=offer_query()["gpu_name"]["in"]
    assert "H100 SXM" in names
    assert all("_" not in n and n.startswith("H100 ") for n in names)

def test_provider_guard_imports_without_numerical_runtime():
    command="import runpy,sys;runpy.run_path(sys.argv[1],run_name='guard_import_check');assert 'torch' not in sys.modules;assert 'numpy' not in sys.modules"
    subprocess.run([sys.executable,"-c",command,str(ROOT/"scripts/refinement_guard.py")],
                   check=True,cwd=ROOT,timeout=5)

def test_execute_records_quote_and_bounds_before_any_provisioning(tmp_path,monkeypatch):
    """Exercise the real launcher up to SSH preparation with no provider mutations."""
    from types import SimpleNamespace
    import run_vast_refinement as launcher
    import vast_readonly, vast_campaign_api, vast_execution_access
    import reconcile_extension_budget, refinement_assessment
    from spectral_peak import METHOD
    (tmp_path/"configs").mkdir();(tmp_path/"scripts").mkdir()
    estimator=tmp_path/"scripts/spectral_peak.py";estimator.write_text("# test estimator")
    write(tmp_path/"configs/n512_interpolated_peak_reference.json",
          dict(status="passed",method=METHOD,estimator_sha256=sha(estimator)))
    write(tmp_path/"configs/project_budget.json",dict(other_committed_project_spend_usd=0))
    environment=tmp_path/"environment";environment.write_bytes(b"environment")
    payload=tmp_path/"payload";payload.write_bytes(b"payload")
    monkeypatch.setattr(launcher,"ROOT",tmp_path)
    monkeypatch.setattr(launcher,"verify_audited_sources",lambda: {})
    monkeypatch.setattr(launcher,"validate_rehearsal",lambda p: {})
    monkeypatch.setattr(launcher,"validate_assets",lambda a: (environment,payload))
    monkeypatch.setattr(refinement_assessment,"historical_reference",lambda: {})
    monkeypatch.setattr(reconcile_extension_budget,"reconcile",lambda p: ledger())
    monkeypatch.setattr(vast_execution_access,"inspect",lambda: dict(broad_instance_write=True))
    monkeypatch.setattr(vast_readonly,"read_key",lambda p: "test-only-placeholder")
    def request(method,path,key,body=None):
        assert (method,path)==("POST","/api/v0/bundles")
        return dict(offers=[offer()])
    monkeypatch.setattr(vast_readonly,"request",request)
    def forbidden(*args,**kwargs):
        pytest.fail("provider mutation before verified quote")
    monkeypatch.setattr(vast_campaign_api,"api",forbidden)
    class PreparedQuote(Exception):pass
    out=tmp_path/"job"
    def ssh_boundary(command,**kwargs):
        assert command[0]=="ssh-keygen"
        receipt=json.loads((out/"quote.json").read_text())
        assert receipt["cap_usd"]==5
        assert receipt["rate_usd"]==validate_quote(offer())["rate_usd"]
        assert receipt["project_exposure_usd"]=="24"
        assert receipt["environment_sha256"]==sha(environment)
        assert receipt["payload_sha256"]==sha(payload)
        assert receipt["offer"]["id"]==123
        assert not (out/"controller_state.json").exists()
        raise PreparedQuote()
    monkeypatch.setattr(launcher.subprocess,"run",ssh_boundary)
    monkeypatch.setattr(launcher.Path,"home",classmethod(lambda cls: tmp_path))
    (tmp_path/".config").mkdir()
    args=SimpleNamespace(rehearsal="test",job_dir=str(out),offer_id=123,image="test-image")
    with pytest.raises(PreparedQuote):
        launcher.execute(args)
