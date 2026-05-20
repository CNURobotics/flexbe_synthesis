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

"""Tests for discrete-abstraction generation helpers."""

from flexbe_synthesis_generic.preprocesses.generate_discrete_abstraction import (
    GenerateDiscreteAbstraction,
)
import pytest
import yaml


def _generator():
    return GenerateDiscreteAbstraction(
        name='Generate Discrete Abstractions',
        system_name='demo',
        system_capabilities={},
        state_implementations_used={},
        behaviors_used={},
    )


def _capability():
    return {
        'interface': 'DemoState',
        'state': {
            'outcomes': {
                'done': {'remapping': 'completed'},
            },
        },
    }


def _behavior_capability():
    return {
        'interface': 'DemoBehavior',
        'behavior': {
            'outcomes': {
                'finished': {'remapping': 'completed'},
                'failed': {'remapping': 'failure'},
            },
        },
    }


# ── preprocess() ──────────────────────────────────────────────────────────────


def test_preprocess_requires_sm_outcome_mappings(tmp_path):
    """Discrete abstraction should fail on incomplete system capability shape."""
    generator = _generator()
    generator.synthesis_home = str(tmp_path)
    generator.system_capabilities = {
        'transition_outcomes': ['completed'],
        'capabilities': {'demo_capability': _capability()},
    }

    with pytest.raises(ValueError, match="'sm_outcome_mappings'"):
        generator.preprocess()


def test_preprocess_preserves_empty_sm_outcome_mappings(tmp_path):
    """Empty SM outcome mappings should stay empty instead of gaining defaults."""
    generator = _generator()
    generator.synthesis_home = str(tmp_path)
    generator.system_capabilities = {
        'sm_outcome_mappings': {},
        'transition_outcomes': ['completed'],
        'capabilities': {'demo_capability': _capability()},
    }

    generator.preprocess()

    output_file = tmp_path / 'demo' / 'configs' / 'demo_discrete_abstraction.yaml'
    assert 'output: {}\n' in output_file.read_text()


def test_preprocess_writes_correct_capability_entry(tmp_path):
    """Output YAML should contain the class_decl and outcome mapping for each capability."""
    generator = _generator()
    generator.synthesis_home = str(tmp_path)
    generator.system_capabilities = {
        'sm_outcome_mappings': {'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {
            'stand_cap': {
                'interface': 'StandState',
                'parameters': {'mode': 'stand'},
                'state': {
                    'outcomes': {
                        'done': {'remapping': 'completed'},
                    },
                },
            },
        },
    }

    generator.preprocess()

    data = yaml.safe_load(
        (tmp_path / 'demo' / 'configs' / 'demo_discrete_abstraction.yaml').read_text()
    )
    entry = data['stand_cap_a']
    assert entry['class_decl']['name'] == 'StandState'
    assert entry['class_decl']['parameters'] == {'mode': 'stand'}
    assert 'done' in entry['state_outcome_mapping']['stand_cap_c']
    assert entry['state_outcome_mapping']['stand_cap_f'] == []


def test_preprocess_writes_canonical_parsed_action_map(tmp_path):
    """Parsed action indexes should not depend on capability YAML insertion order."""
    generator = _generator()
    generator.synthesis_home = str(tmp_path)
    generator.system_capabilities = {
        'sm_outcome_mappings': {'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {
            'gr': _capability(),
            'bd': _capability(),
            'br': _capability(),
        },
    }

    generator.preprocess()

    data = yaml.safe_load(
        (tmp_path / 'demo' / 'configs' / 'demo_discrete_abstraction.yaml').read_text()
    )
    assert data['parsed_action_map']['capability'] == {
        1: 'bd_a',
        2: 'br_a',
        3: 'gr_a',
    }


def test_build_parsed_action_map_excludes_begin_game():
    """begin_game occupies slot 0 and is excluded from the map; real actions start at 1."""
    generator = _generator()
    generator.system_capabilities = {
        'capabilities': {
            'z_action': _capability(),
            'begin_game': _capability(),
            'a_action': _capability(),
        },
    }

    assert generator.build_parsed_action_map() == {
        1: 'a_action_a',
        2: 'z_action_a',
    }


def test_preprocess_excludes_begin_game_action_block(tmp_path):
    """begin_game should not be emitted as a steady-state SM action block."""
    generator = _generator()
    generator.synthesis_home = str(tmp_path)
    generator.system_capabilities = {
        'sm_outcome_mappings': {'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {
            'begin_game': _capability(),
            'work': _capability(),
        },
    }

    generator.preprocess()

    data = yaml.safe_load(
        (tmp_path / 'demo' / 'configs' / 'demo_discrete_abstraction.yaml').read_text()
    )
    assert data['parsed_action_map']['capability'] == {1: 'work_a'}
    assert 'work_a' in data
    assert 'begin_game_a' not in data


def test_preprocess_handles_behavior_backed_capability(tmp_path):
    """Preprocess must not crash on a behavior-backed capability."""
    generator = _generator()
    generator.synthesis_home = str(tmp_path)
    generator.system_capabilities = {
        'sm_outcome_mappings': {'finished': 'finished'},
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {'demo_behavior': _behavior_capability()},
    }

    generator.preprocess()

    data = yaml.safe_load(
        (tmp_path / 'demo' / 'configs' / 'demo_discrete_abstraction.yaml').read_text()
    )
    assert 'demo_behavior_a' in data
    class_decl = data['demo_behavior_a']['class_decl']
    assert class_decl['name'] == ':BEHAVIOR'
    assert class_decl['behavior_class'] == 'DemoBehavior'


# ── build_discrete_abstraction() ──────────────────────────────────────────────


def test_build_discrete_abstraction_returns_correct_structure():
    """build_discrete_abstraction produces class_decl, state_outcome_mapping, and autonomy."""
    generator = _generator()
    generator.system_capabilities = {
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {
            'stand_cap': {
                'interface': 'StandState',
                'parameters': {'mode': 'stand'},
                'autonomy': 2,
                'state': {
                    'outcomes': {
                        'done': {'remapping': 'completed'},
                        'failed': {'remapping': 'failure'},
                    },
                },
            },
        },
    }

    result = generator.build_discrete_abstraction('stand_cap')

    assert result['class_decl'] == {'name': 'StandState', 'parameters': {'mode': 'stand'}}
    assert result['autonomy'] == 2
    assert result['state_outcome_mapping'] == {
        'stand_cap_c': ['done'],
        'stand_cap_f': ['failed'],
    }
    assert 'userdata_in' not in result
    assert 'userdata_out' not in result


def test_build_discrete_abstraction_includes_nonempty_userdata():
    """Non-empty userdata_in/out are remapping-compressed and included."""
    generator = _generator()
    generator.system_capabilities = {
        'transition_outcomes': ['completed'],
        'capabilities': {
            'demo_cap': {
                'interface': 'DemoState',
                'userdata_in': {'pose': {'remapping': 'target_pose'}},
                'userdata_out': {'result': {'remapping': 'grasp_result'}},
                'state': {
                    'outcomes': {'done': {'remapping': 'completed'}},
                },
            },
        },
    }

    result = generator.build_discrete_abstraction('demo_cap')

    assert result['userdata_in'] == {'pose': 'target_pose'}
    assert result['userdata_out'] == {'result': 'grasp_result'}


def test_build_discrete_abstraction_empty_userdata_becomes_list():
    """Empty userdata_in/out dicts are stored as empty lists."""
    generator = _generator()
    generator.system_capabilities = {
        'transition_outcomes': ['completed'],
        'capabilities': {
            'demo_cap': {
                'interface': 'DemoState',
                'userdata_in': {},
                'userdata_out': {},
                'state': {
                    'outcomes': {'done': {'remapping': 'completed'}},
                },
            },
        },
    }

    result = generator.build_discrete_abstraction('demo_cap')

    assert result['userdata_in'] == []
    assert result['userdata_out'] == []


# ── build_state_outcome_mappings() ────────────────────────────────────────────


def test_build_state_outcome_mappings_state_backed():
    """State-backed capabilities map state outcomes to transition-outcome keys."""
    generator = _generator()
    generator.system_capabilities = {
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {'demo_cap': _capability()},
    }

    result = generator.build_state_outcome_mappings('demo_cap')

    assert result == {'demo_cap_c': ['done'], 'demo_cap_f': []}


def test_build_state_outcome_mappings_handles_behavior_capability():
    """Behavior-backed capabilities use behavior outcomes instead of state outcomes."""
    generator = _generator()
    generator.system_capabilities = {
        'transition_outcomes': ['completed', 'failure'],
        'capabilities': {'demo_behavior': _behavior_capability()},
    }

    result = generator.build_state_outcome_mappings('demo_behavior')

    assert result == {
        'demo_behavior_c': ['finished'],
        'demo_behavior_f': ['failed'],
    }


def test_build_state_outcome_mappings_raises_for_missing_interface_data():
    """A KeyError is raised when capability has neither 'state' nor 'behavior'."""
    generator = _generator()
    generator.system_capabilities = {
        'transition_outcomes': ['completed'],
        'capabilities': {'bad_cap': {'interface': 'Unknown'}},
    }

    with pytest.raises(KeyError, match='bad_cap'):
        generator.build_state_outcome_mappings('bad_cap')


# ── _resolve_autonomy() ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('autonomy_config', 'expected'),
    [
        (None, 1),
        (2, 2),
        ('3', 3),
        ({'done': 2, 'failed': '4'}, 4),
    ],
)
def test_resolve_autonomy_accepts_supported_shapes(autonomy_config, expected):
    """Autonomy accepts missing, scalar, and mapping configurations."""
    assert _generator()._resolve_autonomy('demo_capability', autonomy_config) == expected


@pytest.mark.parametrize(
    'autonomy_config',
    [
        [1, 2],
        1.5,
        {'done': 'soon'},
    ],
)
def test_resolve_autonomy_rejects_invalid_shapes(autonomy_config):
    """Invalid autonomy configurations should fail with capability context."""
    with pytest.raises((TypeError, ValueError), match="Invalid autonomy for 'demo'"):
        _generator()._resolve_autonomy('demo', autonomy_config)
