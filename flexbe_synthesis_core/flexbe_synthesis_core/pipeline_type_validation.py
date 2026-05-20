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

"""Utility helpers for validating configured pipeline I/O types."""

from typing import Any, get_args, get_origin

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode

# These types are defined for use in pipelines.
TYPE_MAPPING: dict[str, type] = {
    '': str,
    'bool': bool,
    'dict': dict,
    'float': float,
    'int': int,
    'str': str,
    'set': set,
    'Automaton': dict,
    'FilePathStr': str,
    'FlexBESynthesisRequest': FlexBESynthesisRequest,
    'FlexBESynthesisOptions': str,
    'List[str]': list[str],
    'List[StateInstantiation]': list[StateInstantiation],
    'Mappings': dict,
    'NameStr': str,
    'list': list,
    'Specification': dict,
    'SynthesisErrorCode': SynthesisErrorCode,
    'SystemCapabilities': dict,
    'WorkspaceData': dict,
    'SystemTransitions': dict,
    'SystemPreconditions': dict,
    'SystemPostconditions': dict,
    'StateImplementationsUsed': dict,
    'BehaviorsUsed': dict,
    'None': None,
}


def validate_types(data: Any, expected_type: str, type_mapping=None) -> bool:
    """Return `True` if `data` matches the configured named type."""
    if type_mapping is None:
        type_mapping = TYPE_MAPPING

    try:
        expected = type_mapping[expected_type]
    except KeyError:
        print(f'    unknown expected type ({expected_type})', flush=True)
        return False

    if type(data) == expected:  # noqa: E721 - strict type matching is intentional here.
        return True

    if get_origin(expected) is list:
        item_type = get_args(expected)[0]
        if isinstance(data, list) and all(isinstance(item, item_type) for item in data):
            return True

    if expected is None:
        if data is None:
            return True
        print(
            (
                f"    validate_types error: '{data}' ({type(data)}) "
                'does not match expected type (None)'
            ),
            flush=True,
        )
        return False

    print(
        (
            f"    validate_types error: '{data}' ({type(data)}) "
            f'does not match expected type ({expected})'
        ),
        flush=True,
    )
    return False
