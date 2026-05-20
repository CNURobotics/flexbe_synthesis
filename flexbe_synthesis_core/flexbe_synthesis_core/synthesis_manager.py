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

"""ROS2 action server that runs the FlexBE synthesis pipeline."""

from copy import deepcopy
from importlib.metadata import entry_points
import inspect
import os
import re
import time
import traceback

from ament_index_python.packages import get_package_share_directory
from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_core.base_preprocess import BasePreProcess
from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_core.error_code_map import get_error_code_text
from flexbe_synthesis_core.pipeline_type_validation import TYPE_MAPPING, validate_types
from flexbe_synthesis_core.plugin import Plugin
from flexbe_synthesis_core.validation_error import (
    MappingValidationError,
    UserdataValidationError,
    ValidationError,
)
from flexbe_synthesis_msgs.action import FlexBESynthesis
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode
import rclpy
from rclpy.action import ActionServer, CancelResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
import yaml


class SynthesisYamlDumper(yaml.SafeDumper):
    """YAML dumper that keeps synthesis output readable and serializable."""

    def represent_str(self, data):
        """Render strings in double-quoted style."""
        return self.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    def represent_synthesis_error_code(self, data):
        """Serialize `SynthesisErrorCode` as integer values."""
        return self.represent_int(data.value)

    @staticmethod
    def fallback_representer(dumper, data):
        """Represent unknown objects by `__dict__` or fallback string."""
        try:
            return dumper.represent_dict(data.__dict__)
        except AttributeError:
            return dumper.represent_str(str(data))


SynthesisYamlDumper.add_multi_representer(object, SynthesisYamlDumper.fallback_representer)
SynthesisYamlDumper.add_representer(
    SynthesisErrorCode, SynthesisYamlDumper.represent_synthesis_error_code
)
SynthesisYamlDumper.add_representer(str, SynthesisYamlDumper.represent_str)


class FlexBESynthesisActionServer(Node):
    """Own and execute the configured FlexBE synthesis preprocess/process pipelines."""

    def __init__(self, name):
        """Initialize server configuration, load pipelines, and validate dataflow."""
        super().__init__(name)
        self._result = None
        self._action_server = None

        self.declare_parameter('preprocesses_filepath', '')
        self.declare_parameter('preprocesses_data_filepath', '')
        self.declare_parameter('processes_filepath', '')
        self.declare_parameter('processes_data_filepath', '')
        self.declare_parameter('system_name', '')
        self.declare_parameter('capabilities_path', '')
        self.declare_parameter('spec_path', '')
        self.declare_parameter('automaton_path', '')
        self.declare_parameter('global_mappings_path', '')
        self.declare_parameter('custom_mappings_path', '')
        self.declare_parameter('synthesis_home', '')
        self.declare_parameter('save_outputs', True)
        self.declare_parameter('verbose', False)

        self.preprocess_filepath = self.get_parameter('preprocesses_filepath').value
        self.preprocess_data_filepath = self.get_parameter('preprocesses_data_filepath').value
        self.processes_filepath = self.get_parameter('processes_filepath').value
        self.processes_data_filepath = self.get_parameter('processes_data_filepath').value
        self.system_name = self.get_parameter('system_name').value
        self.capabilities_path = self.get_parameter('capabilities_path').value
        self.spec_path = self.get_parameter('spec_path').value
        self.automaton_path = self.get_parameter('automaton_path').value
        self.global_mappings_path = self.get_parameter('global_mappings_path').value
        self.custom_mappings_path = self.get_parameter('custom_mappings_path').value
        self.synthesis_home = fpths.get_synthesis_home(
            self.get_parameter('synthesis_home').value
        )
        self.save_outputs = self.get_parameter('save_outputs').value
        self.verbose = self.get_parameter('verbose').value

        if not self.processes_filepath or not self.preprocess_filepath:
            self.get_logger().error('Missing required configuration file paths!')
            raise ValueError('Processes and preprocesses file paths must be provided')

        self.get_logger().info(

                'FlexBESynthesisServer initialized with:\n'
                f'  Preprocess config filepath:\n    {self.preprocess_filepath!r}\n'
                '  Preprocess additional data filepath:\n'
                f"    '{self.preprocess_data_filepath}'\n"
                '-------\n'
                f'  Processes config filepath:\n    {self.processes_filepath!r}\n'
                '  Processes additional data filepath:\n'
                f"    '{self.processes_data_filepath}'\n"
                '-------\n'
                f"  Global mappings path:\n    '{self.global_mappings_path}'\n"
                f"  Custom mappings path:\n    '{self.custom_mappings_path}'\n"
                f"  Capabilities path:\n    '{self.capabilities_path}'\n"
                f"  Specs path:\n    '{self.spec_path}'\n"
                f"  Automaton path:\n    '{self.automaton_path}'\n"
                f"  Synthesis home:\n    '{self.synthesis_home}'"

        )

        self.processor_outputs = {}
        self.processor_plugins = []
        self.data = {
            'global_mappings_path': self.global_mappings_path,
            'custom_mappings_path': self.custom_mappings_path,
            'capabilities_path': self.capabilities_path,
            'spec_path': self.spec_path,
            'automaton_path': self.automaton_path,
            'state_mappings': {},
            'synthesis_request': FlexBESynthesisRequest(),
            'synthesis_options': '',
            'system_name': 'unknown',
            'specs_output_dir_path': 'unknown',
            'error_code': SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN),
            'spec_name': 'req:spec_name',
        }

        self.statistics = {'preprocesses': {}, 'processes': {}}
        self.preprocesses_pipeline = None
        self.processes_pipeline = None
        self.preprocess_type_aliases = {}
        self.process_type_aliases = {}
        self.preprocess_type_mapping = dict(TYPE_MAPPING)
        self.process_type_mapping = dict(TYPE_MAPPING)
        self._active_process_instance = None
        self._pipeline_messages = []
        self.preprocess_group = fpths._PREPROCESSES
        self.process_group = fpths._PROCESSES

        self.get_logger().info('Find relevant entry points for FlexBE synthesis ...')
        self.available_preprocesses = entry_points(group=self.preprocess_group)
        self.available_processes = entry_points(group=self.process_group)

        self.get_logger().info('Load pre-processors ...')
        self.load_preprocesses()
        self.validate_preprocesses()

        print(f"Using '{self.data['system_name']}' for system capabilities")
        system_dir = os.path.join(self.synthesis_home, self.data['system_name'])
        os.makedirs(system_dir, exist_ok=True)
        print(f"Using '{system_dir}' for system outputs.", flush=True)

        self.get_logger().info('\n\nExecute pre-processors ...')
        self.execute_preprocesses()
        self._preprocessed_data = deepcopy(self.data)

        self.get_logger().info('\n\nLoad processors ...')
        self.load_processes()
        if self.processes_pipeline is None or len(self.processes_pipeline) == 0:
            return

        self.get_logger().info('\n\nCreate the synthesis action server ...')
        self._action_server = ActionServer(
            self,
            FlexBESynthesis,
            'flexbe_synthesis',
            execute_callback=self.execute_callback,
            cancel_callback=self.cancel_callback,
        )

        self.get_logger().info('\n\nValidate pipeline data flow ...')
        self.validate()

        self._print_preprocess_summary()
        self.get_logger().info('\n\n\033[32mReady to begin FlexBE synthesis ...\033[0m\n')
        self.save_preprocessor_output(
            'preprocesses',
            'statistics',
            self.statistics['preprocesses'],
        )

    def destroy(self):
        """Destroy ROS action server and node resources."""
        if self._action_server is not None:
            self._action_server.destroy()
        super().destroy_node()

    def _print_preprocess_summary(self):
        """Print a consolidated warning summary collected during preprocessing."""
        skipped = self.data.get('workspace_skipped', [])
        if not skipped:
            return
        sep = 30 * '-'
        print(f'\n{sep} Pre-synthesis warnings {sep}', flush=True)
        print(
            f'\033[33mWorkspaceParser: skipped {len(skipped)} state/behavior '
            'implementation(s) with unmapped outcomes.\n'
            'Add the outcome name(s) to global_mappings.yaml to include them:\033[0m'
        )
        for msg in skipped:
            print(f'\033[33m{msg}\033[0m')
        print(sep + ' End warnings ' + sep + '\n', flush=True)

    def execute_callback(self, goal):
        """
        Run the synthesis pipeline for one action goal and return the result.

        Deep-copies preprocessed data so each goal is isolated, loads process
        plugins from the pipeline YAML, applies per-request data (goals, initial
        conditions, spec settings), validates I/O compatibility, then runs the
        process pipeline in declaration order.  Cancellation is checked between
        each major phase and returns a PREEMPTED result immediately if requested.

        Returns a FlexBESynthesis.Result with ``states``, ``error_code``, and
        ``messages`` populated.  Aborts the goal handle if the pipeline produces
        no List[StateInstantiation] output.
        """
        self.statistics['processes']['success'] = False
        self.statistics['processes']['number of states'] = -1
        result = FlexBESynthesis.Result()
        result.error_code = SynthesisErrorCode(value=SynthesisErrorCode.UNKNOWN)
        result.states = []
        result.messages = []
        self._result = result
        self._pipeline_messages = []
        execute_start = time.time()

        try:
            if self._check_cancel_requested(goal, 'request setup'):
                return result
            self.data = deepcopy(self._preprocessed_data)
            self.load_processes()
            self._apply_goal_request_data(goal)
            if self._check_cancel_requested(goal, 'process loading'):
                return result
            self._update_request_spec_settings(goal)
            if self._check_cancel_requested(goal, 'request specification setup'):
                return result
            try:
                self.validate()
            except ValidationError as exc:
                self._set_pipeline_failure(str(exc))
                raise
            if self._check_cancel_requested(goal, 'process validation'):
                return result
            self._prepare_output_directory(goal)
            if self._check_cancel_requested(goal, 'output directory setup'):
                return result

            results = self.execute_processes(goal)
            if result.error_code.value == SynthesisErrorCode.PREEMPTED:
                return result
            if len(results) < 1:
                goal.abort()
                if self.data['error_code'].value in (
                    SynthesisErrorCode.SUCCESS,
                    SynthesisErrorCode.UNKNOWN,
                ):
                    self.data['error_code'] = SynthesisErrorCode(
                        value=SynthesisErrorCode.SM_GENERATION_FAILED
                    )
                    self.get_logger().error(
                        'Process pipeline produced no List[StateInstantiation] output.'
                    )
                result.error_code = SynthesisErrorCode(
                    value=self.data['error_code'].value
                )
                return result

            if self.verbose:
                print(f"\n\n{10 * '='} {len(results[0])} States {10 * '='}\n")
                for state in results[0]:
                    print(state)
                print(f"{10 * '='} States {10 * '='}\n")
                print(30 * '=' + '\n\n', flush=True)

            result.error_code = SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)
            result.states = results[0]
            self._publish_feedback(goal, 'complete', 1.0)
            goal.succeed()
            self.statistics['processes']['success'] = True
            self.statistics['processes']['execution_time'] = time.time() - execute_start
            self.get_logger().info(

                    '\n\n\033[32mSuccessfully synthesized state machine '
                    f'with {len(result.states)} states in '
                    f"{self.statistics['processes']['execution_time']:.3f} "
                    'seconds!\033[0m\n'

            )
            return result

        except (
            AttributeError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            self.get_logger().error(
                f'\n\n\033[33mSynthesis failed '
                f"(error_code={self.data['error_code'].value}): {exc}\033[0m"
            )
            result.error_code = SynthesisErrorCode(value=self.data['error_code'].value)
            goal.abort()
            print('Finished handling exception!', flush=True)
            return result
        finally:
            if 'execution_time' not in self.statistics['processes']:
                self.statistics['processes']['execution_time'] = (
                    time.time() - execute_start
                )
            self.statistics['processes']['flexbe_states'] = len(result.states)
            result.messages = list(getattr(self, '_pipeline_messages', []))
            self._save_execution_statistics()
            self.data = deepcopy(self._preprocessed_data)
            self.get_logger().info('\n\n\033[32mReady to continue FlexBE synthesis ...\033[0m\n')

    def _apply_goal_request_data(self, goal):
        """Apply action-goal values that must take precedence over process YAML."""
        self.data['synthesis_request'] = goal.request.request
        self.data['synthesis_options'] = goal.request.synthesis_options
        try:
            self.data['system_name'] = self._validate_path_component(
                goal.request.request.system_name,
                'system_name',
            )
        except ValueError as exc:
            self._set_invalid_request_failure(str(exc))
            raise
        if goal.request.request.synthesis_timeout_s > 0.0:
            self.data['synthesis_timeout_s'] = goal.request.request.synthesis_timeout_s

    def _fail_invalid_pipeline_load(self, pipeline_kind, filepath, reason):
        """Clear stale pipeline state and raise a controlled pipeline-load error."""
        if pipeline_kind == 'processes':
            self.processes_pipeline = None
            self.processor_plugins = []
            self.processor_outputs = {}
            self.statistics['processes'].pop('pipeline', None)
        elif pipeline_kind == 'preprocesses':
            self.preprocesses_pipeline = None
            self.statistics['preprocesses'].pop('pipeline', None)

        message = f"Invalid {pipeline_kind} pipeline file '{filepath}': {reason}"
        self._set_pipeline_failure(message)
        raise ValidationError(message, kind=ValidationError.PIPELINE_LOAD)

    def _update_request_spec_settings(self, goal):
        """Apply request values for spec name/path when configured as ``req:`` references."""
        if 'spec_path' in self.data:
            spec_path = self.data['spec_path']
            if isinstance(spec_path, str) and spec_path.startswith('req:'):
                try:
                    spec_path = self._resolve_request_value('spec_path', spec_path, goal)
                except ValueError as exc:
                    self._set_invalid_request_failure(str(exc))
                    raise
                if not isinstance(spec_path, str) or spec_path == '':
                    message = (
                        f"Invalid spec_path: request field '{self.data['spec_path']}' "
                        'must be a non-empty string'
                    )
                    self._set_invalid_request_failure(message)
                    raise ValueError(message)

            if spec_path and spec_path[0] != '/':
                if 'spec_package' in self.data:
                    try:
                        spec_folder = self._validate_relative_path(
                            self.data.get('spec_folder', ''),
                            'spec_folder',
                        )
                    except ValueError as exc:
                        self._set_pipeline_failure(str(exc))
                        raise
                    pkg_path = get_package_share_directory(self.data['spec_package'])
                    spec_path = os.path.join(pkg_path, spec_folder, spec_path)

            self.data['spec_path'] = spec_path
            print(
                f"\033[33mUsing '{self.data['spec_path']}' specification file path.\033[0m",
                flush=True,
            )

        if isinstance(self.data['spec_name'], str) and self.data['spec_name'].startswith('req:'):
            req_ref = self.data['spec_name']
            try:
                req_name = self._resolve_request_value('spec_name', req_ref, goal)
            except ValueError as exc:
                self._set_invalid_request_failure(str(exc))
                raise
            if isinstance(req_name, str) and req_name != '':
                if req_name[0] == '/':
                    req_name = req_name[1:]
                try:
                    self.data['spec_name'] = self._validate_path_component(
                        req_name,
                        'spec_name',
                    )
                except ValueError as exc:
                    self._set_invalid_request_failure(str(exc))
                    raise
                print(
                    f"\033[33mUsing '{self.data['spec_name']}' name from request.\033[0m",
                    flush=True,
                )
            else:
                message = (
                    f"Invalid spec_name: request field '{req_ref}' must be a non-empty string"
                )
                self._set_invalid_request_failure(message)
                raise ValueError(message)
        elif self.data['spec_name'] != goal.request.request.spec_name:
            print(
                (
                    f"\033[33mUsing '{self.data['spec_name']}' name but request has "
                    f"'{goal.request.request.spec_name}'!\033[0m"
                ),
                flush=True,
            )

    def _prepare_output_directory(self, goal):
        """Ensure output directories exist for the current system/spec."""
        self.data['system_name'] = self._validate_path_component(
            self.data['system_name'],
            'system_name',
        )
        self.data['spec_name'] = self._validate_path_component(
            self.data['spec_name'],
            'spec_name',
        )
        system_dir = os.path.join(self.synthesis_home, self.data['system_name'])
        if not os.path.exists(system_dir):
            available = [
                d for d in os.listdir(self.synthesis_home)
                if os.path.isdir(os.path.join(self.synthesis_home, d))
            ] if os.path.isdir(self.synthesis_home) else []
            print(
                f"\033[31mGoal requested system '{self.data['system_name']}' but no "
                f"preprocessed configuration exists at '{system_dir}'.\n"
                f'    Available systems: {available}\033[0m',
                flush=True,
            )
            self.data['error_code'] = SynthesisErrorCode(
                value=SynthesisErrorCode.SYSTEM_CONFIG_NOT_FOUND
            )
            raise FileNotFoundError(system_dir)

        spec_dir = os.path.join(system_dir, self.data['spec_name'])
        os.makedirs(spec_dir, exist_ok=True)
        self.data['specs_output_dir_path'] = spec_dir

    @property
    def _ros_params(self):
        return {
            'system_name': self.system_name,
            'capabilities_path': self.capabilities_path,
            'spec_path': self.spec_path,
            'automaton_path': self.automaton_path,
            'global_mappings_path': self.global_mappings_path,
            'custom_mappings_path': self.custom_mappings_path,
            'verbose': self.verbose,
        }

    @staticmethod
    def _request_fields(goal):
        """Return the referenceable string fields of the current action request."""
        req = goal.request.request
        return {
            'spec_name': req.spec_name,
            'specification_file_name': req.specification_file_name,
            'system_name': req.system_name,
        }

    def _resolve_data_value(self, key, value):
        """Resolve a data-file value, expanding ``ros:param_name`` to its ROS parameter."""
        if isinstance(value, str) and value.startswith('ros:'):
            param_name = value[4:]
            if param_name not in self._ros_params:
                raise ValueError(
                    f"Unknown ROS parameter reference '{value}' for data key '{key}'. "
                    f'Valid references: {sorted(self._ros_params)}'
                )
            return self._ros_params[param_name]
        return value

    def _resolve_request_value(self, key, value, goal):
        """Resolve a ``req:field_name`` reference to the named request field."""
        field_name = value[4:]  # strip 'req:'
        fields = self._request_fields(goal)
        if field_name not in fields:
            raise ValueError(
                f"Unknown request field reference '{value}' for data key '{key}'. "
                f'Valid references: {sorted(fields)}'
            )
        return fields[field_name]

    @staticmethod
    def _validate_path_component(value, field_name):
        """Validate request-derived names used as output path components."""
        if not isinstance(value, str):
            raise ValueError(f'Invalid {field_name}: expected string, got {type(value)}')

        if value in {'', '.', '..'}:
            raise ValueError(f"Invalid {field_name}: '{value}' is not a safe path name")

        if os.path.basename(value) != value:
            raise ValueError(f"Invalid {field_name}: '{value}' must not contain path separators")

        if not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
            raise ValueError(
                f"Invalid {field_name}: '{value}' contains unsupported characters"
            )

        return value

    @classmethod
    def _validate_relative_path(cls, value, field_name):
        """Validate a relative path made of safe path components."""
        if not isinstance(value, str):
            raise ValueError(f'Invalid {field_name}: expected string, got {type(value)}')

        if value == '':
            return value

        if os.path.isabs(value):
            raise ValueError(f"Invalid {field_name}: '{value}' must be relative")

        if '\\' in value:
            raise ValueError(f"Invalid {field_name}: '{value}' must not contain backslashes")

        parts = value.split('/')
        for part in parts:
            cls._validate_path_component(part, field_name)

        return os.path.normpath(value)

    def cancel_callback(self, goal_handle):
        """
        Accept a cancel request and forward it to the active process plugin.

        Always returns CancelResponse.ACCEPT.  If a process plugin is currently
        executing, its ``cancel()`` method is called so it can terminate cleanly;
        the plugin is responsible for honouring the signal promptly.
        """
        del goal_handle
        self.get_logger().info('Received cancel request')
        active_process = getattr(self, '_active_process_instance', None)
        if active_process is not None:
            active_process.cancel()
        return CancelResponse.ACCEPT

    def save_preprocessor_output(self, proc_id, output_name, output_data):
        """Write a preprocessor output artifact to disk."""
        proc_id = self._validate_path_component(proc_id, 'proc_id')
        output_name = self._validate_path_component(output_name, 'output_name')
        self._warn_on_fallback_yaml_types(
            output_data,
            f"preprocessor output '{proc_id}/{output_name}'",
        )
        out_dir = os.path.join(self.synthesis_home, self.data['system_name'])
        if not os.path.exists(out_dir):
            raise FileNotFoundError(f"The output directory '{out_dir}' does not exist.")

        out_dir = os.path.join(out_dir, 'preprocessor_outputs')
        os.makedirs(out_dir, exist_ok=True)

        fpath = os.path.join(out_dir, f'{proc_id}_{output_name}.yaml')
        with open(fpath, 'w') as fout:
            yaml.dump(
                output_data,
                fout,
                Dumper=SynthesisYamlDumper,
                width=120,
                default_flow_style=False,
            )

    def save_processor_output(self, proc_id, output_name, output_data):
        """Write a processor output artifact to disk."""
        proc_id = self._validate_path_component(proc_id, 'proc_id')
        output_name = self._validate_path_component(output_name, 'output_name')
        self._warn_on_fallback_yaml_types(
            output_data,
            f"processor output '{proc_id}/{output_name}'",
        )
        out_dir = os.path.join(self.synthesis_home, self.data['system_name'])
        if not os.path.exists(out_dir):
            raise FileNotFoundError(
                f"The processor output directory '{out_dir}' does not exist."
            )

        out_dir = os.path.join(out_dir, self.data['spec_name'], 'processor_outputs')
        os.makedirs(out_dir, exist_ok=True)

        fpath = os.path.join(out_dir, f'{proc_id}_{output_name}.yaml')
        with open(fpath, 'w') as fout:
            yaml.dump(
                output_data,
                fout,
                Dumper=SynthesisYamlDumper,
                width=120,
                default_flow_style=False,
            )

    def _warn_on_fallback_yaml_types(self, output_data, artifact_name):
        """Warn when output data contains objects serialized by YAML fallback."""
        for type_name in sorted(self._find_fallback_yaml_types(output_data)):
            self.get_logger().warning(

                    f"Serializing unknown YAML type '{type_name}' in "
                    f'{artifact_name} using fallback object serialization.'

            )

    @classmethod
    def _find_fallback_yaml_types(cls, value, seen=None):
        """Return type names that require the fallback YAML representer."""
        if seen is None:
            seen = set()

        if id(value) in seen:
            return set()
        seen.add(id(value))

        safe_scalars = (type(None), bool, int, float, str, bytes)
        if isinstance(value, safe_scalars + (SynthesisErrorCode,)):
            return set()

        if isinstance(value, (list, tuple, set)):
            unknown_types = set()
            for item in value:
                unknown_types.update(cls._find_fallback_yaml_types(item, seen))
            return unknown_types

        if isinstance(value, dict):
            unknown_types = set()
            for key, item in value.items():
                unknown_types.update(cls._find_fallback_yaml_types(key, seen))
                unknown_types.update(cls._find_fallback_yaml_types(item, seen))
            return unknown_types

        return {type(value).__name__}

    def _save_execution_statistics(self):
        """Persist execution statistics without masking synthesis results."""
        spec_name = self.data.get('spec_name')
        if isinstance(spec_name, str) and spec_name.startswith('req:'):
            self.get_logger().warning(

                    'Skipping synthesis execution statistics save because '
                    f'spec_name is unresolved ({spec_name!r}).'

            )
            return

        try:
            self.save_processor_output('execute', 'statistics', self.statistics)
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask synthesis result.
            self.get_logger().error(
                f'Failed to save synthesis execution statistics: {type(exc).__name__}: {exc}'
            )

    def execute_preprocesses(self):
        """Execute configured preprocess plugins in order."""
        start_time = time.time()
        if self.preprocesses_pipeline is not None:
            print('--- Begin executing preprocesses --')
            proc_cnt = 0
            for ep in self.preprocesses_pipeline:
                if 'entry_point' not in ep:
                    raise ValidationError(
                        '[entry_point] not found in preprocess pipeline entry',
                        kind=ValidationError.MISSING_ENTRY_POINT,
                    )
                name = '<unknown>'
                preprocess_instance = None
                try:
                    processor_start = time.time()
                    config = ep['entry_point']
                    name = config['name']
                    print(f"Launching plugin '{name}' ...", flush=True)
                    if name not in self.available_preprocesses.names:
                        print(
                            f'Available preprocesses: {self.available_preprocesses.names}',
                            flush=True,
                        )
                        raise ValidationError(
                            f"'{name}' not found in entry_points(group={self.preprocess_group})",
                            kind=ValidationError.PLUGIN_NOT_FOUND,
                        )
                    p_inputs = config.get('inputs', {})
                    p_outputs = config.get('outputs', {})
                    print(f'    defined inputs={p_inputs}')
                    print(f'    defined outputs={p_outputs}')
                    type_mapping = getattr(self, 'preprocess_type_mapping', TYPE_MAPPING)
                    self._validate_declared_types(p_inputs, 'input', type_mapping)
                    self._validate_declared_types(p_outputs, 'output', type_mapping)

                    to_pass = [self.data[input_name] for input_name in p_inputs]
                    preprocess = self.available_preprocesses[name].load()
                    self._check_entry_point_is_function(name, preprocess)
                    preprocess_instance = preprocess(to_pass)
                    preprocess_instance.synthesis_home = self.synthesis_home
                    received = preprocess_instance.preprocess()
                    self._pipeline_messages.extend(preprocess_instance.messages)
                    expected_outputs = list(p_outputs.keys())
                    self._validate_plugin_outputs(name, expected_outputs, received)

                    proc_id = f'preprocess_{proc_cnt}_{name}'
                    proc_cnt += 1
                    self.statistics['preprocesses']['pipeline'][proc_id][
                        'execution_time'
                    ] = (
                        time.time() - processor_start
                    )

                    for index, output_name in enumerate(expected_outputs):
                        print(
                            (
                                f'    Setting data[{output_name}] using {index} '
                                f'({type(received[index])}) from received outputs'
                            ),
                            flush=True,
                        )
                        self.data[output_name] = received[index]
                        if self.save_outputs:
                            self.save_preprocessor_output(
                                proc_id,
                                output_name,
                                received[index],
                            )
                except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                    if preprocess_instance is not None:
                        self._pipeline_messages.extend(preprocess_instance.messages)
                    self._pipeline_messages.append(
                        f"Preprocess '{name}' failed: "
                        f'{type(exc).__name__}: {exc}'
                    )
                    if isinstance(exc, MappingValidationError):
                        self._set_mapping_failure(

                                f"Error occurred while executing preprocess '{name}'.\n"
                                f'    {type(exc).__name__}: {exc}'

                        )
                        raise
                    if isinstance(exc, UserdataValidationError):
                        self._set_userdata_failure(

                                f"Error occurred while executing preprocess '{name}'.\n"
                                f'    {type(exc).__name__}: {exc}'

                        )
                        raise
                    self._set_pipeline_failure(

                            f"Error occurred while executing preprocess '{name}'.\n"
                            f'    {type(exc).__name__}: {exc}'

                    )
                    traceback.print_exc()
                    raise

        print('--- Done executing preprocesses --')
        print(30 * '=', flush=True)
        self.statistics['preprocesses']['execution_time'] = time.time() - start_time

    def validate_preprocesses(self):
        """
        Validate preprocess pipeline structure and initialize per-step statistics.

        Checks that every pipeline entry contains an ``entry_point`` key; raises
        ValidationError (MISSING_ENTRY_POINT) on the first violation.  Also
        initializes the execution-time slot in ``statistics['preprocesses']['pipeline']``
        for each step.  Called once at server startup before preprocesses run.
        """
        if self.preprocesses_pipeline is None:
            return
        self.statistics['preprocesses']['pipeline'] = {}
        for proc_cnt, ep in enumerate(self.preprocesses_pipeline):
            if 'entry_point' not in ep:
                raise ValidationError(
                    '[entry_point] not found in preprocess pipeline entry',
                    kind=ValidationError.MISSING_ENTRY_POINT,
                )
            name = ep['entry_point']['name']
            proc_id = f'preprocess_{proc_cnt}_{name}'
            self.statistics['preprocesses']['pipeline'][proc_id] = {'execution_time': None}

    def validate(self):
        """
        Validate process pipeline I/O compatibility before per-goal execution.

        Walks the pipeline in declaration order and verifies that:
        - each plugin name is registered under the process entry-point group;
        - every declared input key is either present in the shared data dict
          (from launch parameters or preprocessor outputs) or produced by an
          earlier pipeline stage;
        - declared input and output types are mutually compatible.

        Raises ValidationError for missing plugins, unresolved inputs, or type
        mismatches when strict_type_validation is enabled (the default).  In
        non-strict mode, type mismatches are logged as warnings instead.
        """
        print('--- Begin validating processes pipeline ---', flush=True)
        start_time = time.time()
        processor_outputs = {}
        processor_plugins = []

        if self.processes_pipeline is not None:
            for ep in self.processes_pipeline:
                if 'entry_point' not in ep:
                    raise KeyError('[entry_point] not found in second most outer layer')

                config = ep['entry_point']
                name = config['name']
                if name not in self.available_processes.names:
                    raise ValidationError(
                        f"'{name}' not found in entry_points(group={self.process_group})",
                        kind=ValidationError.PLUGIN_NOT_FOUND,
                    )

                p_inputs = config.get('inputs', {})
                p_outputs = config.get('outputs', {})
                type_mapping = getattr(self, 'process_type_mapping', TYPE_MAPPING)
                type_aliases = getattr(self, 'process_type_aliases', {})
                self._validate_declared_types(p_inputs, 'input', type_mapping)
                self._validate_declared_types(p_outputs, 'output', type_mapping)
                strict_type_validation = config.get('strict_type_validation', True)

                for input_name, input_type in p_inputs.items():
                    if input_name in self.data:
                        if not validate_types(
                            self.data[input_name],
                            input_type,
                            type_mapping,
                        ):
                            self._handle_type_mismatch(
                                (
                                    f"Input types differ for '{name}'. "
                                    f"'{input_name}' expects {input_type} but received "
                                    f'{type(self.data[input_name])}'
                                ),
                                strict_type_validation,
                            )
                    elif input_name not in processor_outputs:
                        raise ValidationError(
                            f"input '{input_name}' not defined for '{name}'",
                            kind=ValidationError.INPUT_NOT_DEFINED,
                        )
                    elif not self._types_compatible(
                        input_type,
                        processor_outputs[input_name],
                        type_mapping,
                        type_aliases,
                    ):
                        self._handle_type_mismatch(
                            (
                                f"Input types differ for '{name}'. "
                                f"'{input_name}' expects {input_type} but received "
                                f'{processor_outputs[input_name]}'
                            ),
                            strict_type_validation,
                        )

                for output_name, output_type in p_outputs.items():
                    if output_name in processor_outputs:
                        if not self._types_compatible(
                            processor_outputs[output_name],
                            output_type,
                            type_mapping,
                            type_aliases,
                        ):
                            self._handle_type_mismatch(
                                (
                                    f'{name!r} will overwrite previous data for '
                                    f'output {output_name!r} '
                                    f'({processor_outputs[output_name]}) '
                                    f'with ({output_type})'
                                ),
                                strict_type_validation,
                            )
                    processor_outputs[output_name] = output_type

                processor_plugins.append(
                    Plugin(
                        name,
                        list(p_inputs.keys()),
                        list(p_outputs.keys()),
                        dict(p_outputs),
                    )
                )

            if processor_plugins and not any(
                output_type == 'List[StateInstantiation]'
                for output_type in processor_outputs.values()
            ):
                raise ValidationError(
                    "Process pipeline declares no 'List[StateInstantiation]' output; "
                    'the server cannot return a synthesized state machine.',
                    kind=ValidationError.PIPELINE_LOAD,
                )

            self.processor_outputs = processor_outputs
            self.processor_plugins = processor_plugins
            self.statistics['processes']['pipeline'] = {
                f'process_{i}_{plugin.name}': {'execution_time': None}
                for i, plugin in enumerate(processor_plugins)
            }

            print('--- Validated Pipeline ---', flush=True)
            for plugin in self.processor_plugins:
                print(plugin)

        print('--- Done validation process pipeline ---', flush=True)
        self.statistics['processes']['validation_time'] = time.time() - start_time

    def _validate_declared_types(self, io_map, io_kind, type_mapping=None):
        """Validate configured input/output type strings."""
        if type_mapping is None:
            type_mapping = TYPE_MAPPING

        for key, value in io_map.items():
            if value not in type_mapping:
                raise ValidationError(
                    f"Unknown {io_kind} type '{value}' for '{key}'",
                    kind=ValidationError.TYPE_UNKNOWN,
                )

    @staticmethod
    def _canonical_type_name(type_name, type_aliases):
        """Resolve a type alias to the core or previously declared type name it targets."""
        seen = set()
        while type_name in type_aliases:
            if type_name in seen:
                break
            seen.add(type_name)
            type_name = type_aliases[type_name]
        return type_name

    @classmethod
    def _types_compatible(cls, first_type, second_type, type_mapping, type_aliases):
        """Return whether two declared pipeline types are compatible."""
        if first_type == second_type:
            return True

        first_base = cls._canonical_type_name(first_type, type_aliases)
        second_base = cls._canonical_type_name(second_type, type_aliases)
        if first_base == second_base:
            return True

        return False

    def _load_type_aliases(self, data, pipeline_kind, filepath, base_mapping=None):
        """Load YAML-local pipeline type aliases from the optional ``/types`` block."""
        if base_mapping is None:
            base_mapping = TYPE_MAPPING

        type_mapping = dict(base_mapping)
        type_aliases = {}
        type_aliases_config = data.get('/types', {})
        if type_aliases_config is None:
            return type_mapping, type_aliases
        if not isinstance(type_aliases_config, dict):
            self._fail_invalid_pipeline_load(
                pipeline_kind,
                filepath,
                f'/types must be a mapping, got {type(type_aliases_config).__name__}',
            )

        for alias_name, base_type in type_aliases_config.items():
            if not isinstance(alias_name, str) or alias_name == '':
                self._fail_invalid_pipeline_load(
                    pipeline_kind,
                    filepath,
                    f'/types alias names must be non-empty strings, got {alias_name!r}',
                )
            if alias_name in TYPE_MAPPING:
                self._fail_invalid_pipeline_load(
                    pipeline_kind,
                    filepath,
                    f"/types alias '{alias_name}' conflicts with a core type",
                )
            if not isinstance(base_type, str) or base_type == '':
                self._fail_invalid_pipeline_load(
                    pipeline_kind,
                    filepath,
                    (
                        f"/types alias '{alias_name}' must reference a non-empty "
                        f'type name, got {base_type!r}'
                    ),
                )
            if base_type not in type_mapping:
                self._fail_invalid_pipeline_load(
                    pipeline_kind,
                    filepath,
                    f"/types alias '{alias_name}' references unknown type '{base_type}'",
                )
            type_mapping[alias_name] = type_mapping[base_type]
            type_aliases[alias_name] = base_type

        return type_mapping, type_aliases

    def _handle_type_mismatch(self, message, strict_type_validation):
        """Raise or warn for type mismatches based on validation policy."""
        if strict_type_validation:
            raise ValidationError(message, kind=ValidationError.TYPE_MISMATCH)
        self.get_logger().warning(f'\033[38;5;11m{message}\033[0m')

    def _publish_feedback(self, goal, status, progress):
        """Publish synthesis action feedback when a goal handle is available."""
        feedback = FlexBESynthesis.Feedback()
        feedback.status = status
        feedback.progress = max(0.0, min(1.0, float(progress)))
        goal.publish_feedback(feedback)

    def _check_cancel_requested(self, goal, stage_name):
        """Cancel the action if the client requested cancellation."""
        if not goal.is_cancel_requested:
            return False

        status = 'canceling'
        if stage_name:
            status = f'canceling: {stage_name}'
        self._publish_feedback(goal, status, 1.0)
        if self._result is not None:
            self._result.error_code = SynthesisErrorCode(value=SynthesisErrorCode.PREEMPTED)
            self._result.states = []
        goal.canceled()
        self.statistics['processes']['success'] = False
        return True

    def _set_pipeline_failure(self, message):
        """Record a synthesis-management failure and log the root cause."""
        self.data['error_code'] = SynthesisErrorCode(
            value=SynthesisErrorCode.PIPELINE_INVALID
        )
        if self._result is not None:
            self._result.error_code = SynthesisErrorCode(
                value=SynthesisErrorCode.PIPELINE_INVALID
            )
        self.get_logger().error(message)

    def _set_mapping_failure(self, message):
        """Record a mapping-configuration failure and log the root cause."""
        self.data['error_code'] = SynthesisErrorCode(
            value=SynthesisErrorCode.MAPPING_INVALID
        )
        if self._result is not None:
            self._result.error_code = SynthesisErrorCode(
                value=SynthesisErrorCode.MAPPING_INVALID
            )
        self.get_logger().error(message)

    def _set_userdata_failure(self, message):
        """Record a userdata-configuration failure and log the root cause."""
        self.data['error_code'] = SynthesisErrorCode(
            value=SynthesisErrorCode.USERDATA_INVALID
        )
        if self._result is not None:
            self._result.error_code = SynthesisErrorCode(
                value=SynthesisErrorCode.USERDATA_INVALID
            )
        self.get_logger().error(message)

    def _set_invalid_request_failure(self, message):
        """Record an invalid action request and log the root cause."""
        self.data['error_code'] = SynthesisErrorCode(
            value=SynthesisErrorCode.INVALID_REQUEST
        )
        if self._result is not None:
            self._result.error_code = SynthesisErrorCode(
                value=SynthesisErrorCode.INVALID_REQUEST
            )
        self.get_logger().error(message)

    @staticmethod
    def _check_entry_point_is_function(name, loaded):
        """
        Raise if a loaded entry point is a class rather than a main(inputs) function.

        The plugin convention requires each entry point to be a module-level
        ``main(inputs)`` function that accepts a list of pipeline inputs and
        returns a ``BaseProcess`` or ``BasePreProcess`` instance.  Registering
        the class itself is a common mistake and produces a cryptic pydantic
        instantiation error; this guard catches it early with a clear message.
        """
        if inspect.isclass(loaded) and issubclass(loaded, (BaseProcess, BasePreProcess)):
            raise ValidationError(
                f"Plugin '{name}' entry point resolved to a class ({loaded.__name__!r}), "
                'not a function. Register a main(inputs) factory function, not the class itself.',
                kind=ValidationError.PLUGIN_INTERFACE,
            )

    def _validate_plugin_outputs(self, plugin_name, expected_outputs, received_outputs):
        """Validate that a plugin returned exactly the outputs declared by YAML."""
        if received_outputs is None:
            if not expected_outputs:
                return
            raise ValueError(
                'Plugin/YAML output contract mismatch: '
                f"plugin '{plugin_name}' returned no outputs, but the pipeline "
                f'declares {len(expected_outputs)} output(s): {expected_outputs}'
            )
        try:
            received_count = len(received_outputs)
        except TypeError as exc:
            raise ValueError(
                'Plugin/YAML output contract mismatch: '
                f"plugin '{plugin_name}' returned non-sequence outputs "
                f'{type(received_outputs).__name__}, but the pipeline declares '
                f'{len(expected_outputs)} output(s): {expected_outputs}'
            ) from exc
        if received_count != len(expected_outputs):
            raise ValueError(
                'Plugin/YAML output contract mismatch: '
                f"plugin '{plugin_name}' returned {received_count} output(s), "
                f'but the pipeline declares {len(expected_outputs)} output(s): '
                f'{expected_outputs}'
            )

    def execute_processes(self, goal):
        """Execute validated process plugins and collect outputs."""
        start_time = time.time()
        flexbe_sm_outputs = []
        proc_cnt = 0
        total_processes = len(self.processor_plugins)
        for plugin in self.processor_plugins:
            try:
                process_instance = None
                if self._check_cancel_requested(goal, plugin.name):
                    return []

                proc_start = time.time()
                to_pass = [self.data[input_name] for input_name in plugin.inputs]
                self._publish_feedback(
                    goal,
                    plugin.name,
                    proc_cnt / total_processes if total_processes else 0.0,
                )
                print(
                    f"Executing '{plugin.name}' with {len(to_pass)} arguments ...",
                    flush=True,
                )
                process = self.available_processes[plugin.name].load()
                self._check_entry_point_is_function(plugin.name, process)
                process_instance = process(to_pass)
                process_instance.synthesis_home = self.synthesis_home
                self._active_process_instance = process_instance
                try:
                    received_outputs = process_instance.process()
                finally:
                    if self._active_process_instance is process_instance:
                        self._active_process_instance = None
                self._pipeline_messages.extend(process_instance.messages)
                if self._check_cancel_requested(goal, plugin.name):
                    process_instance.cancel()
                    return []
                self._validate_plugin_outputs(
                    plugin.name,
                    plugin.outputs,
                    received_outputs,
                )

                proc_id = f'process_{proc_cnt}_{plugin.name}'
                proc_cnt += 1
                self.statistics['processes']['pipeline'][proc_id]['execution_time'] = (
                    time.time() - proc_start
                )

                for index, output_name in enumerate(plugin.outputs):
                    self.data[output_name] = received_outputs[index]
                    if (
                        plugin.output_types.get(output_name)
                        == 'List[StateInstantiation]'
                    ):
                        # Capture full received_outputs so caller gets results[0] = state list.
                        print(
                            (
                                f"Received FlexBE SM from '{plugin.name}' "
                                f"output '{output_name}'"
                            ),
                            flush=True,
                        )
                        flexbe_sm_outputs = received_outputs
                    if self.save_outputs:
                        self.save_processor_output(proc_id, output_name, received_outputs[index])

                    if output_name == 'error_code':
                        if self.data['error_code'].value != SynthesisErrorCode.SUCCESS:
                            print(
                                    '\033[31mFlexBE Synthesis processing error='
                                    f"{get_error_code_text(self.data['error_code'])}\033[0m"
                            )
                            return []

            except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
                if process_instance is not None:
                    self._pipeline_messages.extend(process_instance.messages)
                    process_instance.cancel()
                self._pipeline_messages.append(
                    f"Process '{plugin.name}' failed: "
                    f'{type(exc).__name__}: {exc}'
                )
                if isinstance(exc, MappingValidationError):
                    self._set_mapping_failure(

                            f"Error occurred while executing process '{plugin.name}'.\n"
                            f'    {type(exc).__name__}: {exc}'

                    )
                elif isinstance(exc, UserdataValidationError):
                    self._set_userdata_failure(

                            f"Error occurred while executing process '{plugin.name}'.\n"
                            f'    {type(exc).__name__}: {exc}'

                    )
                else:
                    self._set_pipeline_failure(

                            f"Error occurred while executing process '{plugin.name}'.\n"
                            f'    {type(exc).__name__}: {exc}'

                    )
                    traceback.print_exc()
                return []

        self.statistics['processes']['execution_time'] = time.time() - start_time
        return flexbe_sm_outputs

    def load_processes(self):
        """Load process data bindings and process pipeline YAML."""
        start_time = time.time()
        if self.processes_data_filepath:
            try:
                with open(self.processes_data_filepath) as stream:
                    data = yaml.safe_load(stream)
                if data and '/data' in data:
                    for key, value in data['/data'].items():
                        resolved = self._resolve_data_value(key, value)
                        if isinstance(value, str) and value.startswith('ros:'):
                            self.get_logger().warning(
                                f"Using '{resolved}' for '{key}' from ROS parameter '{value[4:]}'"
                            )
                        elif key in self.data:
                            self.get_logger().warning(
                                f"Overwriting existing data for '{key}' from "
                                f"'{self.processes_data_filepath}'"
                            )
                        self.data[key] = resolved
            except FileNotFoundError:
                self.get_logger().warning(
                    f'Processes data file not found at {self.processes_data_filepath}'
                )

        with open(self.processes_filepath) as stream:
            data = yaml.safe_load(stream)
        if data is None:
            self._fail_invalid_pipeline_load(
                'processes',
                self.processes_filepath,
                'file is empty or only contains null',
            )
        if not isinstance(data, dict):
            self._fail_invalid_pipeline_load(
                'processes',
                self.processes_filepath,
                f'expected a mapping with /pipeline, got {type(data).__name__}',
            )
        if '/pipeline' not in data:
            self._fail_invalid_pipeline_load(
                'processes',
                self.processes_filepath,
                'missing /pipeline key',
            )

        pipeline = data['/pipeline']
        if pipeline is None:
            self._fail_invalid_pipeline_load(
                'processes',
                self.processes_filepath,
                '/pipeline is null',
            )
        if not isinstance(pipeline, list):
            self._fail_invalid_pipeline_load(
                'processes',
                self.processes_filepath,
                f'/pipeline must be a list, got {type(pipeline).__name__}',
            )

        self.process_type_mapping, self.process_type_aliases = self._load_type_aliases(
            data,
            'processes',
            self.processes_filepath,
        )
        self.processes_pipeline = pipeline

        self.statistics['processes']['load_time'] = time.time() - start_time

    def load_preprocesses(self):
        """Load preprocess data bindings and preprocess pipeline YAML."""
        start_time = time.time()
        if self.preprocess_data_filepath:
            try:
                with open(self.preprocess_data_filepath) as stream:
                    data = yaml.safe_load(stream)
                if data and '/data' in data:
                    for key, value in data['/data'].items():
                        self.data[key] = self._resolve_data_value(key, value)
            except FileNotFoundError:
                self.get_logger().warning(
                    f"Preprocess data file not found at '{self.preprocess_data_filepath}'"
                )

        with open(self.preprocess_filepath) as stream:
            data = yaml.safe_load(stream)
        if data is None:
            self._fail_invalid_pipeline_load(
                'preprocesses',
                self.preprocess_filepath,
                'file is empty or only contains null',
            )
        if not isinstance(data, dict):
            self._fail_invalid_pipeline_load(
                'preprocesses',
                self.preprocess_filepath,
                f'expected a mapping with /pipeline, got {type(data).__name__}',
            )
        if '/pipeline' not in data:
            self._fail_invalid_pipeline_load(
                'preprocesses',
                self.preprocess_filepath,
                'missing /pipeline key',
            )

        pipeline = data['/pipeline']
        if pipeline is None:
            self._fail_invalid_pipeline_load(
                'preprocesses',
                self.preprocess_filepath,
                '/pipeline is null',
            )
        if not isinstance(pipeline, list):
            self._fail_invalid_pipeline_load(
                'preprocesses',
                self.preprocess_filepath,
                f'/pipeline must be a list, got {type(pipeline).__name__}',
            )

        (
            self.preprocess_type_mapping,
            self.preprocess_type_aliases,
        ) = self._load_type_aliases(
            data,
            'preprocesses',
            self.preprocess_filepath,
        )
        self.preprocesses_pipeline = pipeline

        self.statistics['preprocesses']['load_time'] = time.time() - start_time


def main(args=None):
    """Start the FlexBE synthesis action server node."""
    rclpy.init(args=args)
    try:
        server = FlexBESynthesisActionServer('flexbe_synthesis_server')
        if server.processes_pipeline is None or len(server.processes_pipeline) == 0:
            server.get_logger().info('\nNo synthesis process to perform ... shutdown!')
            server.destroy()
            rclpy.shutdown()
            return
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, ValidationError) as exc:
        if not isinstance(exc, (MappingValidationError, UserdataValidationError, ValidationError)):
            print('\n\n' + 30 * '=' + '\n', flush=True)
            traceback.print_exc()
        print(f'ERROR: Failed to set up node properly:\n {exc}')
        if rclpy.ok():
            rclpy.shutdown()
        if isinstance(exc, ValidationError):
            return 0
        return -1

    executor = MultiThreadedExecutor()
    try:
        rclpy.spin(server, executor)
        server.destroy()
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError, OSError) as exc:
        print(f'FlexBE Synthesis manager ERROR: {exc}')
    finally:
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
