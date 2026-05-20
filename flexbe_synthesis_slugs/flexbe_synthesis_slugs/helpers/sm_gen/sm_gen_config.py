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

import traceback

from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.slugs_automaton import SlugsAutomaton
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_error import SMGenError
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_util import clean_variable


class SMGenConfig:
    """Represent configuration and helpers for state-machine generation."""

    def __init__(self, config, all_in_vars, all_out_vars, automaton, verbose=False):
        self.verbose = verbose
        if verbose:
            print('SMGenConfig', flush=True)
            print(f'\033[38;5;208m Input variables: {all_in_vars} \033[0m', flush=True)
            print(f'\033[38;5;208m Output variables: {all_out_vars} \033[0m', flush=True)
            print(
                f'\033[38;5;208m Number of output variables: {len(all_out_vars)} \033[0m',
                flush=True,
            )

        self.config = config
        self.all_in_vars = all_in_vars
        self.all_out_vars = all_out_vars

        self.automaton = automaton
        if not isinstance(self.automaton, SlugsAutomaton):
            raise SMGenError(SynthesisErrorCode.AUTOMATON_INVALID)

        if verbose:
            print(config, flush=True)

        self.sm_fake_out_to_real_out = config['output']
        if self.sm_fake_out_to_real_out:
            self.sm_fake_outputs = self.sm_fake_out_to_real_out.keys()
        else:
            self.sm_fake_outputs = []

        self.state_name_to_sm_output = self.get_state_name_to_sm_output()

        if verbose:
            print('SMGenConfig - Populate various dictionaries to future functions.', flush=True)
        self.in_var_to_class_decl = {}
        self.in_var_to_out_var = {}
        self.activation_to_out_map = {}
        self.parsed_action_variable = None
        self.parsed_action_index = {}
        self.parsed_index_to_action = {}

        try:
            for act_var, var_config in self.config.items():
                if act_var in ('name', 'output', 'parsed_action_map'):
                    continue

                if 'class_decl' not in var_config:
                    if verbose:
                        print(f" act var '{act_var}' - {var_config} - no class decl continue")
                    continue

                class_decl = var_config['class_decl']
                if class_decl is None:
                    print(f"Invalid class declaration for '{act_var}' \n{var_config}", flush=True)

                out_map = var_config['state_outcome_mapping']
                if out_map is None:
                    print(f"Invalid output map for '{act_var}' \n{var_config}", flush=True)

                if verbose:
                    print(
                        f"SMGenConfig:  act_var='{act_var}' class_decl='{class_decl}' "
                        f'({type(class_decl)}\n{out_map}',
                        flush=True,
                    )
                    if class_decl['name'] == 'OperatorDecisionState':
                        print(30 * '-' + ' OpDecision Here' + 30 * '-')
                        print(var_config)
                        print(out_map)
                        print(30 * '=' + ' OpDecision Here' + 30 * '=')

                if act_var in self.activation_to_out_map:
                    print(f"\033[31mWARNING: Overwriting the outcome map for '{act_var}'\033[0m")
                self.activation_to_out_map[act_var] = out_map

                for in_var in out_map.keys():
                    self.in_var_to_class_decl[in_var] = class_decl
                    self.in_var_to_out_var[in_var] = act_var

            # Parsed-binary support: controller action encoded as one numeric output.
            parsed_action_var = None
            for out_var in self.all_out_vars:
                if (
                    out_var == 'capability'
                    or out_var.startswith('capability:')
                    or out_var.startswith('capability@')
                    or out_var == 'move_action'
                    or out_var.startswith('move_action:')
                    or out_var.startswith('move_action@')
                ):
                    parsed_action_var = out_var.split(':')[0].split('@')[0]
                    break

            if parsed_action_var is not None and self.activation_to_out_map:
                self.parsed_action_variable = parsed_action_var
                self.parsed_index_to_action = self._load_parsed_action_map(parsed_action_var)
                self.parsed_action_index = {
                    act_var: idx for idx, act_var in self.parsed_index_to_action.items()
                }
                self.parsed_index_to_action = {
                    idx: act_var for act_var, idx in self.parsed_action_index.items()
                }
                for act_var, out_map in self.activation_to_out_map.items():
                    if act_var not in self.parsed_action_index:
                        continue
                    class_decl = self.config[act_var].get('class_decl')
                    for in_var in out_map.keys():
                        self.in_var_to_class_decl[in_var] = class_decl
                        self.in_var_to_out_var[in_var] = act_var
                if verbose:
                    print(
                        (
                            f"Parsed action mapping via '{self.parsed_action_variable}': "
                            f'{self.parsed_action_index}'
                        ),
                        flush=True,
                    )

            if verbose:
                print('SMGenConfig - Completed initial setup.', flush=True)

        except KeyError as exc:
            print(
                '\033[31mThe discrete abstraction file is invalid due to missing '
                f"key '{exc}'.\033[0m"
            )
            traceback.print_exc()
            print(exc, flush=True)
            raise SMGenError(SynthesisErrorCode.CONFIG_FILE_INVALID) from exc
        except Exception as exc:
            print('\033[31mThe discrete abstraction file is invalid.\033[0m')
            traceback.print_exc()
            print(exc, flush=True)
            raise SMGenError(SynthesisErrorCode.CONFIG_FILE_INVALID) from exc

    def _load_parsed_action_map(self, parsed_action_var):
        """Load and validate the canonical parsed action index map."""
        parsed_maps = self.config.get('parsed_action_map')
        if not isinstance(parsed_maps, dict):
            raise ValueError(
                f"Parsed action variable '{parsed_action_var}' requires parsed_action_map."
            )

        raw_map = parsed_maps.get(parsed_action_var)
        if raw_map is None and parsed_action_var == 'move_action':
            raw_map = parsed_maps.get('capability')
        if not isinstance(raw_map, dict) or not raw_map:
            raise ValueError(
                f"parsed_action_map for '{parsed_action_var}' must be a non-empty mapping."
            )

        parsed_index_to_action = {}
        for raw_index, raw_action in raw_map.items():
            try:
                index = int(raw_index)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f'parsed_action_map index {raw_index!r} must be an integer.'
                ) from exc
            if not isinstance(raw_action, str) or raw_action == '':
                raise ValueError(
                    f'parsed_action_map[{raw_index!r}] must be a non-empty action name.'
                )
            if raw_action not in self.activation_to_out_map:
                raise ValueError(
                    f"parsed_action_map[{index}] references unknown action '{raw_action}'."
                )
            if index in parsed_index_to_action:
                raise ValueError(f"parsed_action_map repeats index '{index}'.")
            parsed_index_to_action[index] = raw_action

        missing_actions = set(self.activation_to_out_map) - set(parsed_index_to_action.values())
        extra_actions = set(parsed_index_to_action.values()) - set(self.activation_to_out_map)
        if missing_actions or extra_actions:
            raise ValueError(
                'parsed_action_map must exactly match discrete abstraction actions: '
                f'missing={sorted(missing_actions)}, extra={sorted(extra_actions)}.'
            )

        n = len(parsed_index_to_action)
        expected_indexes = set(range(1, n + 1))  # 0 reserved as null
        actual_indexes = set(parsed_index_to_action)
        if actual_indexes != expected_indexes:
            raise ValueError(
                'parsed_action_map indexes must be contiguous from 1 (0 is reserved as null): '
                f'expected={sorted(expected_indexes)}, actual={sorted(actual_indexes)}.'
            )

        return parsed_index_to_action

    def get_init_states(self):
        """
        Return candidate initial states using the explicit ``is_initial`` flag.

        The reducer tags the root state with ``is_initial=True``.  When decoding
        leaves that state with no SM-relevant output variables, it is a null
        bootstrap (no activation or SM outcome); it is removed and its successors
        become the effective initial states. Otherwise the tagged state itself is
        the initial state.
        """
        initial_state = next(
            (self.automaton[n] for n in self.automaton if self.automaton[n].is_initial),
            None,
        )
        if initial_state is None:
            raise SMGenError(SynthesisErrorCode.AUTOMATON_NO_INITIAL_STATE)

        if not initial_state.output_variables:
            # Null bootstrap: no activation variable active (memory bits may still be set);
            # remove and promote its successors.
            init_names = sorted(initial_state.transitions)
            self.automaton.pop(initial_state.name)
            self.automaton.update_state_map()
            if self.verbose:
                print(f"\n\n{10 * '-'} Removed 1 States: {10 * '-'}")
                print(f"Removed '{initial_state.name}'")
                print(f"{10 * '^'} Removed States {10 * '^'}\n\n", flush=True)
        else:
            init_names = [initial_state.name]

        if self.verbose:
            print(f'Current automaton has {self.automaton.size()} states', flush=True)
            print(f'New init states    : {init_names}', flush=True)
        return init_names

    def get_state_name_to_sm_output(self):
        """Create mapping from exit substate names to specific outputs."""
        state_to_output = {}
        for key in self.automaton:
            state = self.automaton[key]
            outputs = state.output_variables
            if self.is_sm_output(outputs):
                in_both = [out for out in self.sm_fake_outputs if out in outputs]
                if len(in_both) > 1:
                    print(
                        f'This substate represent multiple final outputs. ({in_both})',
                        flush=True,
                    )
                    print(f'   outputs={outputs}', flush=True)
                    raise SMGenError(SynthesisErrorCode.AUTOMATON_INVALID)
                if len(in_both) == 0:
                    print(
                        'This substate represent no final outputs, but expected it to.',
                        flush=True,
                    )
                    print(f'   outputs={outputs}', flush=True)
                    raise SMGenError(SynthesisErrorCode.AUTOMATON_INVALID)
                state_to_output[state.name] = in_both[0]

        return state_to_output

    def get_sm_real_outputs(self):
        """Return real (external) outputs of the generated state machine."""
        if self.sm_fake_out_to_real_out:
            return self.sm_fake_out_to_real_out.values()
        return []

    def get_transitions(self, state):
        """Deduce transitions from a source state to reachable next states."""
        next_states = [str(val) for val in state.transitions]
        next_states = sorted(set(next_states))

        transitions = {}
        for next_state_name in next_states:
            if self.verbose:
                print(
                    f"    processing transition from '{state.name}' to '{next_state_name}'",
                    flush=True,
                )
            next_state = self.automaton[next_state_name]
            if next_state is None:
                raise SMGenError(SynthesisErrorCode.AUTOMATON_NEXT_STATE_INVALID)

            input_vars = self._get_next_state_input_conditions(state, next_state)
            conditions = []
            has_active_response = False
            for in_var in input_vars:
                in_var = self._map_generic_outcome_to_response(state, in_var)
                if self.is_response_var(in_var):
                    if self.does_state_activate(state, in_var):
                        conditions.append(in_var)
                        has_active_response = True
                else:
                    conditions.append(in_var)

            if next_state_name == state.name and not has_active_response:
                if self.verbose:
                    print(
                        f"    skip self transition for state: '{state.name}' "
                        'without active response condition',
                        flush=True,
                    )
                continue

            if len(conditions) > 0:
                transitions[next_state_name] = conditions
            elif self.verbose:
                print(
                    f"    Empty conditions for state: '{state.name}'\n"
                    f'       with next states: {next_states}\n'
                    f'       and input vars: {input_vars}',
                    flush=True,
                )

        # Post-process: resolve collisions between forward transitions.
        # When the reducer merges failure/completion variants of the same output state,
        # two forward paths from the same source may be assigned the same condition
        # (e.g. both claim 'bd_c' because the merged target inherits input_variables
        # from its completed variant).  If one colliding target carries failure=True in
        # input_values, remap its conditions to the failure outcome instead.
        forward_items = [(n, conds) for n, conds in transitions.items() if n != state.name]
        cond_counts: dict = {}
        for _, conds in forward_items:
            for c in conds:
                cond_counts[c] = cond_counts.get(c, 0) + 1
        colliding: set = {c for c, cnt in cond_counts.items() if cnt > 1}
        if colliding:
            for target_name, conds in forward_items:
                target_state = self.automaton[target_name]
                if target_state is None or not target_state.input_values.get('failure'):
                    continue
                new_conds = []
                changed = False
                for cond in conds:
                    if cond in colliding and cond in self.in_var_to_out_var:
                        out_var = self.in_var_to_out_var[cond]
                        out_map = self.activation_to_out_map.get(out_var, {})
                        failure_cond = next(
                            (rv for rv in out_map if isinstance(rv, str) and rv.endswith('_f')),
                            None,
                        )
                        if failure_cond and failure_cond != cond:
                            new_conds.append(failure_cond)
                            changed = True
                            continue
                    new_conds.append(cond)
                if changed:
                    if self.verbose:
                        print(
                            f"    remap forward-collision conditions for '{target_name}': "
                            f'{conds} -> {new_conds}',
                            flush=True,
                        )
                    transitions[target_name] = new_conds

        # Post-process: when the reducer merges failure/completion equivalent states
        # the survivor inherits input_variables from both, causing the self-transition
        # to claim the same condition as a forward transition.  Remap the overlapping
        # conditions on the self-transition to their failure counterparts so both the
        # retry loop ('fail') and the forward edge ('done') are emitted correctly.
        if state.name in transitions:
            forward_conds = {
                c for name, conds in transitions.items()
                if name != state.name
                for c in conds
            }
            overlap = [c for c in transitions[state.name] if c in forward_conds]
            if overlap:
                new_self_conds = []
                for cond in transitions[state.name]:
                    if cond in forward_conds and cond in self.in_var_to_out_var:
                        out_var = self.in_var_to_out_var[cond]
                        out_map = self.activation_to_out_map.get(out_var, {})
                        failure_cond = next(
                            (rv for rv in out_map if isinstance(rv, str) and rv.endswith('_f')),
                            None,
                        )
                        new_self_conds.append(failure_cond if failure_cond else cond)
                    else:
                        new_self_conds.append(cond)
                # Deduplicate while preserving order (e.g. 'bd_f' may already be present).
                seen: set = set()
                deduped = [c for c in new_self_conds if not (c in seen or seen.add(c))]
                if deduped != transitions[state.name]:
                    if self.verbose:
                        print(
                            f"    remap self-transition conditions for '{state.name}': "
                            f'{transitions[state.name]} -> {deduped}',
                            flush=True,
                        )
                    transitions[state.name] = deduped

        return transitions

    def _get_next_state_input_conditions(self, source_state, next_state):
        """Return response-bearing input conditions for an outgoing edge."""
        input_vars = list(next_state.input_variables)
        # Augment from input_values for self-transitions and for forward transitions
        # where input_variables is empty.
        #
        # Self-transitions: a merged self-loop state may carry failure indicators
        # (e.g. input_values={'failure': True}) not present in input_variables.
        #
        # Forward transitions with empty input_variables: input_values is the *only*
        # source of the condition (e.g. a non-merged failure state with in_vars=[]).
        #
        # We do NOT augment when input_variables is already non-empty on a forward
        # edge: the target's input_values then reflect why it was originally reached
        # (its own retry-loop condition after reducer merging), not the condition on
        # the current outgoing edge — augmenting there contaminates the forward edge.
        if next_state.name == source_state.name or not input_vars:
            for in_var, value in next_state.input_values.items():
                if not value:
                    continue

                mapped_in_var = self._map_generic_outcome_to_response(source_state, in_var)
                if mapped_in_var != in_var and mapped_in_var not in input_vars:
                    input_vars.append(in_var)

        return input_vars

    def _map_generic_outcome_to_response(self, state, in_var):
        """
        Map a generic transition outcome AP to the active capability's response AP.

        Handles any outcome registered in the discrete abstraction
        (completed → _c, failed/failure → _f, waiting → _w, …) by matching the
        first character of the generic name against the response-variable suffix
        convention used by generate_discrete_abstraction.
        """
        # Already a concrete response variable — no remapping needed.
        if in_var in self.in_var_to_class_decl:
            return in_var

        active_out_var = None
        for out_var in state.output_variables:
            if out_var in self.activation_to_out_map:
                active_out_var = out_var
                break

        if (
            active_out_var is None
            and self.parsed_action_variable is not None
            and self.parsed_action_variable in state.output_values
        ):
            cap_idx = state.output_values[self.parsed_action_variable]
            active_out_var = self.parsed_index_to_action.get(cap_idx)
            if active_out_var is None:
                # Backward compatibility with earlier 1-based parsed encoding.
                active_out_var = self.parsed_index_to_action.get(cap_idx - 1)

        if active_out_var is None or active_out_var not in self.activation_to_out_map:
            return in_var

        out_map = self.activation_to_out_map[active_out_var]

        # Primary: naming convention — response vars end with '_' + first char of outcome
        # (e.g. completed → _c, failed/failure → _f, waiting → _w).
        preferred_suffix = '_' + in_var[0]
        for response_var in out_map.keys():
            if isinstance(response_var, str) and response_var.endswith(preferred_suffix):
                return response_var

        # Fallback: infer from mapped outcome values when suffix convention is not followed.
        desired = in_var[:4]  # 'comp', 'fail', 'wait', …
        for response_var, mapped_outcome in out_map.items():
            if isinstance(mapped_outcome, list):
                mapped_values = [str(val).lower() for val in mapped_outcome]
                if any(val.startswith(desired) for val in mapped_values):
                    return response_var
                # Backward compat: 'failed'/'failure' matches any non-completion outcome.
                if in_var in ('failed', 'failure') and any(
                    val not in ('done', 'completed') for val in mapped_values
                ):
                    return response_var
            elif str(mapped_outcome).lower().startswith(desired):
                return response_var

        return in_var

    def get_substate_name(self, in_var):
        """Return readable name of substate associated with an input variable."""
        if self.is_response_var(in_var):
            return self.in_var_to_out_var[in_var]
        return in_var

    def map_condition_var(self, state, in_var):
        """Map a transition condition variable into a concrete response variable when possible."""
        return self._map_generic_outcome_to_response(state, in_var)

    def is_sm_output(self, outputs):
        """Return whether outputs indicate this state exits the SM."""
        check = set(outputs)
        return any(output in check for output in self.sm_fake_outputs)

    def get_outcome_name(self, is_concurrent, state_name, condition):
        """Return the outcome name needed to transition to the next state."""
        _ = state_name
        if not is_concurrent:
            _k, value = list(condition.items())[0]
            return value

        return '__'.join(
            f'{clean_variable(key)}_{value}'
            for (key, value) in condition.items()
        )

    def get_real_name(self, state_name):
        """Return the real state name, resolving fake output placeholder states."""
        if self.is_fake_state(state_name):
            fake_output = self.state_name_to_sm_output[state_name]
            return self.sm_fake_out_to_real_out[fake_output]
        return state_name

    def get_autonomy_list(self, conditions):
        """Return autonomy values for transition conditions."""
        try:
            return [self.config[out_var]['autonomy'] for out_var, _ in conditions.items()]
        except KeyError:
            raise SMGenError(SynthesisErrorCode.CONFIG_AUTONOMY_INVALID)

    def get_userdata_mapping(self, var):
        """Allow list of unmapped keys, or dictionary of key to mapping."""

        def update_key_mapping(ud_map, src_data, src):
            data = src_data[src]
            if isinstance(data, dict):
                for key, val in data.items():
                    if key in ud_map and ud_map[key] != val:
                        print(
                            f"\033[32mWARNING: '{src}' - multiple key remaps for '{key}'\n"
                            f' ({ud_map[key]}, {val})] - using {val}'
                        )
                    if isinstance(val, dict) and 'remapping' in val:
                        ud_map[key] = val['remapping']
                    else:
                        ud_map[key] = val
            elif isinstance(data, list):
                for key in data:
                    if key in ud_map and ud_map[key] != key:
                        print(
                            f"\033[32mWARNING: '{src}' - multiple key remaps for '{key}'\n"
                            f' ({ud_map[key]}, {key})] - using {key}'
                        )
                    ud_map[key] = key
            else:
                print(
                    f"\033[31mSMGenConfig: get_userdata_mapping for '{var}'\n "
                    f"        unexpected type {type(data)} from '{src}'\033[0m"
                )

        try:
            ud_keys = {}
            if var in self.config:
                var_config = self.config[var]
                if 'userdata_keys' in var_config:
                    if self.verbose:
                        print(f"userdata_keys for '{var}'")
                    if isinstance(var_config['userdata_keys'], dict):
                        ud_keys.update(var_config['userdata_keys'])
                    elif isinstance(var_config['userdata_keys'], list):
                        ud_keys.update({key: key for key in var_config['userdata_keys']})
                    else:
                        print(
                            f"\033[31mSMGenConfig: get_userdata_mapping for '{var}'\n "
                            f"        unexpected type {type(var_config['userdata_keys'])}]\033[0m"
                        )

                if 'userdata_in' in var_config:
                    if self.verbose:
                        print(f"userdata_in for '{var}'")
                    update_key_mapping(ud_keys, var_config, 'userdata_in')

                if 'userdata_out' in var_config:
                    if self.verbose:
                        print(f"userdata_out for '{var}'")
                    update_key_mapping(ud_keys, var_config, 'userdata_out')

            return ud_keys
        except Exception as exc:
            raise SMGenError(SynthesisErrorCode.CONFIG_USERDATA_INVALID) from exc

    def is_fake_state(self, name):
        """Return whether a state is a placeholder for an output."""
        return name in self.state_name_to_sm_output

    def is_response_var(self, in_var):
        """Return whether an input variable is a response variable."""
        return in_var in self.in_var_to_class_decl

    def is_activation_var(self, out_var):
        """Return whether an output variable is an activation variable."""
        var_config = self.config[out_var]
        if 'class_decl' not in var_config or 'state_outcome_mapping' not in var_config:
            raise SMGenError(SynthesisErrorCode.CONFIG_VARIABLE_CONFIG_INVALID)
        out_map = var_config['state_outcome_mapping']
        return any(in_var in self.all_in_vars for in_var, _ in out_map.items())

    def get_out_map(self, act_var):
        """Get the output mapping associated with an activation."""
        return self.activation_to_out_map[act_var]

    def get_class_decl(self, var):
        """Get the class declaration associated with a variable."""
        if var in self.config:
            var_config = self.config[var]
            if 'class_decl' not in var_config:
                raise SMGenError(SynthesisErrorCode.CONFIG_VARIABLE_CONFIG_INVALID)
            return var_config['class_decl']

        if var in self.in_var_to_class_decl:
            return self.in_var_to_class_decl[var]

        print('\n\n' + 30 * 'v', flush=True)
        print(f"  failed to find '{var}' in get_class_decl", flush=True)
        print(
            '   ******** self config keys               : ',
            list(self.config.keys()),
            flush=True,
        )
        print(
            '   ******** self in_var_to_class_decl : ',
            list(self.in_var_to_class_decl.keys()),
            flush=True,
        )
        print(30 * '!', flush=True)
        return None

    def does_state_activate(self, state, in_var):
        """Return whether state activates something that has in_var as a response."""
        if in_var not in self.in_var_to_out_var:
            return False
        out_var = self.in_var_to_out_var[in_var]
        if out_var in state.output_variables:
            return True

        if (
            self.parsed_action_variable is not None
            and out_var in self.parsed_action_index
            and self.parsed_action_variable in state.output_values
        ):
            return state.output_values[self.parsed_action_variable] == self.parsed_action_index[
                out_var
            ]

        return False
