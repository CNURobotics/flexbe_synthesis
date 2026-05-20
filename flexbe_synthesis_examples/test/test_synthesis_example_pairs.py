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

"""End-to-end checks for checked-in synthesis server/request example pairs."""

from dataclasses import dataclass
import multiprocessing
import os
from pathlib import Path
import queue as queue_module
import shutil
import traceback

try:
    from ament_index_python.packages import (
        get_package_share_directory,
        PackageNotFoundError,
    )
except ImportError:  # pragma: no cover - exercised only outside ROS test envs.
    get_package_share_directory = None
    PackageNotFoundError = None

from flexbe_synthesis_core.synthesis_manager import FlexBESynthesisActionServer
from flexbe_synthesis_examples.request_coffee import _DEFAULTS as COFFEE_REQUEST
from flexbe_synthesis_examples.request_hello_world import (
    _DEFAULTS as HELLO_WORLD_REQUEST,
)
from flexbe_synthesis_examples.request_vending import _DEFAULTS as VENDING_REQUEST
from flexbe_synthesis_msgs.action import FlexBESynthesis
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
import pytest
import rclpy

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ExamplePair:
    """A synthesis server example plus its matching request wrapper defaults."""

    launch_name: str
    server_params: dict
    request_defaults: dict
    expected_state_count: int
    requires_slugs: bool = True


class _GoalHandle:
    """Minimal action goal-handle used to call the server callback directly."""

    def __init__(self, request):
        self.request = request
        self.succeeded = False
        self.aborted = False
        self.canceled_called = False
        self.feedback = []

    @property
    def is_cancel_requested(self):
        return False

    def publish_feedback(self, feedback):
        self.feedback.append(feedback)

    def succeed(self):
        self.succeeded = True

    def abort(self):
        self.aborted = True

    def canceled(self):
        self.canceled_called = True


def _example_path(*parts):
    return str(PACKAGE_ROOT.joinpath('example', *parts))


def _generic_mapping_path(file_name):
    if get_package_share_directory is not None:
        try:
            return str(
                Path(get_package_share_directory('flexbe_synthesis_generic'))
                / 'mappings'
                / file_name
            )
        except PackageNotFoundError:
            pass

    source_root = PACKAGE_ROOT.parent / 'flexbe_synthesis_generic'
    return str(source_root / 'mappings' / file_name)


def _request_goal(defaults):
    goal = FlexBESynthesis.Goal()
    goal.request.initial_conditions = defaults.get('initial_conditions', [])
    goal.request.goals = defaults['goals']
    goal.request.sm_outcomes = defaults['outcomes']
    goal.request.system_name = defaults['system_name']
    goal.request.spec_name = defaults['spec_name']
    goal.request.synthesis_timeout_s = defaults.get('synthesis_timeout_s', 0.0)
    return goal


def _hello_world_server_params():
    return {
        'system_name': 'hello_world',
        'global_mappings_path': _generic_mapping_path('global_mappings.yaml'),
        'capabilities_path': _example_path(
            'hello_world',
            'capabilities',
            'hello_world_capabilities.yaml',
        ),
        'automaton_path': _example_path('hello_world', 'sm', 'hello_world_sm.yaml'),
        'processes_filepath': _example_path(
            'hello_world',
            'pipelines',
            'processes_def.yaml',
        ),
        'processes_data_filepath': _example_path(
            'hello_world',
            'pipelines',
            'processes_data.yaml',
        ),
        'preprocesses_filepath': _example_path(
            'common',
            'pipelines',
            'preprocesses_def.yaml',
        ),
        'preprocesses_data_filepath': _example_path(
            'common',
            'pipelines',
            'preprocesses_data.yaml',
        ),
    }


def _slugs_server_params(
    demo,
    capabilities_file,
    spec_file,
    processes_file,
    global_mappings_file,
):
    return {
        'global_mappings_path': _generic_mapping_path(global_mappings_file),
        'capabilities_path': _example_path(demo, 'capabilities', capabilities_file),
        'spec_path': _example_path(demo, 'specs', spec_file),
        'processes_filepath': _example_path(
            'common',
            'pipelines',
            processes_file,
        ),
        'processes_data_filepath': _example_path(
            demo,
            'pipelines',
            'processes_data.yaml',
        ),
        'preprocesses_filepath': _example_path(
            'common',
            'pipelines',
            'slugs_preprocesses_def.yaml',
        ),
        'preprocesses_data_filepath': _example_path(
            demo,
            'pipelines',
            'preprocesses_data.yaml',
        ),
    }


EXAMPLE_PAIRS = (
    ExamplePair(
        'hello_world_example.launch.py',
        _hello_world_server_params(),
        HELLO_WORLD_REQUEST,
        expected_state_count=4,  # generated FlexBE SM: 4 states
        requires_slugs=False,
    ),
    ExamplePair(
        'coffee_capabilities_example.launch.py',
        _slugs_server_params(
            'coffee_maker',
            'coffee_capabilities.yaml',
            'coffee_demo_capabilities_spec.yaml',
            'capability_processes_def.yaml',
            'infinite_mappings.yaml',
        ),
        COFFEE_REQUEST,
        expected_state_count=4,  # post-reduction: 4 states
    ),
    ExamplePair(
        'coffee_capabilities_extended_example.launch.py',
        _slugs_server_params(
            'coffee_maker',
            'coffee_capabilities_extended.yaml',
            'coffee_demo_capabilities_spec.yaml',
            'capability_processes_def.yaml',
            'infinite_mappings.yaml',
        ),
        COFFEE_REQUEST,
        expected_state_count=4,  # post-reduction: 4 states
    ),
    ExamplePair(
        'coffee_capabilities_parsed_example.launch.py',
        _slugs_server_params(
            'coffee_maker',
            'coffee_capabilities.yaml',
            'coffee_demo_capabilities_spec.yaml',
            'capability_processes_def_parsed.yaml',
            'infinite_mappings.yaml',
        ),
        COFFEE_REQUEST,
        expected_state_count=4,  # post-reduction: 4 states
    ),
    ExamplePair(
        'coffee_capabilities_extended_parsed_example.launch.py',
        _slugs_server_params(
            'coffee_maker',
            'coffee_capabilities_extended.yaml',
            'coffee_demo_capabilities_spec.yaml',
            'capability_processes_def_parsed.yaml',
            'infinite_mappings.yaml',
        ),
        COFFEE_REQUEST,
        expected_state_count=4,  # post-reduction: 4 states
    ),
    ExamplePair(
        'coffee_full_spec_example.launch.py',
        _slugs_server_params(
            'coffee_maker',
            'coffee_capabilities.yaml',
            'coffee_full_spec.yaml',
            'full_spec_processes_def.yaml',
            'infinite_mappings.yaml',
        ),
        COFFEE_REQUEST,
        expected_state_count=4,  # post-reduction: 4 states
    ),
    ExamplePair(
        'vending_capabilities_example.launch.py',
        _slugs_server_params(
            'vending_demo',
            'vending_capabilities.yaml',
            'vending_demo_capabilities_spec.yaml',
            'capability_processes_def.yaml',
            'global_mappings.yaml',
        ),
        VENDING_REQUEST,
        expected_state_count=6,  # post-reduction: 6 states
    ),
    ExamplePair(
        'vending_capabilities_extended_example.launch.py',
        _slugs_server_params(
            'vending_demo',
            'vending_capabilities_extended.yaml',
            'vending_demo_capabilities_spec.yaml',
            'capability_processes_def.yaml',
            'global_mappings.yaml',
        ),
        VENDING_REQUEST,
        expected_state_count=6,  # post-reduction: 6 states
    ),
    ExamplePair(
        'vending_capabilities_parsed_example.launch.py',
        _slugs_server_params(
            'vending_demo',
            'vending_capabilities.yaml',
            'vending_demo_capabilities_spec.yaml',
            'capability_processes_def_parsed.yaml',
            'global_mappings.yaml',
        ),
        VENDING_REQUEST,
        expected_state_count=6,  # post-reduction: 6 states
    ),
    ExamplePair(
        'vending_capabilities_extended_parsed_example.launch.py',
        _slugs_server_params(
            'vending_demo',
            'vending_capabilities_extended.yaml',
            'vending_demo_capabilities_spec.yaml',
            'capability_processes_def_parsed.yaml',
            'global_mappings.yaml',
        ),
        VENDING_REQUEST,
        expected_state_count=6,  # post-reduction: 6 states
    ),
    ExamplePair(
        'vending_full_spec_example.launch.py',
        _slugs_server_params(
            'vending_demo',
            'vending_capabilities.yaml',
            'vending_demo_full_spec.yaml',
            'full_spec_processes_def.yaml',
            'global_mappings.yaml',
        ),
        VENDING_REQUEST,
        expected_state_count=6,  # post-reduction: 6 states
    ),
)


def _ros_args(server_params):
    args = ['--ros-args']
    for key, value in server_params.items():
        if value == '':
            continue
        args.extend(['-p', f'{key}:={value}'])
    return args


def _test_synthesis_home(system_name, launch_name):
    base_home = os.environ.get('FLEXBE_SYNTHESIS_HOME')
    if not base_home:
        base_home = str(Path.home() / '.flexbe_synthesis')
    launch_slug = launch_name.replace('.', '_')
    return str(Path(base_home) / f'test_{system_name}_{launch_slug}')


def _execute_example_pair(example_pair, ros_log_dir, queue):
    """
    Run an example pair in a fresh process and return compact result data.

    Synthesis outputs go under
    FLEXBE_SYNTHESIS_HOME/test_<system_name>_<launch_name> so parallel test
    workers cannot share the workspace cache. ROS logs go to ros_log_dir (a
    pytest temp directory).
    """
    os.environ['ROS_LOG_DIR'] = str(ros_log_dir)
    os.environ['FLEXBE_SYNTHESIS_HOME'] = _test_synthesis_home(
        example_pair.request_defaults['system_name'],
        example_pair.launch_name,
    )
    server = None
    try:
        rclpy.init(args=_ros_args(example_pair.server_params))
        server = FlexBESynthesisActionServer(
            f"test_{example_pair.launch_name.replace('.', '_')}"
        )
        goal_handle = _GoalHandle(_request_goal(example_pair.request_defaults))
        result = server.execute_callback(goal_handle)
        queue.put(
            {
                'error_code': result.error_code.value,
                'messages': list(result.messages),
                'state_count': len(result.states),
                'succeeded': goal_handle.succeeded,
                'aborted': goal_handle.aborted,
                'canceled_called': goal_handle.canceled_called,
            }
        )
    except BaseException:  # noqa: BLE001 - propagate child-process failures.
        queue.put({'exception': traceback.format_exc()})
    finally:
        if server is not None:
            server.destroy()
        if rclpy.ok():
            rclpy.shutdown()


def _run_example_pair(example_pair, tmp_path):
    """
    Execute one synthesis pair in an isolated child process.

    Synthesis outputs are grouped below the normal synthesis home by system and
    launch name so overnight runs remain inspectable.
    """
    if example_pair.requires_slugs and shutil.which('slugs') is None:
        pytest.skip('Slugs binary is not installed')

    ctx = multiprocessing.get_context('spawn')
    queue = ctx.Queue()
    process = ctx.Process(
        target=_execute_example_pair,
        args=(example_pair, tmp_path / 'ros_logs', queue),
    )
    process.start()
    process.join(timeout=30)

    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail(f'{example_pair.launch_name} did not finish within 30 seconds')

    assert process.exitcode == 0, (
        f'{example_pair.launch_name} child exited with code {process.exitcode}'
    )
    try:
        return queue.get(timeout=5)
    except queue_module.Empty:
        pytest.fail(f'{example_pair.launch_name}: child exited but wrote nothing to queue')


@pytest.mark.parametrize(
    'example_pair',
    EXAMPLE_PAIRS,
    ids=lambda pair: pair.launch_name,
)
def test_synthesis_server_request_pair_succeeds(example_pair, tmp_path):
    """Verify each checked-in example launch/request pair synthesizes successfully."""
    result = _run_example_pair(example_pair, tmp_path)

    assert 'exception' not in result, result.get('exception')
    assert result['error_code'] == SynthesisErrorCode.SUCCESS
    assert result['messages'] == [], result['messages']
    assert result['state_count'] == example_pair.expected_state_count
    assert result['succeeded']
    assert not result['aborted']
    assert not result['canceled_called']
