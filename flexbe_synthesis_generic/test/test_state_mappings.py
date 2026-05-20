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

"""Tests for custom state mapping preprocessing."""

from flexbe_synthesis_generic.preprocesses.state_mappings import StateMappings
import pytest


def test_state_mappings_rejects_non_mapping_yaml(tmp_path):
    """Custom mapping files must have a top-level mapping."""
    mappings_path = tmp_path / 'custom_mappings.yaml'
    mappings_path.write_text('- invalid\n', encoding='utf-8')

    preprocessor = StateMappings(
        name='StateMappings',
        mappings_path=str(mappings_path),
        state_mappings={},
    )

    with pytest.raises(ValueError, match='top-level mapping'):
        preprocessor.preprocess()


def test_state_mappings_merges_dicts_and_deduplicates_lists(tmp_path):
    """Custom mappings should merge into existing dictionaries and list fields."""
    mappings_path = tmp_path / 'custom_mappings.yaml'
    mappings_path.write_text(
        """\
state_outcome_mappings:
  done: completed
transition_outcomes:
  - failure
  - completed
""",
        encoding='utf-8',
    )
    state_mappings = {
        'state_outcome_mappings': {'failed': 'failure'},
        'transition_outcomes': ['completed'],
    }

    preprocessor = StateMappings(
        name='StateMappings',
        mappings_path=str(mappings_path),
        state_mappings=state_mappings,
    )

    (merged,) = preprocessor.preprocess()

    assert merged['state_outcome_mappings'] == {
        'done': 'completed',
        'failed': 'failure',
    }
    assert merged['transition_outcomes'] == ['completed', 'failure']
