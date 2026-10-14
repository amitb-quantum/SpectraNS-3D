"""Offline checks for the QPU spectral advection experiment. No IBM access.

Run in an environment with qiskit, qiskit-aer and qiskit-ibm-runtime:
    python -m pytest -q quantum
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_qpu as rq  # noqa: E402
import spectral_advection as sa  # noqa: E402
from qiskit.quantum_info import Statevector  # noqa: E402


def fake_heron():
    """FakeKingston, or a same-topology Heron fake on older qiskit-ibm-runtime releases."""
    from qiskit_ibm_runtime import fake_provider as fp
    for name in ("FakeKingston", "FakeFez", "FakeMarrakesh", "FakeTorino"):
        cls = getattr(fp, name, None)
        if cls is None:
            continue
        backend = cls()
        edges = {tuple(sorted(e)) for e in backend.coupling_map.get_edges()}
        if all(tuple(sorted(e)) in edges for e in ((1, 2), (2, 3), (3, 16))):
            return backend
    pytest.skip("no Heron fake backend with the 1-2-3-16 chain in this qiskit-ibm-runtime")


@pytest.fixture(autouse=True)
def _offline_fake(monkeypatch):
    """Route every fake-backend request through fake_heron(); tests never contact IBM."""
    real = rq.get_backend
    monkeypatch.setattr(rq, "get_backend", lambda args: fake_heron() if args.fake else real(args))


def ideal_probs(qc):
    return Statevector(qc.remove_final_measurements(inplace=False)).probabilities()


# ---------------------------------------------------------------- physics

@pytest.mark.parametrize("shift", sa.SHIFTS)
def test_circuit_is_exact_band_limited_translation(shift):
    psi = sa.profile()
    qc = sa.logical_circuit(psi, shift, spectral=False).remove_final_measurements(inplace=False)
    overlap = abs(np.vdot(sa.exact_shift(psi, shift), Statevector(qc).data))
    assert overlap == pytest.approx(1.0, abs=1e-12)


def test_ideal_references_match_circuits_in_both_bases():
    ideal = sa.ideal_distributions()
    for s in sa.SHIFTS:
        for spectral, key in ((False, "position"), (True, "spectral")):
            p = ideal_probs(sa.logical_circuit(sa.profile(), s, spectral))
            assert np.abs(p - ideal[s][key]).max() < 1e-12


def test_advection_leaves_modal_distribution_unchanged():
    ideal = sa.ideal_distributions()
    for s in sa.SHIFTS[1:]:
        assert np.abs(ideal[s]["spectral"] - ideal[0.0]["spectral"]).max() < 1e-12


def test_exact_centroids_and_profile_resolution():
    ideal = sa.ideal_distributions()
    assert [round(sa.centroid_cells(ideal[s]["position"]), 10) for s in sa.SHIFTS] == [8.0, 9.5, 11.5, 13.5]
    modal = ideal[0.0]["spectral"]
    high = modal[[6, 7, 8, 9, 10]].sum()           # |k| >= 6 in the signed convention
    assert high < 1e-6


def test_barriers_keep_the_spectral_step_at_zero_shift():
    from qiskit import transpile
    qc = transpile(sa.logical_circuit(sa.profile(), 0.0, False), backend=fake_heron(),
                   initial_layout=list(sa.PATH), optimization_level=sa.OPTIMIZATION_LEVEL,
                   seed_transpiler=sa.SEED_TRANSPILER)
    # state preparation alone needs far fewer two-qubit gates than prep + QFT + inverse QFT
    assert qc.count_ops().get("cz", 0) > 30


# ---------------------------------------------------------------- analysis

def counts_from(p, shots=10**6):
    return {format(i, "04b"): int(round(v * shots)) for i, v in enumerate(p) if v > 0}


def synthetic_counts(eps=0.0, readout=0.0):
    """Exact distributions with global depolarizing eps and symmetric readout flips."""
    ideal = sa.ideal_distributions()
    _, meta = sa.experiment()
    flip = np.array([[1 - readout, readout], [readout, 1 - readout]])
    A = flip
    for _ in range(sa.N_QUBITS - 1):
        A = np.kron(A, flip)
    out = []
    for m in meta:
        if m["kind"] in ("position", "spectral"):
            p = (1 - eps) * ideal[m["shift"]][m["kind"]] + eps / sa.N
        else:
            p = np.zeros(sa.N)
            p[0 if m["kind"] == "readout_0000" else sa.N - 1] = 1.0
        out.append(counts_from(A @ p))
    return out, meta


def test_noiseless_counts_score_as_exact():
    counts, meta = synthetic_counts()
    obs = sa.observables(*sa.split_results(counts, meta), sa.ideal_distributions())
    assert obs["epsilon_from_shift0_twin"] == pytest.approx(0, abs=1e-6)
    for row in obs["shifts"].values():
        assert row["centroid_error_cells"] < 1e-6
        assert abs(row["peak_raw_rel"]) < 1e-5


def test_depolarizing_alone_never_moves_the_centroid():
    counts, meta = synthetic_counts(eps=0.12)
    obs = sa.observables(*sa.split_results(counts, meta), sa.ideal_distributions())
    for row in obs["shifts"].values():
        assert row["centroid_error_cells"] < 1e-4
        assert row["peak_raw_rel"] < -0.05


def test_readout_flips_can_move_the_centroid():
    # bit flips permute outcomes rather than mixing toward uniform, so they bias position
    counts, meta = synthetic_counts(readout=0.02)
    obs = sa.observables(*sa.split_results(counts, meta), sa.ideal_distributions())
    errors = [row["centroid_error_cells"] for row in obs["shifts"].values()]
    assert max(errors) > 1e-3 and max(errors) < sa.P1_CENTROID_MAX_CELLS


def test_twin_calibration_undoes_depolarizing_and_readout():
    counts, meta = synthetic_counts(eps=0.12, readout=0.02)
    obs = sa.observables(*sa.split_results(counts, meta), sa.ideal_distributions())
    assert obs["epsilon_from_shift0_twin"] == pytest.approx(0.12, abs=1e-4)
    for k, row in obs["shifts"].items():
        assert row["peak_raw_rel"] < -0.05
        if float(k) != 0.0:
            assert abs(row["peak_corrected_rel"]) < 1e-3   # and the twin correction recovers it


def test_assessment_verdicts_follow_the_preregistered_criteria():
    counts, meta = synthetic_counts(eps=0.12, readout=0.02)
    v = sa.assess(sa.observables(*sa.split_results(counts, meta), sa.ideal_distributions()))
    assert v["P1_integral_centroid_survives"]["pass"]
    assert v["P2_local_peak_biased_low"]["pass"]
    assert v["P4_twin_calibrated_peak_recovers"]["pass"]
    # identical depolarizing at every shift: runs agree exactly with each other, not with truth
    assert v["P3_consistent_but_inaccurate"]["pass"]
    noiseless = sa.assess(sa.observables(*sa.split_results(*synthetic_counts()), sa.ideal_distributions()))
    assert not noiseless["P2_local_peak_biased_low"]["pass"]
    assert not noiseless["P3_consistent_but_inaccurate"]["pass"]


def test_bootstrap_is_deterministic():
    counts, meta = synthetic_counts(eps=0.1)
    small = [{k: max(1, v // 250) for k, v in c.items()} for c in counts]
    a = sa.analyse_counts(small, meta)
    b = sa.analyse_counts(small, meta)
    assert a["bootstrap_95ci"] == b["bootstrap_95ci"]


# ---------------------------------------------------------------- runner guards

@pytest.fixture(scope="module")
def fake_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle")
    mp = pytest.MonkeyPatch()
    real = rq.get_backend
    mp.setattr(rq, "get_backend", lambda args: fake_heron() if args.fake else real(args))
    try:
        rq.cmd_prepare(prepare_args(out))
    finally:
        mp.undo()
    return out


def test_prepare_freezes_a_guarded_bundle(fake_bundle):
    manifest, circuits = rq.load_bundle(fake_bundle)
    assert rq.active_qubits(circuits) <= set(sa.PATH)
    assert manifest["budget"]["estimated_qpu_seconds"] <= sa.BUDGET_LIMIT_S
    assert manifest["preregistration_sha256"] == rq.sha256_file(rq.PREREG)
    assert (fake_bundle / "dryrun_assessment.json").exists()
    assert not (fake_bundle / "job.json").exists()


def test_prepare_refuses_a_nonempty_directory(fake_bundle):
    with pytest.raises(SystemExit, match="not empty"):
        rq.cmd_prepare(prepare_args(fake_bundle))


def execute_args(bundle, sha):
    return argparse.Namespace(bundle=str(bundle), manifest_sha=sha, instance=None)


def test_execute_refuses_wrong_manifest_sha(fake_bundle):
    with pytest.raises(SystemExit, match="does not match"):
        rq.cmd_execute(execute_args(fake_bundle, "0" * 64))


def test_execute_refuses_fake_bundles(fake_bundle):
    sha = rq.sha256_file(fake_bundle / "manifest.json")
    with pytest.raises(SystemExit, match="fake backend"):
        rq.cmd_execute(execute_args(fake_bundle, sha))


def test_guard_refuses_over_budget_and_off_path(fake_bundle):
    _, circuits = rq.load_bundle(fake_bundle)
    with pytest.raises(SystemExit, match="exceeds"):
        rq.guard(circuits, {"estimated_qpu_seconds": sa.BUDGET_LIMIT_S + 1})
    from qiskit import QuantumCircuit
    stray = QuantumCircuit(20)
    stray.x(19)
    with pytest.raises(SystemExit, match="outside the pre-registered path"):
        rq.guard([stray], {"estimated_qpu_seconds": 1})


class _Job:
    def __init__(self, counts):
        self._counts = counts

    def job_id(self):
        return "mock-job"

    def result(self):
        class Meas:
            def __init__(self, c):
                self._c = c

            def get_counts(self):
                return self._c

        class Pub:
            def __init__(self, c):
                self.data = type("D", (), {"meas": Meas(c)})()
        return [Pub(c) for c in self._counts]

    def metrics(self):
        return {"usage": {"quantum_seconds": 12}}


class _Sampler:
    """Records options and returns ideal counts; never contacts IBM."""
    seen = None

    def __init__(self, mode):
        self.mode = mode
        ns = lambda **kw: argparse.Namespace(**kw)
        self.options = ns(default_shots=None, max_execution_time=None,
                          dynamical_decoupling=ns(enable=None),
                          twirling=ns(enable_gates=None, enable_measure=None))

    def run(self, circuits):
        _Sampler.seen = {"n": len(circuits), "options": self.options}
        logical, _ = sa.experiment()                 # same order as the frozen bundle
        return _Job([counts_from(ideal_probs(qc), shots=sa.SHOTS) for qc in logical])


def test_execute_with_mock_sampler_sets_caps_and_writes_records(tmp_path, monkeypatch):
    bundle = tmp_path / "b"
    rq.cmd_prepare(prepare_args(bundle))
    m = json.loads((bundle / "manifest.json").read_text())
    m["fake_backend"] = False                     # simulate a real-backend bundle
    sha = rq.write_json(bundle / "manifest.json", m)
    monkeypatch.setattr(rq, "get_backend", lambda args: fake_heron())
    rq.cmd_execute(execute_args(bundle, sha), sampler_factory=_Sampler)
    opts = _Sampler.seen["options"]
    assert _Sampler.seen["n"] == 10
    assert opts.default_shots == sa.SHOTS
    assert opts.max_execution_time == sa.MAX_EXECUTION_TIME_S
    assert opts.dynamical_decoupling.enable is False and opts.twirling.enable_gates is False
    assert json.loads((bundle / "job.json").read_text())["job_id"] == "mock-job"
    assert (bundle / "assessment.json").exists()
    with pytest.raises(SystemExit, match="already has a submitted job"):
        rq.cmd_execute(execute_args(bundle, rq.sha256_file(bundle / "manifest.json")), sampler_factory=_Sampler)


def test_fetch_recovers_results_without_submitting(tmp_path, monkeypatch):
    bundle = tmp_path / "f"
    rq.cmd_prepare(prepare_args(bundle))
    args = argparse.Namespace(bundle=str(bundle), instance=None)
    with pytest.raises(SystemExit, match="nothing was submitted"):
        rq.cmd_fetch(args, job_loader=lambda i: None)
    rq.write_json(bundle / "job.json", {"job_id": "mock-job", "manifest_sha256": rq.sha256_file(bundle / "manifest.json")})
    logical, _ = sa.experiment()
    job = _Job([counts_from(ideal_probs(qc), shots=sa.SHOTS) for qc in logical])
    job.status = lambda: "DONE"
    rq.cmd_fetch(args, job_loader=lambda i: job if i == "mock-job" else None)
    assert json.loads((bundle / "counts.json").read_text())["job_id"] == "mock-job"
    assert (bundle / "assessment.json").exists()
    with pytest.raises(SystemExit, match="already exists"):
        rq.cmd_fetch(args, job_loader=lambda i: job)


# ---------------------------------------------------------------- replication path and addendum

ADDENDUM = rq.HERE / "PREREGISTRATION_ADDENDUM_kingston_002.md"
REPLICATION_PATH = "100,101,102,103"


def prepare_args(out, **kw):
    base = dict(fake=True, backend=None, instance=None, out=str(out), sim_seed=1, path=None, addendum=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_parse_path_validation():
    assert rq.parse_path(None) == list(sa.PATH)
    assert rq.parse_path(REPLICATION_PATH) == [100, 101, 102, 103]
    with pytest.raises(SystemExit, match="distinct"):
        rq.parse_path("1,2,2,3")
    with pytest.raises(SystemExit, match="distinct"):
        rq.parse_path("1,2,3")


def test_non_chain_path_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="not a connected chain"):
        rq.cmd_prepare(prepare_args(tmp_path / "x", path="1,2,3,100", addendum=str(ADDENDUM)))


def test_other_path_requires_an_addendum(tmp_path):
    with pytest.raises(SystemExit, match="needs --addendum"):
        rq.cmd_prepare(prepare_args(tmp_path / "x", path=REPLICATION_PATH))


def test_addendum_must_name_the_path(tmp_path):
    with pytest.raises(SystemExit, match="does not name the path"):
        rq.cmd_prepare(prepare_args(tmp_path / "x", path="17,27,28,29", addendum=str(ADDENDUM)))


def test_replication_bundle_binds_path_and_addendum(tmp_path):
    out = tmp_path / "rep"
    rq.cmd_prepare(prepare_args(out, path=REPLICATION_PATH, addendum=str(ADDENDUM)))
    manifest, circuits = rq.load_bundle(out)
    assert manifest["path"] == [100, 101, 102, 103]
    assert manifest["addendum"]["path"] == "quantum/PREREGISTRATION_ADDENDUM_kingston_002.md"
    assert manifest["addendum"]["sha256"] == rq.sha256_file(ADDENDUM)
    assert rq.active_qubits(circuits) <= {100, 101, 102, 103}
    with pytest.raises(SystemExit, match="outside the pre-registered path"):
        rq.guard(circuits, manifest["budget"])          # default path 1-2-3-16 must reject these circuits


def test_execute_refuses_a_changed_addendum(tmp_path, monkeypatch):
    temp_addendum = rq.HERE / "_test_addendum_tmp.md"
    temp_addendum.write_text(ADDENDUM.read_text())
    try:
        out = tmp_path / "rep"
        rq.cmd_prepare(prepare_args(out, path=REPLICATION_PATH, addendum=str(temp_addendum)))
        m = json.loads((out / "manifest.json").read_text())
        m["fake_backend"] = False
        sha = rq.write_json(out / "manifest.json", m)
        temp_addendum.write_text(temp_addendum.read_text() + "\nedited after prepare\n")
        with pytest.raises(SystemExit, match="addendum is missing or changed"):
            rq.cmd_execute(execute_args(out, sha), sampler_factory=_Sampler)
    finally:
        temp_addendum.unlink(missing_ok=True)


def test_readout_errors_are_recorded_and_flagged():
    counts, meta = synthetic_counts(eps=0.1, readout=0.02)
    a = sa.analyse_counts([{k: max(1, v // 250) for k, v in c.items()} for c in counts], meta)
    assert len(a["readout_calibration"]) == sa.N_QUBITS
    assert a["readout_flagged_logical_qubits"] == []
    bad = [c if m["kind"] != "readout_0000" else {"0000": 700, "0001": 300} for c, m in zip(counts, meta)]
    b = sa.analyse_counts([{k: max(1, v // 250) for k, v in c.items()} for c in bad], meta)
    assert 0 in b["readout_flagged_logical_qubits"]
