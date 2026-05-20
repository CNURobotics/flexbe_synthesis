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

"""Tests for pipeline type validation helpers."""

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core.pipeline_type_validation import validate_types
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode


def test_validate_types_accepts_registered_scalar_types():
    """Registered scalar names should match values of the exact expected type."""
    assert validate_types(True, 'bool')
    assert validate_types({'key': 'value'}, 'dict')
    assert validate_types(1.0, 'float')
    assert validate_types(1, 'int')
    assert validate_types('value', 'str')
    assert validate_types(set(), 'set')


def test_validate_types_accepts_registered_message_types():
    """Registered ROS message type names should match their message instances."""
    assert validate_types(FlexBESynthesisRequest(), 'FlexBESynthesisRequest')
    assert validate_types(SynthesisErrorCode(), 'SynthesisErrorCode')


def test_validate_types_accepts_registered_list_types():
    """Registered list aliases should validate every item in the list."""
    assert validate_types(['a', 'b'], 'List[str]')
    assert validate_types([StateInstantiation()], 'List[StateInstantiation]')


def test_validate_types_accepts_yaml_local_alias_mapping():
    """Callers may pass a pipeline-local type mapping with semantic aliases."""
    type_mapping = {
        'ReducedAutomaton': dict,
    }

    assert validate_types({'automaton': []}, 'ReducedAutomaton', type_mapping)


def test_validate_types_rejects_unknown_and_mismatched_types():
    """Unknown names and mismatched values should fail validation."""
    assert not validate_types('value', 'NotAType')
    assert not validate_types('1', 'int')
    assert not validate_types([1], 'List[str]')


def test_validate_types_requires_none_for_none_alias():
    """The `None` alias should accept only an actual None value."""
    assert validate_types(None, 'None')
    assert not validate_types('', 'None')
