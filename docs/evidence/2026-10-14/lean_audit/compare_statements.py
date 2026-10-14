#!/usr/bin/env python3
"""Reproduce the Lean statement-fidelity checks in LEAN_STATEMENT_AUDIT_2026-10-14.md.

Fetches three files at pinned commits from GitHub (sparse, shallow), checks
their SHA256 against the audited values, and prints the comment-stripped
diffs the audit relies on. It does not build Lean or run Comparator.

    python docs/evidence/2026-10-14/lean_audit/compare_statements.py --workdir /tmp/lean_audit
"""
import argparse
import difflib
import hashlib
import re
import subprocess
from pathlib import Path

SOURCES = {
    "openai": ("https://github.com/openai/NavierStokesAndEuler.git",
               "f9e8bc5b38b6e212696e8a30e3e91517af887bbd",
               ["ComparatorChallenges/NavierStokes.lean", "ComparatorChallenges/NavierStokes.json",
                "NavierStokes/ComparatorDefinitions.lean", "NavierStokes/ComparatorSolution.lean"]),
    "deepmind": ("https://github.com/google-deepmind/formal-conjectures.git",
                 "8bf45ed70d48b2b2a501de9c00b26bfa38c573ee",
                 ["FormalConjectures/Millenium/NavierStokes.lean"]),
    "mathlib": ("https://github.com/leanprover-community/mathlib4.git",
                "85e3a25e006c35636f0e53b0e9296caca2685bc0",
                ["Mathlib/Analysis/Calculus/ContDiff/FTaylorSeries.lean"]),
}
AUDITED_SHA256 = {
    "openai/ComparatorChallenges/NavierStokes.lean": "0cd193b8d5cbd0266e6e2f72e68dd5abcdcf2430ebd435dd9289737e9aa7da61",
    "openai/ComparatorChallenges/NavierStokes.json": "7610ecead7b390d80ff7f4229a3ff8f18d630e046f7ad1de4f92c7e8e76845b8",
    "openai/NavierStokes/ComparatorDefinitions.lean": "8d90e0f9eee14f8b01773852083a02fd58bda59d4de2abb60d1787bbc9f6ebf4",
    "openai/NavierStokes/ComparatorSolution.lean": "52950d5d618a8d34c9bfbdb16641c81c276e97b6d7fd2a76c08577353f0b0227",
    "deepmind/FormalConjectures/Millenium/NavierStokes.lean": "f446284f2aa54375f558c263a580b34e2e7bc9f44a28829637199cc72257d25d",
    "mathlib/Mathlib/Analysis/Calculus/ContDiff/FTaylorSeries.lean": "740c116026c3d17a0802282a7b4d2a8ec979a489748e54de2b845ac258ceb1fa",
}


def fetch(workdir: Path):
    for name, (url, rev, paths) in SOURCES.items():
        d = workdir / name
        if not (d / ".git").exists():
            d.mkdir(parents=True, exist_ok=True)
            run = lambda *a: subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)
            run("init", "-q")
            run("remote", "add", "origin", url)
            run("config", "core.sparseCheckout", "true")
            (d / ".git/info/sparse-checkout").write_text("\n".join(paths) + "\n")
            run("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", rev)
            run("checkout", "-q", "FETCH_HEAD")


def strip(path: Path):
    s = path.read_text()
    s = re.sub(r"/-.*?-/", "", s, flags=re.S)
    s = re.sub(r"--[^\n]*", "", s)
    s = re.sub(r"@\[[^\]]*\]", "", s)
    return [line.rstrip() for line in s.splitlines() if line.strip()]


def show_diff(a: Path, b: Path, label_a: str, label_b: str):
    d = list(difflib.unified_diff(strip(a), strip(b), label_a, label_b, lineterm="", n=0))
    print("\n".join(d) if d else "IDENTICAL after stripping comments and attributes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, required=True)
    w = ap.parse_args().workdir
    fetch(w)
    ok = True
    for rel, expected in AUDITED_SHA256.items():
        actual = hashlib.sha256((w / rel).read_bytes()).hexdigest()
        print(f"{'OK      ' if actual == expected else 'MISMATCH'} {rel}")
        ok &= actual == expected
    print("\n== DeepMind upstream -> OpenAI challenge ==")
    show_diff(w / "deepmind/FormalConjectures/Millenium/NavierStokes.lean",
              w / "openai/ComparatorChallenges/NavierStokes.lean", "deepmind", "openai_challenge")
    print("\n== OpenAI challenge -> OpenAI solution definitions ==")
    show_diff(w / "openai/ComparatorChallenges/NavierStokes.lean",
              w / "openai/NavierStokes/ComparatorDefinitions.lean", "challenge", "solution_definitions")
    print("\n== Meaning of the smoothness exponent in pinned Mathlib ==")
    for line in (w / "mathlib/Mathlib/Analysis/Calculus/ContDiff/FTaylorSeries.lean").read_text().splitlines():
        if 'notation3 "∞"' in line or 'notation3 "ω"' in line:
            print(line.strip())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
