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

"""Build request-driven GR(1) formulas for Slugs synthesis."""

import logging
import re
from typing import ClassVar

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest
from flexbe_synthesis_slugs.helpers.gr1_formula import (
    extract_leaf_expressions,
    fully_wrapped_in_parens,
    get_vars_from_eqn,
    GR1Formula,
    replace_var_in_eqn,
    split_top_level,
)
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
import flexbe_synthesis_slugs.helpers.ltl as LTL

logger = logging.getLogger(__name__)


class SlugsRequestSpecification(BaseProcess):
    """Create GR(1) formulas from an incoming synthesis request."""

    BASIC_VARIABLE_PATTERN: ClassVar = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*'?|\d+)$")
    SAFE_REQUEST_FORMULA_PATTERN: ClassVar = re.compile(r"^[A-Za-z0-9_'\s!&|()<>=-]+$")
    STRUCTURE_INJECTION_CHARS: ClassVar = frozenset({'[', ']', '#', '\n', '\r'})
    FAILURE_OUTCOME_NAMES: ClassVar = frozenset({
        'failed',
        'failure',
        'aborted',
        'canceled',
    })

    spec_name: str
    synthesis_request: FlexBESynthesisRequest
    system_capabilities: dict
    current_specification: dict = {}

    class Config:
        """Allow pydantic model fields with ROS message types."""

        arbitrary_types_allowed = True

    def process(self):
        """Validate request goals/ICs and fold them into the current specification."""
        logger.info('Starting %s ...', self.name)

        gr1_spec = GR1Specification(self.spec_name, verbose=self.verbose)
        gr1_spec.merge_gr1_specification(self.current_specification)

        if self.verbose:
            print(f"Starting spec:\n{gr1_spec}\n{30 * '='}", flush=True)

        ics = [
            val.strip()
            for val in self.synthesis_request.initial_conditions
            if val.strip()
        ]
        goals = [val.strip() for val in self.synthesis_request.goals if val.strip()]
        for ic in ics:
            self._validate_request_formula(ic, 'initial condition')
        for goal in goals:
            self._validate_request_formula(goal, 'goal')

        if self.verbose:
            print(f'ICs: "{ics}"')
            print(f'goals: "{goals}"', flush=True)

        env_init_formula = GR1Formula(
            'env_init',
            env_props=set(gr1_spec.env_props),
            sys_props=set(gr1_spec.sys_props),
        )
        sys_init_formula = GR1Formula(
            'sys_init',
            env_props=env_init_formula.env_props,
            sys_props=env_init_formula.sys_props,
        )
        sys_trans_formula = GR1Formula(
            'sys_trans',
            env_props=env_init_formula.env_props,
            sys_props=env_init_formula.sys_props,
        )
        sys_trans_formula.add(
            '# ---------------------------------------------------------------------------------'
        )
        sys_trans_formula.add(
            '# -------------------------- Sys Safety Goals From Request ------------------------'
        )

        all_valid = True
        env_ic_count = 0
        sys_ic_count = 0
        sys_trans_count = 0

        for ic in ics:
            if self.verbose:
                print(f"Processing IC '{ic}' ...", flush=True)
            vars_in_ic = get_vars_from_eqn(ic, verbose=self.verbose)
            var_props = [gr1_spec.check_prop(var) for var in vars_in_ic]
            if not all(var_props):
                # Check if this works as a memory prop
                for ndx, check in enumerate(var_props):
                    if check is None:
                        if self.verbose:
                            print(f"Checking '{vars_in_ic[ndx]}_m' ...")
                        check_m = gr1_spec.check_prop(f'{vars_in_ic[ndx]}_m')
                        if check_m:
                            var_props[ndx] = check_m
                            if self.verbose:
                                print(
                                    f"  Replacing '{vars_in_ic[ndx]}' with "
                                    f"'{vars_in_ic[ndx]}_m' ({check_m}) in '{ic}'"
                                )
                            ic = replace_var_in_eqn(
                                ic,
                                vars_in_ic[ndx],
                                f'{vars_in_ic[ndx]}_m',
                            )
                            vars_in_ic[ndx] = f'{vars_in_ic[ndx]}_m'
                if not all(var_props):
                    # Recheck after memory replacement
                    print(
                        f"Initial condition '{ic}' contains an invalid proposition\n"
                        f'    vars={vars_in_ic}\n'
                        f'  source={var_props}',
                        flush=True,
                    )
                    all_valid = False

            if all(src == 'env_props' for src in var_props):
                env_ic_count += 1
                env_init_formula.add(f'{ic:50s}  # IC from request')
            elif all(src == 'sys_props' for src in var_props):
                sys_ic_count += 1
                sys_init_formula.add(f'{ic:50s}  # IC from request')
            else:
                print(
                    (
                        f"\033[33mWarning: IC '{ic}' has a mix of ENV and SYS propositions. "
                        'Adding to system.'
                    ),
                    flush=True,
                )
                sys_ic_count += 1
                sys_init_formula.add(f'{ic:50s}  # Composite IC from request')

        processed_goals = []
        for goal in goals:
            if self.verbose:
                print(f"Processing goal '{goal}' ...", flush=True)
            vars_in_goal = get_vars_from_eqn(goal, verbose=self.verbose)
            var_props = [gr1_spec.check_prop(var) for var in vars_in_goal]
            if not all(var_props):
                # Check if this works as a memory prop
                for ndx, check in enumerate(var_props):
                    if check is None:
                        if self.verbose:
                            print(f"Checking '{vars_in_goal[ndx]}' in {gr1_spec.sys_props}")
                        check_m = gr1_spec.check_prop(f'{vars_in_goal[ndx]}_m')
                        if check_m:
                            var_props[ndx] = 'sys_props'
                            if self.verbose:
                                print(
                                    f"  Replacing '{vars_in_goal[ndx]}' with "
                                    f"'{vars_in_goal[ndx]}_m' in '{goal}'"
                                )
                            goal = replace_var_in_eqn(
                                goal,
                                vars_in_goal[ndx],
                                f'{vars_in_goal[ndx]}_m',
                            )
                            vars_in_goal[ndx] = f'{vars_in_goal[ndx]}_m'
                if not all(var_props):
                    # Recheck after memory replacement
                    print(
                        f"Goal '{goal}' contains an invalid proposition\n"
                        f'    vars={vars_in_goal}\n'
                        f'  source={var_props}',
                        flush=True,
                    )
                    all_valid = False

            # Add to goal list after updating any propositions
            processed_goals.append(goal)

        if all_valid:
            goal_string = LTL.conj(processed_goals) if processed_goals else ''
            if self.verbose:
                print(f'  Goal string from request: "{goal_string}"', flush=True)

            sm_outcomes = self.system_capabilities['sm_outcome_mappings']
            if sm_outcomes and goal_string:
                if self.verbose:
                    print(
                        'All ICs and goals are valid - make final formulas ...', flush=True
                    )
                    print(f'  sm_outcomes [{sm_outcomes}]', flush=True)
                ultimate_goal = self._request_success_outcome(
                    self.synthesis_request.sm_outcomes,
                    sm_outcomes,
                    gr1_spec,
                )

                if (
                    ultimate_goal == 'finished'
                    and 'log_finished_a' in gr1_spec.sys_props
                    and 'log_finished' not in goal_string
                ):
                    # Presume we want to generate a log finished before exiting
                    # log_finished must transition to finished for this to work
                    if gr1_spec.check_prop('log_finished_c') is None:
                        raise ValueError(
                            "Spec has 'log_finished_a' but no 'log_finished_c' "
                            'completion proposition.'
                        )
                    print(
                        "\033[33mHandling 'log_finished_a' design case: "
                        "using 'log_finished_a' as the ultimate goal so the "
                        'log capability is activated when the goal is reached, '
                        'then completes before the finished outcome.\033[0m',
                        flush=True,
                    )
                    ultimate_goal = 'log_finished_a'
                if self.verbose:
                    print(f"Using '{ultimate_goal}' as the ultimate goal for system.")

                # Goal formulas
                sys_trans_formula.add(
                    LTL.implication(
                        LTL.conj([LTL.neg(goal_string), LTL.next(goal_string)]),
                        LTL.next(ultimate_goal),
                    )
                    + '  # success!'
                )
                sys_trans_formula.add(
                    LTL.implication(
                        LTL.conj(
                            [LTL.neg(LTL.next(goal_string)), LTL.neg(ultimate_goal)]
                        ),
                        LTL.neg(LTL.next(ultimate_goal)),
                    )
                    + '  # must reach goal!'
                )
                sys_trans_count += 2

                if ultimate_goal == 'log_finished_a':
                    # Gate finished on log_finished_c: the synthesizer must not
                    # claim finished directly — it must pass through log_finished_c.
                    sys_trans_formula.add(
                        LTL.implication(
                            LTL.conj([LTL.neg(LTL.next('log_finished_c')), LTL.neg('finished')]),
                            LTL.neg(LTL.next('finished')),
                        )
                        + '  # finished only after log_finished_c'
                    )
                    sys_trans_count += 1

                if self.verbose:
                    print(f'SYS trans goal formula:\n"{sys_trans_formula}"', flush=True)
            elif goal_string != '':
                # No outcomes defined, treat goal as liveness
                if self.verbose:
                    print(
                        'No SM outcomes defined, assume state machine runs forever; '
                        'using goal as liveness.'
                    )
                goal_clauses = [goal_string]
                split_expr = goal_string.split('#')[0].strip()
                while fully_wrapped_in_parens(split_expr):
                    split_expr = split_expr[1:-1].strip()
                top_tokens = split_top_level(split_expr)
                if '&' in top_tokens and not any(
                    op in top_tokens for op in ('|', '->', '<->')
                ):
                    goal_clauses = [tok for tok in top_tokens if tok and tok != '&']

                env_liveness_formula = GR1Formula(
                    'env_liveness',
                    env_props=env_init_formula.env_props,
                    sys_props=env_init_formula.sys_props,
                )
                sys_liveness_formula = GR1Formula(
                    'sys_liveness',
                    env_props=env_init_formula.env_props,
                    sys_props=env_init_formula.sys_props,
                )

                for goal_clause in goal_clauses:
                    goal_vars = get_vars_from_eqn(goal_clause, verbose=self.verbose)
                    goal_sources = [gr1_spec.check_prop(var) for var in goal_vars]
                    if all(src == 'env_props' for src in goal_sources):
                        if self.verbose:
                            print(
                                (
                                    f"\033[33mWarning: Goal clause '{goal_clause}' uses only "
                                    'ENV props; '
                                    'still adding to sys_liveness for completion.\033[0m'
                                ),
                                flush=True,
                            )
                        sys_liveness_formula.add(goal_clause + '  # success!')
                    elif all(src == 'sys_props' for src in goal_sources):
                        if self.verbose:
                            print(
                                (
                                    f"Goal clause '{goal_clause}' uses only SYS props; "
                                    'adding sys_liveness.'
                                ),
                                flush=True,
                            )
                        sys_liveness_formula.add(goal_clause + '  # success!')
                    else:
                        if self.verbose:
                            print(
                                (
                                    f"Mixed ENV/SYS goal clause '{goal_clause}'; "
                                    'adding to sys_liveness.'
                                ),
                                flush=True,
                            )
                        sys_liveness_formula.add(goal_clause + '  # success!')

                if env_liveness_formula.formulas:
                    gr1_spec.load(env_liveness_formula)
                if sys_liveness_formula.formulas:
                    gr1_spec.load(sys_liveness_formula)

            if self.verbose:
                print('---- Loading formulae into specs ----')
            if env_init_formula.formulas and env_ic_count > 0:
                if self.verbose:
                    print(
                        f'Loading {len(env_init_formula.formulas)} env_init formulae into spec ...',
                        flush=True,
                    )
                    print(env_init_formula)
                gr1_spec.load(env_init_formula)
            if sys_init_formula.formulas and sys_ic_count > 0:
                if self.verbose:
                    print(
                        f'Loading {len(sys_init_formula.formulas)} sys_init formulae into spec ...',
                        flush=True,
                    )
                    print(sys_init_formula)
                gr1_spec.load(sys_init_formula)
            if sys_trans_formula.formulas and sys_trans_count > 0:
                if self.verbose:
                    print(
                        f'Loading {len(sys_trans_formula.formulas)} sys_trans formulae into spec ...',
                        flush=True,
                    )
                    print(sys_trans_formula)
                gr1_spec.load(sys_trans_formula)
        else:
            raise ValueError(
                'slugs_request_specification: Some of the ICs or Goals were invalid!'
            )

        return [gr1_spec.to_dict()]

    @classmethod
    def _validate_request_formula(cls, formula, formula_kind):
        """Reject request formulas containing non-variable tokens or section syntax."""
        if not isinstance(formula, str) or formula.strip() == '':
            raise ValueError(f'Invalid request {formula_kind}: expected non-empty string')

        if any(char in formula for char in cls.STRUCTURE_INJECTION_CHARS):
            raise ValueError(
                f"Invalid request {formula_kind}: '{formula}' contains unsupported "
                'structured-slugs metacharacters'
            )

        if not cls.SAFE_REQUEST_FORMULA_PATTERN.fullmatch(formula):
            raise ValueError(
                f"Invalid request {formula_kind}: '{formula}' contains unsupported "
                'characters'
            )

        for leaf in extract_leaf_expressions(formula):
            cls._validate_request_formula_leaf(leaf, formula_kind, formula)

    @classmethod
    def _validate_request_formula_leaf(cls, leaf, formula_kind, formula):
        """Validate one atomic request formula leaf as basic variable tokens."""
        token = leaf.strip()
        while token.startswith('!'):
            token = token[1:].strip()

        if token == '':
            raise ValueError(f"Invalid request {formula_kind}: empty token in '{formula}'")

        if '!=' in token:
            variables = token.split('!=', 1)
        elif '=' in token:
            variables = token.split('=', 1)
        else:
            variables = [token]

        for variable in variables:
            variable = variable.strip()
            if not cls.BASIC_VARIABLE_PATTERN.fullmatch(variable):
                raise ValueError(
                    f"Invalid request {formula_kind}: token '{variable}' in "
                    f"'{formula}' is not a basic variable"
                )

    @classmethod
    def _request_success_outcome(cls, requested_outcomes, sm_outcome_mappings, gr1_spec):
        """Return the mapped request success outcome used in final goal formulas."""
        requested = [outcome.strip() for outcome in requested_outcomes if outcome.strip()]
        requested_success = next(
            (
                outcome
                for outcome in requested
                if outcome.lower() not in cls.FAILURE_OUTCOME_NAMES
            ),
            None,
        )
        requested_success = requested_success or 'finished'

        mapped_success = sm_outcome_mappings.get(requested_success, requested_success)
        mapped_outcomes = set(sm_outcome_mappings.values())

        if mapped_success not in mapped_outcomes:
            raise ValueError(
                f"Requested success outcome '{requested_success}' maps to "
                f"'{mapped_success}', which is not one of the mapped SM outcomes "
                f'{sorted(mapped_outcomes)}.'
            )

        if gr1_spec.check_prop(mapped_success) is None:
            raise ValueError(
                f"Mapped success outcome '{mapped_success}' is not a proposition "
                'in the current Slugs specification.'
            )

        return mapped_success


def main(inputs):
    """Create the request specification process instance."""
    current_spec = {}
    if len(inputs) > 3:
        current_spec = inputs[3]

    return SlugsRequestSpecification(
        name='SlugsRequestSpecification',
        spec_name=inputs[0],
        synthesis_request=inputs[1],
        system_capabilities=inputs[2],
        current_specification=current_spec,
    )


if __name__ == '__main__':
    """
    Stand alone test file.

    Requires a preprocess run to generate the hidden .flexbe_synthesis/<capability_name> folder!
    """
    import sys

    from flexbe_synthesis_generic.processes.system_capabilities_loader import (
        main as loader,
    )
    from flexbe_synthesis_slugs.processes.slugs_capability_specification import (
        main as cap_spec,
    )
    from flexbe_synthesis_slugs.processes.slugs_transition_system_specification import (
        main as trans_spec,
    )
    import yaml

    capability_name = 'vending_demo'
    if len(sys.argv) > 1:
        capability_name = sys.argv[1]

    print(f"Try to load capabilities for '{capability_name}' ...", flush=True)
    outputs = loader([capability_name]).process()
    print('Returned capabilities: ')
    print(yaml.dump(outputs[0], default_flow_style=False))

    print(f"Run the capability specifier for '{capability_name}' ...", flush=True)
    system_capabilities = outputs[0]
    cap_specifier = cap_spec([capability_name, system_capabilities, {}])
    (cap_specs,) = cap_specifier.process()

    print(f"Run the transition specifier for '{capability_name}' ...", flush=True)
    trans_specifier = trans_spec([capability_name, system_capabilities, cap_specs])
    (trans_specs,) = trans_specifier.process()

    request = FlexBESynthesisRequest(
        initial_conditions=['prep_pay_m', '!soda_m'], goals=['soda_m']
    )
    req_specifier = main([capability_name, request, system_capabilities, cap_specs])
    (req_specs,) = req_specifier.process()

    print('Request Specifications:')
    if isinstance(req_specs, dict):
        gr1_spec = GR1Specification(capability_name)
        gr1_spec.merge_gr1_specification(req_specs)
        print(gr1_spec)
    else:
        print(trans_specs)
        print('--- Unexpected output!')
