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

import os

from flexbe_synthesis_core.base_preprocess import BasePreProcess
import yaml


class StateMappings(BasePreProcess):
    """Merge custom state mappings into the loaded global mapping set."""

    mappings_path: str
    state_mappings: dict

    def preprocess(self):
        """Load and merge custom mapping values into existing state mappings."""
        if not self.mappings_path:
            print(
                f"{self.name} - No change in state mappings from '{self.mappings_path}'.",
                flush=True,
            )
            return [self.state_mappings]

        if not os.path.exists(self.mappings_path):
            print(
                (
                    f"{self.name} - The state mappings file '{self.mappings_path}' "
                    'does not exist!'
                ),
                flush=True,
            )
            raise FileNotFoundError(
                f"The state mappings file '{self.mappings_path}' does not exist!"
            )

        print(f"Loading state mapping data from\n  '{self.mappings_path}' ...")
        with open(self.mappings_path) as stream:
            custom_mappings = yaml.safe_load(stream)

        if custom_mappings is None:
            print('No new data found!')
            return [self.state_mappings]

        if not isinstance(custom_mappings, dict):
            raise ValueError(
                (
                    f"State mappings file '{self.mappings_path}' must contain a "
                    f'top-level mapping, got {type(custom_mappings).__name__}.'
                )
            )

        for key, value in custom_mappings.items():
            if key not in self.state_mappings:
                self.state_mappings[key] = value
                continue

            existing_value = self.state_mappings[key]
            if isinstance(existing_value, dict):
                if not isinstance(value, dict):
                    raise ValueError(f"'{key}' in custom mapping is not a dictionary.")
                print(f"   Updating dictionary '{key}' in state mappings", flush=True)
                existing_value.update(value)
            elif isinstance(existing_value, list):
                if not isinstance(value, list):
                    raise ValueError(f"'{key}' in custom mapping is not a list.")
                print(f"   Updating list '{key}' in state mappings", flush=True)
                # Consumers treat these as sets; sort for stable debug output.
                self.state_mappings[key] = sorted(set(existing_value + value))
            else:
                print(f"   Updating '{key}' in state mappings", flush=True)
                self.state_mappings[key] = value

        return [self.state_mappings]


def main(inputs):
    """Create state mapping preprocessor from pipeline inputs."""
    return StateMappings(
        name='StateMappings',
        mappings_path=inputs[0],
        state_mappings=inputs[1],
    )


if __name__ == '__main__':
    from ament_index_python.packages import get_package_share_directory

    package_path = get_package_share_directory('flexbe_synthesis_generic')
    print(package_path)

    mappings_path = os.path.join(package_path, 'mappings', 'global_mappings.yaml')
    mapper = main([mappings_path, {}])
    outputs = mapper.preprocess()
    print('Mapping Dictionary')
    print(outputs[0])
