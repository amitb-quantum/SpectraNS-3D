#!/usr/bin/env python3
"""Default is plan only. Explicit --execute provisions one source-bound H100."""
import argparse,fcntl,json,os,re,shlex,subprocess,sys,time,uuid
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
from cloud_policy import ROOT,verify_audited_sources,money
from extension_state import sha,write
from refinement_io import fingerprint
from refinement_policy import validate_rehearsal,validate_quote,validate_budget,offer_query
from refinement_guard import birth
from refinement_capacity import DISK_GB,MAX_HOURLY_USD
from refinement_controller import run
from refinement_vast_backend import VastBackend,REMOTE,PROJECT,WORK,PYTHON

def validate_assets(args):
    environment=Path(args.environment).resolve();payload=Path(args.payload).resolve()
    proof=json.loads(Path(args.bootstrap_validation).read_text())
    if proof.get("status")!="passed" or proof.get("full_runtime_status")!="passed" or sha(environment)!=proof.get("archive_sha256"):
        raise ValueError("verified bootstrap archive required")
    if proof["pyproject_sha256"]!=sha(ROOT/"pyproject.toml") or proof["requirements_sha256"]!=sha(ROOT/"requirements-linux-64.lock"):
        raise ValueError("bootstrap contract changed")
    manifest=json.loads(payload.with_name("bundle_manifest.json").read_text())
    if sha(payload)!=manifest["archive_sha256"] or any(sha(ROOT/n)!=h for n,h in manifest["files"].items()):
        raise ValueError("payload archive/source binding mismatch")
    if not set(fingerprint(ROOT))<=set(manifest["files"]):raise ValueError("payload missing bound source/config")
    reference=json.loads((ROOT/"configs/n512_interpolated_peak_reference.json").read_text())
    for name,digest in reference["historical_small_files_sha256"].items():
        key="artifacts/cloud-preparation/2026-10-10/enstrophy_extension_002/results/coarse/"+name
        if manifest["files"].get(key)!=digest:raise ValueError("payload missing required small historical evidence")
    if environment.stat().st_size>6_000_000_000 or not re.fullmatch(r"vastai/base-image@sha256:[a-f0-9]{64}",args.image):
        raise ValueError("bootstrap size or immutable image invalid")
    return environment,payload

def close_budget(out):
    from vast_readonly import discover,read_key,KEYFILE
    from vast_execution_access import inspect
    snapshot=discover(read_key(KEYFILE));write(out/"billing_after.json",snapshot)
    state=json.loads((out/"controller_state.json").read_text())
    if not snapshot["charge_listing_complete"] or not snapshot["instance_listing_complete"]:
        raise ValueError("complete absence/billing required; commitment stays reserved")
    path=ROOT/"configs/project_budget.json";ledger=json.loads(path.read_text())
    previous=Decimal(str(ledger["prior_spend_usd"]));ids=set(ledger["project_instance_ids"])
    identity=state["instance_id"]
    if identity is None:raise ValueError("ambiguous create: retain commitment for reconciliation")
    ids.add(identity)
    from account_coexistence import account_instances
    account=account_instances(snapshot,ids,state.get("account_context"))
    write(out/"account_attribution_after.json",account)
    def parent(i):
        return sum((Decimal(str(r["amount"])) for r in snapshot["charges"]
                    if r.get("type")=="instance" and r.get("source")=="instance-"+str(i)),Decimal("0"))
    posted_new=parent(identity);old=sum((parent(i) for i in ids if i!=identity),Decimal("0"))
    quote=json.loads((out/"quote.json").read_text());termination=json.loads((out/"termination.json").read_text())
    elapsed=termination["at_epoch"]-state["started_epoch"]
    upper=Decimal(quote["rate_usd"])*Decimal(str(elapsed))/3600+Decimal(".5")
    pending_old=max(Decimal(".25"),Decimal(str(ledger["pending_charges_upper_bound_usd"]))-max(Decimal("0"),old-previous))
    ledger.update(prior_spend_usd=float(old+posted_new),
       pending_charges_upper_bound_usd=float(pending_old+max(Decimal("0"),upper-posted_new)),
       other_committed_project_spend_usd=0,project_instance_ids=sorted(ids),
       reported_credit_balance_usd=inspect()["financial_fields"]["credit"],
       nonproject_credit_reserve_usd=float(account["nonproject_credit_reserve_usd"]),
       nonproject_account_instances=account["nonproject_instances"],
       verified_as_of_utc=datetime.now(timezone.utc).isoformat())
    ledger["evidence"].append((out/"billing_after.json").relative_to(ROOT).as_posix())
    write(path,ledger);write(out/"budget_final.json",ledger)
    write(out/"financial_closure.json",dict(cost_upper_usd=str(upper),within_campaign_cap=upper<=5,
                                           posting_pending=True))

def execute(args):
    if sys.platform!="linux":raise ValueError("execute from native WSL")
    hourly_limit=money(getattr(args,"max_hourly_rate",MAX_HOURLY_USD),"selection hourly ceiling")
    if not 0<hourly_limit<=Decimal(MAX_HOURLY_USD):raise ValueError("selection ceiling may only tighten the fixed policy")
    from vast_readonly import read_key,KEYFILE,request,SAFE_OFFER
    from vast_campaign_api import api,owned_instance,attach_owned_ssh
    from vast_execution_access import inspect
    from reconcile_extension_budget import reconcile
    from refinement_assessment import historical_reference
    from spectral_peak import METHOD
    verify_audited_sources();validate_rehearsal(args.rehearsal);historical_reference()
    reference=json.loads((ROOT/"configs/n512_interpolated_peak_reference.json").read_text())
    if reference["status"]!="passed" or reference["method"]!=METHOD or reference["estimator_sha256"]!=sha(ROOT/"scripts/spectral_peak.py"):
        raise ValueError("matched N512 peak reference not ready")
    environment,payload=validate_assets(args)
    out=Path(args.job_dir).resolve();out.mkdir(parents=True,exist_ok=False)
    with (ROOT/"configs/.refinement-execution.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger_path=ROOT/"configs/project_budget.json"
        if json.loads(ledger_path.read_text()).get("other_committed_project_spend_usd",0)!=0:
            raise ValueError("another commitment exists")
        account_context=json.loads(Path(args.account_context).read_text()) if getattr(args,"account_context",None) else None
        ledger=reconcile(out/"billing_before",account_context=account_context) if account_context else reconcile(out/"billing_before")
        access=inspect()
        if access.get("broad_instance_write") is not True:raise ValueError("local key lacks instance operations")
        raw=request("POST","/api/v0/bundles",read_key(KEYFILE),body=offer_query())
        chosen=[r for r in raw["offers"] if r["id"]==args.offer_id]
        if len(chosen)!=1:raise ValueError("specified live offer unavailable; no automatic substitution")
        offer=chosen[0];quote=validate_quote(offer);bounds=validate_budget(ledger,quote)
        if Decimal(quote["rate_usd"])>hourly_limit:raise ValueError("fresh offer exceeds authorized selection ceiling")
        credit_floor=Decimal("1")
        minimum_credit=Decimal(bounds["lifetime_cost_bound_usd"])+Decimal(bounds["nonproject_credit_reserve_usd"])+credit_floor
        available_credit=min(money(ledger["reported_credit_balance_usd"],"ledger credit"),money(access.get("financial_fields",{}).get("credit"),"fresh account credit"))
        if available_credit<minimum_credit:raise ValueError("shared credit cannot fund quoted lifetime plus account guard floor")
        bounds.update(max_hourly_rate_usd=str(hourly_limit),minimum_credit_including_guard_usd=str(minimum_credit),account_credit_floor_usd=str(credit_floor))
        write(out/"quote.json",dict(quote,**bounds,offer={k:offer[k] for k in SAFE_OFFER if k in offer},
              image=args.image,environment_sha256=sha(environment),payload_sha256=sha(payload),at_epoch=time.time()))
        # The key never leaves WSL. Only this run's public SSH key is uploaded.
        private=Path.home()/".config/spectrans-3d";private.mkdir(exist_ok=True);private.chmod(0o700)
        key=private/("refinement-"+uuid.uuid4().hex+".key")
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
        public=key.with_name(key.name+".pub").read_text().strip()
        started=time.time()
        state=dict(mode="vast",controller_pid=os.getpid(),controller_birth=birth(os.getpid()),owned_children=[],
           started_epoch=started,deadline_epoch=started+bounds["lifetime_seconds"]-60,
           provisioning_authorized=True,approval_note=ledger["autonomous_authorization"]["user_instruction"],
           label="SpectraNS-3D-v3-refinement-"+uuid.uuid4().hex[:12],instance_id=None,
           account_context=account_context,account_credit_floor_usd=1.0,
           ssh_key_path=str(key),known_hosts=str(private/"refinement-known-hosts"),phase="prepared")
        write(out/"controller_state.json",state)
        with (out/"guard.log").open("x") as f:
            guard=subprocess.Popen([sys.executable,str(ROOT/"scripts/refinement_guard.py"),"--directory",str(out)],
                        cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        for _ in range(400):
            if (out/"guard_ready.json").exists():break
            if guard.poll() is not None:raise ValueError("guard failed before create")
            time.sleep(.05)
        else:raise TimeoutError("guard did not arm")
        authorization=dict(allowed_grids=[640],source_sha256=verify_audited_sources(),fingerprint=fingerprint(ROOT),
          provisioning_authorized=True,approval_note=state["approval_note"],guard_armed=True,
          cap_usd=5,lifetime_seconds=bounds["lifetime_seconds"],reserve_usd=.5,
          plan_sha256=sha(ROOT/"configs/n640_refinement_proposal.json"),instance_id=None,
          started_epoch=started,deadline_epoch=state["deadline_epoch"])
        backend=VastBackend(out,state,authorization)
        ledger["other_committed_project_spend_usd"]=5;write(ledger_path,ledger);write(out/"budget_reserved.json",ledger)
        try:
            body=dict(image=args.image,label=state["label"],disk=DISK_GB,runtype="ssh",target_state="running",cancel_unavail=True,
              onstart='mkdir -p /root/.ssh && chmod 700 /root/.ssh && printf "%s\\n" '+shlex.quote(public)+' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys')
            write(out/"create_request.json",body)
            response=api("PUT",f"/api/v0/asks/{args.offer_id}/",body);identity=response.get("new_contract")
            if type(identity)is not int or identity<=0:raise ValueError("ambiguous create response; guard tracks exact label")
            state["instance_id"]=identity;authorization["instance_id"]=identity
            write(out/"controller_state.json",state);write(out/"authorization.json",authorization)
            write(out/"ssh_attach_receipt.json",attach_owned_ssh(state,public))
            while True:
                backend.remaining(120);row=owned_instance(state)
                if row and row.get("ssh_host") and row.get("ssh_port"):
                    host=row["ssh_host"];port=int(row["ssh_port"])
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*",host) or not 0<port<65536:raise ValueError("malformed SSH endpoint")
                    state.update(ssh_host=host,ssh_port=port);write(out/"controller_state.json",state)
                    backend.connection=["ssh","-p",str(port),"-i",str(key),"-o","BatchMode=yes","-o","ConnectTimeout=10",
                      "-o","StrictHostKeyChecking=accept-new","-o","UserKnownHostsFile="+state["known_hosts"],"root@"+host]
                    try:backend.remote("true",timeout=15);break
                    except (subprocess.TimeoutExpired,subprocess.CalledProcessError):pass
                time.sleep(5)
            backend.remote("mkdir -p "+REMOTE+"/env "+PROJECT)
            backend.copy(environment,REMOTE+"/environment.tar.gz");backend.copy(payload,REMOTE+"/source.tar")
            commands=[
             "echo "+sha(environment)+" "+REMOTE+"/environment.tar.gz | sha256sum -c -",
             "echo "+sha(payload)+" "+REMOTE+"/source.tar | sha256sum -c -",
             "tar -xzf "+REMOTE+"/environment.tar.gz -C "+REMOTE+"/env",
             "tar -xf "+REMOTE+"/source.tar -C "+PROJECT,
             PYTHON+" "+REMOTE+"/env/bin/conda-unpack","cd "+PROJECT,
             "PIP_NO_CACHE_DIR=1 "+PYTHON+" -m pip install --no-deps --index-url https://download.pytorch.org/whl/cu130 torch==2.13.0+cu130",
             "PIP_NO_CACHE_DIR=1 "+PYTHON+" -m pip install --no-deps -r requirements-linux-64.lock",
             "PIP_NO_CACHE_DIR=1 "+PYTHON+" -m pip install --no-deps --no-build-isolation -e .",
             PYTHON+" -m pip check","mkdir -p "+WORK,
             PYTHON+" scripts/verify_runtime.py --output "+WORK+"/runtime_packages.json"]
            backend.remote(" && ".join(commands),"setup.log")
            result=run(out,backend,"production")
        except Exception as exc:
            result=dict(status="incomplete",error=type(exc).__name__+": "+str(exc),protected_validated=False)
            write(out/"campaign_error.json",result);write(out/"termination.json",backend.close())
        termination=json.loads((out/"termination.json").read_text())
        if termination.get("verified"):close_budget(out)
        return 0 if result.get("protected_validated") and termination.get("verified") else 2

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--execute",action="store_true")
    for name in ("job-dir","rehearsal","environment","payload","image","bootstrap-validation"):p.add_argument("--"+name)
    p.add_argument("--offer-id",type=int);p.add_argument("--account-context")
    p.add_argument("--max-hourly-rate",default=MAX_HOURLY_USD,help="Optional tighter fresh-quote ceiling; cannot exceed fixed policy")
    a=p.parse_args()
    if not a.execute:print((ROOT/"configs/n640_refinement_proposal.json").read_text());return 0
    if any(getattr(a,n) is None for n in ("job_dir","rehearsal","environment","payload","image","bootstrap_validation","offer_id")):
        p.error("all execution bindings required")
    return execute(a)
if __name__=="__main__":raise SystemExit(main())
