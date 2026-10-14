# Statement-fidelity audit of OpenAI's Lean Navier–Stokes formalization

October 14, 2026. An independent check of one narrow question: **do the theorems OpenAI's Lean formalization proves say what Clay's breakdown alternatives (C) and (D) say?** It does not check that the proofs are correct (that is the Lean kernel's job, see "Not verified"), and it does not judge prize eligibility, which is the Clay Mathematics Institute's decision. OpenAI has stated it will not claim the prize.

**Finding: no fidelity gap.** The formal statement of (C) matches Clay's (C) clause by clause. The formal (D) matches Clay's (D) as amended by Clay's published errata. One placement subtlety in that errata is recorded below; it does not change the result.

## Sources (pinned)

| Source | Version | Files audited (six are SHA256-pinned in the reproduction script) |
|---|---|---|
| Clay problem statement, C. Fefferman | [navierstokes.pdf](https://www.claymath.org/wp-content/uploads/2022/06/navierstokes.pdf), equations (1)–(11) and errata on page 5 | read directly |
| OpenAI, [NavierStokesAndEuler](https://github.com/openai/NavierStokesAndEuler) | commit `f9e8bc5` | `ComparatorChallenges/NavierStokes.lean`, `.json`; `NavierStokes/ComparatorDefinitions.lean`; `NavierStokes/ComparatorSolution.lean` |
| Google DeepMind, [Formal Conjectures](https://github.com/google-deepmind/formal-conjectures) | commit `8bf45ed`, the version the challenge cites | `FormalConjectures/Millenium/NavierStokes.lean` |
| Mathlib | commit `85e3a25`, pinned in OpenAI's `lake-manifest.json` | `ContDiff/FTaylorSeries.lean` (hashed); `InnerProductSpace/Laplacian.lean` and `Gradient/Basic.lean` read at the same commit |

## The chain from Clay to the proved theorem

OpenAI's design separates the statement from the proof. A challenge file states (C) and (D) with `sorry`; the solution module proves theorems of the same names; the [Comparator](https://github.com/leanprover/comparator) tool checks the two agree and that only permitted axioms are used.

| Link | Check | Result |
|---|---|---|
| Clay → DeepMind statement | Clause-by-clause reading (below) | Faithful, with the errata applied to (D) |
| DeepMind → OpenAI challenge | Diff with comments and attributes stripped | Only imports, namespace and local notation changed; unforced (A) and (B) dropped. All definitions and both (C)/(D) statements identical |
| Challenge → solution's definitions copy | Same diff | Identical |
| Definitions → proved theorems | Reading `ComparatorSolution.lean` | Same statements, word for word. Permitted axioms: `propext`, `Quot.sound`, `Classical.choice` |

Using a statement written independently, before OpenAI's result, is the strongest part of the design: the proving side did not write its own target.

## Clause-by-clause: (C), breakdown on ℝ³

(C) asserts that suitable data exist **and** that no solution exists. The data side must be at least as demanding as Clay's (4)–(5), or the theorem would exhibit data Clay does not allow. The solution side must be **at least as broad** as Clay's class: ruling out a narrower class is a weaker theorem.

| Clay | Lean (`navier_stokes_breakdown_R3`) | Assessment |
|---|---|---|
| u° smooth, divergence-free on ℝ³ | `ContDiff ℝ ∞ u₀`, `∇⬝ u₀ x = 0` everywhere | Equal |
| (4) \|∂ₓ^α u°\| ≤ C_{αK}(1+\|x\|)^{−K}, any α, K | `‖iteratedFDeriv ℝ m u₀ x‖ ≤ C/(1+‖x‖)^K` for all m ∈ ℕ, K ∈ ℝ | Equivalent: the total derivative bounds every partial and vice versa, up to constants |
| f smooth on ℝ³×[0,∞), (5) decay in x and t | `ContDiffOn ℝ ∞ ↿f (univ ×ˢ Ici 0)`, `iteratedFDerivWithin` bound by C/(1+‖x‖+t)^K | Equal |
| (1) the PDE for x ∈ ℝ³, t ≥ 0 | for all x and t ≥ 0: `derivWithin` on `Ici 0` in t, `fderiv` advection, Mathlib `Δ`, `gradient` | Equal (one-sided at t = 0, as Clay's t ≥ 0 requires) |
| (2) div u = 0; (3) u(x,0) = u°(x) | for all x, t ≥ 0; for all x | Equal |
| (6) p, u ∈ C^∞(ℝ³×[0,∞)) | `ContDiffOn ℝ ∞` on `univ ×ˢ Ici 0` for both | Equal. **No condition on p beyond smoothness**, as in Clay |
| (7) ∫\|u\|² dx < C for all t ≥ 0 | `MemLp ‖v·t‖ 2` for each t, and ∃ E with ∫‖v x t‖² < E for all t ≥ 0 | Equivalent. `MemLp` is needed because Lean's integral of a non-integrable function returns 0, which would make (7) vacuous; Clay's (7) already implies square-integrability |

## Clause-by-clause: (D), breakdown on ℝ³/ℤ³

| Clay | Lean (`navier_stokes_breakdown_periodic`) | Assessment |
|---|---|---|
| u° smooth, divergence-free; (8) u° 1-periodic | smooth, divergence-free, `IsOnePeriodic u₀` | Equal |
| f smooth; (8) f 1-periodic; (9) decay in t | smooth on ℝ³×[0,∞), periodic for each t ≥ 0, bound C/(1+t)^K | Equal |
| (1)–(3), (11) smoothness | as in (C) | Equal |
| (10) u periodic | `IsOnePeriodic (v·t)` for t ≥ 0 | Equal |
| *(not in the original (10))* | **p periodic**: `IsOnePeriodic (p·t)` for t ≥ 0 | Follows Clay's errata (next section) |

## The errata point

Requiring a periodic pressure **narrows** the solution class. Without the errata, Lean's (D) would rule out fewer solutions than the original text and be slightly weaker than the original (D). With no periodicity requirement, a pressure p_per(x,t) + a(t)·x is allowed, and its gradient acts as an extra spatially uniform force.

Clay's published errata, on page 5 of the problem PDF, reads: *"The further condition p(x + e_j, t) = p(x, t) should be made explicit in Eqn (8)."* So periodic pressure is part of the official statement, and Lean's (D) is faithful to it.

The subtlety is placement. In (D), equation (8) governs the data (u° and f), while the solution's conditions are (10) and (11). The pressure is not data, so the only coherent reading of the errata is a requirement on the solution. That is the reading DeepMind and OpenAI both adopt, and the one this audit accepts. The same errata also corrects a sign in the weak-solution identity, which neither (C) nor (D) uses.

## Definitions checked in pinned Mathlib

- **Smoothness exponent.** With `open ContDiff`, `∞` is `((⊤ : ℕ∞) : WithTop ℕ∞)`, meaning C^∞. Analytic is the separate `ω`. Had `∞` meant analytic, the solution class would be far narrower and the theorem far weaker; it does not.
- **Laplacian.** `Δ f x` is the second derivative contracted with the canonical covariant tensor, i.e. the sum of second partials over an orthonormal basis, valid for vector-valued f.
- **Gradient.** `gradient f x` is the Riesz representative of `fderiv f x`, the usual gradient.
- **Junk values.** Lean's `fderiv` returns 0 where a function is not differentiable. Every candidate solution is required to be C^∞ on ℝ³×[0,∞), so no junk value can enter the PDE.

## Not verified here

- **The proofs.** This audit did not build the project or run Comparator; [COMPARATOR_GUIDE.md](evidence/2026-10-14/lean_audit/COMPARATOR_GUIDE.md) gives the steps. That requires the Lean 4.34.0-rc2 toolchain and the Mathlib cache (several GB), with `lake exe comparator ComparatorChallenges/NavierStokes.json`. Statement fidelity is meaningful only together with a passing Comparator run.
- **Comparator's own guarantees.** The audit relies on Comparator checking that the solution's theorem types match the challenge's, including all definitions they reference. The textual identity of the definitions is consistent with that but does not replace it.
- **The Euler result.** Out of scope.

## What remains open

OpenAI's result addresses the **forced** breakdown alternatives. Clay's unforced alternatives remain untouched:
* **(A):** existence and smoothness on ℝ³ for every admissible u° with f = 0.
* **(B):** the periodic analogue.

Whether smooth unforced solutions always exist is still open. That is not an omission in OpenAI's work: Clay's problem asks for a proof of any one of (A)–(D). But it is the question most people mean by "Navier–Stokes regularity", and no numerical study, including SpectraNS-3D, can settle it.

## Reproduce

```bash
python docs/evidence/2026-10-14/lean_audit/compare_statements.py --workdir /tmp/lean_audit
```

The script fetches the pinned files from GitHub, verifies all six SHA256 values, and prints the two diffs and the Mathlib notation lines quoted above. It does not build Lean.
