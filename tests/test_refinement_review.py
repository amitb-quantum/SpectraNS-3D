"""Roundoff clock regression and predeclared refinement budget/collection gates."""
import csv
from pathlib import Path
import pytest
from ns_extension import advance_event_time,simulate
from refinement_review import lifetime_seconds,runtime_forecast,checkpoint_collection,sampled_peak_comparison

@pytest.mark.parametrize('dt', [.0005,.00025])
def test_long_event_clock_has_no_epsilon_steps(dt):
    t=0.;count=0;minimum=dt;snaps=0
    for index in range(1,301):
        end=index*.01
        while t<end:
            achieved=min(dt,end-t)
            t,adjustment=advance_event_time(t,achieved,end)
            count+=1;minimum=min(minimum,achieved);snaps+=bool(adjustment)
    assert t==3 and count==round(3/dt)
    assert minimum>=dt*(1-1e-9) and snaps>0

def test_snap_does_not_discard_real_cfl_remainder():
    t,adjustment=advance_event_time(.5,.0003,.5005)
    assert t==.5003 and adjustment==0
    assert advance_event_time(t,.0002,.5005)[0]==.5005
    with pytest.raises(FloatingPointError,match='overshoots'):
        advance_event_time(.5,.001,.5005)

def test_diagnostics_use_event_interval_and_profile_is_disjoint(tmp_path):
    run=simulate(tmp_path/'run',N=16,device='cpu',case='tgv',target=.03,
                 checkpoint=False,turnover=False,max_wall_seconds=60,max_dt=.0007)
    assert run['status']=='bounded_complete'
    data=list(csv.DictReader((tmp_path/'run/diagnostics.csv').open()))
    for previous,current in zip(data,data[1:]):
        expected=(float(current['E'])-float(previous['E']))/(float(current['t'])-float(previous['t']))
        assert float(current['dEdt_fd'])==pytest.approx(expected,rel=1e-14)
        assert float(current['dt'])<.0007
    profile=run['timing']
    assert sum(profile['seconds'].values())<=profile['process_wall_s']
    assert profile['calls']['integration']==3
    assert (tmp_path/'run/timing.json').is_file()

@pytest.mark.parametrize('rate,expected', [(2.1,7200),(2.88,5625),(4.273,3791)])
def test_five_dollar_lifetime_depends_on_quote(rate,expected):
    assert lifetime_seconds(rate)==expected
    assert rate*expected/3600+.5<=5+1e-12

def test_invalid_financial_forecast_refused():
    with pytest.raises(ValueError):lifetime_seconds(float('nan'))
    with pytest.raises(ValueError):lifetime_seconds(2,cap_usd=6)
    with pytest.raises(ValueError):runtime_forecast(float('inf'),1,1,1,1,1,10)

def test_slow_host_forecast_refuses_production():
    result=runtime_forecast(1.36,.9,20,3000,162,16,5625)
    assert not result['fits']
    assert not runtime_forecast(1.36,.9,20,3000,162,16,7200)['fits']
    assert runtime_forecast(1.32,.9,20,3000,162,16,7200)['fits']

def test_collect_only_latest_accepted_checkpoint_after_fine_window():
    history=[dict(path='regular_1.0',t=1.,kind='regular',retained=True),
             dict(path='regular_1.1',t=1.1,kind='regular',retained=True),
             dict(path='terminal_1.11',t=1.11,kind='terminal',retained=True)]
    result=checkpoint_collection(history,1.1)
    assert result['collect_full_fields']==['regular_1.1']
    assert result['fine_window_anchor']=='regular_1.0'
    assert result['preserve_all_metadata_and_hashes']
    with pytest.raises(ValueError):checkpoint_collection(history,.9)

def test_peak_at_comparison_boundary_is_censored_even_if_values_agree():
    data=[(0.,1.),(.01,2.),(.02,3.)]
    assert sampled_peak_comparison(data,data)['boundary_censored']
    assert not sampled_peak_comparison(data,data)['sampled_peak_agreement']
    data=[(0.,1.),(.01,3.),(.02,2.)]
    assert sampled_peak_comparison(data,data)['sampled_peak_agreement']
    assert not sampled_peak_comparison(data,[(0.,1.),(.01,3.03),(.02,2.)])['sampled_peak_agreement']


def test_protected_result_does_not_require_exploration_or_checkpoint_download():
    from refinement_review import exploration_ready
    state=dict(prefix_numerical_gates_passed=True,local_temporal_window_passed=True,
               spatial_comparison_recorded=True,small_artifacts_hash_verified_in_wsl=True,
               exploration_complete=False,checkpoint_downloaded=False)
    assert exploration_ready(state)
    state['small_artifacts_hash_verified_in_wsl']=False
    assert not exploration_ready(state)

def test_protected_phase_fits_when_full_exploration_does_not():
    from refinement_review import protected_phase_forecast
    assert protected_phase_forecast(1.3,.9,20,5600,180,setup_preflight_seconds=600)['fits']
    assert not runtime_forecast(1.3,.9,20,3000,162,16,5600,
                               setup_preflight_seconds=600,collection_cleanup_seconds=600)['fits']

def test_collection_allowance_uses_measured_slowest_trial():
    from refinement_review import transfer_allowance
    result=transfer_allowance(6311117184,[4e6,10e6])
    assert result['seconds']>2400 and result['measured_lower_bytes_per_second']==4e6
    assert transfer_allowance(10e6,[4e6,10e6])['seconds']<65
    with pytest.raises(ValueError):transfer_allowance(10,[0])

def test_parabolic_peak_recovers_off_event_vertex():
    from refinement_review import fit_local_peak
    data=[(i*.01,2-3*(i*.01-.083)**2) for i in range(15)]
    result=fit_local_peak(data)
    assert result['status']=='estimated'
    assert result['fitted_t']==pytest.approx(.083,abs=1e-12)
    assert result['fitted_value']==pytest.approx(2,abs=1e-12)
    assert result['time_sensitivity_radius']>=.005-1e-14

def test_peak_fits_do_not_extrapolate_past_unbracketed_boundary():
    from refinement_review import fit_local_peak
    assert fit_local_peak([(0,1),(.01,2),(.02,3)])['status']=='boundary_censored'
    assert fit_local_peak([(0,1),(.01,3),(.02,2),(.03,1)])['status']=='insufficient_five_point_bracket'
    data=[(i*.01,1.) for i in range(7)]
    assert fit_local_peak(data)['status']!='estimated'

def test_flat_peak_uncertainty_does_not_reject_protected_comparison():
    from refinement_review import compare_fitted_local_peaks
    left=[(i*.01,2-.1*(i*.01-1.08)**2) for i in range(111)]
    right=[(i*.01,2-.1*(i*.01-1.095)**2) for i in range(115)]
    result=compare_fitted_local_peaks(left,right)
    assert result['left']['status']==result['right']['status']=='estimated'
    assert result['status']=='inconclusive'
    assert result['controls_protected_validation'] is False

def test_peak_model_rejects_duplicate_or_nonfinite_times():
    from refinement_review import fit_local_peak
    with pytest.raises(ValueError):fit_local_peak([(0,1),(0,2),(.01,1)])
    with pytest.raises(ValueError):fit_local_peak([(0,1),(.01,float('nan')),(.02,1)])
