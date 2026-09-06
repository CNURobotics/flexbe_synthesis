# Issue 4: Run the variable-ordering study

Depends on: [Issue 2](batch_run_harness.md) (batch-run harness),
[Issue 3](variable_ordering.md) (ordering modes + reordering policies).

> **Status: tooling implemented, execution/write-up ongoing.** The Coffee
> matrix generator (`slugs_coffee_matrix`) and the harness/postprocess pipeline
> exist; see [coffee_experiment_runbook.md](coffee_experiment_runbook.md) for
> the live run procedure. What follows is the study design, reconciled to the
> shipped matrix (three reordering policies rather than a plain on/off toggle,
> and `dynamic` dropped from the sweep).

## Context

Issue 3 builds the ability to control initial variable order; this issue
spends it — running the actual sweep that answers whether "enumerated costs
more than one-hot" survives a good reordering heuristic, or is an artifact of
the pipeline's naive alphabetic default.

## Matrix

For each `example × encoding (one-hot, enumerated) × liveness (S, F) × pending
(with/without)` cell, and under each of two **CUDD reordering policies**
(`off`, `threshold_250` — see [variable_ordering.md](variable_ordering.md)):

| combo | fixed orderings | random N | reordering policies |
|---|---|---|---|
| Coffee — 16 capability cells | `alphabetic`, `domain` | 40 seeds | `off`, `threshold_250` |
| Coffee — hand-written baseline (col 1) | `alphabetic`, `domain` | 40 seeds | `off`, `threshold_250` |

The `auto` policy (Slugs default sifting) was dropped after the prior run showed
it ≈ `off` at these BDD sizes while `threshold_250` dominated it; random seeds
were cut 100→40 (the distribution is unchanged — only ~4 cells show any spread,
and 40 vs 100 matches on median/p90).

The hand-written baseline (paper Table I column 1) is a **17th combo**: it
compiles through the same ordering-aware compiler/synthesizer, so it carries the
same ordering sweep, but has no encoding/liveness/pending axes (rows are tagged
`encoding=full_spec`, `liveness=na`, `pending=false`). See the runbook's
"Included as a 17th combo" note.

**`dynamic` is not swept.** It remains a valid `order_variables` mode but is
operationally identical to `alphabetic` under an on-reordering policy, so the
"does reordering help" question is answered by the `off`/`threshold_250`
policy axis instead. Only Coffee's `N` is fixed so far. Other examples
(two-rivers, quadcopter, ...) need their own `N` decided per Issue 5's
cost/expense tradeoff (quadcopter cells are called out there as expensive —
expect a much smaller `N`); don't assume 40 generalizes.

"Coffee (all 16 cells)" is grounded (see
[coffee_experiment_runbook.md](coffee_experiment_runbook.md)): both capability
sets (`coffee_capabilities.yaml`/`_extended.yaml`, matching the paper's
scenario `2`/`3`) × both encodings × `{S, F}` × `{with, without pending}` = 16
combos — 4 of which (`F`+pending) don't exist in the paper's current Tables
I/II at all, so this study also produces first-time data for those, not just
ordering-robustness sampling of already-published cells.

Per cell, per reordering policy: `random` gets `N` independent seeded trials
(the distribution), while `alphabetic` and `domain` each get one matrix row
(× `n_trials` exact repeats — deterministic peak-node values), reported as
individually annotated points against that distribution rather than folded
into it — they're specific, motivated orderings, not samples from the same
random process. (The concrete generator is `slugs_coffee_matrix`:
`(16 capability combos + 1 hand-written baseline) × (2 fixed orderings + 40
random seeds) × 2 policies` = 1428 rows.)

## Tasks

1. Execute the matrix via the Issue 2 harness. Fix and record every `random`
   seed used (reproducibility — the harness's metadata columns already carry
   `seed`, so this is a matter of using it, not inventing new bookkeeping).
2. Report distributions of **peak BDD nodes** per encoding (the primary
   metric per Issue 2's notes — deterministic given ordering, so the
   distribution's spread *is* the ordering-sensitivity signal, not noise).
3. Plot/mark `alphabetic` and `domain` as annotated points against the
   `random` distribution (box plot of the 100 random-seed peak-node values per
   `(example, encoding, liveness, pending)` cell, grouped by reordering policy
   on the x-axis, with `alphabetic` and `domain` overlaid as labeled markers).
   The shipped figure is `experiment_postprocess.write_ordering_plots` /
   `write_ordering_summary_plot`, not a standalone plotting script — see
   [ordering_study_figure.md](ordering_study_figure.md).

## Interpretation branches — record which one holds

Decide and record this explicitly per `(example, encoding, liveness,
pending)` cell, not just once globally — different cells may land in
different branches (see the third branch):

1. **Enumerated worse across random orderings and under the on-reordering
   policies (`auto`/`threshold_250`)** → strong claim stands: the
   interaction-density explanation for why enumerated costs more is
   evidence-backed, not an ordering artifact.
2. **An on-reordering policy (`auto`/`threshold_250`) closes most of the gap
   versus `off`** → reframe: the penalty is largely a static-ordering artifact,
   substantially mitigated by CUDD dynamic reordering. Still publishable, but a
   different, weaker claim than branch 1.
3. **Example-dependent** → report as such rather than forcing one global
   conclusion. Quadcopter is called out as the example where the wide shared
   bit-vector makes the interaction-density story most plausible, so it's the
   most likely place to see branch 1 even if other examples land in branch 2.

## Verification

- Confirm the `random` distribution for at least one cell has exactly `N`
  independent rows with distinct recorded seeds (via Issue 2's harness output)
  before trusting any downstream plot.
- Sanity-check `alphabetic`'s peak-node value against the corresponding
  existing (pre-Issue-3) table entry — should match exactly, since
  `alphabetic` is defined to preserve continuity with today's default behavior.
