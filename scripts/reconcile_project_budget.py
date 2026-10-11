#!/usr/bin/env python3
"""Reconcile known project parent charges using a fresh read-only provider snapshot."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from cloud_policy import ROOT
from cloud_records import utc_now
from vast_readonly import discover, read_key, KEYFILE
from vast_execution_access import inspect

def reconcile(output, campaign=None):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    key = read_key(KEYFILE)
    snapshot = discover(key)
    access = inspect()
    (output/'provider.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    (output/'access.json').write_text(json.dumps(access,indent=2)+'\n')
    ledger_path = ROOT/'configs/project_budget.json'
    raw = ledger_path.read_bytes()
    (output/'budget_before.json').write_bytes(raw)
    ledger = json.loads(raw)
    ids = set(ledger['project_instance_ids'])
    extra_pending = Decimal('0')
    if campaign:
        campaign = Path(campaign)
        state = json.loads((campaign/'controller_state.json').read_text())
        if not state.get('termination_verified') or not state.get('label','').startswith('SpectraNS-3D-v3-followup-'):
            raise ValueError('new campaign must have verified destruction before final reconciliation')
        ids.add(state['instance_id'])
        quote = json.loads((campaign/'quote.json').read_text())
        from cloud_policy import utc
        duration = (utc(state['ended_at_utc'])-utc(state['provider_started_at_utc'])).total_seconds()
        upper = min(Decimal('8'),Decimal(str(quote['conservative_hourly_upper_usd']))*Decimal(str(duration))/Decimal('3600')+Decimal('.5'))
        posted = sum((Decimal(str(row['amount'])) for row in snapshot['charges']
                      if row.get('source')=='instance-'+str(state['instance_id'])),Decimal('0'))
        extra_pending = max(Decimal('0'),upper-posted)
    if snapshot['instances']:
        raise ValueError('active account instances must be accounted for before new commitments')
    if not snapshot['charge_listing_complete'] or not snapshot['instance_listing_complete']:
        raise ValueError('provider inventories incomplete')
    total = sum((Decimal(str(row['amount'])) for row in snapshot['charges']
                 if row.get('type')=='instance' and row.get('source') in {'instance-'+str(i) for i in ids}),Decimal('0'))
    ledger.update(prior_spend_usd=float(total),verified_prior_spend=True,
                  project_instance_list_complete=True,project_instance_ids=sorted(ids),
                  verified_as_of_utc=utc_now(),
                  pending_charges_upper_bound_usd=float(Decimal('.25')+extra_pending),
                  other_committed_project_spend_usd=0,
                  reported_credit_balance_usd=access['financial_fields']['credit'])
    ledger['evidence'].append((output/'provider.json').relative_to(ROOT).as_posix())
    ledger['notes'].append('Follow-up reconciliation: '+utc_now()+'; parent project charges only; final provider posting may lag.')
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
    (output/'budget_after.json').write_bytes(ledger_path.read_bytes())
    print(json.dumps(dict(posted_project_usd=float(total),pending_upper_usd=ledger['pending_charges_upper_bound_usd'],
                          credit_usd=ledger['reported_credit_balance_usd'],active_instances=0),indent=2))
    return ledger

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--campaign')
    args=parser.parse_args()
    reconcile(args.output,args.campaign)
