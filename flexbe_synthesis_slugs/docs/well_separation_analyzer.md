# Well-Separation Analyzer

This document describes the `slugs_well_separation_analyzer` process plugin in
[`processes/slugs_well_separation_analyzer.py`](../flexbe_synthesis_slugs/processes/slugs_well_separation_analyzer.py).

## What it checks

Well-separation is a **specification-level** property, distinct from ordinary
GR(1) realizability and from the post-synthesis
[Strategy Auditor](auditor.md). Informally, it asks whether the system can
force the environment to violate its own assumptions — see Maoz & Ringert,
"On Well-Separation of GR(1) Specifications," ESEC/FSE 2016
(doi:10.1145/2950290.2950300).

The analyzer runs after `slugs_spec_compiler` and before `slugs_synthesizer`,
so it checks exactly the compiled `.slugsin` artifact that synthesis will
consume. A non-well-separated result does not by itself mean the
specification is unrealizable, and it is not a substitute for the
post-synthesis auditor, which checks a different property (activation/outcome
protocol conformance and goal-unreachable traps) on the *extracted strategy*
rather than the specification.

## Slugs binary requirement

The analyzer expects the CNU Slugs fork's `flexbe-synthesis` branch to provide
the `--checkWellSeparation` analysis mode. Once the pending Slugs changes are
merged into that branch, the normal [`install_slugs.sh`](../scripts/install_slugs.sh)
workflow installs a binary that supports this stage.

The wrapper invokes Slugs as a separate subprocess with:

```bash
slugs --checkWellSeparation --jsonOutput SPEC.slugsin SPEC.well_separation.json
```

and adds `--minimizeWellSeparationCore` when
`minimize_well_separation_core: true`.

The shipped example pipelines (`processes_data.yaml` for `coffee_maker` and
`vending_demo`) set `fail_on_incomplete: true`. With the expected Slugs binary,
this means timeouts, subprocess failures, or malformed analyzer JSON are
treated as setup/tool failures and stop the pipeline before synthesis. A
definitive `NON_WELL_SEPARATED` result is a normal analysis outcome and is
controlled separately by `fail_on_non_well_separated`.

## Configuration

Set these under `/data` in a pipeline data file, matching the pattern used by
`strategy_auditor_timeout_s` and friends:

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `well_separation_timeout_s` | float | `DEFAULT_SLUGS_TIMEOUT_S` | Wall-clock timeout for the Slugs subprocess. |
| `fail_on_non_well_separated` | bool | `false` | If `true`, a `NON_WELL_SEPARATED` result is a fatal pipeline error instead of a warning. |
| `fail_on_incomplete` | bool | `true` | If `true`, `ANALYSIS_INCOMPLETE`/`ANALYSIS_ERROR` (timeout, missing binary, unparseable output, subprocess failure) is a fatal pipeline error. |
| `minimize_well_separation_core` (`minimize_core` on the class) | bool | `false` | Adds `--minimizeWellSeparationCore`, which performs additional greedy fixed-point checks and can be significantly slower. |

The process returns `[well_separation_result: dict, error_code: SynthesisErrorCode]`.
`well_separation_result['status']` is one of `WELL_SEPARATED`,
`NON_WELL_SEPARATED`, `ANALYSIS_INCOMPLETE`, or `ANALYSIS_ERROR`. An
incomplete or errored analysis is always reported as such — never silently
treated as a pass — regardless of the `fail_on_*` policy, which only controls
whether the pipeline halts.

Like other process outputs, `well_separation_result` is saved to
`processor_outputs/*.yaml` by the standard pipeline output-saving mechanism.
It is not currently read by any downstream process or by the benchmark/paper
table scripts.
