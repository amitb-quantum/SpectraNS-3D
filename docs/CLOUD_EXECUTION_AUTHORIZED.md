# Authorized smoke execution update

The user authorized spending below $10 without another permission request on
2026-10-09 PT. The $30 total project ceiling and numerical validation gates
remain in force. This updates the earlier unapproved planning status in
`CLOUD_EXECUTION_PLAN.md`; that document and all earlier evidence are preserved.

The user identified project instances 54972816, 54977694, 55050441, 55073476,
55125900, 55132133 and 55140712. Complete live charges total **$12.434** for
these IDs. All other account charges are excluded by the user's attribution.
The provider reports $2.902 for 55050441, more than its estimated GPU-active
cost. Expenditure includes idle rental and storage, not just GPU activity.
There are no current instances. A $0.05 pending/rounding reserve is retained.
Actual credit is $17.6650596870099. Provider `balance` is a separate field.

Discovery found a compatible H100 PCIe offer around $2.15/hour with driver
595.71.05 (CUDA maximum 13.2). The cheaper ~$1.74 H100 SXM offer has driver
535.309.01, incompatible with the pinned CUDA 13 environment. No H200 appeared
in the filtered current single-GPU search. Offer availability is rechecked
immediately before creation; the first query's underscore GPU name was corrected
to the live API's space-separated name.

This campaign reserves **$2 all-in**, uses a conservative **$3/hour including
40GB disk** bound, at most **1200 seconds from before the creation request**,
and a verified **$0.25 noncompute reserve**. Worst-case exposure is $1.25,
below the reserved $2. A quote above these bounds is refused. New commitment
plus prior charges/pending reserve remains below $30. The policy allows only
user-approved commitments strictly below $10; numerical core hashes are fixed.

The exact validated environment is packed locally with conda-pack 0.9.2 before
rental. It is copied and hash-verified remotely, relocated with conda-unpack,
and receives only an editable installation of the immutable source payload.
The substrate is a verified immutable Vast base-image digest. Runtime metadata
records H100 PCIe explicitly; this is not an SXM throughput measurement.

`run_vast_smoke.py` checks current creation/destruction authority, quote, budget,
source payload and transfer limits. It starts `vast_watchdog.py` as a separate
local WSL process **before creation**. The guard destroys only the unique named
campaign at the deadline or if the controller exits. The controller also
collects artifacts and destroys its instance in a finally block, then verifies
absence through complete API pagination. These are independent process controls,
not a provider-enforced billing guarantee during a local-machine/network outage.

Only N32 references and the existing float64 N128/N256 smoke matrix execute.
The audited v2/v3 core is unchanged. Tests cover ownership-bound destruction,
deadline behavior, budgets and corrupted artifacts without provider calls.
Every successful or failed campaign retains its controller state, approval,
quote, hashes, runtime logs, available downloaded diagnostics and termination
receipt. The next commitment requires updated actual charges and pending bounds.
No N512/N768/N1024 run is authorized by this smoke controller.
