# flexbe_synthesis_slugs

This package provides the Slugs-backed GR(1) synthesis backend for FlexBE
Synthesis. It contains the synthesis plugins, Slugs specification helpers,
automaton conversion code, and validation utility. Runnable examples and demo
walkthroughs live in
[`flexbe_synthesis_examples`](../flexbe_synthesis_examples/README.md).

## Dependencies

For normal use, build this package in the same ROS 2 workspace as the rest of FlexBE Synthesis:

- `flexbe_synthesis_core`
- `flexbe_synthesis_generic`
- `flexbe_synthesis_msgs`
- `flexbe_synthesis_examples`, when running the checked-in examples
- `flexbe_behavior_engine` and `flexbe_webui` 4.1.5+, when using the
  FlexBE WebUI

## Install Slugs

To use the `flexbe_synthesis_slugs` system,
you must install a custom version of Slugs.

Change to the `flexbe_synthesis/flexbe_synthesis_slugs/scripts` folder and run:

```bash
./install_slugs.sh
```

This only needs to be done once per computer.

### Why a custom fork

The upstream Slugs repository (`https://github.com/VerifiableRobotics/slugs`) targets
Python 2 and does not produce all of the output this package requires. The
CNURobotics fork (`https://github.com/CNURobotics/slugs.git`,
branch `flexbe-synthesis`) differs in three important ways:

1. **Python 3 compatibility.** The upstream structured-slugs parser scripts
   (`compiler.py`, `integerVariableSubstitutor.py`) use Python 2 syntax. The
   fork ports them to Python 3. A local copy of these scripts is bundled in
   `helpers/structured_slugs_parser/` to ensure the parser version stays in
   sync with the rest of the package; `install_slugs.sh` only installs the
   binary.  The bundled parser keeps its BSD-style upstream license; see
   `THIRD_PARTY_LICENSES.md` and
   `helpers/structured_slugs_parser/LICENSE.txt`.

2. **JSON strategy output with rank annotations.** The `--jsonOutput` flag
   writes the synthesized Mealy-machine strategy as a JSON file whose nodes
   carry a `rank` field. The `rank` is used during automaton-to-state-machine
   conversion to order states and drive the equivalence-merging pass in
   `SlugsSMReducer`. This output format is required for the automaton-loading
   and SM-generation pipeline to function.

3. **FlexBE synthesis interface enhancements.** The branch includes additional
   changes to support the capability-based GR(1) synthesis workflow. See the
   [fork changelog](https://github.com/CNURobotics/slugs/blob/flexbe-synthesis/CHANGELOG.md)
   for the full list.

The tested baseline is commit `844e680`. The `flexbe-synthesis` branch is
expected to remain compatible with this baseline as it receives updates, but
pinning a deployment to that commit is recommended for reproducible builds.

The installer requires `git`, `make`, a compiler toolchain, and write access to
the selected install directory. Linux is the primary supported platform. The
script is intended to remain compatible with macOS when the required build tools
are available, but macOS should be treated as best effort unless it is tested for
a release.

### Install Location

By default, the script installs the executable as `/usr/local/bin/slugs`. This
is convenient because `/usr/local/bin` is normally already on `PATH`, but the
script may need `sudo` if that directory is not writable.

To install without touching a root-owned directory, set `SLUGS_INSTALL_DIR`:

```bash
SLUGS_INSTALL_DIR="$HOME/.local/bin" ./install_slugs.sh
```

You can also use a workspace-local directory:

```bash
SLUGS_INSTALL_DIR="$HOME/flexbe_tools/bin" ./install_slugs.sh
```

The Slugs validation and synthesis plugins use this lookup order:

1. `$SLUGS_INSTALL_DIR/slugs`, when `SLUGS_INSTALL_DIR` is set
2. `slugs` found on `PATH`
3. `/usr/local/bin/slugs`

### ROS 2 Environment

ROS 2 nodes and launch files inherit the environment from the shell that starts
them. Before running `ros2 launch` or `ros2 run`, make sure the shell can find
Slugs in one of the lookup locations above.

For a user-local install, add the directory to `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

For a custom install directory, either add it to `PATH` or export
`SLUGS_INSTALL_DIR`:

```bash
export SLUGS_INSTALL_DIR="$HOME/flexbe_tools/bin"
```

Add the chosen `export` line to your shell startup file, such as `~/.bashrc`, if
you want it to be available in every new terminal. Then open a new terminal or
source that file before sourcing the ROS 2 workspace:

```bash
source ~/.bashrc
source install/setup.bash
```

If you launch FlexBE or synthesis from another terminal, a desktop launcher, or
a script, that process needs the same `PATH` or `SLUGS_INSTALL_DIR` environment.
You can verify discovery with:

```bash
ros2 run flexbe_synthesis_slugs validate_slugs_install
```

## Known Limitations

**Composite pre/postconditions are not yet supported.**
Capability `preconditions` and `postconditions` entries must be single-variable
conditions (e.g., `step_a_m`, `mode=ready`). Boolean formulas that combine
variables with `&` or `|` (e.g., `a&b`, `step_c|mode=1`) will be rejected
during preprocessing with a clear error message. Full Boolean-formula support
in the Slugs transition-system specification is planned for a future release.

**Postconditions are state setters, not action-selection guards.**
Capability `postconditions` entries are interpreted as outcome-driven state updates.
`slugs_transition_system_specification` generates setter and frame/inertia rules from
them, which is correct for persistent state or memory propositions (e.g., a memory flag
used as a goal condition) but wrong for activation variables (`*_a`).

An activation variable such as `log_finished_a` is freely selected each step by the
synthesizer subject to `SYS_TRANS` constraints. Listing `!log_finished_a` as a
postcondition treats it as a persistent proposition and generates incorrect frame rules
for it; the result is either an unrealizable specification or incorrect synthesizer
behavior with no preprocessing-time error.

To prevent a capability from being reactivated on consecutive steps, encode the guard
directly in the `SYS_TRANS` section of a hand-written spec file instead:

```yaml
# Wrong — generates incorrect frame rules for the *_a variable
postconditions:
  completed:
    - '!log_finished_a'

# Correct — explicit guard in the hand-written spec (SYS_TRANS)
SYS_TRANS:
  - "log_finished_c -> !log_finished_a"
```

**`show_slugs_output` is not configurable via pipeline data.**
Unlike `synthesis_timeout_s`, there is no pipeline-data-file equivalent for
`show_slugs_output`; it must be changed directly in the `SlugsSynthesizerHelper`
constructor call inside `slugs_synthesizer.py`.

## Request Semantics

The Slugs request-specification process treats `FlexBESynthesisRequest.goals` as
optional request-level goal constraints. Leave `goals` empty when the objective
is already encoded by capabilities or by an additional specification file; the
process will preserve the existing specification and will not add
request-derived success formulas. Valid `initial_conditions` are still applied
when provided.

When `goals` are provided and finite state-machine outcomes are configured, the
first non-failure requested outcome is used as the success outcome. If the
request does not name a success outcome, the backend defaults to the configured
`finished` mapping.

Two GR(1) safety-transition formulas are generated from the goal and success
outcome.  With `goal` as the conjuncted goal string and `success` as the mapped
outcome proposition:

```
(!goal  &  X(goal))  →  X(success)    # reaching the goal triggers the success outcome
(!X(goal) & !success)  →  !X(success) # success cannot be claimed before the goal is reached
```

**`log_finished_a` design case.** When the mapped success outcome is `finished`
and the specification declares `log_finished_a` as a system proposition, the
backend redirects `success` from `finished` to `log_finished_a`.  This is
because the other capabilities needed to achieve the goal cannot be running
simultaneously with `log_finished`, so `log_finished_a` must be activated at
the step the goal is first reached — not `finished` directly.  The full three-formula set becomes:

```
(!goal  &  X(goal))               →  X(log_finished_a)   # reaching goal activates log
(!X(goal) & !log_finished_a)      →  !X(log_finished_a)  # can't activate before goal
(!X(log_finished_c) & !finished)  →  !X(finished)        # finished only via log_finished_c
```

The third formula uses `X(log_finished_c)` (next-step value) rather than the
current-step value because `log_finished_c` becomes true in the same step that
`finished` does — both are set one step after `log_finished_a` is active.
Using the current-step value would incorrectly block the transition at the step
where `log_finished_a` is active but `log_finished_c` has not yet been set.

The third formula is required because without it the synthesizer has no
constraint preventing it from jumping straight to `finished` without passing
through `log_finished_c`.  The existing `SYS_TRANS` rule
`log_finished_a → log_finished_c'` (written in the capability spec) completes
the chain: one step after activation the log state completes, and the SM
generator maps `log_finished_c` to the `finished` SM outcome.  The
specification must declare both `log_finished_a` and `log_finished_c` as
system propositions for this redirection to apply.

## State Generation

For a detailed walkthrough of how the synthesized automaton is converted into
FlexBE `StateInstantiation` objects — including the `ConcurrentStateGenerator`
pipeline, the concurrent vs. single-state resolution, `@`-parameter lookup,
autonomy computation, and userdata forwarding — see
[docs/state_generation.md](docs/state_generation.md).

## Begin-Game Bootstrap

Some capability-based specifications include a pseudo-capability named
`begin_game`. In the non-parsed one-hot pipeline, `begin_game_a` is a
startup-only activation used to mark the initial synthesized state. It is not a
real FlexBE state and should not appear in the discrete abstraction. The SM
generator strips `begin_game_a` only from the tagged initial state and removes
startup outcome conditions such as `begin_game_c` and `begin_game_f` before
mapping the automaton to FlexBE states. If `begin_game_a` appears on any
non-initial state, SM generation treats the automaton as invalid.

Do not add fake FlexBE mappings for `begin_game` to capability YAML files just
to satisfy SM generation. Model real first actions as ordinary capabilities;
`begin_game` exists only to bootstrap the GR(1) game.

## Parsed Capability Encoding

When `SlugsActivationSpecificationParsed` is in the pipeline it replaces
individual `<cap>_a` activation propositions with a single integer variable
(default name: `capability`).  Two invariants apply across every component that
reads or writes this encoding.

**Slot 0 is always the startup-only slot.**
Index 0 is permanently reserved for the startup phase and is never a valid
steady-state action.  If the user's capabilities include a `begin_game` action
it is assigned index 0; otherwise slot 0 is a virtual null placeholder.
Either way the GR(1) spec always includes `(capability'!=0)` in `sys_trans`,
preventing the synthesizer from returning to slot 0 after the initial step.
Real capability actions always occupy indices 1..N.

The `parsed_action_map` written to the discrete-abstraction YAML contains only
real actions (1..N).  `begin_game` is excluded because it never becomes a
FlexBE SM state.

**Null-bootstrap removal.**
The initial synthesized state may have no SM-level action or terminal outcome
active, even when raw output valuation bits such as memory or pending flags are
set.  After the automaton is decoded, the SM generator recognises an
`is_initial=True` state with no `output_variables` as a null bootstrap, removes
it, and promotes its successors as the effective initial SM states.  The reducer
tags the root candidate with `is_initial=True` so the SM generator can locate it
by flag rather than by graph structure.

## Automaton Reduction Contract

`SlugsSMReducer` applies two equivalence rules during the state-merging phase.

**Input-valuation equivalence.**
Two states are equivalent when their `output_valuation` and `transitions`
match, even when `input_valuation` differs.  States reached via `completed` vs
`failure` that produce the same outputs and reach the same successors are the
same SM state.  They are merged, and their `input_variables` lists are unioned
so the SM generator can emit correct failure/completion outcomes from a single
state.

`completed`, `failure`/`failed`, and other names listed in
`transition_outcomes` are reserved as transition-outcome propositions for this
translation step. Do not reuse those names as unrelated domain propositions in
capabilities or custom specifications. The SM generator uses the generic
`failure` proposition to recover retry/failure edges after reducer merging; a
non-outcome proposition with the same name can therefore be interpreted as a
failure response during transition reconstruction.

**Pending-bit equivalence.**
Output variables whose names end in `_p` are *pending flags*: they record that
an action was activated on the current GR(1) step (conceptually an on-entry
side-effect) and carry no SM-level meaning.  The reducer computes a bitmask of
all `_p`-suffix bit positions and masks those bits out before comparing
`output_valuation`, so states that differ only in pending bits are treated as
equivalent and collapsed into one SM state.  The merged state inherits the
union of `input_variables` from all equivalent variants.

## Diagnostic Output

All Slugs pipeline plugins inherit `verbose: bool = False` from `BaseProcess`.
When `verbose` is `True`, they emit step-by-step diagnostic prints covering
specification building, automaton decoding, state-machine generation, and
layout. See [`flexbe_synthesis_core`](../flexbe_synthesis_core/README.md#verbose-diagnostics)
for how to wire `verbose` into a pipeline via the data file.

`SlugsSynthesizerHelper` has an additional independent flag,
`show_slugs_output` (default `True`), that controls whether the raw terminal
output from the Slugs binary is printed after synthesis. It is separate from
`verbose` because it is useful even during normal (non-verbose) runs — it shows
the synthesis result and the raw Slugs log, which is the primary source of
information when a specification is unrealizable. Set it to `False` in the
`SlugsSynthesizerHelper` constructor call inside `slugs_synthesizer.py` to
suppress it.

`slugs_synthesizer` also enforces a wall-clock timeout for the external Slugs
process. The default is 900 seconds (15 minutes). To allow more time for a
large specification, add or change `synthesis_timeout_s` in the process pipeline
data file and include it as a `float` input for the `slugs_synthesizer` step:

```yaml
/data:
    synthesis_timeout_s: 1800.0
```

Alternatively, set `synthesis_timeout_s` on the `FlexBESynthesisRequest` message to
override the pipeline default for a single request. With the provided request
client or example wrappers, pass `-p synthesis_timeout_s:=<seconds>` after
`--ros-args`. A value of `0.0` (the message default) leaves the
pipeline-configured value unchanged.

When the timeout expires, the helper terminates Slugs, returns synthesis failure,
and writes the timeout warning plus this configuration hint to the `.output`
artifact beside the generated Slugs files.

## Tools

This package also installs command-line helpers for use with Slugs artifacts.

### User Tools

Use `mealy2dot` to generate a GraphViz representation from a `.slugsin` file
and the matching Slugs JSON strategy:

```bash
ros2 run flexbe_synthesis_slugs mealy2dot path/to/spec.slugsin path/to/strategy.json
```

This tool is useful for documenting the resulting state machine.

### Developer Tools

The following tools help debug generated specifications.

Use `count_slugs_specs` to count the entries in each section of a
`.structuredslugs` or `.slugsin` file and validate the `INPUT` and `OUTPUT`
declarations:

```bash
ros2 run flexbe_synthesis_slugs count_slugs_specs path/to/spec.structuredslugs
```

For script-friendly output, use `--format yaml` or `--format json`.


Use `inspect_slugs_specs` with one YAML specification to check formula blocks
for invalid formulas and duplicate or equivalent formulas:

```bash
ros2 run flexbe_synthesis_slugs inspect_slugs_specs path/to/spec.yaml
```

Pass two YAML specifications to compare proposition blocks and report formulas
that do not have an equivalent formula in the other file:

```bash
ros2 run flexbe_synthesis_slugs inspect_slugs_specs path/to/old.yaml path/to/new.yaml
```

Formula parsing and equivalence checks require optional SymPy. Install it with
`sudo apt install python3-sympy` or `python3 -m pip install sympy` if the tool
reports that SymPy is missing.


After a Slugs-backed synthesis run,
you can use `check_slugs_automaton` to inspect the
raw Slugs JSON strategy and verify that it can be converted into the internal
`SlugsAutomaton` representation used by the backend:

```bash
ros2 run flexbe_synthesis_slugs check_slugs_automaton --spec-name coffee_maker
```

The checker searches the current directory and `FLEXBE_SYNTHESIS_HOME`, or
`~/.flexbe_synthesis` when that environment variable is unset. You can also pass
explicit files:

```bash
ros2 run flexbe_synthesis_slugs check_slugs_automaton \
  path/to/spec.json --structuredslugs path/to/spec.structuredslugs
```

Use `check_slugs_automaton` when a synthesis run produces a JSON automaton but
SM generation fails or produces unexpected states — it isolates whether the
problem is in automaton parsing or in downstream SM generation.
