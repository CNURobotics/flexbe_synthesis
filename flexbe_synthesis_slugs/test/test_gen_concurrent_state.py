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
Tests for ConcurrentStateGenerator.gen().

Multi-state case: gen() returns [container_si, sub_si_1, ...] where the container
uses CLASS_CONCURRENCY with cond_outcome/cond_transition, and each sub-state is a
proper StateInstantiation.

Single-state case: gen() returns [single_si] (wraps gen_single() in a list).
"""

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_slugs.helpers.slugs_automaton import SlugsAutomatonState
from flexbe_synthesis_slugs.helpers.sm_gen.concurrent_state_generator import (
    ConcurrentStateGenerator,
)


def _make_decl(name, parameters=None):
    """Return a minimal class declaration dict for testing."""
    return {'name': name, 'parameters': parameters or {}}


def _make_behavior_decl(behavior_class, parameters=None):
    """Return a behavior class declaration dict for testing."""
    return {
        'name': StateInstantiation.CLASS_BEHAVIOR,
        'behavior_class': behavior_class,
        'parameters': parameters or {},
    }


def _make_csg_with_two_states(name='my_state'):
    """Return a ConcurrentStateGenerator with two internal states and one outcome."""
    csg = ConcurrentStateGenerator(name)
    csg.add_internal_state('stand_a', _make_decl('StandState'))
    csg.add_internal_state('grasp_a', _make_decl('GraspState'))
    csg.add_internal_outcome_and_transition('stand_changed__grasp_grasped', 'next_state', [2])
    csg.add_internal_outcome_maps({
        'outcome': 'stand_changed__grasp_grasped',
        'condition': {'stand_a': 'changed', 'grasp_a': 'grasped'},
    })
    return csg


# ── is_concurrent() ────────────────────────────────────────────────────────────


def test_is_concurrent_false_with_one_state():
    """Single internal state should not be treated as concurrent."""
    csg = ConcurrentStateGenerator('s')
    csg.add_internal_state('act_a', _make_decl('ActionState'))
    assert not csg.is_concurrent()


def test_is_concurrent_true_with_two_states():
    """Two internal states should trigger the concurrent path."""
    csg = _make_csg_with_two_states()
    assert csg.is_concurrent()


# ── gen() always returns a list ────────────────────────────────────────────────


def test_gen_single_returns_list():
    """gen() with one internal state must return a list with one element."""
    csg = ConcurrentStateGenerator('s')
    csg.add_internal_state('act_a', _make_decl('ActionState'))
    csg.add_internal_outcome_and_transition('done', 'next', [1])
    csg.add_internal_outcome_maps({'outcome': 'done', 'condition': {'act_a': 'done'}})
    state = SlugsAutomatonState(name='0')
    state.output_values = {}
    state.input_values = {}
    result = csg.gen(state)
    assert isinstance(result, list)
    assert len(result) == 1


def test_gen_concurrent_returns_list_with_container_and_substates():
    """gen() with two states returns a list: [container, sub1, sub2]."""
    result = _make_csg_with_two_states().gen(None)
    assert isinstance(result, list)
    assert len(result) == 3  # container + 2 sub-states


# ── gen() – concurrent path: container SI ─────────────────────────────────────


def test_gen_concurrent_container_uses_class_concurrency():
    """Container SI must use CLASS_CONCURRENCY."""
    container_si = _make_csg_with_two_states().gen(None)[0]
    assert container_si.state_class == StateInstantiation.CLASS_CONCURRENCY


def test_gen_concurrent_container_state_path():
    """Container state path should be the generator name prefixed with /."""
    container_si = _make_csg_with_two_states('demo').gen(None)[0]
    assert container_si.state_path == '/demo'


def test_gen_concurrent_container_outcomes_and_transitions():
    """Container outcomes and transitions are propagated correctly."""
    csg = ConcurrentStateGenerator('s')
    csg.add_internal_state('act_a', _make_decl('ActionState'))
    csg.add_internal_state('sensor_x', _make_decl('SensorState'))
    csg.add_internal_outcome_and_transition('out1', 'state_a', [1])
    csg.add_internal_outcome_and_transition('out2', 'state_b', [1])
    csg.add_internal_outcome_maps({'outcome': 'out1', 'condition': {'act_a': 'done'}})
    csg.add_internal_outcome_maps({'outcome': 'out2', 'condition': {'act_a': 'failed'}})

    container_si = csg.gen(None)[0]
    outcome_to_transition = dict(zip(container_si.outcomes, container_si.transitions))
    assert outcome_to_transition['out1'] == 'state_a'
    assert outcome_to_transition['out2'] == 'state_b'


def test_gen_concurrent_container_autonomy_uses_max():
    """Container autonomy for each outcome is the max value in the autonomy list."""
    csg = ConcurrentStateGenerator('s')
    csg.add_internal_state('act_a', _make_decl('ActionState'))
    csg.add_internal_state('sensor_x', _make_decl('SensorState'))
    csg.add_internal_outcome_and_transition('done', 'next', [1, 3])
    csg.add_internal_outcome_maps({'outcome': 'done', 'condition': {'act_a': 'done'}})

    container_si = csg.gen(None)[0]
    assert list(container_si.autonomy) == [3]


def test_gen_concurrent_container_has_cond_outcome():
    """Container cond_outcome must list each outcome from the outcome maps."""
    container_si = _make_csg_with_two_states().gen(None)[0]
    assert list(container_si.cond_outcome) == ['stand_changed__grasp_grasped']


def test_gen_concurrent_container_has_cond_transition():
    """Container cond_transition must encode the condition mapping as OutcomeCondition."""
    container_si = _make_csg_with_two_states().gen(None)[0]
    assert len(container_si.cond_transition) == 1
    oc = container_si.cond_transition[0]
    # clean_variable strips _a suffix: stand_a -> stand, grasp_a -> grasp
    paired = dict(zip(oc.state_name, oc.state_outcome))
    assert paired == {'stand': 'changed', 'grasp': 'grasped'}


def test_gen_concurrent_container_forwards_userdata():
    """Userdata collected via add_internal_userdata must be on the container SI."""
    csg = _make_csg_with_two_states()
    csg.add_internal_userdata({'target_pose': 'pose'})

    container_si = csg.gen(None)[0]
    assert container_si.state_class == StateInstantiation.CLASS_CONCURRENCY
    assert list(container_si.userdata_keys) == ['target_pose']
    assert list(container_si.userdata_remapping) == ['pose']


def test_gen_concurrent_container_has_no_parameter_names():
    """Concurrent container SI has no parameter_names; conditions go in cond_* fields."""
    container_si = _make_csg_with_two_states().gen(None)[0]
    assert list(container_si.parameter_names) == []


# ── gen() – concurrent path: sub-state SIs ────────────────────────────────────


def test_gen_concurrent_substates_have_correct_paths():
    """Sub-state paths must be /container_name/label."""
    result = _make_csg_with_two_states('demo').gen(None)
    sub_paths = {si.state_path for si in result[1:]}
    assert sub_paths == {'/demo/stand', '/demo/grasp'}


def test_gen_concurrent_substates_have_correct_classes():
    """Sub-state SIs must carry the state class from their class_decl."""
    result = _make_csg_with_two_states().gen(None)
    sub_classes = {si.state_class for si in result[1:]}
    assert sub_classes == {'StandState', 'GraspState'}


def test_gen_concurrent_substates_outcomes_from_conditions():
    """Sub-state outcomes are derived from the outcome maps."""
    result = _make_csg_with_two_states().gen(None)
    sub_by_path = {si.state_path: si for si in result[1:]}
    assert list(sub_by_path['/my_state/stand'].outcomes) == ['changed']
    assert list(sub_by_path['/my_state/grasp'].outcomes) == ['grasped']


def test_gen_concurrent_substates_have_empty_transitions():
    """Sub-states inside a ConcurrencyContainer have no inter-state transitions."""
    result = _make_csg_with_two_states().gen(None)
    for sub_si in result[1:]:
        assert list(sub_si.transitions) == []


def test_gen_concurrent_behavior_substate_uses_class_behavior():
    """A behavior capability becomes a sub-state with CLASS_BEHAVIOR and behavior_class set."""
    csg = ConcurrentStateGenerator('mixed')
    csg.add_internal_state('act_a', _make_decl('ActionState'))
    csg.add_internal_state('beh_a', _make_behavior_decl('MyBehaviorSM'))
    csg.add_internal_outcome_and_transition('done', 'next', [1])
    csg.add_internal_outcome_maps({
        'outcome': 'done',
        'condition': {'act_a': 'finished', 'beh_a': 'finished'},
    })

    result = csg.gen(None)
    sub_by_path = {si.state_path: si for si in result[1:]}

    beh_si = sub_by_path['/mixed/beh']
    assert beh_si.state_class == StateInstantiation.CLASS_BEHAVIOR
    assert beh_si.behavior_class == 'MyBehaviorSM'

    act_si = sub_by_path['/mixed/act']
    assert act_si.state_class == 'ActionState'
    assert act_si.behavior_class == ''


# ── gen() – single-state fallback ─────────────────────────────────────────────


def test_gen_single_returns_inner_state_class():
    """One internal state should unwrap to the inner class, not ConcurrencyContainer."""
    csg = ConcurrentStateGenerator('stand_state')
    csg.add_internal_state('stand_a', _make_decl('ControlModeState'))
    csg.add_internal_outcome_and_transition('changed', 'next', [2])
    csg.add_internal_outcome_maps({'outcome': 'changed', 'condition': {'stand_a': 'changed'}})

    state = SlugsAutomatonState(name='0_stand')
    state.output_values = {}
    state.input_values = {}

    result = csg.gen(state)
    assert result[0].state_class == 'ControlModeState'


def test_gen_single_resolves_at_param_from_output_values():
    """@-prefixed parameter values are resolved against the state's output_values."""
    csg = ConcurrentStateGenerator('stand_state')
    csg.add_internal_state('stand_a', _make_decl('ControlModeState', {'target_mode': '@stand_a'}))
    csg.add_internal_outcome_and_transition('changed', 'next', [2])
    csg.add_internal_outcome_maps({'outcome': 'changed', 'condition': {'stand_a': 'changed'}})

    state = SlugsAutomatonState(name='0_stand')
    state.output_values = {'stand_a': 'stand'}
    state.input_values = {}

    si = csg.gen(state)[0]

    idx = si.parameter_names.index('target_mode')
    assert si.parameter_values[idx] == "'stand'"


def test_gen_single_resolves_at_param_from_input_values():
    """@-prefixed parameter values fall back to input_values when not in output_values."""
    csg = ConcurrentStateGenerator('stand_state')
    csg.add_internal_state('stand_a', _make_decl('ControlModeState', {'target_mode': '@env_mode'}))
    csg.add_internal_outcome_and_transition('changed', 'next', [2])
    csg.add_internal_outcome_maps({'outcome': 'changed', 'condition': {'stand_a': 'changed'}})

    state = SlugsAutomatonState(name='0_stand')
    state.output_values = {}
    state.input_values = {'env_mode': 'manipulate'}

    si = csg.gen(state)[0]

    idx = si.parameter_names.index('target_mode')
    assert si.parameter_values[idx] == "'manipulate'"


def test_gen_single_unknown_at_param_leaves_at_prefix_quoted():
    """An @-param whose key is absent from both output and input values is left as a string."""
    csg = ConcurrentStateGenerator('stand_state')
    csg.add_internal_state('stand_a', _make_decl('ControlModeState', {'target_mode': '@unknown'}))
    csg.add_internal_outcome_and_transition('changed', 'next', [2])
    csg.add_internal_outcome_maps({'outcome': 'changed', 'condition': {'stand_a': 'changed'}})

    state = SlugsAutomatonState(name='0_stand')
    state.output_values = {}
    state.input_values = {}

    si = csg.gen(state)[0]

    idx = si.parameter_names.index('target_mode')
    # Resolution fails silently; string processing then quotes the raw @-value.
    assert si.parameter_values[idx] == "'@unknown'"
