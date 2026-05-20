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

"""Add environment-side fair-outcome liveness constraints for capabilities."""

import logging

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.gr1_formula import GR1Formula
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
import flexbe_synthesis_slugs.helpers.ltl as LTL

logger = logging.getLogger(__name__)


class SlugsFairOutcomeLiveness(BaseProcess):
    """Generate fair-outcome `env_liveness` constraints for capability completion."""

    spec_name: str
    system_capabilities: dict
    current_specification: dict = {}

    def process(self):
        """Append env liveness clauses: inactive or eventually complete when active."""
        logger.info('Starting %s ...', self.name)

        capabilities = self.system_capabilities.get('capabilities', {})
        sm_outcomes = set(self.system_capabilities.get('sm_outcome_mappings', {}).values())
        gr1_spec = GR1Specification(self.spec_name)
        gr1_spec.merge_gr1_specification(self.current_specification)

        env_liveness_formula = GR1Formula(
            'env_liveness',
            set(gr1_spec.env_props),
            set(gr1_spec.sys_props),
        )

        env_liveness = []
        for prop in sorted(gr1_spec.sys_props):
            if prop.endswith('_m') or not prop.endswith('_a'):
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

            env_liveness.append(LTL.disj([LTL.neg(prop), LTL.next(f'{cap_name}_c')]))

        if env_liveness:
            for form in env_liveness:
                env_liveness_formula.add(form)
            gr1_spec.load(env_liveness_formula)

        has_sys_liveness = any(
            isinstance(line, str) and line.strip() and not line.strip().startswith('#')
            for line in gr1_spec.sys_liveness
        )
        if sm_outcomes and not has_sys_liveness:
            sys_liveness_formula = GR1Formula(
                'sys_liveness',
                set(gr1_spec.env_props),
                set(gr1_spec.sys_props),
            )
            sys_liveness_formula.add('# Must have outcome')
            sys_liveness_formula.add(LTL.disj(sorted(sm_outcomes)))
            gr1_spec.load(sys_liveness_formula)

        return [gr1_spec.to_dict()]


def main(inputs):
    """Create fair outcome liveness process instance."""
    current_spec = {}
    if len(inputs) > 2:
        current_spec = inputs[2]

    return SlugsFairOutcomeLiveness(
        name='SlugsFairOutcomeLiveness',
        spec_name=inputs[0],
        system_capabilities=inputs[1],
        current_specification=current_spec,
    )
