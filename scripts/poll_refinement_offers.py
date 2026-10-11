#!/usr/bin/env python3
"""One read-only Vast offer poll; scheduling belongs to the attached Codex heartbeat."""
import argparse,fcntl,json,os,tempfile,uuid
from datetime import datetime,timezone
from pathlib import Path
from refinement_policy import offer_query,validate_quote
from refinement_capacity import DISK_GB,MAX_HOURLY_USD
from vast_readonly import request,read_key,KEYFILE,SAFE_OFFER

DEFAULT_OUTPUT=Path(__file__).resolve().parents[1]/"artifacts/offer-watch"

def atomic_json(path,value):
    path=Path(path)
    with tempfile.NamedTemporaryFile(mode="w",dir=path.parent,prefix="poll-",suffix=".tmp",delete=False) as f:
        json.dump(value,f,indent=2,allow_nan=False);f.write("\n");temporary=Path(f.name)
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def evaluate(response):
    if not isinstance(response,dict) or not isinstance(response.get("offers"),list):
        raise ValueError("offer response missing expected list")
    eligible=[];rejected=[]
    for row in response["offers"]:
        safe={k:row[k] for k in SAFE_OFFER if k in row}
        try:
            quote=validate_quote(safe)
            eligible.append(dict(offer=safe,quote=quote))
        except (ValueError,TypeError,OverflowError,KeyError):
            # Never echo server payloads or credentials in a rejection.
            rejected.append(dict(id=safe.get("id"),reason="hardware, price, transfer or required-field gate"))
    eligible.sort(key=lambda x:(float(x["quote"]["rate_usd"]),x["offer"]["id"]))
    return dict(eligible=eligible,rejected=rejected,returned_count=len(response["offers"]),
                possibly_truncated=len(response["offers"])>=offer_query()["limit"])

def signal(record,previous):
    if record["status"]!="completed":
        signature=("error",record["error_kind"])
        # Exception payloads are deliberately not persisted.
        return dict(signature=list(signature),alert=previous.get("signal")!=list(signature),
                    reason="new_poll_error")
    signature=["offers",[[x["offer"]["id"],round(float(x["quote"]["rate_usd"]),2),
                          round(float(x["quote"]["transfer_upper_usd"]),2)] for x in record["eligible"]]]
    changed=previous.get("signal")!=signature
    return dict(signature=signature,alert=bool(record["eligible"]) and changed,
                reason="qualifying_offer_change" if changed else "unchanged")

def poll_once(output,query_fn=request,key_fn=lambda:read_key(KEYFILE)):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    # Separate local evidence writes from provider calls; no ledger or instance mutations.
    with (output/".poll.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=output/"state.json"
        previous=json.loads(state.read_text()) if state.exists() else {}
        record=dict(mode="read-only",status="started",as_of_utc=datetime.now(timezone.utc).isoformat(),
                    provisioning_performed=False,instance_mutations_performed=False,
                    budget_mutations_performed=False,requested_disk_GB=DISK_GB,
                    max_gpu_plus_disk_hourly_usd=MAX_HOURLY_USD,
                    requires_fresh_billing_rehearsal_and_measured_preflight_before_execution=True,
                    query=offer_query())
        try:
            key=key_fn()
            if not key:raise ValueError("local credential unavailable")
            result=query_fn("POST","/api/v0/bundles",key,body=record["query"])
            record.update(evaluate(result),status="completed")
        except Exception as exc:
            record.update(status="error",error_kind=type(exc).__name__)
        note=signal(record,previous)
        record.update(alert=note["alert"],alert_reason=note["reason"])
        name=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex+".json"
        report=output/name
        with report.open("x") as f:json.dump(record,f,indent=2,allow_nan=False);f.write("\n")
        atomic_json(state,dict(signal=note["signature"],last_report=str(report),as_of_utc=record["as_of_utc"]))
        return record,report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    a=p.parse_args();record,report=poll_once(a.output)
    print(json.dumps(dict(status=record["status"],alert=record["alert"],reason=record["alert_reason"],
                         qualifying_offers=len(record.get("eligible",[])),report=str(report))))
    return 0 if record["status"]=="completed" else 2
if __name__=="__main__":raise SystemExit(main())
