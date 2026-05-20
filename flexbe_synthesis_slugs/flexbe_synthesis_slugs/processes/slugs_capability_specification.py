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

"""Build GR(1) capability constraints for Slugs synthesis."""

import logging

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.gr1_formula import GR1Formula
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
import flexbe_synthesis_slugs.helpers.ltl as LTL

logger = logging.getLogger(__name__)

ONEHOT_MUTEX_MARKER = '# One and only one capability must be active every step'


class SlugsCapabilitySpecification(BaseProcess):
    """Load capability definitions into a GR(1) specification."""

    spec_name: str
    system_capabilities: dict
    current_specification: dict = {}

    def process(self):
        """Transform capabilities into GR(1) formulas and merge with current spec."""
        logger.info('Starting %s ...', self.name)

        if 'capabilities' not in self.system_capabilities:
            raise ValueError(
                'This must be the SystemCapabilities  (not simple capabilities file)'
            )

        # Extract the basic capabilities definitions
        capabilities = self.system_capabilities['capabilities']

        gr1_spec = GR1Specification(self.spec_name, verbose=self.verbose)
        gr1_spec.merge_gr1_specification(self.current_specification)
        cap_names = sorted(capabilities.keys())

        env_init_formula = GR1Formula(
            'env_init', set(gr1_spec.env_props), set(gr1_spec.sys_props)
        )
        env_trans_formula = GR1Formula(
            'env_trans',
            env_props=env_init_formula.env_props,
            sys_props=env_init_formula.sys_props,
        )
        env_trans_formula.add(
            '# ------------------------------------------------------------------------------'
        )
        env_trans_formula.add(
            '# ----------------------------- System Capabilities ----------------------------'
        )
        sys_init_formula = GR1Formula(
            'sys_init', set(gr1_spec.env_props), set(gr1_spec.sys_props)
        )
        sys_trans_formula = GR1Formula(
            'sys_trans',
            env_props=sys_init_formula.env_props,
            sys_props=sys_init_formula.sys_props,
        )
        sys_trans_formula.add(
            '# ------------------------------------------------------------------------------'
        )
        sys_trans_formula.add(
            '# ----------------------------- System Capabilities ----------------------------'
        )
        sys_props = []

        if 'sm_outcome_mappings' not in self.system_capabilities:
            print('\033[31mNo SM outcomes defined ...\033[0m', flush=True)
        else:
            sys_trans_formula.add(
                '# ------------------------------------------------------------------------------'
            )
            sys_trans_formula.add(

                    '# -------------------------- Sys Safety due to SM Outcomes '
                    '------------------------'

            )
            sm_outcomes = list(self.system_capabilities['sm_outcome_mappings'].values())
            sm_outcomes.sort()
            if self.verbose:
                print(f'\033[33mSet up SM outcomes {sm_outcomes}\033[0m', flush=True)
            for out in sm_outcomes:
                sys_props.append(out)
                gr1_spec.sys_props.add(out)
                sys_init_formula.add(f'{LTL.neg(out):50s}  # SM outcome IC')
                sys_trans_formula.add(
                    f'{LTL.implication(out, LTL.next(out)):<50s}  # SM outcomes are persistent'
                )

        if 'memory' not in self.system_capabilities:
            if self.verbose:
                print('No special memory variables defined ...', flush=True)
        else:
            if 'env_props' in self.system_capabilities['memory']:
                env_mem = list(self.system_capabilities['memory']['env_props'].keys())
                env_mem.sort()
                for var in env_mem:
                    ic = self.system_capabilities['memory']['env_props'][var]
                    if len(var) > 2 and var[-2:] != '_m':
                        var = var + '_m'  # Flag as a memory variable
                    gr1_spec.env_props.add(var)
                    if ic:
                        env_init_formula.add(f'{var:50s}  # Capability memory IC')
                    else:
                        env_init_formula.add(
                            f'{LTL.neg(var):50s}  # Capability memory IC'
                        )

            if 'sys_props' in self.system_capabilities['memory']:
                sys_mem = list(self.system_capabilities['memory']['sys_props'].keys())
                sys_mem.sort()
                for var in sys_mem:
                    ic = self.system_capabilities['memory']['sys_props'][var]
                    if len(var) > 2 and var[-2:] != '_m':
                        var = var + '_m'  # Flag as a memory variable
                    gr1_spec.sys_props.add(var)
                    if ic:
                        sys_init_formula.add(f'{var:50s}  # Capability memory IC')
                    else:
                        sys_init_formula.add(
                            f'{LTL.neg(var):50s}  # Capability memory IC'
                        )

        for cap_name in cap_names:
            cap_data = capabilities[cap_name]
            if 'state' in cap_data:
                state_data = cap_data['state']
            elif 'behavior' in cap_data:
                state_data = cap_data['behavior']
            else:
                raise ValueError(
                    f"Capability '{cap_name}' has neither 'state' nor 'behavior' interface data"
                )
            sys_prop = cap_name + '_a'

            if sys_prop in gr1_spec.sys_init:
                if self.verbose:
                    print(f"Existing IC for '{sys_prop}' found!")
            else:
                if sys_prop != 'begin_game_a':
                    sys_init_formula.add(
                        f'{LTL.neg(sys_prop):50s}  # Capability - Activations initially off'
                    )
                else:
                    sys_init_formula.add(
                        f'{sys_prop:50s}  #  Capability - Define begin_game_a as initial state'
                    )

                sys_init_formula.sys_props.add(sys_prop)
                gr1_spec.sys_props.add(sys_prop)

            sys_props.append(sys_prop)  # Add each capability to system props list

            env_props = []  # New env_props list related to this capability
            # if state_data['name'] == 'OperatorDecisionState':
            #     # OperatorDecisionState outcomes are defined by parameters
            #     # They are not fixed by state
            #     print(
            #         f"Capability '{cap_name}' using "
            #         f"'{state_data['name']}' requires special handling of outcomes"
            #     )
            #     for out in cap_data['parameters']['outcomes']:
            #         out2 = state_outcome_mappings[out]
            #         env_props.append(cap_name + f'_{out2[0]}')
            # else:
            # Handle OperatorDecisionState when loading capabilities
            for out in state_data['outcomes']:
                out2 = state_data['outcomes'][out]['remapping']
                env_props.append(cap_name + f'_{out2[0]}')
            if self.verbose:
                print(f"Cap '{cap_name}' - env_props={env_props}", flush=True)
            env_props = sorted(set(env_props))  # outcomes are not necessarily unique
            if self.verbose:
                print(f'             env_props={env_props}\n  {state_data}', flush=True)
            mutexes = GR1Formula.gen_mutex_formulas(map(LTL.next, env_props), verbose=self.verbose)
            for form in mutexes:
                env_trans_formula.add(
                    f'{LTL.implication(sys_prop, form):<50s}  # 1-and-only-1'
                )
            for prop in env_props:
                env_trans_formula.add(

                        f'{LTL.implication(LTL.neg(sys_prop), LTL.next(LTL.neg(prop))):<50s}  '
                        '# No outcome until activated'

                )

            # All outcomes are false initially
            for form in env_props:
                env_init_formula.add(
                    f'{LTL.neg(form):<50s}  # outcomes are off at start'
                )
            # We do not make any claims about sys_init here.
            # Let synthesis decide what to start with.

        sys_trans_formula.add(
            '# ---------------------------------------------------------------------------------'
        )
        sys_trans_formula.add(ONEHOT_MUTEX_MARKER)
        if 'begin_game_a' in sys_props:
            sys_trans_formula.add(
                LTL.neg(LTL.next('begin_game_a')) + '  # do not use begin_game again'
            )
            sys_props.remove('begin_game_a')  # Not part of our mutual exclusions

        mutexes = GR1Formula.gen_mutex_formulas(map(LTL.next, sys_props), verbose=self.verbose)
        sys_trans_formula.add(mutexes)

        gr1_spec.load(env_init_formula)
        gr1_spec.load(env_trans_formula)
        gr1_spec.load(sys_init_formula)
        gr1_spec.load(sys_trans_formula)

        return [gr1_spec.to_dict()]


def main(inputs):
    """Create the process entry-point used by the synthesis pipeline."""
    current_spec = {}
    if len(inputs) > 2:
        current_spec = inputs[2]

    return SlugsCapabilitySpecification(
        name='SlugsCapabilitySpecification',
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
    import yaml

    capability_name = 'vending_demo'
    if len(sys.argv) > 1:
        capability_name = sys.argv[1]

    print(f"Try to load capabilities for '{capability_name}' ...", flush=True)
    outputs = loader([capability_name]).process()
    print('Returned capabilities: ')
    print(yaml.dump(outputs[0], default_flow_style=False))

    capability_spec = main([capability_name, outputs[0], {}])
    outputs = capability_spec.process()

    print('Capability Specification Outputs:')
    if isinstance(outputs[0], dict):
        gr1_spec = GR1Specification(capability_name)
        gr1_spec.merge_gr1_specification(outputs[0])
        print(gr1_spec.structured_slugs_yaml())
    else:
        for out in outputs:
            print(30 * '=')
            print(out, flush=True)
        print('--- Unexpected output!')
