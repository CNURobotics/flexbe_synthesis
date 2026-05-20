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

"""Helpers for expanding compact Slugs integer variable declarations."""

import re

BINARY_RANGE_PATTERN = re.compile(r'!?([A-Za-z0-9_]+):(\d+)\.\.\.(\d+)')


def expand_binary_variables(var_list):
    """Expand `name:min...max` entries in-place into `name@bit` variables; return mapping of name->(min,max)."""
    original = var_list[:]
    binary_variables = {}

    for var in original:
        match = BINARY_RANGE_PATTERN.fullmatch(var)
        if not match:
            continue

        ap = match.group(1)
        min_val = int(match.group(2))
        max_val = int(match.group(3))
        index = var_list.index(var)

        range_size = max_val - min_val + 1
        binary_variables[ap] = (min_val, max_val)
        var_list[index] = f'{ap}@0'

        num_bits = max(1, (range_size - 1).bit_length())
        for cnt in range(1, num_bits):
            var_list.insert(index + cnt, f'{ap}@{cnt}')

    return binary_variables
