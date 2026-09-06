# Issue 6: Clause/constraint ordering sanity check

Type: experiment (small). No dependencies. **Scope is deliberately capped —
this is a footnote, not a subsection.**

## Context

Checks whether the *textual* clause order inside the generated `.slugsin`
body (the order `ENV_TRANS`/`SYS_TRANS`/`ENV_LIVENESS`/`SYS_LIVENESS` lines
appear in) is itself confounding results — distinct from Issue 3's *BDD
variable* ordering, which is about the
`[INPUT]`/`[OUTPUT]` declaration order, not the clause bodies.

## Tasks

1. Shuffle the textual clause order within each block (`__block_to_string` in
   `gr1_specification.py` — currently emits clauses in insertion order, not
   sorted) a handful of times per example (e.g. 3-5 shuffles, one example or
   two, not the full benchmark suite).
2. Confirm synthesis cost (peak BDD nodes) is stable across shuffles.
3. If stable: add one sentence to the paper attributing observed effects to
   BDD variable ordering, not clause ordering. If *not* stable, that's a
   separate, more serious finding worth its own discussion — but don't expand
   this issue's scope preemptively on the assumption it won't be stable.

## Verification

- A handful of shuffled-clause-order `.slugsin` runs against one example,
  peak-BDD-node values compared — that's the entire deliverable. No table, no
  distribution plot, no new harness config-matrix axis.
