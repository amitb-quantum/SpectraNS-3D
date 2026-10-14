"""Predeclared selective Fourier diagnostics; sampled maxima remain at every event."""
import math

def selected(t, phase, p, *, continued=False):
    if not math.isfinite(t):
        raise ValueError("nonfinite diagnostic time")
    close=lambda a: abs(t-a)<=1e-11
    if phase=="fine":
        return close(p["anchor"]) or close(p["prefix"])
    if phase=="reload":
        return True
    if phase=="preflight":
        return close(0.) or close(p["preflight_t"])
    if phase not in ("coarse","exploration"):
        raise ValueError("unknown sampling phase")
    if phase=="coarse" and continued and close(p["preflight_t"]):
        return False  # The verified preflight endpoint supplies this estimate.
    index=round(t/p["log_dt"])
    if abs(t-index*p["log_dt"])>1e-11:
        raise ValueError("diagnostic is off the declared event lattice")
    lo,hi=(86,94) if p["N"]==768 else (8,9)
    return index%5==0 or lo<=index<=hi or close(p["anchor"]) or close(p["prefix"]) or close(p["preflight_t"])

def count_remaining(p):
    start=round(p["preflight_t"]/p["log_dt"])
    end=round(p["prefix"]/p["log_dt"])
    fine_start=round(p["anchor"]/p["log_dt"])
    coarse=sum(selected(i*p["log_dt"],"coarse",p,continued=True) for i in range(start,end+1))
    fine=sum(selected(i*p["log_dt"],"fine",p) for i in range(fine_start,end+1))
    return dict(coarse=coarse,fine=fine,total=coarse+fine,
                coarse_diagnostic_events=end-start+1,
                fine_diagnostic_events=end-fine_start+1)
