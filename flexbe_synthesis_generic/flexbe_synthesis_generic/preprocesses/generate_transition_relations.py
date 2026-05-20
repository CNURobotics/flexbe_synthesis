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

from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_core.base_preprocess import BasePreProcess
import yaml


def extract_variables(condition):
    """Extract basic variable names from a boolean condition string."""
    condition = condition.strip()
    if condition == '':
        return []

    if condition[0] == '(':
        # Find the closing paren that matches the opening one.
        depth = 0
        for i, ch in enumerate(condition):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    inner = condition[1:i]
                    rest = condition[i + 1:].strip()
                    if not rest:
                        # Outer parens wrap the whole expression — unwrap and recurse.
                        return extract_variables(inner)
                    # The leading parens cover only the left side of a larger
                    # expression, e.g. ``(a|b)&c``. Leave ``condition`` intact
                    # and let the operator split below recurse into both sides.
                    break

    if condition[0] == '!':
        return extract_variables(condition[1:])

    if '&' in condition:
        variables = []
        for cond in condition.split('&'):
            variables.extend(extract_variables(cond))
        return variables

    if '|' in condition:
        variables = []
        for cond in condition.split('|'):
            variables.extend(extract_variables(cond))
        return variables

    if '!=' in condition:
        return extract_variables(condition.split('!=')[0])

    if '=' in condition:
        return extract_variables(condition.split('=')[0])

    has_brackets = '(' in condition or '[' in condition
    condition = (
        condition.replace('(', '')
        .replace(')', '')
        .replace('[', '')
        .replace(']', '')
    ).strip()
    if has_brackets:
        print(
            f'\033[33mWarning: extract_variables could not fully resolve a bracketed '
            f"fragment; results may be incomplete: '{condition}'\033[0m",
            flush=True,
        )
    return [condition] if condition else []


class GenerateTransitionRelations(BasePreProcess):
    """Generate transition relation and pre/post-condition YAML for capabilities."""

    system_name: str
    system_capabilities: dict
    state_implementations_used: dict
    behaviors_used: dict
    workspace_data: dict
    verbose: bool = False

    def preprocess(self):
        """Process capability pre/postconditions into transition-relations config."""
        file_dir = os.path.join(self.synthesis_home, self.system_name, 'configs')
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)

        file_target = os.path.join(
            file_dir,
            self.system_name + fpths._TRANSITION_RELATIONS_CONFIG_EXT,
        )
        print(
            (
                'Processing transition relations from capabilities for '
                f"'{self.system_name}' ..."
            ),
            flush=True,
        )

        capabilities = self.system_capabilities['capabilities']
        sm_outcome_mappings = self.system_capabilities['sm_outcome_mappings']

        needed_in_preconditions = {}
        provided_postconditions = {}
        potential_system_transitions = {}
        transition_relations = {}
        system_preconditions = {}
        system_postconditions = {}
        implementations_used = {}

        for capability_name in capabilities:
            print(f"Processing capabilities for '{capability_name}' ...")
            interface = capabilities[capability_name]['interface']
            if interface not in implementations_used:
                implementations_used[interface] = [capability_name]
            else:
                implementations_used[interface].append(capability_name)

            remapped_outcomes = set()
            cap = capabilities[capability_name]
            if 'state' in cap:
                interface_outcomes = cap['state']['outcomes']
            elif 'behavior' in cap:
                interface_outcomes = cap['behavior']['outcomes']
            else:
                raise KeyError(
                    f"Capability '{capability_name}' has neither 'state' nor 'behavior' "
                    'interface data'
                )
            for _, out_dict in interface_outcomes.items():
                remapped_outcomes.add(out_dict['remapping'])
            for remapped_outcome in remapped_outcomes:
                outcome_key = f'{capability_name}_{remapped_outcome[0]}'
                if outcome_key not in provided_postconditions:
                    provided_postconditions[outcome_key] = set()
                provided_postconditions[outcome_key].add(capability_name)

            if 'transition_relation' in capabilities[capability_name]:
                transitions = capabilities[capability_name]['transition_relation']
                if isinstance(transitions, list):
                    print(
                        (
                            f"WARNING: capability '{capability_name}' uses a bare "
                            "'transition_relation' list; treating it as the "
                            "'completed' outcome. Use an outcome-keyed mapping "
                            'for non-completed transitions.'
                        ),
                        flush=True,
                    )
                    transitions = {'completed': transitions}
                transition_relations[capability_name] = transitions

                for outcome, postconds_list in transitions.items():
                    if not isinstance(postconds_list, list):
                        raise TypeError(
                            f'Transitions must be a list, not {type(postconds_list)}'
                        )
                    cap_outcome = f'{capability_name}_{outcome[0]}'
                    for postcond in postconds_list:
                        postcondition_key = postcond.replace('@', '')
                        if postcond in capabilities:
                            if cap_outcome in provided_postconditions:
                                provided_postconditions[cap_outcome].add(postcond)
                            else:
                                provided_postconditions[cap_outcome] = {postcond}
                        else:
                            if cap_outcome in provided_postconditions:
                                provided_postconditions[cap_outcome].add(postcondition_key)
                            else:
                                provided_postconditions[cap_outcome] = {postcondition_key}

                            if postcondition_key in provided_postconditions:
                                provided_postconditions[postcondition_key].add(
                                    capability_name
                                )
                            else:
                                provided_postconditions[postcondition_key] = {
                                    capability_name
                                }

                        if capability_name in potential_system_transitions:
                            potential_system_transitions[capability_name].add(postcond)
                        else:
                            potential_system_transitions[capability_name] = {postcond}

            if 'preconditions' in capabilities[capability_name]:
                for precond in capabilities[capability_name]['preconditions']:
                    precond = precond.strip()
                    # TODO: remove guard once Slugs backend supports composite conditions.
                    if any(ch in precond for ch in '&|'):
                        raise ValueError(
                            f"Composite precondition for '{capability_name}': '{precond}' — "
                            'Boolean formulas in preconditions are not yet supported. '
                            'Use only single-variable conditions.'
                        )

                    if capability_name in system_preconditions:
                        system_preconditions[capability_name].add(precond)
                    else:
                        system_preconditions[capability_name] = {precond}

                    if precond in potential_system_transitions:
                        potential_system_transitions[precond].add(capability_name)
                    else:
                        if precond in capabilities:
                            potential_system_transitions[precond] = {capability_name}
                        else:
                            if precond in provided_postconditions:
                                potential_system_transitions[precond] = set()
                                potential_system_transitions[precond].update(
                                    provided_postconditions[precond]
                                )
                            else:
                                variables = extract_variables(precond)
                                if self.verbose:
                                    print(f" precond '{precond}' --> {variables}")
                                if variables:
                                    for variable in variables:
                                        if variable in provided_postconditions:
                                            if variable not in potential_system_transitions:
                                                potential_system_transitions[variable] = set()
                                            potential_system_transitions[variable].add(
                                                capability_name
                                            )
                                        else:
                                            if variable in needed_in_preconditions:
                                                needed_in_preconditions[variable].add(
                                                    capability_name
                                                )
                                            else:
                                                needed_in_preconditions[variable] = {
                                                    capability_name
                                                }

                                if precond in needed_in_preconditions:
                                    needed_in_preconditions[precond].add(capability_name)
                                else:
                                    needed_in_preconditions[precond] = {capability_name}

            if 'postconditions' in capabilities[capability_name]:
                postconds = capabilities[capability_name]['postconditions']
                if not isinstance(postconds, dict):
                    print(

                            f"'{capability_name}' - Assuming 'completed' outcome "
                            f'for post condition {postconds}'

                    )
                    postconds = {'completed': postconds}

                for outcome, postconds_list in postconds.items():
                    if not isinstance(postconds_list, list):
                        raise TypeError(
                            f'Post conditions must be a list, not {type(postconds_list)}'
                        )
                    for postcond in postconds_list:
                        postcond = postcond.strip()
                        # TODO: remove guard once Slugs backend supports composite conditions.
                        if any(ch in postcond for ch in '&|'):
                            raise ValueError(
                                f"Composite postcondition for '{capability_name}': '{postcond}' — "
                                'Boolean formulas in postconditions are not yet supported. '
                                'Use only single-variable conditions.'
                            )

                        if capability_name in system_postconditions:
                            if outcome in system_postconditions[capability_name]:
                                system_postconditions[capability_name][outcome].add(postcond)
                            else:
                                system_postconditions[capability_name][outcome] = {postcond}
                        else:
                            system_postconditions[capability_name] = {outcome: {postcond}}

                        if postcond in provided_postconditions:
                            provided_postconditions[postcond].add(capability_name)
                        else:
                            provided_postconditions[postcond] = {capability_name}

                        variables = extract_variables(postcond)
                        if self.verbose:
                            print(f" postcond '{postcond}' --> {variables}")
                        for variable in variables:
                            if variable in provided_postconditions:
                                provided_postconditions[variable].add(capability_name)
                            else:
                                provided_postconditions[variable] = {capability_name}

                            if variable in needed_in_preconditions and variable != capability_name:
                                if self.verbose:
                                    print(f"We needed '{variable}' earlier")
                                if variable not in potential_system_transitions:
                                    potential_system_transitions[variable] = {capability_name}
                                potential_system_transitions[variable].update(
                                    needed_in_preconditions.pop(variable)
                                )

                        if capability_name in potential_system_transitions:
                            if outcome not in potential_system_transitions[capability_name]:
                                if self.verbose:
                                    print(
                                        f"'{capability_name}' outcome '{outcome}' not in "
                                        'potential_system_transitions'
                                    )

                            if postcond in capabilities:
                                potential_system_transitions[capability_name].add(postcond)

                            if postcond in needed_in_preconditions:
                                potential_system_transitions[capability_name].update(
                                    needed_in_preconditions.pop(postcond)
                                )
                        else:
                            potential_system_transitions[capability_name] = set()
                            if postcond in capabilities:
                                potential_system_transitions[capability_name].add(postcond)

                            if postcond in needed_in_preconditions:
                                potential_system_transitions[capability_name].update(
                                    needed_in_preconditions.pop(postcond)
                                )
                                if self.verbose:
                                    print(
                                        f"\033[33m  '{capability_name}':'{outcome}' is "
                                        f"providing '{postcond}' needed by preconditions"
                                        '\033[0m'
                                    )
                                    print(potential_system_transitions[capability_name])

        if self.verbose:
            print('  Specified Transitions:')
            for key in transition_relations:
                print(f'    {key}: {transition_relations[key]}', flush=True)
            print(30 * '-')

            print('  System transitions:')
            for key in potential_system_transitions:
                print(f'    {key}: {potential_system_transitions[key]}', flush=True)
            print(30 * '-')

            print('  Provided Postconditions:')
            for key in provided_postconditions:
                print(f'    {key}: {provided_postconditions[key]}', flush=True)
            print(30 * '-')

        if needed_in_preconditions:
            needed_keys = list(needed_in_preconditions.keys())
            for key in needed_keys:
                if key in provided_postconditions:
                    if self.verbose:
                        print(
                            f"'{provided_postconditions[key]}' is providing '{key}' "
                            f'needed by {needed_in_preconditions[key]}'
                        )
                    needed_in_preconditions.pop(key)
                else:
                    variables = extract_variables(key)
                    provided = True
                    for variable in variables:
                        if variable not in provided_postconditions:
                            print(

                                    f"'{variable}' is not provided (needed by '{key}' - "
                                    f'{needed_in_preconditions[key]})'

                            )
                            provided = False
                    if provided:
                        needed_in_preconditions.pop(key)

            if needed_in_preconditions:
                print('\033[31mThe following preconditions are currently unmet:')
                for key in needed_in_preconditions:
                    print(
                        f'\033[31m    {key}: {needed_in_preconditions[key]}\033[0m',
                        flush=True,
                    )
                print(30 * '-')

        print(
            f"\033[32mWriting transition relations to \n    '{file_target}' ...\033[0m",
            flush=True,
        )
        with open(file_target, 'w') as target:
            transition_config = {
                'name': self.system_name,
                'transition_relations': {},
                'action_preconditions': {},
                'action_postconditions': {},
            }
            for capability_name in capabilities:
                if capability_name in transition_relations:
                    transition_config['transition_relations'][capability_name] = {}
                    for outcome in transition_relations[capability_name]:
                        valid_transitions = []
                        for transition in transition_relations[capability_name][outcome]:
                            transition_target = self._transition_target_name(transition)
                            if transition_target is None:
                                continue

                            if (
                                transition_target in capabilities
                                or transition_target in sm_outcome_mappings
                            ):
                                valid_transitions.append(transition)
                            else:
                                raise ValueError(
                                    f"Transition relation for '{capability_name}' "
                                    f"outcome '{outcome}' targets unknown capability or "
                                    f"SM outcome '{transition}'. Use a defined "
                                    'capability/outcome, or prefix variable postconditions '
                                    "with '@'."
                                )
                        transition_config['transition_relations'][capability_name][
                            outcome
                        ] = valid_transitions
                else:
                    transition_config['transition_relations'][capability_name] = []

            for capability_name in capabilities:
                if capability_name in system_preconditions:
                    transition_config['action_preconditions'][capability_name] = sorted(
                        system_preconditions[capability_name]
                    )
                else:
                    transition_config['action_preconditions'][capability_name] = []

            for capability_name in capabilities:
                if capability_name in system_postconditions:
                    transition_config['action_postconditions'][capability_name] = {}
                    for outcome in system_postconditions[capability_name]:
                        transition_config['action_postconditions'][capability_name][
                            outcome
                        ] = sorted(system_postconditions[capability_name][outcome])
                else:
                    transition_config['action_postconditions'][capability_name] = []

            if needed_in_preconditions:
                transition_config['unmet_needs'] = sorted(needed_in_preconditions)

            yaml.safe_dump(transition_config, target, sort_keys=False)

        return [
            self.system_capabilities,
            transition_relations,
            system_preconditions,
            system_postconditions,
            self.state_implementations_used,
            self.behaviors_used,
        ]

    @staticmethod
    def _transition_target_name(transition):
        """Return normalized transition target, or None for variable postconditions."""
        if not isinstance(transition, str):
            raise TypeError(f'Transition target must be a string, not {type(transition)}')

        stripped = transition.strip()
        if stripped.startswith('@'):
            return None
        if stripped.startswith('!'):
            return stripped[1:].strip()
        return stripped


def main(inputs):
    """Create GenerateTransitionRelations preprocess from pipeline inputs."""
    system_name = inputs[0]
    system_capabilities = inputs[1]
    state_implementations_used = inputs[2]
    behaviors_used = inputs[3]
    workspace_data = inputs[4]
    return GenerateTransitionRelations(
        name='Generate Transition Relations',
        system_name=system_name,
        system_capabilities=system_capabilities,
        state_implementations_used=state_implementations_used,
        behaviors_used=behaviors_used,
        workspace_data=workspace_data,
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

    parser = wp_main([{'state_outcome_mappings': state_mappings}, 'test'])
    outputs = parser.preprocess()

    print(f"Try to load capabilities from '{capability_path}' ...", flush=True)
    capability_loader = cl_main([system_name, capability_path, outputs[0], state_mappings])
    outputs = capability_loader.preprocess()
    print(f"  {outputs[0]['name']} capabilities with {len(outputs)} outputs")
    print('Try to generate transition relation ...', flush=True)
    gen_trans = main([outputs[0]['name']] + outputs + [{}])
    outputs = gen_trans.preprocess()
    print('Wrote transition relation file.')
