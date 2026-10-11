#!/usr/bin/env python3
"""Strict archive analysis: descriptive fits only; no convergence certification."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from analyze_runs import regression


def read_rows(path):
    with Path(path).open(newline='') as f:
        raw=list(csv.DictReader(f))
    if len(raw)<2:
        raise ValueError(f'{path}: fewer than two records')
    required=('t','E','Z','eps','wmax','bkm','tail_ratio','div_max')
    rows=[]
    for i,row in enumerate(raw):
        converted={}
        for key in required:
            value=float(row[key])
            if not math.isfinite(value) or value<0:
                raise ValueError(f'{path}: invalid {key} at record {i}')
            converted[key]=value
        for key in ('budget_resid_rel','peak_mem_GB','wall_s'):
            value=row.get(key)
            if value not in ('',None):
                value=float(value)
                if not math.isfinite(value):
                    raise ValueError(f'{path}: nonfinite {key} at record {i}')
                converted[key]=value
        rows.append(converted)
    if rows[0]['E']<=0 or any(b['t']<=a['t'] for a,b in zip(rows,rows[1:])):
        raise ValueError(f'{path}: invalid initial energy or nonincreasing time')
    return rows


def summarize(path, family, nu=None):
    path=Path(path)
    rows=read_rows(path)
    n=int(re.search(r'_N(\d+)',path.name).group(1))
    if nu is None:
        nu=float(re.search(r'_nu([\d.]+(?:e[+-]?\d+)?)',path.name).group(1))
    peak=max(rows,key=lambda r:r['wmax'])
    gaps=[b['t']-a['t'] for a,b in zip(rows,rows[1:])]
    tail=max(r['tail_ratio'] for r in rows)
    return dict(file=str(path),family=family,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                N=n,nu=nu,n_observations=len(rows),t_final=rows[-1]['t'],
                peak_wmax=peak['wmax'],t_peak_sampled=peak['t'],
                max_tail_ratio=tail,tail_screen_pass=tail<=1e-6,
                max_divergence=max(r['div_max'] for r in rows),
                max_abs_budget_resid_rel=max(abs(r.get('budget_resid_rel',0)) for r in rows),
                energy_interval_rises=sum(b['E']>a['E'] for a,b in zip(rows,rows[1:])),
                energy_fraction_change=rows[-1]['E']/rows[0]['E']-1,
                final_bkm_quadrature=rows[-1]['bkm'],
                sampling_gap_min=min(gaps),sampling_gap_max=max(gaps),
                peak_allocated_GB=max(r.get('peak_mem_GB',0) for r in rows),
                wall_s=rows[-1].get('wall_s'),
                convergence_verified=False)


def interpolate(rows,t,key):
    for a,b in zip(rows,rows[1:]):
        if a['t']<=t<=b['t']:
            f=(t-a['t'])/(b['t']-a['t'])
            return a[key]*(1-f)+b[key]*f
    raise ValueError('requested comparison time not covered')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='artifacts/validation/archive_summary.json')
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]/'data/original'
    audit=root/'ns_regularity_upgrade/audit'
    campaign=root/'historical/campaign_results/results/out'
    sweep=[summarize(path,'audit_fp64_reductions') for path in sorted(audit.glob('tubes_N512*.csv'))]
    earlier=[summarize(path,'campaign_fp32_reductions',.000625 if path.name.startswith('tgv') else None)
             for path in sorted(campaign.glob('*.csv'))]
    comparisons=[]
    high=read_rows(campaign/'tubes_N1024_nu5e-4.csv')
    for n in (256,512):
        low=read_rows(campaign/f'tubes_N{n}_nu5e-4.csv')
        times=[j/100 for j in range(101)]
        metrics={}
        for key in ('E','Z','wmax','bkm'):
            errors=[abs(interpolate(low,t,key)-interpolate(high,t,key))/max(abs(interpolate(high,t,key)),1e-14) for t in times]
            metrics[key]=dict(max_relative_difference=max(errors),final_relative_difference=errors[-1])
        comparisons.append(dict(N=n,reference_N=1024,nu=.0005,metrics=metrics,
                                method='linear interpolation onto 0:.01:1; sampled extrema, no field comparison',
                                caution='Adaptive dt changes with N; this does not separate time and grid errors.'))
    result=dict(tail_warning_threshold=1e-6,runs=sweep+earlier,
                audit_sweep_descriptive_fit=regression(sweep),
                physical_fit=None,physical_fit_status='WITHHELD: no viscosities have independent grid AND time convergence evidence',
                audit_sweep_tail_pass_count=sum(r['tail_screen_pass'] for r in sweep),
                historical_matched_time_comparisons=comparisons,
                missing_evidence=['No N768 CSV: supplied audit log ends at t=0.3309 without completion',
                                  'No matched-grid timestep refinement campaign',
                                  'Historical provenance is archived source association, not runtime hash attestation'],
                warning='All historical data are supplied records, not newly reproduced runs. Tail screening is a heuristic; no regularity or reconnection claim.')
    output=Path(a.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(f'{len(result["runs"])} archive runs; {result["audit_sweep_tail_pass_count"]}/4 sweep tail screens pass; physical fit withheld')
    for r in comparisons:
        print(f'N{r["N"]} vs N1024 max matched-time relative wmax difference: {r["metrics"]["wmax"]["max_relative_difference"]:.4%}')


if __name__=='__main__':
    main()
