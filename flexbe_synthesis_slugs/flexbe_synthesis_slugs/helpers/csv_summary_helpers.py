#!/usr/bin/env python3

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

"""
Shared CSV-row summary helpers.

Used by both batch_run_harness.py (writing master/summary CSVs) and
experiment_postprocess.py (reading them back into paper tables and plots),
so the two stay behaviorally identical by construction instead of by
keeping two copies in sync by hand.
"""

from __future__ import annotations

from typing import Any


def bool_text(value: Any) -> str:
    """Normalize bool-like CSV values to True/False strings."""
    return str(value).strip().lower().capitalize()


def realizable_summary(group_rows: list[dict[str, str]]) -> str:
    """
    Return 'Yes'/'No'/'Mixed' for a group's realizable values, '' if none reported.

    Realizability is a property of the compiled spec, not the variable ordering, so a
    well-formed group (same capability file/encoding/liveness/pending) should always
    resolve to 'Yes' or 'No' uniformly across its ordering/reordering rows. 'Mixed' is a
    real anomaly worth investigating, not an expected outcome. '' means no row in the
    group ever reached a realizability determination (e.g. every trial timed out first).
    """
    values = {
        bool_text(row.get('realizable'))
        for row in group_rows
        if row.get('realizable') not in (None, '')
    }
    if not values:
        return ''
    if values == {'True'}:
        return 'Yes'
    if values == {'False'}:
        return 'No'
    return 'Mixed'


def text_summary(group_rows: list[dict[str, str]], field: str) -> str:
    """Return the group's unique text value, Mixed for disagreement, or blank."""
    values = {
        str(row.get(field, ''))
        for row in group_rows
        if row.get(field, '') not in (None, '')
    }
    if not values:
        return ''
    if len(values) == 1:
        return next(iter(values))
    return 'Mixed'


def reordering_policy(row: dict[str, str]) -> str:
    """Return a stable reordering policy, deriving it for older CSV rows."""
    explicit = row.get('reordering_policy')
    if explicit:
        return str(explicit)
    if bool_text(row.get('reordering_enabled', '')) != 'True':
        return 'off'
    threshold = row.get('reordering_threshold')
    if threshold not in (None, ''):
        return f'threshold_{threshold}'
    return 'auto'
