"""Checks for the post-hoc spectral resolution analysis.

Run with: python -m pytest -q analysis
They live outside tests/ so the campaign source fingerprint is unchanged.
"""
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("spectral_resolution", HERE / "spectral_resolution.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)


def synthetic(n=3.0, delta=0.02, kmax=200):
    k = np.arange(kmax + 1, dtype=float)
    E = np.zeros_like(k)
    E[1:] = k[1:] ** -n * np.exp(-2 * delta * k[1:])
    return E


def test_strip_fit_recovers_exact_parameters():
    E = synthetic(n=2.5, delta=0.013)
    delta, n, rms = sr.strip_fit(E, 40, 180)
    assert delta == pytest.approx(0.013, rel=1e-9)
    assert n == pytest.approx(2.5, rel=1e-9)
    assert rms < 1e-10


def test_strip_summary_window_spread_is_zero_for_exact_spectrum():
    E = synthetic(kmax=300)
    s = sr.strip_summary(E, 768)
    assert s["delta_window_max"] - s["delta_window_min"] < 1e-10
    assert s["kmax_delta"] == pytest.approx(0.02 * sr.k_max(768), rel=1e-9)


def test_k_max_counts_only_complete_shells():
    assert sr.k_max(512) == 170   # 512/3 = 170.67, shell 170 ends at 170.5
    assert sr.k_max(640) == 212   # 640/3 = 213.33, shell 213 would end at 213.5
    assert sr.k_max(768) == 255   # 768/3 = 256, shell 256 is partial


def test_identical_spectra_have_no_disagreement():
    E = synthetic()
    assert sr.onset(E, E, 150, 0.01) is None
    frac = sr.weighted_fractions(E[:151], E, 150)
    for v in frac.values():
        assert v["disagreeing_shells"] == 0.0


def test_perturbed_shells_are_detected_and_weighted():
    fine = synthetic()
    coarse = fine[:151].copy()
    coarse[120:151] *= 1.05
    assert sr.onset(coarse, fine, 150, 0.01) == 120
    assert sr.onset(coarse, fine, 150, 0.10) is None
    frac = sr.weighted_fractions(coarse, fine, 150)
    # higher-k weightings must see a larger share of the same disagreement
    assert 0 < frac["enstrophy"]["disagreeing_shells"] < frac["viscous_loss"]["disagreeing_shells"]
    assert frac["peak_proxy"]["above_coarse_cutoff"] > frac["enstrophy"]["above_coarse_cutoff"]


def test_find_hash_requires_a_unique_binding():
    assert sr.find_hash({"files": {"coarse/spectra.csv": "abc"}}) == "abc"
    assert sr.find_hash({"spectra.csv": "abc"}) == "abc"
    with pytest.raises(ValueError):
        sr.find_hash({"a": {"spectra.csv": "x"}, "b": {"spectra.csv": "y"}})
    with pytest.raises(ValueError):
        sr.find_hash({"files": {"fine/spectra.csv": "x"}})


def test_published_inputs_verify():
    paths = sr.verify_inputs()
    assert set(paths) == {512, 640, 768}


def test_tampered_input_is_rejected(tmp_path):
    for spec in sr.INPUTS.values():
        for rel in (spec["path"], spec["binding"]):
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(sr.ROOT / rel, dst)
    target = tmp_path / sr.INPUTS[768]["path"]
    target.write_text(target.read_text() + "1.10,999,0.0\n")
    with pytest.raises(ValueError, match="N768 spectra hash mismatch"):
        sr.verify_inputs(tmp_path)


def assert_close(actual, expected, path="headline"):
    """Exact match for structure, integers and None; tolerance for floats.

    Least-squares strip fits are mildly ill-conditioned (condition number up
    to ~2e5), so different NumPy/BLAS builds legitimately differ near 1e-11
    relative. Reported values carry three to four significant figures.
    """
    if isinstance(expected, dict):
        assert set(actual) == set(expected), path
        for k in expected:
            assert_close(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-8, abs=1e-12), path
    else:
        assert actual == expected, path


def test_analysis_matches_published_summary():
    result = sr.analyse()
    assert len(result["times"]) == 111
    assert max(result["times"]) == pytest.approx(1.10)
    published = json.loads((sr.ROOT / "docs/evidence/2026-10-14/spectral_resolution/summary.json").read_text())
    assert_close(sr.headline(result), published["headline"])


def test_assert_close_still_catches_real_changes():
    with pytest.raises(AssertionError):
        assert_close({"a": 0.0110}, {"a": 0.0111})
    with pytest.raises(AssertionError):
        assert_close({"k": 83}, {"k": 84})
    assert_close({"a": 0.011 * (1 + 1e-11)}, {"a": 0.011})
