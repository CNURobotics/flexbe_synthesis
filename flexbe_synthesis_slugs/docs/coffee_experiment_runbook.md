# Coffee Experiment Runbook

Concrete directions for running the Coffee experiment with the matrix
generator, batch harness, and postprocessor. The runbook is scoped to the
Coffee example in this repository; the same tools can run against an external
example directory without Coffee-specific harness code. See
[batch_run_harness.md](batch_run_harness.md)'s `example` field note for the
path-not-name design constraint this drives.

## What exists for Coffee today

```
flexbe_synthesis_examples/example/coffee_maker/
  capabilities/
    coffee_capabilities.yaml            # 52 lines — base capability set
    coffee_capabilities_extended.yaml   # 117 lines — larger capability set
  pipelines/
    preprocesses_data.yaml              # capabilities_path etc., ROS-param-driven
    processes_data.yaml                 # synthesis_timeout_s, spec_name, etc.
  specs/
    coffee_demo_capabilities_spec.yaml  # the spec slugs_coffee_matrix actually uses
    coffee_full_spec.yaml / .structuredslugs
```

The full Coffee capability sweep covers both capability files × both encodings
× both liveness formulations × both pending settings:
`2 × 2 × 2 × 2 = 16` combinations. Scenario labels are:

- `coffee_capabilities.yaml` (52 lines) = scenario **2** ("baseline capability-based").
- `coffee_capabilities_extended.yaml` (117 lines) = scenario **3** ("extended
  with complete/failure outcomes").
- Encoding: one-hot / enumerated.
- Liveness × pending: `S`, `F`, `S+P`, `F+P`.

**Included as a 17th combination (the hand-written baseline)**: scenario `1`
is a hand-written full spec
([`coffee_full_spec.yaml`](../../flexbe_synthesis_examples/example/coffee_maker/specs/coffee_full_spec.yaml)),
authored directly rather than generated through the capability pipeline, so
**encoding/liveness/pending do not apply** to it. It is *not* excluded,
however: it loads and compiles through the **same** `slugs_spec_compiler` and
`slugs_synthesizer` (see
[`full_spec_processes_def.yaml`](../../flexbe_synthesis_examples/example/coffee_maker/pipelines/full_spec_processes_def.yaml):
`spec_loader → request_spec → compiler → synthesizer`), so the
variable-ordering and CUDD-reordering sweep applies to it just like the 16
capability combos. `coffee_matrix` emits it as one extra combo with sentinel
`encoding=full_spec`, `liveness=na`, `pending=false`, and `full_spec=true`
(which tells the harness to skip the capability/liveness/pending generation and
bind only the request goal). It answers a distinct question — is the
hand-written baseline also ordering-sensitive, or is that penalty specific to
the generated encodings?

## Directions

Run from the repository root after sourcing the built workspace:

```bash
cd ~/chrislab/src/flexbe_synthesis
source ~/chrislab/setup.bash

export FLEXBE_SYNTHESIS_HOME="$HOME/.flexbe_synthesis"
export COFFEE_EXP="$HOME/.flexbe_synthesis/experiments/coffee"
export COFFEE_STATE_MAPPINGS="$(ros2 pkg prefix flexbe_synthesis_generic)/share/flexbe_synthesis_generic/mappings/infinite_mappings.yaml"
test -f "$COFFEE_STATE_MAPPINGS"
mkdir -p "$COFFEE_EXP/matrices" "$COFFEE_EXP/runs"
```

If you deleted `~/.flexbe_synthesis` to start from a clean experiment state,
recreate the workspace definition before running the harness:

```bash
ros2 launch flexbe_synthesis_examples coffee_preprocess_example.launch.py
```

That runs the full generic preprocessing pipeline and rewrites:

```text
~/.flexbe_synthesis/workspace_defn.yaml
~/.flexbe_synthesis/coffee_maker/configs/
```

> **Mappings — use `infinite_mappings.yaml` for Coffee.** Every Coffee launch
> (`coffee_capabilities_example`, `..._parsed_example`, `coffee_full_spec_example`)
> uses `infinite_mappings.yaml` (`sm_outcome_mappings: {}` — the Coffee scenario
> runs forever, with no terminal `finished` outcome). Pass it explicitly to the
> harness; its generic default is `global_mappings.yaml`, which injects a
> spurious `finished` proposition. That default **fails the hand-written
> baseline** (`Mapped success outcome 'finished' is not a proposition`) and also
> changes the capability-row BDD sizes, so all Coffee runs — capability and
> baseline alike — must use `infinite_mappings.yaml`. The `--state-mappings`
> path below resolves through the installed `flexbe_synthesis_generic` package
> share, so it works from either the workspace root or the repository root.
> If `test -f "$COFFEE_STATE_MAPPINGS"` fails, rebuild/source the workspace and
> rerun the export before launching the harness.

First run a smoke test — now **two rows**, one capability combo and one
hand-written baseline, so both build paths are exercised:

```bash
python3 -m flexbe_synthesis_slugs.helpers.coffee_matrix \
  --smoke \
  --n-trials 1 \
  "$COFFEE_EXP/matrices/coffee_smoke.yaml"

python3 -m flexbe_synthesis_slugs.helpers.batch_run_harness \
  --matrix "$COFFEE_EXP/matrices/coffee_smoke.yaml" \
  --out-dir "$COFFEE_EXP/runs/coffee_smoke" \
  --state-mappings "$COFFEE_STATE_MAPPINGS" \
  --slugs-bin /usr/local/bin/slugs \
  --synthesis-timeout-s 60
```

Then generate and run the full Coffee ordering matrix:

```bash
python3 -m flexbe_synthesis_slugs.helpers.coffee_matrix \
  --full \
  --n-trials 5 \
  "$COFFEE_EXP/matrices/coffee_full.yaml"

python3 -m flexbe_synthesis_slugs.helpers.batch_run_harness \
  --matrix "$COFFEE_EXP/matrices/coffee_full.yaml" \
  --out-dir "$COFFEE_EXP/runs/coffee_full" \
  --state-mappings "$COFFEE_STATE_MAPPINGS" \
  --slugs-bin /usr/local/bin/slugs \
  --synthesis-timeout-s 60
```

Use a fresh `--out-dir` for each full run, or remove the old run directory
before starting again. The harness refuses to append to an existing
`master.csv` by default because mixing old and new matrices makes the plots
misleading. Use `--append` only when deliberately resuming into an existing
`master.csv`.

The full matrix is the 16 Coffee capability combinations above **plus the
hand-written baseline (17 combos total)**, each with four fixed treatments plus
40 seeded `random` orderings under each CUDD reordering policy. The policies
are:

- `off`: Slugs gets `--no-reorder`
- `threshold_250`: Slugs gets `--reorder-threshold 250`

The `auto` policy (Slugs default sifting) was **dropped**: prior-run data
([synthesis-experiments/coffee_run](../../..)) showed it is effectively
identical to `off` at these BDD sizes (default sifting rarely fires), while
`threshold_250` never lost to it and often won 3-4x. `off` is kept as the
no-reorder floor/control. The fixed treatments are `alphabetic` and `domain`
under each policy. The baseline uses the same ordering sweep but no
encoding/liveness/pending axes (it is a single combo, not part of the 16-way
cross product).

```text
per combo: 4 fixed orderings + 40 random seeds × 2 reordering policies = 84 rows
(16 capability combos + 1 hand-written baseline) × 84 = 1428 matrix rows
1428 matrix rows × 5 exact repeated trials = 7140 executed trials
```

Adjust `--random-seeds` to change the number of random variable-order samples,
and adjust `--n-trials` to change the number of exact repeats per matrix row.
The default Coffee generator uses `--n-trials 5`; the smoke command above uses
`--n-trials 1` to stay quick.

The harness prints one global progress line per contiguous experiment combo,
not one line per random seed:

```text
Preparing capabilities: .../coffee_capabilities.yaml
Tests 341-380 of 7140: coffee_capabilities, one-hot, S, no pending, random, off
```

Detailed process output is redirected to log files by default so the terminal
stays readable during the full matrix. Add `--verbose-console` to the harness
command if you need the underlying preprocess/process output streamed directly
to the terminal.

## Output Layout

The generated matrices and raw results live under:

```text
~/.flexbe_synthesis/experiments/coffee/
  matrices/
    coffee_smoke.yaml
    coffee_full.yaml
  runs/
    coffee_smoke/
      harness.log
      master.csv
      summary.csv
      runs/<row_id>/trial_00/synthesis_byproducts/
        CoffeeSM.structuredslugs
        CoffeeSM.slugsin
        CoffeeSM.json
        CoffeeSM.output
        CoffeeSM.variable_order.json
      runs/<row_id>/trial_00/harness.log
    coffee_full/
      harness.log
      master.csv
      summary.csv
      runs/<row_id>/trial_00/synthesis_byproducts/
        ...
      runs/<row_id>/trial_00/harness.log
```

`master.csv` is the canonical raw data file.  Each row points back to its
`trial_dir`, Slugs output log, JSON strategy, and variable-order sidecar.

`harness.log` under the run directory captures preprocessing output such as
capability loading and transition-relation generation.  Each trial directory's
`harness.log` captures spec-generation, compilation, synthesis, and reduction
output for that trial.

`summary.csv` is a convenience post-processing artifact generated by the
harness after each matrix run.  It groups `master.csv` by capability file,
encoding, liveness, pending mode, ordering mode, and reordering flag, then
writes `n`, failure count, and mean/min/max/stdev columns for the main numeric
metrics.

`CoffeeSM.variable_order.json` records the requested input/output declaration
order, requested CUDD reordering mode, Slugs-reported CUDD reordering status,
reordering count/time, and final variable order when the Slugs binary reports
that block.

Generated capability/transition configs still follow the normal FlexBE
synthesis convention and are written under:

```text
~/.flexbe_synthesis/coffee_maker/configs/
```

## Processing `master.csv`

The immediate post-run checks are:

```bash
wc -l "$COFFEE_EXP/runs/coffee_full/master.csv"
```

With the default `--n-trials 5`, the line count should be `7141`: one header
plus 7140 executed trial rows (1428 matrix rows × 5 trials).

Inspect failures:

```bash
python3 - <<'PY'
import csv
from pathlib import Path

master = Path.home() / '.flexbe_synthesis/experiments/coffee/runs/coffee_full/master.csv'
with master.open(newline='') as f:
    rows = list(csv.DictReader(f))

failures = [r for r in rows if r.get('failure') or r.get('return_code') not in ('0', 0)]
print(f'rows={len(rows)} failures={len(failures)}')
for row in failures[:10]:
    print(row['row_id'], row.get('error_code'), row.get('failure'))
PY
```

Confirm the reordering axis is populated and that Slugs reported the requested
CUDD state:

```bash
python3 - <<'PY'
import csv
from collections import Counter
from pathlib import Path

master = Path.home() / '.flexbe_synthesis/experiments/coffee/runs/coffee_full/master.csv'
with master.open(newline='') as f:
    rows = list(csv.DictReader(f))

print('ordering_mode × requested_reordering_policy')
for key, count in sorted(Counter(
    (r['ordering_mode'], r.get('reordering_policy', '')) for r in rows
).items()):
    print(key, count)

print('\nrequested_policy × requested_threshold × reported_cudd_reordering × next_reordering')
for key, count in sorted(Counter(
    (
        r.get('reordering_policy', ''),
        r.get('reordering_threshold', ''),
        r.get('cudd_reordering_enabled', ''),
        r.get('cudd_next_reordering', ''),
    )
    for r in rows
).items()):
    print(key, count)
PY
```

The harness writes the quick grouped summary automatically:

```bash
ls -lh "$COFFEE_EXP/runs/coffee_full/master.csv" \
       "$COFFEE_EXP/runs/coffee_full/summary.csv"
```

If a plot looks stale, compare timestamps:

```bash
ls -lh "$COFFEE_EXP/runs/coffee_full/master.csv" \
       "$COFFEE_EXP/runs/coffee_full/summary.csv" \
       "$COFFEE_EXP/runs/coffee_full/plots"
```

Regenerate postprocessing artifacts after every matrix run; older plots can
otherwise reflect a previous matrix even when `master.csv` has changed.

Generate the default peak-BDD-node LaTeX table and ordering plots:

```bash
python3 -m flexbe_synthesis_slugs.helpers.experiment_postprocess \
  --run-dir "$COFFEE_EXP/runs/coffee_full" \
  --refresh-summary \
  --summary-plot
```

That writes:

```text
$COFFEE_EXP/runs/coffee_full/
  summary.csv
  tables/cudd_peak_nodes_mean.tex           # single-metric diagnostic table
  tables/coffee_one_hot_results.tex         # one-hot table, incl. scenario 1 baseline
  tables/coffee_enumerated_results.tex      # enumerated table
  plots/ordering_summary_cudd_peak_nodes.pdf
  plots/ordering_summary_cudd_peak_nodes.png
  plots/ordering_summary_capability_file_*_cudd_peak_nodes.pdf
  plots/ordering_summary_capability_file_*_cudd_peak_nodes.png
  plots/complexity_time_cudd_peak_nodes.pdf
  plots/complexity_time_cudd_peak_nodes.png
  plots/*cudd_peak_nodes.pdf
  plots/*cudd_peak_nodes.png
```

If you want the summary figures and timing relationship plot, but not the
individual diagnostic ordering plots:

```bash
python3 -m flexbe_synthesis_slugs.helpers.experiment_postprocess \
  --run-dir "$COFFEE_EXP/runs/coffee_full" \
  --refresh-summary \
  --summary-plot-only
```

Add `--no-time-plot` to skip `complexity_time_cudd_peak_nodes.*`.  Add
`--time-x-metric <metric>` if you want the timing plot x axis to use a metric
other than `cudd_peak_nodes`.

To write only the combined ordering grid and suppress both the split figures
and timing plot:

```bash
python3 -m flexbe_synthesis_slugs.helpers.experiment_postprocess \
  --run-dir "$COFFEE_EXP/runs/coffee_full" \
  --refresh-summary \
  --summary-plot-only \
  --summary-plot-split none \
  --no-time-plot
```

The default split figures write one
`ordering_summary_capability_file_*_cudd_peak_nodes.pdf` per capability set,
with a shared log-y range within each capability-set grid.  The base and
extended figures can still use different y ranges because they are separate
plots.  The script sets an explicit padded y range from each plot's data, so
single-valued grids do not get stretched to a full log decade. Use
`--summary-plot-split-independent-y` only for diagnostic plots where each panel
should autoscale independently.

Use `summary.csv` for quick inspection and table generation.  Keep using
`master.csv` for distribution plots and any analysis that needs per-seed or
per-trial data.

## Tables and Plots

The postprocessor writes Coffee result tables directly:
`tables/coffee_one_hot_results.tex` (one-hot, including the hand-written
baseline as column `1`) and `tables/coffee_enumerated_results.tex`
(enumerated). Both use the same row layout: AP/formula counts, BDD nodes, SM
sizes, and three active timing rows — **Realizability**, **Extraction**, and
**Auditing** (ms). The mean CUDD-peak-size ordering table is the summary/plot
output below. Other examples can use the same generators once their matrices
are available.

Each cell is the **mean over the `random` orderings under `threshold_250`**
(the retained on-reordering policy). Override with `--table-policy` /
`--table-ordering`.

The `|φ_i^a|` / `|φ_i^g|` rows (`env_init_count` / `sys_init_count`) are counted
from the compiled `.structuredslugs` `[ENV_INIT]` / `[SYS_INIT]` sections at
build time (Slugs itself does not emit those counts, only TRANS/LIVENESS), so
they populate correctly alongside the other formula counts.

For the single-metric diagnostic table:

- Use `tables/cudd_peak_nodes_mean.tex` as the starting point for the
  peak-BDD-node table.
- Keep one representative statistic per table cell, usually the mean.
- Keep one representative table statistic and put spread in plots.
- Treat the `F+P` cells (`2FP`, `3FP`) as additional sweep cells.
- The hand-written scenario `1` column is now **generated by this matrix too**
  (rows with `encoding=full_spec`, `liveness=na`); its peak-node value can be
  taken from the same `summary.csv`/table output rather than carried over
  by hand. Encoding/liveness/pending don't apply to it, but it carries a full
  ordering distribution like every other combo (see the ordering plots).

Generate a table for another metric by changing `--metric`:

```bash
python3 -m flexbe_synthesis_slugs.helpers.experiment_postprocess \
  --run-dir "$COFFEE_EXP/runs/coffee_full" \
  --metric realizability_time_s \
  --no-plots
```

Common metric names are `cudd_peak_nodes`, `cudd_live_nodes`,
`realizability_time_s`, `extraction_time_s`, `overall_pipeline_time_s`,
`slugs_sm_size`, and `reduced_sm_size`.

The default postprocessor also writes `plots/complexity_time_cudd_peak_nodes.*`,
which plots peak BDD nodes against Slugs realizability time and overall
pipeline wall-clock time.  Use this figure to show whether the structural BDD
proxy tracks the measured computational cost.

For ordering plots:

- Use `master.csv`, not `summary.csv`, so seeded `random` distributions remain
  visible.
- Plot `cudd_peak_nodes` on a log-y axis.
- Put CUDD reordering policy as centered x-axis group labels, with slanted
  encoding labels under each box.
- Facet or otherwise separate capability set and liveness/pending mode.
- Use random-seed runs as the distribution for each reordering policy, with
  `alphabetic` and `domain` overlaid as reference points.
- Overlay mean `overall_pipeline_time_s` for the random-seed runs on a right
  log-y axis, using the same policy/encoding x positions.

The generated plots follow that convention: one plot per capability-file ×
liveness × pending setting, CUDD reordering policy as the main horizontal
grouping, encoding as the within-group label, random ordering as the box plot,
fixed ordering treatments overlaid as markers, and mean pipeline time overlaid
on the right axis.

The summary plot follows the same visual encoding but places every
capability-file × liveness × pending panel in one figure with a shared y axis
and one legend. The default command also writes split capability-set versions
because the combined y-range can hide differences within either capability
set; each split grid has one shared y range, but the base and extended grids can
differ from each other.

Use `--summary-time-metric realizability_time_s` to put Slugs realizability
time on the right axis instead, or `--summary-plot-no-time-axis` to suppress
the timing overlay.

## Verification

- `master.csv` row count for the Coffee run matches the arithmetic in step 2
  exactly (no silently-dropped or silently-duplicated trials).
- `alphabetic` mode's peak-BDD-node value stays stable for previously recorded
  scenario cells. The `F+P` cells are additional sweep cells with no prior
  continuity baseline.
