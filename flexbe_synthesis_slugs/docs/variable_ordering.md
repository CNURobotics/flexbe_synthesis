# Variable-ordering control for the Slugs synthesis pipeline

> **Status: implemented.** `order_variables()` lives in
> [`gr1_specification.py`](../flexbe_synthesis_slugs/helpers/gr1_specification.py)
> and the `SlugsAdversarialLiveness → SlugsSystemGoalLiveness` rename is done.
> One design change landed during implementation: reordering grew a second
> knob. Instead of a single `reordering_enabled` boolean, the pipeline now
> carries **`reordering_enabled` (bool)** *and* **`reordering_threshold`
> (int|None)**, and downstream code derives a three-way **`reordering_policy`**
> label from the pair — `off` (`reordering_enabled=False`), `threshold_N`
> (`reordering_enabled=True`, `reordering_threshold=N` → Slugs
> `--reorder-threshold N`), or `auto` (`reordering_enabled=True`, no threshold →
> Slugs default sifting). The Coffee sweep uses `off`, `auto`, `threshold_250`.

## Context

Issue 3 asks for pipeline control over the initial BDD variable ordering fed to
Slugs, because "compact encoding costs more" (the paper's headline claim) could
currently be an artifact of the pipeline's naive alphabetic ordering rather than
a real property of the encoding.

Investigation established the concrete constraints this plan works within:

- Slugs' CUDD sifting was previously **unconditionally on** with no CLI toggle.
  The user has since patched `~/slugs` (commit `f511e48`) to add a `--no-reorder`
  flag (`BFBddManager::setReorderingEnabledForNewManagers`, wired in `main.cpp`,
  default unchanged/on). This plan consumes that flag; **no further changes to
  `~/slugs` are made here.**
- `.slugsin`'s `[INPUT]`/`[OUTPUT]` sections are read as two fully separate
  blocks (`synthesisContextBasics.cpp:218-244`): every input variable (with its
  primed pair) gets a CUDD index before any output variable does. So a
  capability's output activation bit can never be initially adjacent to an
  input outcome bit — "domain" ordering can only group related bits *within*
  each section, not across the input/output boundary. This is a real
  limitation of the current file format, not a shortcut; the domain mode
  docstring/log output will say so explicitly.
- `env_props`/`sys_props` on `GR1Specification` are plain `set()`
  ([gr1_specification.py:50-51](../flexbe_synthesis_slugs/helpers/gr1_specification.py#L50-L51)),
  so there is no surviving "declaration order" to fall back on — every mode
  must actively compute an order.
- Resolved semantics:
  - `alphabetic`: `sorted()` order, reordering **on** — today's unchanged
    default, preserves continuity with existing tables.
  - `random`: seeded shuffle, reordering on.
  - `domain`: capability-grouped order (within each section only), reordering on.
  - `dynamic`: same `sorted()` order as alphabetic, reordering explicitly
    forced/logged on — exists as a distinct, nameable treatment so it can be
    paired against an `alphabetic` + `reordering_enabled: false` control run
    (the on/off comparison used to isolate the reordering effect).
  - `reordering_enabled` (bool, default `true`) is an **independent** knob from
    ordering mode, since the on/off comparison needs to combine with any mode
    (mainly `alphabetic`, to isolate the reordering effect from the ordering effect).

Follow-up patch `3aee1ac` ("Report post-sifting CUDD variable order in stats
output") closes the remaining gap: Slugs now dumps each CUDD level's variable
name/index (`Cudd_ReadInvPerm` + `variableNames`) to stderr after
`checkRealizability()`, already captured into the existing `<name>.output`
file written by `call_slugs_synthesizer`. So "log the actual final ordering
used" can mean the *true* post-sifting order, not just the pre-sifting order
we requested — see step 3 below, which parses that block out of the captured
Slugs output and folds it into the same sidecar JSON the compiler writes.

## Design

Independent pipeline inputs, following the existing `synthesis_timeout_s`
pattern (plain `self.data` key set in `processes_data.yaml`, not the typed
Request message — this is a pipeline/experiment knob, not a per-request
end-user field):

- `variable_ordering_mode: str = 'alphabetic'` (`alphabetic|random|domain|dynamic`)
- `variable_ordering_seed: int | None = None` (used by `random`)
- `reordering_enabled: bool = True`
- `reordering_threshold: int | None = None` (**added during implementation** —
  when set with `reordering_enabled=True`, passed to Slugs as
  `--reorder-threshold N`; see the status note above for the derived
  `reordering_policy` label)

### 1. `flexbe_synthesis_slugs/helpers/gr1_specification.py`

- Add a module-level `order_variables(names, mode, rng)` helper implementing
  the four strategies:
  - `alphabetic` / `dynamic` → `sorted(names)`
  - `random` → `rng.sample(list(names), len(names))` (one shared `random.Random`
    instance created per `structured_slugs_string()` call so INPUT and OUTPUT
    shuffles are both driven by the same seed, deterministically)
  - `domain` → group by a capability key derived from existing naming
    conventions already used elsewhere in this codebase (`slugs_synthesizer_helper.py`'s
    `activation_tag='_a'` / outcome-tag-from-first-letter convention, and
    `update_composite_props()`'s `prop.split(':')[0]` convention for indexed
    vars): strip a trailing `_a`/`_c`/`_f`/`_m` suffix, or take the part before
    `:` for composite/indexed vars; group by that key (sorted alphabetically),
    sort within each group alphabetically, concatenate. No new metadata plumbing
    needed — reuses conventions already in the codebase.
- Thread `variable_ordering_mode` / `variable_ordering_seed` through
  `structured_slugs_string()` → `write_structured_slugs_file()`, replacing the
  hardcoded `sorted(block)` in `__ordered_block_to_string`
  ([gr1_specification.py:554-583](../flexbe_synthesis_slugs/helpers/gr1_specification.py#L554-L583))
  with a call to the new ordering helper. Keep the existing `capability:` /
  comment-line special-casing for `[OUTPUT]` (still needed regardless of mode).
- Record the actual ordered `env_props`/`sys_props` lists produced (e.g.
  `self.last_variable_order = {'mode':..., 'seed':..., 'input_order': [...], 'output_order': [...]}`)
  so the caller can log them without recomputing.

### 2. `flexbe_synthesis_slugs/processes/slugs_spec_compiler.py`

- Add optional constructor fields `variable_ordering_mode: str = 'alphabetic'`,
  `variable_ordering_seed: int | None = None`; read from `inputs[2]`/`inputs[3]`
  in `main(inputs)` when present (mirrors the optional-trailing-arg pattern in
  `slugs_synthesizer.py`'s `main()`).
- Pass through to `gr1_spec.write_structured_slugs_file(...)`.
- After compiling, print the resolved mode/seed/order to stdout and write a
  sidecar `<spec_name>.variable_order.json` next to the `.slugsin` file (same
  `synthesis_byproducts` dir as the existing `.output`/`.json` artifacts)
  containing `{mode, seed, reordering_enabled, requested_input_order,
  requested_output_order}` — the *requested* pre-sifting order. Step 3 below
  fills in the actual post-sifting order once synthesis runs.

### 3. `flexbe_synthesis_slugs/helpers/slugs_synthesizer_helper.py`

- Add `reordering_enabled: bool = True` constructor param on
  `SlugsSynthesizerHelper`.
- In `call_slugs_synthesizer`, append `'--no-reorder'` to `options` when
  `not self.reordering_enabled`.
- **As implemented**, also add a `reordering_threshold: int | None = None`
  param; when set (and reordering enabled), append `'--reorder-threshold'` /
  `str(threshold)` to `options`.
- Add a small parser (e.g. `_parse_final_variable_order(slugs_output)`) that
  regex-matches the `"CUDD variable order (current level -> name [index]):"`
  block Slugs now writes to stderr (patch `3aee1ac`,
  `synthesisContextBasics.cpp:147-156`) and returns the ordered list of
  variable names by level. Call it after `determine_synthesizability`
  succeeds, and merge the result (`final_order`, plus the "CUDD dynamic
  reordering: enabled/disabled" line already reported) into the same
  `<spec_name>.variable_order.json` sidecar the compiler wrote (read-modify-write,
  since compile and synthesis are separate processes writing to the same file) —
  this is the true "actual final ordering used" deliverable, not just the request.

### 4. `flexbe_synthesis_slugs/processes/slugs_synthesizer.py`

- Add optional `reordering_enabled: bool = True` field; read from `inputs[3]`
  in `main(inputs)` (after existing optional `synthesis_timeout_s` at index 2),
  pass to `SlugsSynthesizerHelper`. **As implemented**, the process also
  accepts `reordering_threshold` as a trailing optional input (the batch
  harness passes it at `inputs[6]`).

### 5. Pipeline YAML wiring

- `flexbe_synthesis_examples/example/common/pipelines/capability_processes_def.yaml`
  and `capability_processes_def_parsed.yaml`: add `variable_ordering_mode: Str`,
  `variable_ordering_seed: Int` to `slugs_spec_compiler`'s `inputs`, and
  `reordering_enabled: bool` to `slugs_synthesizer`'s `inputs`.
- `full_spec_processes_def.yaml`: same additions to its `slugs_synthesizer` entry.
- `flexbe_synthesis_examples/example/coffee_maker/pipelines/processes_data.yaml`:
  add defaults alongside `synthesis_timeout_s` —
  `variable_ordering_mode: 'alphabetic'`, `variable_ordering_seed: 0`,
  `reordering_enabled: true` — so existing example runs are unaffected by default.

### 6. Tests

- `test/test_gr1_formula.py` or a new `test_variable_ordering.py`: unit-test
  `order_variables()` directly for all four modes (determinism of `random` given
  a fixed seed, grouping correctness for `domain`, unchanged behavior for
  `alphabetic`/`dynamic`).
- **New**: direct unit tests for `SlugsFairOutcomeLiveness` (`F`) and
  `SlugsSystemGoalLiveness` (`S` / **System-Goal Liveness** — renamed from
  "Adversarial-Liveness"; the code identifier now matches, see below)
  ([processes/slugs_fair_outcome_liveness.py](../flexbe_synthesis_slugs/processes/slugs_fair_outcome_liveness.py),
  [processes/slugs_system_goal_liveness.py](../flexbe_synthesis_slugs/processes/slugs_system_goal_liveness.py)) —
  currently **zero** test coverage on either, even though `capability_processes_def.yaml:53-54`
  hardcodes a choice between them (one `name:` active, the other commented
  out) with no test catching a regression in the untaken branch. Test each
  `.process()` directly against a small fixture `system_capabilities` dict
  (mirroring the `test_slugs_spec_compiler_main_binds_inputs` pattern — call
  `main(inputs)` then `.process()`, assert on the resulting `env_liveness`
  (`F`) / `sys_liveness` (`S`) clauses), plus a case for
  `SlugsSystemGoalLiveness`'s documented invariant that it requires exactly
  one prior `sys_liveness` goal
  ([slugs_system_goal_liveness.py:94-100](../flexbe_synthesis_slugs/processes/slugs_system_goal_liveness.py#L94)).
- **Done**: renamed `SlugsAdversarialLiveness` → `SlugsSystemGoalLiveness`
  (class, `slugs_adversarial_liveness.py` → `slugs_system_goal_liveness.py`,
  the YAML `name:`/console-script entry point in `setup.py`, both
  `capability_processes_def*.yaml` files, and `batch_run_harness.py`'s
  import) so code matches the paper's "System-Goal Liveness (S)"
  terminology instead of permanently diverging from it. The unit tests above
  are still outstanding — write them against the renamed identifiers.
- `test/test_slugs_processes.py`: extend the existing
  `test_slugs_spec_compiler_main_binds_inputs`-style tests
  ([test_slugs_processes.py:408-415](../test/test_slugs_processes.py#L408))
  with a case for the new optional trailing inputs, and mirror
  `test_slugs_synthesizer_process_accepts_optional_timeout`
  ([test_slugs_processes.py:1198-1221](../test/test_slugs_processes.py#L1198))
  for `reordering_enabled`.
- Regression-check: run the full existing test suite for
  `flexbe_synthesis_slugs` to confirm `alphabetic` (the default) reproduces
  byte-identical `.structuredslugs`/`.slugsin` output to today's `sorted()`
  behavior, preserving continuity with existing result tables.

## 7. Experiment setup (how the ordering-robustness study actually gets run)

> **Superseded by [batch_run_harness.md](batch_run_harness.md) (Issue 2).**
> That harness is the actual prerequisite this section was building toward —
> a generic `(example, encoding, liveness, pending, ...)` config-matrix runner
> that emits one raw row per trial (no in-harness aggregation). Once it
> exists, `ordering_mode`/`ordering_seed`/`reordering_enabled` are just three
> more config-matrix fields, and the `--tag` addition to `slugs_timing_stats.py`
> proposed below is unnecessary — this section is kept for the confound
> rationale and run-matrix reasoning, not as the literal implementation path.

**Third axis: liveness formulation.** `capability_processes_def.yaml` hardcodes
a choice between `slugs_system_goal_liveness` (`S` / System-Goal Liveness —
renamed from "Adversarial-Liveness"; `sys_liveness`, no environment fairness
assumed) and `slugs_fair_outcome_liveness` (`F`; `env_liveness`, assumes
the environment eventually reports completion) by which `name:` line is
commented out. This is the same class of confound as variable ordering — a
pipeline authoring choice that could be silently shaping the headline result —
so it belongs in the same sweep, not as a separate one-off toggle. Unlike
ordering mode, `liveness_mode` changes the **upstream** spec content (it's a
process that runs before compilation, not a serialization-order choice at
compile time), so it multiplies the whole matrix below rather than composing
with it for free: build two base `current_specification` dicts per
`(spec, encoding)` — one via `SlugsSystemGoalLiveness().process()`, one via
`SlugsFairOutcomeLiveness().process()` — then run the full ordering-mode ×
reordering sweep against each.

**Trial policy.** Every leaf configuration (a specific
`spec × encoding × liveness_mode × ordering_mode × reordering_enabled`, plus
`seed` for `random`) is run `N` times via `slugs_timing_stats.py -n N`, not
just once — even though sifting is deterministic for fixed input, this both
smooths wall-clock timing noise and guards against an unstated assumption
about determinism turning out to be wrong on a given machine/build. `-n`
already produces `_summarize_numeric`'s `n/mean/stdev/min/max` per field
([slugs_timing_stats.py:85-97](../flexbe_synthesis_slugs/helpers/slugs_timing_stats.py#L85)) —
no new statistics code needed, just wiring every leaf config through it with
a `--tag` set that includes `liveness_mode`. Default `N=5` per leaf config
(adjustable); for `random` ordering, each seed is its own leaf config with its
own `N=5` trials — seed-to-seed spread is the ordering-sensitivity signal,
trial-to-trial spread within one seed is the noise floor, and both are worth
reporting separately rather than conflating them.

Two existing tools already do most of what's needed, so this reuses them
rather than writing a new sweep orchestrator:

- `slugs_timing_stats.py` ([helpers/slugs_timing_stats.py](../flexbe_synthesis_slugs/helpers/slugs_timing_stats.py))
  already runs one `.slugsin` N times and forwards `--extra-arg` straight to
  the `slugs` binary — so `--extra-arg --no-reorder` already works today with
  **no pipeline change needed** for the reordering on/off toggle at the CLI level.
- `slugs_stats_helper.py` ([helpers/slugs_stats_helper.py](../flexbe_synthesis_slugs/helpers/slugs_stats_helper.py))
  already parses the CUDD stats block into `SlugsRunMetrics`, but its
  `_FIELD_PATTERNS` list ([slugs_stats_helper.py:142-184](../flexbe_synthesis_slugs/helpers/slugs_stats_helper.py#L142))
  doesn't yet know about the two lines the Slugs patches added: `"CUDD dynamic
  reordering: enabled/disabled"` and `"CUDD reorderings:"` /
  `"CUDD reordering time:"`. Add three fields — `cudd_reordering_enabled: bool`,
  `cudd_reorderings: int`, `cudd_reordering_time_s: float` — the same way the
  existing fields are declared.

Two small additions close the remaining gap:

- **Generating the `.slugsin` variants**: for each `(spec, encoding, mode,
  seed)` combination, call `GR1Specification.write_structured_slugs_file(...,
  variable_ordering_mode=mode, variable_ordering_seed=seed)` +
  `slugs_compiler.performConversion(...)` directly (the same two calls
  `SlugsSpecCompiler.process()` makes) in a short driver loop — bypassing the
  ROS action/pipeline-manager overhead is much faster for a sweep than
  launching the full FlexBE pipeline once per config.
- **Tagging runs so results merge cleanly**: add a repeatable `--tag
  key=value` option to `slugs_timing_stats.py` that gets stamped onto every
  row written by `--save-raw-metrics` (e.g. `--tag encoding=enumerated --tag
  mode=random --tag seed=7 --tag spec=coffee_maker --tag liveness=S`).
  That turns "run this tool once per leaf config" into a trivially mergeable
  set of JSON files — `pd.concat` or `jq -s` across all of them gives one long
  table (one row per trial, `n`/`mean`/`min`/`max` computable per tag-group
  afterwards), no bespoke aggregator needed.

**Recommended run matrix** per `(spec, encoding, liveness_mode)` triple — this
doubles everything below (×2 for `S`/`F`) but keeps the
per-liveness-mode sweep itself tractable, and each row runs `N=5` trials
(min/mean/max/stdev via `_summarize_numeric`) unless noted:

| ordering condition | leaf configs | purpose |
|---|---|---|
| `alphabetic`, reordering on | 1 (×5 trials) | today's baseline (reuse/continuity) |
| `alphabetic`, reordering **off** | 1 (×5 trials) | the naive floor — no optimization at all |
| `dynamic` | *(none — operationally identical to `alphabetic` on; the flag/log path is what's new, not the number)* | confirms reordering was explicitly on & logged |
| `random`, reordering on | 10-20 seeds (×5 trials each, fixed seed list reused across all specs/encodings/liveness modes) | sensitivity to initial order under always-on sifting — report as mean ± range across seeds, plus within-seed min/max as the noise floor |
| `domain`, reordering on | 1 (×5 trials) | does hand-tuned grouping beat/match alphabetic |

For N benchmark specs × 2 encodings × 2 liveness modes × (~13 leaf configs
with 10 seeds) × 5 trials, that's on the order of `13 × 2 × 2 × 5 × N` Slugs
invocations — still cheap enough to run directly (seconds-to-low-minutes per
invocation on the existing benchmark sizes).

**The actual comparison for the paper**: for each `(spec, encoding)`, compute
Δ = cost(enumerated) − cost(one-hot) under each condition above, separately for
each `liveness_mode`. If Δ's sign and rough magnitude hold across `alphabetic`
on/off, `domain`, the `random` seed distribution, **and** both liveness
formulations, that's the evidence that the encoding penalty is intrinsic
rather than an artifact of naive alphabetic ordering or of one particular
liveness-formulation choice — which is exactly the confound Issue 3 was
opened to close.

## Verification

- `python -m pytest flexbe_synthesis_slugs/test/test_gr1_formula.py flexbe_synthesis_slugs/test/test_slugs_processes.py -q`
  (or the project's usual `colcon test` invocation if that's the norm).
- Manually compile one example spec (e.g. coffee_maker) through
  `SlugsSpecCompiler` with each of the four modes and confirm
  `<spec_name>.variable_order.json` is produced with distinct, sensible
  `requested_input_order`/`requested_output_order` per mode, and that
  `alphabetic` matches the pre-change `.slugsin` output exactly (diff against
  a checked-out pre-change copy).
- Run the full pipeline (compiler + synthesizer) once with
  `reordering_enabled: false` and once with `true`, against a rebuilt `slugs`
  binary (post `3aee1ac`), and confirm: `--no-reorder` appears in the logged
  command line for the `false` case; the sidecar JSON's `final_order` matches
  `requested_input_order + requested_output_order` exactly when reordering is
  off (sanity check — no sifting means final == requested); and `final_order`
  differs from the requested order when reordering is on (sifting did
  something).
