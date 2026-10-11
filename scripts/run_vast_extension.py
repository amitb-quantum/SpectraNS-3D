#!/usr/bin/env python3
"""Execute one fixed N512 refinement campaign; always collect and destroy it."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import tarfile
import uuid

from cloud_policy import ROOT,AUDITED_SOURCES,verify_audited_sources
from extension_policy import fingerprint as execution_fingerprint,validate_budget,prerequisite as validate_prerequisite
from extension_records import inventory,record_termination,utc_now
from vast_campaign_api import api,destroy_owned,owned_instance,attach_owned_ssh
from vast_execution_access import inspect
from vast_readonly import request,read_key,KEYFILE,discover,SAFE_OFFER


from extension_state import sha


def write(path,data):
    path=Path(path);temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');temp.replace(path)


def validate_bootstrap_evidence(archive,record,root=ROOT):
    archive=Path(archive)
    proof=json.loads(Path(record).read_text())
    if (proof.get('status')!='passed' or proof.get('full_runtime_status')!='passed'
            or proof.get('archive_sha256')!=sha(archive)):
        raise ValueError('complete local bootstrap installation validation is required')
    for field,name in [('pyproject_sha256','pyproject.toml'),('requirements_sha256','requirements-linux-64.lock')]:
        if proof.get(field)!=sha(root/name):
            raise ValueError('bootstrap validation no longer matches the package/dependency contract')
    return proof


def execute(args):
    validate_bootstrap_evidence(args.environment,args.bootstrap_validation)
    verify_audited_sources()
    validate_prerequisite()
    ledger_path=ROOT/'configs/project_budget.json'
    ledger=json.loads(ledger_path.read_text())
    authorization=ledger.get('autonomous_authorization',{})
    if authorization.get('authorized') is not True or authorization.get('exclusive_additional_cap_usd')!=10:
        raise ValueError('current user authorization for spending below $10 is missing')
    key=read_key(KEYFILE)
    access=inspect()
    if not access['broad_instance_write']:
        raise ValueError('known instance creation/destruction authority is required')
    # Live bundle IDs are not reliably searchable with the documented id filter.
    # Refresh the same family query and match the returned purchasable ID locally.
    response=request('POST','/api/v0/bundles',key,body=dict(limit=50,type='on-demand',
        gpu_name={'in':['H100 SXM','H100 PCIE','H100 NVL']},gpu_ram={'gte':80000},
        dph_total={'lte':2.1},verified={'eq':True},reliability2={'gte':.99},
        num_gpus={'eq':1},rentable={'eq':True},rented={'eq':False},order=[['dph_total','asc']]))
    offers=response.get('offers',[])
    def eligible(offer):
        return not ('H100' not in offer.get('gpu_name','') or offer.get('num_gpus')!=1
        or offer.get('cuda_max_good',0)<13 or offer.get('cpu_arch')!='amd64'
        or offer.get('gpu_ram',0)<80000 or offer.get('reliability2',0)<.99
        or offer.get('verification')!='verified' or offer.get('cpu_cores_effective',0)<4
        or offer.get('cpu_ram',0)<16000 or offer.get('disk_space',0)<80
        or offer['dph_total']+80*offer['storage_cost']/720>2.1
        or 14*offer['inet_down_cost']+12*offer['inet_up_cost']>.5)
    suitable=[offer for offer in offers if eligible(offer)]
    if not suitable: raise ValueError('no current offer meets approved hardware/runtime/cost requirements')
    preferred=[offer for offer in suitable if offer['id']==args.offer_id]
    offer=preferred[0] if len(preferred)==1 else min(suitable,key=lambda r:r['dph_total']+40*r['storage_cost']/720)
    args.offer_id=offer['id']
    print(f'Selected live {offer["gpu_name"]} offer {offer["id"]}: quoted GPU/disk upper ${offer["dph_total"]+80*offer["storage_cost"]/720:.4f}/hour',flush=True)
    # Add a full 80GB disk charge even if search already includes a default disk.
    quoted_upper=offer['dph_total']+80*offer['storage_cost']/720
    if quoted_upper>2.1: raise ValueError('selected GPU/disk quote exceeds approved $2.10/hour bound')
    env_archive=Path(args.environment).resolve();payload=Path(args.payload).resolve()
    manifest=json.loads(payload.with_name('bundle_manifest.json').read_text())
    if sha(payload)!=manifest['archive_sha256']: raise ValueError('payload archive hash mismatch')
    for name,digest in manifest['files'].items():
        if sha(ROOT/name)!=digest: raise ValueError('source changed after payload construction')
    if env_archive.stat().st_size>6_000_000_000: raise ValueError('environment archive exceeds transfer budget')
    # Bound download of a <=8GB image, <=6GB environment and <=12GB result archive.
    transfer_bound=14*offer['inet_down_cost']+12*offer['inet_up_cost']
    if transfer_bound>.5: raise ValueError('transfer quote exceeds noncompute reserve')
    if not args.image.startswith('vastai/base-image@sha256:') or not re.fullmatch(r'[a-f0-9]{64}',args.image.split(':')[-1]):
        raise ValueError('a verified immutable Vast base-image digest is required')
    out=Path(args.job_dir).resolve();out.mkdir(parents=True,exist_ok=False)
    approval=dict(approved=True,approval_note=authorization['user_instruction'],provisioning_authorized=True,
        source_sha256=AUDITED_SOURCES,execution_sha256=execution_fingerprint(),allowed_grids=[512],campaign_kind="enstrophy_extension",
        budget_ledger_sha256=sha(ledger_path),max_additional_usd=3,hourly_rate_usd=2.1,
        noncompute_cost_reserve_usd=.5,max_instance_wall_seconds=4200,
        quoted_costs_verified=True,cost_quote_evidence='quote.json')
    spending=validate_budget(ledger,approval)
    write(out/'quote.json',dict(as_of_utc=utc_now(),offer={k:offer[k] for k in SAFE_OFFER if k in offer},
        selected_disk_GB=80,conservative_hourly_upper_usd=quoted_upper,transfer_upper_usd=transfer_bound,
        campaign_cap_usd=3,cost_bound_usd=spending['lifetime_cost_bound_usd'],
        bootstrap_validation_sha256=sha(args.bootstrap_validation),
        image=args.image,environment_sha256=sha(env_archive),payload_sha256=sha(payload)))
    private_dir=Path.home()/'.config/spectrans-3d';private_dir.mkdir(parents=True,exist_ok=True);private_dir.chmod(0o700)
    sshkey=private_dir/('extension-'+uuid.uuid4().hex+'.key')
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(sshkey)],check=True)
    public=sshkey.with_name(sshkey.name+'.pub').read_text().strip()
    known_hosts=private_dir/'smoke-known-hosts'
    label='SpectraNS-3D-v3-extension-'+uuid.uuid4().hex[:12]
    started=datetime.now(timezone.utc);deadline=started+timedelta(seconds=4200)
    state=dict(label=label,instance_id=None,provisioning_authorized=True,
        approval_note=authorization['user_instruction'],controller_pid=os.getpid(),ssh_key_path=str(sshkey),
        provider_started_at_utc=started.isoformat(),termination_deadline_utc=deadline.isoformat(),
        termination_verified=False,status='prepared')
    state['artifact_manifest_verified']=False
    write(out/'controller_state.json',state);write(out/'approval.json',approval)
    (out/'budget_ledger.json').write_bytes(ledger_path.read_bytes())
    with (out/'guard.log').open('x') as log:
        guard=subprocess.Popen([sys.executable,str(ROOT/'scripts/vast_extension_watchdog.py'),'--directory',str(out)],
                               cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    for _ in range(50):
        if (out/'guard_ready.json').exists(): break
        if guard.poll() is not None: raise ValueError('independent guard failed before provisioning')
        time.sleep(.1)
    else: raise ValueError('independent guard did not arm before provisioning')
    approval.update(termination_guard_armed=True,termination_guard_evidence='Independent local WSL watchdog; guard_ready.json',
                    provider_started_at_utc=started.isoformat(),termination_deadline_utc=deadline.isoformat())
    connection=None;downloaded=False;created=False
    def remaining(cleanup=120):
        seconds=(deadline-datetime.now(timezone.utc)).total_seconds()-cleanup
        if seconds<=0: raise TimeoutError('campaign deadline reached')
        return seconds
    def remote(command,logname,timeout=300):
        with (out/logname).open('a') as log:
            subprocess.run(connection+[command],stdout=log,stderr=subprocess.STDOUT,
                           check=True,timeout=min(timeout,remaining(30 if logname=='collection.log' else 120)))
    def copy(source,destination,download=False):
        host=state['ssh_host'];port=state['ssh_port']
        cmd=['scp','-q','-P',str(port),'-i',str(sshkey),'-o','BatchMode=yes',
             '-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(known_hosts)]
        src=f'root@{host}:{source}' if download else str(source)
        dst=str(destination) if download else f'root@{host}:{destination}'
        with (out/'transfer.log').open('a') as log:
            subprocess.run(cmd+[src,dst],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=min(600,remaining(30)))
    try:
        print('Provisioning authorized H100 enstrophy extension; retry cap $3 within shared $4; deadline '+deadline.isoformat(),flush=True)
        onstart='mkdir -p /root/.ssh && chmod 700 /root/.ssh && printf "%s\\n" '+shlex.quote(public)+' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys'
        create_body=dict(image=args.image,label=label,disk=80,runtype='ssh',target_state='running',
                         cancel_unavail=True,onstart=onstart)
        write(out/'create_request.json',create_body)
        result=api('PUT',f'/api/v0/asks/{args.offer_id}/',create_body)
        instance_id=result.get('new_contract')
        if type(instance_id) is not int or instance_id<=0: raise ValueError('creation response lacks instance ID')
        created=True;state.update(instance_id=instance_id,status='provisioned');write(out/'controller_state.json',state)
        write(out/'create_receipt.json',dict(instance_id=instance_id,at_utc=utc_now(),success=True))
        approval['instance_id']=instance_id;write(out/'approval.json',approval)
        write(out/'ssh_attach_receipt.json',dict(attach_owned_ssh(state,public),at_utc=utc_now()))
        print(f'Instance {instance_id} created; independent watchdog armed.',flush=True)
        ready=False
        for _ in range(60):
            remaining()
            row=owned_instance(state)
            if row and row.get('ssh_host') and row.get('ssh_port'):
                host=row['ssh_host'];port=row['ssh_port']
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*',host) or not 0<int(port)<65536:
                    raise ValueError('provider SSH endpoint is malformed')
                state.update(ssh_host=host,ssh_port=int(port));write(out/'controller_state.json',state)
                connection=['ssh','-p',str(port),'-i',str(sshkey),'-o','BatchMode=yes',
                    '-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(known_hosts),
                    '-o','ConnectTimeout=10',f'root@{host}']
                try: remote('true','ssh_ready.log',15);ready=True;break
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired): pass
            time.sleep(5)
        if not ready: raise TimeoutError('instance SSH did not become ready')
        print('SSH ready; transferring environment bootstrap and verified source payload.',flush=True)
        remote('mkdir -p /opt/spectrans-3d/env /opt/spectrans-3d/project','setup.log')
        copy(env_archive,'/opt/spectrans-3d/environment.tar.gz')
        copy(payload,'/opt/spectrans-3d/source.tar')
        copy(out/'approval.json','/opt/spectrans-3d/approval.json')
        copy(ledger_path,'/opt/spectrans-3d/ledger.json')
        verify_env=f'echo {sha(env_archive)} /opt/spectrans-3d/environment.tar.gz | sha256sum -c -'
        verify_src=f'echo {sha(payload)} /opt/spectrans-3d/source.tar | sha256sum -c -'
        setup=' && '.join([verify_env,verify_src,
            'tar -xzf /opt/spectrans-3d/environment.tar.gz -C /opt/spectrans-3d/env',
            'tar -xf /opt/spectrans-3d/source.tar -C /opt/spectrans-3d/project',
            '/opt/spectrans-3d/env/bin/python /opt/spectrans-3d/env/bin/conda-unpack',
            'cd /opt/spectrans-3d/project',
            'PIP_NO_CACHE_DIR=1 /opt/spectrans-3d/env/bin/python -m pip install --no-deps --index-url https://download.pytorch.org/whl/cu130 torch==2.13.0+cu130',
            'PIP_NO_CACHE_DIR=1 /opt/spectrans-3d/env/bin/python -m pip install --no-deps -r requirements-linux-64.lock',
            'PIP_NO_CACHE_DIR=1 /opt/spectrans-3d/env/bin/python -m pip install --no-deps --no-build-isolation -e .',
            '/opt/spectrans-3d/env/bin/python -m pip check',
            '/opt/spectrans-3d/env/bin/python scripts/verify_runtime.py --output /opt/spectrans-3d/runtime_packages.json'])
        remote(setup,'setup.log',600)
        print('Environment ready; running tests, CPU/H100 references, checkpoint preflight, bounded N512 extension, and terminal timestep window.',flush=True)
        command='cd /opt/spectrans-3d/project && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 /opt/spectrans-3d/env/bin/python scripts/launch_enstrophy_extension.py --execute --approval-record /opt/spectrans-3d/approval.json --budget-ledger /opt/spectrans-3d/ledger.json --output /opt/spectrans-3d/results'
        remote(command,'remote_campaign.log',remaining())
        state['status']='compute_passed'
    except Exception as e:
        state.update(status='failed',error=f'{type(e).__name__}: {e}')
        print('Campaign phase failed: '+type(e).__name__+'; collecting evidence and terminating.',flush=True)
    finally:
        try:
            row=owned_instance(state)
            if row and state['instance_id'] is None: state['instance_id']=row['id']
            if connection:
                try:
                    remote("tar -I 'gzip -1' -cf /opt/spectrans-3d/results.tar.gz -C /opt/spectrans-3d results runtime_packages.json",'collection.log',120)
                    copy('/opt/spectrans-3d/results.tar.gz',out/'results.tar.gz',download=True)
                    if (out/'results.tar.gz').stat().st_size > 12_000_000_000:
                        raise ValueError('result archive exceeds transfer bound')
                    with tarfile.open(out/'results.tar.gz') as archive:
                        if sum(member.size for member in archive.getmembers())>12_000_000_000:
                            raise ValueError('uncompressed results exceed collection bound')
                        archive.extractall(out,filter='data')
                    downloaded=True
                except Exception as e:
                    state['collection_error']=type(e).__name__
        finally:
            try:
                receipt=destroy_owned(state);write(out/'destroy_receipt.json',dict(receipt,at_utc=utc_now()))
                for _ in range(12):
                    if owned_instance(state) is None: state['termination_verified']=True;break
                    time.sleep(5)
                if not state['termination_verified']: raise ValueError('provider destruction not yet verified')
                snapshot=discover(key)
                write(out/'after_destruction.json',snapshot)
                if downloaded:
                    record_termination(out/'results',out/'after_destruction.json','Downloaded results.tar.gz; artifact hashes verified; destroy_receipt.json records destruction')
                    state['artifact_manifest_verified']=True
                print('Provider instance absence verified; billable rental terminated.',flush=True)
            except Exception as e:
                state['termination_error']=type(e).__name__
                print('Termination verification incomplete; independent watchdog remains active.',flush=True)
            state['ended_at_utc']=utc_now();state['artifacts_downloaded']=downloaded
            write(out/'controller_state.json',state);inventory(out)
    return 0 if (state['status']=='compute_passed' and downloaded and state['termination_verified']
                 and state['artifact_manifest_verified']) else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--job-dir',required=True)
    p.add_argument('--offer-id',type=int,required=True);p.add_argument('--environment',required=True)
    p.add_argument('--payload',required=True);p.add_argument('--image',required=True)
    p.add_argument('--bootstrap-validation',required=True)
    a=p.parse_args()
    if not a.execute: p.error('execution requires --execute and previously recorded user authorization')
    raise SystemExit(execute(a))
