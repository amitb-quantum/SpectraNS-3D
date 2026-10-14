# Research contribution and claim boundaries

SpectraNS-3D's intended contribution is a reproducible numerical study of unforced, positive-viscosity vortex tubes, with observable-specific validation and recorded failure paths. Its value is assessed from the evidence, not by ranking it against a different mathematical theorem.

## What the completed two-grid evidence already supports

Energy can agree much more closely than derivative-sensitive diagnostics. Through the common accepted interval, energy differed at most0.000340%, while scaled net enstrophy production differed0.181614%. At t=1.00 the stable Fourier local vorticity estimates differed0.483900%, despite both grids passing the declared energy-tail heuristic. The finer grid's viscous enstrophy loss at that time was about1.40% larger relative toN512. This is a concrete calibration result: passing the tail gate does not certify every observable to0.1%.

Grid-sampled peaks also differ from local Fourier estimates. At t=1.00 the retained N512 field gave about0.9274% sampling bias, while N640 gave about0.2390%. Sampling and discretization therefore require separate checks. A sampled peak discrepancy cannot automatically identify a physical mechanism.

The workflow preserves exact inputs, source/runtime bindings, accepted and failing samples, full shell spectra, budget identities, timing/memory data, checkpoint metadata/hashes and owned-instance termination. Real controller/collection SIGKILL rehearsals verify what evidence survives failure. These are methodological deliverables in their own right.

[Completed numerical report](N640_COMPARISON_2026-10-13.md).

## What the completed third grid adds

The predeclared hypothesis was that derivative-sensitive N640/N768 discrepancies would shrink relative to N512/N640. The result is observable-specific. Maximum relative enstrophy difference shrank from 0.05997% to 0.01279%, and scaled net-production difference from 0.18161% to 0.08044%, meeting the 0.1% criterion for the closest pair.

Stable local Fourier vorticity estimates did not follow that pattern. N640/N768 differences are 1.53049% at 1.00 and 1.10622% at 1.10. The earlier N512/N640 agreement of 0.00911% at 1.10 was therefore insufficient to establish convergence. The third grid supplied a concrete counterexample to treating close two-grid agreement or a passing energy-tail gate as a certificate for a local observable.

The own-anchor finer-timestep check passed with maximum specified difference 1.64332e-8. It bounds local continuation sensitivity, not inherited prefix error. Stable local interpolation does not certify a global supremum. Unequal grid ratios and shrinking integral increments do not establish a continuum order/error bound. Enstrophy was still rising at 1.10, so no turnover is claimed.

The [completed three-grid report](N768_THREE_GRID_COMPARISON_2026-10-13.md), complete protected small evidence and independent replay distinguish integral consistency, local-peak sensitivity, sampling and operational validity. This is a completed research release even though universal spatial certification remains unresolved.

## What the spectral resolution addendum adds

The [October 14 addendum](SPECTRAL_RESOLUTION_ADDENDUM_2026-10-14.md) locates the integral/local split in wavenumber space using only the published spectra. Between N640 and N768, under 1% of enstrophy but 24% of viscous loss and 33% of a peak-vorticity proxy sit in shells whose energy differs by more than 1% at t = 1.00, and all three shares peak at t = 0.99. This gives a mechanism-level account of why one diagnostic converged and another did not. It also records a negative result: the conventional analyticity-strip fit is too window-sensitive on these spectra to certify resolution.

## Relationship to OpenAI's published claim

OpenAI's September2026 announcement claims an analytical and Lean-formalized finite-time singularity construction for an initially resting fluid with smooth forcing and finite energy. SpectraNS-3D evolves prescribed smooth unforced tubes and studies finite-grid reliability. The equation class overlaps, but initial conditions, forcing and evidence differ. [OpenAI primary announcement](https://openai.com/index/navier-stokes-solution/).

We can say that this project supplies a separate empirical methodology and quantified numerical sensitivity for its own experiment. We cannot say that it surpasses an analytical proof, independently certifies OpenAI's formalization, establishes unforced Navier–Stokes blowup/regularity, or discovers a new physical mechanism from these scalars. Claiming broader scientific novelty requires comparison with the numerical literature; it has not yet been established.

## Finite release definition

Complete the authorized common-window three-grid experiment where admitted, independently assess and publish its result, verify financial/resource closure and document unresolved questions. Spatial certification and a converged turnover may remain open. A research release can be complete without declaring the underlying PDE problem solved.

## Selected primary literature context

Numerical resolution and method choice have long mattered in nearly singular vortex calculations. Hou and Li's2006 Euler study compares2/3-dealiased and Fourier-smoothed pseudo-spectral schemes across resolutions and reports bounded velocity with at most doubly exponential peak-vorticity growth over its computed interval. That is a different zero-viscosity problem and does not validate our viscous tubes. [Hou and Li, original paper/abstract](https://arxiv.org/abs/physics/0608126).

Kerr's2017 Navier–Stokes reconnection study examines trefoil and anti-parallel vortices, viscosity-dependent vorticity/enstrophy norms and domain scaling. Our single-viscosity, fixed-domain short interval cannot establish those viscosity-limit scalings or a dissipation anomaly. [Kerr, original paper/abstract](https://arxiv.org/abs/1610.00398).

These examples establish that resolution studies and enstrophy diagnostics themselves are not new. This is a selected context check, not an exhaustive novelty review. Our defensible contribution is the exact experimental evidence and auditable workflow for this specified trajectory, including failure-path evidence and observable-specific acceptance decisions.
