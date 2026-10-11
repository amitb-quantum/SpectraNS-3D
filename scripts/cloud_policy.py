"""Fail-closed financial and source controls for already-approved smoke runs."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from ns_fast_v3 import source_hashes


TOTAL_CEILING = Decimal('30')
ROOT = Path(__file__).resolve().parents[1]
AUDITED_SOURCES = {
    'ns_fast_v2.py': '6f01107b931b80231e27336faeae94b51916d91861473f46e85aedbba0bdaf5d',
    'ns_fast_v3.py': 'ab9eebda2750c7be019d3c2f54fe7aa5f2be98a0276a55260e35a81989b34842',
}


def money(value, name):
    if value is None or isinstance(value, bool):
        raise ValueError(f'{name} must be a reconciled number, not missing/boolean')
    try:
        result = Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError(f'{name} is not numeric') from e
    if not result.is_finite() or result < 0:
        raise ValueError(f'{name} must be finite and nonnegative')
    return result


def utc(value):
    if not isinstance(value, str):
        raise ValueError('timestamps must be strings with UTC offsets')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps must have UTC offsets')
    return result.astimezone(timezone.utc)


def verify_audited_sources():
    current = source_hashes()
    if current != AUDITED_SOURCES:
        raise ValueError('candidate core no longer matches audited sources; re-audit before cloud use')
    return current


def execution_fingerprint():
    names=['configs/h100_acceptance.json']
    names.extend(p.relative_to(ROOT).as_posix() for folder in ('src','scripts','tests')
                 for p in sorted((ROOT/folder).rglob('*.py')) if '__pycache__' not in p.parts)
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names)}


def validate_budget(ledger, approval):
    if money(ledger.get('total_ceiling_usd'), 'total ceiling') != TOTAL_CEILING:
        raise ValueError('the hard total project ceiling is $30')
    if ledger.get('verified_prior_spend') is not True or not ledger.get('evidence'):
        raise ValueError('exact previous expenditure must be reconciled with evidence')
    if ledger.get('project_instance_list_complete') is not True:
        raise ValueError('the project instance/charge inventory is incomplete')
    prior = money(ledger.get('prior_spend_usd'), 'previous spending')
    pending = money(ledger.get('pending_charges_upper_bound_usd'), 'pending charges')
    committed = money(ledger.get('other_committed_project_spend_usd'), 'other commitments')
    cap = money(approval.get('max_additional_usd'), 'new all-in cap')
    rate = money(approval.get('hourly_rate_usd'), 'GPU plus disk hourly rate')
    reserve = money(approval.get('noncompute_cost_reserve_usd'), 'transfer/cleanup reserve')
    if approval.get('quoted_costs_verified') is not True or not approval.get('cost_quote_evidence'):
        raise ValueError('GPU/disk and transfer/cleanup cost bounds require verified quote evidence')
    wall = approval.get('max_instance_wall_seconds')
    if not isinstance(wall, int) or isinstance(wall, bool) or not 0 < wall <= 1200:
        raise ValueError('smoke rental lifetime must be <=1200 seconds including setup and cleanup')
    if not 0 < cap < Decimal('10') or not 0 < rate <= Decimal('4') or reserve < Decimal('.25'):
        raise ValueError('user-approved autonomous cap must be <$10, hourly rate <=$4, reserve >=$0.25')
    bound = rate * Decimal(wall) / Decimal(3600) + reserve
    if bound > cap:
        raise ValueError('worst-case rental duration plus noncompute reserve exceeds approved cap')
    if prior + pending + committed + cap > TOTAL_CEILING:
        raise ValueError('new commitment would exceed the $30 project ceiling')
    # Balance is an additional funding check, never a substitute for spend.
    if ledger.get('reported_credit_balance_usd') is not None:
        if cap > money(ledger['reported_credit_balance_usd'], 'available credit'):
            raise ValueError('available credit is below the proposed commitment')
    return dict(prior_spend_usd=str(prior), pending_upper_bound_usd=str(pending),
                other_committed_usd=str(committed), approved_new_cap_usd=str(cap),
                project_total_exposure_usd=str(prior+pending+committed+cap),
                lifetime_cost_bound_usd=str(bound))


def validate_execution(ledger_path, approval, now=None):
    verify_audited_sources()
    raw = Path(ledger_path).read_bytes()
    ledger = json.loads(raw)
    if approval.get('approved') is not True or not approval.get('approval_note'):
        raise ValueError('actual user approval is required')
    if approval.get('source_sha256') != AUDITED_SOURCES or approval.get('allowed_grids') != [128, 256]:
        raise ValueError('approval must name the audited core and only N128/N256')
    if approval.get('execution_sha256') != execution_fingerprint():
        raise ValueError('approval must bind the complete execution sources, tests and numerical criteria')
    if approval.get('budget_ledger_sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('approval is not bound to the current budget ledger')
    summary = validate_budget(ledger, approval)
    if type(approval.get('instance_id')) is not int or approval['instance_id'] <= 0:
        raise ValueError('the approved existing provider instance ID is required')
    if approval.get('termination_guard_armed') is not True or not approval.get('termination_guard_evidence'):
        raise ValueError('an external provider termination guard must be armed before compute')
    now = datetime.now(timezone.utc) if now is None else now
    verified = utc(ledger['verified_as_of_utc'])
    if not 0 <= (now-verified).total_seconds() <= 86400:
        raise ValueError('spending reconciliation must be at most 24 hours old')
    started = utc(approval['provider_started_at_utc'])
    deadline = utc(approval['termination_deadline_utc'])
    lifetime = (deadline-started).total_seconds()
    if not 0 < lifetime <= approval['max_instance_wall_seconds']:
        raise ValueError('termination deadline exceeds the approved provider lifetime')
    remaining = (deadline-now).total_seconds()
    if now < started or remaining <= 120:
        raise ValueError('provider lifetime expired or insufficient cleanup time remains')
    summary.update(instance_id=approval['instance_id'], termination_deadline_utc=deadline.isoformat(),
                   compute_timeout_seconds=remaining-120)
    return summary
