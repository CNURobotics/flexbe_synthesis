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

"""Add one-hot pending flags and pending-based liveness constraints to GR(1) specs."""

import logging
import re

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.gr1_formula import strip_outer_parens
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification

logger = logging.getLogger(__name__)


class SlugsPendingSpecification(BaseProcess):
    """Augment capability specs with per-capability `_p` pending propositions."""

    spec_name: str
    system_capabilities: dict
    current_specification: dict = {}

    def process(self):
        """Inject one-hot pending flag dynamics and liveness rewrites."""
        logger.info('Starting %s ...', self.name)

        gr1_spec = GR1Specification(self.spec_name)
        gr1_spec.merge_gr1_specification(self.current_specification)
        capabilities = self.system_capabilities.get('capabilities', {})

        pending_formulas = []
        liveness_rewrites = {}
        for cap_name, cap_data in capabilities.items():
            activation_prop = f'{cap_name}_a'
            if activation_prop not in gr1_spec.sys_props:
                continue

            outcome_tokens = self._collect_capability_outcome_tokens(cap_name, cap_data)
            completed_prop = outcome_tokens.get('completed')
            non_completed_props = outcome_tokens.get('non_completed', [])
            if not completed_prop or not non_completed_props:
                continue

            pending_var = f'{cap_name}_p'
            gr1_spec.sys_props.add(pending_var)
            gr1_spec.sys_init[(pending_var,)] = f'!{pending_var:46s}  # pending IC'

            non_completed_terms = [self._as_next_token(prop) for prop in non_completed_props]
            non_completed_expr = (
                non_completed_terms[0]
                if len(non_completed_terms) == 1
                else '(' + ' | '.join(non_completed_terms) + ')'
            )
            trigger_expr = f"(({activation_prop}) | ({activation_prop}'))"
            pending_formulas.extend(
                [
                    (
                        f"({activation_prop}') -> {pending_var}'"
                        '  # set pending when selected'
                    ),
                    (
                        f"(({activation_prop}) & ({non_completed_expr})) -> {pending_var}'"
                        '  # keep/set pending on non-completed outcome'
                    ),
                    (
                        f"((!({activation_prop}')) & (({activation_prop}) & ({completed_prop}'))) -> !{pending_var}'"
                        '  # clear pending on completion unless re-selected next'
                    ),
                    (
                        f"!{trigger_expr} -> ({pending_var}' <-> {pending_var})"
                        '  # pending inertia unless this capability updates it'
                    ),
                ]
            )
            liveness_rewrites[activation_prop] = (completed_prop, pending_var)

        if pending_formulas:
            insert_at = len(gr1_spec.sys_trans)
            for idx, line in enumerate(gr1_spec.sys_trans):
                if isinstance(line, str) and 'System Postconditions' in line:
                    insert_at = idx + 1
                    break
            gr1_spec.sys_trans[insert_at:insert_at] = pending_formulas

        if liveness_rewrites:
            gr1_spec.env_liveness = [
                self._rewrite_pending_liveness(line, liveness_rewrites)
                for line in gr1_spec.env_liveness
            ]

        gr1_spec.update_composite_props()
        return [gr1_spec.to_dict()]

    def _collect_capability_outcome_tokens(self, cap_name, cap_data):
        """Return completed and non-completed one-hot outcome APs for a capability."""
        if 'state' in cap_data:
            state_data = cap_data['state']
        elif 'behavior' in cap_data:
            state_data = cap_data['behavior']
        else:
            raise ValueError(
                f"Capability '{cap_name}' has neither 'state' nor 'behavior' interface data"
            )
        outcomes = state_data.get('outcomes', {})
        remapped = {}
        for out_cfg in outcomes.values():
            if not isinstance(out_cfg, dict):
                continue
            mapped = out_cfg.get('remapping')
            if mapped is None:
                continue
            mapped_str = str(mapped).strip()
            if not mapped_str:
                continue
            remapped[mapped_str.lower()] = f'{cap_name}_{mapped_str[0]}'

        completed_prop = remapped.get('completed')
        non_completed = [
            token for name, token in remapped.items() if name != 'completed'
        ]
        return {'completed': completed_prop, 'non_completed': non_completed}

    def _rewrite_pending_liveness(self, expr, rewrites):
        """Replace `(!<cap>_a | <cap>_c')` with pending-aware liveness clauses."""
        if not isinstance(expr, str):
            return expr

        if '#' in expr:
            raw_expr, comment = expr.split('#', 1)
            comment_suffix = '#' + comment
        else:
            raw_expr = expr
            comment_suffix = ''

        stripped = raw_expr.strip()
        core = strip_outer_parens(stripped)
        top_level = self._split_top_level_or(core)
        if top_level is None:
            return expr
        lhs, rhs = top_level
        lhs = strip_outer_parens(lhs.strip())
        rhs = strip_outer_parens(rhs.strip())

        for activation_prop, (completed_prop, pending_var) in rewrites.items():
            left_candidate = f'!{activation_prop}'
            right_candidate = f"{completed_prop}'"
            if {lhs, rhs} != {left_candidate, right_candidate}:
                continue

            rewritten = f"(!{pending_var}) | {completed_prop}'"
            if comment_suffix:
                return rewritten + '  ' + comment_suffix
            return rewritten

        return expr

    def _split_top_level_or(self, text):
        """Split expression on top-level `|` and return `(left, right)`."""
        depth = 0
        for index, char in enumerate(text):
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == '|' and depth == 0:
                return text[:index], text[index + 1:]
        return None

    def _as_next_token(self, token):
        """Return a normalized next-step AP token like `move_corn_c'`."""
        cleaned = str(token)
        cleaned = re.sub(r'[\s()]', '', cleaned)
        cleaned = cleaned.rstrip("'")
        return f"{cleaned}'"


def main(inputs):
    """Create pending rewrite process instance for pipeline execution."""
    current_spec = {}
    if len(inputs) > 2:
        current_spec = inputs[2]

    return SlugsPendingSpecification(
        name='SlugsPendingSpecification',
        spec_name=inputs[0],
        system_capabilities=inputs[1],
        current_specification=current_spec,
    )
