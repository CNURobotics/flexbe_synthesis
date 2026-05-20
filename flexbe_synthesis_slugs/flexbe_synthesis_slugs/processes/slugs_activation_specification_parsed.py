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

"""
Rewrite GR(1) capability activation specs to a parsed numeric action variable.

This process replaces one-hot `<capability>_a` propositions with a single
indexed variable (default: `capability`), updates init/transition/liveness
formulas accordingly, remaps per-capability outcomes (`*_c`, `*_f`, ...) to
generic outcome propositions derived from ``system_capabilities['transition_outcomes']``.
"""

import logging
import re

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.gr1_formula import strip_outer_parens
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
from flexbe_synthesis_slugs.processes.slugs_capability_specification import (
    ONEHOT_MUTEX_MARKER,
)

logger = logging.getLogger(__name__)


class SlugsActivationSpecificationParsed(BaseProcess):
    """Replace `<capability>_a` propositions with `(move_action=<index>)` formulas."""

    spec_name: str
    system_capabilities: dict
    current_specification: dict = {}
    action_variable_name: str = 'capability'

    def process(self):
        """Transform activation propositions in all GR(1) sections."""
        logger.info('Starting %s ...', self.name)

        gr1_spec = GR1Specification(self.spec_name)
        gr1_spec.merge_gr1_specification(self.current_specification)

        capabilities = self.system_capabilities.get('capabilities', {})
        current_sys_props = set(gr1_spec.sys_props)
        activation_props = [
            f'{capability_name}_a'
            for capability_name in sorted(capabilities.keys())
            if f'{capability_name}_a' in current_sys_props
        ]
        if not activation_props:
            print(
                '\033[33mNo capability activation props found; returning unchanged spec.\033[0m',
                flush=True,
            )
            return [gr1_spec.to_dict()]

        # begin_game always occupies slot 0 (startup only); real actions start at 1.
        begin_game_prop = 'begin_game_a'
        real_props = [p for p in activation_props if p != begin_game_prop]
        has_begin_game = len(real_props) < len(activation_props)
        action_map = {prop: idx for idx, prop in enumerate(real_props, start=1)}
        if has_begin_game:
            action_map[begin_game_prop] = 0

        max_index = len(real_props)  # real actions 1..N; slot 0 is always begin_game/null
        action_var_decl = f'{self.action_variable_name}:0...{max_index}'

        print(
            (
                f"Activation mapping for '{self.action_variable_name}' "
                f'(0=begin_game/null startup, real actions 1..{max_index}): {action_map}'
            ),
            flush=True,
        )

        gr1_spec.sys_props.difference_update(set(activation_props))
        gr1_spec.sys_props.add(action_var_decl)
        if has_begin_game:
            gr1_spec.sys_props.add('# 0: begin_game (startup only)')
        else:
            gr1_spec.sys_props.add('# 0: null (startup slot)')
        for activation_prop, action_index in action_map.items():
            if action_index > 0:
                gr1_spec.sys_props.add(f'# {action_index}: {activation_prop[:-2]}')
        gr1_spec.update_composite_props()

        gr1_spec.env_init = self._replace_ic_block(gr1_spec.env_init, action_map)
        gr1_spec.sys_init = self._replace_ic_block(gr1_spec.sys_init, action_map)

        gr1_spec.env_trans = [
            self._replace_activation_expr(expr, action_map) for expr in gr1_spec.env_trans
        ]
        gr1_spec.sys_trans = [
            self._replace_activation_expr(expr, action_map) for expr in gr1_spec.sys_trans
        ]
        gr1_spec.env_liveness = [
            self._replace_activation_expr(expr, action_map) for expr in gr1_spec.env_liveness
        ]
        gr1_spec.sys_liveness = [
            self._replace_activation_expr(expr, action_map) for expr in gr1_spec.sys_liveness
        ]
        self._rewrite_outcomes_to_generic(gr1_spec, action_map)
        self._rewrite_parsed_control_rules(gr1_spec, action_map)

        return [gr1_spec.to_dict()]

    def _replace_activation_expr(self, expr, action_map):
        """Replace activation variables in one formula string."""
        if not isinstance(expr, str):
            return expr

        if '#' in expr:
            raw_expr, comment = expr.split('#', 1)
            comment_suffix = '#' + comment
        else:
            raw_expr = expr
            comment_suffix = ''

        transformed = raw_expr
        for activation_prop, action_index in action_map.items():
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(activation_prop)}(')?(?![A-Za-z0-9_])"
            )

            def repl(match):
                prime = "'" if match.group(1) else ''
                return f'({self.action_variable_name}{prime}={action_index})'

            transformed = pattern.sub(repl, transformed)

        return transformed + comment_suffix

    def _replace_ic_block(self, block, action_map):
        """Replace formulas and adjust IC keys to avoid re-adding old `_a` props."""
        transformed = {}
        for key, expr in block.items():
            new_expr = self._replace_activation_expr(expr, action_map)
            transformed[self._replace_ic_key(key, action_map)] = new_expr
        return transformed

    def _replace_ic_key(self, key, action_map):
        """Replace activation variables in IC dictionary keys."""
        if isinstance(key, tuple):
            return tuple(self._replace_ic_key_token(token, action_map) for token in key)
        if isinstance(key, str):
            return self._replace_ic_key_token(key, action_map)
        return key

    def _replace_ic_key_token(self, token, action_map):
        """Map `<capability>_a` key tokens to the parsed variable name."""
        if token in action_map:
            return self.action_variable_name
        return token

    def _rewrite_parsed_control_rules(self, gr1_spec, action_map):
        """Normalize init + one-hot control rules for parsed numeric capability variable."""
        # Slot 0 is always the startup (begin_game if present, null otherwise).
        init_index = 0
        enforce_non_idle_rule = True  # capability must always be non-zero after startup

        # Keep non-capability init rules and force parsed init to the chosen index.
        filtered_sys_init = {}
        for key, expr in gr1_spec.sys_init.items():
            if self.action_variable_name in expr:
                continue
            filtered_sys_init[key] = expr
        filtered_sys_init[(self.action_variable_name,)] = (
            f'({self.action_variable_name}={init_index})'
            '  # Parsed capability initial state'
        )
        gr1_spec.sys_init = filtered_sys_init

        # Replace one-hot mutex expansion with one numeric non-idle rule.
        new_sys_trans = []
        in_onehot_block = False
        found_onehot_block = False
        for line in gr1_spec.sys_trans:
            stripped = line.strip()
            if stripped.startswith(ONEHOT_MUTEX_MARKER):
                in_onehot_block = True
                found_onehot_block = True
                new_sys_trans.append(line)
                if enforce_non_idle_rule:
                    new_sys_trans.append(
                        f"({self.action_variable_name}'!=0)  # parsed capability must be active"
                    )
                continue

            if in_onehot_block:
                if 'System Transition Relations' in stripped:
                    in_onehot_block = False
                    new_sys_trans.append(line)
                continue

            new_sys_trans.append(line)

        if not found_onehot_block:
            raise RuntimeError(
                f'Could not locate one-hot mutex block in sys_trans '
                f'(expected marker: {ONEHOT_MUTEX_MARKER!r}). '
                'The capability spec generator may have changed; '
                'check slugs_capability_specification.py.'
            )

        gr1_spec.sys_trans = new_sys_trans

    def _rewrite_outcomes_to_generic(self, gr1_spec, action_map):
        """Replace per-capability outcome APs (`*_c`,`*_f`) with generic `completed/failure`."""
        transition_outcomes = self.system_capabilities.get(
            'transition_outcomes',
            ['completed', 'failure'],
        )

        suffix_to_generic = {}
        for outcome in transition_outcomes:
            if not outcome:
                continue
            low = outcome.lower()
            if low.startswith('comp'):
                suffix_to_generic[outcome[0]] = 'completed'
            elif low.startswith('fail'):
                suffix_to_generic[outcome[0]] = 'failure'
            else:
                suffix_to_generic[outcome[0]] = low

        if not suffix_to_generic:
            return

        outcome_props_to_remove = set()
        for activation_prop in action_map:
            cap_name = activation_prop[:-2]
            for suffix in suffix_to_generic:
                outcome_props_to_remove.add(f'{cap_name}_{suffix}')

        gr1_spec.env_props.difference_update(outcome_props_to_remove)
        gr1_spec.env_props.update(set(suffix_to_generic.values()))
        gr1_spec.update_composite_props()

        # Replace old outcome init entries with generic outcome ICs.
        new_env_init = {}
        for key, expr in gr1_spec.env_init.items():
            vars_in_key = key if isinstance(key, tuple) else (key,)
            if any(var in outcome_props_to_remove for var in vars_in_key):
                continue
            new_env_init[key] = expr
        for generic_name in dict.fromkeys(suffix_to_generic.values()):
            new_env_init[(generic_name,)] = f'!{generic_name}  # generic outcome IC'
        gr1_spec.env_init = new_env_init

        def replace_expr(expr):
            if not isinstance(expr, str):
                return expr
            if '#' in expr:
                raw_expr, comment = expr.split('#', 1)
                comment_suffix = '#' + comment
            else:
                raw_expr = expr
                comment_suffix = ''

            transformed = raw_expr
            for activation_prop, action_index in action_map.items():
                cap_name = activation_prop[:-2]
                for suffix, generic_var in suffix_to_generic.items():
                    token = f'{cap_name}_{suffix}'
                    pattern = re.compile(
                        rf"(?<![A-Za-z0-9_]){re.escape(token)}(')?(?![A-Za-z0-9_])"
                    )
                    transformed = pattern.sub(
                        (
                            f'(({self.action_variable_name}={action_index}) '
                            f"& {generic_var}')"
                        ),
                        transformed,
                    )

            transformed = self._rewrite_outcome_implication_rhs(
                transformed, list(suffix_to_generic.values())
            )
            transformed = self._simplify_duplicate_capability_rhs(transformed)
            if transformed is None:
                return None
            if comment_suffix:
                return transformed.rstrip() + ' ' + comment_suffix
            return transformed

        gr1_spec.env_trans = [
            line
            for line in (replace_expr(expr) for expr in gr1_spec.env_trans)
            if line is not None
        ]
        gr1_spec.sys_trans = [replace_expr(expr) for expr in gr1_spec.sys_trans]
        gr1_spec.env_liveness = [replace_expr(expr) for expr in gr1_spec.env_liveness]
        gr1_spec.sys_liveness = [replace_expr(expr) for expr in gr1_spec.sys_liveness]
        generic_names = list(dict.fromkeys(suffix_to_generic.values()))
        self._add_generic_outcome_uniqueness(gr1_spec, generic_names)

    def _add_generic_outcome_uniqueness(self, gr1_spec, generic_names):
        """Add ENV safety enforcing mutual exclusion among generic outcome APs."""
        if len(generic_names) < 2:
            return

        uniqueness_lines = ['# outcome uniqueness always']
        for index, name_a in enumerate(generic_names):
            for name_b in generic_names[index + 1:]:
                uniqueness_lines.append(f"!({name_a}' & {name_b}')")

        insert_at = len(gr1_spec.env_trans)
        for idx, line in enumerate(gr1_spec.env_trans):
            if isinstance(line, str) and 'Environment Preconditions' in line:
                insert_at = idx
                break

        gr1_spec.env_trans[insert_at:insert_at] = uniqueness_lines

    def _rewrite_outcome_implication_rhs(self, expr, generic_names=None):
        """If implication is based on next-step outcome, target next-step capability."""
        if '->' not in expr:
            return expr

        lhs, rhs = expr.split('->', 1)
        if generic_names is None:
            generic_names = ['completed', 'failure']
        if not any(f"{name}'" in lhs for name in generic_names):
            return expr

        rhs = re.sub(
            rf'\(\s*{re.escape(self.action_variable_name)}\s*=\s*(\d+)\s*\)',
            rf"({self.action_variable_name}'=\1)",
            rhs,
            count=1,
        )
        return lhs + '->' + rhs

    def _simplify_duplicate_capability_rhs(self, expr):
        """Simplify duplicate capability checks introduced by parsed outcome rewrite."""
        if '->' not in expr:
            return expr

        lhs_raw, rhs_raw = expr.split('->', 1)
        lhs = strip_outer_parens(lhs_raw.strip())
        rhs = strip_outer_parens(rhs_raw.strip())
        lhs = self._normalize_negated_parens(lhs)
        rhs = self._normalize_negated_parens(rhs)

        cap = re.escape(self.action_variable_name)

        # (cap=i) -> ((cap=i) & completed')  ==>  (cap=i) -> completed'
        lhs_match = re.match(rf'^{cap}\s*=\s*(\d+)$', lhs)
        rhs_match = re.match(rf'^\(\s*{cap}\s*=\s*(\d+)\s*\)\s*&\s*(.+)$', rhs)
        if lhs_match and rhs_match and lhs_match.group(1) == rhs_match.group(1):
            index = lhs_match.group(1)
            rhs_term = rhs_match.group(2).strip()
            return f'({self.action_variable_name}={index}) -> {rhs_term}'

        # !(cap=i) -> !((cap=i) & completed') is tautological; drop it.
        lhs_match = re.match(rf'^!\(\s*{cap}\s*=\s*(\d+)\s*\)$', lhs)
        rhs_match = re.match(rf'^!\(\(\s*{cap}\s*=\s*(\d+)\s*\)\s*&\s*.+\)$', rhs)
        if lhs_match and rhs_match and lhs_match.group(1) == rhs_match.group(1):
            return None

        # (cap=i) -> (((cap=i) & A) | ((cap=i) & B)) ==> (cap=i) -> (A | B)
        duplicate_capability_or = (
            rf'^\(\s*{cap}\s*=\s*(\d+)\s*\)\s*->'
            rf'\s*\(\(\(\s*{cap}\s*=\s*\1\s*\)\s*&\s*(.+?)\)'
            rf'\s*\|\s*\(\(\s*{cap}\s*=\s*\1\s*\)\s*&\s*(.+?)\)\)\s*$'
        )
        pattern_or = re.match(duplicate_capability_or, expr)
        if pattern_or:
            index = pattern_or.group(1)
            term_a = pattern_or.group(2).strip()
            term_b = pattern_or.group(3).strip()
            return f'({self.action_variable_name}={index}) -> ({term_a} | {term_b})'

        # (cap=i) -> !(((cap=i) & A) & ((cap=i) & B)) ==> (cap=i) -> !(A & B)
        duplicate_capability_and_negation = (
            rf'^\(\s*{cap}\s*=\s*(\d+)\s*\)\s*->\s*!'
            rf'\(\(\(\s*{cap}\s*=\s*\1\s*\)\s*&\s*(.+?)\)'
            rf'\s*&\s*\(\(\s*{cap}\s*=\s*\1\s*\)\s*&\s*(.+?)\)\)\s*$'
        )
        pattern_and_neg = re.match(duplicate_capability_and_negation, expr)
        if pattern_and_neg:
            index = pattern_and_neg.group(1)
            term_a = pattern_and_neg.group(2).strip()
            term_b = pattern_and_neg.group(3).strip()
            return f'({self.action_variable_name}={index}) -> !({term_a} & {term_b})'

        return expr

    def _normalize_negated_parens(self, text):
        """Normalize negated wrapper expressions like `!((x))` to `!(x)`."""
        text = text.strip()
        if text.startswith('!'):
            inner = strip_outer_parens(text[1:].strip())
            return f'!({inner})'
        return text


def main(inputs):
    """Create parsed activation-conversion process instance."""
    current_spec = {}
    if len(inputs) > 2:
        current_spec = inputs[2]

    action_variable_name = 'capability'
    if len(inputs) > 3 and isinstance(inputs[3], str) and inputs[3]:
        action_variable_name = inputs[3]

    return SlugsActivationSpecificationParsed(
        name='SlugsActivationSpecificationParsed',
        spec_name=inputs[0],
        system_capabilities=inputs[1],
        current_specification=current_spec,
        action_variable_name=action_variable_name,
    )
