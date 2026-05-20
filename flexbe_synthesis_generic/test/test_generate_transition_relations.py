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

"""Tests for transition-relation generation helpers."""

from flexbe_synthesis_generic.preprocesses.generate_transition_relations import (
    extract_variables,
    GenerateTransitionRelations,
    main,
)
import pytest
import yaml


def _make_system_caps(capabilities):
    return {
        'sm_outcome_mappings': {'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': capabilities,
    }


def _state_cap(outcomes=None, **kwargs):
    cap = {
        'interface': 'DemoState',
        'state': {
            'outcomes': outcomes or {'done': {'remapping': 'completed'}},
        },
    }
    cap.update(kwargs)
    return cap


def _make_generator(system_capabilities, tmp_path):
    gen = GenerateTransitionRelations(
        name='Generate Transition Relations',
        system_name='demo',
        system_capabilities=system_capabilities,
        state_implementations_used={},
        behaviors_used={},
        workspace_data={},
    )
    gen.synthesis_home = str(tmp_path)
    return gen


def _run(capabilities, tmp_path):
    gen = _make_generator(_make_system_caps(capabilities), tmp_path)
    gen.preprocess()
    return yaml.safe_load(
        (tmp_path / 'demo' / 'configs' / 'demo_transition_relations.yaml').read_text()
    )


# ── extract_variables() ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('condition', 'expected'),
    [
        ('', []),
        ('item', ['item']),
        ('!item', ['item']),
        ('a&b', ['a', 'b']),
        ('a|b', ['a', 'b']),
        ('a|b|c', ['a', 'b', 'c']),
        ('a&!b', ['a', 'b']),
        ('item=1', ['item']),
        ('item!=1', ['item']),
        ('(item)', ['item']),
        ('  item  ', ['item']),
        # Outer-paren stripping: negation inside wrapping parens was previously broken.
        ('(!a)', ['a']),
        ('(!a|b)', ['a', 'b']),
        ('(!a&b)', ['a', 'b']),
        # Nested outer parens unwrap correctly.
        ('((a))', ['a']),
        # Non-outer parens fall through to & / | splitting.
        ('(a|b)&c', ['a', 'b', 'c']),
        ('(a|b)&(c|d)', ['a', 'b', 'c', 'd']),
    ],
)
def test_extract_variables(condition, expected):
    """extract_variables returns the variable names from a boolean condition string."""
    assert extract_variables(condition) == expected


# ── _transition_target_name() ─────────────────────────────────────────────────


def test_transition_target_name_returns_stripped_plain_string():
    assert GenerateTransitionRelations._transition_target_name('  target  ') == 'target'


def test_transition_target_name_at_prefix_returns_none():
    """@-prefixed postconditions are variable references, not capability targets."""
    assert GenerateTransitionRelations._transition_target_name('@some_var') is None


def test_transition_target_name_bang_prefix_strips_negation():
    assert GenerateTransitionRelations._transition_target_name('!cap_name') == 'cap_name'


def test_transition_target_name_non_string_raises_type_error():
    with pytest.raises(TypeError):
        GenerateTransitionRelations._transition_target_name(42)


# ── preprocess() – output content ─────────────────────────────────────────────


def test_preprocess_writes_transition_relations(tmp_path):
    """Explicit transition_relation entries are written under transition_relations."""
    caps = {
        'choose': _state_cap(
            transition_relation={'completed': ['use_item']},
        ),
        'use_item': _state_cap(),
    }

    data = _run(caps, tmp_path)

    assert data['transition_relations']['choose'] == {'completed': ['use_item']}
    assert data['transition_relations']['use_item'] == []


def test_preprocess_raises_for_unknown_transition_target(tmp_path):
    """Transitions to undefined capabilities or SM outcomes raise ValueError."""
    caps = {
        'choose': _state_cap(
            transition_relation={'completed': ['no_such_capability']},
        ),
    }
    gen = _make_generator(_make_system_caps(caps), tmp_path)

    with pytest.raises(ValueError, match='no_such_capability'):
        gen.preprocess()


def test_preprocess_variable_postcondition_skipped_in_transition_validation(tmp_path):
    """@-prefixed postconditions are variable references and must not raise."""
    caps = {
        'choose': _state_cap(
            transition_relation={'completed': ['@item']},
        ),
    }

    data = _run(caps, tmp_path)

    assert data['transition_relations']['choose'] == {'completed': []}


def test_preprocess_writes_preconditions(tmp_path):
    """Declared preconditions appear in action_preconditions for the capability."""
    caps = {
        'step_a': _state_cap(),
        'step_b': _state_cap(preconditions=['step_a']),
    }

    data = _run(caps, tmp_path)

    assert 'step_a' in data['action_preconditions']['step_b']
    assert data['action_preconditions']['step_a'] == []


def test_preprocess_writes_postconditions(tmp_path):
    """Declared postconditions appear in action_postconditions under the outcome key."""
    caps = {
        'step_a': _state_cap(
            postconditions={'completed': ['mode=ready']},
        ),
    }

    data = _run(caps, tmp_path)

    assert 'mode=ready' in data['action_postconditions']['step_a']['completed']


def test_preprocess_writes_unmet_preconditions(tmp_path):
    """Preconditions with no matching postcondition provider are written to unmet_needs."""
    caps = {
        'step_a': _state_cap(preconditions=['missing_thing']),
    }

    data = _run(caps, tmp_path)

    assert 'missing_thing' in data['unmet_needs']


def test_preprocess_handles_behavior_backed_capability(tmp_path):
    """Transition relations must not crash on a behavior-backed capability."""
    system_caps = {
        'sm_outcome_mappings': {'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {
            'demo_behavior': {
                'interface': 'DemoBehavior',
                'behavior': {
                    'outcomes': {
                        'finished': {'remapping': 'completed'},
                        'failed': {'remapping': 'failure'},
                    },
                },
            },
        },
    }
    gen = _make_generator(system_caps, tmp_path)

    gen.preprocess()

    data = yaml.safe_load(
        (tmp_path / 'demo' / 'configs' / 'demo_transition_relations.yaml').read_text()
    )
    assert 'demo_behavior' in data['transition_relations']
    assert 'demo_behavior' in data['action_preconditions']


# ── main() ────────────────────────────────────────────────────────────────────


def test_main_uses_behaviors_used_field_name():
    """Transition generator should expose the same behavior field name as inputs."""
    behaviors_used = {'DemoBehavior': {'discrete_abstractions': ['demo']}}

    generator = main(
        [
            'demo_system',
            {'capabilities': {}, 'sm_outcome_mappings': {}},
            {},
            behaviors_used,
            {'states': {}, 'behaviors': {}},
        ]
    )

    assert isinstance(generator, GenerateTransitionRelations)
    assert generator.behaviors_used is behaviors_used
    assert not hasattr(generator, 'behavior_implementations_used')
