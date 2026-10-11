import json,math,sys
from pathlib import Path
import pytest
import torch
from ns_fast_v3 import Solver
from spectral_peak import evaluate_cartesian,refine
from refinement_io import inventory,pack,copy_verified,unpack_verified,verify,overlap_decision,small_snapshot
from refinement_guard import birth,same
from extension_state import write
from ns_refinement_worker import profile

def analytic(N=16,device="cpu"):
    S=Solver(N,.0005,.2,.0005,device,torch.float64)
    x=torch.arange(N,device=device,dtype=torch.float64)*S.dx
    X,Y,Z=torch.meshgrid(x,x,x,indexing="ij")
    U=[S.fft(torch.sin(Z-.31)),S.fft(torch.sin(X-.13)),S.fft(torch.sin(Y-.27))]
    return S,U

def test_fourier_exact_off_grid_vector_and_periodicity():
    S,U=analytic()
    xs=[.13,.6,.13+2*math.pi];ys=[.27,.4];zs=[.31,.8]
    got=evaluate_cartesian(S,U,xs,ys,zs)
    expected=torch.tensor([[[math.sqrt(math.cos(x-.13)**2+math.cos(y-.27)**2+math.cos(z-.31)**2)
                            for z in zs] for y in ys] for x in xs],dtype=torch.float64)
    assert torch.max(abs(got-expected)).item()<2e-14

def test_fourier_grid_matches_audited_inverse():
    S,U=analytic()
    coords=[0,S.dx*3,S.dx*9]
    got=evaluate_cartesian(S,U,coords,coords,coords)
    full=sum(S.ifft(S.curl_component(U,i)).square() for i in range(3)).sqrt()
    indices=torch.tensor([0,3,9])
    expected=full[indices[:,None,None],indices[None,:,None],indices[None,None,:]]
    assert torch.max(abs(got-expected)).item()<2e-14

def test_shifted_peak_refinement_controls_sampling_bias():
    S,U=analytic()
    result=refine(S,U)
    assert result["estimator_stable"]
    assert abs(result["fourier_refined_peak_estimate"]-math.sqrt(3))<2e-6
    assert result["fourier_refined_peak_estimate"]>result["sampled_wmax"]
    assert result["sampling_bias_fraction"]>1e-4

def test_collected_snapshot_is_immutable_and_arrays_excluded(tmp_path):
    work=tmp_path/"work";work.mkdir()
    (work/"data.csv").write_text("1,2\n");(work/"U0.npy").write_bytes(b"field")
    snap=tmp_path/"snapshot";expected=small_snapshot(work,snap)
    assert set(expected)=={"data.csv"}
    (work/"data.csv").write_text("changed")
    verify(snap,expected)
    archive=tmp_path/"source.gz";pack(snap,archive)
    destination=tmp_path/"copied.gz";copy_verified(archive,destination)
    assert unpack_verified(destination,tmp_path/"recovered",expected)["verified"]
    (tmp_path/"recovered"/"data.csv").write_text("corrupt")
    with pytest.raises(ValueError):verify(tmp_path/"recovered",expected)

def test_bad_manifest_cannot_promote_partial_collection(tmp_path):
    source=tmp_path/"source";source.mkdir();(source/"evidence").write_text("data")
    expected=inventory(source);write(source/"collection_manifest.json",dict(files=expected))
    pack(source,tmp_path/"source.gz")
    expected["evidence"]="0"*64
    with pytest.raises(ValueError):unpack_verified(tmp_path/"source.gz",tmp_path/"recovered",expected)
    assert not (tmp_path/"recovered").exists()

@pytest.mark.parametrize("remaining,transfer,explore,expected",[(100,20,40,True),(60,20,40,False),(100,80,40,False)])
def test_overlap_includes_contention_and_cleanup(remaining,transfer,explore,expected):
    assert overlap_decision(remaining,transfer,explore,cleanup=20)["overlap"]==expected

def test_birth_stamp_guards_against_pid_reuse():
    import os
    assert same(os.getpid(),birth(os.getpid()))
    assert not same(os.getpid(),"wrong-birth")
    assert not same(999999999,None)

def test_profiles_do_not_expand_existing_cli_scope():
    assert profile("production")["N"]==640
    assert profile("cpu-rehearsal")["N"]==64
    assert profile("cuda-rehearsal")["N"]==256
    with pytest.raises(ValueError):profile("N768")

@pytest.mark.skipif(not torch.cuda.is_available(),reason="CUDA unavailable")
def test_cpu_cuda_exact_fourier_evaluation():
    a,u=analytic();b,v=analytic(device="cuda:0")
    points=([.13,.27],[.31,.2],[.5,.7])
    x=evaluate_cartesian(a,u,*points);y=evaluate_cartesian(b,v,*points).cpu()
    assert torch.max(abs(x-y)).item()<2e-13
