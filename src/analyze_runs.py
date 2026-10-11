#!/usr/bin/env python3
"""Auditable postprocessing of ns_fast(.py/_v2.py) CSVs.

Do not interpret any finite grid result as a proof of global regularity.
A spectral-tail screen is a necessary diagnostic, not a sufficient resolution test.
"""
import argparse, csv, glob, json, math, re
from pathlib import Path


def parse_run(path):
    name = Path(path).name
    nm = re.search(r'(?:^|_)N(\d+)', name)
    nu = re.search(r'(?:^|_)nu([\d.]+(?:e[+-]?\d+)?)', name, re.I)
    if not (nm and nu):
        raise ValueError(f'{name}: expected Nxxx_nuxxx in filename')
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        raise ValueError(f'{name}: requires >= 2 observations')
    for req in ('t', 'E', 'Z', 'eps', 'wmax', 'bkm', 'tail_ratio', 'div_max'):
        if req not in rows[0]:
            raise ValueError(f'{name}: missing field {req}')
    t = [float(row['t']) for row in rows]
    if not all(b>a for a,b in zip(t,t[1:])):
        raise ValueError(f'{name}: time must strictly increase')
    def floats(key):
        return [float(r[key]) for r in rows if r.get(key) not in ('',None)]
    energies = floats('E'); tails = floats('tail_ratio'); divs = floats('div_max')
    m = max(rows, key=lambda row:float(row['wmax']))
    rises = [(float(r1['t']),float(r2['t'])) for r1,r2 in zip(rows,rows[1:])
             if float(r2['E']) > float(r1['E'])]
    bres = floats('budget_resid_rel')
    return {'file':name, 'N':int(nm.group(1)), 'nu':float(nu.group(1)),
            'n_observations':len(rows), 't_final':t[-1],
            'peak_wmax':float(m['wmax']), 't_peak_sampled':float(m['t']),
            'max_tail_ratio':max(tails), 'max_divergence':max(divs),
            'max_abs_budget_resid_rel':max(map(abs,bres)) if bres else None,
            'energy_interval_rises':len(rises), 'energy_fraction_change':energies[-1]/energies[0]-1,
            'final_bkm_quadrature':float(rows[-1]['bkm'])}


def regression(rows):
    """Return log(peak_wmax) versus log(1/nu) slope; no uncertainty claim."""
    if len(rows)<3: return None
    x=[math.log(1/r['nu']) for r in rows]
    y=[math.log(r['peak_wmax']) for r in rows]
    xm=sum(x)/len(x); ym=sum(y)/len(y)
    xx=sum((v-xm)**2 for v in x)
    if xx < 1e-18: return None
    a=sum((u-xm)*(v-ym) for u,v in zip(x,y))/xx
    intercept=ym-a*xm
    yy=sum((v-ym)**2 for v in y)
    return {'alpha':a,'intercept':intercept, 'r_squared':1-sum((v-a*u-intercept)**2 for u,v in zip(x,y))/yy if yy else None,
            'n':len(rows), 'warning':'descriptive fit; not a singularity test or proof of convergence'}


def run(paths, tail_threshold):
    reports=[parse_run(p) for p in paths]
    reports.sort(key=lambda r:(r['N'],r['nu']))
    for r in reports:
        r['tail_screen_pass'] = r['max_tail_ratio'] <= tail_threshold
        r['note'] = ('No energy increase at logged times' if not r['energy_interval_rises']
                     else 'Measured energy increase: investigate')
    fits={}
    for n in sorted(set(r['N'] for r in reports)):
        peers=[r for r in reports if r['N']==n]
        passed=[r for r in peers if r['tail_screen_pass'] and not r['energy_interval_rises']]
        fits[str(n)]={'all_descriptive_fit':regression(peers),
                      'tail_screened_fit':regression(passed),
                      'screened_points':len(passed),
                      'fit_status':'screened fit withheld: fewer than 3 observations' if len(passed)<3 else 'screened descriptive fit only'}
    return {'tail_warning_threshold':tail_threshold,
            'disclaimer':'Tail screening alone does not establish spatial or temporal convergence. Peak values are sampled at CSV logging times. Finite BKM quadrature is not a proof of global regularity.',
            'runs':reports,'fits_by_grid':fits}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('files',nargs='+', help='CSV files or glob patterns (quote globs on shell)')
    ap.add_argument('--tail-warning-threshold',type=float,default=1e-6)
    ap.add_argument('--json-out',default=None)
    a=ap.parse_args()
    paths=sorted(set(p for item in a.files for p in glob.glob(item)))
    if not paths: ap.error('no matching CSVs')
    results=run(paths,a.tail_warning_threshold)
    print(' N     nu          peak|omega|   sampled t_peak    max tail     rises   tail screen')
    print('-'*86)
    for r in results['runs']:
        print(f"{r['N']:4d}  {r['nu']:10.3g}    {r['peak_wmax']:12.5f}   {r['t_peak_sampled']:13.5f}   {r['max_tail_ratio']:10.3g}   {r['energy_interval_rises']:4d}    {('PASS' if r['tail_screen_pass'] else 'WARN')}")
    for n,fit in results['fits_by_grid'].items():
        raw=fit['all_descriptive_fit']
        good=fit['tail_screened_fit']
        print(f"Grid N={n}: exploratory unscreened alpha={raw['alpha']:.4f}" if raw else f'Grid N={n}: no >=3-point unscreened fit')
        print(f"  Screened alpha={good['alpha']:.4f} (NOT grid validated)" if good else '  Screened alpha withheld: insufficient screened viscosities')
    print('CAUTION: passing a tail cutoff does not establish convergence; compare grids at matched nu and time.')
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True,exist_ok=True)
        Path(a.json_out).write_text(json.dumps(results,indent=2)+'\n')
        print('JSON summary:',a.json_out)

if __name__=='__main__': main()
