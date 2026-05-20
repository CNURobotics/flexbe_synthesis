# FlexBE Synthesis System

This system provides a capability-based pipeline for
generating executable FlexBE state machines.


## Quick Start

```bash
# 1. Clone into a ROS 2 workspace and install dependencies
cd $WORKSPACE_ROOT
git clone https://github.com/CNURobotics/flexbe_synthesis src/flexbe_synthesis
rosdep update && rosdep install --from-paths src --ignore-src -r -y

# 2. Build and source
colcon build --symlink-install --packages-up-to flexbe_synthesis_examples
source install/setup.bash

# 3. Install the custom Slugs binary (required for GR(1) synthesis examples)
cd src/flexbe_synthesis/flexbe_synthesis_slugs/scripts
./install_slugs.sh

# 4. Run an example
ros2 launch flexbe_synthesis_examples hello_world_example.launch.py
# or, for the full capability-based synthesis pipeline:
ros2 launch flexbe_synthesis_examples coffee_capabilities_example.launch.py
```

See [Minimum Test Setup](#minimum-test-setup) below for full prerequisites,
including FlexBE Behavior Engine and WebUI.

---

Basic examples demonstrating the pipeline are in
[`flexbe_synthesis_examples`](flexbe_synthesis_examples/README.md).

This system is described in

  * D. C. Conner, J. Luzier, E. R. Faith, W. J. Doyle, A. B. Kooiker, A. J. Farney, and I. G. Conner, “Capability-based robot controller synthesis,” in Proc. 2026 IEEE Int. Conf. Electro/Information Technology (EIT), La Crosse, WI, USA, May 21–23, 2026, to be published.

More extensive and interactive demonstrations described in the paper live in
[flexbe_synthesis_demo](https://github.com/CNURobotics/flexbe_synthesis_demo.git).


## Minimum Test Setup

This repository has been tested on ROS 2 Jazzy, Kilted, and Rolling.

In a clean ROS 2 workspace, you need to clone:
 * [`flexbe_synthesis`](https://github.com/CNURobotics/flexbe_synthesis) (main)

To use the `flexbe_synthesis_slugs` GR(1)-based synthesis system,
you must install a custom version of `Slugs` as
described in the [Slugs README](flexbe_synthesis_slugs/README.md).


The synthesis system can be tested standalone, but
is intended to generate executable state machines using the FlexBE Behavior Engine.
This requires installing:
 * [`flexbe_behavior_engine`](https://github.com/FlexBE/flexbe_behavior_engine.git) (ros2-devel)
 * [`flexbe_webui`](https://github.com/FlexBE/flexbe_webui.git) (main)
The FlexBE Behavior Engine and FlexBE WebUI should be 4.1.5+.

After cloning the relevant repositories,
install ROS dependencies, do a `colcon build`, and source the `setup.bash`; e.g.,

```bash
cd $WORKSPACE_ROOT
rosdep update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-up-to flexbe_synthesis_examples
source install/setup.bash
```

The Slugs-backed synthesis examples use the Slugs GR(1) synthesis tool. For
Slugs-specific setup directions, see

* [flexbe_synthesis_slugs/README.md](flexbe_synthesis_slugs/README.md)


## Package Documentation

Core pipeline, plugin, and action-server documentation now lives in
[`flexbe_synthesis_core/README.md`](flexbe_synthesis_core/README.md).

Generic preprocessing documentation lives in
[`flexbe_synthesis_generic/README.md`](flexbe_synthesis_generic/README.md).

Information about using
Slugs GR(1)-based synthesis lives in
[`flexbe_synthesis_slugs/README.md`](flexbe_synthesis_slugs/README.md).

## Examples

This project provides several example demonstrations in:

* [flexbe_synthesis_examples/README.md](flexbe_synthesis_examples/README.md)


## Related Publications

This synthesis work is based on prior work by:

 - J. Luzier and D. C. Conner, "Solving the Farmer's Dilemma with FlexBE Using GR(1) Synthesis," SoutheastCon 2024, Atlanta, GA, USA, 2024, pp. 1189–1196, doi: [10.1109/SoutheastCon52093.2024.10500189](https://doi.org/10.1109/SoutheastCon52093.2024.10500189).


- J. W. M. Hayhurst and D. C. Conner, ["Towards Capability-Based Synthesis of Executable Robot Behaviors,"](http://dx.doi.org/10.1109/SECON.2018.8479047) IEEE SoutheastCon 2018, St. Petersburg, FL, USA, 2018.

- S. Maniatopoulos, P. Schillinger, V. Pong, D. C. Conner and H. Kress-Gazit, ["Reactive high-level behavior synthesis for an Atlas humanoid robot,"](http://dx.doi.org/10.1109/ICRA.2016.7487613), 2016 IEEE International Conference on Robotics and Automation (ICRA), Stockholm, Sweden, 2016.

- Rüdiger Ehlers and Vasumathi Raman: [Slugs: Extensible GR(1) Synthesis](https://www.ruediger-ehlers.de/papers/cav2016.pdf). 28th International Conference on Computer Aided Verification (CAV 2016), Volume 2, p.333-339

Please use the following publications for reference when using FlexBE:

- Joshua Zutell, David C. Conner and Philipp Schillinger, ["ROS 2-Based Flexible Behavior Engine for Flexible Navigation,"](http://dx.doi.org/10.1109/SoutheastCon48659.2022.9764047), IEEE SouthEastCon, April 2022.

- Philipp Schillinger, Stefan Kohlbrecher, and Oskar von Stryk, ["Human-Robot Collaborative High-Level Control with Application to Rescue Robotics"](http://dx.doi.org/10.1109/ICRA.2016.7487442), IEEE International Conference on Robotics and Automation (ICRA), Stockholm, Sweden, May 2016.

### BibTeX

```bibtex
@inproceedings{FlexBESynthesis26,
  author    = {Conner, David C. and Luzier, Joshua and Faith, Emma R. and Doyle, William J. and Kooiker, Aubrie B. and Farney, Andrew J. and Conner, Ian G.},
  title     = {Capability-based Robot Controller Synthesis},
  booktitle = {Proceedings of the 2026 IEEE International Conference on Electro/Information Technology (EIT)},
  address   = {La Crosse, WI, USA},
  month     = may,
  year      = {2026},
  note      = {To be published}
}
```
