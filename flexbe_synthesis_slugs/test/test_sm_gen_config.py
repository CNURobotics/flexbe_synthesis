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

"""Tests for state-machine generation configuration helpers."""

from flexbe_synthesis_slugs.helpers.slugs_automaton import (
    SlugsAutomaton,
    SlugsAutomatonState,
)
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_config import SMGenConfig
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_error import SMGenError
import pytest


def test_get_init_states_removes_null_bootstrap_and_promotes_successor():
    """A null-bootstrap initial state with no SM output is removed; its successor is returned."""
    bootstrap = SlugsAutomatonState(
        name='bootstrap',
        output_valuation=0,
        transitions=['real'],
    )
    bootstrap.is_initial = True
    real = SlugsAutomatonState(
        name='real',
        output_valuation=1,
        transitions=['real'],
    )
    automaton = SlugsAutomaton(states=[bootstrap, real])
    automaton.update_state_map()

    config = SMGenConfig({'output': {}}, [], [], automaton)

    assert config.get_init_states() == ['real']
    assert automaton['bootstrap'] is None
    assert automaton['real'].incoming == ['real']


def test_get_init_states_returns_real_initial_state_directly():
    """A real initial state with an SM output variable is returned without removal."""
    init = SlugsAutomatonState(name='init', output_valuation=1, transitions=['next'])
    init.is_initial = True
    init.output_variables = ['start_a']
    nxt = SlugsAutomatonState(name='next', output_valuation=2, transitions=[])

    automaton = SlugsAutomaton(states=[init, nxt])
    automaton.update_state_map()

    config = SMGenConfig({'output': {}}, [], [], automaton)

    assert config.get_init_states() == ['init']
    assert automaton['init'] is not None


def test_get_init_states_removes_initial_state_with_only_non_sm_outputs():
    """A decoded initial state with only memory/pending outputs is still bootstrap."""
    bootstrap = SlugsAutomatonState(
        name='bootstrap',
        output_valuation=4,
        transitions=['real'],
    )
    bootstrap.is_initial = True
    bootstrap.output_values = {'step_m': True}
    real = SlugsAutomatonState(
        name='real',
        output_valuation=1,
        transitions=['real'],
    )
    real.output_variables = ['step_a']

    automaton = SlugsAutomaton(states=[bootstrap, real])
    automaton.update_state_map()

    config = SMGenConfig({'output': {}}, [], [], automaton)

    assert config.get_init_states() == ['real']
    assert automaton['bootstrap'] is None


def test_get_init_states_raises_when_no_initial_state_tagged():
    """get_init_states must raise SMGenError when no state carries is_initial."""
    state = SlugsAutomatonState(name='orphan', output_valuation=1, transitions=[])
    automaton = SlugsAutomaton(states=[state])
    automaton.update_state_map()

    config = SMGenConfig({'output': {}}, [], [], automaton)

    import pytest
    with pytest.raises(SMGenError):
        config.get_init_states()


def test_get_transitions_preserves_self_transition_conditions():
    """Self loops with response conditions should be emitted for SM generation."""
    state = SlugsAutomatonState(
        name='1_bd',
        output_valuation=1,
        transitions=['1_bd', '2_gr'],
    )
    state.output_variables = ['bd_a']
    state.input_variables = ['bd_f', 'br_c']

    next_state = SlugsAutomatonState(name='2_gr', output_valuation=2)
    next_state.input_variables = ['bd_c', 'gr_f']

    automaton = SlugsAutomaton(states=[state, next_state])
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'bd_a': {
                'class_decl': {'name': 'ButtonState', 'parameters': {}},
                'state_outcome_mapping': {
                    'bd_c': 'button',
                    'bd_f': 'fail',
                },
            },
            'br_a': {
                'class_decl': {'name': 'BrewState', 'parameters': {}},
                'state_outcome_mapping': {'br_c': 'brew'},
            },
            'gr_a': {
                'class_decl': {'name': 'GrindState', 'parameters': {}},
                'state_outcome_mapping': {'gr_f': 'fail'},
            },
        },
        ['bd_c', 'bd_f', 'br_c', 'gr_f'],
        ['bd_a', 'br_a', 'gr_a'],
        automaton,
    )

    assert config.get_transitions(state) == {
        '1_bd': ['bd_f'],
        '2_gr': ['bd_c'],
    }


def test_get_transitions_drops_self_transition_without_response_condition():
    """Self loops without an active capability response are treated as stutter."""
    state = SlugsAutomatonState(
        name='1_bd',
        output_valuation=1,
        transitions=['1_bd', '2_gr'],
    )
    state.output_variables = ['bd_a']
    state.input_variables = ['sensor_ready']

    next_state = SlugsAutomatonState(name='2_gr', output_valuation=2)
    next_state.input_variables = ['bd_c']

    automaton = SlugsAutomaton(states=[state, next_state])
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'bd_a': {
                'class_decl': {'name': 'ButtonState', 'parameters': {}},
                'state_outcome_mapping': {'bd_c': 'button'},
            },
        },
        ['bd_c', 'sensor_ready'],
        ['bd_a'],
        automaton,
    )

    assert config.get_transitions(state) == {'2_gr': ['bd_c']}


def test_get_transitions_maps_generic_failure_input_value_to_response():
    """Generic failure stored in input_values should become the active fail response."""
    state = SlugsAutomatonState(
        name='1',
        output_valuation=8,
        transitions=['1', '2'],
    )
    state.output_values = {'capability': 1, 'bd_p': True}

    retry_state = SlugsAutomatonState(name='1', input_valuation=2)
    retry_state.input_values = {'failure': True}
    retry_state.output_values = {'capability': 1, 'bd_p': True}

    next_state = SlugsAutomatonState(name='2', input_valuation=1)
    next_state.input_variables = ['completed']

    automaton = SlugsAutomaton(
        output_variables=['capability@0', 'bd_p'],
        input_variables=['completed', 'failure'],
        states=[retry_state, next_state],
    )
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'parsed_action_map': {'capability': {1: 'bd_a'}},
            'bd_a': {
                'class_decl': {'name': 'ButtonState', 'parameters': {}},
                'state_outcome_mapping': {
                    'bd_c': 'button',
                    'bd_f': 'fail',
                },
            },
        },
        ['completed', 'failure'],
        ['capability@0', 'capability@1', 'bd_p'],
        automaton,
    )

    assert config.get_transitions(state) == {
        '1': ['bd_f'],
        '2': ['bd_c'],
    }


def test_get_transitions_remaps_forward_collision_when_target_carries_failure_flag():
    """
    Forward-forward collision: both outgoing edges initially share the same condition.

    Reproduces the '0_bd -> 1_bd / 0_bd -> 2_gr' ambiguity after reduction.
    State '0_bd' (bd_a, no pending bit) transitions to:
      - '1_bd': the failure-representative merged state;
                input_values={'failure': True} AND input_variables=['completed'] (from merge)
      - '2_gr': the completion target; input_variables=['completed']
    Both initially map to 'bd_c'.  Post-processing must remap '1_bd' to 'bd_f'.
    """
    source = SlugsAutomatonState(
        name='0_bd',
        output_valuation=1,
        transitions=['1_bd', '2_gr'],
    )
    source.output_values = {'capability': 1}

    failure_target = SlugsAutomatonState(name='1_bd', input_valuation=2)
    failure_target.input_variables = ['completed']   # merged from the completed-representative
    failure_target.input_values = {'failure': True}  # original failure-representative value
    failure_target.output_values = {'capability': 1, 'bd_p': True}

    completed_target = SlugsAutomatonState(name='2_gr', input_valuation=1)
    completed_target.input_variables = ['completed']
    completed_target.output_values = {'capability': 3}

    automaton = SlugsAutomaton(
        output_variables=['capability@0', 'capability@1', 'bd_p'],
        input_variables=['completed', 'failure'],
        states=[source, failure_target, completed_target],
    )
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'parsed_action_map': {'capability': {1: 'bd_a', 2: 'br_a', 3: 'gr_a'}},
            'bd_a': {
                'class_decl': {'name': 'ButtonState', 'parameters': {}},
                'state_outcome_mapping': {'bd_c': 'button', 'bd_f': 'fail'},
            },
            'br_a': {
                'class_decl': {'name': 'BrewState', 'parameters': {}},
                'state_outcome_mapping': {'br_c': 'brew', 'br_f': 'fail'},
            },
            'gr_a': {
                'class_decl': {'name': 'GrindState', 'parameters': {}},
                'state_outcome_mapping': {'gr_c': 'grind', 'gr_f': 'fail'},
            },
        },
        ['completed', 'failure'],
        ['capability@0', 'capability@1', 'bd_p'],
        automaton,
    )

    assert config.get_transitions(source) == {
        '1_bd': ['bd_f'],
        '2_gr': ['bd_c'],
    }


def test_get_transitions_forward_target_failure_flag_does_not_contaminate_edge():
    """
    Forward target's input_values must not bleed onto incoming transition conditions.

    Reproduces the '4_br -> 1_bd' bug in the coffee automaton: state '1_bd' was the
    failure representative after reduction so its input_values={'failure': True}.
    That flag belongs to the 1_bd self-loop (retry), not to the forward edge from 4_br.
    With the guard in place only 'br_c' (completed) should appear on the forward edge.
    """
    source_state = SlugsAutomatonState(
        name='4_br',
        output_valuation=8,
        transitions=['1_bd', '4_br'],
    )
    source_state.output_values = {'capability': 2, 'gr_m': True}

    # Self-transition target for 4_br: merged 'completed' representative — no failure flag.
    self_state = SlugsAutomatonState(name='4_br', input_valuation=1)
    self_state.input_variables = ['completed']
    self_state.output_values = {'capability': 2, 'gr_m': True}

    # Forward target for 4_br: 1_bd carries both the completed condition (input_variables)
    # and the failure flag (input_values) — the latter must NOT bleed onto this edge.
    forward_target = SlugsAutomatonState(name='1_bd', input_valuation=2)
    forward_target.input_variables = ['completed']
    forward_target.input_values = {'failure': True}
    forward_target.output_values = {'capability': 1, 'bd_p': True}

    automaton = SlugsAutomaton(
        output_variables=['capability@0', 'capability@1', 'bd_p', 'gr_m'],
        input_variables=['completed', 'failure'],
        states=[self_state, forward_target],
    )
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'parsed_action_map': {'capability': {1: 'bd_a', 2: 'br_a'}},
            'bd_a': {
                'class_decl': {'name': 'ButtonState', 'parameters': {}},
                'state_outcome_mapping': {'bd_c': 'button', 'bd_f': 'fail'},
            },
            'br_a': {
                'class_decl': {'name': 'BrewState', 'parameters': {}},
                'state_outcome_mapping': {'br_c': 'brew', 'br_f': 'fail'},
            },
        },
        ['completed', 'failure'],
        ['capability@0', 'capability@1', 'bd_p', 'gr_m'],
        automaton,
    )

    assert config.get_transitions(source_state) == {
        '4_br': ['br_f'],
        '1_bd': ['br_c'],
    }


def test_get_transitions_remaps_self_when_completed_representative_merges_failure_state():
    """
    Remap self-transition when the completed representative has no failure flag.

    Covers states like '2' (gr_a) and '4' (br_a) in the coffee automaton where the
    reducer keeps the 'completed' variant as the representative (input_values={}).
    Both self and forward transitions initially map to the same condition ('gr_c'),
    so the post-processing in get_transitions must remap the self-loop to 'gr_f'.
    """
    state = SlugsAutomatonState(
        name='2',
        output_valuation=70,
        transitions=['2', '4'],
    )
    state.output_values = {'capability': 3, 'bd_m': True, 'gr_p': True}

    # Self-transition target: merged representative is the 'completed' state — no failure flag.
    self_state = SlugsAutomatonState(name='2', input_valuation=1)
    self_state.input_variables = ['completed']
    self_state.output_values = {'capability': 3, 'bd_m': True, 'gr_p': True}

    next_state = SlugsAutomatonState(name='4', input_valuation=1)
    next_state.input_variables = ['completed']

    automaton = SlugsAutomaton(
        output_variables=['capability@0', 'capability@1', 'bd_m', 'bd_p', 'br_p', 'gr_m', 'gr_p'],
        input_variables=['completed', 'failure'],
        states=[self_state, next_state],
    )
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'parsed_action_map': {'capability': {1: 'bd_a', 2: 'br_a', 3: 'gr_a'}},
            'bd_a': {
                'class_decl': {'name': 'OperatorDecisionState', 'parameters': {}},
                'state_outcome_mapping': {'bd_c': ['button'], 'bd_f': ['fail']},
                'autonomy': 3,
            },
            'br_a': {
                'class_decl': {'name': 'OperatorDecisionState', 'parameters': {}},
                'state_outcome_mapping': {'br_c': ['brew'], 'br_f': ['fail']},
                'autonomy': 3,
            },
            'gr_a': {
                'class_decl': {'name': 'OperatorDecisionState', 'parameters': {}},
                'state_outcome_mapping': {'gr_c': ['grind'], 'gr_f': ['fail']},
                'autonomy': 3,
            },
        },
        ['completed', 'failure'],
        ['capability@0', 'capability@1', 'bd_m', 'bd_p', 'br_p', 'gr_m', 'gr_p'],
        automaton,
    )

    assert config.get_transitions(state) == {
        '2': ['gr_f'],
        '4': ['gr_c'],
    }


def test_get_transitions_maps_nonstandard_generic_outcome_to_active_response():
    """Parsed generic outcomes beyond completed/failure should map to active responses."""
    state = SlugsAutomatonState(
        name='1',
        output_valuation=1,
        transitions=['2'],
    )
    state.output_values = {'capability': 1}

    waiting_state = SlugsAutomatonState(name='2', input_valuation=4)
    waiting_state.input_variables = ['waiting']

    automaton = SlugsAutomaton(
        output_variables=['capability@0'],
        input_variables=['completed', 'failure', 'waiting'],
        states=[state, waiting_state],
    )
    automaton.update_state_map()

    config = SMGenConfig(
        {
            'output': {},
            'parsed_action_map': {'capability': {1: 'step_a'}},
            'step_a': {
                'class_decl': {'name': 'StepState', 'parameters': {}},
                'state_outcome_mapping': {
                    'step_c': ['done'],
                    'step_f': ['failed'],
                    'step_w': ['waiting'],
                },
                'autonomy': 1,
            },
        },
        ['completed', 'failure', 'waiting'],
        ['capability@0'],
        automaton,
    )

    assert config.get_transitions(state) == {'2': ['step_w']}


def _parsed_config(parsed_action_map=None):
    config = {
        'output': {},
        'parsed_action_map': {
            'capability': parsed_action_map or {
                1: 'bd_a',
                2: 'br_a',
                3: 'gr_a',
            },
        },
        'gr_a': {
            'class_decl': {'name': 'GrindState', 'parameters': {}},
            'state_outcome_mapping': {'gr_c': ['done']},
        },
        'bd_a': {
            'class_decl': {'name': 'BrewDrinkState', 'parameters': {}},
            'state_outcome_mapping': {'bd_c': ['done']},
        },
        'br_a': {
            'class_decl': {'name': 'BrewRegularState', 'parameters': {}},
            'state_outcome_mapping': {'br_c': ['done']},
        },
    }
    return config


def test_parsed_action_map_overrides_discrete_abstraction_order():
    """Parsed action decoding should use the explicit map, not YAML insertion order."""
    automaton = SlugsAutomaton()

    config = SMGenConfig(
        _parsed_config(),
        [],
        ['capability:0...3'],
        automaton,
    )

    assert config.parsed_action_index == {
        'bd_a': 1,
        'br_a': 2,
        'gr_a': 3,
    }
    assert config.parsed_index_to_action == {
        1: 'bd_a',
        2: 'br_a',
        3: 'gr_a',
    }


def test_parsed_action_output_requires_explicit_map():
    """Parsed automata should fail instead of deriving a second implicit ordering."""
    automaton = SlugsAutomaton()
    config = _parsed_config()
    del config['parsed_action_map']

    with pytest.raises(SMGenError):
        SMGenConfig(config, [], ['capability:0...3'], automaton)


def test_parsed_action_map_must_match_actions_exactly():
    """A stale parsed map should be rejected before state-machine generation."""
    automaton = SlugsAutomaton()

    with pytest.raises(SMGenError):
        SMGenConfig(
            _parsed_config({1: 'bd_a', 2: 'br_a', 3: 'missing_a'}),
            [],
            ['capability:0...3'],
            automaton,
        )
