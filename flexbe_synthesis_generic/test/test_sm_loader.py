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

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_generic.processes.sm_loader import main, SMLoader
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
import pytest


_VALID_SM_YAML = """\
sm:
  outcomes:
    - finished
    - failed
  initial_state: DoWork
states:
  - name: DoWork
    state_class: flexbe_states/LogState
    behavior_class: ''
    outcomes:
      - done
      - error
    transitions:
      - finished
      - failed
    parameters:
      text: hello world
    autonomy:
      - 0
      - 0
    userdata_keys:
      - msg
    userdata_remapping:
      - msg
"""


@pytest.fixture
def valid_sm_file(tmp_path):
    p = tmp_path / 'test_sm.yaml'
    p.write_text(_VALID_SM_YAML, encoding='utf-8')
    return str(p)


def test_sm_loader_success(valid_sm_file):
    loader = SMLoader(name='SM Loader', automaton_path=valid_sm_file)
    state_defn, error_code = loader.process()

    assert isinstance(error_code, SynthesisErrorCode)
    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert isinstance(state_defn, list)

    # root + 1 state + 2 outcome pseudo-states
    assert len(state_defn) == 4

    root = state_defn[0]
    assert root.state_path == '/'
    assert root.state_class == StateInstantiation.CLASS_STATEMACHINE
    assert root.initial_state_name == 'DoWork'
    assert root.outcomes == ['finished', 'failed']

    state = state_defn[1]
    assert state.state_path == '/DoWork'
    assert state.state_class == 'flexbe_states/LogState'
    assert state.outcomes == ['done', 'error']
    assert state.transitions == ['finished', 'failed']
    assert state.parameter_names == ['text']
    assert state.parameter_values == ['hello world']
    assert list(state.autonomy) == [0, 0]
    assert state.userdata_keys == ['msg']
    assert state.userdata_remapping == ['msg']

    pseudo_finished = state_defn[2]
    assert pseudo_finished.state_path == 'finished'
    assert pseudo_finished.state_class == ':OUTCOME'

    pseudo_failed = state_defn[3]
    assert pseudo_failed.state_path == 'failed'
    assert pseudo_failed.state_class == ':OUTCOME'


def test_sm_loader_missing_file():
    loader = SMLoader(name='SM Loader', automaton_path='/nonexistent/path/sm.yaml')
    state_defn, error_code = loader.process()

    assert state_defn == []
    assert isinstance(error_code, SynthesisErrorCode)
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_loader_malformed_yaml(tmp_path):
    bad_file = tmp_path / 'bad.yaml'
    bad_file.write_text(': invalid: yaml: [unclosed', encoding='utf-8')

    loader = SMLoader(name='SM Loader', automaton_path=str(bad_file))
    state_defn, error_code = loader.process()

    assert state_defn == []
    assert isinstance(error_code, SynthesisErrorCode)
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_loader_missing_sm_key(tmp_path):
    bad_file = tmp_path / 'no_sm.yaml'
    bad_file.write_text('states:\n  - name: Foo\n', encoding='utf-8')

    loader = SMLoader(name='SM Loader', automaton_path=str(bad_file))
    state_defn, error_code = loader.process()

    assert state_defn == []
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_loader_missing_states_key(tmp_path):
    bad_file = tmp_path / 'no_states.yaml'
    bad_file.write_text('sm:\n  outcomes: [done]\n  initial_state: Foo\n', encoding='utf-8')

    loader = SMLoader(name='SM Loader', automaton_path=str(bad_file))
    state_defn, error_code = loader.process()

    assert state_defn == []
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_loader_not_a_dict(tmp_path):
    bad_file = tmp_path / 'list.yaml'
    bad_file.write_text('- item1\n- item2\n', encoding='utf-8')

    loader = SMLoader(name='SM Loader', automaton_path=str(bad_file))
    state_defn, error_code = loader.process()

    assert state_defn == []
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_loader_state_missing_name(tmp_path):
    bad_file = tmp_path / 'no_name.yaml'
    bad_file.write_text(
        'sm:\n  outcomes: [done]\n  initial_state: Foo\nstates:\n  - state_class: foo/Bar\n',
        encoding='utf-8',
    )

    loader = SMLoader(name='SM Loader', automaton_path=str(bad_file))
    state_defn, error_code = loader.process()

    assert state_defn == []
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_main_factory_returns_sm_loader_with_correct_path():
    loader = main(['/some/path/sm.yaml'])

    assert isinstance(loader, SMLoader)
    assert loader.automaton_path == '/some/path/sm.yaml'
