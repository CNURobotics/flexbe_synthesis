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

"""Tests for concurrent state generation helpers."""

from flexbe_synthesis_slugs.helpers.sm_gen.concurrent_state_generator import (
    ConcurrentStateGenerator,
)
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_util import new_si
import pytest


def test_add_internal_outcome_and_transition_treats_string_as_one_outcome():
    """Single outcome strings should not be iterated character by character."""
    generator = ConcurrentStateGenerator('demo')

    generator.add_internal_outcome_and_transition('done', 'next', [1])

    assert generator.internal_outcomes == ['done']
    assert generator.internal_transitions == ['next']
    assert generator.outcome_to_autonomy_list == {'done': [1]}


def test_add_internal_outcome_and_transition_accepts_outcome_lists():
    """Outcome lists remain supported for callers that pass multiple outcomes."""
    generator = ConcurrentStateGenerator('demo')

    generator.add_internal_outcome_and_transition(['done', 'failed'], 'next', [1])

    assert generator.internal_outcomes == ['done', 'failed']
    assert generator.internal_transitions == ['next', 'next']
    assert generator.outcome_to_autonomy_list == {
        'done': [1],
        'failed': [1],
    }


def test_new_si_rejects_at_prefix_parameter_names():
    """`@` belongs in parameter values, not parameter names."""
    with pytest.raises(ValueError, match='Use @ only in parameter values'):
        new_si(
            '/demo',
            'DemoState',
            '',
            ['done'],
            ['finished'],
            None,
            {'@target': "'value'"},
        )


def test_new_si_rejects_sets_for_paired_outcomes_and_transitions():
    """Paired outcomes/transitions must preserve caller-provided alignment."""
    with pytest.raises(TypeError, match='ordered sequences'):
        new_si(
            '/demo',
            'DemoState',
            '',
            {'done', 'failed'},
            {'finished', 'failed'},
            None,
            {},
        )


def test_new_si_allows_top_level_outcome_set_without_transitions():
    """Top-level SM outcomes are unpaired and may still be normalized from a set."""
    state = new_si(
        '/',
        ':STATEMACHINE',
        '',
        {'finished', 'failed'},
        [],
        'first',
        {},
    )

    assert state.outcomes == ['failed', 'finished']
    assert state.transitions == []
