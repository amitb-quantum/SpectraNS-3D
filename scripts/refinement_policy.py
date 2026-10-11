"""Dedicated N640 authority; never loosens the earlier N128/N256 or N512 launchers."""
import json,math
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from cloud_policy import ROOT,money,utc,verify_audited_sources
from extension_state import sha
from refinement_io import fingerprint
from refinement_capacity import DISK_GB,MAX_HOURLY_USD

def validate_rehearsal(path):
    r=json.loads(Path(path).read_text())
    names={c["name"] for c in r.get("cases",[]) if c.get("status")=="passed"}
    needed={"success_overlap","success_sequential","kill_coarse","kill_fine","kill_protected_collection","kill_checkpoint_collection","kill_exploration","success_cuda"}
    if r.get("status")!="passed" or r.get("provider_calls")!=0 or not needed<=names or r.get("fingerprint")!=fingerprint(ROOT):
        raise ValueError("current source/config-bound complete CPU/CUDA kill rehearsals required")
    return r

def validate_quote(offer):
    required=("id","gpu_name","gpu_ram","num_gpus","dph_total","storage_cost","inet_up_cost","inet_down_cost",
              "reliability2","verification","cuda_max_good","cpu_arch","cpu_cores_effective","cpu_ram","disk_space")
    if any(k not in offer for k in required):raise ValueError("incomplete provider quote")
    for k in ("gpu_ram","dph_total","storage_cost","inet_up_cost","inet_down_cost","reliability2",
              "cuda_max_good","cpu_cores_effective","cpu_ram","disk_space"):
        if isinstance(offer[k],bool) or not math.isfinite(float(offer[k])) or float(offer[k])<0:raise ValueError("invalid quote value")
    if type(offer["id"])is not int or offer["id"]<=0 or "H100" not in offer["gpu_name"] or offer["num_gpus"]!=1 or offer["gpu_ram"]<80000 or offer["cuda_max_good"]<13 or offer["cpu_arch"]!="amd64" or offer["cpu_cores_effective"]<4 or offer["cpu_ram"]<16000 or offer["disk_space"]<DISK_GB or offer["verification"]!="verified" or offer["reliability2"]<.99:
        raise ValueError("offer does not meet fixed H100 requirements")
    rate=Decimal(str(offer["dph_total"]))+DISK_GB*Decimal(str(offer["storage_cost"]))/720
    transfer=14*Decimal(str(offer["inet_down_cost"]))+Decimal("8.25")*Decimal(str(offer["inet_up_cost"]))
    if not 0<rate<=Decimal(MAX_HOURLY_USD) or transfer>Decimal(".5"):raise ValueError("offer exceeds hourly or noncompute reserve")
    return dict(rate_usd=str(rate),transfer_upper_usd=str(transfer))

def validate_budget(ledger,quote,now=None):
    now=now or datetime.now(timezone.utc)
    if money(ledger.get("total_ceiling_usd"),"ceiling")!=Decimal("30") or not ledger.get("verified_prior_spend") or not ledger.get("project_instance_list_complete") or not ledger.get("evidence"):
        raise ValueError("complete USD30 reconciliation required")
    age=(now-utc(ledger["verified_as_of_utc"])).total_seconds()
    if not 0<=age<=3600:raise ValueError("fresh billing required")
    authority=ledger.get("autonomous_authorization",{})
    if authority.get("authorized") is not True or money(authority.get("exclusive_additional_cap_usd"),"authority")<=Decimal("5"):
        raise ValueError("standing user authorization missing")
    total=sum((money(ledger.get(k),k) for k in ("prior_spend_usd","pending_charges_upper_bound_usd","other_committed_project_spend_usd")),Decimal("0"))
    if total+5>30 or money(ledger.get("reported_credit_balance_usd"),"credit")<5:raise ValueError("USD5 commitment does not fit budget/credit")
    rate=money(quote["rate_usd"],"rate")
    if not 0<rate<=Decimal(MAX_HOURLY_USD):raise ValueError("hourly bound exceeded")
    from refinement_review import lifetime_seconds
    lifetime=lifetime_seconds(rate)
    return dict(cap_usd=5,project_exposure_usd=str(total+5),lifetime_seconds=lifetime,
                lifetime_cost_bound_usd=str(rate*Decimal(lifetime)/3600+Decimal(".5")))

def validate_production_request(cfg):
    a=cfg.get("authorization")
    if not isinstance(a,dict) or a.get("allowed_grids")!=[640] or a.get("source_sha256")!=verify_audited_sources() or a.get("fingerprint")!=fingerprint(ROOT):
        raise ValueError("production source/authority binding missing")
    if a.get("provisioning_authorized") is not True or not a.get("approval_note") or not a.get("guard_armed") or type(a.get("instance_id"))is not int:
        raise ValueError("owned instance and armed provider guard required")
    if a.get("cap_usd")!=5 or not 0<a.get("lifetime_seconds",0)<=7200 or a.get("reserve_usd")!=.5:
        raise ValueError("production spending guard mismatch")
    if a.get("plan_sha256")!=sha(ROOT/"configs/n640_refinement_proposal.json"):raise ValueError("plan mismatch")
    if cfg.get("provider_deadline_epoch")!=a.get("deadline_epoch") or not 0<a.get("deadline_epoch",0)-a.get("started_epoch",0)<=a["lifetime_seconds"]:
        raise ValueError("provider deadline binding mismatch")
    if cfg.get("rehearsal_pause_s"):raise ValueError("rehearsal hooks forbidden")
    return a

def offer_query():
    # Provider API names use spaces; underscores are CLI presentation aliases.
    return dict(limit=50,type="on-demand",gpu_name={"in":["H100 SXM","H100 PCIE","H100 NVL"]},
        num_gpus={"eq":1},verified={"eq":True},rentable={"eq":True},rented={"eq":False},
        reliability2={"gte":.99},cuda_max_good={"gte":13},disk_space={"gte":DISK_GB},
        gpu_ram={"gte":80000},cpu_arch={"eq":"amd64"},cpu_cores_effective={"gte":4},
        cpu_ram={"gte":16000},dph_total={"lte":float(MAX_HOURLY_USD)},order=[["dph_total","asc"]])
