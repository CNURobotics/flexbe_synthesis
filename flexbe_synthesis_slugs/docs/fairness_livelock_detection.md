# Game/Fairness-Aware Livelock Detection (design, not yet implemented)

Design for closing the gap Corollary 1 in `Auditor.tex` already names: the
current `GOAL_UNREACHABLE_TRAP` check (`StrategyAuditor._check_goal_unreachable_traps` in
`flexbe_synthesis_slugs/helpers/strategy_auditor.py:510`) proves a *structural*
property (does a reachable cyclic SCC have **a path** to a cyclic
goal-containing component in the condensed DAG), not that execution is ever
actually **forced** onto that path. This doc specifies the analysis needed to
close that gap, why it needs a formula evaluator and a fairness-aware
fixpoint (not just more graph traversal), and why that combination should be
its own scoped implementation effort rather than an add-on to this session's
other fixes.

## Why the structural check can't be tightened further

Every non-trivial SCC produced by Tarjan's algorithm (`tarjan_scc` in
`flexbe_synthesis_core/graph_utils.py:19`) is, by construction, strongly
connected using *only* edges internal to that component — if reaching between
two members required leaving to a different component and coming back, that
component would already have been merged into one SCC by the algorithm. So
for **any** cyclic SCC that currently passes `_check_goal_unreachable_traps` (i.e. has
an edge out to a component that can reach a cyclic goal-containing component),
there is, structurally, also always an infinite path that stays inside the SCC
and never takes that exit — looping the SCC's own internal cycle forever is
always available. This isn't a rare edge case; it's true of essentially any
SCC with more than one viable successor at some node, which is common for any
strategy with a retry or "try alternative" branch.

This has a direct consequence for scoping the fix: a purely structural check
("does this SCC also contain an internal-only cycle that avoids the exit
edge(s)?") would fire on nearly every SCC with a side exit, structurally
provable as shown above, giving it no discriminating power. Whether the
avoidance is actually *exploitable* depends entirely on whether the
environment's GR(1) fairness assumptions (`env_liveness`) force it to
eventually take the exit — information the current auditor never evaluates.
Any useful version of this check has to incorporate `env_liveness`.

## What "incorporate env_liveness" requires

### 1. A GR(1) formula evaluator (does not exist yet)

`SPEC_EVAL_ERROR` is already reserved as a failure kind in
`strategy_auditor.py:36` for exactly this — symbolic formula evaluation — but
nothing evaluates formulas today. `helpers/gr1_formula.py` only *constructs*
and manipulates formula strings (`get_vars_from_eqn`, `split_top_level`,
`extract_leaf_expressions`, etc.); there is no function that takes a formula
string and a variable assignment and returns a boolean.

Checked the actual generated clauses to ground the required grammar (via
`SlugsFairOutcomeLiveness.process()` in
`processes/slugs_fair_outcome_liveness.py:77`):

```python
env_liveness.append(LTL.disj([LTL.neg(prop), LTL.next(f'{cap_name}_c')]))
```

producing clauses shaped like `!cap_a | next(cap_c)`. **This is the key
complication**: real `env_liveness` clauses reference **next-state**
(primed / `next(...)`) propositions, not just current-state ones. A formula
like this cannot be evaluated against a single product-graph node — it has to
be evaluated against a **transition** (a `(source, target)` edge), using
`source`'s current-state values for unprimed terms and `target`'s values for
`next(...)` terms. This changes the shape of the whole downstream algorithm
from "which nodes satisfy formula `i`" to "which edges satisfy formula `i`."

Grammar the evaluator needs to support, based on what's actually generated
today (`helpers/ltl.py`, `slugs_capability_specification.py`,
`slugs_activation_specification_parsed.py`):

- Bare boolean propositions (`cap_a`, `completed`, `finished`, ...).
- `next(term)` / primed terms (`term'`) for next-state reference.
- `!`, `&`, `|` (already used throughout the generators).
- `->` (appears in `env_trans`/`sys_trans`; less common in `env_liveness`
  but should be supported for robustness rather than assumed absent).
- Indexed-variable comparisons `var=N` / `var!=N`, needed for the
  parsed/enumerated encoding's `capability=i` style terms
  (`slugs_activation_specification_parsed.py`).
- Parenthesized grouping.

A node's/edge's assignment can be built the same way
`_observed_outcomes`/`_activated_capabilities` already do (reading
`state.input_values`/`state.output_values` off the underlying
`SlugsAutomatonState`), so the evaluator itself is the only missing piece —
the state-assignment plumbing already exists.

### 2. An edge-accepting generalized-Büchi emptiness check

Given an evaluator, the question for one currently-passing cyclic SCC
becomes: restricted to the SCC's own induced subgraph, does there exist an
infinite path (using only edges internal to the SCC) along which **every** one of the
`k` `env_liveness` clauses is satisfied infinitely often? If yes, a
fairness-compliant environment can stay in the SCC forever without ever being
forced to take the exit — a genuine livelock the current check misses. If no
such path exists, every infinite internal-only path eventually violates some
fairness clause, so a fairness-compliant environment cannot avoid the exit
forever, and the SCC is not exploitable this way.

This is exactly the classical generalized-Büchi automaton emptiness problem
(Courcoubetis, Vardi, Wolper & Yannakakis, "Memory-efficient algorithms for
the verification of temporal properties," 1992 — already cited in the paper's
bibliography as `Courcoubetis1992` for the SCC/model-checking framing, so this
extends rather than introduces a citation). Standard algorithm, adapted to
edge-acceptance instead of the usual node-acceptance:

1. `current = ` the SCC's node set, with only SCC-internal edges.
2. For each of the `k` `env_liveness` clauses in turn: recompute SCCs of
   `current`; keep only nodes belonging to a non-trivial component that
   contains at least one edge satisfying this clause (evaluated via the
   formula evaluator above); drop everything else; if `current` becomes
   empty, stop — no fair cycle exists.
3. Repeat step 2 until either `current` is empty (not exploitable — safe) or a
   full pass over all `k` clauses completes with no further shrinkage
   (fixpoint — a genuine fair cycle exists, i.e. exploitable).

Complexity: `O(k * (n + m))` per SCC via `k` rounds of SCC recomputation,
same order of cost as the existing `GOAL_UNREACHABLE_TRAP` check's single SCC pass,
just multiplied by the number of `env_liveness` clauses.

## Why this needs to be its own effort, not folded into this session

- No formula evaluator exists; building one that's actually correct for the
  real grammar above (especially `next()`/priming, which most naive
  "evaluate a boolean expression" approaches don't handle by default) needs
  dedicated unit tests against the real clause shapes shown above, not just
  synthetic examples.
- A bug in a *new* check that can flag `valid: False` is a much worse failure
  mode than a missed detection: it would spuriously fail currently-passing
  real strategies (the coffee pipeline, the paper's already-reported results)
  until caught. That risk profile is different from this session's other
  three fixes, all of which were verified end-to-end against the real
  pipeline before being trusted.
- Scope is genuinely larger than "add a check": new evaluator module, new
  edge-accepting SCC algorithm, new failure kind (or a non-blocking warning
  field, to be decided), new `AuditorConfig` fields to carry `env_liveness`
  through to this check, updated `docs/auditor.md` and `Auditor.tex`
  (Corollary 1's gap becomes partially closed, not fully — see below), and a
  real test suite exercising primed/next() clauses specifically.

## Suggested implementation shape (for the future session that picks this up)

- New failure kind: this should almost certainly land as a **non-blocking
  warning** first (e.g. `unfair_livelock_states` alongside the existing
  `bad_scc_states`, without setting `valid: False`), not a hard failure —
  until it has the same level of real-pipeline validation as the other
  checks, a false positive here is worse than a missed detection.
- Only evaluate this for SCCs that already **pass** `_check_goal_unreachable_traps`
  (i.e. `comp_index in can_reach_goal` at `strategy_auditor.py:560`) — SCCs
  that already fail don't need this refinement.
- Thread `env_liveness` from `slugs_specification` into `AuditorConfig`
  (`derive_config` in `strategy_auditor.py:126` already receives
  `slugs_specification`; it just doesn't extract `env_liveness` today).
- Cite `Courcoubetis1992` (already in `main.bib`) for the algorithm; update
  `Auditor.tex`'s Corollary 1 discussion once implemented, since it currently
  states this class of livelock is fully out of scope for the check.

## Status

Not started. Recorded here as a scoped, implementation-ready design per an
explicit decision to write this up rather than implement it in the same
session as three other, lower-risk fixes (protocol-violation false positive,
`SlugsSystemGoalLiveness` rename, `AUDIT_INCOMPLETE` status).
