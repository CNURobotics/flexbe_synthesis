# Strategy Auditor

This document describes the `strategy_auditor` process plugin and the
explicit-state validation algorithm implemented in
[`helpers/strategy_auditor.py`](../flexbe_synthesis_slugs/helpers/strategy_auditor.py).

The auditor is a post-synthesis checker for Slugs-generated Mealy strategies.
It is intended to catch semantic progress errors that can survive ordinary
syntactic specification compilation and successful GR(1) synthesis.

It is not a symbolic GR(1) model checker.  It validates the explicit strategy
automaton that Slugs produced, using the same `Automaton` dictionary structure
already passed through the FlexBE synthesis pipeline.

## Graph Terms

A **directed graph** is a set of nodes with one-way edges between them.  In the
auditor, each node is a product state and each edge is one possible strategy
transition plus monitor update.

A **path** is a sequence of nodes connected by directed edges.  A node `b` is
**reachable** from node `a` if there is some directed path from `a` to `b`.

A **cycle** is a non-empty path that returns to a node already on the path.  In
a finite graph, every infinite execution eventually repeats a node, and once it
does, the repeated portion contains a cycle.  This is the key reason cycle
analysis is enough to reason about livelock in an explicit finite strategy.

A **strongly connected component**, or **SCC**, is a maximal set of nodes where
every node in the set can reach every other node in the set.  "Maximal" means
the set cannot be made larger without losing that mutual-reachability property.

Example:

```text
A -> B -> C -> B
```

`{B, C}` is an SCC because `B` reaches `C` and `C` reaches `B`.  `{A}` is its
own SCC because no later node reaches back to `A`.

The **condensed graph** is built by collapsing each SCC into a single node.
Edges between original SCCs become edges between condensed nodes.  The
condensed graph is always acyclic: if two condensed nodes could reach each
other, they would have been one larger SCC.

The auditor uses Tarjan's algorithm to compute SCCs.

Tarjan's algorithm is a linear-time depth-first graph algorithm: it visits each
node and edge once, assigns discovery indices, and uses low-link values to
identify exactly when a complete SCC has been found
([Tarjan 1972](https://doi.org/10.1137/0201010)).  The implementation in
`flexbe_synthesis_core.graph_utils.tarjan_scc()` is iterative rather than
recursive so it does not hit Python's recursion limit on large strategy graphs.

## Pipeline Position

The plugin is registered as:

```text
strategy_auditor = flexbe_synthesis_slugs.processes.strategy_auditor:main
```

The example Slugs pipelines run it twice:

1. Immediately after `slugs_synthesizer`, on the original synthesized strategy.
2. Immediately after `slugs_sm_reducer`, on the reduced automaton.

This lets the pipeline check the solver output before reduction and then check
that the reduced graph still preserves the semantic progress properties needed
by downstream state-machine generation.

The two audits do not enable exactly the same checks.  The raw synthesized
strategy still gets the full activation/outcome protocol monitor, including
`PROTOCOL_VIOLATION` and bounded-failure checks when the spec shape supports
them. Reduced automata are marked with
`reduced_automaton: true`; for those, strict protocol enforcement is skipped
because the reducer may merge multiple source states and union their input
labels for downstream state-machine generation. Treating those merged labels as
concrete per-edge observations can create false protocol failures.
The reduced audit therefore remains a structural/progress audit: it still checks
graph validity, deadlocks, goal reachability, and goal-unreachable cyclic traps,
but it does not reinterpret merged input labels as one-step capability outcomes.

## Inputs

The plugin uses a fixed nine-argument process signature:

| Input | Purpose |
|---|---|
| `automaton` | Original or reduced `Automaton` dictionary. |
| `specs_output_dir_path` | Per-request synthesis output directory. |
| `spec_name` | Original synthesis spec name. Used to locate the compiled `.slugsin`. |
| `system_capabilities` | Capability names, outcome metadata, and SM outcome mappings. |
| `state_mappings` | Transition outcome names and SM outcome fallback mappings. |
| `slugs_specification` | Pipeline GR(1) specification payload, used to supplement simple liveness goals. |
| `strategy_auditor_spec_path` | Optional explicit compiled spec path. Empty string means use the generated `.slugsin`. |
| `strategy_auditor_goal_outcomes` | Optional goal outcome override. Empty list means derive from pipeline data. |
| `strategy_auditor_timeout_s` | Wall-clock budget for validation. |

If `strategy_auditor_spec_path` is empty, the auditor reads:

```text
<specs_output_dir_path>/synthesis_byproducts/<spec_name>.slugsin
```

The compiled `.slugsin` is used as the authoritative variable universe for this
release because it matches the numeric-variable expansion and naming that Slugs
actually synthesized against.  Future work may add a structured-to-compiled
source map so diagnostics can point back to `.structuredslugs` formulas.

## Result

The plugin returns:

```text
strategy_auditor_result: dict
error_code: SynthesisErrorCode
```

The result dictionary has stable keys:

| Key | Meaning |
|---|---|
| `valid` | `True` if no confirmed semantic failure was found. **Not** a claim of correctness when `incomplete` is also `True` — see below. |
| `incomplete` | `True` when timeout stopped analysis before it could confirm or rule out a failure. An incomplete audit is neither a pass nor a fail; it's unknown. Callers must check this flag explicitly rather than treat `valid`/the returned error code alone as an assurance. |
| `failure_kinds` | List of failure kinds found in this run. The current implementation reports the first confirmed failure. |
| `failure_kind` | Convenience copy of the primary failure kind, or `None`. |
| `message` | Human-readable summary. |
| `counterexample_trace` | Product-state trace explaining the failure when available. |
| `bad_scc_states` | Strategy state names in a goal-unreachable trap when one is found (reported as `GOAL_UNREACHABLE_TRAP`; see "Goal-Unreachable Trap Detection" below for why this is narrower than "livelock" in general). |
| `warnings` | Non-fatal derivation, parsing, or timeout warnings. |

Confirmed semantic failures return
`SynthesisErrorCode.AUTOMATON_INVALID`, which halts later pipeline stages.
Timeouts return `SynthesisErrorCode.AUDIT_INCOMPLETE` with `valid: True`,
`incomplete: True`, and a warning — a distinct status from
`SynthesisErrorCode.SUCCESS`, so callers checking the error code alone (not
just the `incomplete` flag) can tell "audit passed" from "audit didn't
finish." The pipeline manager treats `AUDIT_INCOMPLETE` as non-fatal: it
does not abort like other non-`SUCCESS` codes, and later stages keep
running. Because a later stage's own `SUCCESS` would otherwise silently
overwrite the in-flight error code, the manager separately tracks the first
non-fatal code seen (`self._degraded_error_code` in `synthesis_manager.py`)
and reports it as the request's final `error_code` instead of `SUCCESS`, so
an incomplete audit is still visible in the top-level result even though the
controller was generated. This is a default policy choice (unverified
audits are non-blocking, matching the pre-existing behavior before this
status existed), not an inherent property of the code — a future revision
could add a stricter opt-in mode for hardware deployments that should treat
an incomplete audit as fatal.

## Failure Kinds

Known failure kinds are:

| Kind | Meaning |
|---|---|
| `PARSE_ERROR` | The automaton or compiled spec could not be normalized. |
| `DEADLOCK` | A reachable strategy state has no outgoing transition. |
| `PROTOCOL_VIOLATION` | Activation/outcome timing or exclusivity is violated. |
| `INVALID_TRANSITION` | A strategy transition references a missing state. |
| `GOAL_UNREACHABLE` | No configured goal outcome is reachable. |
| `GOAL_UNREACHABLE_TRAP` | A *goal-unreachable trap*: a reachable cyclic SCC that cannot reach any *cyclic* goal-containing SCC (see "Goal Outcomes" below for why this must be cyclic). See "Goal-Unreachable Trap Detection" for why this is narrower than "livelock" in the general sense. |
| `BOUNDED_FAILURE_VIOLATION` | A capability exceeds its configured consecutive failure limit. |
| `SPEC_EVAL_ERROR` | Reserved for future formula-evaluation failures. |

`UNDECLARED_OUTCOME` remains defined as a compatibility constant for older
diagnostics, but the current checker reports wrong-capability outcomes as
`PROTOCOL_VIOLATION`.

## Semantic Model

The auditor treats the Slugs strategy as an explicit directed graph. Each
strategy state carries two labels: `in(s)`, the environment-input valuation
observed on arrival at `s`, and `out(s)`, the system-output valuation
asserted at `s`. Labels live on **states, not edges** — the Slugs explicit
strategy already guarantees that a distinct input/output valuation is always
represented as a distinct state, so per-state labels are sufficient; there's
no need for a separate edge-label alphabet. "Capability `cap` is activated
at `s`" means `cap_a ∈ out(s)`; "an outcome of `cap` is observed on arrival
at `s`" means `in(s)` contains one of `cap`'s declared outcome tokens.

This concrete state-label interpretation applies to raw synthesized strategies.
For reduced automata, labels may be quotient metadata inherited from several
merged raw states.  The auditor detects this with the `reduced_automaton` marker
emitted by `slugs_sm_reducer` and disables strict protocol monitoring for that
second audit.

The monitor adds semantic state to the graph:

```text
strategy state
  x pending capability
  x consecutive failure counters
```

The pending capability records a capability activated in the previous step.
Failure counters record consecutive failed attempts per capability, not raw
state visits.

### Capability Protocol

For a capability `cap`, default variable names are:

```text
activate: cap_a
complete: cap_c
fail:     cap_f
```

Declared outcomes are derived from `system_capabilities` when available.  If a
capability does not carry explicit outcome metadata, the auditor falls back to
the configured `transition_outcomes` list, such as `completed` and `failure`.

The protocol is:

1. If `cap_a` is asserted at step `k`, then a declared outcome for `cap` must
   be observed at step `k + 1`.
2. Multiple declared outcomes for the pending capability at the same successor
   state are invalid.
3. Outcomes observed with no pending capability are invalid, with one
   exception: for parsed/enumerated specs, the generic outcome props
   (`completed`/`failure`) are only constrained relative to the *current*
   real capability (`(capability=i) -> completed'` for `i >= 1`), so they are
   free on the transition leaving the null start state (`capability=0`,
   which is the only state where nothing can be pending, since the spec
   always forces the action variable non-zero afterward). Slugs may legally
   branch on that unconstrained value before any real capability has ever
   run; the branch is behaviorally inert, so the auditor does not flag it.
4. Outcomes observed for a different capability than the pending one are invalid.
   Terminal state-machine outcomes such as `finished` or `failed` are goal
   labels, not capability outcome tokens, and do not exempt a strict raw audit
   from this rule.
5. Multiple simultaneous activations are invalid for this single-pending
   monitor.

This matches the one-attempt-at-a-time abstraction used by the generated
capability specifications.  A future extension could replace the pending
capability field with a pending set if concurrent independent capabilities need
full semantic auditing.

### Goal Outcomes

Ultimate goals are top-level state-machine outcomes.  By default they are
derived from `system_capabilities['sm_outcome_mappings']`, falling back to
`state_mappings['sm_outcome_mappings']`.  The plugin also adds simple
`sys_liveness` entries from `slugs_specification` when a liveness formula is
exactly a system proposition.

`strategy_auditor_goal_outcomes` can override the derived goal set. This
matters for more than just supplying a goal when there's no SM outcome
(Coffee, below): the goal set `G` is a **configuration choice** with two
different meanings depending on what it contains, and the auditor makes no
assumption about which one is intended:

- **Termination audit**: `G` includes both `finished` and `failed` — "does
  the strategy always eventually reach *some* terminal state." A terminal
  failure counts as satisfying `G`.
- **Task-completion audit**: `G` includes only the success outcome(s) —
  "does the strategy always eventually reach *successful* completion." A
  terminal failure does **not** vacuously satisfy this `G`.

For a strategy with no terminal SM outcome at all (e.g. Coffee, which is
designed to loop forever), override with an environment-reported completion
input such as `br_c` instead — this is the "recurrence" goal case discussed
next, and it's orthogonal to the termination/task-completion distinction: the
override can be either kind, the auditor treats it uniformly either way.

**Two different kinds of goal, one check.** A *terminal* goal (a system
output with a persistence guarantee like `finished -> finished'` in
`SYS_TRANS`) is absorbing: any state asserting it has an outgoing edge that
keeps asserting it, so its component is cyclic automatically, and "the goal
is reachable" and "the goal recurs" coincide. A *recurrence* goal (an
environment-reported input with no such system-side guarantee, used when
there's no terminal outcome) has no such guarantee — a goal node reached
inside a non-cyclic component is visited at most once, which does not
certify recurrence. `_is_goal_state()` checks both output and input
propositions (matching either kind) without knowing which one it's looking
at, and `_check_goal_unreachable_traps()` seeds backward reachability only from
*cyclic* goal-containing components, which is the correct requirement for
recurrence goals and a no-op restriction for terminal ones (since their goal
components are already always cyclic). See "Goal-Unreachable Trap Detection" below.

### Bounded Failures

If a capability contains either:

```text
max_consecutive_failures
```

or:

```text
bounded_failure_limit
```

the auditor enforces a **pending-episode failure bound**: `k_cap` counts
failure outcomes observed within `cap`'s current unbroken streak of
immediate re-activation, and resets to `0` whenever that streak breaks —
`cap` succeeding, `cap` failing but a *different* capability becoming
pending next instead of `cap` being retried, or nothing being pending at
all. This is deliberately not either of the two simpler readings that don't
match what a retry bound should mean once other capabilities can interleave:
not "failures since `cap`'s last success regardless of what else ran in
between" (the previous, buggy behavior — see below), and not a
literal-adjacent-steps notion of "consecutive" either, since this protocol
never leaves a capability mid-flight (every activation fully resolves,
success or failure, at the very next step) — there's no partial "episode" to
interrupt other than by activating something else instead of retrying.

**Fix note:** an earlier version of `_advance_counters()` only ever updated
the *pending* capability's own counter, leaving every other capability's
counter untouched across its own activations. That meant `π` failing, `ρ`
running to completion, then `π` failing again counted as **2** consecutive
failures of `π`, even though the two failures were separated by an entirely
unrelated capability's episode. The fix computes `next_pending` before
updating counters and, on every step, resets every capability other than
`next_pending` to `0` — only the capability about to be immediately
re-pending can carry a nonzero count forward.
`test_strategy_auditor_resets_failure_streak_on_interrupting_capability` in
`test/test_strategy_auditor.py` pins this: `step` fails, `other` is
activated and succeeds, `step` fails again — with `max_consecutive_failures
= 1` this must pass, not trip a violation, since the two `step` failures are
not consecutive.

No bound is enforced when neither key is present.

## Algorithm

The audit has five phases.

### Why SCCs Drive Goal-Unreachable Trap Detection

The semantic question behind this check is:

```text
Is there a reachable region from which the goal can never be reached again?
```

This is deliberately narrower than "can the strategy continue forever
without ever reaching an ultimate goal" — see "Goal-Unreachable Trap
Detection" below for exactly where those two questions diverge and why the
narrower one is still the right thing to check by graph reachability alone.

Because the product graph is finite, any infinite non-goal execution must
eventually stay inside some cyclic SCC.  If that SCC has no path to a
*cyclic* goal-containing SCC, then the strategy can keep cycling forever and
the goal is permanently unreachable from there.  That is a goal-unreachable
trap.  The cyclic requirement on the goal side matters for recurrence-type
goals (see "Goal Outcomes" above): reaching a goal node that is itself only
ever visited once does not mean the goal recurs, so it must not clear an
otherwise-bad SCC.

If a cyclic SCC can reach a cyclic goal-containing SCC, the auditor does not
classify the SCC as a trap.  The explicit graph still contains a way to
leave the cycle and make progress.  This choice matches the auditor's
purpose: it detects reachable closed progress traps in the explicit
strategy, not every transient retry loop that still has an escape edge —
even one the environment might never actually be forced to take.

So the algorithm is:

1. Compute SCCs of the reachable product graph.
2. Collapse them into the condensed SCC graph.
3. Mark every *cyclic* SCC that contains a goal.
4. Walk backward through the condensed graph to mark every SCC that can reach
   one of the SCCs marked in step 3.
5. Any reachable cyclic SCC not marked in step 4 is a goal-unreachable trap,
   reported as `GOAL_UNREACHABLE_TRAP`.

### 1. Parse Inputs

The auditor scans the compiled `.slugsin` file into sections and warns if
basic `[INPUT]` or `[OUTPUT]` declarations are missing.  It does not attempt a
full symbolic parse of GR(1) formulas.

The automaton dictionary is normalized with `SlugsAutomaton.from_dict()`.
This rekeys states and rebuilds incoming-edge lists.  Missing transition targets
are reported as `INVALID_TRANSITION`.

### 2. Derive Semantic Configuration

Capability names, declared outcomes, goal outcomes, transition outcomes, and
bounded-failure limits are derived from existing pipeline payloads.  There is
no separate semantic YAML file in this release.

### 3. Build the Reachable Product Graph

The auditor starts from explicit `is_initial` states.  If no explicit initial
state is tagged, it follows the existing automaton convention and uses the
first root state with no incoming edges, or the first automaton state as a last
fallback.

For each product node, it explores each strategy transition and applies the
capability monitor and bounded-failure monitor to compute successor product
nodes.  Any protocol, deadlock, invalid-transition, or bounded-failure failure
returns immediately with a counterexample trace.

### 4. Check Goal Reachability

If goal outcomes are configured, at least one reachable product node must assert
a goal label. Otherwise the audit fails with `GOAL_UNREACHABLE`.

### 5. Check for Goal-Unreachable Traps

The auditor computes strongly connected components using the shared iterative
Tarjan helper in `flexbe_synthesis_core.graph_utils`.

A cyclic SCC is a goal-unreachable trap only if it cannot reach any *cyclic*
SCC containing a goal node.  The checker therefore builds the condensed SCC
graph, walks backward from cyclic goal-containing SCCs only, and marks every
SCC that can transitively reach one.  A reachable cyclic SCC not in that set
fails with `GOAL_UNREACHABLE_TRAP`.

## Proof Sketch

The following arguments assume that the input `Automaton` faithfully represents
the explicit Slugs strategy and that the derived capability metadata correctly
names activation and outcome propositions.

### Product Graph Soundness

Each product node is a tuple:

```text
(strategy_state, pending_capability, failure_counters)
```

The initial products pair each initial strategy state with the activation
asserted by that state, if any, and zero failure counters.  For every outgoing
strategy edge whose target activates at most one capability, the transition
relation computes exactly the semantic monitor state after one strategy step:

- the target state's input labels determine the observed outcome for the
  previous pending capability,
- the target state's output labels determine the next pending capability,
- success outcomes reset that capability's failure counter,
- finite-bound failure outcomes increment it only when the same capability is
  immediately retried,
- unbounded failure outcomes do not change product-state identity,
- all counters other than the capability immediately becoming pending reset to
  zero.

Because the monitor update at each step is a deterministic function of the
previous monitor state and the labels observed at that step, every strategy
execution prefix whose successor states activate at most one capability lifts
to exactly one product path `(s0,p0,0) -> ... -> (s,p,k)` — the lift is a
function of the prefix, by induction on prefix length. Edges whose target
activates multiple capabilities are checked as protocol violations before a
product successor is constructed. Similarly, if a finite failure counter would
exceed its configured bound, the auditor reports `BOUNDED_FAILURE_VIOLATION`
instead of treating that beyond-bound value as another valid product state.
The converse can still be many-to-one: distinct prefixes can land on the same
product node whenever they have the same strategy state, pending capability,
and in-bound counter values. That's fine — the argument below only needs every
product path to correspond to some real, monitor-consistent strategy prefix
(which it does, by the same induction run forward instead of backward), not
that the correspondence is one-to-one in the other direction.

### Safety Checks

Deadlock, protocol, invalid-transition, and bounded-failure checks are safety
properties: a finite bad prefix is enough to witness each violation.

During product expansion the auditor examines every strategy edge out of every
reachable product node as a candidate audited edge. If a bad prefix exists, let
`e` be the first edge where the property is violated. All earlier edges are
valid, so the source of `e` is reachable in the product graph. The expansion of
that source examines `e` and reports the violation, either directly for
multi-activation or after constructing the unique monitor successor for the
remaining local checks. Therefore the algorithm is complete for these
finite-prefix violations.

Conversely, each reported safety violation is produced only from a reachable
product node and a candidate strategy edge, or from a reachable deadlock node,
and is checked directly against the corresponding semantic rule. Therefore each
reported counterexample is sound.

### Goal Reachability

The product graph contains exactly the monitor-valid reachable strategy
prefixes. A goal is reachable iff some reachable product node's strategy state
asserts a configured goal label, either as a system output or as an
environment-input observation. The auditor records exactly those product nodes
during BFS. Therefore `GOAL_UNREACHABLE` is reported iff no monitor-valid
reachable strategy execution reaches a configured goal label.

### Goal-Unreachable Trap Detection

**Note (corrected):** an earlier version of this proof sketch called this
property "livelock" and defined it as "some infinite execution eventually
avoids goals." It argued the forward direction by asserting that the SCC
such an execution settles into can't reach a goal "otherwise the execution
could have followed that path."  That
does not follow — an SCC can contain both a forever-looping path and a
separate escape path to a goal that some other execution takes; the mere
existence of a goal-avoiding execution says nothing about whether the goal is
reachable from that SCC at all.  The auditor's actual check (see
"Limitations" below, which already stated this correctly) is a strict
per-node property — "the goal is *permanently* unreachable from here" — not
"some execution happens to avoid it."  The argument below uses that stricter,
correct definition, for which the iff genuinely holds.

**Update:** the goal-membership predicate is per-state, but "the goal
recurs" is a trace property that a per-node predicate genuinely cannot
express on its own. A node reached inside a component that is only ever
visited once does not certify recurrence, even though it does certify
one-time reachability. The definition and argument below use *cyclic*
goal-containing components throughout, not just goal-containing ones, which
is what makes the two notions coincide correctly. As discussed under "Goal
Outcomes" above, this is a no-op restriction for terminal goals (their goal
components are cyclic by construction, via the `finished -> finished'`-style
trap) and the substantive fix for recurrence-type goals such as Coffee's
`br_c`.

Let `R` be the set of reachable product nodes with no path to a *cyclic*
goal-containing component — i.e., `R` is exactly the set of
**goal-unreachable** nodes. A goal-unreachable trap exists iff some reachable
cyclic SCC is a subset of `R`. (A goal-containing component trivially reaches
itself via the empty path, so no node of such a component is ever in `R`.)

`R` is closed under the transition relation: if `x` is in `R` and `x → y`,
then `y` must also be in `R` — otherwise a path from `y` to a cyclic goal
component, prefixed with the edge `x → y`, would give `x` such a path,
contradicting `x ∈ R`.

*(⇐, holds unconditionally)* If a reachable cyclic SCC `C` has no path to a
cyclic goal-containing SCC, take any `q ∈ C`. A path from `q` to a cyclic
goal component would witness a path from `C`'s component to it, contradicting
the hypothesis. So `q` has no such path, i.e., `q ∈ R`, so `R` is non-empty
and the strategy has a reachable goal-unreachable node.

*(⇒, needs deadlock-freedom)* If some reachable `q` is in `R`. Since this
check only runs after the deadlock check finds none (see "Algorithm" above —
this is exactly why that sequencing matters, not just a convenience), `q`
has an outgoing edge; by closure that successor is also in `R`, and so is
every node reached by repeatedly following edges from `q`. Because `R` is
finite, this must eventually revisit a node, producing a cycle entirely
within `R`. Let `C` be the SCC containing that cycle: every node of `C` is
mutually reachable with every other by definition of SCC, and each
connecting path starts from a node already in `R`, so by closure every node
of `C` is in `R` — meaning no node of `C` has a path to a cyclic goal
component, so `C` has no path to one in the condensed graph. `C` is
reachable (via `q`) and cyclic by construction, so it is a goal-unreachable
trap. (Had `q` instead been a deadlock, "Algorithm" step 1 above would
already have reported it first.)

The auditor computes all SCCs, constructs the condensed acyclic graph, marks
all SCCs that can transitively reach a *cyclic* goal-containing SCC (seeding
backward reachability only from cyclic goal components, not all of them),
and rejects exactly the reachable cyclic SCCs not marked. By the argument
above this flags a component iff it is a goal-unreachable trap — for both
terminal and recurrence goals, and for both termination and task-completion
audits (see "Goal Outcomes" above), without the checker needing to know
which kind it's looking at.

**What this does and doesn't prove.** Every goal-unreachable trap admits an
infinite non-goal execution once the reachable product graph is
deadlock-free (the ⇐ direction above). The converse does *not* hold: an
execution may remain indefinitely in a cyclic SCC that also has an unused
exit toward a cyclic goal-containing component, without the environment ever
being compelled to take it. That's a possible livelock in the ordinary
sense, and this check does not flag it — detecting whether the environment
can be forced or indefinitely sustained into avoiding that exit needs game-
or fairness-aware analysis over the strategy, not ordinary graph
reachability, and is left for future work. So this is a sound and complete
detector for goal-unreachable traps specifically (a structural, closed-off
region with no route to recurring goal satisfaction at all), which is a
real and useful property, but it is not a complete detector for every
possible livelock. See "Limitations" below for what this means for the
pending-without-activation pathology this auditor was built to catch: that
pathology has *no* exit edge at all (no completion outcome is available once
activation has permanently ceased), so it's fully within what this check
catches — it is not an instance of the class this check misses.

### Timeout Semantics

Timeout is intentionally not part of the correctness proof: the
soundness/completeness argument above (Product Graph Soundness, Safety
Checks, Goal-Unreachable Trap Detection) is conditioned on the exploration
completing within its configured wall-clock budget. If it doesn't, the audit
is incomplete — not a pass, not a fail, unknown — and the implementation
reports that as `SynthesisErrorCode.AUDIT_INCOMPLETE` with `incomplete: true`
and a warning, a status distinct from both `SUCCESS` and the confirmed-failure
codes (see "Result" above). This is a pipeline policy choice: the auditor
warns without blocking synthesis when validation cost exceeds the configured
budget — the pipeline manager treats `AUDIT_INCOMPLETE` as non-fatal and
carries it through to the final result rather than letting a later stage's
`SUCCESS` silently overwrite it, so "presumed valid" no longer overstates
what an incomplete audit actually established, and callers that care can
still tell the difference.

## Complexity

Let `n = |S|` (states in the explicit Slugs strategy, i.e. `|Slugs SM|`),
`m` the number of transitions in `S`, `k = |capabilities|`, and `B` the
product of failure-counter domain sizes over capabilities with a configured
`max_consecutive_failures`/`bounded_failure_limit` — each such capability
contributes a factor of `(bound + 2)`; capabilities without a configured
bound contribute a factor of `1` (this is exactly what the counter-explosion
fix guarantees: an unbounded capability can never inflate `B`).

Then the product automaton size is bounded by `|P| ≤ n·(k+1)·B` and its edge
count by `|E_P| ≤ m·(k+1)·B`. Every phase of the audit — reachable
product-graph construction, Tarjan's SCC computation, and the
condensation-plus-backward-reachability pass — is a linear-time graph
algorithm in the graph it processes. The audit therefore runs in
`O((n+m)·(k+1)·B)`: linear in the size of the already-extracted explicit
strategy, times the product-monitor factor from the number of capabilities
and any configured failure bounds. `B` is a *product* over bounded
capabilities — exponential in the number of capabilities that carry a
configured `max_consecutive_failures`/`bounded_failure_limit` specifically,
not in the total capability count `k` — so it can itself dominate cost if
several capabilities each carry a large bound. Don't read "linear in the
explicit strategy" as "small in general": `B` is only observed to be `1` in
every capability set audited so far (none currently configure a bound), not
guaranteed to stay small.

**Relative to synthesis**, the auditor operates in a different computational
regime rather than a strictly cheaper one. GR(1) realizability checking
operates symbolically over the BDD-encoded specification; its practical cost
— as this project's own results show — is governed by BDD size, which
depends on variable interaction and ordering structure rather than
proposition count alone, and can vary by orders of magnitude between
logically similar specifications. The auditor never touches that BDD
representation: it operates entirely on the explicit strategy synthesis has
already extracted. In the configurations evaluated so far, no capability has
a finite failure bound, so `B=1`; subject to confirmation by dedicated
audit-timing experiments (the batch harness now records an `auditor_time_s`
metric per trial — see [batch_run_harness.md](batch_run_harness.md)), the
resulting product graph is expected to remain proportional to the extracted
strategy size, which is consistently orders of magnitude smaller than the BDD
node counts driving synthesis cost.

## Limitations

- The auditor checks the explicit strategy only.  It does not prove that the
  original symbolic GR(1) specification is correct.
- The compiled `.slugsin` is scanned by section; formulas are not symbolically
  evaluated in this release.
- Capability metadata is derived from current pipeline structures.  If a system
  uses nonstandard activation or outcome names that are not reflected in those
  structures, the auditor may need future override support.
- The monitor tracks one pending capability.  Multiple simultaneous activations
  are rejected rather than modeled as independent concurrent attempts.
- For automata marked `reduced_automaton`, strict activation/outcome protocol
  checks are skipped because reduced states may contain merged input-label
  metadata rather than a single concrete incoming outcome.  Run the auditor on
  the raw synthesized strategy to validate pending-capability protocol
  semantics; the reduced audit checks structural/progress properties.
- The `GOAL_UNREACHABLE_TRAP` check detects **goal-unreachable traps** specifically,
  not every possible livelock: it reports a closed progress trap only when
  no path to a *cyclic* goal-containing SCC exists anywhere in the condensed
  DAG.  An SCC with an exit edge to a cyclic goal-containing SCC is not
  flagged, even if the environment can block that exit indefinitely — that's
  a real, possible livelock this check does not catch (see
  "Goal-Unreachable Trap Detection" above for exactly where the two notions
  diverge). This is an intentional design choice (also a coarser guarantee
  than specification-level well-separation checking, which certifies the
  system can never be forced into violating an assumption at
  all — see Maoz & Ringert, "On well-separation of GR(1) specifications,"
  ESEC/FSE 2016) that avoids false positives on retry loops, at the cost of
  not catching every livelock in the general sense. The pending-without-activation
  pathology this auditor targets is unaffected by this gap — it has no exit
  edge at all, so it's always fully caught. Closing this gap needs a
  game/fairness-aware analysis over `env_liveness`, not just more graph
  traversal — every non-trivial SCC with a side exit structurally admits an
  internal-only avoiding cycle, so only evaluating whether the environment's
  fairness assumptions actually force the exit gives a useful signal. See
  [fairness_livelock_detection.md](fairness_livelock_detection.md) for the
  scoped design (not yet implemented).
- An incomplete audit (timeout) is reported as a distinct
  `SynthesisErrorCode.AUDIT_INCOMPLETE` with `incomplete: true`, non-fatal
  by default — see "Timeout Semantics" above. This is why the
  soundness/completeness argument above is conditioned on the audit
  completing within its configured budget, and why callers that need a
  stricter guarantee (e.g. hardware deployment) must check `incomplete` or
  the error code explicitly rather than trust `valid` alone; there is no
  built-in opt-in mode yet to make an incomplete audit fatal.
