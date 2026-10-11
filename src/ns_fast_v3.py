#!/usr/bin/env python3
"""Validation-first driver. The exact v2 RHS, integrators and legacy IC are reused.

CSV columns retain v2 meanings. Output events clip timesteps to matched physical
times; BKM remains trapezoidal over diagnostic samples. No regularity claim.
"""
import argparse
from contextlib import ExitStack
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

import numpy as np
import torch
from ns_fast_v2 import Solver as V2Solver


class Solver(V2Solver):
    def __init__(self, N, nu, cfl=.35, max_dt=.01, device='cpu', dtype=torch.float32):
        if not isinstance(N, int) or N < 6 or N % 2:
            raise ValueError('N must be an even integer >= 6')
        if not all(math.isfinite(x) for x in (nu, cfl, max_dt)):
            raise ValueError('nu, cfl and max_dt must be finite')
        if nu < 0 or not 0 < cfl <= 1 or max_dt <= 0:
            raise ValueError('require nu >= 0, 0 < cfl <= 1 and max_dt > 0')
        if dtype not in (torch.float32, torch.float64):
            raise ValueError('only float32 and float64 are supported')
        super().__init__(N, nu, cfl, max_dt, device, dtype)
        self.spectrum_slab = 4

    def get_dt(self, umax):
        if not math.isfinite(umax) or umax < 0:
            raise FloatingPointError('nonfinite or negative velocity maximum')
        dt = super().get_dt(umax)
        if not math.isfinite(dt) or dt <= 0:
            raise FloatingPointError('nonfinite or nonpositive timestep')
        return dt

    def spectrum_shells(self, U, slab=None):
        """Shell sums, not shell averages; include every Fourier shell.

        Temporary indices occupy O(N^2*slab), never a cached full-grid int64
        tensor. CUDA weighted bincount is validated in tolerance, not bitwise.
        """
        slab = self.spectrum_slab if slab is None else slab
        if not isinstance(slab, int) or slab < 1:
            raise ValueError('spectrum slab must be a positive integer')
        count = int(math.sqrt(3) * (self.N // 2) + .5) + 1
        bins = torch.zeros(count, device=self.dev, dtype=torch.float64)
        nz = self.N // 2 + 1
        for z0 in range(0, nz, slab):
            z1 = min(z0 + slab, nz)
            shell = torch.floor(self.K2[:, :, z0:z1].sqrt() + .5).long()
            if z0 == 0:
                shell[0, 0, 0] = 0
            power = torch.zeros_like(shell, dtype=torch.float64)
            for a in U:
                part = a[:, :, z0:z1]
                power.add_(part.real.double().square()).add_(part.imag.double().square())
            weights = torch.full((z1-z0,), 2., device=self.dev, dtype=torch.float64)
            if z0 == 0:
                weights[0] = 1
            if z1 == nz:
                weights[-1] = 1
            power.mul_(weights)
            bins.add_(torch.bincount(shell.flatten(), weights=power.flatten(), minlength=count))
        return bins.mul_(.5 / self.N**6)

    def spectrum_tail(self, U, slab=None):
        bins = self.spectrum_shells(U, slab)
        return bins[self.kcut-1].item() / max(bins[1:self.kcut].max().item(), 1e-300)

    def curl_component(self, U, i):
        j, k = (i+1) % 3, (i+2) % 3
        waves = (self.kx, self.ky, self.kz)
        return 1j * (waves[j] * U[k] - waves[k] * U[j])

    def save_vorticity_snapshot(self, U, path, stride=4, t=0., requested_t=None):
        if stride < 1:
            raise ValueError('snapshot stride must be positive')
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # One full real component at a time. Copy on CPU too: a numpy view of
        # a strided tensor otherwise retains its full N^3 backing allocation.
        shape = len(range(0, self.N, stride))
        vectors = np.empty((3, shape, shape, shape),
                           dtype=np.float64 if self.dt_ == torch.float64 else np.float32)
        for i in range(3):
            field = self.ifft(self.curl_component(U, i))
            vectors[i] = field[::stride, ::stride, ::stride].cpu().numpy()
            del field
        coords = np.arange(0, self.N, stride) * self.dx
        np.savez_compressed(path, omega=vectors, N=self.N, t=t,
                            requested_t=t if requested_t is None else requested_t,
                            stride=stride, dx=self.dx, sample_dx=self.dx*stride,
                            domain=2*math.pi, x=coords, y=coords, z=coords,
                            axes='component,x,y,z', components=np.array(['wx','wy','wz']),
                            sampling='unfiltered spatial sampling; may alias' if stride > 1 else 'full field')

    def enstrophy_budget(self, U):
        """Optional, expensive instantaneous identity. Additional full fields
        are required; this option must be included in any memory reference.
        """
        omega = [self.ifft(self.curl_component(U, i)).double() for i in range(3)]
        waves = (self.kx, self.ky, self.kz)
        production = 0.
        grad_omega_sq = 0.
        for i in range(3):
            oh = self.curl_component(U, i)
            for j in range(3):
                du = self.ifft(1j * waves[j] * U[i]).double()
                production += (omega[i] * omega[j] * du).mean().item()
                del du
                dw = self.ifft(1j * waves[j] * oh).double()
                grad_omega_sq += dw.square().mean().item()
                del dw
        rhs, _ = self.rhs(*U)
        dz = sum((omega[i] * self.ifft(self.curl_component(rhs, i)).double()).mean().item()
                 for i in range(3))
        residual = dz - production + self.nu * grad_omega_sq
        return dict(production=production, grad_omega_sq=grad_omega_sq,
                    dZdt_rhs=dz, residual=residual)


def source_hashes():
    root = Path(__file__).resolve().parent
    return {n: hashlib.sha256((root/n).read_bytes()).hexdigest()
            for n in ('ns_fast_v3.py', 'ns_fast_v2.py')}


def memory_state(device):
    if device.type != 'cuda':
        return {}
    torch.cuda.synchronize(device)
    free, total = torch.cuda.mem_get_info(device)
    return dict(peak_allocated_GB=torch.cuda.max_memory_allocated(device)/1e9,
                peak_reserved_GB=torch.cuda.max_memory_reserved(device)/1e9,
                free_GB=free/1e9, total_GB=total/1e9,
                gpu=torch.cuda.get_device_name(device))


def memory_signature(a):
    return dict(scheme=a.scheme, fp64=a.fp64, case=a.case,
                spectrum=bool(a.spectrum_csv), spectrum_slab=a.spectrum_slab,
                snapshots=bool(a.snapshot_times), snapshot_stride=a.snapshot_stride,
                enstrophy_budget=bool(a.budget_csv))


def check_memory_reference(ref, a, current):
    if ref.get('status') not in ('completed', 'stopped_max_steps') or ref.get('steps', 0) < 5:
        raise ValueError('memory reference needs at least five successful steps')
    if ref.get('memory_signature') != memory_signature(a) or ref.get('source_sha256') != source_hashes():
        raise ValueError('memory reference must match source, scheme, precision and diagnostics')
    if ref.get('torch') != torch.__version__ or ref.get('cuda') != torch.version.cuda:
        raise ValueError('memory reference must match PyTorch and CUDA versions')
    n = ref.get('parameters', {}).get('N', 0)
    if not 768 <= n < a.N:
        raise ValueError('reference grid must be >=768 and smaller than target')
    mem = ref.get('memory', {})
    if mem.get('gpu') != current['gpu']:
        raise ValueError('reference must use the same GPU model')
    if a.snapshot_times and ref.get('snapshots_written', 0) == 0:
        raise ValueError('reference did not exercise snapshot output')
    peak = max(mem.get('peak_allocated_GB', 0), mem.get('peak_reserved_GB', 0))
    if not math.isfinite(peak) or peak <= 0:
        raise ValueError('invalid measured memory peak')
    estimate = peak * (a.N / n)**3
    limit = min(current['total_GB'], current['free_GB']) * a.max_gpu_fraction
    if estimate > limit:
        raise ValueError(f'projected {estimate:.2f} GB exceeds memory limit {limit:.2f} GB')
    return estimate


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=['tubes', 'tgv'], default='tubes')
    p.add_argument('--N', type=int, default=256)
    p.add_argument('--nu', type=float, default=5e-4)
    p.add_argument('--target_t', type=float, default=1.)
    p.add_argument('--cfl', type=float, default=.35)
    p.add_argument('--max_dt', type=float, default=.01)
    p.add_argument('--log_dt', type=float, default=.01)
    p.add_argument('--scheme', choices=['ssprk3','lsrk4'], default='ssprk3')
    p.add_argument('--device', default='cpu')
    p.add_argument('--fp64', action='store_true')
    p.add_argument('--csv', default='run_v3.csv')
    p.add_argument('--spectrum_csv')
    p.add_argument('--spectrum_slab', type=int, default=4)
    p.add_argument('--spectrum_stride', type=int, default=10)
    p.add_argument('--budget_csv')
    p.add_argument('--snapshot_times', default='')
    p.add_argument('--snapshot_stride', type=int, default=4)
    p.add_argument('--snapshot_dir', default='snapshots_v3')
    p.add_argument('--max_steps', type=int, default=0)
    p.add_argument('--abort_on_energy_rise', type=float, default=1e-4)
    p.add_argument('--abort_on_interval_energy_rise', type=float, default=1e-5)
    p.add_argument('--tail_warn', type=float, default=1e-6)
    p.add_argument('--abort_on_tail', type=float, default=0.)
    p.add_argument('--max_divergence', type=float, default=0.)
    p.add_argument('--preflight_only', action='store_true')
    p.add_argument('--allow_large_grid', action='store_true')
    p.add_argument('--memory_reference', help='v3 JSON manifest from measured same-config N>=768 run')
    p.add_argument('--max_gpu_fraction', type=float, default=.8)
    return p


def validate_args(a):
    floats = [v for v in vars(a).values() if isinstance(v, float)]
    if not all(math.isfinite(v) for v in floats):
        raise ValueError('all numeric parameters must be finite')
    if a.N < 6 or a.N % 2 or a.nu < 0 or not 0 < a.cfl <= 1:
        raise ValueError('require even N>=6, nu>=0, 0<cfl<=1')
    if min(a.max_dt, a.target_t, a.log_dt) <= 0:
        raise ValueError('max_dt, target_t and log_dt must be positive')
    if min(a.spectrum_slab, a.spectrum_stride, a.snapshot_stride) < 1 or a.max_steps < 0:
        raise ValueError('strides/slab must be positive; max_steps must be nonnegative')
    if not 0 < a.max_gpu_fraction <= .8:
        raise ValueError('max_gpu_fraction must be in (0, .8]')
    if min(a.abort_on_energy_rise, a.abort_on_interval_energy_rise, a.tail_warn,
           a.abort_on_tail, a.max_divergence) < 0:
        raise ValueError('watchdog thresholds must be nonnegative')
    times = sorted(set(float(s) for s in a.snapshot_times.split(',') if s.strip()))
    if any(not math.isfinite(t) or not 0 <= t <= a.target_t for t in times):
        raise ValueError('snapshot times must be finite and within [0,target_t]')
    return times


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    try:
        pending = validate_args(a)
        device = torch.device(a.device)
        if device.type not in ('cpu','cuda'):
            raise ValueError('only CPU and CUDA devices supported')
        if device.type == 'cuda':
            if device.index is None:
                device = torch.device('cuda', torch.cuda.current_device())
            torch.cuda.set_device(device)
            torch.cuda.reset_peak_memory_stats(device)
        current = memory_state(device)
        if a.N >= 768 and not a.allow_large_grid and not a.preflight_only:
            raise ValueError('N>=768 requires --allow_large_grid')
        if a.N >= 1024:
            if device.type != 'cuda' or not a.memory_reference:
                raise ValueError('N>=1024 requires CUDA and a measured --memory_reference manifest')
            estimate = check_memory_reference(json.loads(Path(a.memory_reference).read_text()), a, current)
            print(f'PROJECTED_PEAK_GB={estimate:.3f}; extrapolation does not guarantee allocation safety')
        if a.preflight_only:
            print(json.dumps(dict(N=a.N, memory=current, signature=memory_signature(a)), indent=2))
            return 0
    except (ValueError, RuntimeError, OSError) as e:
        p.error(str(e))

    manifest_path = Path(a.csv + '.json')
    manifest = dict(parameters=vars(a), source_sha256=source_hashes(),
                    memory_signature=memory_signature(a), python=sys.version,
                    platform=platform.platform(), torch=torch.__version__, cuda=torch.version.cuda,
                    numpy=np.__version__, status='initializing', steps=0, t=0., snapshots_written=0)
    outputs = [Path(x) for x in (a.csv, a.spectrum_csv, a.budget_csv, str(manifest_path)) if x]
    if len(set(x.resolve() for x in outputs)) != len(outputs):
        p.error('output paths must be distinct')
    if any(x.exists() for x in outputs):
        p.error('output already exists; use a new run directory')
    for x in outputs:
        x.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    try:
        with ExitStack() as stack:
            def writer(path, header):
                if not path:
                    return None
                f = stack.enter_context(open(path, 'x', newline='', buffering=1))
                w = csv.writer(f)
                w.writerow(header)
                return w
            W = writer(a.csv, ['step','t','dt','E','Z','eps','dEdt_fd','budget_resid_rel',
                               'wmax','bkm','tail_ratio','div_max','wall_s','peak_mem_GB'])
            SW = writer(a.spectrum_csv, ['t','shell_k','E_shell_mean_density'])
            BW = writer(a.budget_csv, ['t','production','grad_omega_sq','dZdt_rhs','residual'])
            S = Solver(a.N, a.nu, a.cfl, a.max_dt, device, torch.float64 if a.fp64 else torch.float32)
            S.spectrum_slab = a.spectrum_slab
            U = S.ic_tubes() if a.case == 'tubes' else S.ic_tgv()
            R = [torch.zeros_like(u) for u in U] if a.scheme == 'lsrk4' else None
            t = dt = bkm = 0.
            step = records = 0
            prev = None
            E0 = None
            next_log = a.log_dt
            while True:
                stop = bool(a.max_steps and step >= a.max_steps)
                final = t >= a.target_t
                log = prev is None or t >= next_log or final or stop
                if log:
                    E, Z, wm, div, tail = S.diagnostics(U)
                    if not all(math.isfinite(x) for x in (E,Z,wm,div,tail)):
                        raise FloatingPointError('nonfinite diagnostic')
                    if E0 is None:
                        E0 = E
                    dEdt = resid = ''
                    if prev is not None:
                        tp, Ep, wp, Zp = prev
                        bkm += .5*(wp+wm)*(t-tp)
                        dEdt = (E-Ep)/(t-tp)
                        eps_mid = a.nu*(Z+Zp)
                        resid = (dEdt+eps_mid)/eps_mid if eps_mid > 0 else ''
                    if SW and (records % a.spectrum_stride == 0 or final or stop):
                        bins = S.spectrum_shells(U).cpu().tolist()
                        SW.writerows((t,k,e) for k,e in enumerate(bins))
                    if BW:
                        budget = S.enstrophy_budget(U)
                        if not all(math.isfinite(x) for x in budget.values()):
                            raise FloatingPointError('nonfinite enstrophy budget')
                        BW.writerow([t, *budget.values()])
                    mem = memory_state(device)
                    W.writerow([step,t,dt,E,Z,2*a.nu*Z,dEdt,resid,wm,bkm,tail,div,
                                time.perf_counter()-start,mem.get('peak_allocated_GB',0)])
                    if tail > a.tail_warn:
                        print(f'WARN tail={tail:.4g} at t={t:.8g}', flush=True)
                    if a.abort_on_tail and tail > a.abort_on_tail:
                        raise FloatingPointError('tail threshold exceeded')
                    if a.max_divergence and div > a.max_divergence:
                        raise FloatingPointError('divergence threshold exceeded')
                    if E > E0*(1+a.abort_on_energy_rise):
                        raise FloatingPointError('energy exceeds initial threshold')
                    if prev is not None and E > prev[1]+a.abort_on_interval_energy_rise*E0:
                        raise FloatingPointError('interval energy rise')
                    prev = t,E,wm,Z
                    records += 1
                    if t >= next_log:
                        next_log = (math.floor(t/a.log_dt)+1)*a.log_dt
                        if next_log <= t:
                            next_log = t+a.log_dt
                while pending and t >= pending[0]:
                    requested = pending.pop(0)
                    out = Path(a.snapshot_dir) / f'omega_{manifest["snapshots_written"]:05d}_t{t:.17g}.npz'
                    if out.exists():
                        raise FileExistsError(out)
                    S.save_vorticity_snapshot(U, out, a.snapshot_stride, t, requested)
                    manifest['snapshots_written'] += 1
                if final or stop:
                    manifest['status'] = 'completed' if final else 'stopped_max_steps'
                    break
                end = min(a.target_t, next_log, pending[0] if pending else a.target_t)
                if a.scheme == 'ssprk3':
                    dt, _ = S.step_ssprk3(U,t,end)
                else:
                    dt, _ = S.step_lsrk4(U,R,t,end)
                if not math.isfinite(dt) or dt <= 0 or t+dt <= t:
                    raise FloatingPointError('timestep failed to advance time')
                t = end if dt == end-t else t+dt
                step += 1
                manifest.update(t=t, steps=step)
    except Exception as e:
        manifest.update(status='failed', error=f'{type(e).__name__}: {e}')
        print(manifest['error'], file=sys.stderr, flush=True)
    finally:
        manifest['wall_s'] = time.perf_counter()-start
        manifest['memory'] = memory_state(device)
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
        print(f'SUMMARY status={manifest["status"]} steps={manifest["steps"]} t={manifest["t"]:.9g}', flush=True)
    return 0 if manifest['status'] == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
