#!/usr/bin/env python

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

"""Helpers for generating FlexBE state machines from synthesized automata."""

import os
import re
import traceback

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.slugs_automaton import SlugsAutomaton
from flexbe_synthesis_slugs.helpers.sm_gen.concurrent_state_generator import (
    ConcurrentStateGenerator,
)
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_config import SMGenConfig
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_error import SMGenError
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_util import clean_variable, new_si
import yaml

INIT_STATE_NAME = 'ROOT_OF_INIT_STATES'
BOOTSTRAP_ACTION = 'begin_game_a'
BOOTSTRAP_OUTCOME_PREFIX = 'begin_game_'


class SMGenerationHelpers:
    """Utilities for converting synthesized automata into state instantiations."""

    @staticmethod
    def _validate_path_component(value, field_name):
        """Validate names used as hidden artifact path components."""
        if not isinstance(value, str):
            raise ValueError(f'Invalid {field_name}: expected string, got {type(value)}')

        if value in {'', '.', '..'}:
            raise ValueError(f"Invalid {field_name}: '{value}' is not a safe path name")

        if os.path.basename(value) != value:
            raise ValueError(f"Invalid {field_name}: '{value}' must not contain path separators")

        if not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
            raise ValueError(
                f"Invalid {field_name}: '{value}' contains unsupported characters"
            )

        return value

    def modify_names(self, sa, parsed_var=None, index_to_action=None):
        """
        Make state names human-readable by appending active output labels.

        For explicit boolean activations (e.g. ``bd_a``) the label comes from
        ``state.output_variables``.  For the parsed-integer encoding
        (``capability`` / ``move_action``) pass the variable name and
        index→action mapping so that ``capability=2`` renders as ``_gr`` rather
        than leaving the state unnamed.
        """
        for state in sa.automaton:
            state.name = str(state.name)

        old_name_to_new_name = {}
        for state in sa.automaton:
            new_name = state.name
            for out_var in state.output_variables:
                new_name += '_' + clean_variable(out_var)
            # Parsed encoding: derive label from the active capability index.
            if not state.output_variables and parsed_var and index_to_action:
                if parsed_var in state.output_values:
                    act_var = index_to_action.get(state.output_values[parsed_var])
                    if act_var:
                        new_name += '_' + clean_variable(act_var)
            old_name_to_new_name[state.name] = new_name

        for state in sa.automaton:
            state.name = old_name_to_new_name[state.name]
            state.transitions = [old_name_to_new_name[name] for name in state.transitions]

        sa.update_state_map()

    @staticmethod
    def _is_bootstrap_begin_game_outcome(var_name):
        """Return true for begin-game outcome variables."""
        return (
            isinstance(var_name, str)
            and var_name.startswith(BOOTSTRAP_OUTCOME_PREFIX)
            and var_name != BOOTSTRAP_ACTION
        )

    def normalize_bootstrap_begin_game(self, sa):
        """
        Remove begin-game bootstrap variables before FlexBE SM translation.

        Non-parsed capability specs model ``begin_game_a`` as the initial state so
        Slugs can enter the game cleanly.  It is not a real FlexBE state, and the
        discrete abstraction intentionally omits it.  Strip ``begin_game_a`` only
        from the tagged initial state so the existing null-root handling can
        promote the first real action state.  Outcome variables such as
        ``begin_game_c``/``begin_game_f`` are startup transition conditions and
        are removed from all states.
        """
        initial_state = next(
            (sa[name] for name in sa if sa[name].is_initial),
            None,
        )
        if initial_state is None:
            return

        non_initial_bootstrap = [
            state.name for state in sa.automaton
            if state is not initial_state and BOOTSTRAP_ACTION in state.output_variables
        ]
        if non_initial_bootstrap:
            raise ValueError(
                'Invalid Slugs automaton: solver output violates the begin-game '
                f'bootstrap invariant. {BOOTSTRAP_ACTION} must only appear on '
                f'the tagged initial state; found in {non_initial_bootstrap}.'
            )

        if BOOTSTRAP_ACTION not in initial_state.output_variables:
            return

        if BOOTSTRAP_ACTION not in sa.output_variables:
            raise ValueError(
                'Invalid Slugs automaton: solver output violates the begin-game '
                f'bootstrap invariant. {BOOTSTRAP_ACTION} appears on the tagged '
                'initial state but is missing from automaton output_variables.'
            )

        sa.input_variables = [
            var for var in sa.input_variables
            if not self._is_bootstrap_begin_game_outcome(var)
        ]
        sa.output_variables = [
            var for var in sa.output_variables
            if var != BOOTSTRAP_ACTION
        ]

        for state in sa.automaton:
            state.input_variables = [
                var for var in state.input_variables
                if not self._is_bootstrap_begin_game_outcome(var)
            ]
            state.input_values = {
                var: value for var, value in state.input_values.items()
                if not self._is_bootstrap_begin_game_outcome(var)
            }

        initial_state.output_variables = [
            var for var in initial_state.output_variables
            if var != BOOTSTRAP_ACTION
        ]
        initial_state.output_values = {
            var: value for var, value in initial_state.output_values.items()
            if var != BOOTSTRAP_ACTION
        }

        sa.update_state_map()

    def generate_sm(self, automaton, capabilities_name, verbose=False):
        """Create a new state machine and map errors to synthesis error codes."""
        try:
            return self.generate_sm_handle(automaton, capabilities_name, verbose=verbose)
        except SMGenError as exc:
            print(f'There was an SMGenError={exc.error_code}', flush=True)
            return [], exc.error_code, []
        except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
            print(f'Something went wrong generate_sm wrapper:\n\t{exc.__doc__}\n\t{exc}')
            traceback.print_exc()
            return [], SynthesisErrorCode.SM_GENERATION_FAILED, []

    def generate_sm_handle(self, automaton, system_name, verbose=False):
        """Load config files from disk and delegate to `generate_sm_from_data`."""
        system_name = self._validate_path_component(system_name, 'system_name')
        file_dir = os.path.join(fpths.get_synthesis_home(), system_name, 'configs')

        if not os.path.exists(file_dir):
            raise FileNotFoundError(f"Cannot find system capabilities directory at '{file_dir}'!")

        try:
            capabilities_file = os.path.join(
                file_dir,
                system_name + fpths._SYSTEM_CAPABILITIES_CONFIG_EXT,
            )
            with open(capabilities_file, encoding='utf-8') as yaml_file:
                system_capabilities = yaml.safe_load(yaml_file)
            self._validate_loaded_mapping(
                system_capabilities,
                capabilities_file,
                required_keys=('capabilities',),
            )
        except OSError:
            print(f"Capabilities file not found at '{capabilities_file}'", flush=True)
            raise SMGenError(SynthesisErrorCode.SYSTEM_CONFIG_NOT_FOUND)

        config_file = os.path.join(file_dir, system_name + fpths._DISCRETE_ABSTRACTION_CONFIG_EXT)
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Cannot find system discrete abstraction at '{config_file}'!")

        print(f"Reading discrete abstraction from \n    '{config_file}' ...", flush=True)
        try:
            with open(config_file, encoding='utf-8') as yaml_file:
                discrete_abstraction = yaml.safe_load(yaml_file)
            self._validate_loaded_mapping(
                discrete_abstraction,
                config_file,
                required_keys=('output',),
            )
        except OSError:
            print(f"Discrete abstraction file not found at '{config_file}'", flush=True)
            raise SMGenError(SynthesisErrorCode.SYSTEM_CONFIG_NOT_FOUND)

        return self.generate_sm_from_data(
            automaton, system_capabilities, discrete_abstraction, verbose=verbose
        )

    @staticmethod
    def _validate_loaded_mapping(data, file_path, required_keys=()):
        """Validate a YAML config loaded for state-machine generation."""
        if not isinstance(data, dict):
            raise ValueError(
                f"SM generation config '{file_path}' must contain a top-level "
                f'mapping, got {type(data).__name__}.'
            )
        missing_keys = sorted(key for key in required_keys if key not in data)
        if missing_keys:
            raise ValueError(
                f"SM generation config '{file_path}' is missing required "
                f"key(s): {', '.join(missing_keys)}."
            )

    def generate_sm_from_data(self, automaton, system_capabilities, discrete_abstraction,
                              verbose=False):
        """Create state instantiations from an automaton and in-memory config dicts."""
        sa = SlugsAutomaton.from_dict(automaton)
        self.normalize_bootstrap_begin_game(sa)

        if (
            'variable_mappings' in system_capabilities
            and system_capabilities['variable_mappings'] is not None
        ):
            var_map = system_capabilities['variable_mappings']
            if 'sys_props' not in var_map:
                var_map['sys_props'] = {}
            if 'env_props' not in var_map:
                var_map['env_props'] = {}

            if verbose:
                print(f'Doing variable mapping with {var_map} ...', flush=True)
            for name in sa:
                state = sa[name]
                if verbose:
                    print(30 * '-')
                    print(
                        f"    State '{state.name}' with  {len(state.input_values)} input values "
                        f'and {len(state.output_values)} output values ...'
                    )
                    print(state, flush=True)
                try:
                    for key, value in state.output_values.items():
                        if key in var_map['sys_props']:
                            state.output_values[key] = var_map['sys_props'][key].get(value, value)
                            if verbose:
                                print(
                                    f"      - update '{key}' remap value {value} --> "
                                    f'{state.output_values[key]}'
                                )
                        elif key in var_map['env_props']:
                            state.output_values[key] = var_map['env_props'][key].get(value, value)
                            if verbose:
                                print(
                                    f"    State '{name}' - update '{key}' remap value {value} --> "
                                    f'{state.output_values[key]} (??? output in env_props???!)'
                                )

                    for key, value in state.input_values.items():
                        if key in var_map['sys_props']:
                            state.input_values[key] = var_map['sys_props'][key].get(value, value)
                            if verbose:
                                print(
                                    f"      - update '{key}' remap value {value} --> "
                                    f'{state.input_values[key]}  (??? input in sys_props???!)'
                                )
                        elif key in var_map['env_props']:
                            state.input_values[key] = var_map['env_props'][key].get(value, value)
                            if verbose:
                                print(
                                    f"    State '{name}' - update '{key}' remap value {value} --> "
                                    f'{state.input_values[key]}'
                                )
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    print(f"\033[31m   Error: State '{name}' - {exc}\033[0m")
                    print(var_map)
        else:
            if verbose:
                print('No variable mappings found!')

        all_out_vars = sa.output_variables
        all_in_vars = sa.input_variables
        if verbose:
            print(f'\033[38;5;208m Output VARS: {all_out_vars} \033[0m', flush=True)
            print(f'\033[38;5;208m Input VARS: {all_in_vars} \033[0m', flush=True)

        # Extract parsed action map for state labeling (e.g. capability index → bd_a).
        parsed_var = None
        index_to_action = {}
        for out_var in all_out_vars:
            if (
                out_var in ('capability', 'move_action')
                or out_var.startswith(('capability@', 'capability:', 'move_action@', 'move_action:'))
            ):
                parsed_var = out_var.split(':')[0].split('@')[0]
                break
        if parsed_var:
            raw_maps = discrete_abstraction.get('parsed_action_map', {}) or {}
            raw_map = raw_maps.get(parsed_var, {}) or {}
            for idx, act in raw_map.items():
                try:
                    index_to_action[int(idx)] = act
                except (TypeError, ValueError):
                    pass

        self.modify_names(sa, parsed_var, index_to_action)
        if verbose:
            print(f' Processing Slugs Automaton with {sa.size()} states ...', flush=True)
            print('set up SMGenConfig helper from discrete abstraction ...', flush=True)
        helper = SMGenConfig(discrete_abstraction, all_in_vars, all_out_vars, sa, verbose=verbose)

        if verbose:
            print('Get the initial states ...', flush=True)
        init_states = helper.get_init_states()
        if verbose:
            print(f" {30 * 'v'} Initial States {30 * 'v'}", flush=True)
            print(f' {init_states}', flush=True)
            print(f" {30 * '^'} Initial States {30 * '^'}", flush=True)
        if not init_states:
            print('Unable to deduce an initial state for the automaton.', flush=True)
            raise SMGenError(SynthesisErrorCode.AUTOMATON_NO_INITIAL_STATE)

        state_instantiations = [
            new_si(
                '/',
                StateInstantiation.CLASS_STATEMACHINE,
                '',
                set(helper.get_sm_real_outputs()),
                [],
                init_states[0],
                {},
                [],
                verbose=verbose,
            )
        ]
        sm_messages = []

        for name in sa:
            state = sa[name]
            if helper.is_fake_state(name):
                if verbose:
                    print(f"  '{name}' is a fake state!", flush=True)
                continue

            if verbose:
                print(f"\n\n Processing state '{name}' ...", flush=True)
                print(f'    state={state}', flush=True)
            csg = ConcurrentStateGenerator(name, verbose=verbose)

            curr_state_output_vars = state.output_variables
            if verbose:
                print(f'    outvars = {curr_state_output_vars}', flush=True)
            for out_var in curr_state_output_vars:
                if isinstance(out_var, str) and '@' in out_var:
                    print(
                        f"generate_sm_from_data: skipping parsed binary variable '{out_var}' "
                        '(should not be here in this reworked version)',
                        flush=True,
                    )
                    raise ValueError(f"Invalid outvar '{out_var}' for '{name}'")

                decl = helper.get_class_decl(out_var)
                if verbose:
                    print(f"   adding internal state to csg for '{out_var}' ({decl})")
                csg.add_internal_state(out_var, decl)

                if verbose:
                    print(f"  Processing user data for '{name}'", flush=True)
                ud_mapping = helper.get_userdata_mapping(out_var)
                csg.add_internal_userdata(ud_mapping)

            transitions = helper.get_transitions(state)
            if not transitions:
                if verbose:
                    print('    no transitions from this state - continue processing other states')
                continue

            if verbose:
                print(f'    transitions = {transitions}', flush=True)

            for next_state, conditions in transitions.items():
                if verbose:
                    print(f"    transition '{next_state}' - conditions={conditions}", flush=True)

                substate_name_to_out = {}
                for in_var in conditions:
                    mapped_in_var = helper.map_condition_var(state, in_var)
                    if mapped_in_var != in_var and verbose:
                        print(
                            (
                                f"      remap condition '{in_var}' -> "
                                f"'{mapped_in_var}' for state '{name}'"
                            ),
                            flush=True,
                        )

                    if '_' in mapped_in_var:
                        ss_name = helper.get_substate_name(mapped_in_var)

                        if '_' != mapped_in_var[-2] and verbose:
                            print(
                                f"      not activation ? '{mapped_in_var}' - substate '{ss_name}'",
                                flush=True,
                            )

                        decl = helper.get_class_decl(mapped_in_var)
                        if decl is None and verbose:
                            print(
                                f"      '{mapped_in_var}' is NOT a state implementation!",
                                flush=True,
                            )

                        out_map = helper.get_out_map(ss_name)
                        try:
                            substate_name_to_out[ss_name] = out_map[mapped_in_var]
                        except (AttributeError, KeyError, TypeError, ValueError) as exc:
                            print(exc)
                            print(
                                f"in_var='{mapped_in_var}' ss_name='{ss_name}' ",
                                flush=True,
                            )
                            print(f'outmap={out_map.keys()}', flush=True)
                            print(f'class declaration={decl}', flush=True)
                            print(exc)
                            raise

                        if decl is not None:
                            if verbose:
                                print(
                                    f"      add internal state for '{ss_name}' from condition "
                                    f"'{mapped_in_var}'"
                                )
                            csg.add_internal_state(ss_name, decl)

                is_concurrent = csg.is_concurrent()
                if verbose:
                    print(
                        f"      next state {next_state}' is concurrent = {is_concurrent} "
                        f'ss2out={substate_name_to_out}'
                    )
                if not substate_name_to_out:
                    if verbose:
                        print(
                            (
                                f"      skip transition '{name}->{next_state}' because "
                                'no mapped response outcomes were found'
                            ),
                            flush=True,
                        )
                    continue

                outcome_name = helper.get_outcome_name(
                    is_concurrent,
                    next_state,
                    substate_name_to_out,
                )
                # When any substate has no mapped outcome the chosen state class does not
                # expose an outcome for this condition.  If the target is a real SM output
                # state (e.g. 'failed'), the synthesized path is unreachable in the FlexBE SM.
                has_empty_outcome = any(not ss_out for ss_out in substate_name_to_out.values())
                if has_empty_outcome and helper.is_fake_state(next_state):
                    real_out = helper.get_real_name(next_state)
                    for ss_name, ss_outcomes in substate_name_to_out.items():
                        if not ss_outcomes:
                            class_decl = helper.get_class_decl(ss_name) or {}
                            class_name = class_decl.get('name', ss_name)
                            msg = (
                                f"State '{name}' uses '{class_name}' which declares "
                                f'no FlexBE outcome for condition(s) {conditions}. '
                                f"The '{real_out}' path is not represented in the "
                                f'generated FlexBE SM. To fix: update the discrete '
                                f'abstraction to map {conditions} to a '
                                f"'{real_out}' outcome, or use a state class that "
                                f'exposes it.'
                            )
                            sm_messages.append(msg)
                            print(f'\033[38;5;208m WARNING: {msg}\033[0m', flush=True)
                    continue
                csg.add_internal_outcome_and_transition(
                    outcome_name,
                    helper.get_real_name(next_state),
                    helper.get_autonomy_list(substate_name_to_out),
                )
                csg.add_internal_outcome_maps(
                    {
                        'outcome': outcome_name,
                        'condition': substate_name_to_out,
                    }
                )
                if verbose:
                    print(f"      transition '{name} -> '{next_state}' if: '{substate_name_to_out}'")

            if not csg.internal_states:
                if verbose:
                    print(
                        (
                            f"  skip generated state '{name}' because no internal states "
                            'were collected after transition filtering'
                        ),
                        flush=True,
                    )
                continue

            state_instantiations.extend(csg.gen(state))

        if verbose:
            print(
                f'SMGenHelper: State Machine generation Successfull with '
                f'{len(state_instantiations)} state instantiations',
                flush=True,
            )
        return state_instantiations, SynthesisErrorCode.SUCCESS, sm_messages
