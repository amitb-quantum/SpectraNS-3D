"""CPU-only regression checks. These are not a global regularity proof."""
import math
import numpy as np
import pytest
import torch

from ns_fast_v2 import Solver


def solver(N=16, nu=0.005):
    return Solver(N=N, nu=nu, cfl=.25, max_dt=.01, device='cpu', dtype=torch.float64)


def test_zero_mode_laplacian_and_safe_inverse():
    S = solver()
    assert S.K2[0,0,0].item() == 1.0  # safe projection divisor
    assert S.K2_safe is S.K2   # zero additional full-grid allocation


def test_taylor_green_energy_enstrophy_and_solenoidality():
    S = solver()
    U = S.ic_tgv()
    E, Z, wmax, div, tail = S.diagnostics(U)
    assert E == pytest.approx(.125, abs=2e-13)
    assert Z == pytest.approx(.375, abs=2e-13)
    assert div < 1e-12
    assert tail >= 0.0


def test_constant_velocity_zero_mode_not_damped():
    S = solver()
    c = torch.ones(S.s, dtype=torch.float64)
    z = torch.zeros_like(c)
    U = [S.fft(c), S.fft(z), S.fft(z)]
    initial = [a.clone() for a in U]
    S.step_ssprk3(U, 0.0, .01)
    assert all(torch.max(torch.abs(a-b)).item() < 1e-12 for a,b in zip(U,initial))
    bins=S.spectrum_shells(U)
    assert bins[0].item() == pytest.approx(.5, abs=1e-12)


def test_shell_spectrum_equals_total_energy():
    S = solver(N=24)
    for U in [S.ic_tgv(), S.ic_tubes()]:
        E = S.diagnostics(U)[0]
        bins = S.spectrum_shells(U, slab=3)
        assert bins.sum().item() == pytest.approx(E, abs=1e-12)
        assert (bins >= 0).all()


def test_rk_schemes_agree_on_short_tgv():
    S = solver()
    a = S.ic_tgv()
    b = [u.clone() for u in a]
    R = [torch.zeros_like(u) for u in b]
    ta = tb = 0.0
    while ta < .03 - 1e-14:
        dt, _ = S.step_ssprk3(a, ta, .03)
        ta += dt
    while tb < .03 - 1e-14:
        dt, _ = S.step_lsrk4(b, R, tb, .03)
        tb += dt
    assert abs(ta - tb) < 1e-12
    maxdiff = max(torch.max(torch.abs(x-y)).item() for x,y in zip(a,b))
    assert maxdiff < 2e-7
    assert S.diagnostics(b)[3] < 1e-12


def test_pure_shear_is_exact_diffusive_solution():
    # u=(sin(y),0,0) satisfies (u.grad)u=0; Fourier k^2=1.
    S = solver(N=16,nu=0.2)
    x = torch.arange(S.N, dtype=torch.float64) * S.dx
    real = torch.sin(x).view(1,S.N,1).expand(S.N,S.N,S.N).contiguous()
    U = [S.fft(real), S.fft(torch.zeros_like(real)), S.fft(torch.zeros_like(real))]
    t = 0.0
    while t < .1-1e-12:
        dt,_ = S.step_lsrk4(U,[torch.zeros_like(c) for c in U],t,.1)
        # Note: residual must persist across stages within a step; new residual across steps is valid.
        t += dt
    u = S.ifft(U[0]); exact=real*math.exp(-.2*.1)
    assert (u-exact).abs().max().item() < 5e-7


def test_vector_vorticity_snapshot_metadata(tmp_path):
    S=solver()
    p=tmp_path/'snapshot.npz'
    S.save_vorticity_snapshot(S.ic_tgv(),p,stride=4,t=.123)
    with np.load(p) as z:
        assert z['omega'].shape == (3,4,4,4)
        assert z['t'].item() == pytest.approx(.123)
        assert z['domain'].item() == pytest.approx(2*math.pi)


def test_instantaneous_energy_dissipation_identity():
    # For unforced rotational-form pseudo-spectral NS, nonlinear term does not
    # change kinetic energy; dE/dt = -2 nu Z at an exactly divergence-free state.
    S = solver(N=24, nu=0.0125)
    for U in (S.ic_tgv(), S.ic_tubes()):
        rhs, _ = S.rhs(*U)
        dE = sum((S.ifft(a).double() * S.ifft(r).double()).mean().item()
                 for a, r in zip(U, rhs))
        Z = S.diagnostics(U)[1]
        assert dE == pytest.approx(-2 * S.nu * Z, rel=3e-11, abs=1e-12)
