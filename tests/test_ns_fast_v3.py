"""Independent references, regression and fail-closed driver checks."""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
import torch

import ns_fast_v3 as v3
from ns_fast_v2 import Solver as V2Solver

torch.set_num_threads(2)


def solver(N=16, nu=.02, **kwargs):
    return v3.Solver(N, nu, dtype=torch.float64, **kwargs)


def advance(S, U, scheme, target):
    t = 0.
    R = [torch.zeros_like(u) for u in U]
    while t < target-1e-14:
        dt, _ = S.step_ssprk3(U,t,target) if scheme == 'ssprk3' else S.step_lsrk4(U,R,t,target)
        t += dt
    return U


def numpy_reference(S, U):
    """Full complex NumPy FFT, advective form and independent projection.
    No solver curl/project/fft methods are used by the reference.
    """
    real = np.stack([torch.fft.irfftn(u, s=S.s).cpu().numpy() for u in U])
    hats = np.fft.fftn(real, axes=(1,2,3))
    k = np.fft.fftfreq(S.N, d=1/S.N)
    waves = np.meshgrid(k,k,k,indexing='ij')
    k2 = sum(kj**2 for kj in waves)
    mask = k2 < (S.N/3)**2
    grads = np.array([[np.fft.ifftn(1j*waves[j]*hats[i]).real for j in range(3)] for i in range(3)])
    adv = -np.einsum('jxyz,ijxyz->ixyz',real,grads)
    rhs = np.fft.fftn(adv,axes=(1,2,3))*mask
    dot = sum(waves[j]*rhs[j] for j in range(3))
    safe = np.where(k2 == 0, 1., k2)
    rhs -= np.array(waves)*dot/safe
    rhs -= S.nu*k2*hats
    omega = np.array([grads[2,1]-grads[1,2], grads[0,2]-grads[2,0], grads[1,0]-grads[0,1]])
    prod = np.einsum('ixyz,jxyz,ijxyz->xyz',omega,omega,grads).mean()
    return np.fft.ifftn(rhs,axes=(1,2,3)).real, prod


@pytest.mark.parametrize('case',['tgv','tubes'])
def test_original_ic_and_rhs_regression(case):
    source = Path(__file__).resolve().parent/'fixtures/ns_fast_original.py'
    spec = importlib.util.spec_from_file_location('original', source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    old = original.Solver(24,.02,device='cpu',dtype=torch.float64)
    new = solver(24)
    U = getattr(old,'ic_'+case)()
    V = getattr(new,'ic_'+case)()
    assert all(torch.equal(u,v) for u,v in zip(U,V))
    a,_ = old.rhs(*U)
    b,_ = new.rhs(*V)
    # The intentional zero-mode damping fix is the only RHS difference.
    assert all(torch.max(torch.abs(x-y)).item() < 1e-12 for x,y in zip(a,b))
    assert new.spectrum_tail(V) == pytest.approx(old.spectrum_tail(U),abs=1e-14)


@pytest.mark.parametrize('scheme',['ssprk3','lsrk4'])
def test_mean_velocity_conserved_in_both_schemes(scheme):
    S=solver(nu=.7)
    U=[S.fft(torch.full(S.s,c,dtype=torch.float64)) for c in (1.,-.5,.25)]
    initial=[u.clone() for u in U]
    advance(S,U,scheme,.1)
    assert all(torch.allclose(u,v,rtol=0,atol=2e-12) for u,v in zip(U,initial))


@pytest.mark.parametrize('case',['tgv','tubes'])
def test_independent_advective_rhs_and_enstrophy(case):
    S=solver(24)
    U=getattr(S,'ic_'+case)()
    reference, prod=numpy_reference(S,U)
    rhs,_=S.rhs(*U)
    actual=np.stack([S.ifft(r).numpy() for r in rhs])
    np.testing.assert_allclose(actual,reference,atol=3e-13,rtol=2e-11)
    budget=S.enstrophy_budget(U)
    assert budget['production'] == pytest.approx(prod,abs=2e-12)
    scale=max(abs(budget['production']),S.nu*budget['grad_omega_sq'],1.)
    assert abs(budget['residual'])/scale < 2e-12


def test_full_fft_shells_including_zero_and_nyquist():
    S=solver()
    rng=np.random.default_rng(7123)
    real=rng.standard_normal((3,*S.s))+1.
    U=[S.fft(torch.from_numpy(u)) for u in real]
    k=np.fft.fftfreq(S.N,d=1/S.N)
    waves=np.meshgrid(k,k,k,indexing='ij')
    shell=np.floor(np.sqrt(sum(w**2 for w in waves))+.5).astype(int)
    hats=np.fft.fftn(real,axes=(1,2,3))
    expected=np.bincount(shell.ravel(),weights=(np.abs(hats)**2).sum(axis=0).ravel())*.5/S.N**6
    for slab in (1,3,9):
        actual=S.spectrum_shells(U,slab).numpy()
        np.testing.assert_allclose(actual,expected,rtol=2e-14,atol=1e-14)
        assert actual.sum() == pytest.approx(.5*(real**2).sum(axis=0).mean(),abs=1e-13)
    assert S.shell is None


@pytest.mark.parametrize('scheme,order',[('ssprk3',3),('lsrk4',4)])
def test_temporal_order_on_exact_shear(scheme,order):
    errors=[]
    for dt in (.1,.05,.025):
        # N12 keeps all three requested dt values below the diffusion cap.
        S=solver(N=12,nu=.5,max_dt=dt,cfl=1.)
        y=torch.arange(S.N,dtype=torch.float64)*S.dx
        u=torch.sin(y)[None,:,None].expand(S.s).contiguous()
        U=[S.fft(u),S.fft(torch.zeros_like(u)),S.fft(torch.zeros_like(u))]
        advance(S,U,scheme,.4)
        errors.append((S.ifft(U[0])-u*math.exp(-.2)).abs().max().item())
    observed=[math.log2(a/b) for a,b in zip(errors,errors[1:])]
    assert min(observed)>order-.12, (errors,observed)
    assert max(observed)<order+.15, (errors,observed)


def test_fp32_effect_is_bounded_separately():
    states=[]
    for dtype in (torch.float32,torch.float64):
        S=v3.Solver(24,.02,max_dt=.002,device='cpu',dtype=dtype)
        U=advance(S,S.ic_tgv(),'ssprk3',.1)
        states.append(np.array(S.diagnostics(U)))
    np.testing.assert_allclose(states[0][:3],states[1][:3],atol=5e-6,rtol=5e-6)


def test_snapshot_precision_coordinates_and_components(tmp_path):
    S=solver(16)
    U=S.ic_tgv()
    path=tmp_path/'omega.npz'
    S.save_vorticity_snapshot(U,path,stride=3,t=.2,requested_t=.2)
    with np.load(path) as z:
        assert z['axes'].item()=='component,x,y,z'
        assert z['omega'].dtype==np.float64
        np.testing.assert_array_equal(z['x'],np.arange(0,16,3)*S.dx)
        np.testing.assert_allclose(z['omega'],np.stack([S.ifft(c).numpy()[::3,::3,::3] for c in S.curl_h(*U)]))
        assert z['requested_t']==z['t']==.2


@pytest.mark.parametrize('args',[
    ['--nu','nan'],['--target_t','inf'],['--max_dt','0'],['--max_dt','nan'],
    ['--max_steps','-1'],['--max_gpu_fraction','1.1'],['--snapshot_times','nan'],
    ['--N','7'],['--abort_on_tail','-1'],['--N','1024','--preflight_only']])
def test_invalid_cli_fails_before_outputs(args,tmp_path):
    with pytest.raises(SystemExit) as error:
        v3.main(['--device','cpu','--csv',str(tmp_path/'bad.csv'),*args])
    assert error.value.code==2
    assert not list(tmp_path.iterdir())


def test_nonfinite_umax_is_rejected_before_update():
    S=solver()
    with pytest.raises(FloatingPointError):
        S.get_dt(float('nan'))


def test_driver_matches_times_outputs_and_completion(tmp_path):
    path=tmp_path/'run.csv'
    code=v3.main(['--case','tgv','--N','16','--device','cpu','--fp64','--max_dt','.007',
                  '--target_t','.03','--log_dt','.01','--snapshot_times','.013,.03',
                  '--snapshot_dir',str(tmp_path/'snaps'),'--csv',str(path),
                  '--spectrum_csv',str(tmp_path/'nested/spectrum.csv'),
                  '--budget_csv',str(tmp_path/'budget.csv')])
    assert code==0
    data=np.genfromtxt(path,delimiter=',',names=True)
    np.testing.assert_array_equal(data['t'],[0,.01,.02,.03])
    report=json.loads(Path(str(path)+'.json').read_text())
    assert report['status']=='completed' and report['snapshots_written']==2
    assert sorted(float(np.load(p)['t']) for p in (tmp_path/'snaps').glob('*.npz'))==[.013,.03]


def test_initial_tail_gate_and_step_cap_are_not_success(tmp_path):
    path=tmp_path/'tail.csv'
    result=v3.main(['--N','16','--abort_on_tail','1e-30','--csv',str(path)])
    assert result==2
    report=json.loads(Path(str(path)+'.json').read_text())
    assert report['status']=='failed' and report['steps']==0
    path=tmp_path/'cap.csv'
    result=v3.main(['--N','16','--case','tgv','--max_steps','1','--csv',str(path)])
    assert result==2
    assert json.loads(Path(str(path)+'.json').read_text())['status']=='stopped_max_steps'


def test_memory_reference_requires_matching_scheme_and_real_headroom():
    a=v3.parser().parse_args(['--N','1024','--device','cuda'])
    ref=dict(status='completed',steps=5,parameters=dict(N=768),
             memory_signature=v3.memory_signature(a), source_sha256=v3.source_hashes(),
             torch=torch.__version__,cuda=torch.version.cuda,
             memory=dict(gpu='test GPU',peak_allocated_GB=33.8,peak_reserved_GB=34.))
    current=dict(gpu='test GPU',free_GB=80.,total_GB=80.)
    with pytest.raises(ValueError,match='exceeds'):
        v3.check_memory_reference(ref,a,current)
    ref['memory']['peak_allocated_GB']=20.
    ref['memory']['peak_reserved_GB']=21.
    assert v3.check_memory_reference(ref,a,current)<64.
    ref['memory_signature']['scheme']='lsrk4'
    with pytest.raises(ValueError,match='match source'):
        v3.check_memory_reference(ref,a,current)


@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA unavailable')
@pytest.mark.parametrize('dtype',[torch.float32,torch.float64])
def test_small_gpu_equivalence_and_repeat_spectra(dtype):
    cpu=v3.Solver(32,.02,device='cpu',dtype=dtype)
    gpu=v3.Solver(32,.02,device='cuda',dtype=dtype)
    U=cpu.ic_tubes()
    V=[u.cuda() for u in U]
    a,_=cpu.rhs(*U)
    b,_=gpu.rhs(*V)
    tol=3e-5 if dtype==torch.float32 else 3e-12
    for x,y in zip(a,b):
        np.testing.assert_allclose(cpu.ifft(x).numpy(),gpu.ifft(y).cpu().numpy(),rtol=tol,atol=tol)
    reference=cpu.spectrum_shells(U).numpy()
    for _ in range(3):
        np.testing.assert_allclose(gpu.spectrum_shells(V).cpu().numpy(),reference,rtol=2e-12,atol=1e-14)
    assert gpu.shell is None


@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA unavailable')
def test_cuda_driver_accepts_unindexed_device_and_writes_outputs(tmp_path):
    path=tmp_path/'gpu.csv'
    assert v3.main(['--N','16','--case','tgv','--device','cuda','--fp64',
                    '--target_t','.01','--csv',str(path),
                    '--snapshot_times','.01','--snapshot_dir',str(tmp_path/'snapshots'),
                    '--budget_csv',str(tmp_path/'budget.csv')]) == 0
    manifest=json.loads(Path(str(path)+'.json').read_text())
    assert manifest['memory']['peak_allocated_GB']>0
    assert manifest['snapshots_written']==1
