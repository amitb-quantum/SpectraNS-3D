"""Local campaign inventory and read-only verification of provider termination."""
from datetime import datetime, timezone
import hashlib
from extension_state import sha
import json
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def inventory(directory):
    directory=Path(directory)
    result={p.relative_to(directory).as_posix():sha(p)
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name!='artifact_manifest.json'}
    (directory/'artifact_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def record_termination(campaign,snapshot,archive_evidence):
    campaign=Path(campaign)
    path=campaign/'termination.json'
    previous=json.loads(path.read_text())
    instance_id=previous['instance_id']
    snapshot=Path(snapshot)
    data=json.loads(snapshot.read_text())
    if (data.get('mode')!='read-only' or data.get('provider_queries_performed') is not True
            or data.get('instance_listing_complete') is not True or not isinstance(data.get('instances'),list)):
        raise ValueError('termination needs a successful complete provider instance-list snapshot')
    checked=datetime.fromisoformat(data['as_of_utc'].replace('Z','+00:00'))
    ended=datetime.fromisoformat(previous['compute_ended_at_utc'].replace('Z','+00:00'))
    if checked.tzinfo is None or ended.tzinfo is None or checked<ended:
        raise ValueError('provider snapshot must be taken after compute ended')
    age=(datetime.now(timezone.utc)-checked).total_seconds()
    if not -60<=age<=300:
        raise ValueError('provider termination snapshot must be fresh (within five minutes)')
    if any(r.get('id')==instance_id for r in data['instances']):
        raise ValueError('instance still exists; stopped instances can continue charging storage')
    if not archive_evidence:
        raise ValueError('downloaded artifact evidence must be recorded before closing lifecycle')
    inventory_path=campaign/'artifact_manifest.json'
    expected=json.loads(inventory_path.read_text())
    for name,digest in expected.items():
        if name=='termination.json':
            continue  # this is the record being advanced
        p=(campaign/name).resolve()
        if not p.is_relative_to(campaign.resolve()) or sha(p)!=digest:
            raise ValueError('downloaded artifact manifest verification failed')
    record=dict(previous,status='provider_destruction_verified',verified_at_utc=utc_now(),
                provider_snapshot_sha256=sha(snapshot),
                provider_snapshot_as_of_utc=data['as_of_utc'],artifact_download_evidence=archive_evidence,
                final_charge_reconciliation='pending until final provider charges are included in project ledger')
    # Preserve the pending record as immutable evidence before advancing it.
    prior=campaign/'termination.pending.json'
    if not prior.exists():
        prior.write_bytes(path.read_bytes())
    path.write_text(json.dumps(record,indent=2)+'\n')
    inventory(campaign)
    return record
