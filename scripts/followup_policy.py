"""Fixed N512 timestep-refinement authority; smoke restrictions remain unchanged."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from cloud_policy import ROOT, AUDITED_SOURCES, money, utc, verify_audited_sources, execution_fingerprint

PLAN_PATH = ROOT/'configs/timestep_followup.json'

def plan():
    return json.loads(PLAN_PATH.read_text())

def fingerprint():
    result = execution_fingerprint()
    for name in ('configs/timestep_followup.json', 'configs/followup_smoke_evidence.json'):
        result[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return dict(sorted(result.items()))

def validate_prerequisite():
    proof = json.loads((ROOT/'configs/followup_smoke_evidence.json').read_text())
    if (proof.get('compute_status') != 'passed' or proof.get('reference_status') != 'passed'
            or proof.get('termination_verified') is not True
            or proof.get('artifact_manifest_verified') is not True
            or proof.get('source_sha256') != verify_audited_sources()
            or proof.get('completed_runs') != 8 or proof.get('reference_checks') != 8
            or proof.get('tests_passed', 0) < 76
            or proof.get('acceptance_sha256') != hashlib.sha256((ROOT/'configs/h100_acceptance.json').read_bytes()).hexdigest()):
        raise ValueError('completed audited CPU/H100 and N128/N256 validation is required')
    return proof

def validate_budget(ledger, approval):
    if money(ledger.get('total_ceiling_usd'), 'ceiling') != Decimal('30'):
        raise ValueError('hard project ceiling must remain $30')
    if not (ledger.get('verified_prior_spend') is True and ledger.get('evidence')
            and ledger.get('project_instance_list_complete') is True):
        raise ValueError('complete reconciled project spending is required')
    prior = money(ledger.get('prior_spend_usd'), 'prior')
    pending = money(ledger.get('pending_charges_upper_bound_usd'), 'pending')
    committed = money(ledger.get('other_committed_project_spend_usd'), 'committed')
    cap = money(approval.get('max_additional_usd'), 'cap')
    rate = money(approval.get('hourly_rate_usd'), 'rate')
    reserve = money(approval.get('noncompute_cost_reserve_usd'), 'reserve')
    wall = approval.get('max_instance_wall_seconds')
    if not (cap == Decimal('8') and 0 < rate <= Decimal('3') and reserve >= Decimal('.5')
            and type(wall) is int and 0 < wall <= 9000):
        raise ValueError('follow-up requires $8 cap, <=$3/hour, >=$0.50 reserve, <=9000s')
    if not approval.get('quoted_costs_verified') or not approval.get('cost_quote_evidence'):
        raise ValueError('verified quote evidence is required')
    bound = rate * Decimal(wall)/Decimal(3600) + reserve
    if bound > cap or prior + pending + committed + cap > Decimal('30'):
        raise ValueError('financial exposure exceeds the authorized budget')
    if cap > money(ledger.get('reported_credit_balance_usd'), 'available credit'):
        raise ValueError('insufficient available credit')
    verified = utc(ledger['verified_as_of_utc'])
    if not 0 <= (datetime.now(timezone.utc)-verified).total_seconds() <= 3600:
        raise ValueError('follow-up billing reconciliation must be within one hour')
    return dict(prior_spend_usd=str(prior), pending_upper_bound_usd=str(pending),
                approved_new_cap_usd=str(cap), project_total_exposure_usd=str(prior+pending+committed+cap),
                lifetime_cost_bound_usd=str(bound))

def validate_execution(ledger_path, approval, now=None):
    verify_audited_sources()
    validate_prerequisite()
    raw = Path(ledger_path).read_bytes()
    ledger = json.loads(raw)
    if not approval.get('approved') or not approval.get('approval_note'):
        raise ValueError('recorded user authorization is required')
    if (approval.get('campaign_kind') != 'timestep_followup'
            or approval.get('allowed_grids') != [256,512]
            or approval.get('source_sha256') != AUDITED_SOURCES
            or approval.get('execution_sha256') != fingerprint()
            or approval.get('budget_ledger_sha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('follow-up must bind the fixed experiment, execution sources and ledger')
    summary = validate_budget(ledger, approval)
    if type(approval.get('instance_id')) is not int or approval['instance_id'] <= 0:
        raise ValueError('owned provider instance required')
    if not approval.get('termination_guard_armed') or not approval.get('termination_guard_evidence'):
        raise ValueError('independent external termination guard required')
    now = datetime.now(timezone.utc) if now is None else now
    start, deadline = utc(approval['provider_started_at_utc']), utc(approval['termination_deadline_utc'])
    if not 0 < (deadline-start).total_seconds() <= approval['max_instance_wall_seconds']:
        raise ValueError('deadline exceeds approved lifetime')
    remaining = (deadline-now).total_seconds()
    if now < start or remaining <= 300:
        raise ValueError('insufficient lifetime for compute and cleanup')
    summary.update(instance_id=approval['instance_id'], compute_timeout_seconds=remaining-300,
                   termination_deadline_utc=deadline.isoformat())
    return summary
