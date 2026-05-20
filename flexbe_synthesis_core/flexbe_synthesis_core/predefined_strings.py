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

"""Project-wide constants and standard filesystem paths."""

import os

_DEFAULT_SYNTHESIS_HOME = '~/.flexbe_synthesis'
_SYNTHESIS_HOME_ENV = 'FLEXBE_SYNTHESIS_HOME'


def get_synthesis_home(override=''):
    """Return the configured FlexBE synthesis artifact directory."""
    try:
        base_path = override or os.getenv(_SYNTHESIS_HOME_ENV) or _DEFAULT_SYNTHESIS_HOME
        return os.path.abspath(os.path.expanduser(base_path))
    except (OSError, ValueError) as exc:
        raise RuntimeError('Failed to resolve FlexBE synthesis home') from exc


# Standard file names.
_DISCRETE_ABSTRACTION_CONFIG_EXT = '_discrete_abstraction.yaml'
_SYSTEM_CAPABILITIES_CONFIG_EXT = '_system_capabilities.yaml'
_TRANSITION_RELATIONS_CONFIG_EXT = '_transition_relations.yaml'

# Entry point groups.
_PREPROCESSES = 'FlexBESynthesis.preprocesses'
_PROCESSES = 'FlexBESynthesis.processes'
