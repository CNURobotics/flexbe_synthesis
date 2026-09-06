# Issue 2: Batch-run harness for repeated synthesis sampling

> **Status: implemented.** Shipped as
> [`helpers/batch_run_harness.py`](../flexbe_synthesis_slugs/helpers/batch_run_harness.py)
> (console script `slugs_batch_run_harness`). This doc is kept for the design
> rationale; where the shipped interface differs from the original design it
> has been reconciled below (the harness is matrix-file-driven, reordering is a
> three-way policy, and graph rendering was not wired in). See
> [coffee_experiment_runbook.md](coffee_experiment_runbook.md) for the live
> run procedure.

## Context

Most reported synthesis numbers today are single runs; only one benchmark
(`two-rivers 3S`) has ever had 10-run variance data, and that was produced
outside this repo (no harness code for it exists here). This is a blocking
prerequisite for the ordering-robustness study
([variable_ordering.md](variable_ordering.md), Issue 3) and for the planned
liveness-formulation and pending-encoding robustness studies (Issues 4/5):
none of those can produce a defensible min/mean/max table without a harness
that runs a given configuration N times and records every run, not just an
average.

Design principle from the source issue: **the harness emits raw per-run rows
only — it does not aggregate.** Aggregation (mean/min/max/stdev, Δ between
encodings, etc.) happens downstream in analysis code, so the raw data always
stays available to recompute a different statistic later without re-running
Slugs. This is a deliberate departure from `slugs_timing_stats.py`'s current
behavior, which prints aggregated stats and only optionally keeps per-run
JSON via `--save-raw-metrics`.

## Config matrix

One row of the matrix is `(example, encoding, liveness, pending, ...)` — the
`...` grows as later issues land (Issue 3 adds the matrix inputs
`ordering_mode`, `ordering_seed`, `reordering_enabled`, and
`reordering_threshold`; `reordering_policy` is a derived `off`/`auto`/`threshold_N`
label, not a settable field; future issues may add more). Concretely,
today's pipeline axes:

- `example`: **a path to a capabilities directory, not just a name.**
  Coffee lives in this repo
  ([flexbe_synthesis_examples/example/coffee_maker/](../../flexbe_synthesis_examples/example/coffee_maker/)),
  but other benchmark examples (two-rivers, quadcopter) live outside it and
  the same config-matrix/harness must run against them unmodified later — so
  the harness takes a `capabilities_dir` (or `--examples-root` for a batch of
  them) rather than hardcoding a repo-relative lookup by name. See
  [coffee_experiment_runbook.md](coffee_experiment_runbook.md) for the
  Coffee-scoped first pass this constraint is designed to generalize from.
- `encoding`: which pipeline YAML — `capability_processes_def.yaml`
  (**one-hot**: named boolean capability variables, mutex-constrained — see
  `ONEHOT_MUTEX_MARKER` in
  [processes/slugs_capability_specification.py](../flexbe_synthesis_slugs/processes/slugs_capability_specification.py))
  vs `capability_processes_def_parsed.yaml` (**enumerated**: compact,
  numeric-indexed capability encoding).
- `liveness`: `S` / **System-Goal Liveness** (renamed from "Adversarial-Liveness";
  code identifier `SlugsSystemGoalLiveness` now matches) vs `F` / fair-outcome
  (`SlugsFairOutcomeLiveness`) — see
  [variable_ordering.md](variable_ordering.md) §7 for why this is a confound
  worth sweeping, not just a fixed pipeline choice.
- `pending`: with/without — whether `SlugsPendingSpecification`
  ([processes/slugs_pending_specification.py](../flexbe_synthesis_slugs/processes/slugs_pending_specification.py))
  runs. Confirmed by Issue 4/5's matrix definitions (`pending (with/without)`):
  a simple include/exclude toggle, not multiple named strategies. Currently
  unconditionally included in the pipeline YAML (no commented-out alternative
  like `liveness` has), so making this an axis means the harness must be able
  to build a spec with that process skipped, not just re-point at a different
  `name:`.

Each matrix row also carries an `N` (repeat count) and a `seed` (only
meaningful for configurations with randomness, e.g. Issue 3's `random`
ordering mode — deterministic configs still get `N` repeats per the trial
policy below, just with a fixed/absent seed).

## Harness design

New module `flexbe_synthesis_slugs/flexbe_synthesis_slugs/helpers/batch_run_harness.py`,
registered as a console script (`slugs_batch_run_harness`, following the
existing `slugs_stats_helper`/`slugs_timing_stats` pattern in
[setup.py:53](../setup.py#L53)).

**Input**: a YAML config-matrix file — either a top-level list, or a mapping
with a `rows:` list — of dicts with fields `{example, system_name, spec_name,
spec_path, capabilities_path, encoding, liveness, pending, ordering_mode,
ordering_seed, reordering_enabled, reordering_threshold, n_trials,
initial_conditions, goals, sm_outcomes}`. The matrix file is **required**
(`--matrix`); there is **no single-row flag form** — produce a one-off row by
generating a one-row matrix (e.g. `slugs_coffee_matrix --smoke`). Full CLI:
`--matrix` and `--out-dir` (required), plus `--slugs-bin`, `--state-mappings`,
`--synthesis-timeout-s`, `--synthesis-home`, `--verbose-console`, `--append`.

**Per matrix row × trial, the harness**:
1. Builds the spec by calling the relevant pipeline processes directly in
   sequence (`SlugsCapabilitySpecification` → `SlugsRequestSpecification` →
   the selected liveness process → `SlugsPendingSpecification` if enabled →
   `SlugsSpecCompiler`'s two calls to `GR1Specification.write_structured_slugs_file()`
   / `slugs_compiler.performConversion()`) — same "call processes directly,
   skip the ROS pipeline-manager" approach as
   [variable_ordering.md](variable_ordering.md) §7, generalized to the full
   axis set instead of just ordering mode.
2. Runs `slugs` once (reusing `SlugsSynthesizerHelper.call_slugs_synthesizer`
   rather than re-implementing subprocess handling).
3. Parses the captured output via (an extended) `slugs_stats_helper.parse_slugs_log`.
4. Runs `SlugsSMReducer` on the result and records `SlugsAutomaton.size()`
   before (`slugs_sm_size`, i.e. `|Slugs SM|`) and after (`reduced_sm_size`,
   i.e. `|Reduced|`) reduction
   ([slugs_automaton.py:123](../flexbe_synthesis_slugs/helpers/slugs_automaton.py#L123),
   [processes/slugs_sm_reducer.py](../flexbe_synthesis_slugs/processes/slugs_sm_reducer.py)).
4b. Runs `strategy_auditor` on the synthesized automaton and records the wall-clock
   `auditor_time_s` (measured by the harness) plus `audit_valid` /
   `audit_incomplete` / `audit_failure_kind`. Timeout via `--auditor-timeout-s`
   (default 60s). Skipped when synthesis failed (empty automaton).
5. *(Not implemented in the shipped harness.)* Optional Mealy-graph rendering
   via [helpers/mealy2dot.py](../flexbe_synthesis_slugs/helpers/mealy2dot.py)
   was designed as a `--render-graphs` step (off by default for large sweeps,
   since rendering 100 graphs for a `random`-mode cell is pure waste) but is
   not wired into `batch_run_harness.py`. Render graphs separately from a
   trial's saved `.json` when needed.
6. Appends **one row** to the master CSV — no averaging, no summarizing.

### Artifact layout — reuses the existing pipeline convention, no new logic

The harness doesn't need its own artifact-placement code: `SlugsSpecCompiler`
and `SlugsSynthesizerHelper` already write every per-run artifact
(`.slugsin`, `.json`, `.output`, and — once Issue 3 lands — `variable_order.json`)
under `<specs_output_dir_path>/synthesis_byproducts/<spec_name>.*`
([slugs_spec_compiler.py:52-55](../flexbe_synthesis_slugs/processes/slugs_spec_compiler.py#L52),
[slugs_synthesizer_helper.py:56-59](../flexbe_synthesis_slugs/helpers/slugs_synthesizer_helper.py#L56)).
`mealy2dot.py` follows the same base-filename convention. So the only thing
the harness controls per trial is **which `specs_output_dir_path` it passes
in** — everything downstream already lands in the right place because the
existing processes already do that:

```
<out_dir>/
  harness.log                    # run-level preprocess/cache logs
  master.csv                     # every trial's row, whole config-matrix run — the one
                                  # file everything downstream reads from
  runs/
    <row_id>/                    # one specs_output_dir_path per config-matrix row
      trial_00/
        synthesis_byproducts/    # populated entirely by existing pipeline code
          <spec_name>.structuredslugs
          <spec_name>.slugsin
          <spec_name>.json
          <spec_name>.output
          <spec_name>.variable_order.json
        harness.log              # process output for this trial
      trial_01/
        ...
```

The terminal output is intentionally sparse for large matrices: one
`Preparing capabilities: ...` line per capability cache entry, one
`Tests start-end of N: ...` line per contiguous experiment-combo group, and
final artifact paths. Underlying
preprocess/process stdout and stderr are redirected to the run/trial
`harness.log` files by default; use `--verbose-console` to stream them to the
terminal while debugging.

`row_id` is a deterministic slug built from the config tuple —
`<example>__<capability_stem>__<encoding>__<liveness>__<pending>__<ordering_mode>__seed<seed>__<reordering_policy>`,
e.g. `coffee__coffee_capabilities__enumerated__S__with_pending__random__seed7__auto`
(seed is not zero-padded; `<pending>` is `with_pending`/`no_pending`;
`<reordering_policy>` is the derived `off`/`auto`/`threshold_N` label) — so any
trial's artifacts can be found from its `master.csv` row without a lookup table.
Per-trial folders keep every run's raw output on disk — needed for
Issue 6's clause-order sanity check and general debugging, not just the
metrics extracted into `master.csv`.

### Downstream summarization (shared by Issues 4, 5, 13)

Downstream analysis is deliberately **separate from the harness** when it
produces publication artifacts (keeps "harness emits raw rows" honest — these
read `master.csv`, they don't run Slugs):

- The harness writes `summary.csv` automatically after each matrix run by
  grouping `master.csv` over the config-matrix columns and computing
  min/max/mean/stdev per metric.
- `experiment_postprocess.py`, registered as `slugs_experiment_postprocess`,
  consumes `master.csv`/`summary.csv` and writes LaTeX tables plus ordering
  plots. Its LaTeX default emits a **single representative statistic per
  cell** (mean, or per-metric override), matching one column per cell like
  today's Tables I–IV. Full spread belongs in figures (Issue 13), not extra
  table columns.

### Per-run columns

The paper's tables report six formula counts
(`|φ^a_i|, |φ^g_i|, |φ^a_s|, |φ^g_s|, |φ^a_l|, |φ^g_l|` — assumption/guarantee
× init/safety/liveness). `slugs_stats_helper.SlugsRunMetrics` parses the four
that Slugs emits (`env_trans_count`, `sys_trans_count`, `env_liveness_count`,
`sys_liveness_count`); Slugs does **not** emit `|ENV_INIT|`/`|SYS_INIT|`, so the
harness counts `env_init_count`/`sys_init_count` itself from the compiled
`.structuredslugs` `[ENV_INIT]`/`[SYS_INIT]` sections (`count_init_clauses`).

- `peak_bdd_nodes`, `live_bdd_nodes` (existing: `cudd_peak_nodes`,
  `cudd_live_nodes` — matches paper's "CUDD Peak/Live BDD Nodes" exactly)
- `realizability_time_s` (existing: `synthesis_time_s` — matches paper's
  "Slugs (ms)")
- `extraction_time_s` (existing: `explicit_extraction_time_s`)
- `auditor_time_s` (**new** — wall-clock around the `strategy_auditor` run on the
  synthesized automaton, measured by the harness; matches the paper's "Auditing
  (ms)"), plus non-numeric `audit_valid` / `audit_incomplete` /
  `audit_failure_kind`
- `overall_pipeline_time_s` (**new** — wall-clock around the harness's own
  build+compile+synthesize+reduce sequence, measured by the harness itself,
  not parsed from Slugs output — matches paper's "Overall (ms)")
- `slugs_sm_size` / `reduced_sm_size` (**new**, per above — matches paper's
  `|Slugs SM|` / `|Reduced|`)
- `ap_i`, `ap_o` (existing — matches paper's `|AP_I|`/`|AP_O|`)
- `env_init_count`, `sys_init_count` (**new** — counted from the compiled
  `.structuredslugs`, per above; matches
  `|φ^a_i|`/`|φ^g_i|`), `env_trans_count`, `sys_trans_count` (existing,
  matches `|φ^a_s|`/`|φ^g_s|`), `env_liveness_count`, `sys_liveness_count`
  (existing, matches `|φ^a_l|`/`|φ^g_l|`)
- `realizable` (existing, bool)

Metadata columns (**all new** — none of this is captured anywhere today; the
authoritative list is `CSV_FIELDNAMES` in `batch_run_harness.py`):

- Ordering/reordering: `ordering_mode`, `ordering_seed`, `reordering_enabled`,
  `reordering_threshold`, `reordering_policy` (derived `off`/`auto`/`threshold_N`
  label), `requested_input_order`, `requested_output_order`,
  `final_variable_order`, `cudd_reordering_enabled`, `cudd_next_reordering`,
  `cudd_reorderings`, `cudd_reordering_time_s`, `cudd_var_count` (from
  [variable_ordering.md](variable_ordering.md); the requested input/output
  orders record the compiler input, while the final order and CUDD fields
  record what Slugs actually used after any dynamic reordering). Note the
  order is split into two columns (`requested_input_order` /
  `requested_output_order`), reflecting the `.slugsin` `[INPUT]`/`[OUTPUT]`
  split, not a single combined order.
- `git_sha_flexbe_synthesis`, `git_sha_slugs` (two separate repos, independently
  versioned — both matter, since a Slugs-side patch like the `--no-reorder`/
  post-sifting-dump changes affect results just as much as a pipeline change)
- `hostname` (`platform.node()`), `timestamp` (ISO 8601, UTC)
- `example`, `system_name`, `spec_name`, `capability_file`, `encoding`,
  `liveness`, `pending`, `run_index` (which of the `N` trials this row is),
  `return_code`, `error_code`
- Artifact back-pointers: `trial_dir`, `slugs_output_file`, `slugs_json_file`,
  `variable_order_file`, `failure` (empty on success)

### Trial policy (matches variable_ordering.md §7)

Primary metric for statistical claims is **peak BDD nodes**, which is
deterministic given a fixed `.slugsin` + fixed reordering setting — so
`N`-trial spread on that metric is a correctness signal (it should be ~0
unless something's nondeterministic that shouldn't be) rather than a
noise-smoothing target. Timing fields are expected to be noisy and are
secondary; `N` trials mainly serve to smooth *those*. Both facts fall out
naturally from "raw rows only, aggregate downstream" — nothing in the harness
itself needs to treat these metric classes differently.

## Relationship to variable_ordering.md (Issue 3)

Issue 3's ordering work slots into this harness's config matrix as four more
row fields — `ordering_mode`, `ordering_seed`, `reordering_enabled`,
`reordering_threshold` (`reordering_policy` is derived from the latter two, not
set directly) — rather than being its own driver script. [variable_ordering.md](variable_ordering.md) §7's `--tag`
proposal for `slugs_timing_stats.py` is superseded by this harness's metadata
columns — once this harness exists, Issue 3 doesn't need its own aggregation
glue, just entries in the config matrix.

## Tests

- Unit test the row-building logic against a small fixture spec with
  `n_trials=2`, asserting exactly 2 output rows with distinct `run_index`,
  identical structural metrics (peak/live nodes, realizable, AP/formula
  counts — deterministic), and independently-measured `overall_pipeline_time_s`
  per row.
- Unit test metadata capture (`git_sha_*` via `git rev-parse HEAD` in each
  repo, `hostname`, `timestamp` monotonically increasing across rows) with
  the actual `subprocess`/`platform` calls mocked.
- Integration test: run the harness against one real example spec with
  `n_trials=3`, confirm the output file has 3 rows and every declared column
  is populated (no silent `None`s from an unparsed Slugs stats line).

## Verification

- Generate a one-row smoke matrix and run it:
  `slugs_coffee_matrix --smoke --n-trials 3 /tmp/smoke.yaml` then
  `slugs_batch_run_harness --matrix /tmp/smoke.yaml --out-dir /tmp/harness_test
  --slugs-bin slugs`. Inspect `/tmp/harness_test/master.csv`: 3 rows, identical
  `cudd_peak_nodes`/`realizable`, varying `overall_pipeline_time_s`, all
  metadata columns populated.
- Confirm `master.csv` contains only raw per-trial rows — aggregation is
  confined to the separately written `summary.csv` (grouped mean/min/max/stdev
  per config group), never mixed into the raw file.
