"""Fixed $4 N512 extension authority, separate from completed campaigns."""
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json
from pathlib import Path
from cloud_policy import ROOT,AUDITED_SOURCES,money,utc,verify_audited_sources,execution_fingerprint
from followup_policy import validate_prerequisite

PLAN_PATH=ROOT/'configs/enstrophy_extension.json'
def plan():return json.loads(PLAN_PATH.read_text())
def fingerprint():
    d=execution_fingerprint()
    for n in ('configs/enstrophy_extension.json','configs/extension_baseline.json','configs/followup_smoke_evidence.json'):
        d[n]=hashlib.sha256((ROOT/n).read_bytes()).hexdigest()
    return dict(sorted(d.items()))
def prerequisite():
    validate_prerequisite()
    d=json.loads((ROOT/'configs/extension_baseline.json').read_text())
    if d.get('status')!='passed' or not d.get('termination_verified') or not d.get('artifacts_verified') or d.get('source_sha256')!=verify_audited_sources() or d.get('tests_passed',0)<89:
        raise ValueError('completed audited N512 timestep campaign required')
    return d
def validate_budget(ledger,a):
    if money(ledger.get('total_ceiling_usd'),'ceiling')!=Decimal('30'):raise ValueError('hard ceiling must be $30')
    if not ledger.get('verified_prior_spend') or not ledger.get('project_instance_list_complete') or not ledger.get('evidence'):
        raise ValueError('complete reconciled spending required')
    cfg=plan()
    if money(cfg.get('shared_extension_cap_usd'),'shared cap')!=Decimal('4') or cfg.get('previous_attempt_termination_verified') is not True or money(cfg.get('previous_attempt_cost_upper_usd'),'previous attempt')+Decimal('3')>Decimal('4'):
        raise ValueError('corrected retry must fit original shared $4 ceiling')
    prior=money(ledger.get('prior_spend_usd'),'prior');pending=money(ledger.get('pending_charges_upper_bound_usd'),'pending')
    committed=money(ledger.get('other_committed_project_spend_usd'),'committed')
    cap=money(a.get('max_additional_usd'),'cap');rate=money(a.get('hourly_rate_usd'),'rate');reserve=money(a.get('noncompute_cost_reserve_usd'),'reserve')
    wall=a.get('max_instance_wall_seconds')
    if cap!=Decimal('3') or not 0<rate<=Decimal('2.1') or reserve<Decimal('.5') or type(wall)is not int or not 0<wall<=4200:
        raise ValueError('corrected extension requires $3 cap, <=$2.10/hour, >=$0.50 reserve, <=4200s')
    if not a.get('quoted_costs_verified') or not a.get('cost_quote_evidence'):raise ValueError('verified quote required')
    bound=rate*Decimal(wall)/Decimal(3600)+reserve
    if bound>cap or prior+pending+committed+cap>Decimal('30'):raise ValueError('financial exposure exceeds ceiling')
    if cap>money(ledger.get('reported_credit_balance_usd'),'credit'):raise ValueError('insufficient credit')
    age=(datetime.now(timezone.utc)-utc(ledger['verified_as_of_utc'])).total_seconds()
    if not 0<=age<=3600:raise ValueError('billing must be within one hour')
    return dict(project_total_exposure_usd=str(prior+pending+committed+cap),lifetime_cost_bound_usd=str(bound),approved_new_cap_usd='3')
def validate_execution(path,a):
    verify_audited_sources();prerequisite()
    raw=Path(path).read_bytes();ledger=json.loads(raw)
    if not a.get('approved') or not a.get('approval_note'):raise ValueError('recorded user authorization required')
    if a.get('campaign_kind')!='enstrophy_extension' or a.get('allowed_grids')!=[512] or a.get('source_sha256')!=AUDITED_SOURCES or a.get('execution_sha256')!=fingerprint() or a.get('budget_ledger_sha256')!=hashlib.sha256(raw).hexdigest():
        raise ValueError('fixed extension source/config/ledger binding required')
    d=validate_budget(ledger,a)
    if type(a.get('instance_id'))is not int or a['instance_id']<=0 or not a.get('termination_guard_armed') or not a.get('termination_guard_evidence'):
        raise ValueError('owned instance and armed external guard required')
    start=utc(a['provider_started_at_utc']);end=utc(a['termination_deadline_utc']);now=datetime.now(timezone.utc)
    if not 0<(end-start).total_seconds()<=a['max_instance_wall_seconds'] or now<start or (end-now).total_seconds()<=1200:
        raise ValueError('invalid deadline or insufficient lifetime')
    return dict(d,instance_id=a['instance_id'],compute_timeout_seconds=(end-now).total_seconds()-600)
