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

class ValidationError(Exception):
    """
    Raised when pipeline or plugin configuration is invalid.

    Attributes
    ----------
    kind : str or None
        One of the ``ValidationError.*`` class constants that identifies the
        failure category, or ``None`` when the kind is unspecified.

    """

    PIPELINE_LOAD = 'pipeline_load'
    MISSING_ENTRY_POINT = 'missing_entry_point'
    PLUGIN_NOT_FOUND = 'plugin_not_found'
    PLUGIN_INTERFACE = 'plugin_interface'
    INPUT_NOT_DEFINED = 'input_not_defined'
    TYPE_UNKNOWN = 'type_unknown'
    TYPE_MISMATCH = 'type_mismatch'

    def __init__(self, message, kind=None):
        super().__init__(message)
        self.kind = kind


class MappingValidationError(ValueError):
    """Raised when configured mappings are missing or invalid."""

    pass


class UserdataValidationError(ValueError):
    """Raised when capability userdata configuration is missing or invalid."""

    pass
