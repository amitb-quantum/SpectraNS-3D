#!/usr/bin/env python3
"""Independent local guard: destroy only its named campaign at deadline."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time

from cloud_policy import utc
from cloud_records import utc_now
from vast_campaign_api import destroy_owned,owned_instance


def alive(pid):
    try: os.kill(pid,0);return True
    except ProcessLookupError: return False


def guard(directory):
    directory=Path(directory)
    state_path=directory/'controller_state.json'
    initial=json.loads(state_path.read_text())
    if not initial.get('provisioning_authorized') or not initial.get('label','').startswith('SpectraNS-3D-v3-extension-'):
        raise ValueError('guard refuses unapproved campaign')
    if (utc(initial['termination_deadline_utc'])-utc(initial['provider_started_at_utc'])).total_seconds()>4200:
        raise ValueError('extension guard lifetime exceeds 4200s')
    (directory/'guard_ready.json').write_text(json.dumps(dict(pid=os.getpid(),ready_at_utc=utc_now()))+'\n')
    while True:
        state=json.loads(state_path.read_text())
        if state.get('termination_verified'): return 0
        now=datetime.now(timezone.utc)
        (directory/'guard_heartbeat.json').write_text(json.dumps(dict(pid=os.getpid(),at_utc=utc_now()))+'\n')
        if now>=utc(initial['termination_deadline_utc']) or not alive(initial['controller_pid']):
            try:
                receipt=destroy_owned(initial)
                (directory/'guard_destroy_receipt.json').write_text(json.dumps(dict(receipt,at_utc=utc_now()))+'\n')
                if owned_instance(initial) is None: return 0
            except Exception as e:
                (directory/'guard_error.json').write_text(json.dumps(dict(type=type(e).__name__,at_utc=utc_now()))+'\n')
        time.sleep(5)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',required=True)
    raise SystemExit(guard(p.parse_args().directory))
