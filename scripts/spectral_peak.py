"""Memory-bounded Fourier refinement of several sampled vorticity peaks.

This is an estimate of a local maximum, not a certified global supremum.
No global zero padding and no simultaneous three-component real vorticity.
"""
import math
import torch

METHOD = dict(name="separable Fourier local search", seeds=8, expanded_seeds=16,
              patch_points=5, initial_radius_grid_cells=4, levels=9, stability_tolerance=1e-5,
              scope="local peak estimate; seed and search sensitivity are not rigorous error bounds")

def evaluate_cartesian(S, U, x, y, z):
    """Exact trigonometric evaluation of the dealiased rfft vector curl."""
    cdtype=U[0].dtype
    def basis(coords,k):
        c=torch.as_tensor(coords,dtype=S.dt_,device=S.dev)
        return torch.exp(1j*c[:,None]*k.reshape(1,-1)).to(cdtype)
    ax=basis(x,S.kx);ay=basis(y,S.ky);az=basis(z,S.kz)
    weights=torch.full((S.N//2+1,),2.,device=S.dev,dtype=S.dt_)
    weights[0]=weights[-1]=1.
    az=az*weights
    result=torch.zeros((len(x),len(y),len(z)),dtype=S.dt_,device=S.dev)
    for i in range(3):
        coefficients=S.curl_component(U,i)
        # The strict spherical mask excludes every Nyquist mode, eliminating
        # the ambiguity of off-grid interpolation of a sampled Nyquist wave.
        a=(ax @ coefficients.reshape(S.N,-1)).reshape(len(x),S.N,-1)
        del coefficients
        b=torch.einsum('yj,xjk->xyk',ay,a)
        del a
        field=(b @ az.T).real/S.N**3
        result.add_(field.square())
        del b,field
    return result.sqrt()

def sampled_seeds(S,U,count):
    magnitude=torch.zeros((S.N,S.N,S.N),device=S.dev,dtype=S.dt_)
    for i in range(3):
        w=S.ifft(S.curl_component(U,i))
        magnitude.add_(w.square())
        del w
    maximum=float(magnitude.max().sqrt().item())
    seeds=[]
    for _ in range(count):
        flat=int(magnitude.argmax().item())
        ix=flat//(S.N*S.N);iy=(flat//S.N)%S.N;iz=flat%S.N
        seeds.append([ix*S.dx,iy*S.dx,iz*S.dx])
        # Distinct candidate neighborhoods, with periodic exclusion.
        offsets=torch.arange(-3,4,device=S.dev)
        xs=(ix+offsets)%S.N;ys=(iy+offsets)%S.N;zs=(iz+offsets)%S.N
        magnitude[xs[:,None,None],ys[None,:,None],zs[None,None,:]]=-1
    return maximum,seeds

def refine(S,U,*,seeds=8,expanded_seeds=16,levels=9,points=5,tolerance=1e-5):
    if S.dt_!=torch.float64 or not 1<=seeds<=expanded_seeds<=16 or points!=5 or levels<3:
        raise ValueError("fixed fp64 peak refinement requires valid seeds and >=3 levels")
    sampled,starts=sampled_seeds(S,U,expanded_seeds)
    answers=[]
    for initial in starts:
        center=list(initial);radius=4*S.dx;old=0.;increment=0.
        for level in range(levels):
            coords=[[v+radius*j/2 for j in (-2,-1,0,1,2)] for v in center]
            values=evaluate_cartesian(S,U,*coords)
            idx=int(values.argmax().item());best=float(values.flatten()[idx].item())
            indices=(idx//25,(idx//5)%5,idx%5)
            center=[coords[k][indices[k]]%(2*math.pi) for k in range(3)]
            increment=abs(best-old)/max(best,1e-300);old=best
            radius/=2
        answers.append(dict(value=old,location=center,last_level_relative_increment=increment))
    early=max(answers[:seeds],key=lambda a:a["value"])
    best=max(answers,key=lambda a:a["value"])
    seed_delta=abs(best["value"]-early["value"])/max(best["value"],1e-300)
    if best["value"]+1e-11*max(sampled,1)<sampled:
        raise ValueError("Fourier interpolation fell below sampled maximum")
    refined=max(best["value"],sampled)
    return dict(sampled_wmax=sampled,fourier_refined_peak_estimate=refined,
                sampling_bias_fraction=(refined-sampled)/max(refined,1e-300),
                location=best["location"],seed_expansion_relative_change=seed_delta,
                last_level_relative_increment=best["last_level_relative_increment"],
                estimator_stable=seed_delta<=tolerance and best["last_level_relative_increment"]<=tolerance,
                method=dict(METHOD,seeds=seeds,expanded_seeds=expanded_seeds,levels=levels),
                candidates=answers)
