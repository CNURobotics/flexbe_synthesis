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

"""Tests for synthesis manager startup error handling."""

from flexbe_synthesis_core import synthesis_manager


def test_main_stops_when_server_setup_raises_runtime_error(monkeypatch):
    """Startup should report setup failures and return without spinning."""
    calls = {'init': 0, 'shutdown': 0, 'spin': 0}

    def _init(args=None):
        del args
        calls['init'] += 1

    def _shutdown():
        calls['shutdown'] += 1

    def _spin(*args, **kwargs):
        del args, kwargs
        calls['spin'] += 1

    class _FailingServer:

        def __init__(self, name):
            del name
            raise RuntimeError('path setup failed')

    monkeypatch.setattr(synthesis_manager.rclpy, 'init', _init)
    monkeypatch.setattr(synthesis_manager.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(synthesis_manager.rclpy, 'shutdown', _shutdown)
    monkeypatch.setattr(synthesis_manager.rclpy, 'spin', _spin)
    monkeypatch.setattr(
        synthesis_manager,
        'FlexBESynthesisActionServer',
        _FailingServer,
    )

    assert synthesis_manager.main() == -1
    assert calls == {'init': 1, 'shutdown': 1, 'spin': 0}


def test_main_shuts_down_cleanly_when_pipeline_validation_fails(monkeypatch):
    """Invalid pipeline YAML should not make ros2 launch report a crashed process."""
    calls = {'init': 0, 'shutdown': 0, 'spin': 0}

    def _init(args=None):
        del args
        calls['init'] += 1

    def _shutdown():
        calls['shutdown'] += 1

    def _spin(*args, **kwargs):
        del args, kwargs
        calls['spin'] += 1

    class _InvalidPipelineServer:

        def __init__(self, name):
            del name
            raise synthesis_manager.ValidationError('Invalid processes pipeline file')

    monkeypatch.setattr(synthesis_manager.rclpy, 'init', _init)
    monkeypatch.setattr(synthesis_manager.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(synthesis_manager.rclpy, 'shutdown', _shutdown)
    monkeypatch.setattr(synthesis_manager.rclpy, 'spin', _spin)
    monkeypatch.setattr(
        synthesis_manager,
        'FlexBESynthesisActionServer',
        _InvalidPipelineServer,
    )

    assert synthesis_manager.main() == 0
    assert calls == {'init': 1, 'shutdown': 1, 'spin': 0}
