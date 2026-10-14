"""Scientific contracts for selective diagnostics and same-grid prefix continuation."""
import csv,json
from pathlib import Path
import numpy as np
import pytest
import torch
from ns_third_grid_worker import execute,profile
from third_grid_sampling import selected,count_remaining
from third_grid_prefix import join_prefix,release_prefix
from third_grid_assessment import validate,checkpoint_at
from third_grid_review import protected_phase_forecast
from third_grid_io import fingerprint
from cloud_policy import ROOT
from extension_state import write,sha
from ns_extension import simulate

def test_declared_schedule_keeps_both_primary_peaks_and_dense_peak_window():
    p=profile("production")
    coarse=[i*.01 for i in range(111) if selected(i*.01,"coarse",p)]
    assert len(coarse)==31
    assert all(t in coarse for t in (0.,.05,1.,1.1))
    assert all(selected(i*.01,"coarse",p) for i in range(86,95))
    assert not selected(.83,"coarse",p)
    assert [i*.01 for i in range(100,111) if selected(i*.01,"fine",p)]==[1.,1.1]
    assert count_remaining(p)==dict(coarse=29,fine=2,total=31,coarse_diagnostic_events=106,fine_diagnostic_events=11)
    assert not selected(.05,"coarse",p,continued=True)
    with pytest.raises(ValueError):selected(.083,"coarse",p)

def test_measured_sampling_and_saved_prefix_fit_without_relaxing_margin():
    step=1.4634369390551;diagnostic=6.202531598430748
    refinement=30.80309974262491/6;checkpoint=18.86317149363458
    remaining=5943.585358142853
    old=protected_phase_forecast(step,diagnostic,checkpoint,remaining,180)
    sparse=protected_phase_forecast(step,diagnostic-refinement,checkpoint,remaining,180,
             refinement_seconds=refinement,refinement_events=33)
    reused=protected_phase_forecast(step,diagnostic-refinement,checkpoint,remaining,180,
             coarse_start_t=.05,refinement_seconds=refinement,refinement_events=31)
    assert not old["fits"] and sparse["fits"] and reused["fits"]
    assert old["forecast_seconds"]==pytest.approx(6165.003693094282)
    assert reused["remaining_coarse_steps"]==2100 and reused["fine_steps"]==400
    assert reused["diagnostic_events"]==117 and reused["checkpoint_events"]==12
    assert reused["forecast_seconds"]<5400 and remaining-reused["forecast_seconds"]>540
    assert reused["forecast_seconds"]==pytest.approx(1.25*reused["compute_uninflated_seconds"]+180)
    with pytest.raises(ValueError):protected_phase_forecast(step,1,1,remaining,180,refinement_seconds=float("nan"))

@pytest.fixture
def continued(tmp_path):
    prior=torch.get_num_threads();torch.set_num_threads(2)
    work=tmp_path/"work";work.mkdir();p=profile("cpu-rehearsal");binding=fingerprint(ROOT)
    base=dict(profile="cpu-rehearsal",fingerprint=binding,wall_seconds=120,rehearsal_pause_s=0)
    execute(dict(base,phase="preflight",output=str(work/"preflight"),restart=None,telemetry_path=str(work/"preflight_driver.csv")))
    state=checkpoint_at(work/"preflight",p["preflight_t"])
    execute(dict(base,phase="coarse",output=str(work/"coarse"),restart=str(state),telemetry_path=str(work/"coarse_driver.csv")))
    yield work,p
    torch.set_num_threads(prior)

def test_continuation_join_matches_uninterrupted_fields_and_preserves_phase_evidence(continued,tmp_path):
    work,p=continued
    phase_hash=sha(work/"coarse/run.json")
    receipt=join_prefix(work,p)
    assert receipt["verified"] and receipt["integrated_steps"]==22
    assert receipt["merged_diagnostic_events"]==12
    assert sha(work/"coarse_continuation_small/run.json")==phase_hash
    joined=validate(work/"coarse",64,.011,.001)
    assert joined["manifest"]["start_t"]==0 and joined["manifest"]["initial_step"]==0
    times=[float(r["wall_s"]) for r in joined["rows"]]
    assert times==sorted(times)
    with (work/"coarse/steps.csv").open() as f:steps=list(csv.DictReader(f))
    assert [float(r["wall_s"]) for r in steps]==sorted(float(r["wall_s"]) for r in steps)
    assert joined["manifest"]["last_accepted"]["wall_s"]==float(joined["rows"][-1]["wall_s"])
    with (work/"coarse/interpolated_vorticity.csv").open() as f:data=list(csv.DictReader(f))
    assert len(data)==12 and data[2]["refinement_performed"]=="False"
    assert data[2]["fourier_refined_peak_estimate"]==""
    original=simulate(tmp_path/"original",N=64,case="tgv",device="cpu",target=.011,
                      log_dt=.001,checkpoint_dt=.010,max_dt=.0005,turnover=False,max_wall_seconds=120)
    assert original["status"]=="bounded_complete"
    left=checkpoint_at(work/"coarse",.011)
    right=checkpoint_at(tmp_path/"original",.011)
    for name in ("U0.npy","U1.npy","U2.npy"):
        assert np.array_equal(np.load(left/name),np.load(right/name))
    release_prefix(work)
    assert not (work/"preflight/checkpoints").exists()
    assert (work/"preflight/checkpoint_metadata").exists()
    assert (work/"preflight/run.json").exists()
    validate(work/"coarse",64,.011,.001)

def test_foreign_checkpoint_identity_cannot_join_or_release_fields(continued):
    work,p=continued
    m=json.loads((work/"coarse/run.json").read_text())
    m["restart"]["metadata"]["files"]["U0.npy"]="0"*64
    write(work/"coarse/run.json",m)
    with pytest.raises(ValueError,match="field identity"):join_prefix(work,p)
    assert not (work/"continuation_receipt.json").exists()
    assert (work/"preflight/checkpoints").exists()
    with pytest.raises(FileNotFoundError):release_prefix(work)

def test_missing_continuation_anchor_cannot_be_accepted_or_joined(continued):
    work,p=continued
    for name in ("diagnostics.csv","enstrophy.csv","spectra.csv","interpolated_vorticity.csv","dissipation_shares.csv"):
        q=work/"coarse"/name
        with q.open(newline="") as f:
            reader=csv.DictReader(f);headers=reader.fieldnames;data=list(reader)
        with q.open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader()
            writer.writerows(r for r in data if float(r["t"])>p["preflight_t"]+1e-12)
    with pytest.raises(ValueError,match="event lattice"):validate(work/"coarse",64,.011,.001)
    with pytest.raises(ValueError,match="event lattice"):join_prefix(work,p)
    assert not (work/"continuation_receipt.json").exists()
    assert (work/"preflight/checkpoints").exists()

def test_changed_prefix_record_cannot_release_anchor_arrays(continued):
    work,p=continued
    join_prefix(work,p)
    q=work/"preflight/run.json";m=json.loads(q.read_text());m["review_test"]="changed"
    write(q,m)
    with pytest.raises(ValueError,match="prefix manifest"):release_prefix(work)
    assert (work/"preflight/checkpoints").exists()

def test_worker_handoff_publishes_fresh_progress_marker_with_phase(tmp_path,monkeypatch):
    import time
    import third_grid_controller as controller
    out=tmp_path/"controller";out.mkdir();work=out/"work";work.mkdir()
    class Backend:
        state=dict(deadline_epoch=time.time()+300)
        def phase(self,name,cfg):raise RuntimeError("stop after checked preflight handoff")
        def close(self):return dict(verified=True,mode="local-rehearsal")
    backend=Backend();backend.work=work
    original=controller.write;checked=[]
    def record(path,data):
        if Path(path)==out/"controller_state.json" and data.get("phase")=="preflight":
            assert data["worker_progress"]==str(work/"preflight/peak_last_event.json")
            assert data["worker_start_t"]==0.
            checked.append(True)
        return original(path,data)
    monkeypatch.setattr(controller,"write",record)
    result=controller.run(out,backend,"cpu-rehearsal")
    assert checked and not result["protected_validated"]
