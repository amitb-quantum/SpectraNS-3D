#!/usr/bin/env python3
"""Pseudo-spectral incompressible Navier-Stokes on the 2pi-periodic cube (GPU/CPU, PyTorch).

Rotational form  du/dt = P[u x omega] - nu k^2 u   (9 FFTs per RHS evaluation),
2/3 spherical dealiasing, SSP-RK3 (3 stages) or Carpenter-Kennedy LSRK4 (5 stages),
adaptive CFL time step, and verification diagnostics written to CSV:
  E, enstrophy Z, dissipation eps = 2 nu Z, energy-budget residual (dE/dt + eps),
  ||w||_inf, BKM integral (trapezoid), spectral tail ratio E(k_cut-1)/max E(k), div check.
"""
import argparse, csv, math, os, sys, time
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import torch

LSRK_A = [0.0, -567301805773.0/1357537059087.0, -2404267990393.0/2016746695238.0,
          -3550918686646.0/2091501179385.0, -1275806237668.0/842570457699.0]
LSRK_B = [1432997174477.0/9575080441755.0, 5161836677717.0/13612068292357.0,
          1720146321549.0/2090206949498.0, 3134564353537.0/4481467310338.0,
          2277821191437.0/14882151754819.0]  # Carpenter & Kennedy (1994), NASA TM-109112, (5,4) 2N-storage


class Solver:
    def __init__(self, N, nu, cfl=0.35, max_dt=1e-2, device="cuda", dtype=torch.float32):
        self.N, self.nu, self.cfl, self.max_dt = N, nu, cfl, max_dt
        self.dev, self.dt_ = torch.device(device), dtype
        self.dx = 2 * math.pi / N
        k = torch.fft.fftfreq(N, d=1.0 / N, device=self.dev, dtype=dtype)
        kz = torch.fft.rfftfreq(N, d=1.0 / N, device=self.dev, dtype=dtype)
        self.kx, self.ky, self.kz = k.view(N, 1, 1), k.view(1, N, 1), kz.view(1, 1, -1)
        self.K2 = self.kx**2 + self.ky**2 + self.kz**2
        self.K2[0, 0, 0] = 1.0
        self.kcut = N // 3
        self.dealias = (self.K2 < (N / 3.0) ** 2)
        self.s = (N, N, N)
        # shell index for spectra (computed once, int64 needed by scatter_add)
        self.shell = None

    # ---------- transforms ----------
    def ifft(self, a):
        return torch.fft.irfftn(a, s=self.s)

    def fft(self, a):
        return torch.fft.rfftn(a)

    def curl_h(self, u, v, w):
        return (1j * (self.ky * w - self.kz * v), 1j * (self.kz * u - self.kx * w), 1j * (self.kx * v - self.ky * u))

    def project(self, fu, fv, fw):
        d = (self.kx * fu + self.ky * fv + self.kz * fw) / self.K2
        fu.sub_(self.kx * d); fv.sub_(self.ky * d); fw.sub_(self.kz * d)
        return fu, fv, fw

    # ---------- RHS (rotational form, 9 FFTs) ----------
    def rhs(self, uh, vh, wh, want_umax=False):
        u, v, w = self.ifft(uh), self.ifft(vh), self.ifft(wh)
        umax = torch.sqrt((u * u + v * v + w * w).max()).item() if want_umax else None
        oxh, oyh, ozh = self.curl_h(uh, vh, wh)
        ox = self.ifft(oxh); del oxh
        oy = self.ifft(oyh); del oyh
        oz = self.ifft(ozh); del ozh
        # u x omega
        fu = self.fft(v * oz - w * oy)
        fv = self.fft(w * ox - u * oz)
        fw = self.fft(u * oy - v * ox)
        del u, v, w, ox, oy, oz
        fu.mul_(self.dealias); fv.mul_(self.dealias); fw.mul_(self.dealias)
        self.project(fu, fv, fw)
        nk = self.nu * self.K2
        fu.sub_(nk * uh); fv.sub_(nk * vh); fw.sub_(nk * wh)
        return (fu, fv, fw), umax

    def get_dt(self, umax):
        dt = self.cfl * self.dx / max(umax, 1e-6)
        if self.nu > 0:
            dt = min(dt, 0.25 * self.dx**2 / self.nu)
        return min(dt, self.max_dt)

    # ---------- integrators ----------
    def step_ssprk3(self, U, t, t_end):
        (r, umax) = self.rhs(*U, want_umax=True)
        dt = min(self.get_dt(umax), t_end - t)
        U1 = [a + dt * b for a, b in zip(U, r)]; del r
        r, _ = self.rhs(*U1)
        U2 = [0.75 * a + 0.25 * (a1 + dt * b) for a, a1, b in zip(U, U1, r)]; del U1, r
        r, _ = self.rhs(*U2)
        for a, a2, b in zip(U, U2, r):
            a.mul_(1.0 / 3.0).add_(a2 + dt * b, alpha=2.0 / 3.0)
        del U2, r
        for a in U: a.mul_(self.dealias)
        return dt, umax

    def step_lsrk4(self, U, R, t, t_end):
        dt, umax = None, None
        for s in range(5):
            r, um = self.rhs(*U, want_umax=(s == 0))
            if s == 0:
                umax = um; dt = min(self.get_dt(um), t_end - t)
            for a, res, b in zip(U, R, r):
                res.mul_(LSRK_A[s]).add_(b, alpha=dt)
                a.add_(res, alpha=LSRK_B[s])
            del r
        for a in U: a.mul_(self.dealias)
        return dt, umax

    # ---------- initial conditions ----------
    def ic_tubes(self, gamma=5.0, a=0.25, sep=0.6, pert=0.35):
        x = torch.arange(self.N, device=self.dev, dtype=self.dt_) * self.dx
        X, Y, Z = x.view(-1, 1, 1), x.view(1, -1, 1), x.view(1, 1, -1)
        p = pert * torch.sin(X)
        r1 = (Y - (math.pi - sep / 2) - p) ** 2 + (Z - math.pi) ** 2
        r2 = (Y - (math.pi + sep / 2) + p) ** 2 + (Z - math.pi) ** 2
        ox = (gamma / (math.pi * a * a)) * (torch.exp(-r1 / a**2) - torch.exp(-r2 / a**2))
        del r1, r2, p
        oxh = self.fft(ox) * self.dealias; del ox
        uh = torch.zeros_like(oxh)
        vh = 1j * self.kz * oxh / self.K2
        wh = -1j * self.ky * oxh / self.K2
        vh[0, 0, 0] = 0; wh[0, 0, 0] = 0
        return [uh * self.dealias, vh * self.dealias, wh * self.dealias]

    def ic_tgv(self):
        x = torch.arange(self.N, device=self.dev, dtype=self.dt_) * self.dx
        X, Y, Z = x.view(-1, 1, 1), x.view(1, -1, 1), x.view(1, 1, -1)
        u = torch.sin(X) * torch.cos(Y) * torch.cos(Z)
        v = -torch.cos(X) * torch.sin(Y) * torch.cos(Z)
        w = torch.zeros_like(u)
        return [self.fft(u) * self.dealias, self.fft(v) * self.dealias, self.fft(w) * self.dealias]

    # ---------- diagnostics ----------
    def spectrum_tail(self, U):
        if self.shell is None:
            self.shell = torch.round(torch.sqrt(self.K2)).to(torch.int64).clamp_(max=self.kcut + 1).flatten()
        e = sum(a.real**2 + a.imag**2 for a in U)
        e[:, :, 1:-1] *= 2.0
        bins = torch.zeros(self.kcut + 2, device=self.dev, dtype=self.dt_)
        bins.scatter_add_(0, self.shell, e.flatten())
        peak = bins[1:self.kcut].max().item()
        return bins[self.kcut - 1].item() / max(peak, 1e-300)

    def diagnostics(self, U):
        # state stays float32; global reductions done in float64 to avoid round-off in E, Z budgets
        E = 0.0
        for a in U:
            c = self.ifft(a).double(); E += 0.5 * (c * c).mean().item(); del c
        div = self.ifft(1j * (self.kx * U[0] + self.ky * U[1] + self.kz * U[2])).abs().max().item()
        o2 = None
        for oh in self.curl_h(*U):
            c = self.ifft(oh).double(); del oh
            o2 = c * c if o2 is None else o2.add_(c * c); del c
        Z = 0.5 * o2.mean().item()
        wmax = math.sqrt(o2.max().item()); del o2
        return E, Z, wmax, div, self.spectrum_tail(U)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["tubes", "tgv"], default="tubes")
    ap.add_argument("--N", type=int, default=256)
    ap.add_argument("--nu", type=float, default=5e-4)
    ap.add_argument("--target_t", type=float, default=1.0)
    ap.add_argument("--cfl", type=float, default=0.35)
    ap.add_argument("--max_dt", type=float, default=1e-2)
    ap.add_argument("--scheme", choices=["ssprk3", "lsrk4"], default="ssprk3")
    ap.add_argument("--log_dt", type=float, default=0.01, help="diagnostic interval in simulation time")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--fp64", action="store_true")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--abort_on_energy_rise", type=float, default=1e-4)
    a = ap.parse_args()

    dtype = torch.float64 if a.fp64 else torch.float32
    S = Solver(a.N, a.nu, a.cfl, a.max_dt, a.device, dtype)
    U = S.ic_tubes() if a.case == "tubes" else S.ic_tgv()
    R = [torch.zeros_like(c) for c in U] if a.scheme == "lsrk4" else None
    csv_path = a.csv or f"{a.case}_N{a.N}_nu{a.nu:g}_{a.scheme}.csv"
    f = open(csv_path, "w", newline=""); W = csv.writer(f)
    W.writerow(["step", "t", "dt", "E", "Z", "eps", "dEdt_fd", "budget_resid_rel", "wmax", "bkm", "tail_ratio", "div_max", "wall_s", "peak_mem_GB"])
    hdr = f"case={a.case} N={a.N}^3 nu={a.nu} scheme={a.scheme} cfl={a.cfl} dtype={dtype} device={a.device}"
    print(hdr, flush=True)
    if S.dev.type == "cuda":
        print("GPU:", torch.cuda.get_device_name(0), flush=True)

    t, step, bkm = 0.0, 0, 0.0
    E0, Z0, w0, div0, tail0 = S.diagnostics(U)
    prev = (t, E0, w0, Z0)
    W.writerow([0, 0.0, 0.0, E0, Z0, 2 * a.nu * Z0, "", "", w0, 0.0, tail0, div0, 0.0, 0.0]); f.flush()
    print(f"t=0 E={E0:.6e} Z={Z0:.6e} |w|inf={w0:.4f} tail={tail0:.2e}", flush=True)
    next_log = a.log_dt
    if S.dev.type == "cuda": torch.cuda.synchronize()
    t0 = time.time(); status = "completed"
    while t < a.target_t - 1e-12:
        if a.scheme == "ssprk3":
            dt, umax = S.step_ssprk3(U, t, a.target_t)
        else:
            dt, umax = S.step_lsrk4(U, R, t, a.target_t)
        t += dt; step += 1
        if t >= next_log - 1e-12 or t >= a.target_t - 1e-12:
            E, Z, wm, div, tail = S.diagnostics(U)
            tp, Ep, wp, Zp = prev
            bkm += 0.5 * (wp + wm) * (t - tp)
            dEdt = (E - Ep) / (t - tp)
            eps_mid = a.nu * (Z + Zp)  # 2 nu * mean(Z)
            resid = (dEdt + eps_mid) / max(eps_mid, 1e-300) if a.nu > 0 else float("nan")
            if S.dev.type == "cuda": torch.cuda.synchronize()
            wall = time.time() - t0
            mem = torch.cuda.max_memory_allocated() / 1e9 if S.dev.type == "cuda" else 0.0
            W.writerow([step, t, dt, E, Z, 2 * a.nu * Z, dEdt, resid, wm, bkm, tail, div, wall, mem]); f.flush()
            print(f"step={step} t={t:.4f} dt={dt:.2e} E={E:.6e} eps={2*a.nu*Z:.4e} resid={resid:+.2e} "
                  f"|w|inf={wm:.3f} (x{wm/w0:.3f}) BKM={bkm:.4f} tail={tail:.2e} div={div:.1e} "
                  f"{1000*wall/step:.1f}ms/step mem={mem:.1f}GB", flush=True)
            prev = (t, E, wm, Z)
            next_log += a.log_dt
            if a.nu > 0 and E > E0 * (1 + a.abort_on_energy_rise):
                status = "aborted_energy_rise"
                print(f"[ABORT] non-physical energy rise E={E:.6e} > E0={E0:.6e}, tail={tail:.2e}", flush=True)
                break
    wall = time.time() - t0
    print(f"SUMMARY status={status} steps={step} t={t:.4f} wall={wall:.1f}s ms/step={1000*wall/max(step,1):.2f} "
          f"dE/E0={(prev[1]-E0)/E0*100:.4f}% BKM={bkm:.5f} csv={csv_path}", flush=True)
    f.close()


if __name__ == "__main__":
    main()
