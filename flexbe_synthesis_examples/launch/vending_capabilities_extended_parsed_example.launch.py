# Copyright 2026 Christopher Newport University
# Capable Humanitarian Robotics and Intelligent Systems Lab (CHRISLAB)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Launch the extended parsed-activation Slugs vending example."""

from flexbe_synthesis_examples.slugs_launch import make_slugs_launch_description


def generate_launch_description():
    """Create the launch description."""
    return make_slugs_launch_description(
        demo='vending_demo',
        capabilities_file='vending_capabilities_extended.yaml',
        spec_file='vending_demo_capabilities_spec.yaml',
        processes_file='capability_processes_def_parsed.yaml',
        processes_data_file='processes_data.yaml',
        preprocesses_data_file='preprocesses_data.yaml',
        global_mappings_file='global_mappings.yaml',
    )
