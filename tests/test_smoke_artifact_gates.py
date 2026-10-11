"""Reject incomplete or corrupted results even when a subprocess exits zero."""
import csv
import json
import math

import pytest
from cloud_policy import AUDITED_SOURCES
from launch_h100_smoke import compare


def table(path,fields,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def smoke_fixture(out):
    times=[0.,.01,.02,.03,.04,.05]
    scalar_fields=['t','dt','E','Z','eps','wmax','bkm','tail_ratio','div_max','wall_s','peak_mem_GB','budget_resid_rel']
    for case in ('tgv','tubes'):
        for scheme in ('ssprk3','lsrk4'):
            name=f'{case}_N128_{scheme}'
            report=dict(status='completed',t=.05,source_sha256=AUDITED_SOURCES,
                parameters=dict(N=128,case=case,scheme=scheme,nu=.0005,target_t=.05,max_dt=.002,
                                cfl=.2,log_dt=.01,fp64=True,spectrum_slab=4,spectrum_stride=1),
                memory=dict(peak_allocated_GB=1,peak_reserved_GB=2,total_GB=80))
            (out/(name+'.csv.json')).write_text(json.dumps(report))
            rows=[dict(t=t,dt=.002,E=1-t*.001,Z=1,eps=.001,wmax=1,bkm=t,tail_ratio=0,
                       div_max=1e-7,wall_s=1,peak_mem_GB=1,budget_resid_rel=0) for t in times]
            table(out/(name+'.csv'),scalar_fields,rows)
            spectra=[dict(t=t,shell_k=k,E_shell_mean_density=1-t*.001 if k==1 else 0)
                     for t in times for k in range(int(math.sqrt(3)*64+.5)+1)]
            table(out/(name+'_spectra.csv'),['t','shell_k','E_shell_mean_density'],spectra)
            table(out/(name+'_enstrophy.csv'),['t','production','grad_omega_sq','dZdt_rhs','residual'],
                  [dict(t=t,production=0,grad_omega_sq=1,dZdt_rhs=-.001,residual=0) for t in times])


def test_smoke_matrix_requires_all_diagnostics(tmp_path):
    smoke_fixture(tmp_path)
    assert len(compare(tmp_path,128))==48
    with pytest.raises(ValueError,match='only'):
        compare(tmp_path,512)


@pytest.mark.parametrize('change',['hash','memory','configuration','spectrum','nan','energy','budget'])
def test_bad_smoke_artifacts_rejected(tmp_path,change):
    smoke_fixture(tmp_path)
    prefix=tmp_path/'tgv_N128_ssprk3'
    manifest=prefix.with_suffix('.csv.json')
    if change in ('hash','memory','configuration'):
        report=json.loads(manifest.read_text())
        if change=='hash': report['source_sha256']={}
        if change=='memory': report['memory']['peak_reserved_GB']=65
        if change=='configuration': report['parameters']['max_dt']=.1
        manifest.write_text(json.dumps(report))
    else:
        path=prefix.with_name(prefix.name+'_spectra.csv') if change=='spectrum' else prefix.with_suffix('.csv')
        with path.open() as f: rows=list(csv.DictReader(f))
        fields=list(rows[0])
        if change=='spectrum': rows.pop()
        if change=='nan': rows[2]['Z']='nan'
        if change=='energy': rows[2]['E']='2'
        if change=='budget': rows[2]['budget_resid_rel']='.02'
        table(path,fields,rows)
    with pytest.raises(ValueError):
        compare(tmp_path,128)
