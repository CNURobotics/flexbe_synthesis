# flexbe_synthesis

`flexbe_synthesis` is the metapackage for the FlexBE Synthesis stack. It does
not implement synthesis behavior directly; it groups the runtime packages that
make up the default synthesis workflow so a user can depend on or install the
stack as a unit.

## Repository Layout

This repository contains the following ROS 2 packages:

- `flexbe_synthesis`: this metapackage for the default FlexBE Synthesis stack.
- `flexbe_synthesis_msgs`: action and message interfaces shared by the stack.
- `flexbe_synthesis_core`: synthesis action server, plugin loading, pipeline
  execution, validation helpers, and shared base classes.
- `flexbe_synthesis_generic`: generic preprocessors and pipeline stages for
  capability loading, workspace parsing, transition relation generation, and
  state-machine layout support.
- `flexbe_synthesis_slugs`: Slugs-backed GR(1) synthesis backend, specification
  generation helpers, automaton loading, and state machine generation.  This is
  provided as a reference backend implementation for the pipeline.
- `flexbe_synthesis_examples`: basic examples and tutorials.

## Dependency Role

The metapackage declares runtime dependencies on:

- `flexbe_synthesis_core`
- `flexbe_synthesis_generic`
- `flexbe_synthesis_msgs`
- `flexbe_synthesis_slugs`

The examples package is intentionally kept outside the metapackage dependency set
so downstream users can depend on the runtime stack without also pulling in
tutorial launch files and fixtures. Build `flexbe_synthesis_examples` explicitly
when running the repository examples.

## Build

From a ROS 2 workspace containing this repository:

```bash
colcon build --symlink-install --packages-up-to flexbe_synthesis
```
