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

"""Build transition-system GR(1) constraints for Slugs synthesis."""

import logging

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.gr1_formula import (
    get_var_from_condition,
    get_vars_from_eqn,
    GR1Formula,
)
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
import flexbe_synthesis_slugs.helpers.ltl as LTL

logger = logging.getLogger(__name__)


class SlugsTransitionSystemSpecification(BaseProcess):
    """Generate transition system formulas from system capabilities."""

    spec_name: str
    system_capabilities: dict
    current_specification: dict = {}

    def process(self):
        """Load all transition-related constraints into the GR(1) specification."""
        logger.info('Starting %s ...', self.name)

        if 'capabilities' not in self.system_capabilities:
            raise ValueError(
                'Need full system capabilities,'
                f' this only has {list(self.system_capabilities.keys())}'
            )
        gr1_spec = GR1Specification(self.spec_name, verbose=self.verbose)
        gr1_spec.merge_gr1_specification(self.current_specification)

        self.process_capability_variables(gr1_spec)

        self.process_transition_relations_specs(gr1_spec)

        self.process_precondition_specs(gr1_spec)

        self.process_postcondition_specs(gr1_spec)

        return [gr1_spec.to_dict()]

    def process_capability_variables(self, gr1_spec):
        """Load numeric capability variables into env/sys proposition sets."""
        if (
            'variable_mappings' not in self.system_capabilities
            or self.system_capabilities['variable_mappings'] is None
        ):
            if self.verbose:
                print(f"No variable mappings defined for '{self.spec_name}'")
            return

        variables = self.system_capabilities['variable_mappings']
        if not variables:
            if self.verbose:
                print(f"Empty variable mappings defined for '{self.spec_name}'")
            return

        env_props = set()
        sys_props = set()

        if 'env_props' in variables:
            for var in variables['env_props']:
                try:
                    values = variables['env_props'][var]
                    min_val = min(values.keys())
                    max_val = max(values.keys())
                    new_var = f'{var}:{min_val}...{max_val}'
                    if self.verbose:
                        print(f"    Adding '{new_var}' to env_props")
                    env_props.add(new_var)
                except (KeyError, TypeError, ValueError) as exc:
                    print(f"Exception processing env_prop '{var}':\n{exc}", flush=True)
                    print(variables['env_props'])
                    raise exc

            gr1_spec.env_props.update(env_props)

        if 'sys_props' in variables:
            for var in variables['sys_props']:
                try:
                    values = variables['sys_props'][var]
                    min_val = min(values.keys())
                    max_val = max(values.keys())
                    new_var = f'{var}:{min_val}...{max_val}'
                    if self.verbose:
                        print(f"    Adding '{new_var}' to sys_props")
                    sys_props.add(new_var)
                except (KeyError, TypeError, ValueError) as exc:
                    print(f"Exception processing sys_prop '{var}':\n{exc}", flush=True)
                    print(variables['sys_props'])
                    raise exc
            gr1_spec.sys_props.update(sys_props)
        gr1_spec.update_composite_props()

    def process_transition_relations_specs(self, gr1_spec):
        """Add transition relation constraints linking outcomes to activations."""
        if 'transition_relations' not in self.system_capabilities:
            if self.verbose:
                print(f"No transition relations defined for '{self.spec_name}'")
            return

        capabilities = self.system_capabilities['capabilities']
        sm_outcome_mappings = self.system_capabilities['sm_outcome_mappings']
        transition_relations = self.system_capabilities['transition_relations']
        formula = GR1Formula('sys_trans')
        # Track who is setting what variables
        setters = {'sm_outcomes': {}}

        formula.add(
            '# ------------------------------------------------------------------------------'
        )
        formula.add(
            '# ---------------------- System Transition Relations ----------------------'
        )
        for cap in transition_relations:
            if self.verbose:
                print(f"Processing transition relation for '{cap}'", flush=True)
            if cap not in capabilities:
                raise ValueError(f"'{cap}' is not a defined capability!")

            relations = transition_relations[cap]
            if not relations:
                if self.verbose:
                    print(f"   No transition relationship defined for '{cap}'")
                continue
            else:
                if self.verbose:
                    print(f"transition relation for '{cap}':\n    {relations}", flush=True)
                for out in relations:
                    activation_props = []
                    for act in relations[out]:
                        act = act.strip()
                        act_targ = act.replace('!', '').strip()  # allow exclusions
                        if act_targ in capabilities:
                            activation_props.append(act + '_a')
                        elif act_targ in sm_outcome_mappings:
                            mapped_act = self._map_sm_outcome_transition_target(
                                act,
                                sm_outcome_mappings,
                            )
                            activation_props.append(mapped_act)
                            if mapped_act not in setters['sm_outcomes']:
                                setters['sm_outcomes'][mapped_act] = []
                            setters['sm_outcomes'][mapped_act].append(f'{cap}_{out[0]}')
                        else:
                            print(
                                (
                                    f'Transition relation must use capability or sm_outcome '
                                    f"for '{cap}' not '{act}'"
                                ),
                                flush=True,
                            )
                            raise ValueError(

                                    f'Transition relation must use capability or sm_outcome '
                                    f"for '{cap}' not '{act}'"

                            )

                    formula.add(
                        LTL.implication(
                            LTL.next(cap + f'_{out[0]}'),
                            LTL.disj(map(LTL.next, activation_props)),
                        )
                    )

        for key, props in setters['sm_outcomes'].items():
            if sm_outcome_mappings.get('failed') == key:
                # For failure outcomes we will restrict this to if and only if
                if self.verbose:
                    print(f"Transition Relation Spec: '{key}' - {props} - Failed handling")
                formula.add(
                    LTL.implication(
                        LTL.neg(LTL.disj([LTL.next(prop) for prop in props] + [key])),
                        LTL.neg(LTL.next('failed')),
                    )
                )
        if self.verbose:
            print('Transition relation specs:')
            print(formula, flush=True)
        gr1_spec.load(formula)

    @staticmethod
    def _map_sm_outcome_transition_target(target, sm_outcome_mappings):
        """Map transition-relation SM outcome keys to Slugs proposition names."""
        stripped = target.strip()
        negated = stripped.startswith('!')
        outcome_key = stripped[1:].strip() if negated else stripped
        mapped_target = sm_outcome_mappings[outcome_key]
        if negated:
            return LTL.neg(mapped_target)
        return mapped_target

    def process_precondition_specs(self, gr1_spec):
        """Convert action preconditions into transition constraints."""
        if 'action_preconditions' not in self.system_capabilities:
            if self.verbose:
                print(f"No action_preconditions defined for '{self.spec_name}'")
            return

        if self.verbose:
            print(
                f"\033[33m\n\n{30 * '='}\nProcessing pre conditions ...\n\n\033[0m",
                flush=True,
            )

        capabilities = self.system_capabilities['capabilities']
        preconditions = self.system_capabilities['action_preconditions']

        env_init_formula = GR1Formula('env_init')
        env_trans_formula = GR1Formula('env_trans')
        env_trans_formula.add(
            '# ------------------------------------------------------------------------------'
        )
        env_trans_formula.add(
            '# -------------------------- Environment Preconditions -------------------------'
        )
        sys_init_formula = GR1Formula('sys_init')
        sys_trans_formula = GR1Formula('sys_trans')
        sys_trans_formula.add(
            '# ------------------------------------------------------------------------------'
        )
        sys_trans_formula.add(
            '# ---------------------------- System Preconditions ----------------------------'
        )
        for cap in preconditions:
            if cap not in capabilities:
                raise ValueError(f"'{cap}' is not a defined capability!")

            conditions = preconditions[cap]
            if not conditions:
                if self.verbose:
                    print(f"   No preconditions defined for '{cap}'")
                continue
            else:
                condition_props = []
                for cond in conditions:
                    vars_in_cond = get_vars_from_eqn(cond, verbose=self.verbose)
                    if len(vars_in_cond) == 1 and vars_in_cond[0] in capabilities:
                        # A single proposition related to an action
                        # Assume this is a memory prop set on prior completion
                        var = vars_in_cond[0]
                        condition_props.append(cond + '_m')
                        if gr1_spec.check_prop(var + '_m') is None:
                            if self.verbose:
                                print(f"Adding '{var}_m' to SYS props")
                            sys_trans_formula.sys_props.add(var + '_m')
                            sys_init_formula.sys_props.add(var + '_m')
                            # Assume off unless otherwise specificed in ICs
                            sys_init_formula.add(
                                f"{LTL.neg(var + '_m'):50s}  # Transition memory IC"
                            )
                        else:
                            if self.verbose:
                                print(
                                    f"Precondition '{cond}' is already a proposition.",
                                    flush=True,
                                )

                    elif len(vars_in_cond) == 1 and gr1_spec.check_prop(vars_in_cond[0] + '_m'):
                        # A single memory proposition
                        # Assume this is a memory prop set on prior completion
                        # Must be defined in capabilities file
                        var = vars_in_cond[0]
                        condition_props.append(cond + '_m')
                        if self.verbose:
                            print(
                                f" Adding precondition memory prop for '{cond + '_m'} "
                                'without setting init (do in capabilities!)'
                            )
                    elif len(vars_in_cond) > 0:
                        if self.verbose:
                            print(
                                f"Checking preconditions '{cond}' for '{vars_in_cond}' ...",
                                flush=True,
                            )
                        sources = [gr1_spec.check_prop(var) for var in vars_in_cond]
                        source = all(src is not None for src in sources)
                        if source:
                            # An equation containing only environment or system props
                            if any(ch in cond for ch in '&|='):
                                # Add parentheses if numeric or con/disjunction
                                condition_props.append(LTL.paren(cond))
                            else:
                                condition_props.append(cond)
                        else:
                            if any(ch in cond for ch in '&|'):
                                # TODO: implement composite preconditions in the Slugs backend.
                                # GenerateTransitionRelations.preprocess() should have blocked
                                # composite conditions before reaching here; this is a safety net.
                                print(
                                    (
                                        f'\033[31mComposite precondition reached Slugs backend '
                                        f"for '{cap}'!\n    {cond}\033[0m"
                                    ),
                                    flush=True,
                                )
                                raise ValueError(
                                    f"Composite precondition for '{cap}': {cond} — "
                                    'support not yet implemented in the Slugs backend'
                                )
                            else:
                                print(
                                    (
                                        f"\033[31mInvalid precondition for '{cap}'!\n"
                                        f"  '{vars_in_cond}' : '{cond}'\033[0m"
                                    ),
                                    flush=True,
                                )
                                print(f'   sources=<{sources}>')
                                print(f' Current spec:\n{gr1_spec}', flush=True)
                                raise ValueError(

                                        f"Invalid precondition for '{cap}': "
                                        f"'{vars_in_cond}' : '{cond}'"

                                )
                if self.verbose:
                    print(f'Precondition setup: {condition_props}', flush=True)
                lhs = LTL.neg(LTL.conj(map(LTL.next, condition_props)))
                if self.verbose:
                    print(f'"{lhs}"')
                lhs = lhs.replace('!!', '')  # Clean up double negation for clarity
                if self.verbose:
                    print(f'"{lhs}"')
                    print('---- Precond ----', flush=True)
                precondition = LTL.implication(lhs, LTL.next(LTL.neg(cap + '_a')))
                sys_trans_formula.add(f'{precondition:50s}' + '  # precondition')
        # print(sys_trans_formula, flush=True)
        gr1_spec.load(env_init_formula)
        gr1_spec.load(env_trans_formula)
        gr1_spec.load(sys_init_formula)
        gr1_spec.load(sys_trans_formula)

    def process_postcondition_specs(self, gr1_spec):
        """Convert action postconditions into env/sys transition constraints."""
        if 'action_postconditions' not in self.system_capabilities:
            if self.verbose:
                print(f"No action_postconditions defined for '{self.spec_name}'")
            return

        if self.verbose:
            print(
                f"\033[33m\n\n{30 * '='}\nProcessing post conditions ...\n\n\033[0m",
                flush=True,
            )
        capabilities = self.system_capabilities['capabilities']
        postconditions = self.system_capabilities['action_postconditions']

        # Track who is setting what variables
        setters = {'env_props': {}, 'sys_props': {}, 'sm_outcomes': {}}

        env_init_formula = GR1Formula(
            'env_init',
            env_props=set(gr1_spec.env_props),
            sys_props=set(gr1_spec.sys_props),
        )
        env_trans_formula = GR1Formula(
            'env_trans',
            env_props=set(gr1_spec.env_props),
            sys_props=set(gr1_spec.sys_props),
        )
        env_trans_formula.add(
            '# ------------------------------------------------------------------------------'
        )
        env_trans_formula.add(
            '# ----------------------- Environment Postconditions -----------------------'
        )

        sys_init_formula = GR1Formula(
            'sys_init',
            env_props=set(gr1_spec.env_props),
            sys_props=set(gr1_spec.sys_props),
        )
        sys_trans_formula = GR1Formula(
            'sys_trans',
            env_props=set(gr1_spec.env_props),
            sys_props=set(gr1_spec.sys_props),
        )
        sys_trans_formula.add(
            '# ------------------------------------------------------------------------------'
        )
        sys_trans_formula.add(
            '# ---------------------------- System Postconditions ----------------------------'
        )

        for cap in postconditions:
            if cap not in capabilities:
                raise ValueError(f"'{cap}' is not a defined capability!")

            outcomes = postconditions[cap]
            if not outcomes:
                if self.verbose:
                    print(f"   No postconditions defined for '{cap}'")
                continue

            for out in outcomes:
                conditions = outcomes[out]
                cap_out = cap + f'_{out[0]}'
                if not conditions:
                    if self.verbose:
                        print(f"   No postconditions defined for '{cap}' outcome '{out}'")
                    continue
                else:
                    if self.verbose:
                        print(
                            f"\033[33mPost conditions for '{cap}' {outcomes}\033[0m",
                            flush=True,
                        )
                    for cond in conditions:
                        # We are doing separate implication statements vs. one big one
                        vars_in_cond = get_vars_from_eqn(cond, verbose=self.verbose)
                        if len(vars_in_cond) != 1:
                            print(

                                    f"\033[31mInvalid number of variables '{vars_in_cond}' "
                                    f"in '{cond}' for '{cap}'\n"
                                    '   we only allow conjunctive list of single variables.\033[0m'

                            )
                            raise ValueError(

                                    f"Invalid number of variables '{vars_in_cond}' "
                                    f"in '{cond}' for '{cap}'"

                            )
                        var = vars_in_cond[0]
                        if '@' in cond:
                            # Special handling for system variables being set by synthesis
                            var = var.replace('@', '')
                            found_var = False
                            if gr1_spec.check_prop(var):
                                for prop in gr1_spec.sys_props:
                                    if prop.startswith(var):
                                        found_var = True
                                        if self.verbose:
                                            print(
                                                f"Synthesis will set '{cond}' as required"
                                            )
                                        # Not set here, but activating will allow change
                                        if var in setters['sys_props']:
                                            setters['sys_props'][var].append(cap_out)
                                        else:
                                            setters['sys_props'][var] = [cap_out]
                                        break
                                if found_var:
                                    continue  # Not creating a spec for this

                                for prop in gr1_spec.env_props:
                                    if prop.startswith(var):
                                        found_var = True
                                        if self.verbose:
                                            print(
                                                f"Environment equations '{cond}' are based on outcome"
                                            )
                                        # Not set here, but activating will allow change
                                        if var in setters['env_props']:
                                            setters['env_props'][var].append(cap_out)
                                        else:
                                            setters['env_props'][var] = [cap_out]
                                        break

                            if not found_var:
                                print(
                                    f"\033[31mInvalid condition for '{cap}'!\n"
                                    f"    '{cond}' is not env_ or sys_prop!\033[0m",
                                    flush=True,
                                )
                                raise ValueError(
                                    f"Invalid condition for '{cap}'!\n"
                                    f"    '{cond}' is not env_ or sys_prop!"
                                )
                        elif var in capabilities:
                            # Assume this is a memory prop set on completion
                            # memory variables are set by SYS_TRANS rules based on outcomes
                            mem_var = var + '_m'
                            mem_prop = cond + '_m'
                            sys_trans_formula.sys_props.add(mem_var)
                            # Assume off unless otherwise specificed in ICs
                            sys_init_formula.add(
                                f"{LTL.neg(var + '_m'):50s}  # Transition memory IC"
                            )
                            sys_trans_formula.add(
                                LTL.implication(LTL.next(cap_out), LTL.next(mem_prop))
                            )  # mem set on same step as output
                            if mem_var in setters['sys_props']:
                                setters['sys_props'][mem_var].append(cap_out)
                            else:
                                setters['sys_props'][mem_var] = [cap_out]
                        else:
                            source = gr1_spec.check_prop(var)
                            if source is None:
                                # Check for memory prop
                                source = gr1_spec.check_prop(var + '_m')
                                if source is None:
                                    if any(ch in cond for ch in '&|'):
                                        # TODO: implement composite postconditions in the Slugs backend.
                                        # GenerateTransitionRelations.preprocess() should have blocked
                                        # composite conditions before reaching here; this is a safety net.
                                        print(
                                            (
                                                f'\033[31mComposite postcondition reached Slugs backend '
                                                f"for '{cap}'!\n    {cond}\033[0m"
                                            ),
                                            flush=True,
                                        )
                                        raise ValueError(
                                            f"Composite postcondition for '{cap}': {cond} — "
                                            'support not yet implemented in the Slugs backend'
                                        )
                                    else:
                                        print(
                                            (
                                                f"\033[31mInvalid postcondition for '{cap}'!\n"
                                                f"  '{var}' : '{cond}'\033[0m"
                                            ),
                                            flush=True,
                                        )
                                        raise ValueError(

                                                f"Invalid postcondition for '{cap}': "
                                                f"'{var}' : '{cond}'"

                                        )
                                else:
                                    if '=' in cond:
                                        raise ValueError(
                                            f"numeric not a memory block for '{cond}'"
                                        )

                                    var = var + '_m'
                                    cond = cond + '_m'
                                    if self.verbose:
                                        print(
                                            f"  Setting '{var}' ({cond}) for post conditions "
                                            '(not setting IC)'
                                        )

                            # Post condition occurs in same step as outcome
                            # But use next semantics to constrain environment choices
                            if '=' in cond:
                                # Add parenthesis around numerics
                                terms = cond.split('=')
                                cond = LTL.paren(LTL.next(terms[0]) + '=' + terms[1])
                            else:
                                cond = LTL.next(cond)

                            if source == 'env_props':
                                # An environment prop
                                env_trans_formula.add(
                                    LTL.implication(LTL.next(cap_out), cond)
                                )
                                if var in setters['env_props']:
                                    setters['env_props'][var].append(cap_out)
                                else:
                                    setters['env_props'][var] = [cap_out]
                            elif source == 'sys_props':
                                # system prop
                                sys_trans_formula.add(
                                    LTL.implication(LTL.next(cap_out), cond)
                                )
                                if var in setters['sys_props']:
                                    setters['sys_props'][var].append(cap_out)
                                else:
                                    setters['sys_props'][var] = [cap_out]
                            else:
                                print(
                                    (
                                        f"\033[31mInvalid postcondition for '{cap}'!\n"
                                        f"  '{var}' : '{cond}'\033[0m"
                                    ),
                                    flush=True,
                                )
                                raise ValueError(
                                    f"Invalid postcondition for '{cap}': '{var}' : '{cond}'"
                                )

        if self.verbose:
            print(30 * '=')
        env_setters = setters['env_props']
        sys_setters = setters['sys_props']
        if env_setters:
            if self.verbose:
                print(f'env_setters: {env_setters}', flush=True)
            env_trans_formula.add('# Values do not change unless acted on')
            for prop in env_setters:
                # Values don't change in next step if nothing relevant
                props_list = []
                for out in env_setters[prop]:
                    props_list.append(LTL.next(out))
                var = get_var_from_condition(prop)
                if var in env_trans_formula.env_props:
                    # regular boolean
                    lhs = LTL.conj([LTL.neg(LTL.disj(props_list)), var])
                    env_trans_formula.add(LTL.implication(lhs, LTL.next(var)))
                    lhs = LTL.conj([LTL.neg(LTL.disj(props_list)), LTL.neg(var)])
                    env_trans_formula.add(LTL.implication(lhs, LTL.neg(LTL.next(var))))
                else:
                    # numeric
                    if self.verbose:
                        print(f"'{var}' is numeric")
                    lhs = LTL.neg(LTL.disj(props_list))
                    rhs = LTL.paren(LTL.next(var) + '=' + var)
                    env_trans_formula.add(LTL.implication(lhs, rhs))
        if sys_setters:
            if self.verbose:
                print(f'sys_setters: {sys_setters}', flush=True)
            sys_trans_formula.add('# Values do not change unless acted on')
            for prop in sys_setters:
                # Values don't change in next step if nothing relevant
                props_list = []
                var = get_var_from_condition(prop)
                for out in sys_setters[prop]:
                    props_list.append(LTL.next(out))
                if var in sys_trans_formula.sys_props:
                    # regular boolean
                    lhs = LTL.conj([LTL.neg(LTL.disj(props_list)), var])
                    sys_trans_formula.add(LTL.implication(lhs, LTL.next(var)))
                    lhs = LTL.conj([LTL.neg(LTL.disj(props_list)), LTL.neg(var)])
                    sys_trans_formula.add(LTL.implication(lhs, LTL.next(LTL.neg(var))))
                else:
                    # numeric
                    if self.verbose:
                        print(f"'{var}' is numeric")
                    lhs = LTL.neg(LTL.disj(props_list))
                    rhs = LTL.paren(LTL.next(var) + '=' + var)
                    sys_trans_formula.add(LTL.implication(lhs, rhs))

        if len(env_init_formula.formulas) > 0:
            gr1_spec.load(env_init_formula)
        if len(env_trans_formula.formulas) > 2:  # 2 for comments
            gr1_spec.load(env_trans_formula)
        if len(sys_init_formula.formulas) > 0:
            gr1_spec.load(sys_init_formula)
        if len(sys_trans_formula.formulas) > 2:  # 2 for comments
            gr1_spec.load(sys_trans_formula)

        if self.verbose:
            print(env_trans_formula, flush=True)
            print(sys_trans_formula, flush=True)
            print('\x1b[33m' + 30 * '*' + '\x1b[0m')


def main(inputs):
    """Create the transition-system process instance."""
    current_spec = {}
    if len(inputs) > 2:
        current_spec = inputs[2]

    return SlugsTransitionSystemSpecification(
        name='SlugsTransitionSystemSpecification',
        spec_name=inputs[0],
        system_capabilities=inputs[1],
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
    trans_specifier = main([capability_name, system_capabilities, cap_specs])
    (trans_specs,) = trans_specifier.process()

    print('Capability and Transition Specification Outputs:')
    if isinstance(trans_specs, dict):
        gr1_spec = GR1Specification(capability_name)
        gr1_spec.merge_gr1_specification(trans_specs)
        print(gr1_spec)
    else:
        print(trans_specs)
        print('--- Unexpected output!')
