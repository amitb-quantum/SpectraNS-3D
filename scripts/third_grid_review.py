"""Read-only planning helpers for the proposed N640 spatial comparison."""
from decimal import Decimal, ROUND_FLOOR
import math

def lifetime_seconds(rate_usd,cap_usd=14,reserve_usd=.5,maximum_seconds=10800):
    rate,cap,reserve=map(lambda x:Decimal(str(x)),(rate_usd,cap_usd,reserve_usd))
    if not all(x.is_finite() for x in (rate,cap,reserve)) or rate<=0 or reserve<Decimal('.5') or cap>14 or cap<=reserve:
        raise ValueError('require finite positive rate, cap<=14, and reserve>=0.5')
    return min(maximum_seconds,int(((cap-reserve)*3600/rate).to_integral_value(rounding=ROUND_FLOOR)))

def runtime_forecast(step_seconds,diagnostic_seconds,checkpoint_seconds,remaining_steps,
                     diagnostic_events,checkpoint_events,remaining_lifetime_seconds,
                     fine_steps=400,setup_preflight_seconds=300,collection_cleanup_seconds=600,
                     safety_factor=1.25):
    values=(step_seconds,diagnostic_seconds,checkpoint_seconds,remaining_steps,diagnostic_events,
            checkpoint_events,remaining_lifetime_seconds,fine_steps,setup_preflight_seconds,
            collection_cleanup_seconds,safety_factor)
    if not all(math.isfinite(x) and x>=0 for x in values) or safety_factor<1:
        raise ValueError('invalid measured runtime forecast')
    compute=(remaining_steps+fine_steps)*step_seconds+diagnostic_events*diagnostic_seconds+checkpoint_events*checkpoint_seconds
    bound=safety_factor*compute+setup_preflight_seconds+collection_cleanup_seconds
    return dict(forecast_seconds=bound,remaining_lifetime_seconds=remaining_lifetime_seconds,
                fits=bound<=remaining_lifetime_seconds,compute_uninflated_seconds=compute)

def checkpoint_collection(history,last_accepted_t):
    eligible=[x for x in history if x.get('retained') and x['t']<=last_accepted_t+1e-12]
    if not eligible:raise ValueError('no retained accepted checkpoint')
    last=max(eligible,key=lambda x:(x['t'],x['kind']=='terminal'))
    anchors=[x for x in eligible if .05-1e-12<=last_accepted_t-x['t']<=.2+1e-12]
    anchor=max(anchors,key=lambda x:x['t']) if anchors else None
    return dict(collect_full_fields=[last['path']],fine_window_anchor=None if anchor is None else anchor['path'],
                accepted_checkpoint_t=last['t'],diagnostic_accepted_end_t=last_accepted_t,
                preserve_all_metadata_and_hashes=True,
                prune_other_fields_only_after_fine_validation_and_metadata_archival=True)

def sampled_peak_comparison(left,right,relative_tolerance=.001,time_tolerance=.01):
    if not left or [x[0] for x in left]!=[x[0] for x in right]:
        raise ValueError('peaks need identical accepted event times')
    if not all(math.isfinite(t) and math.isfinite(v) for curve in (left,right) for t,v in curve):
        raise ValueError('nonfinite peak data')
    a=max(left,key=lambda x:x[1]);b=max(right,key=lambda x:x[1])
    error=abs(a[1]-b[1])/max(abs(a[1]),abs(b[1]),1e-14)
    censored=a[0] in (left[0][0],left[-1][0]) or b[0] in (right[0][0],right[-1][0])
    passed=error<=relative_tolerance and abs(a[0]-b[0])<=time_tolerance+1e-12 and not censored
    return dict(left_t=a[0],right_t=b[0],relative_value_difference=error,
                time_difference=abs(a[0]-b[0]),boundary_censored=censored,
                sampled_peak_agreement=passed,
                scope='Sampled two-grid agreement; no continuous-time peak, spatial order or regularity certification.')


def transfer_allowance(bytes_to_transfer,trial_bytes_per_second,compression_seconds=0,
                       verification_seconds=0,cleanup_seconds=60,safety_factor=1.5):
    """Budget using the slowest measured end-to-end trial, never advertised Mbps."""
    rates=list(trial_bytes_per_second)
    values=[bytes_to_transfer,compression_seconds,verification_seconds,cleanup_seconds,safety_factor,*rates]
    if not rates or not all(math.isfinite(x) for x in values) or min(rates)<=0 or min(values[:-len(rates)])<0 or safety_factor<1:
        raise ValueError('invalid measured collection allowance')
    return dict(seconds=safety_factor*(bytes_to_transfer/min(rates)+compression_seconds+verification_seconds)+cleanup_seconds,
                measured_lower_bytes_per_second=min(rates),bytes_to_transfer=bytes_to_transfer)

def protected_phase_forecast(step_seconds,diagnostic_seconds,checkpoint_seconds,
                             remaining_lifetime_seconds,small_artifact_collection_seconds,
                             setup_preflight_seconds=0,safety_factor=1.25,
                             *,coarse_start_t=0.,refinement_seconds=0.,refinement_events=0,coarse_steps_override=None):
    """Separate always-on diagnostics from the declared selective refinement cost."""
    if not 0<=coarse_start_t<=.05 or not math.isfinite(refinement_seconds) or refinement_seconds<0 or type(refinement_events)is not int or refinement_events<0:
        raise ValueError("invalid retained-prefix/refinement forecast")
    steps=round((1.1-coarse_start_t)/.0005)
    if coarse_steps_override is not None:
        if type(coarse_steps_override)is not int or coarse_steps_override<steps:
            raise ValueError("measured step override may only increase fixed-cap forecast")
        steps=coarse_steps_override
    events=round((1.1-coarse_start_t)/.01)+1+11
    result=runtime_forecast(step_seconds,diagnostic_seconds,checkpoint_seconds,steps,events,12,
                            remaining_lifetime_seconds,fine_steps=400,
                            setup_preflight_seconds=setup_preflight_seconds,
                            collection_cleanup_seconds=small_artifact_collection_seconds,
                            safety_factor=safety_factor)
    added=refinement_seconds*refinement_events
    result["compute_uninflated_seconds"]+=added
    result["forecast_seconds"]+=safety_factor*added
    result["fits"]=result["forecast_seconds"]<=remaining_lifetime_seconds
    result.update(coarse_start_t=coarse_start_t,remaining_coarse_steps=steps,fine_steps=400,
                  diagnostic_events=events,refinement_events=refinement_events,
                  refinement_seconds_per_call=refinement_seconds,checkpoint_events=12)
    return result

def exploration_ready(record):
    """Planning status gate; the controller must independently verify these receipts."""
    required=('prefix_numerical_gates_passed','local_temporal_window_passed',
              'spatial_comparison_recorded','small_artifacts_hash_verified_in_wsl')
    return all(record.get(k) is True for k in required)

def fit_local_peak(curve):
    """Fit a bracketed sampled maximum. Sensitivity is not a statistical confidence interval."""
    import numpy as np
    if len(curve)<3 or not all(math.isfinite(v) for row in curve for v in row):
        raise ValueError('finite peak samples required')
    times=np.array([x[0] for x in curve],dtype=float)
    values=np.array([x[1] for x in curve],dtype=float)
    if np.any(np.diff(times)<=0):
        raise ValueError('peak sample times must increase strictly')
    index=int(np.argmax(values))
    base=dict(sampled_t=float(times[index]),sampled_value=float(values[index]),
              accepted_range=[float(times[0]),float(times[-1])],
              scope='Observed local episode only; no global maximum or confidence-interval certification.')
    if index==0 or index==len(curve)-1:
        return dict(base,status='boundary_censored')
    if index<2 or index>len(curve)-3:
        return dict(base,status='insufficient_five_point_bracket')
    fitted=[]
    for width in (3,5):
        radius=width//2
        ts=times[index-radius:index+radius+1]
        ys=values[index-radius:index+radius+1]
        spacing=float(np.median(np.diff(ts)))
        if not np.allclose(np.diff(ts),spacing,rtol=1e-8,atol=1e-14):
            raise ValueError('peak fit needs uniform diagnostic spacing')
        x=(ts-times[index])/spacing
        a,b,c=np.linalg.lstsq(np.column_stack((x*x,x,np.ones_like(x))),ys,rcond=None)[0]
        if a>=-64*np.finfo(float).eps*max(float(np.max(np.abs(ys))),1e-300):
            return dict(base,status='flat_or_nonconcave_fit')
        vertex=-b/(2*a)
        if abs(vertex)>1+1e-12:
            return dict(base,status='vertex_outside_neighbor_bracket')
        residual=float(np.max(np.abs(ys-(a*x*x+b*x+c))))
        fitted.append(dict(points=width,t=float(times[index]+vertex*spacing),
                           value=float(c-b*b/(4*a)),curvature=float(2*a/spacing**2),
                           residual_max=residual,spacing=spacing,
                           residual_time_scale=float(spacing*math.sqrt(residual/abs(a)))))
    three,five=fitted
    time_radius=max(five['spacing']/2,abs(five['t']-three['t']),five['residual_time_scale'])
    value_radius=abs(five['value']-three['value'])+five['residual_max']
    return dict(base,status='estimated',fits=fitted,fitted_t=five['t'],fitted_value=five['value'],
                time_sensitivity_radius=time_radius,value_sensitivity_radius=value_radius,
                uncertainty_convention='Maximum of half-event spacing, 3/5-point vertex shift and residual/curvature time scale; value uses window shift plus max residual. Heuristic fit sensitivity only.')

def compare_fitted_local_peaks(left,right,relative_tolerance=.001,time_tolerance=.01):
    """Supplementary comparison allows different accepted horizons and never controls core status."""
    a,b=fit_local_peak(left),fit_local_peak(right)
    result=dict(left=a,right=b,controls_protected_validation=False)
    if a['status']!='estimated' or b['status']!='estimated':
        return dict(result,status='inconclusive')
    dt=abs(a['fitted_t']-b['fitted_t'])
    tu=a['time_sensitivity_radius']+b['time_sensitivity_radius']
    dv=abs(a['fitted_value']-b['fitted_value'])
    vu=a['value_sensitivity_radius']+b['value_sensitivity_radius']
    vt=relative_tolerance*max(abs(a['fitted_value']),abs(b['fitted_value']),1e-14)
    if max(0,dt-tu)>time_tolerance+1e-12 or max(0,dv-vu)>vt:
        status='separated_estimates'
    elif dt+tu<=time_tolerance+1e-12 and dv+vu<=vt:
        status='within_declared_tolerances'
    else:
        status='inconclusive'
    return dict(result,status=status,time_difference=dt,value_relative_difference=dv/max(abs(a['fitted_value']),abs(b['fitted_value']),1e-14))

def measured_step_plan(rows,start_t=.05,end_t=1.1,log_dt=.01,cap_dt=.0005,safety=.9):
    """Separate legitimate event truncation from ordinary stability-controlled steps."""
    if not rows or not 0<safety<=1 or not 0<=start_t<end_t or not log_dt>0:
        raise ValueError("invalid measured step plan")
    ordinary=[];events=0;limits={}
    for r in rows:
        dt=float(r["dt"]);limits_row=[float(r[k]) for k in ("cap_dt","cfl_dt","viscous_dt")]
        if not all(math.isfinite(v) and v>1e-12 for v in (dt,*limits_row)):
            raise ValueError("nonfinite, nonpositive or roundoff-sized step")
        if dt>min(limits_row)*(1+1e-10):
            raise ValueError("recorded step exceeds its stability/cap limit")
        limiter=r["limiter"]
        if limiter not in ("cap","cfl","viscous","event"):raise ValueError("unknown limiter")
        limits[limiter]=limits.get(limiter,0)+1
        if limiter=="event":events+=1
        else:ordinary.append(dt)
    if not ordinary:raise ValueError("ordinary step timing required")
    minimum=min(ordinary)
    if minimum>cap_dt*(1+1e-10):raise ValueError("ordinary step exceeds declared cap")
    floor=safety*minimum
    if floor<=.00025:raise ValueError("stability floor cannot support declared fine cap; revise temporal specification")
    n_event=round((end_t-start_t)/log_dt)
    if abs(start_t+n_event*log_dt-end_t)>1e-11:raise ValueError("off-lattice endpoint")
    steps=math.ceil((end_t-start_t)/floor)+n_event
    return dict(ordinary_min_dt=minimum,planning_dt_floor=floor,dt_floor_factor=safety,
        limiter_counts=limits,event_truncated_steps_observed=events,
        remaining_coarse_steps=steps,event_alignment_step_allowance=n_event,
        cap_only_remaining_steps=round((end_t-start_t)/cap_dt),
        qualification="Planning allowance, not a future CFL bound; per-event measured remaining-phase refusal stays active.")
