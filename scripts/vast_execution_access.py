#!/usr/bin/env python3
"""Read only the current credential's execution permissions; emit no secrets."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

from vast_readonly import BASE,KEYFILE,NoRedirect,read_key


def read(path,key):
    if path not in ('/api/v0/users/current/','/api/v0/auth/apikeys/'):
        raise ValueError('metadata endpoint not allowed')
    req=urllib.request.Request(BASE+path,headers={'Authorization':'Bearer '+key},method='GET')
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise ValueError(f'Credential metadata access failed with HTTP {e.code}') from None


def inspect():
    key=read_key(KEYFILE)
    if not key: raise ValueError('credential not configured')
    user=read('/api/v0/users/current/',key)
    keys=read('/api/v0/auth/apikeys/',key)
    matches=[row for row in keys.get('apikeys',[]) if row.get('id')==user.get('key_id')]
    if len(matches)!=1:
        raise ValueError('could not identify current key permissions')
    rights=matches[0].get('rights',matches[0].get('permissions',matches[0].get('params')))
    if rights is None:
        rights=user.get('rights')
    if isinstance(rights,str):
        try: rights=json.loads(rights)
        except ValueError: pass
    api=rights.get('api',{}) if isinstance(rights,dict) else {}
    result=dict(as_of_utc=datetime.now(timezone.utc).isoformat(),mode='read-only',
                current_key_identified=True,permission_categories=sorted(api),
                is_account_master_key=user.get('api_key')==key,
                key_type=matches[0].get('key_type'),rights_id=matches[0].get('rights_id'),
                broad_instance_write='instance_write' in api and api['instance_write']=={},
                named_role=rights if isinstance(rights,(str,int)) and len(str(rights))<80 and rights!=key else None,
                rights_type=type(rights).__name__,
                rights_top_level_keys=sorted(rights) if isinstance(rights,dict) else [],
                financial_fields={name:user[name] for name in ('balance','credit','credit_balance','balance_usd')
                                  if name in user and isinstance(user[name],(int,float))})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    a=p.parse_args()
    try:
        result=inspect()
        with Path(a.output).open('x') as f: json.dump(result,f,indent=2);f.write('\n')
        print(json.dumps(result,indent=2))
    except (ValueError,OSError) as e:
        raise SystemExit(str(e))
