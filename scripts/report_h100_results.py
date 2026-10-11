#!/usr/bin/env python3
"""Recompute scientific diagnostics from preserved smoke artifacts; no GPU use."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def summarize(campaign,output,local=None):
    campaign=Path(campaign).resolve();output=Path(output).resolve()
    manifest=json.loads((campaign/'artifact_manifest.json').read_text())
    if any(sha(campaign/name)!=digest for name,digest in manifest.items()):
        raise ValueError('Campaign artifact hash verification failed.')
    maxima=dict(energy_fd_relative=0.,divergence=0.,tail_ratio=0.,
                enstrophy_relative_residual=0.,parseval_relative=0.,
                high_k_energy_fraction=0.,scheme_scalar_relative=0.)
    checks=[];inputs={}
    for path in sorted(campaign.glob('*.csv.json')):
        name=path.name[:-9];config=json.loads(path.read_text())
        if config['status']!='completed':
            raise ValueError('Incomplete run: '+name)
        paths=[path,campaign/(name+'.csv'),campaign/(name+'_spectra.csv'),
               campaign/(name+'_enstrophy.csv')]
        for p in paths: inputs[str(p)]=sha(p)
        rows=list(csv.DictReader(paths[1].open()))
        energies={r['t']:float(r['E']) for r in rows}
        for row in rows:
            for metric,key in [('divergence','div_max'),('tail_ratio','tail_ratio')]:
                maxima[metric]=max(maxima[metric],abs(float(row[key])))
            if float(row['t'])>0:
                maxima['energy_fd_relative']=max(maxima['energy_fd_relative'],abs(float(row['budget_resid_rel'])))
        shells=list(csv.DictReader(paths[2].open()))
        totals={};high={}
        for row in shells:
            t=row['t'];v=float(row['E_shell_mean_density'])
            totals[t]=totals.get(t,0.)+v
            if int(row['shell_k'])>=config['parameters']['N']//3:
                high[t]=high.get(t,0.)+v
        for t,value in totals.items():
            maxima['parseval_relative']=max(maxima['parseval_relative'],abs(value-energies[t])/energies[t])
            maxima['high_k_energy_fraction']=max(maxima['high_k_energy_fraction'],high.get(t,0.)/energies[t])
        for row in csv.DictReader(paths[3].open()):
            scale=max(abs(float(row['production'])),config['parameters']['nu']*float(row['grad_omega_sq']),
                      abs(float(row['dZdt_rhs'])),1e-14)
            maxima['enstrophy_relative_residual']=max(maxima['enstrophy_relative_residual'],abs(float(row['residual']))/scale)
        if local:
            local=Path(local).resolve()
            lp=local/path.name;lc=json.loads(lp.read_text());inputs[str(lp)]=sha(lp)
            if lc['source_sha256']!=config['source_sha256']:
                raise ValueError('Cross-GPU solver source mismatch.')
            for key in ['N','case','scheme','nu','target_t','max_dt','cfl','log_dt','fp64','spectrum_stride','spectrum_slab']:
                if lc['parameters'][key]!=config['parameters'][key]:
                    raise ValueError('Cross-GPU configuration mismatch.')
            lp=local/(name+'.csv');inputs[str(lp)]=sha(lp)
            earlier=list(csv.DictReader(lp.open()))
            if [r['t'] for r in earlier]!=[r['t'] for r in rows]:
                raise ValueError('Cross-GPU diagnostic times differ.')
            scalar={k:max(abs(float(a[k])-float(b[k]))/max(abs(float(a[k])),abs(float(b[k])),1e-14)
                          for a,b in zip(earlier,rows)) for k in ['E','Z','wmax','bkm']}
            lp=local/(name+'_spectra.csv');inputs[str(lp)]=sha(lp)
            earlier=list(csv.DictReader(lp.open()))
            if [(r['t'],r['shell_k']) for r in earlier]!=[(r['t'],r['shell_k']) for r in shells]:
                raise ValueError('Cross-GPU spectrum times or shells differ.')
            differences={}
            for a,b in zip(earlier,shells):
                t=a['t'];differences[t]=differences.get(t,0.)+abs(float(a['E_shell_mean_density'])-float(b['E_shell_mean_density']))
            spectral=max(v/energies[t] for t,v in differences.items())
            checks.append(dict(run=name,scalar_relative_errors=scalar,spectrum_l1_relative_to_energy=spectral))
    record=json.loads((campaign/'campaign.json').read_text())
    maxima['scheme_scalar_relative']=max(r['relative_difference'] for r in record['comparisons'])
    result=dict(analysis_source_sha256=sha(__file__),campaign_manifest_sha256=sha(campaign/'artifact_manifest.json'),
                input_sha256=inputs,observed_maxima=maxima,cross_gpu_checks=checks,
                gpu_execution_performed=False)
    with output.open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print('Preserved artifacts verified and analysis reproduced:',output)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',required=True);p.add_argument('--output',required=True)
    p.add_argument('--local-reference')
    a=p.parse_args();summarize(a.campaign,a.output,a.local_reference)
