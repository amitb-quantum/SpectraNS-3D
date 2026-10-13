"""Exact user-attributed nonproject rentals and shared-account credit protection.

No instance mutations. Unknown identities and project identities fail closed.
The runtime estimate reserves credit; an independent balance guard handles overruns.
"""
import math
from decimal import Decimal

def account_instances(snapshot, project_ids, context=None):
    if not snapshot.get("instance_listing_complete"):
        raise ValueError("complete account instance listing required")
    context = context or {"nonproject_instances": []}
    entries = context.get("nonproject_instances")
    if not isinstance(entries, list):
        raise ValueError("invalid nonproject account context")
    known = {}
    for entry in entries:
        identity = entry.get("id")
        hours = entry.get("remaining_seconds")
        if type(identity) is not int or identity <= 0 or identity in known or identity in project_ids:
            raise ValueError("nonproject identity invalid, duplicated or belongs to project")
        if not isinstance(entry.get("label"), str) or not entry["label"] or not entry.get("user_attribution"):
            raise ValueError("explicit user-attributed exact nonproject label required")
        if type(hours) is not int or not 0 < hours <= 7200:
            raise ValueError("nonproject remaining-runtime estimate required")
        known[identity] = entry
    records = []
    total = Decimal("0")
    seen = set()
    for row in snapshot["instances"]:
        identity = row.get("id")
        if identity in seen or identity in project_ids:
            raise ValueError("active project or duplicate account instance")
        seen.add(identity)
        if identity not in known or row.get("label") != known[identity]["label"]:
            raise ValueError("active account instance not exactly attributed")
        # Account rentals can charge storage even while stopped. Include every
        # listed contract, never assume its state makes it free.
        costs = []
        for field in ("dph_total", "storage_total_cost"):
            value = row.get(field)
            if isinstance(value, bool) or value is None or not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError("nonproject hourly costs unavailable")
            costs.append(Decimal(str(value)))
        rate = sum(costs, Decimal("0"))
        reserve = rate * known[identity]["remaining_seconds"] / Decimal("3600")
        total += reserve
        records.append(dict(id=identity, label=row["label"],
            hourly_upper_usd=str(rate), remaining_seconds=known[identity]["remaining_seconds"],
            credit_reserve_usd=str(reserve), attribution=known[identity]["user_attribution"]))
    return dict(nonproject_instances=records, nonproject_credit_reserve_usd=str(total),
                project_instances_active=0, account_instances_active=len(records))

def credit_floor_reason(credit, minimum=1.0):
    if isinstance(credit, bool) or credit is None or not math.isfinite(float(credit)):
        return "account_credit_unavailable"
    return "account_credit_low" if float(credit) <= minimum else None

def read_account_credit():
    # The response and credential stay internal. Return only numeric credit.
    from vast_readonly import read_key, KEYFILE
    from vast_execution_access import read
    key = read_key(KEYFILE)
    if not key:
        raise ValueError("local credential unavailable")
    user = read("/api/v0/users/current/", key)
    value = user.get("credit")
    if credit_floor_reason(value) == "account_credit_unavailable":
        raise ValueError("provider credit unavailable")
    return float(value)

def monitor_credit(out, state, now):
    """One read per minute; failed reads also trigger owned-instance cleanup."""
    if now < state.get("credit_next_check_epoch", 0):
        return None
    from pathlib import Path
    from refinement_guard import write
    state["credit_next_check_epoch"] = now + 60
    try:
        credit = read_account_credit()
        reason = credit_floor_reason(credit, state["account_credit_floor_usd"])
        record = dict(at_epoch=now, credit_usd=credit, minimum_usd=state["account_credit_floor_usd"], reason=reason)
    except Exception as exc:
        reason = "account_credit_unavailable"
        record = dict(at_epoch=now, reason=reason, error_kind=type(exc).__name__)
    write(Path(out)/"account_credit_watch.json", record)
    return reason
