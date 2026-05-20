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

"""Tests for generic state-machine layout failure handling."""

from unittest.mock import patch

from flexbe_msgs.msg import StateInstantiation
import flexbe_synthesis_generic.processes.sm_layout as sm_layout_mod
from flexbe_synthesis_generic.processes.sm_layout import SM_Layout
from flexbe_synthesis_msgs.msg import SynthesisErrorCode


def _state(path, outcomes=None, transitions=None):
    state = StateInstantiation()
    state.state_path = path
    state.outcomes = outcomes or []
    state.transitions = transitions or []
    return state


def test_sm_layout_failure_returns_synthesis_error_code(tmp_path):
    layout = SM_Layout(
        name='SM Layout',
        synthesized_state_machine=[],
        specs_output_dir_path=str(tmp_path / 'missing'),
    )

    states, error_code = layout.process()

    assert states == []
    assert isinstance(error_code, SynthesisErrorCode)
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_layout_fallback_writes_dot_when_output_dir_requested(tmp_path):
    root = _state('/', outcomes=['finished'])
    root.initial_state_name = 'Start'
    start = _state('/Start', outcomes=['done'], transitions=['finished'])
    layout = SM_Layout(
        name='SM Layout',
        synthesized_state_machine=[root, start],
        specs_output_dir_path=str(tmp_path),
        use_fallback_layout=True,
    )

    states, error_code = layout.process()

    assert states == [root, start]
    assert isinstance(error_code, SynthesisErrorCode)
    assert error_code.value == SynthesisErrorCode.SUCCESS
    dot_text = (tmp_path / 'state_machine.dot').read_text(encoding='utf-8')
    assert '"/" -> "Start";' in dot_text
    assert '"Start" -> "finished" [label="done"];' in dot_text


def test_sm_layout_fallback_used_when_pygraphviz_unavailable():
    root = _state('/', outcomes=['finished'])
    root.initial_state_name = 'Start'
    start = _state('/Start', outcomes=['done'], transitions=['finished'])
    layout = SM_Layout(
        name='SM Layout',
        synthesized_state_machine=[root, start],
        specs_output_dir_path='',
        use_fallback_layout=False,
    )

    with patch.object(sm_layout_mod, '_PYGRAPHVIZ_AVAILABLE', False):
        states, error_code = layout.process()

    assert states == [root, start]
    assert isinstance(error_code, SynthesisErrorCode)
    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert start.position[0] > 0
    assert start.position[1] >= 0
