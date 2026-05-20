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

"""Add system-side (adversarial) liveness constraints for capability outcomes."""

import logging

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.gr1_formula import GR1Formula
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
import flexbe_synthesis_slugs.helpers.ltl as LTL

logger = logging.getLogger(__name__)


class SlugsAdversarialLiveness(BaseProcess):
    """Generate `sys_liveness` constraints for capability completion progress."""

    spec_name: str
    system_capabilities: dict
    current_specification: dict = {}

    def process(self):
        """Append adversarial liveness: outcomes or progress obligations."""
        logger.info('Starting %s ...', self.name)

        capabilities = self.system_capabilities.get('capabilities', {})
        gr1_spec = GR1Specification(self.spec_name)
        gr1_spec.merge_gr1_specification(self.current_specification)

        sys_liveness_formula = GR1Formula(
            'sys_liveness',
            set(gr1_spec.env_props),
            set(gr1_spec.sys_props),
        )
        sys_liveness_formula.add('# Must have outcome or continue until actions succeed')

        sm_outcomes = set(self.system_capabilities.get('sm_outcome_mappings', {}).values())
        progress_clauses = []

        for prop in sorted(gr1_spec.sys_props):
            if prop in sm_outcomes or prop.endswith('_m') or not prop.endswith('_a'):
                continue

            cap_name = prop[:-2]
            cap_data = capabilities.get(cap_name)
            if not cap_data:
                continue

            if 'state' in cap_data:
                state_data = cap_data['state']
            elif 'behavior' in cap_data:
                state_data = cap_data['behavior']
            else:
                raise ValueError(
                    f"Capability '{cap_name}' has neither 'state' nor 'behavior' interface data"
                )
            outcomes = state_data.get('outcomes', {})
            non_completed = {
                str(out_cfg.get('remapping', '')).strip()
                for out_cfg in outcomes.values()
                if isinstance(out_cfg, dict)
            }
            non_completed = {name for name in non_completed if name and name != 'completed'}
            if not non_completed:
                continue

            progress_clauses.append(
                LTL.neg(LTL.paren(LTL.implication(prop, LTL.next(f'{cap_name}_c'))))
            )

        if sm_outcomes or progress_clauses:
            goals = list(sm_outcomes)
            if gr1_spec.sys_liveness:
                # This plugin collapses all sys_liveness goals into a single disjunction.
                # That is only semantically safe when there is exactly one prior goal:
                # with multiple goals, replacing them with a disjunction would weaken
                # the GR(1) spec (from "each holds infinitely often" to "at least one
                # holds infinitely often").  The pipeline must place this plugin
                # immediately after slugs_request_specification, which is the only
                # upstream plugin that may add a sys_liveness entry.
                if len(gr1_spec.sys_liveness) != 1:
                    raise ValueError(
                        f'SlugsAdversarialLiveness requires exactly one prior sys_liveness '
                        f'goal (set by slugs_request_specification), but found '
                        f'{len(gr1_spec.sys_liveness)}. Check the process pipeline '
                        f'ordering — no other plugin should add sys_liveness before this one.'
                    )
                for spec in gr1_spec.sys_liveness:
                    trimmed_spec = spec.strip().split('#')[0].strip()
                    print(f"Updating sys liveness '{trimmed_spec}'  ({spec})")
                    goals.append(LTL.paren(trimmed_spec))
                gr1_spec.sys_liveness = []
            sys_liveness_formula.add(LTL.disj(sorted(goals) + progress_clauses))
            gr1_spec.load(sys_liveness_formula)

        return [gr1_spec.to_dict()]


def main(inputs):
    """Create adversarial liveness process instance."""
    current_spec = {}
    if len(inputs) > 2:
        current_spec = inputs[2]

    return SlugsAdversarialLiveness(
        name='SlugsAdversarialLiveness',
        spec_name=inputs[0],
        system_capabilities=inputs[1],
        current_specification=current_spec,
    )
