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

"""Tests for generic capability loading validation."""

import textwrap

from flexbe_synthesis_core.validation_error import UserdataValidationError
from flexbe_synthesis_generic.preprocesses.capability_loader import CapabilityLoader
import pytest


def test_capability_parameter_validation_raises_value_error():
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path='unused.yaml',
        workspace_data={},
        state_mappings={},
    )
    capability = {
        'parameters': {
            'unexpected': 'value',
        },
    }
    state_info = {
        'name': 'DemoState',
        'parameters': {
            'expected': {},
        },
    }

    with pytest.raises(ValueError, match="'demo_step' parameter 'unexpected'"):
        loader.validate_capability_state('demo_step', capability, state_info)


def test_capability_userdata_validation_accepts_known_keys():
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path='unused.yaml',
        workspace_data={},
        state_mappings={},
    )
    capability = {
        'userdata_in': {
            'request': 'request',
        },
        'userdata_out': {
            'result': 'result',
        },
    }
    state_info = {
        'name': 'DemoState',
        'userdata_in': {
            'request': {},
        },
        'userdata_out': {
            'result': {},
        },
    }

    loader.validate_capability_userdata('demo_step', capability, state_info)


def test_capability_userdata_validation_rejects_unknown_keys():
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path='unused.yaml',
        workspace_data={},
        state_mappings={},
    )
    capability = {
        'userdata_in': {
            'typo': 'typo',
        },
    }
    state_info = {
        'name': 'DemoState',
        'userdata_in': {
            'request': {},
        },
        'userdata_out': {},
    }

    with pytest.raises(UserdataValidationError, match="'demo_step' userdata_in 'typo'"):
        loader.validate_capability_userdata('demo_step', capability, state_info)


def test_capability_userdata_validation_rejects_non_mapping_values():
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path='unused.yaml',
        workspace_data={},
        state_mappings={},
    )
    capability = {
        'userdata_out': ['result'],
    }
    state_info = {
        'name': 'DemoState',
        'userdata_in': {},
        'userdata_out': {
            'result': {},
        },
    }

    with pytest.raises(UserdataValidationError, match='userdata_out must be a mapping'):
        loader.validate_capability_userdata('demo_step', capability, state_info)


def test_invalid_state_mapping_key_reports_schema_error(tmp_path):
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text(
        textwrap.dedent(
            """\
            name: demo
            capabilities: {}
            """
        )
    )
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data={
            'states': {},
            'behaviors': {},
        },
        state_mappings={
            'state_outcome_mapping': {},
        },
    )

    with pytest.raises(ValueError, match='Invalid state mapping key'):
        loader.preprocess()


def test_missing_capabilities_key_reports_schema_error(tmp_path):
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text('name: demo\n')
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data={
            'states': {},
            'behaviors': {},
        },
        state_mappings={},
    )

    with pytest.raises(ValueError, match="missing required 'capabilities' mapping"):
        loader.preprocess()


def test_non_mapping_capabilities_file_reports_schema_error(tmp_path):
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text('- invalid\n')
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data={
            'states': {},
            'behaviors': {},
        },
        state_mappings={},
    )

    with pytest.raises(TypeError, match='top-level mapping'):
        loader.preprocess()


def test_non_mapping_capabilities_reports_schema_error(tmp_path):
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text(
        textwrap.dedent(
            """\
            name: demo
            capabilities:
                - invalid
            """
        )
    )
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data={
            'states': {},
            'behaviors': {},
        },
        state_mappings={},
    )

    with pytest.raises(TypeError, match="'capabilities' must be a mapping"):
        loader.preprocess()


def _behavior_workspace_data(userdata_in=None, userdata_out=None):
    """Return minimal workspace_data containing a behavior interface."""
    return {
        'states': {},
        'behaviors': {
            'DemoBehavior': {
                'name': 'DemoBehavior',
                'package': 'demo_pkg',
                'outcomes': {
                    'finished': {'name': 'finished', 'remapping': 'completed'},
                },
                'userdata_in': userdata_in or {},
                'userdata_out': userdata_out or {},
            },
        },
    }


def _behavior_state_mappings():
    return {
        'state_outcome_mappings': {'finished': 'completed'},
        'sm_outcome_mappings': {},
        'transition_outcomes': ['completed'],
    }


def test_behavior_capability_with_valid_userdata_loads_successfully(tmp_path):
    """A behavior-backed capability with declared userdata should pass validation."""
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text(
        textwrap.dedent(
            """\
            name: demo
            capabilities:
                demo_step:
                    interface: DemoBehavior
                    userdata_in:
                        request: request
            """
        )
    )
    workspace_data = _behavior_workspace_data(
        userdata_in={'request': {'name': 'request', 'type': 'str'}},
    )
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data=workspace_data,
        state_mappings=_behavior_state_mappings(),
        synthesis_home=str(tmp_path),
    )

    result = loader.preprocess()

    system_capabilities = result[0]
    assert 'behavior' in system_capabilities['capabilities']['demo_step']


def test_behavior_capability_with_unknown_userdata_raises(tmp_path):
    """A behavior-backed capability with an undeclared userdata key must raise."""
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text(
        textwrap.dedent(
            """\
            name: demo
            capabilities:
                demo_step:
                    interface: DemoBehavior
                    userdata_in:
                        typo_key: some_value
            """
        )
    )
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data=_behavior_workspace_data(),
        state_mappings=_behavior_state_mappings(),
    )

    with pytest.raises(UserdataValidationError, match="userdata_in 'typo_key'"):
        loader.preprocess()


def test_capability_interface_matching_state_and_behavior_is_ambiguous(tmp_path):
    """An interface name shared by state and behavior registries must be explicit."""
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text(
        textwrap.dedent(
            """\
            name: demo
            capabilities:
                demo_step:
                    interface: SharedInterface
            """
        )
    )
    workspace_data = {
        'states': {
            'SharedInterface': {
                'name': 'SharedInterface',
                'package': 'demo_states',
                'parameters': {},
                'userdata_in': {},
                'userdata_out': {},
            },
        },
        'behaviors': {
            'SharedInterface': {
                'name': 'SharedInterface',
                'package': 'demo_behaviors',
                'outcomes': {},
                'userdata_in': {},
                'userdata_out': {},
            },
        },
    }
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data=workspace_data,
        state_mappings={},
        synthesis_home=str(tmp_path),
    )

    with pytest.raises(ValueError, match='matches both a FlexBE state and'):
        loader.preprocess()


def test_duplicate_transition_outcome_tags_report_schema_error(tmp_path):
    capabilities_path = tmp_path / 'demo_capabilities.yaml'
    capabilities_path.write_text(
        textwrap.dedent(
            """\
            name: demo
            transition_outcomes:
                - canceled
            capabilities: {}
            """
        )
    )
    loader = CapabilityLoader(
        name='CapabilityLoader',
        system_name='demo',
        capabilities_path=str(capabilities_path),
        workspace_data={
            'states': {},
            'behaviors': {},
        },
        state_mappings={
            'state_outcome_mappings': {},
            'sm_outcome_mappings': {},
            'transition_outcomes': [
                'completed',
                'failure',
            ],
        },
    )

    with pytest.raises(ValueError, match='unique first-character tags'):
        loader.preprocess()
