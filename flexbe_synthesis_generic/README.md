# flexbe_synthesis_generic

`flexbe_synthesis_generic` provides reusable FlexBE Synthesis preprocessors and
pipeline stages for turning capability YAML into intermediate synthesis
configuration.

The package includes:

- capability loading and workspace validation
- global outcome and state mapping support
- transition-relation generation
- discrete-abstraction generation
- state-machine layout helpers

Runnable examples live in
[`flexbe_synthesis_examples`](../flexbe_synthesis_examples/README.md)
so this package can stay focused on reusable framework code.

## Plugins

### Preprocessors

Preprocessors run once at server startup and write intermediate configuration
files under `synthesis_home`.

- **`WorkspaceCrawler`** (`workspace_crawler.py`) — discovers every FlexBE
  package in the ROS workspace, parses state and behavior Python files via AST,
  and writes a `workspace_defn.yaml` containing interface metadata (outcomes,
  parameters, userdata) for all found states and behaviors.

- **`StateMappings`** (`state_mappings.py`) — loads a global mapping YAML and
  merges any per-system custom outcome mappings into it. Produces the
  `state_outcome_mappings`, `sm_outcome_mappings`, and `transition_outcomes`
  tables consumed by downstream preprocessors. Runs twice in the default
  pipeline: once for the global mappings file, once for the per-system custom
  mappings file.

- **`WorkspaceParser`** (`workspace_parser.py`) — loads the crawled workspace
  definition and remaps raw state/behavior outcomes using the merged state-
  outcome mappings. Outputs a `workspace_data` dict keyed by interface name.

- **`CapabilityLoader`** (`capability_loader.py`) — reads a system capabilities
  YAML, validates each capability's interface name against the workspace data,
  validates declared parameters and userdata keys, resolves transition-outcome
  tags for uniqueness, and writes a merged `system_capabilities` config file.
  Supports both state-backed and behavior-backed capabilities.

- **`GenerateTransitionRelations`** (`generate_transition_relations.py`) —
  derives capability-to-capability transition structure from declared
  `preconditions`, `postconditions`, and `transition_relation` entries. Writes a
  `transition_relations` config including `action_preconditions`,
  `action_postconditions`, and `unmet_needs` for planner consumption.

- **`GenerateDiscreteAbstraction`** (`generate_discrete_abstraction.py`) —
  produces the discrete-abstraction YAML that maps each capability to its GR(1)
  proposition names (`<name>_a`, `<name>_c`, `<name>_f`, …), interface class
  declaration, autonomy level, and userdata remappings. Supports both state-backed
  and behavior-backed capabilities.

### Processes

Processes run per synthesis request.

- **`SystemCapabilityLoader`** (`system_capabilities_loader.py`) — reloads the
  `system_capabilities` and `transition_relations` config files written by the
  preprocessors and merges them into a single `system_capabilities` dict for use
  by downstream synthesis processes.

- **`SM_Layout`** (`sm_layout.py`) — takes a list of `StateInstantiation`
  objects from the SM generator and embeds display positions before passing the
  list downstream. It uses the Graphviz-backed layout when `pygraphviz` is
  available and `use_fallback_layout` is false; otherwise, it falls back to a
  deterministic rank-based layout. The Graphviz path can write `.dot` and `.png`
  graph artifacts, while the fallback path writes `.dot` only.

## Shared Mappings

The installed `mappings/global_mappings.yaml` file defines the default outcome
normalization commonly used in FlexBE states.
The generic capability examples and demonstration launch files use it
directly from this package.

`state_outcome_mappings` maps concrete FlexBE state outcomes, such as `done` or
`failed`, onto normalized transition outcomes. Those normalized outcomes are
listed in `transition_outcomes`.

The first character of each normalized transition outcome is used as the compact
tag in generated discrete-abstraction keys, so every entry in
`transition_outcomes` must be non-empty and must start with a unique character.
The default mappings use `completed` and `failure`, producing the unique tags
`c` and `f`. A mapping set with both `completed` and `canceled` would be
rejected because both outcomes start with `c`.

## Transition Relations

Capability YAML should prefer outcome-keyed transition relations when different
outcomes produce different postconditions:

```yaml
transition_relation:
  completed:
    - pay
  failure:
    - retry_payment
```

For backward compatibility, a bare list is also accepted and is interpreted as
the `completed` outcome:

```yaml
transition_relation:
  - pay
```

The transition-relation generator logs a warning when it applies this shorthand.
Use the outcome-keyed form whenever a capability has non-`completed` transition
effects, or when documenting the outcome explicitly makes the capability easier
to audit.

## Postcondition Semantics

Capability `postconditions` describe persistent state or memory effects that occur when
an outcome is reached. `GenerateTransitionRelations` collects them as
`action_postconditions` and the GR(1) backend generates setter and frame/inertia rules
from them in the transition system (see `slugs_transition_system_specification` in
`flexbe_synthesis_slugs` for the Slugs implementation).

This model is appropriate for memory propositions used as goal conditions:

```yaml
postconditions:
  completed:
    - 'log_finished'  # memory flag; used in SYS_LIVENESS as the goal condition
```

**Do not put activation variables (`*_a`) in postconditions.** Action variables are
freely chosen each step by the synthesizer, subject to `SYS_TRANS` constraints. Writing
one as a postcondition target causes the pipeline to treat it as a persistent state
proposition and emit incorrect frame rules for it. The pipeline does not detect this
misuse at preprocessing time. Encode action-selection guards in an explicit `SYS_TRANS`
clause instead:

```yaml
# Wrong — postcondition on an *_a variable generates incorrect frame rules
postconditions:
  completed:
    - '!log_finished_a'

# Correct — hand-write the guard in the backend spec (Slugs SYS_TRANS section)
SYS_TRANS:
  - "log_finished_c -> !log_finished_a"
```

Composite Boolean postconditions (e.g., `a&b` or `x|y`) are also not yet supported;
see the `flexbe_synthesis_slugs` Known Limitations for details.

## Workspace Discovery

The workspace crawler can still be run directly when you need to refresh the
workspace definition used by capability validation:

```bash
ros2 run flexbe_synthesis_generic workspace_crawler
```

The generated workspace data is written under `FLEXBE_SYNTHESIS_HOME` when that
environment variable is set, or `~/.flexbe_synthesis` otherwise.

When these preprocessors are run by `flexbe_synthesis_core`, the manager injects
its resolved `synthesis_home` value into each plugin through the shared base
classes. That keeps generated workspace and system configuration files in the
same artifact directory selected by the launch file without repeating that path
in every pipeline entry.
