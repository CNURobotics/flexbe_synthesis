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

"""Focused tests for GR(1) expression helper parsing."""

from flexbe_synthesis_slugs.helpers.gr1_formula import (
    extract_leaf_expressions,
    get_vars_from_eqn,
    split_top_level,
)


def test_split_top_level_ignores_nested_operators():
    """Top-level splitting should leave parenthesized sub-expressions intact."""
    assert split_top_level('(a | b) & (next(c) -> d)') == [
        '(a | b)',
        '&',
        '(next(c) -> d)',
    ]


def test_split_top_level_prefers_multi_character_operators():
    """Implication operators should not be split as shorter token fragments."""
    assert split_top_level('a <-> b -> c') == ['a', '<->', 'b', '->', 'c']


def test_extract_leaf_expressions_unwraps_negated_composites():
    """Negated grouped formulas should expose normalized atomic leaves."""
    assert extract_leaf_expressions('!((a & !b) | next(c=1))') == [
        'a',
        'b',
        'next(c=1)',
    ]


def test_extract_leaf_expressions_strips_comments():
    """Inline comments are metadata, not part of the formula leaves."""
    assert extract_leaf_expressions('a & b # comment with c') == ['a', 'b']


def test_get_vars_from_eqn_handles_next_primes_and_comparisons():
    """Variable extraction should normalize next(), primes, and value comparisons."""
    assert get_vars_from_eqn("!(next(item=1) & select_m') -> !soda_a'") == [
        'item',
        'select_m',
        'soda_a',
    ]


def test_get_vars_from_eqn_preserves_first_seen_order():
    """Callers rely on deterministic variable ordering from left to right."""
    assert get_vars_from_eqn('(ready & !ready) | next(mode!=idle)') == [
        'ready',
        'ready',
        'mode',
    ]
