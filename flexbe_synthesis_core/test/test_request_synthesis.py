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

"""Tests for the generic synthesis request client."""

from flexbe_synthesis_core import request_synthesis
from flexbe_synthesis_core.request_synthesis import FlexBESynthesisActionClient
from flexbe_synthesis_msgs.msg import SynthesisErrorCode


class _Logger:
    """Minimal logger used by callback-only tests."""

    def __init__(self):
        self.infos = []

    def info(self, message):
        self.infos.append(message)


class _Future:
    """Small future double that returns a preconfigured value."""

    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


class _Parameter:
    """Minimal ROS parameter double for request-client construction tests."""

    def __init__(self, value):
        self._value = value

    def get_parameter_value(self):
        if isinstance(self._value, list):
            return type(
                'ParameterValue',
                (),
                {'string_array_value': self._value, 'string_value': '', 'double_value': 0.0},
            )()
        if isinstance(self._value, (float, int)):
            return type(
                'ParameterValue',
                (),
                {
                    'string_array_value': [],
                    'string_value': '',
                    'double_value': float(self._value),
                },
            )()
        return type(
            'ParameterValue',
            (),
            {'string_array_value': [], 'string_value': str(self._value), 'double_value': 0.0},
        )()


class _ResultResponse:
    """Action result response double."""

    def __init__(self, error_code_value):
        self.result = type(
            'Result',
            (),
            {
                'error_code': SynthesisErrorCode(value=error_code_value),
                'states': [],
            },
        )()


def _callback_client():
    """Build a request client instance without initializing a ROS node."""
    client = object.__new__(FlexBESynthesisActionClient)
    client.request_complete = False
    logger = _Logger()
    client.get_logger = lambda: logger
    client._logger = logger
    return client


def test_request_client_maps_synthesis_timeout_parameter(monkeypatch):
    """The generic CLI client should expose the request-level Slugs timeout."""

    class _ActionClient:

        def __init__(self, node, action_type, action_name):
            self.node = node
            self.action_type = action_type
            self.action_name = action_name

    def node_init(self, name):
        self._node_name = name
        self._declared_parameters = {}

    def declare_parameter(self, name, value):
        self._declared_parameters[name] = value

    def get_parameter(self, name):
        return _Parameter(self._declared_parameters[name])

    monkeypatch.setattr(request_synthesis.Node, '__init__', node_init)
    monkeypatch.setattr(request_synthesis, 'ActionClient', _ActionClient)
    monkeypatch.setattr(FlexBESynthesisActionClient, 'declare_parameter', declare_parameter)
    monkeypatch.setattr(FlexBESynthesisActionClient, 'get_parameter', get_parameter)

    client = FlexBESynthesisActionClient(
        defaults={
            'initial_conditions': ['ready'],
            'goals': ['done'],
            'outcomes': ['finished'],
            'system_name': 'demo',
            'spec_name': 'DemoSM',
            'specification_file_name': 'demo.yaml',
            'synthesis_timeout_s': 12.5,
        }
    )

    assert client.goal_msg.request.synthesis_timeout_s == 12.5


def test_goal_response_callback_marks_rejected_goal_complete_without_shutdown(monkeypatch):
    """Goal rejection should let the main spin loop shut down outside the callback."""
    shutdown_calls = []
    monkeypatch.setattr(request_synthesis.rclpy, 'shutdown', lambda: shutdown_calls.append(True))
    goal_handle = type('GoalHandle', (), {'accepted': False})()
    client = _callback_client()

    client.goal_response_callback(_Future(goal_handle))

    assert client.request_complete
    assert shutdown_calls == []
    assert 'Goal rejected' in client._logger.infos


def test_result_callback_marks_request_complete_without_shutdown(monkeypatch):
    """Receiving a result should stop the spin loop without calling shutdown in callback."""
    shutdown_calls = []
    monkeypatch.setattr(request_synthesis.rclpy, 'shutdown', lambda: shutdown_calls.append(True))
    client = _callback_client()

    client.get_result_callback(
        _Future(_ResultResponse(SynthesisErrorCode.SYNTHESIS_FAILED))
    )

    assert client.request_complete
    assert shutdown_calls == []
    assert 'Failed to synthesize state machine' in client._logger.infos
