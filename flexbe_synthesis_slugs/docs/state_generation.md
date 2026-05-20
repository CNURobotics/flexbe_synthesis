# State Generation from Synthesized Automata

This document describes how the Slugs backend converts a synthesized GR(1)
automaton into the `StateInstantiation` list that FlexBE uses to load a
behavior at runtime.

## Overview

The entry point is
`SMGenerationHelpers.generate_sm_handle()` in
[`sm_generation_helpers.py`](../flexbe_synthesis_slugs/helpers/sm_generation_helpers.py).
It reads two YAML artifacts produced by earlier pipeline steps, iterates over
every state in the synthesized automaton, and emits one `StateInstantiation`
per automaton state (plus a root `StateInstantiation` for the state machine
itself).

```
generate_sm_handle(automaton, system_name)
│
├─ load system_capabilities YAML          ← <system>_capabilities.yaml
├─ load discrete_abstraction YAML         ← <system>_discrete_abstraction.yaml
├─ SlugsAutomaton.from_dict(automaton)    ← parse Slugs JSON strategy
├─ normalize_bootstrap_begin_game()       ← strip startup-only begin_game vars
├─ apply variable_mappings (optional)     ← remap integer values to strings
├─ modify_names()                         ← make state names human-readable
├─ SMGenConfig(discrete_abstraction, …)   ← helper for decl/transition lookups
├─ emit root StateInstantiation  (path="/")
│
└─ for each automaton state:
       ConcurrentStateGenerator(name)
       │  add_internal_state() per output variable
       │  add_internal_userdata() per output variable
       │  for each transition → add_internal_outcome_and_transition()
       │                      → add_internal_outcome_maps()
       └─ csg.gen(state)  →  StateInstantiation
```

### State naming

`modify_names()` renames each numeric automaton state by appending the
output-variable labels that are active in that state.  A state that activates
`stand_a` and `grasp_a` becomes `0_stand_grasp` (the `_<char>` suffixes added
by the GR(1) encoding are stripped by `clean_variable()`).

### Variable mappings

When the capabilities YAML contains a `variable_mappings` block, the integer
values produced by Slugs for each state's `input_values` and `output_values`
are remapped to their string labels before any further processing.  This lets
the downstream code work with names like `"stand"` instead of `"2"`.

### Begin-game bootstrap

The non-parsed capability pipeline may carry a `begin_game` pseudo-capability
from the GR(1) startup phase. `begin_game_a` is allowed only on the tagged
`is_initial=True` automaton state. Before SM generation builds state labels or
looks up discrete-abstraction mappings, `normalize_bootstrap_begin_game()`
removes `begin_game_a` from that initial state and removes startup outcome
conditions such as `begin_game_c` and `begin_game_f` from every state.

This makes the initial state look like the null bootstrap described below, so
`SMGenConfig.get_init_states()` can remove it and promote the first real action
state. Because `begin_game` is not a real FlexBE state, it should not be listed
in the discrete abstraction. A non-initial `begin_game_a` is treated as an
invalid automaton instead of being silently normalized.

### Outcome tags

`SMGenConfig` maps generic transition outcomes from parsed Slugs automata back
to the active capability response variable by using the compact outcome tag
stored in the discrete abstraction, such as `completed` → `_c`, `failure` →
`_f`, or `waiting` → `_w`.  The canonical contract for those tags lives in the
[`flexbe_synthesis_generic` README](../../flexbe_synthesis_generic/README.md#shared-mappings):
each normalized `transition_outcomes` entry must be non-empty and must start
with a unique character.

The transition-outcome names themselves are reserved for this backend
translation. In particular, `failure`/`failed` must mean a capability failure
outcome, not an unrelated domain proposition. After `SlugsSMReducer` merges
equivalent completed/failure variants, `SMGenConfig.get_transitions()` uses the
generic `failure` input value plus the `_f` response suffix to reconstruct
retry/failure edges. Reusing `failure` for another purpose can make transition
generation silently choose the failure response.

---

## ConcurrentStateGenerator

[`helpers/sm_gen/concurrent_state_generator.py`](../flexbe_synthesis_slugs/helpers/sm_gen/concurrent_state_generator.py)
accumulates the class declarations and transition data for a single automaton
state, then emits a `StateInstantiation` via `gen()`.

### Building up the generator

| Method | What it stores |
|---|---|
| `add_internal_state(label, class_decl)` | Cleaned label → class declaration mapping.  Duplicate labels are silently ignored.  The `_<char>` suffix is stripped with `clean_variable()` before storing. |
| `add_internal_outcome_and_transition(outcome, transition, autonomy_list)` | Appends outcome/transition pair; accumulates autonomy values into `outcome_to_autonomy_list[outcome]`. |
| `add_internal_outcome_maps(out_map)` | Appends a cleaned outcome-map dict `{outcome, condition}` with all condition keys run through `clean_variable()`.  Duplicate maps are skipped. |
| `add_internal_userdata(userdata_remapping)` | Extends the userdata keys and remapping lists. |

### is_concurrent()

```python
def is_concurrent(self):
    return len(self.internal_states) > 1
```

An automaton state is *concurrent* when it activates more than one capability
at the same time.  In that case `gen()` wraps the internal states in a
`ConcurrentState`; otherwise it unwraps to the single inner class directly.

---

## gen() — concurrent path

When `is_concurrent()` is `True`, `gen()` builds a `ConcurrentState`
`StateInstantiation` with three parameters:

| Parameter | Content |
|---|---|
| `states` | Python dict literal mapping each cleaned label to its constructor string, e.g. `{"stand": StandState(), "grasp": GraspState()}` |
| `outcomes` | Python list literal of the outcome labels |
| `outcome_mapping` | Python list-of-dicts literal, one entry per outcome, each with `outcome` and `condition` keys |

```python
parameters = {
    'states': self.gen_states_str(),
    'outcomes': str(self.internal_outcomes),
    'outcome_mapping': str(self.internal_outcome_maps),
}
```

`gen_states_str()` calls `class_decl_to_string()` for each internal state,
which produces `ClassName(param1=val1, …)` constructor syntax.

The `StateInstantiation` is created via `new_si()` with:
- `state_path = '/' + self.name`
- `state_class = 'ConcurrentState'`
- outcomes, transitions, and autonomy derived from the accumulated data
- userdata keys and remapping forwarded from `add_internal_userdata()` calls

---

## gen_single() — single-state path

When only one internal state was added, `gen()` delegates to `gen_single()`,
which unwraps to the inner class:

```python
state_class = decl['name']          # e.g. 'ControlModeState'
```

All parameters from the class declaration are processed and added to the
`StateInstantiation`.  `@`-prefixed parameter values are resolved against the
automaton state's `output_values` and `input_values`:

```
parameter value "@stand_a"
    → strip "@"  → look up "stand_a" in state.output_values
    → if found, use that value
    → else look up in state.input_values
    → else leave the raw "@…" string (quoted as a Python string literal)
```

String values are then normalized:
- Values starting with `*` are treated as variable references (the `*` is
  stripped and the value is used as-is).
- `'None'` and `"None"` become the bare Python keyword `None`.
- Values containing `self.` are passed through unchanged (self-references).
- All other bare strings are wrapped in single quotes.

---

## Autonomy

Both paths compute autonomy the same way: for each outcome, take the maximum
of all autonomy values collected for that outcome across every transition that
was added:

```python
autonomy = [
    max(self.outcome_to_autonomy_list[outcome])
    for outcome in self.internal_outcomes
]
```

The autonomy list fed to `add_internal_outcome_and_transition()` comes from
`SMGenConfig.get_autonomy_list()`, which derives a value per sub-state from
the discrete abstraction.

---

## Userdata

Userdata keys and remapping values are collected per output variable by
`SMGenConfig.get_userdata_mapping()` and forwarded to the `ConcurrentStateGenerator`
via `add_internal_userdata()`.  Both `gen()` and `gen_single()` propagate the
accumulated lists to `new_si()`, so userdata is present regardless of whether
the resulting state is a `ConcurrentState` or a plain inner class.

---

## Supporting utilities

| Utility | Location |
|---|---|
| `new_si()` — build a `StateInstantiation` | `helpers/sm_gen/sm_gen_util.py` |
| `class_decl_to_string()` — class declaration to constructor string | `helpers/sm_gen/sm_gen_util.py` |
| `clean_variable()` — strip `_<char>` suffix | `helpers/sm_gen/sm_gen_util.py` |
| `SMGenConfig` — discrete-abstraction lookups | `helpers/sm_gen/sm_gen_config.py` |
| `SlugsAutomaton` — automaton model | `helpers/slugs_automaton.py` |
