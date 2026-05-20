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

"""Tests for synthesis manager pipeline loading and validation."""

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core import synthesis_manager
from flexbe_synthesis_core.base_preprocess import BasePreProcess
from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_core.plugin import Plugin
from flexbe_synthesis_core.synthesis_manager import FlexBESynthesisActionServer
from flexbe_synthesis_core.validation_error import (
    MappingValidationError,
    UserdataValidationError,
    ValidationError,
)
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode
import pytest


class _AvailableEntryPoints:
    """Minimal entry point collection used by pipeline validation."""

    def __init__(self, names, entries=None):
        self.names = names
        self.entries = entries or {}

    def __getitem__(self, name):
        return self.entries[name]


class _Logger:
    """Minimal logger for methods exercised without initializing a ROS node."""

    def __init__(self):
        self.errors = []
        self.infos = []
        self.warnings = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)

    def warning(self, message):
        self.warnings.append(message)


class _EntryPoint:
    """Minimal loadable entry point for process execution tests."""

    def __init__(self, process_class):
        self.process_class = process_class

    def load(self):
        return self.process_class


class _Process:
    """Minimal process plugin returning configured outputs."""

    canceled = []
    calls = []

    def __init__(self, inputs):
        self.inputs = inputs
        self.messages = []

    def process(self):
        self.calls.append(self.inputs)
        return ['output']

    def cancel(self):
        self.canceled.append(self.inputs)


class _ShortOutputProcess(_Process):
    """Process plugin returning fewer outputs than the pipeline declares."""

    def process(self):
        self.calls.append(self.inputs)
        return []


class _ExtraOutputProcess(_Process):
    """Process plugin returning more outputs than the pipeline declares."""

    def process(self):
        self.calls.append(self.inputs)
        return ['output', 'extra']


class _RuntimeErrorProcess(_Process):
    """Process plugin that fails with a runtime execution error."""

    def process(self):
        self.calls.append(self.inputs)
        raise RuntimeError('compiler failed')


class _ShortOutputPreprocess:
    """Preprocess plugin returning fewer outputs than the pipeline declares."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.synthesis_home = 'default'
        self.messages = []

    def preprocess(self):
        return []


class _MappingFailurePreprocess:
    """Preprocess plugin reporting an invalid mapping configuration."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.synthesis_home = 'default'
        self.messages = []

    def preprocess(self):
        raise MappingValidationError('missing outcome mapping')


class _UserdataFailurePreprocess:
    """Preprocess plugin reporting an invalid userdata configuration."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.synthesis_home = 'default'
        self.messages = []

    def preprocess(self):
        raise UserdataValidationError('missing userdata key')


class _CancelableProcess:
    """Minimal active process used by cancel callback tests."""

    def __init__(self):
        self.canceled = False

    def cancel(self):
        self.canceled = True


class _PluginWithSynthesisHome:
    """Minimal plugin that records manager-injected synthesis home."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.synthesis_home = 'default'
        self.messages = []

    def process(self):
        return [self.synthesis_home]

    def cancel(self):
        pass


class _StateMachineProducer:
    """Minimal process that returns configured state machine outputs by input label."""

    def __init__(self, inputs):
        self.inputs = inputs
        self.messages = []

    def process(self):
        state = StateInstantiation()
        state.state_path = self.inputs[0]
        return [[state]]

    def cancel(self):
        pass


class _DirectProcessClass(BaseProcess):
    """BaseProcess subclass registered directly (misconfigured entry point)."""

    def process(self):
        return []


class _DirectPreProcessClass(BasePreProcess):
    """BasePreProcess subclass registered directly (misconfigured entry point)."""

    def preprocess(self):
        return []


class _UnknownYamlObject:
    """Object that relies on SynthesisYamlDumper fallback serialization."""

    def __init__(self):
        self.value = 'fallback'


class _Goal:
    """Minimal goal handle for feedback/cancel tests."""

    def __init__(self, cancel_sequence=None):
        if cancel_sequence is None:
            cancel_sequence = [False]
        self.cancel_sequence = list(cancel_sequence)
        self.feedback = []
        self.canceled_called = False

    @property
    def is_cancel_requested(self):
        if len(self.cancel_sequence) > 1:
            return self.cancel_sequence.pop(0)
        return self.cancel_sequence[0]

    def publish_feedback(self, feedback):
        self.feedback.append(feedback)

    def canceled(self):
        self.canceled_called = True


class _RequestGoal:
    """Minimal goal handle with a FlexBE synthesis action request."""

    def __init__(self, system_name, synthesis_options):
        request = FlexBESynthesisRequest()
        request.system_name = system_name
        request.spec_name = 'TestSpec'
        self.request = type(
            'ActionRequest',
            (),
            {
                'request': request,
                'synthesis_options': synthesis_options,
            },
        )()


def _manager_stub():
    manager = object.__new__(FlexBESynthesisActionServer)
    manager.data = {'seed': 'ready'}
    manager._logger = _Logger()
    manager.get_logger = lambda: manager._logger
    manager._result = type('Result', (), {})()
    manager._result.error_code = SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)
    manager._result.states = []
    manager.available_processes = {}
    manager.processor_outputs = {}
    manager.processor_plugins = []
    manager.process_group = 'FlexBESynthesis.processes'
    manager.save_outputs = False
    manager.synthesis_home = '/tmp/synthesis-home'
    manager.statistics = {'processes': {}}
    manager._active_process_instance = None
    manager._pipeline_messages = []
    manager.system_name = ''
    manager.capabilities_path = ''
    manager.spec_path = ''
    manager.automaton_path = ''
    manager.global_mappings_path = ''
    manager.custom_mappings_path = ''
    manager.verbose = False
    return manager


class _ActionGoal(_RequestGoal):
    """Goal handle with action-server methods used by execute_callback."""

    def __init__(self):
        super().__init__('request_system', 'request_options')
        self.aborted = False
        self.succeeded = False
        self.feedback = []

    def abort(self):
        self.aborted = True

    def succeed(self):
        self.succeeded = True

    @property
    def is_cancel_requested(self):
        return False

    def publish_feedback(self, feedback):
        self.feedback.append(feedback)


def test_load_processes_applies_data_file_and_pipeline(tmp_path):
    """Process data and pipeline YAML should populate manager runtime state."""
    data_file = tmp_path / 'process_data.yaml'
    data_file.write_text(
        '/data:\n'
        '  spec_path: ros:spec_path\n'
        '  system_name: vending_demo\n',
        encoding='utf-8',
    )
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text(
        '/pipeline:\n'
        '  - entry_point:\n'
        '      name: first_process\n'
        '      outputs:\n'
        '        output_value: str\n',
        encoding='utf-8',
    )

    manager = _manager_stub()
    manager.processes_data_filepath = str(data_file)
    manager.processes_filepath = str(pipeline_file)
    manager.spec_path = '/tmp/spec.structuredslugs'

    FlexBESynthesisActionServer.load_processes(manager)

    assert manager.data['spec_path'] == '/tmp/spec.structuredslugs'
    assert manager.data['system_name'] == 'vending_demo'
    assert manager.processes_pipeline == [
        {
            'entry_point': {
                'name': 'first_process',
                'outputs': {'output_value': 'str'},
            }
        }
    ]
    assert 'pipeline' not in manager.statistics['processes']


def test_load_processes_loads_pipeline_type_aliases(tmp_path):
    """Process pipeline YAML may define aliases to known core pipeline types."""
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text(
        '/types:\n'
        '  ReducedAutomaton: Automaton\n'
        '/pipeline:\n'
        '  - entry_point:\n'
        '      name: reducer\n'
        '      outputs:\n'
        '        reduced_automaton: ReducedAutomaton\n',
        encoding='utf-8',
    )

    manager = _manager_stub()
    manager.processes_data_filepath = ''
    manager.processes_filepath = str(pipeline_file)

    FlexBESynthesisActionServer.load_processes(manager)

    assert manager.process_type_aliases == {'ReducedAutomaton': 'Automaton'}
    assert manager.process_type_mapping['ReducedAutomaton'] is dict


def test_load_processes_rejects_unknown_type_alias_target(tmp_path):
    """Pipeline type aliases must point at known core or earlier local types."""
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text(
        '/types:\n'
        '  ReducedAutomaton: MissingType\n'
        '/pipeline: []\n',
        encoding='utf-8',
    )

    manager = _manager_stub()
    manager.data['error_code'] = SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)
    manager.processes_data_filepath = ''
    manager.processes_filepath = str(pipeline_file)

    with pytest.raises(ValidationError, match='references unknown type'):
        FlexBESynthesisActionServer.load_processes(manager)


def test_load_preprocesses_loads_pipeline_type_aliases(tmp_path):
    """Preprocess pipeline YAML supports the same local type alias block."""
    pipeline_file = tmp_path / 'preprocesses.yaml'
    pipeline_file.write_text(
        '/types:\n'
        '  ParsedWorkspace: WorkspaceData\n'
        '/pipeline:\n'
        '  - entry_point:\n'
        '      name: workspace_parser\n'
        '      outputs:\n'
        '        workspace_data: ParsedWorkspace\n',
        encoding='utf-8',
    )

    manager = _manager_stub()
    manager.preprocess_data_filepath = ''
    manager.preprocess_filepath = str(pipeline_file)
    manager.statistics = {'preprocesses': {}, 'processes': {}}

    FlexBESynthesisActionServer.load_preprocesses(manager)

    assert manager.preprocess_type_aliases == {'ParsedWorkspace': 'WorkspaceData'}
    assert manager.preprocess_type_mapping['ParsedWorkspace'] is dict


def test_goal_request_data_takes_precedence_after_process_reload(tmp_path):
    """Action request data should win over per-request process data reloads."""
    data_file = tmp_path / 'process_data.yaml'
    data_file.write_text(
        '/data:\n'
        '  system_name: yaml_system\n'
        '  synthesis_request: yaml_request\n'
        '  synthesis_options: yaml_options\n',
        encoding='utf-8',
    )
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text('/pipeline: []\n', encoding='utf-8')

    manager = _manager_stub()
    manager.processes_data_filepath = str(data_file)
    manager.processes_filepath = str(pipeline_file)
    manager.spec_path = '/tmp/spec.structuredslugs'
    goal = _RequestGoal('request_system', 'request_options')

    FlexBESynthesisActionServer.load_processes(manager)
    FlexBESynthesisActionServer._apply_goal_request_data(manager, goal)

    assert manager.data['system_name'] == 'request_system'
    assert manager.data['synthesis_request'] is goal.request.request
    assert manager.data['synthesis_options'] == 'request_options'


def test_goal_request_data_reports_invalid_system_name():
    """Invalid request-derived path components should fail as invalid requests."""
    manager = _manager_stub()
    manager.data['error_code'] = SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)
    goal = _RequestGoal('../bad_system', 'request_options')

    with pytest.raises(ValueError, match='Invalid system_name'):
        FlexBESynthesisActionServer._apply_goal_request_data(manager, goal)

    assert manager.data['error_code'].value == SynthesisErrorCode.INVALID_REQUEST
    assert manager._result.error_code.value == SynthesisErrorCode.INVALID_REQUEST


def test_update_request_spec_settings_rejects_empty_request_spec_name():
    """Request-derived spec names must be non-empty."""
    manager = _manager_stub()
    manager.data = {
        'spec_name': 'req:spec_name',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    goal = _RequestGoal('request_system', 'request_options')
    goal.request.request.spec_name = ''

    with pytest.raises(ValueError, match='must be a non-empty string'):
        FlexBESynthesisActionServer._update_request_spec_settings(manager, goal)

    assert manager.data['spec_name'] == 'req:spec_name'
    assert manager.data['error_code'].value == SynthesisErrorCode.INVALID_REQUEST
    assert manager._result.error_code.value == SynthesisErrorCode.INVALID_REQUEST


def test_update_request_spec_settings_rejects_empty_request_spec_path():
    """Request-derived spec paths must be non-empty."""
    manager = _manager_stub()
    manager.data = {
        'spec_path': 'req:specification_file_name',
        'spec_name': 'TestSpec',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    goal = _RequestGoal('request_system', 'request_options')
    goal.request.request.specification_file_name = ''

    with pytest.raises(ValueError, match='must be a non-empty string'):
        FlexBESynthesisActionServer._update_request_spec_settings(manager, goal)

    assert manager.data['spec_path'] == 'req:specification_file_name'
    assert manager.data['error_code'].value == SynthesisErrorCode.INVALID_REQUEST
    assert manager._result.error_code.value == SynthesisErrorCode.INVALID_REQUEST


def test_update_request_spec_settings_rejects_unsafe_spec_folder():
    """YAML-derived spec folders must not traverse outside the package share."""
    manager = _manager_stub()
    manager.data = {
        'spec_path': 'spec.structuredslugs',
        'spec_package': 'demo_pkg',
        'spec_folder': '../escape',
        'spec_name': 'TestSpec',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    goal = _RequestGoal('request_system', 'request_options')

    with pytest.raises(ValueError, match='Invalid spec_folder'):
        FlexBESynthesisActionServer._update_request_spec_settings(manager, goal)

    assert manager.data['error_code'].value == SynthesisErrorCode.PIPELINE_INVALID
    assert manager._result.error_code.value == SynthesisErrorCode.PIPELINE_INVALID


def test_update_request_spec_settings_resolves_relative_path_with_package(monkeypatch):
    """A relative spec_path with spec_package is joined to the package share directory."""
    monkeypatch.setattr(
        'flexbe_synthesis_core.synthesis_manager.get_package_share_directory',
        lambda pkg: f'/opt/ros/share/{pkg}',
    )
    manager = _manager_stub()
    manager.data = {
        'spec_path': 'my_spec.structuredslugs',
        'spec_package': 'my_pkg',
        'spec_folder': 'slugs/specs',
        'spec_name': 'TestSpec',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    goal = _RequestGoal('request_system', 'request_options')

    FlexBESynthesisActionServer._update_request_spec_settings(manager, goal)

    assert manager.data['spec_path'] == (
        '/opt/ros/share/my_pkg/slugs/specs/my_spec.structuredslugs'
    )


def test_update_request_spec_settings_resolves_relative_path_without_spec_folder(monkeypatch):
    """A relative spec_path with spec_package but no spec_folder joins at package root."""
    monkeypatch.setattr(
        'flexbe_synthesis_core.synthesis_manager.get_package_share_directory',
        lambda pkg: f'/opt/ros/share/{pkg}',
    )
    manager = _manager_stub()
    manager.data = {
        'spec_path': 'my_spec.structuredslugs',
        'spec_package': 'my_pkg',
        'spec_name': 'TestSpec',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    goal = _RequestGoal('request_system', 'request_options')

    FlexBESynthesisActionServer._update_request_spec_settings(manager, goal)

    assert manager.data['spec_path'] == '/opt/ros/share/my_pkg/my_spec.structuredslugs'


def test_update_request_spec_settings_leaves_relative_path_without_package():
    """A relative spec_path without spec_package is stored unchanged."""
    manager = _manager_stub()
    manager.data = {
        'spec_path': 'my_spec.structuredslugs',
        'spec_name': 'TestSpec',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    goal = _RequestGoal('request_system', 'request_options')

    FlexBESynthesisActionServer._update_request_spec_settings(manager, goal)

    assert manager.data['spec_path'] == 'my_spec.structuredslugs'


def test_load_processes_rejects_empty_pipeline_file_without_stale_reuse(tmp_path):
    """Empty process YAML should clear stale state and fail instead of reusing it."""
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text('', encoding='utf-8')

    manager = _manager_stub()
    manager.data['error_code'] = SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)
    manager.processes_data_filepath = ''
    manager.processes_filepath = str(pipeline_file)
    manager.processes_pipeline = [{'entry_point': {'name': 'stale'}}]
    manager.processor_plugins = [object()]
    manager.processor_outputs = {'stale': 'str'}
    manager.statistics = {
        'processes': {'pipeline': {'process_0_stale': {'execution_time': None}}}
    }

    with pytest.raises(ValidationError, match='file is empty'):
        FlexBESynthesisActionServer.load_processes(manager)

    assert manager.processes_pipeline is None
    assert manager.processor_plugins == []
    assert manager.processor_outputs == {}
    assert 'pipeline' not in manager.statistics['processes']
    assert manager.data['error_code'].value == SynthesisErrorCode.PIPELINE_INVALID
    assert 'Invalid processes pipeline file' in manager._logger.errors[-1]


def test_load_processes_rejects_missing_pipeline_key(tmp_path):
    """Process YAML without /pipeline should fail clearly."""
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text('/data:\n  only: data\n', encoding='utf-8')

    manager = _manager_stub()
    manager.data['error_code'] = SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)
    manager.processes_data_filepath = ''
    manager.processes_filepath = str(pipeline_file)

    with pytest.raises(ValidationError, match='missing /pipeline key'):
        FlexBESynthesisActionServer.load_processes(manager)


def test_validate_builds_plugin_order_from_pipeline():
    """Validation should record executable plugins in configured order."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer', 'consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'int'},
            }
        },
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'produced': 'int'},
                'outputs': {'result': 'str', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]

    FlexBESynthesisActionServer.validate(manager)

    assert [plugin.name for plugin in manager.processor_plugins] == [
        'producer',
        'consumer',
    ]
    assert manager.processor_outputs == {
        'produced': 'int',
        'result': 'str',
        'state_defn': 'List[StateInstantiation]',
    }
    assert manager.statistics['processes']['pipeline'] == {
        'process_0_producer': {'execution_time': None},
        'process_1_consumer': {'execution_time': None},
    }
    assert manager.statistics['processes']['validation_time'] >= 0.0
    assert manager.processor_plugins[0].output_types == {'produced': 'int'}
    assert manager.processor_plugins[1].output_types == {
        'result': 'str',
        'state_defn': 'List[StateInstantiation]',
    }


def test_validate_accepts_yaml_type_alias_for_core_type():
    """A local alias to a core type should be compatible with its base type."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer', 'consumer'])
    manager.process_type_mapping = dict(synthesis_manager.TYPE_MAPPING)
    manager.process_type_mapping['ReducedAutomaton'] = dict
    manager.process_type_aliases = {'ReducedAutomaton': 'Automaton'}
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {},
                'outputs': {'reduced_automaton': 'ReducedAutomaton'},
            }
        },
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'reduced_automaton': 'Automaton'},
                'outputs': {'result': 'str', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]

    FlexBESynthesisActionServer.validate(manager)

    assert manager.processor_outputs == {
        'reduced_automaton': 'ReducedAutomaton',
        'result': 'str',
        'state_defn': 'List[StateInstantiation]',
    }


def test_validate_rebuilds_state_on_repeated_calls():
    """Repeated validation should not duplicate plugins or keep stale outputs."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer', 'consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'int', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]

    FlexBESynthesisActionServer.validate(manager)
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'seed': 'str'},
                'outputs': {'result': 'str', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]
    FlexBESynthesisActionServer.validate(manager)

    assert [plugin.name for plugin in manager.processor_plugins] == ['consumer']
    assert manager.processor_outputs == {'result': 'str', 'state_defn': 'List[StateInstantiation]'}


def test_validate_failure_does_not_replace_existing_state():
    """Failed validation should leave the previously valid state intact."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer', 'consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'int', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]
    FlexBESynthesisActionServer.validate(manager)

    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'missing': 'str'},
                'outputs': {'result': 'str'},
            }
        },
    ]

    with pytest.raises(ValidationError, match="input 'missing' not defined"):
        FlexBESynthesisActionServer.validate(manager)

    assert [plugin.name for plugin in manager.processor_plugins] == ['producer']
    assert manager.processor_outputs == {
        'produced': 'int',
        'state_defn': 'List[StateInstantiation]',
    }


def test_validate_preprocesses_rejects_missing_entry_point():
    """Preprocess pipelines should reject malformed entries before execution."""
    manager = _manager_stub()
    manager.statistics = {'preprocesses': {}}
    manager.preprocesses_pipeline = [{'not_entry_point': {'name': 'ignored'}}]

    with pytest.raises(ValidationError, match=r'\[entry_point\] not found'):
        FlexBESynthesisActionServer.validate_preprocesses(manager)


def test_entry_point_class_registration_raises_plugin_interface_error():
    """Direct class registration (not a main() factory) should raise PLUGIN_INTERFACE."""
    manager = _manager_stub()
    manager.data = {'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)}
    manager.synthesis_home = '/tmp'

    # Process path: class registered directly instead of a main() function
    manager.processes_pipeline = [
        {'entry_point': {'name': 'bad_plugin', 'inputs': {}, 'outputs': {'out': 'str'}}}
    ]
    manager.available_processes = _AvailableEntryPoints(
        ['bad_plugin'],
        {'bad_plugin': _EntryPoint(_DirectProcessClass)},
    )
    manager.processor_plugins = [Plugin('bad_plugin', [], ['out'], {'out': 'str'})]
    manager.statistics = {'processes': {'pipeline': {'process_0_bad_plugin': {}}}}

    with pytest.raises(ValidationError) as exc_info:
        FlexBESynthesisActionServer.execute_processes(manager, _Goal())
    assert exc_info.value.kind == ValidationError.PLUGIN_INTERFACE
    assert 'main(inputs)' in str(exc_info.value)

    # Preprocess path: class registered directly instead of a main() function
    manager.data = {'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)}
    manager.preprocesses_pipeline = [
        {'entry_point': {'name': 'bad_pre', 'inputs': {}, 'outputs': {'pre_out': 'str'}}}
    ]
    manager.available_preprocesses = _AvailableEntryPoints(
        ['bad_pre'],
        {'bad_pre': _EntryPoint(_DirectPreProcessClass)},
    )
    manager.statistics = {
        'preprocesses': {'pipeline': {'preprocess_0_bad_pre': {'execution_time': None}}}
    }

    with pytest.raises(ValidationError) as exc_info:
        FlexBESynthesisActionServer.execute_preprocesses(manager)
    assert exc_info.value.kind == ValidationError.PLUGIN_INTERFACE
    assert 'main(inputs)' in str(exc_info.value)


def test_validation_error_kind_attribute():
    """ValidationError.kind identifies the failure category without string parsing."""
    manager = _manager_stub()
    manager.statistics = {'preprocesses': {}, 'processes': {}}

    # MISSING_ENTRY_POINT
    manager.preprocesses_pipeline = [{'not_entry_point': {}}]
    with pytest.raises(ValidationError) as exc_info:
        FlexBESynthesisActionServer.validate_preprocesses(manager)
    assert exc_info.value.kind == ValidationError.MISSING_ENTRY_POINT

    # PLUGIN_NOT_FOUND
    manager.processes_pipeline = [{'entry_point': {'name': 'no_such_plugin', 'inputs': {}}}]
    manager.available_processes = _AvailableEntryPoints([])
    with pytest.raises(ValidationError) as exc_info:
        FlexBESynthesisActionServer.validate(manager)
    assert exc_info.value.kind == ValidationError.PLUGIN_NOT_FOUND

    # INPUT_NOT_DEFINED
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {},
                'outputs': {'out': 'str'},
            }
        },
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'missing': 'str'},
                'outputs': {},
            }
        },
    ]
    manager.available_processes = _AvailableEntryPoints(['producer', 'consumer'])
    with pytest.raises(ValidationError) as exc_info:
        FlexBESynthesisActionServer.validate(manager)
    assert exc_info.value.kind == ValidationError.INPUT_NOT_DEFINED

    # TYPE_MISMATCH
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {},
                'outputs': {'out': 'str'},
            }
        },
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'out': 'int'},
                'outputs': {},
                'strict_type_validation': True,
            }
        },
    ]
    with pytest.raises(ValidationError) as exc_info:
        FlexBESynthesisActionServer.validate(manager)
    assert exc_info.value.kind == ValidationError.TYPE_MISMATCH


def test_validate_preprocesses_builds_matching_statistics_keys():
    """Preprocess statistics keys should use the executable pipeline order."""
    manager = _manager_stub()
    manager.statistics = {'preprocesses': {}}
    manager.preprocesses_pipeline = [
        {'entry_point': {'name': 'workspace_crawler'}},
        {'entry_point': {'name': 'state_mappings'}},
    ]

    FlexBESynthesisActionServer.validate_preprocesses(manager)

    assert manager.statistics['preprocesses']['pipeline'] == {
        'preprocess_0_workspace_crawler': {'execution_time': None},
        'preprocess_1_state_mappings': {'execution_time': None},
    }


def test_execute_preprocesses_reports_short_plugin_outputs():
    """Short preprocess output lists should be logged before startup fails."""
    manager = _manager_stub()
    manager.data = {
        'seed': 'ready',
        'system_name': 'stale_system',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager.statistics = {
        'preprocesses': {
            'pipeline': {'preprocess_0_first': {'execution_time': None}}
        }
    }
    manager.preprocesses_pipeline = [
        {
            'entry_point': {
                'name': 'first',
                'inputs': {'seed': 'str'},
                'outputs': {'result': 'str'},
            }
        },
    ]
    manager.available_preprocesses = _AvailableEntryPoints(
        ['first'],
        {'first': _EntryPoint(_ShortOutputPreprocess)},
    )
    manager.preprocess_group = 'FlexBESynthesis.preprocesses'

    with pytest.raises(
        ValueError,
        match=r'returned 0 output\(s\), but the pipeline declares 1 output\(s\)',
    ):
        FlexBESynthesisActionServer.execute_preprocesses(manager)

    assert manager.data['error_code'].value == SynthesisErrorCode.PIPELINE_INVALID
    assert (
        manager._result.error_code.value
        == SynthesisErrorCode.PIPELINE_INVALID
    )
    assert 'Error occurred while executing preprocess' in manager._logger.errors[-1]
    assert 'result' not in manager.data


def test_execute_preprocesses_reports_mapping_validation_failures():
    """Mapping validation errors should use the mapping-specific error code."""
    manager = _manager_stub()
    manager.data = {
        'seed': 'ready',
        'system_name': 'stale_system',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager.statistics = {
        'preprocesses': {
            'pipeline': {'preprocess_0_workspace_parser': {'execution_time': None}}
        }
    }
    manager.preprocesses_pipeline = [
        {
            'entry_point': {
                'name': 'workspace_parser',
                'inputs': {'seed': 'str'},
                'outputs': {'result': 'str'},
            }
        },
    ]
    manager.available_preprocesses = _AvailableEntryPoints(
        ['workspace_parser'],
        {'workspace_parser': _EntryPoint(_MappingFailurePreprocess)},
    )
    manager.preprocess_group = 'FlexBESynthesis.preprocesses'

    with pytest.raises(MappingValidationError, match='missing outcome mapping'):
        FlexBESynthesisActionServer.execute_preprocesses(manager)

    assert manager.data['error_code'].value == SynthesisErrorCode.MAPPING_INVALID
    assert (
        manager._result.error_code.value
        == SynthesisErrorCode.MAPPING_INVALID
    )
    assert 'Error occurred while executing preprocess' in manager._logger.errors[-1]
    assert 'missing outcome mapping' in manager._logger.errors[-1]
    assert 'result' not in manager.data


def test_execute_preprocesses_reports_userdata_validation_failures():
    """Userdata validation errors should use the userdata-specific error code."""
    manager = _manager_stub()
    manager.data = {
        'seed': 'ready',
        'system_name': 'stale_system',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager.statistics = {
        'preprocesses': {
            'pipeline': {'preprocess_0_capability_loader': {'execution_time': None}}
        }
    }
    manager.preprocesses_pipeline = [
        {
            'entry_point': {
                'name': 'capability_loader',
                'inputs': {'seed': 'str'},
                'outputs': {'result': 'str'},
            }
        },
    ]
    manager.available_preprocesses = _AvailableEntryPoints(
        ['capability_loader'],
        {'capability_loader': _EntryPoint(_UserdataFailurePreprocess)},
    )
    manager.preprocess_group = 'FlexBESynthesis.preprocesses'

    with pytest.raises(UserdataValidationError, match='missing userdata key'):
        FlexBESynthesisActionServer.execute_preprocesses(manager)

    assert manager.data['error_code'].value == SynthesisErrorCode.USERDATA_INVALID
    assert (
        manager._result.error_code.value
        == SynthesisErrorCode.USERDATA_INVALID
    )
    assert 'Error occurred while executing preprocess' in manager._logger.errors[-1]
    assert 'missing userdata key' in manager._logger.errors[-1]
    assert 'result' not in manager.data


def test_execute_callback_validates_reloaded_process_pipeline():
    """Per-request process reloads should rebuild plugin state before execution."""
    manager = _manager_stub()
    manager.statistics = {
        'processes': {'pipeline': {'process_0_stale': {'execution_time': None}}}
    }
    manager.data = {
        'seed': 'ready',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager._preprocessed_data = dict(manager.data)
    manager.spec_path = '/tmp/spec.yaml'
    manager._publish_feedback = lambda goal, status, progress: None
    manager._check_cancel_requested = lambda goal, stage_name: False
    manager._update_request_spec_settings = lambda goal: None
    manager._prepare_output_directory = lambda goal: None
    manager._save_execution_statistics = lambda: None
    manager.available_processes = _AvailableEntryPoints(['fresh'])
    manager.processes_pipeline = [{'entry_point': {'name': 'stale'}}]
    manager.processor_plugins = [
        Plugin('stale', [], [])
    ]

    def _load_processes():
        manager.data['system_name'] = 'yaml_system'
        manager.data['synthesis_options'] = 'yaml_options'
        manager.processes_pipeline = [
            {
                'entry_point': {
                    'name': 'fresh',
                    'inputs': {'seed': 'str'},
                    'outputs': {'result': 'str', 'state_defn': 'List[StateInstantiation]'},
                }
            }
        ]

    def _execute_processes(goal):
        del goal
        manager.statistics['processes']['execution_time'] = 0.0
        assert [plugin.name for plugin in manager.processor_plugins] == ['fresh']
        assert manager.processor_plugins[0].inputs == ['seed']
        assert manager.data['system_name'] == 'request_system'
        assert manager.data['synthesis_options'] == 'request_options'
        return [['state']]

    manager.load_processes = _load_processes
    manager.execute_processes = _execute_processes
    goal = _ActionGoal()

    result = FlexBESynthesisActionServer.execute_callback(manager, goal)

    assert [plugin.name for plugin in manager.processor_plugins] == ['fresh']
    assert manager.processor_outputs == {'result': 'str', 'state_defn': 'List[StateInstantiation]'}
    assert manager.statistics['processes']['pipeline'] == {
        'process_0_fresh': {'execution_time': None}
    }
    assert goal.succeeded
    assert result.states == ['state']


def test_execute_callback_fails_action_on_invalid_reloaded_pipeline(tmp_path):
    """Invalid per-request pipeline reloads should abort with failure code."""
    pipeline_file = tmp_path / 'processes.yaml'
    pipeline_file.write_text('', encoding='utf-8')

    manager = _manager_stub()
    manager.statistics = {
        'processes': {'pipeline': {'process_0_stale': {'execution_time': None}}}
    }
    manager.data = {
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager._preprocessed_data = {'error_code': manager.data['error_code']}
    manager.processes_data_filepath = ''
    manager.processes_filepath = str(pipeline_file)
    manager.processes_pipeline = [{'entry_point': {'name': 'stale'}}]
    manager.processor_plugins = [object()]
    manager.processor_outputs = {'stale': 'str'}
    manager._publish_feedback = lambda goal, status, progress: None
    manager._check_cancel_requested = lambda goal, stage_name: False
    manager._save_execution_statistics = lambda: None
    goal = _ActionGoal()

    result = FlexBESynthesisActionServer.execute_callback(manager, goal)

    assert goal.aborted
    assert not goal.succeeded
    assert result.error_code.value == SynthesisErrorCode.PIPELINE_INVALID
    assert manager.processes_pipeline is None


def test_execute_callback_sets_pipeline_invalid_on_validate_failure():
    """A ValidationError raised by validate() should produce PIPELINE_INVALID, not UNKNOWN."""
    manager = _manager_stub()
    manager.statistics = {'processes': {}}
    manager.data = {
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager._preprocessed_data = {'error_code': manager.data['error_code']}
    manager._publish_feedback = lambda goal, status, progress: None
    manager._check_cancel_requested = lambda goal, stage_name: False
    manager.load_processes = lambda: None
    manager._update_request_spec_settings = lambda goal: None
    manager._prepare_output_directory = lambda goal: None
    manager._save_execution_statistics = lambda: None
    manager.available_processes = _AvailableEntryPoints([])
    manager.processes_pipeline = [{'entry_point': {'name': 'missing'}}]
    manager.processor_plugins = []
    manager.processor_outputs = {}
    goal = _ActionGoal()

    result = FlexBESynthesisActionServer.execute_callback(manager, goal)

    assert goal.aborted
    assert result.error_code.value == SynthesisErrorCode.PIPELINE_INVALID


def test_execute_callback_success_log_uses_callback_duration(monkeypatch):
    """Success logging should report callback wall-clock time, not process time."""
    manager = _manager_stub()
    manager.statistics = {'processes': {}}
    manager.data = {
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager._preprocessed_data = {'error_code': manager.data['error_code']}
    manager._publish_feedback = lambda goal, status, progress: None
    manager._check_cancel_requested = lambda goal, stage_name: False
    manager.load_processes = lambda: None
    manager._update_request_spec_settings = lambda goal: None
    manager.validate = lambda: None
    manager._prepare_output_directory = lambda goal: None
    manager._save_execution_statistics = lambda: None
    times = iter([10.0, 13.25])
    monkeypatch.setattr(synthesis_manager.time, 'time', lambda: next(times))

    def _execute_processes(goal):
        del goal
        manager.statistics['processes']['execution_time'] = 0.5
        return [['state']]

    manager.execute_processes = _execute_processes
    goal = _ActionGoal()

    result = FlexBESynthesisActionServer.execute_callback(manager, goal)

    assert goal.succeeded
    assert result.states == ['state']
    assert manager.statistics['processes']['execution_time'] == 3.25
    assert '3.250 seconds' in manager._logger.infos[-2]


def test_execute_callback_allocates_fresh_result_per_goal():
    """Each action request should receive an independent result message."""
    manager = _manager_stub()
    manager.statistics = {'processes': {}}
    manager.data = {'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)}
    manager._preprocessed_data = {'error_code': manager.data['error_code']}
    manager._publish_feedback = lambda goal, status, progress: None
    manager._check_cancel_requested = lambda goal, stage_name: False
    manager.load_processes = lambda: None
    manager.validate = lambda: None
    manager._update_request_spec_settings = lambda goal: None
    manager._prepare_output_directory = lambda goal: None
    manager._save_execution_statistics = lambda: None
    call_count = {'count': 0}

    def _execute_processes(goal):
        del goal
        call_count['count'] += 1
        state = StateInstantiation()
        state.state_path = f"/state_{call_count['count']}"
        manager.statistics['processes']['execution_time'] = 0.0
        return [[state]]

    manager.execute_processes = _execute_processes

    first = FlexBESynthesisActionServer.execute_callback(manager, _ActionGoal())
    second = FlexBESynthesisActionServer.execute_callback(manager, _ActionGoal())

    assert first is not second
    assert first.states[0].state_path == '/state_1'
    assert second.states[0].state_path == '/state_2'


def test_validate_rejects_undefined_pipeline_input():
    """Validation should fail before runtime if a configured input is missing."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'missing': 'str'},
                'outputs': {'result': 'str'},
            }
        },
    ]

    with pytest.raises(ValidationError, match="input 'missing' not defined"):
        FlexBESynthesisActionServer.validate(manager)


def test_validate_rejects_mismatched_existing_input_type_by_default():
    """Strict validation should reject mismatches against initial manager data."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'seed': 'int'},
                'outputs': {'result': 'str'},
            }
        },
    ]

    with pytest.raises(ValidationError, match="Input types differ for 'consumer'"):
        FlexBESynthesisActionServer.validate(manager)


def test_validate_can_warn_for_mismatched_existing_input_type():
    """Warning-only validation should be configurable per process."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'consumer',
                'strict_type_validation': False,
                'inputs': {'seed': 'int'},
                'outputs': {'result': 'str', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]

    FlexBESynthesisActionServer.validate(manager)

    assert [plugin.name for plugin in manager.processor_plugins] == ['consumer']
    assert len(manager._logger.warnings) == 1
    assert "Input types differ for 'consumer'" in manager._logger.warnings[0]


def test_validate_can_warn_for_one_pipeline_input_type_mismatch():
    """Warning-only validation should apply only to the configured process."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(
        ['producer', 'consumer', 'strict_consumer']
    )
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'int'},
            }
        },
        {
            'entry_point': {
                'name': 'consumer',
                'strict_type_validation': False,
                'inputs': {'produced': 'str'},
                'outputs': {'result': 'str'},
            }
        },
        {
            'entry_point': {
                'name': 'strict_consumer',
                'inputs': {'produced': 'int'},
                'outputs': {'strict_result': 'str', 'state_defn': 'List[StateInstantiation]'},
            }
        },
    ]

    FlexBESynthesisActionServer.validate(manager)

    assert [plugin.name for plugin in manager.processor_plugins] == [
        'producer',
        'consumer',
        'strict_consumer',
    ]
    assert len(manager._logger.warnings) == 1
    assert "Input types differ for 'consumer'" in manager._logger.warnings[0]


def test_validate_rejects_mismatched_pipeline_input_type_by_default():
    """Strict validation should reject mismatches between pipeline steps."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer', 'consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'int'},
            }
        },
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'produced': 'str'},
                'outputs': {'result': 'str'},
            }
        },
    ]

    with pytest.raises(ValidationError, match="Input types differ for 'consumer'"):
        FlexBESynthesisActionServer.validate(manager)


def test_validate_rejects_mismatched_output_overwrite_by_default():
    """Strict validation should reject incompatible output overwrites."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer', 'replacement'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'int'},
            }
        },
        {
            'entry_point': {
                'name': 'replacement',
                'inputs': {'seed': 'str'},
                'outputs': {'produced': 'str'},
            }
        },
    ]

    with pytest.raises(
        ValidationError,
        match="'replacement' will overwrite previous data for output 'produced'",
    ):
        FlexBESynthesisActionServer.validate(manager)


def test_validate_rejects_unknown_input_type():
    """Unknown configured input type names should fail validation."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['consumer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'consumer',
                'inputs': {'seed': 'MysteryType'},
                'outputs': {'result': 'str'},
            }
        },
    ]

    with pytest.raises(
        ValidationError,
        match="Unknown input type 'MysteryType' for 'seed'",
    ):
        FlexBESynthesisActionServer.validate(manager)


def test_validate_rejects_unknown_output_type():
    """Unknown configured output type names should fail validation."""
    manager = _manager_stub()
    manager.available_processes = _AvailableEntryPoints(['producer'])
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'producer',
                'inputs': {'seed': 'str'},
                'outputs': {'result': 'MysteryType'},
            }
        },
    ]

    with pytest.raises(
        ValidationError,
        match="Unknown output type 'MysteryType' for 'result'",
    ):
        FlexBESynthesisActionServer.validate(manager)


def test_save_execution_statistics_logs_save_failures():
    """Statistics cleanup should not raise if artifact persistence fails."""
    manager = _manager_stub()
    manager.data['spec_name'] = 'demo_spec'
    manager.statistics = {'processes': {'success': False}}

    def _raise_save_error(proc_id, output_name, output_data):
        del proc_id, output_name, output_data
        raise OSError('disk unavailable')

    manager.save_processor_output = _raise_save_error

    FlexBESynthesisActionServer._save_execution_statistics(manager)

    assert manager._logger.errors == [
        'Failed to save synthesis execution statistics: OSError: disk unavailable'
    ]


def test_save_execution_statistics_skips_unresolved_request_spec_name():
    """Early failures before spec_name resolution should not log save errors."""
    manager = _manager_stub()
    manager.data['spec_name'] = 'req:spec_name'
    manager.statistics = {'processes': {'success': False}}

    def _raise_if_called(proc_id, output_name, output_data):
        del proc_id, output_name, output_data
        raise AssertionError('save_processor_output should not be called')

    manager.save_processor_output = _raise_if_called

    FlexBESynthesisActionServer._save_execution_statistics(manager)

    assert manager._logger.errors == []
    assert manager._logger.warnings == [
        (
            'Skipping synthesis execution statistics save because spec_name is '
            "unresolved ('req:spec_name')."
        )
    ]


def test_save_processor_output_rejects_unsafe_output_name(tmp_path):
    """Processor artifacts should reject unsafe YAML output names before writing."""
    manager = _manager_stub()
    manager.synthesis_home = str(tmp_path)
    manager.data = {
        'system_name': 'demo_system',
        'spec_name': 'demo_spec',
    }
    (tmp_path / 'demo_system').mkdir()

    with pytest.raises(ValueError, match='Invalid output_name'):
        FlexBESynthesisActionServer.save_processor_output(
            manager,
            'process_0_generator',
            '../escape',
            {'result': 'unsafe'},
        )

    assert not (tmp_path / 'demo_system' / 'demo_spec').exists()


def test_save_preprocessor_output_rejects_unsafe_proc_id(tmp_path):
    """Preprocessor artifacts should reject unsafe process IDs before writing."""
    manager = _manager_stub()
    manager.synthesis_home = str(tmp_path)
    manager.data = {'system_name': 'demo_system'}
    (tmp_path / 'demo_system').mkdir()

    with pytest.raises(ValueError, match='Invalid proc_id'):
        FlexBESynthesisActionServer.save_preprocessor_output(
            manager,
            '../preprocess_0_loader',
            'safe_output',
            {'result': 'unsafe'},
        )

    assert not (tmp_path / 'demo_system' / 'preprocessor_outputs').exists()


def test_save_processor_output_warns_for_fallback_yaml_type(tmp_path):
    """Unknown artifact objects should be logged before fallback serialization."""
    manager = _manager_stub()
    manager.synthesis_home = str(tmp_path)
    manager.data = {
        'system_name': 'demo_system',
        'spec_name': 'demo_spec',
    }
    (tmp_path / 'demo_system').mkdir()

    FlexBESynthesisActionServer.save_processor_output(
        manager,
        'process_0_generator',
        'result',
        {'nested': [_UnknownYamlObject()]},
    )

    assert manager._logger.warnings == [
        (
            "Serializing unknown YAML type '_UnknownYamlObject' in processor "
            "output 'process_0_generator/result' using fallback object "
            'serialization.'
        )
    ]
    assert (
        tmp_path
        / 'demo_system'
        / 'demo_spec'
        / 'processor_outputs'
        / 'process_0_generator_result.yaml'
    ).exists()


def test_check_cancel_requested_cancels_goal():
    """Cancel helper should mark the action result as preempted."""
    manager = _manager_stub()
    goal = _Goal([True])

    assert FlexBESynthesisActionServer._check_cancel_requested(manager, goal, 'setup')

    assert goal.canceled_called
    assert goal.feedback[-1].status == 'canceling: setup'
    assert manager._result.error_code.value == SynthesisErrorCode.PREEMPTED
    assert manager._result.states == []


def test_cancel_callback_cancels_active_process():
    """Action cancel callback should notify the process currently running."""
    manager = _manager_stub()
    active_process = _CancelableProcess()
    manager._active_process_instance = active_process

    response = FlexBESynthesisActionServer.cancel_callback(manager, object())

    assert active_process.canceled
    assert response.name == 'ACCEPT'


def test_execute_processes_cancels_before_first_plugin():
    """Cancellation before a process should avoid loading/running plugins."""
    _Process.canceled = []
    _Process.calls = []
    manager = _manager_stub()
    manager.processor_plugins = [
        Plugin('first', ['seed'], ['result'])
    ]
    manager.available_processes = {'first': _EntryPoint(_Process)}
    manager.statistics = {
        'processes': {'pipeline': {'process_0_first': {'execution_time': None}}}
    }
    goal = _Goal([True])

    assert FlexBESynthesisActionServer.execute_processes(manager, goal) == []

    assert goal.canceled_called
    assert _Process.calls == []
    assert _Process.canceled == []
    assert 'result' not in manager.data
    assert manager._result.error_code.value == SynthesisErrorCode.PREEMPTED


def test_execute_processes_cancels_after_plugin_returns():
    """Cancellation after a process should avoid consuming its outputs."""
    _Process.canceled = []
    _Process.calls = []
    manager = _manager_stub()
    manager.processor_plugins = [
        Plugin('first', ['seed'], ['result'])
    ]
    manager.available_processes = {'first': _EntryPoint(_Process)}
    manager.statistics = {
        'processes': {'pipeline': {'process_0_first': {'execution_time': None}}}
    }
    goal = _Goal([False, True])

    assert FlexBESynthesisActionServer.execute_processes(manager, goal) == []

    assert goal.canceled_called
    assert _Process.calls == [['ready']]
    assert _Process.canceled == [['ready']]
    assert 'result' not in manager.data
    assert manager._result.error_code.value == SynthesisErrorCode.PREEMPTED


def test_execute_processes_injects_manager_synthesis_home():
    """Process instances should receive the manager's resolved artifact root."""
    manager = _manager_stub()
    manager.processor_plugins = [
        Plugin('first', ['seed'], ['result'])
    ]
    manager.available_processes = {'first': _EntryPoint(_PluginWithSynthesisHome)}
    manager.statistics = {
        'processes': {'pipeline': {'process_0_first': {'execution_time': None}}}
    }
    goal = _Goal([False])

    FlexBESynthesisActionServer.execute_processes(manager, goal)

    assert manager.data['result'] == '/tmp/synthesis-home'


def test_execute_processes_returns_last_state_instantiation_output_by_type():
    """The final List[StateInstantiation] output should win regardless of plugin name."""
    manager = _manager_stub()
    manager.data = {
        'first_label': 'first_sm',
        'second_label': 'second_sm',
        'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
    }
    manager.available_processes = _AvailableEntryPoints(
        ['make_first', 'make_second'],
        {
            'make_first': _EntryPoint(_StateMachineProducer),
            'make_second': _EntryPoint(_StateMachineProducer),
        },
    )
    manager.processes_pipeline = [
        {
            'entry_point': {
                'name': 'make_first',
                'inputs': {'first_label': 'str'},
                'outputs': {'first_result': 'List[StateInstantiation]'},
            }
        },
        {
            'entry_point': {
                'name': 'make_second',
                'inputs': {'second_label': 'str'},
                'outputs': {'second_result': 'List[StateInstantiation]'},
            }
        },
    ]
    FlexBESynthesisActionServer.validate(manager)
    goal = _Goal([False])

    result = FlexBESynthesisActionServer.execute_processes(manager, goal)

    assert result[0][0].state_path == 'second_sm'
    assert manager.data['first_result'][0].state_path == 'first_sm'
    assert manager.data['second_result'][0].state_path == 'second_sm'


@pytest.mark.parametrize(
    ('process_class', 'expected_message'),
    (
        (
            _ShortOutputProcess,
            'returned 0 output(s), but the pipeline declares 1 output(s)',
        ),
        (
            _ExtraOutputProcess,
            'returned 2 output(s), but the pipeline declares 1 output(s)',
        ),
    ),
)
def test_execute_processes_reports_plugin_output_count_mismatch(
    process_class,
    expected_message,
):
    """Plugin/YAML output count mismatches should return controlled failures."""
    process_class.canceled = []
    process_class.calls = []
    manager = _manager_stub()
    manager.processor_plugins = [
        type(
            'Plugin',
            (),
            {'name': 'first', 'inputs': ['seed'], 'outputs': ['result']},
        )()
    ]
    manager.available_processes = {'first': _EntryPoint(process_class)}
    manager.statistics = {
        'processes': {'pipeline': {'process_0_first': {'execution_time': None}}}
    }
    goal = _Goal([False])

    assert FlexBESynthesisActionServer.execute_processes(manager, goal) == []

    assert manager.data['error_code'].value == SynthesisErrorCode.PIPELINE_INVALID
    assert (
        manager._result.error_code.value
        == SynthesisErrorCode.PIPELINE_INVALID
    )
    assert expected_message in manager._logger.errors[-1]
    assert 'result' not in manager.data
    assert process_class.canceled == [['ready']]


def test_execute_processes_reports_runtime_error_as_pipeline_failure():
    """Process runtime errors must not propagate past the pipeline manager."""
    _RuntimeErrorProcess.canceled = []
    _RuntimeErrorProcess.calls = []
    manager = _manager_stub()
    manager.processor_plugins = [
        Plugin('compiler', ['seed'], ['result'])
    ]
    manager.available_processes = {'compiler': _EntryPoint(_RuntimeErrorProcess)}
    manager.statistics = {
        'processes': {'pipeline': {'process_0_compiler': {'execution_time': None}}}
    }
    goal = _Goal([False])

    assert FlexBESynthesisActionServer.execute_processes(manager, goal) == []

    assert manager.data['error_code'].value == SynthesisErrorCode.PIPELINE_INVALID
    assert manager._result.error_code.value == SynthesisErrorCode.PIPELINE_INVALID
    assert 'RuntimeError: compiler failed' in manager._pipeline_messages[-1]
    assert 'compiler failed' in manager._logger.errors[-1]
    assert _RuntimeErrorProcess.canceled == [['ready']]


def test_execute_callback_preserves_process_failure_code():
    """Callback no-result handling should not overwrite process failure codes."""
    manager = _manager_stub()
    failure_code = SynthesisErrorCode(value=SynthesisErrorCode.PIPELINE_INVALID)
    manager.statistics = {'processes': {}}
    manager.data = {'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)}
    manager._preprocessed_data = {'error_code': manager.data['error_code']}
    manager._publish_feedback = lambda goal, status, progress: None
    manager._check_cancel_requested = lambda goal, stage_name: False
    manager.load_processes = lambda: None
    manager.validate = lambda: None
    manager._update_request_spec_settings = lambda goal: None
    manager._prepare_output_directory = lambda goal: None
    manager._save_execution_statistics = lambda: None

    def _execute_processes(goal):
        del goal
        manager.data['error_code'] = failure_code
        return []

    manager.execute_processes = _execute_processes
    goal = _ActionGoal()

    result = FlexBESynthesisActionServer.execute_callback(manager, goal)

    assert goal.aborted
    assert not goal.succeeded
    assert result.error_code.value == SynthesisErrorCode.PIPELINE_INVALID


@pytest.mark.parametrize(
    'value',
    [
        'vending_demo',
        'VendingDemoSM',
        'spec-1.2_3',
    ],
)
def test_validate_path_component_accepts_safe_names(value):
    """Output path components should allow ordinary package/spec names."""
    assert FlexBESynthesisActionServer._validate_path_component(value, 'spec_name') == value


@pytest.mark.parametrize(
    'value',
    [
        '',
        '.',
        '..',
        '../escape',
        'nested/spec',
        'nested\\spec',
        'name with spaces',
        'name:$bad',
    ],
)
def test_validate_path_component_rejects_unsafe_names(value):
    """Output path components should reject traversal and unsupported names."""
    with pytest.raises(ValueError, match='Invalid spec_name'):
        FlexBESynthesisActionServer._validate_path_component(value, 'spec_name')


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('', ''),
        ('specs', 'specs'),
        ('nested/specs-v1', 'nested/specs-v1'),
    ],
)
def test_validate_relative_path_accepts_safe_paths(value, expected):
    """Relative paths should allow safe nested package-share folders."""
    assert (
        FlexBESynthesisActionServer._validate_relative_path(value, 'spec_folder')
        == expected
    )


@pytest.mark.parametrize(
    'value',
    [
        '/absolute',
        '.',
        '..',
        '../escape',
        'nested/../escape',
        'nested//folder',
        'nested\\folder',
        'folder with spaces',
    ],
)
def test_validate_relative_path_rejects_unsafe_paths(value):
    """Relative paths should reject traversal and unsupported components."""
    with pytest.raises(ValueError, match='Invalid spec_folder'):
        FlexBESynthesisActionServer._validate_relative_path(value, 'spec_folder')
