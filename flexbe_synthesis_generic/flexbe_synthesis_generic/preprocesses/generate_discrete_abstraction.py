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

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_core.base_preprocess import BasePreProcess
import yaml


class GenerateDiscreteAbstraction(BasePreProcess):
    """Generate the discrete-abstraction YAML from merged capability data."""

    system_name: str
    system_capabilities: dict
    state_implementations_used: dict
    behaviors_used: dict

    def preprocess(self):
        """Write discrete abstraction configuration to hidden config directory."""
        file_dir = os.path.join(self.synthesis_home, self.system_name, 'configs')
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)

        if 'sm_outcome_mappings' not in self.system_capabilities:
            raise ValueError(

                    'System capabilities for discrete abstraction must include '
                    "'sm_outcome_mappings'."

            )
        sm_outcome_mappings = self.system_capabilities['sm_outcome_mappings']

        file_target = os.path.join(
            file_dir,
            self.system_name + fpths._DISCRETE_ABSTRACTION_CONFIG_EXT,
        )
        print(f"Writing discrete abstraction to \n    '{file_target}' ...", flush=True)
        with open(file_target, 'w') as target:
            discrete_abstraction = {
                'name': self.system_name,
                'output': sm_outcome_mappings,
                'parsed_action_map': {
                    'capability': self.build_parsed_action_map(),
                },
            }
            for abstraction in self.system_capabilities['capabilities']:
                if abstraction == 'begin_game':
                    continue
                discrete_abstraction[f'{abstraction}_a'] = self.build_discrete_abstraction(
                    abstraction
                )

            yaml.safe_dump(discrete_abstraction, target, sort_keys=False)

    def build_parsed_action_map(self):
        """
        Return the canonical parsed-action index map.

        begin_game always occupies slot 0 as the startup-only action and is
        excluded from this map — it is never a real SM state.  Real actions
        start at index 1.
        """
        capability_names = sorted(self.system_capabilities.get('capabilities', {}))
        real_names = [name for name in capability_names if name != 'begin_game']
        return {
            index: f'{name}_a'
            for index, name in enumerate(real_names, start=1)
        }

    def build_discrete_abstraction(self, abstraction_name):
        """Build one discrete-abstraction capability block."""
        capability = self.system_capabilities['capabilities'][abstraction_name]
        autonomy = self._resolve_autonomy(abstraction_name, capability.get('autonomy'))

        if 'behavior' in capability:
            class_decl = {
                'name': StateInstantiation.CLASS_BEHAVIOR,
                'behavior_class': capability['interface'],
                'parameters': capability.get('parameters') or {},
            }
        else:
            class_decl = {
                'name': capability['interface'],
                'parameters': capability.get('parameters') or {},
            }

        abstraction = {
            'class_decl': class_decl,
            'state_outcome_mapping': self.build_state_outcome_mappings(
                abstraction_name
            ),
            'autonomy': autonomy,
        }

        if 'userdata_in' in capability:
            if len(capability['userdata_in']) > 0:
                abstraction['userdata_in'] = {
                    user_data_name: user_data_data['remapping']
                    for user_data_name, user_data_data in capability[
                        'userdata_in'
                    ].items()
                }
            else:
                abstraction['userdata_in'] = []

        if 'userdata_out' in capability:
            if len(capability['userdata_out']) > 0:
                abstraction['userdata_out'] = {
                    user_data_name: user_data_data['remapping']
                    for user_data_name, user_data_data in capability[
                        'userdata_out'
                    ].items()
                }
            else:
                abstraction['userdata_out'] = []

        return abstraction

    def _resolve_autonomy(self, abstraction_name, autonomy_config):
        """Resolve scalar or mapping autonomy configuration to one integer value."""
        if autonomy_config is None:
            return 1

        if isinstance(autonomy_config, (str, int)):
            return self._parse_autonomy_value(abstraction_name, autonomy_config)

        if not isinstance(autonomy_config, dict):
            raise TypeError(

                    f"Invalid autonomy for '{abstraction_name}': expected int, "
                    f'string, or mapping, got {type(autonomy_config).__name__}'

            )

        print(f"  '{abstraction_name}' - {autonomy_config}", flush=True)
        autonomy = 1
        for key, value in autonomy_config.items():
            autonomy = max(
                autonomy,
                self._parse_autonomy_value(
                    abstraction_name,
                    value,
                    f" mapping key '{key}'",
                ),
            )
        return autonomy

    def _parse_autonomy_value(self, abstraction_name, value, context=''):
        """Parse one autonomy value and report invalid configuration clearly."""
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid autonomy for '{abstraction_name}'{context}: {value!r}"
            ) from exc

    def build_state_outcome_mappings(self, abstraction_name):
        """Build outcome remapping list for all transition outcomes."""
        capability = self.system_capabilities['capabilities'][abstraction_name]
        if 'state' in capability:
            outcomes = capability['state']['outcomes']
        elif 'behavior' in capability:
            outcomes = capability['behavior']['outcomes']
        else:
            raise KeyError(
                f"Capability '{abstraction_name}' has neither 'state' nor 'behavior' "
                'interface data'
            )
        transition_outcomes = sorted(self.system_capabilities['transition_outcomes'])

        state_outcome_mappings = {}
        for outcome in transition_outcomes:
            stripped_outcome = outcome.strip()
            mapped_outcomes = []
            for out, out_data in outcomes.items():
                try:
                    remapped = out_data['remapping'].strip()
                    if remapped == stripped_outcome:
                        mapped_outcomes.append(out)
                    elif remapped not in transition_outcomes:
                        print(

                                '\033[1;31m   Invalid outcome remapping '
                                f'{out}: {out_data} not in {transition_outcomes}\033[0m'

                        )
                        raise ValueError('Invalid remapping of outcome!')
                except Exception as exc:
                    print('\033[1;31mgenerate_discrete_abstraction: error while mapping', exc)
                    print(f"'{abstraction_name}' - {outcomes}\033[0m")
                    raise ValueError(
                        f"Invalid mapping from '{out}' in '{abstraction_name}'"
                    ) from exc
            state_outcome_mappings[f'{abstraction_name}_{stripped_outcome[0]}'] = (
                mapped_outcomes
            )

        return state_outcome_mappings


def main(inputs):
    """Create GenerateDiscreteAbstraction preprocess from pipeline inputs."""
    system_name = inputs[0]
    system_capabilities = inputs[1]
    state_implementations_used = inputs[2]
    behaviors_used = inputs[3]

    transition_outcomes = system_capabilities.get('transition_outcomes')
    print(
        f' GenerateDiscreteAbstraction: transition_outcomes={transition_outcomes}',
        flush=True,
    )
    return GenerateDiscreteAbstraction(
        name='Generate Discrete Abstractions',
        system_name=system_name,
        system_capabilities=system_capabilities,
        state_implementations_used=state_implementations_used,
        behaviors_used=behaviors_used,
    )


if __name__ == '__main__':
    from ament_index_python.packages import get_package_share_directory
    from flexbe_synthesis_generic.preprocesses.capability_loader import main as cl_main
    from flexbe_synthesis_generic.preprocesses.workspace_parser import main as wp_main

    package_path = get_package_share_directory('flexbe_synthesis_generic')
    capability_path = os.path.join(
        package_path,
        'example',
        'capabilities',
        'vending_capabilities.yaml',
    )
    system_name = 'vending_demo'

    state_mappings = {
        'state_outcome_mappings': {
            'aborted': 'failure',
            'canceled': 'failure',
            'done': 'completed',
            'empty': 'failure',
            'failed': 'failure',
            'false': 'failure',
            'received': 'completed',
            'timeout': 'failure',
            'true': 'completed',
            'unavailable': 'failure',
        },
        'sm_outcome_mappings': {'failed': 'failed', 'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
    }
    parser = wp_main([state_mappings, 'test'])
    outputs = parser.preprocess()

    print(f"Try to load capabilities from '{capability_path}' ...", flush=True)
    capability_loader = cl_main([system_name, capability_path, outputs[0], state_mappings])
    outputs = capability_loader.preprocess()
    print(f"  {outputs[0]['name']} capabilities with {len(outputs)} outputs")

    print(main([outputs[0]['name']] + outputs).preprocess())
