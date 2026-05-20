# flexbe_synthesis_core

Core synthesis manager, plugin interfaces, and pipeline utilities for FlexBE
Synthesis.

This package provides the ROS 2 action server that executes a configured
behavior synthesis pipeline. It also defines the base classes and entry point
contracts used by preprocess and process plugins in backend packages such as
`flexbe_synthesis_generic` and `flexbe_synthesis_slugs`.

## Package Contents

- `flexbe_synthesis_core.synthesis_manager`: action server for
  `flexbe_synthesis_msgs/action/FlexBESynthesis`.
- `flexbe_synthesis_core.base_preprocess.BasePreProcess`: base class for
  workspace/setup preprocessing steps.
- `flexbe_synthesis_core.base_process.BaseProcess`: base class for synthesis
  process steps.
- `flexbe_synthesis_core.pipeline_type_validation`: helpers for validating
  configured pipeline input/output types.
- `flexbe_synthesis_core.error_code_map`: helpers for displaying
  `SynthesisErrorCode` values.

## Action Server

Run the server with:

```bash
ros2 run flexbe_synthesis_core flexbe_synthesis_server
```

The server requires pipeline configuration parameters, normally supplied by a
launch file:

- `preprocesses_filepath`: YAML file describing preprocessing entry points.
- `preprocesses_data_filepath`: optional YAML file with preprocessing data.
- `processes_filepath`: YAML file describing runtime process entry points.
- `processes_data_filepath`: optional YAML file with runtime process data.
- `system_name`: default synthesis system name.
- `capabilities_path`: path to system capabilities.
- `spec_path`: path to input specifications.
- `automaton_path`: path to a pre-synthesized automaton file (bypasses synthesis).
- `global_mappings_path`: path to shared outcome/capability mappings.
- `custom_mappings_path`: path to system-specific mappings.
- `synthesis_home`: directory for generated synthesis artifacts. If unset, the
  server uses an environment variable `FLEXBE_SYNTHESIS_HOME`, or if that is not defined, then falls back to `~/.flexbe_synthesis`.
- `save_outputs`: whether to write intermediate YAML artifacts.
- `verbose`: when `true`, the server prints the full `StateInstantiation` dump
  after a successful synthesis run. Also available as `ros:verbose` in data
  files so individual plugins can opt in (see [Verbose Diagnostics](#verbose-diagnostics)).

The resolved `synthesis_home` value is injected into every `BasePreProcess` and
`BaseProcess` instance so plugins use the same artifact directory as the
manager. The `verbose` parameter is not injected globally; plugins that want
to produce diagnostic output must declare `verbose: bool` as a pipeline input
and receive it from the data file (see [Verbose Diagnostics](#verbose-diagnostics)).

At startup, the server loads preprocessors, runs them once, loads process
plugins, validates the runtime pipeline, and then waits for
`FlexBESynthesis` action goals. During goal execution it publishes feedback
with the running plugin name and a step-start progress fraction before each
plugin executes.

## Pipeline YAML

Pipelines are ordered lists of Python entry points. Each entry point may declare
named inputs and outputs. The names connect one step's outputs to later steps'
inputs through the server's shared data dictionary.

```yaml
/pipeline:
  - entry_point:
      name: capability_loader
      inputs:
        system_name: str
      outputs:
        system_capabilities: dict
  - entry_point:
      name: slugs_spec_compiler
      inputs:
        system_name: str
        system_capabilities: dict
      outputs:
        current_specification: dict
        error_code: SynthesisErrorCode
```

Each `entry_point` must define `name`. `inputs` and `outputs` are optional for
steps that do not consume or produce shared data. Each entry point may also set
`strict_type_validation: false` to keep type mismatches as warnings for that
single process; omitted values default to strict validation.

Before accepting action goals, the server validates that every configured input
is available from initial data or from an earlier plugin output. If a plugin
writes a name that was already produced, the server logs a warning because later
steps will see the new value.

## Data Files

An optional data file (`*_data.yaml`) seeds the shared data dictionary before the pipeline runs. It uses a `/data` top-level key:

```yaml
/data:
    system_name: 'ros:system_name'              # resolved from the ROS launch parameter
    capabilities_path: 'ros:capabilities_path'
    spec_name: 'req:spec_name'                  # resolved from the action request field
    spec_path: 'req:specification_file_name'    # resolved from a differently-named request field
    mealy_graph_config:                         # literal nested value
        draw_graph: false
        layout: 'dot'
```

Two reference prefixes are supported:

- **`ros:param_name`** — resolved at data-file load time to the named ROS launch parameter. Valid names: `system_name`, `capabilities_path`, `spec_path`, `automaton_path`, `global_mappings_path`, `custom_mappings_path`, `verbose`. A typo raises a `ValueError` immediately.
- **`req:field_name`** — resolved per action request to the named field of `FlexBESynthesisRequest`. Valid names: `spec_name`, `specification_file_name`, `system_name`. A typo or empty field raises a `ValueError` when the request arrives.

All other values (strings, numbers, lists, nested mappings) are placed into the dictionary as literals.

## Plugin Entry Points

Python packages that provide synthesis plugins expose them through setuptools
entry points. Runtime process plugins use the `FlexBESynthesis.processes` group;
preprocess plugins use `FlexBESynthesis.preprocesses`.

```python
entry_points={
    'FlexBESynthesis.processes': [
        'my_process = my_package.processes.my_process:main',
    ],
    'FlexBESynthesis.preprocesses': [
        'my_preprocess = my_package.preprocesses.my_preprocess:main',
    ],
}
```

The configured pipeline `name` must match the entry point name.

After adding, renaming, or removing an entry point in `setup.py`, run
`colcon build` before starting the server. `--symlink-install` symlinks Python
source files but does not regenerate the `entry_points.txt` egg-info metadata,
so the server will not see the change until the package is rebuilt. The symptom
of a missing rebuild is a "plugin not found" `ValidationError` at startup that
looks like a code bug but is actually a packaging artifact.

## Plugin Input Contract

The manager passes inputs to `main(inputs)` as a positional list ordered by the
YAML `inputs:` declaration, not as a dict keyed by the YAML input names.  This
is intentional.  A reusable utility plugin may appear at multiple positions in a
pipeline, receiving a semantically equivalent value that happens to live under
different pipeline key names at each call site.  If `main` received a dict keyed
by those names, the factory would have to enumerate every key it might encounter,
coupling the plugin to naming decisions made outside it.  With a positional list
the factory declares its expected argument order in the YAML and the pipeline
author supplies the right value at the right position, keeping the plugin
decoupled from the surrounding pipeline's naming conventions.  Keep plugin input
lists short so positional errors are caught quickly during pipeline validation.

## Process Plugins

Runtime process plugins inherit from `BaseProcess` and implement `process()`.
Their entry point function receives a list of configured input values and
returns an initialized process instance.

```python
from flexbe_synthesis_core.base_process import BaseProcess


class Divider(BaseProcess):
    num1: int
    num2: int

    def process(self):
        return self.num1 / self.num2, self.num2 / self.num1


def main(inputs):
    return Divider(name='divider', num1=inputs[0], num2=inputs[1])
```

The tuple/list returned by `process()` is mapped to the configured output names
by position. For outputs named `error_code`, return a
`flexbe_synthesis_msgs.msg.SynthesisErrorCode` instance so the server can stop
the pipeline on failure. Plugins may override `cancel()` to clean up work they
own, such as terminating subprocesses. The default implementation is a no-op.

## Preprocess Plugins

Preprocess plugins inherit from `BasePreProcess` and implement `preprocess()`.
They use the same entry point pattern as process plugins, but run once during
server startup before runtime action goals are accepted.

```python
from flexbe_synthesis_core.base_preprocess import BasePreProcess


class CapabilityIndex(BasePreProcess):
    capabilities_path: str

    def preprocess(self):
        index = load_capabilities(self.capabilities_path)
        return [index]   # one value per declared output, in declaration order


def main(inputs):
    return CapabilityIndex(name='capability_index', capabilities_path=inputs[0])
```

## Type Names

Pipeline YAML may use the type names supported by
`flexbe_synthesis_core.pipeline_type_validation.TYPE_MAPPING`, including common
Python types, `FlexBESynthesisRequest`, `SynthesisErrorCode`, and
`List[StateInstantiation]`. Type declarations are used for validation and
warnings; plugin implementations should still validate user-facing data before
using it.

`TYPE_MAPPING` is a centralized dict in `flexbe_synthesis_core`. Plugin packages
in other repositories cannot add named types without editing core. Two approaches
are available:

**Preferred: use `dict`.**
Pass structured data as a plain `dict`, or declare it with one of the existing
semantic aliases (`Automaton`, `Specification`, `SystemCapabilities`, etc. — all
`dict` under the hood). The YAML key name carries the semantic meaning; the type
string is only used for pipeline validation.

**Alternative: extend `TYPE_MAPPING` at import time.**
Add entries in your plugin package's `__init__.py` before the server validates
the pipeline:

```python
from flexbe_synthesis_core.pipeline_type_validation import TYPE_MAPPING
TYPE_MAPPING['MyCustomType'] = dict
```

This runs at package import time, which is before pipeline validation, so the
type is available when needed. It avoids modifying core but mutates shared state.

A future `FlexBESynthesis.types` entry-point group would let packages
self-register types the same way plugins are discovered, but this is not yet
implemented.

## Verbose Diagnostics

Most pipeline plugins suppress diagnostic print output by default. Each plugin
that supports it exposes a `verbose: bool` field (inherited from `BaseProcess`,
default `False`). Because `verbose` is not injected globally, enabling it for a
specific plugin requires two small additions to the pipeline configuration.

**Step 1 — declare the input in the pipeline definition file:**

```yaml
- entry_point:
    name: system_capabilities_loader
    inputs:
        system_name: NameStr
        slugs_specification: Specification
        verbose: bool       # set true to dump the full capabilities dict on load
    outputs:
        system_capabilities: SystemCapabilities
```

**Step 2 — supply the value in the data file, referencing the server's `verbose`
ROS parameter:**

```yaml
/data:
    # ... other entries ...
    verbose: 'ros:verbose'   # pass verbose:=true at launch to enable diagnostic output
```

**Step 3 — launch with `verbose:=true`:**

```bash
ros2 launch flexbe_synthesis_examples coffee_capabilities_example.launch.py verbose:=true
```

When `verbose` is `false` (the default), `system_capabilities_loader` loads
silently. When `true`, it prints the full parsed capabilities dictionary,
which is useful for confirming that capability YAML was loaded and merged
correctly.

The `verbose: 'ros:verbose'` entry is pre-wired in the coffee and vending
example data files. The same pattern can be applied to any other plugin that
declares a `verbose` input.

The server's own `verbose` parameter (without any plugin input declaration)
controls only the final `StateInstantiation` dump printed after a successful
synthesis run.

## Generated Artifacts

When `save_outputs` is enabled, preprocessing outputs and process outputs are
written under `synthesis_home` for the active system and specification. These
artifacts are intended for debugging and inspection, not as a stable public file
format.
