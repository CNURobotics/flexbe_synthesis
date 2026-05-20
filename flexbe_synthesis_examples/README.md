# FlexBE Synthesis Examples

This package contains small, runnable examples for the reusable preprocessors in
`flexbe_synthesis_generic` and the Slugs synthesis backend.

These examples are
intentionally dependency-light so they can ship with the core pipeline without
pulling in the richer demo stacks.

Examples are ordered from simplest to most complex:

- [`Hello World`](docs/hello_world/hello_world.md) — **minimal**: loads a hand-written
  state machine definition from YAML and applies layout; no Slugs synthesis involved.
- [`Coffee`](docs/coffee/coffee.md) — **classic**: full capability-based GR(1) synthesis pipeline
  with a small capability set; good first synthesis example.
  Includes a preprocessing-only launch (`coffee_preprocess_example.launch.py`) that stops before synthesis.
- [`Vending`](docs/vending/vending.md) — **simple**: larger capability set and specification;
  uses the fallback rank-based layout by default.
  Includes a preprocessing-only launch (`vending_preprocess_example.launch.py`) that stops before synthesis.

For more extensive interactive demonstrations, see
[flexbe_synthesis_demo](https://github.com/CNURobotics/flexbe_synthesis_demo.git).

Those demonstrations are described in:

  * D. C. Conner, J. Luzier, E. R. Faith, W. J. Doyle, A. B. Kooiker, A. J. Farney, and I. G. Conner, “Capability-based robot controller synthesis,” in Proc. 2026 IEEE Int. Conf. Electro/Information Technology (EIT), La Crosse, WI, USA, May 21–23, 2026, to be published.


The Slugs-backed examples set `synthesis_timeout_s: 60.0` in their process data so
test and demo runs fail quickly if the solver hangs. Production pipelines can
omit that key to use the backend default of 900 seconds, or raise it for larger
specifications. The timeout can also be set per request by passing
`-p synthesis_timeout_s:=<seconds>` to the generic request client or example
wrappers; this sets the `synthesis_timeout_s` field in `FlexBESynthesisRequest`.

During pytest runs, the synthesis example-pair tests prepend
`test_<system_name>_<launch_name>` to the normal synthesis home before launching
each child process. This keeps parallel `pytest-xdist` workers from sharing
`workspace_defn.yaml` or other preprocessing artifacts while still preserving
outputs for inspection. For example, with the default home, one coffee test
writes under
`~/.flexbe_synthesis/test_coffee_maker_coffee_capabilities_example_launch_py/coffee_maker/`.
Set `FLEXBE_SYNTHESIS_HOME` to redirect the collection root.


## Build

These demonstrations presume that the `flexbe_synthesis`
repo has been cloned and the system built.

```bash
colcon build --symlink-install --packages-up-to flexbe_synthesis_examples
source install/setup.bash
```

The FlexBE usage demonstrations also require the `flexbe_behavior_engine` and `flexbe_webui` 4.1.5+.
