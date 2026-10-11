"""Narrow API for one authorized smoke rental and its destruction."""
import json
import re
import urllib.error
import urllib.request

from vast_readonly import BASE,KEYFILE,NoRedirect,read_key,pages,SAFE_INSTANCE


def api(method,path,body=None):
    allowed=((method=='PUT' and re.fullmatch(r'/api/v0/asks/[1-9][0-9]*/',path)) or
             (method=='POST' and re.fullmatch(r'/api/v0/instances/[1-9][0-9]*/ssh/',path)) or
             (method=='DELETE' and re.fullmatch(r'/api/v0/instances/[1-9][0-9]*/',path)))
    if not allowed: raise ValueError('campaign API endpoint refused')
    key=read_key(KEYFILE)
    if not key: raise ValueError('credential missing')
    req=urllib.request.Request(BASE+path,method=method,
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response:
            result=json.load(response)
    except urllib.error.HTTPError as e:
        raise ValueError(f'Campaign API HTTP {e.code}') from None
    if not isinstance(result,dict) or result.get('success') is False:
        raise ValueError('Campaign API returned an unsuccessful response')
    return result


def instances():
    key=read_key(KEYFILE)
    if not key: raise ValueError('credential missing')
    return pages('/api/v1/instances',key,'instances')


def owned_instance(state):
    matches=[r for r in instances() if r.get('label')==state['label']]
    if len(matches)>1: raise ValueError('ambiguous campaign ownership')
    if not matches: return None
    row=matches[0]
    if state.get('instance_id') is not None and row['id']!=state['instance_id']:
        raise ValueError('instance ID does not match campaign ownership')
    return row


def destroy_owned(state):
    row=owned_instance(state)
    if row is None: return dict(already_absent=True)
    if not state.get('provisioning_authorized') or not state.get('approval_note'):
        raise ValueError('destruction needs recorded campaign authorization')
    result=api('DELETE',f'/api/v0/instances/{row["id"]}/')
    return dict(instance_id=row['id'],success=result.get('success',True))


def attach_owned_ssh(state,public_key):
    row=owned_instance(state)
    if not row or not state.get('provisioning_authorized') or not public_key.startswith('ssh-ed25519 '):
        raise ValueError('SSH attachment requires the owned authorized instance and public key')
    result=api('POST',f'/api/v0/instances/{row["id"]}/ssh/',{'ssh_key':public_key})
    return dict(instance_id=row['id'],success=result.get('success',True))
