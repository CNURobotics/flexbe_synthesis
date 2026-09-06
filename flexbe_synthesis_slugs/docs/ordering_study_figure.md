# Issue 13: Ordering-study figure

Depends on: [Issue 4](variable_ordering_study.md) (run the variable-ordering
study — this is where the figure's data comes from).

> **Status: implemented** — not as the standalone `plot_ordering_study.py`
> this doc originally proposed, but as functions in
> [`experiment_postprocess.py`](../flexbe_synthesis_slugs/helpers/experiment_postprocess.py):
> `write_ordering_plots` (per-panel diagnostics) and
> `write_ordering_summary_plot` (the combined paper figure), driven by
> `slugs_experiment_postprocess`. The original spec below is kept for intent;
> the "As shipped" section records what was actually built, and the earlier
> open question is now resolved.

## Context

Issue 4 produces the `random`-mode peak-BDD-node distribution plus the
`alphabetic`/`domain` single points per
`(capability-file, encoding, liveness, pending)` cell, under each reordering
policy. This issue turns that data into the paper figure. It's also where [multi_run_sampling.md](multi_run_sampling.md)'s
"spread goes in the figure, not the table" rule actually gets satisfied —
this figure is the spread.

## Spec (as given)

- **Box plots.**
- **X-axis**: encoding (`one-hot` vs `enumerated`).
- **Y-axis**: peak BDD nodes, **log scale**.
- **One panel per example** (facet/subplot per `example`).
- **`dynamic` and `domain`** marked as annotated points against the `random`
  distribution — distinct markers/labels, not folded into the box.

## Figure Layout

Each `(capability-file × liveness × pending)` combination gets its **own
panel**, with **CUDD reordering policy** (`off` / `auto` / `threshold_250`) as
the main x-axis grouping and **encoding** as the within-group label. The single
Coffee example doesn't need one-panel-per-example faceting; the panels tile the
`(capability-file, liveness, pending)` space instead. `alphabetic` and `domain`
(not `dynamic` — it isn't swept, see
[variable_ordering_study.md](variable_ordering_study.md)) are the overlaid
annotated points.

## As shipped

Implemented in
[`experiment_postprocess.py`](../flexbe_synthesis_slugs/helpers/experiment_postprocess.py),
reading Issue 4's `master.csv` (the box needs the raw per-seed rows, not the
summary):

- `write_ordering_plots` — one diagnostic plot per
  `(capability-file × liveness × pending)` setting.
- `write_ordering_summary_plot` — the combined paper figure: every panel in one
  figure with a shared y-axis and one legend, plus split-by-capability-set
  variants (`ordering_summary_capability_file_*`) since a combined y-range can
  hide within-set differences.
- In each panel: CUDD reordering policy is the main horizontal grouping,
  encoding is the within-group (slanted) label, the seeded `random` runs form
  the box on a log-y axis, `alphabetic` and `domain` are overlaid as reference
  markers, and mean `overall_pipeline_time_s` for the random runs is overlaid on
  a right log-y axis (`--summary-time-metric realizability_time_s` swaps it for
  Slugs realizability time; `--summary-plot-no-time-axis` suppresses it).

See [coffee_experiment_runbook.md](coffee_experiment_runbook.md) → "Tables and
Plots" for the exact `slugs_experiment_postprocess` invocations and output
paths.

## Verification

- For one panel, confirm the box plot's median/IQR visually match
  `summary.csv`'s mean/min/max for that `(capability-file, liveness, pending,
  encoding, policy, random)` group (sanity check that the box is drawn from the
  same data the table reports).
- Confirm `alphabetic`/`domain` markers land at the correct log-y height and are
  visually distinguishable from each other and from outlier points in the box.
