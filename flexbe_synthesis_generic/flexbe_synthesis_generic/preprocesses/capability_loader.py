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

from copy import deepcopy
import logging
import os

from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_core.base_preprocess import BasePreProcess
from flexbe_synthesis_core.validation_error import UserdataValidationError
import yaml

logger = logging.getLogger(__name__)


class CapabilityYamlDumper(yaml.SafeDumper):
    """YAML dumper that forces double-quoted strings and serializes unknown objects."""

    def ignore_aliases(self, data):
        return True

    def represent_str(self, data):
        return self.represent_scalar(
            'tag:yaml.org,2002:str',
            data,
            style='"',
        )

    @staticmethod
    def fallback_representer(dumper, data):
        logger.warning(
            "CapabilityYamlDumper: serializing '%s' via fallback representer — "
            'unexpected type in capability data.',
            type(data).__name__,
        )
        try:
            return dumper.represent_dict(data.__dict__)
        except AttributeError:
            return dumper.represent_str(str(data))


CapabilityYamlDumper.add_multi_representer(object, CapabilityYamlDumper.fallback_representer)
CapabilityYamlDumper.add_representer(str, CapabilityYamlDumper.represent_str)


class CapabilityInterfaceAmbiguityError(ValueError):
    """Raised when a capability interface resolves to more than one artifact type."""


class CapabilityLoader(BasePreProcess):
    """Load and validate system capabilities against workspace definitions."""

    system_name: str
    capabilities_path: str
    workspace_data: dict
    state_mappings: dict

    def preprocess(self):
        """Build merged system capabilities and persist them under hidden configs."""
        state_implementations_used = {}
        behaviors_used = {}

        print(f"Capabilities file path '{self.capabilities_path}'", flush=True)
        if not os.path.isfile(self.capabilities_path):
            print(f"defined capabilities_path '{self.capabilities_path}' does not exist!")
            raise FileNotFoundError(
                f"defined capabilities_path '{self.capabilities_path}' does not exist!"
            )

        with open(self.capabilities_path) as stream:
            params = yaml.safe_load(stream)

        if not isinstance(params, dict):
            raise TypeError(
                (
                    f"Capabilities file '{self.capabilities_path}' must contain a "
                    f'top-level mapping, got {type(params).__name__}.'
                )
            )

        for key in params:
            if key not in (
                'name',
                'variable_mappings',
                'state_outcome_mappings',
                'sm_outcome_mappings',
                'transition_outcomes',
                'memory',
                'capabilities',
            ):
                raise ValueError(f"Invalid key '{key}' in '{self.capabilities_path}'")

        if 'capabilities' not in params:
            raise ValueError(
                (
                    f"Capabilities file '{self.capabilities_path}' is missing "
                    "required 'capabilities' mapping."
                )
            )
        if not isinstance(params['capabilities'], dict):
            raise TypeError(
                (
                    f"Capabilities file '{self.capabilities_path}' field "
                    f"'capabilities' must be a mapping, got "
                    f"{type(params['capabilities']).__name__}."
                )
            )

        allowed_mapping_keys = (
            'state_outcome_mappings',
            'sm_outcome_mappings',
            'transition_outcomes',
        )
        if self.state_mappings:
            for key in self.state_mappings:
                if key not in allowed_mapping_keys:
                    raise ValueError(
                        f"Invalid state mapping key '{key}'. Expected one of "
                        f'{allowed_mapping_keys}.'
                    )

        transition_outcomes = set()
        if self.state_mappings:
            transition_outcomes.update(self.state_mappings.get('transition_outcomes', []))
        transition_outcomes.update(params.get('transition_outcomes', []))
        self.validate_transition_outcome_tags(sorted(transition_outcomes))

        try:
            capabilities_name = params.get('name')
            if capabilities_name is None:
                base_name = os.path.basename(self.capabilities_path)
                capabilities_name = os.path.splitext(base_name)[0]

            if self.system_name != capabilities_name:
                print(
                    (
                        '\033[31mWARNING: System capabilities name '
                        f"'{self.system_name}' does not match name from "
                        f"capabilities file '{capabilities_name}'"
                    ),
                    flush=True,
                )

            system_capabilities = {
                'name': capabilities_name,
                'state_outcome_mappings': {},
                'sm_outcome_mappings': {},
                'transition_outcomes': [],
            }
            if self.state_mappings:
                for key, value in self.state_mappings.items():
                    if isinstance(value, dict) and isinstance(
                        system_capabilities[key], dict
                    ):
                        system_capabilities[key].update(value)
                    elif isinstance(value, list) and isinstance(
                        system_capabilities[key], list
                    ):
                        system_capabilities[key] += value
                    else:
                        raise TypeError(f"Invalid {type(value)} for '{key}'")
                    print(f"Added '{key}' to system capabilities via mappings")
                    print(f'            {system_capabilities[key]}')

            if 'sm_outcome_mappings' in params and params['sm_outcome_mappings']:
                mappings = params['sm_outcome_mappings']
                print(f'    Adding {len(mappings)} custom SM outcome mappings:')
                for key, value in mappings.items():
                    print(f'    - {key}:{value}')
                    system_capabilities['sm_outcome_mappings'][key] = value

                print(
                    'Final sm_outcome_mappings '
                    f"{system_capabilities['sm_outcome_mappings']}"
                )

            if 'state_outcome_mappings' in params and params['state_outcome_mappings']:
                mappings = params['state_outcome_mappings']
                print(f'    Adding {len(mappings)} custom state outcome mappings:')
                for key, value in mappings.items():
                    print(f'    - {key}:{value}')
                    system_capabilities['state_outcome_mappings'][key] = value

                print(
                    'Final state_outcome_mappings '
                    f"{system_capabilities['state_outcome_mappings']}"
                )

            if 'transition_outcomes' in params:
                previous_count = len(system_capabilities['transition_outcomes'])
                outcomes = set(params['transition_outcomes'])
                outcomes.update(system_capabilities['transition_outcomes'])
                system_capabilities['transition_outcomes'] = sorted(outcomes)
                added_count = len(system_capabilities['transition_outcomes']) - previous_count
                print(

                        f'    Added {added_count} new custom transition outcomes='
                        f"{system_capabilities['transition_outcomes']}"

                )

            self.validate_transition_outcome_tags(
                system_capabilities['transition_outcomes']
            )

            capabilities = params['capabilities']

            print(
                (
                    '\033[32m ------ FlexBE Capability Loader w/ '
                    f'{len(capabilities)} capabilities ------ \033[0m'
                ),
                flush=True,
            )
            for abstraction_name in capabilities:
                for key in capabilities[abstraction_name]:
                    if key not in (
                        'autonomy',
                        'interface',
                        'parameters',
                        'preconditions',
                        'postconditions',
                        'transition_relation',
                        'userdata_in',
                        'userdata_out',
                    ):
                        raise ValueError(
                            f"Invalid key '{key}' in '{abstraction_name}' capabilities"
                        )

                interface = capabilities[abstraction_name]['interface']
                is_state_interface = interface in self.workspace_data['states']
                is_behavior_interface = interface in self.workspace_data['behaviors']
                if is_state_interface and is_behavior_interface:
                    msg = (
                        f"\033[31mERROR: Interface '{interface}' for "
                        f"'{abstraction_name}' matches both a FlexBE state and "
                        'a FlexBE behavior.\n'
                        '  Prepend with <package_name>/<interface> in '
                        'capabilities file.\033[0m'
                    )
                    print(msg)
                    raise CapabilityInterfaceAmbiguityError(msg)

                if is_state_interface:
                    if interface not in state_implementations_used:
                        interface_data = self.workspace_data['states'][interface]
                        check_name = f"{interface_data['package']}/{interface}"
                        if check_name in self.workspace_data['states']:
                            msg = (
                                f"\033[31mERROR: This interface '{interface}' occurs in "
                                'multiple packages!\n'
                                '  Prepend with <package_name>/<interface> in '
                                'capabilities file.\033[0m'
                            )
                            print(msg)
                            raise ValueError(msg)

                        state_implementations_used[interface] = {
                            'name': interface,
                            'interface': dict(self.workspace_data['states'][interface]),
                            'discrete_abstractions': [],
                        }

                    state_implementations_used[interface]['discrete_abstractions'].append(
                        abstraction_name
                    )

                    state_info = self.workspace_data['states'][
                        capabilities[abstraction_name]['interface']
                    ]
                    capabilities[abstraction_name]['state'] = deepcopy(state_info)
                    if capabilities[abstraction_name]['state']['name'] == 'OperatorDecisionState':
                        print(

                                'Special handling of OperatorDecisionState '
                                f"'{abstraction_name}' to handle parameterized outcomes!"

                        )
                        try:
                            capability = capabilities[abstraction_name]
                            out_mappings = system_capabilities['state_outcome_mappings']
                            outcomes = capability['state']['outcomes']
                            for out in capability['parameters']['outcomes']:
                                outcomes[out] = {'remapping': out_mappings[out]}
                        except Exception as exc:
                            print(
                                (
                                    '\033[31mFailed to process outcomes for '
                                    f"OperatorDecisionState '{abstraction_name}':\n"
                                    f'   {exc}\033[0m'
                                ),
                                flush=True,
                            )
                            raise ValueError(
                                f"Error in OperatorDecisionState '{abstraction_name}'"
                            ) from exc

                    self.validate_capability_state(
                        abstraction_name,
                        capabilities[abstraction_name],
                        state_info,
                    )
                    self.validate_capability_userdata(
                        abstraction_name,
                        capabilities[abstraction_name],
                        state_info,
                    )

                if is_behavior_interface:
                    if interface not in behaviors_used:
                        interface_data = self.workspace_data['behaviors'][interface]
                        check_name = f"{interface_data['package']}/{interface}"
                        if check_name in self.workspace_data['behaviors']:
                            msg = (
                                f"\033[31mERROR: This interface '{interface}' occurs in "
                                'multiple packages!\n'
                                '  Prepend with <package_name>/<interface> in '
                                'capabilities file.\033[0m'
                            )
                            print(msg)
                            raise ValueError(msg)

                        behaviors_used[interface] = {
                            'name': interface,
                            'interface': dict(self.workspace_data['behaviors'][interface]),
                            'discrete_abstractions': [],
                        }

                    behaviors_used[interface]['discrete_abstractions'].append(
                        abstraction_name
                    )

                    behavior_info = self.workspace_data['behaviors'][
                        capabilities[abstraction_name]['interface']
                    ]
                    capabilities[abstraction_name]['behavior'] = behavior_info
                    self.validate_capability_userdata(
                        abstraction_name,
                        capabilities[abstraction_name],
                        behavior_info,
                    )
                else:
                    if 'state' not in capabilities[abstraction_name]:
                        print(

                                f"\033[31m Interface '{interface}' for "
                                f"'{abstraction_name}' is NOT known in this "
                                'workspace!\033[0m'

                        )
                        raise ValueError(
                            f"Interface '{interface}' for '{abstraction_name}' "
                            'is NOT known in this workspace!'
                        )

            file_dir = os.path.join(self.synthesis_home, self.system_name, 'configs')
            if not os.path.exists(file_dir):
                os.makedirs(file_dir)
            file_target = os.path.join(
                file_dir,
                self.system_name + fpths._SYSTEM_CAPABILITIES_CONFIG_EXT,
            )
            print(f"Writing system capabilities to \n    '{file_target}' ...", flush=True)

            system_capabilities['capabilities'] = capabilities
            for key, value in params.items():
                if key not in (
                    'name',
                    'capabilities',
                    'state_outcome_mappings',
                    'sm_outcome_mappings',
                    'transition_outcomes',
                ):
                    print(f"  Adding '{key}' to system_capabilities")
                    system_capabilities[key] = value

            with open(file_target, 'w') as target:
                target.write(
                    yaml.dump(
                        system_capabilities,
                        Dumper=CapabilityYamlDumper,
                        default_flow_style=False,
                    )
                )

            print('\033[32m ======= Returning from Capability Loader =======\033[0m', flush=True)
            return [system_capabilities, state_implementations_used, behaviors_used]
        except Exception as exc:
            print(
                (
                    f"failed to load capabilities from '{self.capabilities_path}'!\n"
                    f'    error: {exc}'
                ),
                flush=True,
            )
            if isinstance(
                exc,
                (UserdataValidationError, CapabilityInterfaceAmbiguityError),
            ):
                raise
            raise ValueError('No system capabilities were able to be loaded') from exc

    def validate_capability_state(self, abstraction_name, capability, state_info):
        """Validate provided parameters against workspace state interface."""
        if 'parameters' in capability:
            for key, _ in capability['parameters'].items():
                if key not in state_info['parameters']:
                    raise ValueError(
                        f"'{abstraction_name}' parameter '{key}' "
                        f"not defined in '{state_info['name']}'"
                    )

    def validate_capability_userdata(self, abstraction_name, capability, state_info):
        """Validate capability userdata keys against the workspace state interface."""
        for userdata_key in ('userdata_in', 'userdata_out'):
            if userdata_key not in capability:
                continue

            if not isinstance(capability[userdata_key], dict):
                raise UserdataValidationError(
                    (
                        f"'{abstraction_name}' {userdata_key} must be a mapping, "
                        f'not {type(capability[userdata_key]).__name__}'
                    )
                )

            valid_userdata = state_info.get(userdata_key, {})
            for key in capability[userdata_key]:
                if key not in valid_userdata:
                    raise UserdataValidationError(
                        (
                            f"'{abstraction_name}' {userdata_key} '{key}' "
                            f"not defined in '{state_info['name']}'"
                        )
                    )

    def validate_transition_outcome_tags(self, transition_outcomes):
        """Validate generated outcome tags are unique for discrete abstractions."""
        outcome_tags = {}
        for outcome in transition_outcomes:
            normalized_outcome = str(outcome).strip()
            if not normalized_outcome:
                raise ValueError('Transition outcomes must not be empty.')

            outcome_tag = normalized_outcome[0]
            if outcome_tag in outcome_tags:
                raise ValueError(
                    'Transition outcomes must have unique first-character tags: '
                    f"'{outcome_tags[outcome_tag]}' and '{normalized_outcome}' "
                    f"both use '{outcome_tag}'."
                )
            outcome_tags[outcome_tag] = normalized_outcome


def main(inputs):
    """Create capability loader preprocessor from pipeline inputs."""
    return CapabilityLoader(
        name='CapabilityLoader',
        system_name=inputs[0],
        capabilities_path=inputs[1],
        workspace_data=inputs[2],
        state_mappings=inputs[3],
    )


if __name__ == '__main__':
    from ament_index_python.packages import get_package_share_directory
    from flexbe_synthesis_generic.preprocesses.workspace_parser import main as wp_main

    package_path = get_package_share_directory('flexbe_synthesis_generic')
    print(package_path)

    capability_path = os.path.join(
        package_path,
        'example',
        'capabilities',
        'vending_capabilities.yaml',
    )

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
    capability_loader = main(['vending_demo', capability_path, outputs[0], state_mappings])
    outputs = capability_loader.preprocess()
    print('Returned capabilities: ')
    for output in outputs:
        print(yaml.dump(output, default_flow_style=False))
        print(30 * '-', flush=True)
