#!/usr/bin/env python3
"""Vast discovery only. No instance creation, mutation, SSH execution, or deletion.

Secrets are read from a local WSL file; never passed in CLI arguments or output.
Only instance listing, billing charges and optional offer search are allowed.
"""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import stat
import urllib.error
import urllib.parse
import urllib.request


BASE = 'https://console.vast.ai'
KEYFILE = Path.home()/'.config/spectrans-3d/vast-readonly.key'
ALLOWED = {('GET','/api/v1/instances'), ('GET','/api/v0/charges'), ('POST','/api/v0/bundles')}
SAFE_INSTANCE = ('id','actual_status','cur_state','label','gpu_name','gpu_ram','num_gpus',
                 'dph_total','storage_total_cost','start_date','duration')
SAFE_OFFER = ('id','gpu_name','gpu_ram','num_gpus','dph_total','storage_cost',
              'inet_up_cost','inet_down_cost','reliability2','verification','cuda_max_good',
              'driver_version','cpu_arch','cpu_cores_effective','cpu_ram','disk_space','inet_down','inet_up')


def configure(path):
    path = Path(path).expanduser()
    if path.exists():
        raise ValueError('credential file already exists; rotate it manually if needed')
    key = getpass.getpass('Paste the restricted Vast.ai key locally (hidden input): ').strip()
    if not key:
        raise ValueError('empty key')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.parent.chmod(0o700)
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write(key+'\n')
    print(f'Credential stored locally with mode 0600: {path}')


def read_key(path):
    path=Path(path).expanduser()
    if not path.is_file():
        return None
    if os.name!='nt' and stat.S_IMODE(path.stat().st_mode)&0o077:
        raise ValueError('credential permissions must be 0600 (owner only)')
    return path.read_text().strip() or None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=urllib.parse.urlsplit(newurl)
        safe_target=urllib.parse.urlunsplit((target.scheme,target.netloc,target.path,'',''))
        raise ValueError('redirect refused to protect authorization header; target: '+safe_target)


def request(method,path,key,params=None,body=None):
    if (method,path) not in ALLOWED:
        raise ValueError('endpoint is outside read-only allowlist')
    # The live service canonicalizes these endpoints with a trailing slash.
    # Address that URL directly; never forward a credential through redirects.
    url=BASE+path+'/'
    if params:
        url+='?'+urllib.parse.urlencode(params)
    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    req=urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                               headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response:
            result=json.load(response)
    except urllib.error.HTTPError as e:
        try:
            error=json.loads(e.read(4096))
            detail='; '.join(str(error[k])[:200] for k in ('error','msg','detail')
                             if k in error and isinstance(error[k],str))
            detail=detail.replace(key,'[REDACTED]')
        except (ValueError,TypeError):
            detail=''
        raise ValueError(f'Vast read-only {path} failed with HTTP {e.code}: {detail}') from None
    if not isinstance(result,dict) or result.get('success') is False:
        raise ValueError('provider returned an unsuccessful or unexpected response')
    return result


def pages(path,key,collection,base_params=None):
    rows=[]; seen=set(); token=None
    for _ in range(100):
        params=dict(base_params or {})
        if token:
            params['after_token']=token
        result=request('GET',path,key,params=params)
        if not isinstance(result.get(collection),list):
            raise ValueError('provider pagination response missing expected collection')
        rows.extend(result[collection])
        token=result.get('next_token')
        if not token:
            return rows
        if token in seen:
            raise ValueError('provider pagination token repeated')
        seen.add(token)
    raise ValueError('provider pagination incomplete after 100 pages')


def discover(key,include_offers=False,charges_from='1970-01-01',offer_max_hourly=2,broad_hopper=False):
    start=datetime.fromisoformat(charges_from).replace(tzinfo=timezone.utc)
    end=datetime.now(timezone.utc)
    if start>end:
        raise ValueError('charge start date is in the future')
    instances=pages('/api/v1/instances',key,'instances',
                    {'select_cols':json.dumps(list(SAFE_INSTANCE))})
    # The live endpoint rejects epoch zero as a missing lower bound.
    filters={'day':{'gte':max(1,int(start.timestamp())),'lte':int(end.timestamp())}}
    charges=pages('/api/v0/charges',key,'results',
                  {'select_filters':json.dumps(filters),'format':'table','limit':500})
    result=dict(mode='read-only',as_of_utc=datetime.now(timezone.utc).isoformat(),
                status='completed',provider_queries_performed=True,instance_listing_complete=True,
                charge_listing_complete=True,
                charge_date_filter=filters,
                instances=[{k:r.get(k) for k in SAFE_INSTANCE if k in r} for r in instances],
                charges=[{k:r.get(k) for k in ('start','end','type','source','amount') if k in r} for r in charges],
                project_spend_reconciled=False,
                note='Select every project instance/volume and reconcile parent charge totals. Top-ups/credit are not expenditure.')
    if include_offers:
        query=dict(limit=50,type='on-demand',num_gpus={'eq':1},
                   verified={'eq':True},rentable={'eq':True},rented={'eq':False},
                   dph_total={'lte':offer_max_hourly},reliability2={'gte':.99},
                   order=[['dph_total','asc']])
        if broad_hopper:
            query['gpu_ram']={'gte':80000}
            query['gpu_name']={'in':['H100 SXM','H100 PCIE','H100 NVL','H200','H200 SXM','H200 NVL']}
        else:
            query['gpu_name']={'eq':'H100 SXM'}
        response=request('POST','/api/v0/bundles',key,body=query)
        offers=response.get('offers')
        if not isinstance(offers,list):
            raise ValueError('offer search response missing offers')
        result['offers']=[{k:r.get(k) for k in SAFE_OFFER if k in r} for r in offers]
        result['offer_query']=query
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--key-file',default=os.environ.get('VAST_READONLY_API_KEY_FILE',str(KEYFILE)))
    p.add_argument('--configure-key',action='store_true')
    p.add_argument('--include-offers',action='store_true')
    p.add_argument('--offer-max-hourly',type=float,default=2)
    p.add_argument('--broad-hopper',action='store_true',help='Compare single >=80GB H100/H200 variants')
    p.add_argument('--charges-from',default='1970-01-01',help='UTC date; default covers entire account history')
    p.add_argument('--output',default='artifacts/cloud-preparation/vast-discovery.json')
    a=p.parse_args()
    if a.configure_key:
        configure(a.key_file)
        return 0
    key=read_key(a.key_file)
    if key is None:
        result=dict(mode='read-only',status='credential_unavailable',provider_queries_performed=False,
                    project_spend_reconciled=False,offers_verified=False,
                    note='Configure a restricted key locally with --configure-key; no key is required in chat.')
        code=2
    else:
        result=discover(key,a.include_offers,a.charges_from,a.offer_max_hourly,a.broad_hopper);code=0
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(f'Read-only discovery status: {result.get("status","completed")}; report: {out}')
    return code


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,OSError) as e:
        raise SystemExit(str(e))
