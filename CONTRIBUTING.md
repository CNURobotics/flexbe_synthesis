# Contributing

Thank you for helping improve FlexBE Synthesis. This repository contains ROS 2 packages for synthesis pipelines, Slugs-backed GR(1) synthesis, message/action interfaces, and demonstration workflows.

## How to Contribute

1. Fork the repository and create a feature branch from `main`.
2. Make your changes, following the code style described below.
3. Run the tests before opening a pull request (see [Before Opening a Pull Request](#before-opening-a-pull-request)).
4. Open a pull request against `main` with a clear description of the change and why it is needed.

## Development Setup

Use a ROS 2 workspace and place this repository under `src/`.

```bash
colcon build --symlink-install --packages-up-to flexbe_synthesis
source install/setup.bash
```

Install package dependencies with `rosdep` before building in a clean environment.

```bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

## Before Opening a Pull Request

Run the package tests that match your change.

```bash
colcon test --packages-select flexbe_synthesis flexbe_synthesis_msgs flexbe_synthesis_core flexbe_synthesis_generic flexbe_synthesis_slugs flexbe_synthesis_examples
colcon test-result --verbose
```

For metadata-only changes, also check the affected `package.xml` and `setup.py` files remain consistent.

## Code Style

The repository uses ROS 2 ament linting conventions for Python packages:

- `ament_flake8`
- `ament_pep257`
- `ament_copyright`

Python source files must stay within a **135-character line limit** (enforced by the root `.flake8`
and `pyproject.toml`). Do not add per-package `[flake8]` sections that contradict the root config.

Keep source files under the Apache-2.0 header used in this repository unless the file is
vendored third-party code with its own license.

## Pull Request Expectations

- Keep changes scoped to one topic.
- Update package manifests for new runtime or test dependencies.
- Add tests for behavior changes where practical.
- Update README or package documentation when commands, launch files, examples, or user-facing behavior changes.
- Include `colcon test-result --verbose` output or explain why tests were not run.

## License

Any contribution that you make to this repository will be under the Apache 2 License, as
dictated by that [license](http://www.apache.org/licenses/LICENSE-2.0.html):

~~~
5. Submission of Contributions. Unless You explicitly state otherwise,
   any Contribution intentionally submitted for inclusion in the Work
   by You to the Licensor shall be under the terms and conditions of
   this License, without any additional terms or conditions.
   Notwithstanding the above, nothing herein shall supersede or modify
   the terms of any separate license agreement you may have executed
   with Licensor regarding such Contributions.
~~~
