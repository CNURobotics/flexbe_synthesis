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

from flexbe_msgs.msg import OutcomeCondition, StateInstantiation
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_util import (
    clean_variable,
    new_si,
)


class ConcurrentStateGenerator:
    """Generate `StateInstantiation` instances for concurrent states."""

    def __init__(self, name, verbose=False):
        """Initialize the generator for a concurrent state with the given name."""
        self.name = name
        self.verbose = verbose
        self.internal_states = {}
        self.internal_outcomes = []
        self.internal_transitions = []
        self.internal_outcome_maps = []
        self.outcome_to_autonomy_list = {}
        self.internal_userdata_keys = []
        self.internal_userdata_remapping = []

    def add_internal_state(self, label, class_decl):
        """Add an internal state declaration to this concurrent state."""
        clean_label = clean_variable(label)
        if clean_label not in self.internal_states:
            self.internal_states[clean_label] = class_decl

    def add_internal_userdata(self, userdata_remapping):
        """Add userdata_keys and userdata_remapping."""
        if not userdata_remapping:
            return

        ordered_keys = list(userdata_remapping.keys())
        ordered_mapping = [userdata_remapping[key] for key in ordered_keys]

        self.internal_userdata_keys.extend(ordered_keys)
        self.internal_userdata_remapping.extend(ordered_mapping)

    def add_internal_outcome_and_transition(self, outcomes, transition, autonomy_list):
        """Add internal outcomes, transitions, and autonomy values."""
        if isinstance(outcomes, str):
            outcomes = [outcomes]
        for outcome in outcomes:
            if outcome not in self.internal_outcomes:
                if self.verbose:
                    print(
                        f"Adding '{outcome}' to internals with trans'{transition}' "
                        f'and {autonomy_list}'
                    )
                self.internal_outcomes.append(outcome)
                self.internal_transitions.append(transition)

                if outcome in self.outcome_to_autonomy_list:
                    self.outcome_to_autonomy_list[outcome] += autonomy_list
                else:
                    self.outcome_to_autonomy_list[outcome] = autonomy_list

    def clean_out_map(self, out_map):
        """Normalize outcome-map labels for generated concurrent states."""
        if self.verbose:
            print(f'ConcurrentStateGenerator: input out map = {out_map}')
        clean_out_map = {'outcome': out_map['outcome']}

        clean_conditions = {
            clean_variable(key): value for key, value in out_map['condition'].items()
        }
        clean_out_map['condition'] = clean_conditions

        if self.verbose:
            print(f'ConcurrentStateGenerator: clean out map = {clean_out_map}')
        return clean_out_map

    def add_internal_outcome_maps(self, out_map):
        """Add a cleaned outcome map if it is not already present."""
        clean_out_map = self.clean_out_map(out_map)
        if clean_out_map not in self.internal_outcome_maps:
            self.internal_outcome_maps.append(clean_out_map)
        if self.verbose:
            print(f'     internal outcome map {self.internal_outcome_maps}', flush=True)

    def _resolve_parameters(self, class_decl, state):
        """Resolve @ and * parameter prefixes against automaton state values."""
        parameters = {}
        for key, value in class_decl['parameters'].items():
            if self.verbose:
                print(f" Processing '{self.name}' - parameter '{key}' <{value}>")

            if isinstance(value, str) and len(value) > 1 and value[0] == '@':
                val_str = value[1:]
                if state is not None and val_str in state.output_values:
                    value = state.output_values[val_str]
                    print(
                        f"\033[32m  '{self.name}' - got mapped value for '{val_str}' "
                        f'= <{value}> from OUTPUTS.\033[0m'
                    )
                elif state is not None and val_str in state.input_values:
                    value = state.input_values[val_str]
                    print(
                        f"\033[32m  '{self.name}' - got mapped value for '{val_str}' "
                        f'= <{value}> from INPUTS.\033[0m'
                    )
                else:
                    print(f"\033[31mUnknown mapping for '{val_str}'!\033[0m", flush=True)

            if isinstance(value, str):
                if len(value) > 1:
                    if value[0] == '*':
                        print(
                            f"\033[32m treat key'{key}' as variable '{value}' "
                            f'= <{value[1:]}>\033[0m'
                        )
                        value = value[1:]
                    elif value in ('None', "'None'", '"None"'):
                        value = 'None'
                    elif 'self.' in value:
                        print(
                            f"   self reference in '{self.name}' with parameter "
                            f'<{value}> ({type(value)})',
                            flush=True,
                        )
                    elif value[0] not in ("'", '"'):
                        if "'" in value or '"' in value:
                            value = f"'''{value}'''"
                        else:
                            value = f"'{value}'"
                else:
                    value = "''"

                if self.verbose:
                    print(f" --> Processing '{self.name}' - parameter '{key}' <{value}>")
            elif isinstance(value, list):
                types = [type(val) for val in value]
                if not all(typ in (int, float, str) for typ in types):
                    print(
                        f'\033[31mUnexpected type in parameter list <{value}> ({types}>\n'
                        '   not int, float, or str!\033[0m',
                        flush=True,
                    )
                value = str(value)
            elif value is None:
                value = 'None'
            else:
                if not isinstance(value, (int, float)):
                    print(
                        f"\033[31m  Unexpected value type for '{key}' "
                        f'= {type(value)} <{value}>\033[0m'
                    )
                value = str(value)

            parameters[key] = value
        return parameters

    def gen_single(self, state):
        """Generate state instantiation for the single-state degenerate case."""
        label, decl = list(self.internal_states.items())[0]

        transitions = self.internal_transitions
        if self.verbose:
            print(
                f"    ConcurrentStateGen: gen_single '{label}' - {transitions}",
                flush=True,
            )
            print(f'        outcome map {self.internal_outcome_maps}', flush=True)
            print(f'  internal outcomes {self.internal_outcomes}')
            print(f'      autonomy list {self.outcome_to_autonomy_list}', flush=True)

        autonomy = [
            max(self.outcome_to_autonomy_list[outcome])
            for outcome in self.internal_outcomes
        ]
        if self.verbose:
            print(f'   autonomy {autonomy}', flush=True)
            print(
                f'       userdata : keys={self.internal_userdata_keys} '
                f'remappings={self.internal_userdata_remapping}'
            )
        userdata_keys = self.internal_userdata_keys if any(self.internal_userdata_keys) else []
        userdata_remapping = (
            self.internal_userdata_remapping if any(self.internal_userdata_remapping) else []
        )

        state_class = decl['name']
        behavior_class = decl.get('behavior_class', '')
        parameters = self._resolve_parameters(decl, state)

        if self.verbose:
            print(f'    decl[{state_class}]=<{decl}>')
        return new_si(
            '/' + self.name,
            state_class,
            behavior_class,
            self.internal_outcomes,
            self.internal_transitions,
            None,
            parameters,
            autonomy=autonomy,
            userdata_keys=userdata_keys,
            userdata_remapping=userdata_remapping,
            verbose=self.verbose,
        )

    def gen(self, state):
        """
        Generate a list of StateInstantiations for this concurrent state.

        Returns ``[single_si]`` for one internal state, or
        ``[container_si, sub_si_1, ...]`` for multiple states where the container
        uses ``CLASS_CONCURRENCY`` with ``cond_outcome``/``cond_transition``.
        """
        if not self.is_concurrent():
            return [self.gen_single(state)]

        if self.verbose:
            print(f"-- Generating a ConcurrencyContainer for '{self.name}' ...", flush=True)

        autonomy = [
            max(self.outcome_to_autonomy_list[outcome])
            for outcome in self.internal_outcomes
        ]
        userdata_keys = self.internal_userdata_keys if any(self.internal_userdata_keys) else []
        userdata_remapping = (
            self.internal_userdata_remapping if any(self.internal_userdata_remapping) else []
        )

        container_si = new_si(
            '/' + self.name,
            StateInstantiation.CLASS_CONCURRENCY,
            '',
            self.internal_outcomes,
            self.internal_transitions,
            None,
            {},
            autonomy=autonomy,
            userdata_keys=userdata_keys,
            userdata_remapping=userdata_remapping,
            verbose=self.verbose,
        )
        container_si.cond_outcome = [om['outcome'] for om in self.internal_outcome_maps]
        container_si.cond_transition = [
            OutcomeCondition(
                state_name=list(om['condition'].keys()),
                state_outcome=list(om['condition'].values()),
            )
            for om in self.internal_outcome_maps
        ]

        # Collect the outcomes each sub-state can emit, derived from the condition maps.
        sub_state_outcomes: dict[str, list] = {label: [] for label in self.internal_states}
        for om in self.internal_outcome_maps:
            for label, outcome in om['condition'].items():
                if label in sub_state_outcomes and outcome not in sub_state_outcomes[label]:
                    sub_state_outcomes[label].append(outcome)

        result = [container_si]
        for label, class_decl in self.internal_states.items():
            parameters = self._resolve_parameters(class_decl, state)
            sub_si = new_si(
                '/' + self.name + '/' + label,
                class_decl['name'],
                class_decl.get('behavior_class', ''),
                sub_state_outcomes.get(label, []),
                [],
                None,
                parameters,
                autonomy=[],
                verbose=self.verbose,
            )
            result.append(sub_si)

        return result

    def is_concurrent(self):
        """Return whether this generator creates a concurrent (not single) state."""
        return len(self.internal_states) > 1
