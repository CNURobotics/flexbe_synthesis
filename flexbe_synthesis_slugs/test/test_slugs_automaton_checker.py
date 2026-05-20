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

"""Tests for the Slugs automaton checker helper."""

import importlib.util
import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    PACKAGE_ROOT
    / 'flexbe_synthesis_slugs'
    / 'helpers'
    / 'slugs_automaton_checker.py'
)
MODULE_SPEC = importlib.util.spec_from_file_location('slugs_automaton_checker', MODULE_PATH)
slugs_automaton_checker = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(slugs_automaton_checker)

SlugsAutomatonChecker = slugs_automaton_checker.SlugsAutomatonChecker
parse_structuredslugs_variables = slugs_automaton_checker.parse_structuredslugs_variables
resolve_existing_path = slugs_automaton_checker.resolve_existing_path


def test_parse_structuredslugs_variables(tmp_path):
    """Input/output variables should be read from structured Slugs sections."""
    spec_path = tmp_path / 'demo.structuredslugs'
    spec_path.write_text(
        """\
[INPUT]
request
count:0...2

[OUTPUT]
done
mode:0...2

[SYS_INIT]
!done
""",
        encoding='utf-8',
    )

    input_vars, output_vars = parse_structuredslugs_variables(spec_path)

    assert input_vars == ['request', 'count:0...2']
    assert output_vars == ['done', 'mode:0...2']


def test_resolve_existing_path_searches_roots(tmp_path):
    """Relative names should resolve from provided search roots."""
    nested = tmp_path / 'share' / 'example'
    nested.mkdir(parents=True)
    target = nested / 'demo.json'
    target.write_text('{}\n', encoding='utf-8')

    assert resolve_existing_path('demo.json', [tmp_path]) == target


def test_slugs_automaton_checker_converts_json(tmp_path):
    """The checker should build a SlugsAutomaton from JSON and variables."""
    json_path = tmp_path / 'demo.json'
    json_path.write_text(
        json.dumps(
            {
                'nodes': {
                    '0': {
                        'state': [1, 0],
                        'trans': [0],
                        'rank': 0,
                    },
                },
            }
        ),
        encoding='utf-8',
    )

    automaton = SlugsAutomatonChecker().gen_automaton_msg_from_json(
        json_path,
        ['request'],
        ['done'],
    )

    assert automaton.input_variables == ['request']
    assert automaton.output_variables == ['done']
    assert automaton.size() == 1
