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

"""Tests for workspace outcome remapping validation."""

from flexbe_synthesis_core.validation_error import MappingValidationError
from flexbe_synthesis_generic.preprocesses.workspace_parser import WorkspaceParser
import pytest
import yaml


def _parser(tmp_path, state_outcome_mappings):
    return WorkspaceParser(
        name='Workspace Parser',
        state_mappings={'state_outcome_mappings': state_outcome_mappings},
        synthesis_home=str(tmp_path),
    )


def _write_workspace(tmp_path, state_outcomes=None, behavior_outcomes=None):
    if state_outcomes is None:
        state_outcomes = ['done']
    if behavior_outcomes is None:
        behavior_outcomes = []

    workspace = {
        'states': {
            'DemoState': {
                'outcomes': {
                    outcome: {'name': outcome}
                    for outcome in state_outcomes
                },
            },
        },
        'behaviors': {
            'DemoBehavior': {
                'outcomes': {
                    outcome: {'name': outcome}
                    for outcome in behavior_outcomes
                },
            },
        },
    }
    (tmp_path / 'workspace_defn.yaml').write_text(yaml.safe_dump(workspace))


def test_workspace_parser_applies_all_outcome_mappings(tmp_path):
    """Mapped state and behavior outcomes should receive remapping fields."""
    _write_workspace(tmp_path, state_outcomes=['done'], behavior_outcomes=['failed'])

    workspace_defn, skipped = _parser(
        tmp_path,
        {
            'done': 'completed',
            'failed': 'failure',
        },
    ).preprocess()

    assert skipped == []
    assert (
        workspace_defn['states']['DemoState']['outcomes']['done']['remapping']
        == 'completed'
    )
    assert (
        workspace_defn['behaviors']['DemoBehavior']['outcomes']['failed']['remapping']
        == 'failure'
    )


def test_workspace_parser_rejects_missing_state_outcome_mapping(tmp_path):
    """Unmapped state outcomes should be skipped and reported."""
    _write_workspace(tmp_path, state_outcomes=['unmapped'])

    workspace_defn, skipped = _parser(tmp_path, {'done': 'completed'}).preprocess()

    assert 'DemoState' not in workspace_defn['states']
    assert skipped == ["  state 'DemoState' outcome 'unmapped' — no mapping defined"]


def test_workspace_parser_rejects_missing_behavior_outcome_mapping(tmp_path):
    """Unmapped behavior outcomes should be skipped and reported."""
    _write_workspace(
        tmp_path,
        state_outcomes=['done'],
        behavior_outcomes=['unmapped'],
    )

    workspace_defn, skipped = _parser(tmp_path, {'done': 'completed'}).preprocess()

    assert 'DemoBehavior' not in workspace_defn['behaviors']
    assert skipped == ["  behavior 'DemoBehavior' outcome 'unmapped' — no mapping defined"]


def test_workspace_parser_rejects_non_mapping_state_outcome_mappings(tmp_path):
    """The state_outcome_mappings value must be a mapping."""
    _write_workspace(tmp_path)

    with pytest.raises(MappingValidationError, match='Invalid state_outcome_mappings'):
        _parser(tmp_path, ['done']).preprocess()
