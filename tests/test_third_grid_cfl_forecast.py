import csv,copy,json,math
import pytest
from cloud_policy import ROOT
from extension_state import sha
from third_grid_review import measured_step_plan,protected_phase_forecast

def actual_rows():
    plan=json.loads((ROOT/"configs/n768_third_grid_proposal.json").read_text())
    name,digest=next(iter(plan["preflight"]["step_regression_reference"].items()))
    assert sha(ROOT/name)==digest
    with (ROOT/name).open(newline="") as f:return list(csv.DictReader(f))

def test_actual_768_CFL_and_event_remainders_produce_conservative_count():
    rows=actual_rows();r=measured_step_plan(rows)
    assert len(rows)==118
    assert r["limiter_counts"]=={"cfl":113,"event":5}
    assert r["ordinary_min_dt"]==pytest.approx(.0004315345212859038)
    assert r["planning_dt_floor"]==pytest.approx(.00038838106915731343)
    assert r["remaining_coarse_steps"]==2809
    assert r["event_alignment_step_allowance"]==105
    assert r["ordinary_min_dt"]>min(float(x["dt"]) for x in rows)*10
    coarse=2809
    bound=protected_phase_forecast(1.5299608710071988,1.1561707886867225,57.959347777068615,
        9000,180,coarse_start_t=.05,refinement_seconds=6.167240385897458,refinement_events=31,
        coarse_steps_override=coarse)
    assert bound["remaining_coarse_steps"]==2809 and bound["fine_steps"]==400
    assert bound["forecast_seconds"]==pytest.approx(7594.516303282616)
    assert bound["fits"]
    assert bound["forecast_seconds"]==pytest.approx(1.25*bound["compute_uninflated_seconds"]+180)

def test_forecast_cannot_be_reduced_and_still_refuses_short_lifetime():
    kwargs=dict(coarse_start_t=.05,coarse_steps_override=2809)
    assert not protected_phase_forecast(1.6,2,60,5000,180,**kwargs)["fits"]
    with pytest.raises(ValueError):protected_phase_forecast(1,1,1,9000,180,coarse_start_t=.05,coarse_steps_override=2099)

@pytest.mark.parametrize("field,value",[("dt","nan"),("dt","0"),("dt","1e-15"),("dt",".1"),("cfl_dt","-1"),("limiter","unknown")])
def test_invalid_and_roundoff_steps_cannot_be_admitted(field,value):
    rows=actual_rows();rows[0][field]=value
    with pytest.raises(ValueError):measured_step_plan(rows)

def test_event_only_and_fine_cap_incompatible_records_fail_closed():
    event=copy.deepcopy(actual_rows()[-1]);event["limiter"]="event"
    with pytest.raises(ValueError):measured_step_plan([event])
    low=copy.deepcopy(actual_rows()[0]);low.update(dt=".0002",cfl_dt=".0002")
    with pytest.raises(ValueError):measured_step_plan([low])

def test_controller_runtime_forecast_passes_actual_count_to_shared_estimator():
    # Gate contract: revised count, rather than minimum event remainder or fixed2100.
    rows=actual_rows();count=measured_step_plan(rows)["remaining_coarse_steps"]
    base=protected_phase_forecast(1.5,1,50,9000,180,coarse_start_t=.05)
    revised=protected_phase_forecast(1.5,1,50,9000,180,coarse_start_t=.05,coarse_steps_override=count)
    assert revised["forecast_seconds"]-base["forecast_seconds"]==pytest.approx(1.25*(count-2100)*1.5)
