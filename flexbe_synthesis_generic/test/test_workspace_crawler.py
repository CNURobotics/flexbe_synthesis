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

"""Tests for AST-based workspace crawling helpers."""

import textwrap

from flexbe_synthesis_generic.preprocesses import workspace_crawler
from flexbe_synthesis_generic.preprocesses.workspace_crawler import WorkspaceCrawler
import pytest


def _crawler():
    return WorkspaceCrawler(name='WorkspaceCrawler')


def test_process_python_file_extracts_event_state_docstring(tmp_path):
    source_path = tmp_path / 'demo_state.py'
    source_path.write_text(
        textwrap.dedent(
            '''\
            from flexbe_core import EventState


            class DemoState(EventState):
                """Demo state.

                -- text string Text to log
                <= done completed
                ># request string Request input
                #> result string Result output
                """
            '''
        )
    )

    title, file_type, state_data, behavior_data = _crawler().process_python_file(
        str(source_path)
    )

    assert title == 'DemoState'
    assert file_type == 'EventState'
    assert '-- text string Text to log' in state_data
    assert behavior_data == ''


def test_process_python_file_extracts_multiline_behavior_interface(tmp_path):
    source_path = tmp_path / 'demo_behavior.py'
    source_path.write_text(
        textwrap.dedent(
            """\
            from flexbe_core import Behavior, OperatableStateMachine

            OUTCOMES = ['done', 'failed']
            DEFAULT_COUNT = 2


            class DemoBehavior(Behavior):
                def __init__(self):
                    super().__init__()
                    self.name = 'Demo Behavior'

                def create(self):
                    _state_machine = OperatableStateMachine(
                        outcomes=OUTCOMES,
                        input_keys=['request'],
                        output_keys=['result'],
                    )
                    _state_machine.userdata.count = DEFAULT_COUNT
                    return _state_machine
            """
        )
    )

    title, file_type, state_data, behavior_data = _crawler().process_python_file(
        str(source_path)
    )

    assert title == 'DemoBehavior'
    assert file_type == 'Behavior'
    assert state_data == ''
    assert '$$ Demo Behavior' in behavior_data
    assert '<= done, failed' in behavior_data
    assert '##_state_machine.userdata.count = 2' in behavior_data


def test_process_python_file_ignores_helper_modules(tmp_path):
    source_path = tmp_path / 'helper.py'
    source_path.write_text('class Helper: pass\n')

    assert _crawler().process_python_file(str(source_path)) == (
        None,
        None,
        None,
        None,
    )


def test_process_python_file_reports_syntax_errors(tmp_path):
    source_path = tmp_path / 'broken.py'
    source_path.write_text('class Broken(:\n')

    with pytest.raises(ValueError, match='Failed to parse Python syntax'):
        _crawler().process_python_file(str(source_path))


@pytest.mark.parametrize('marker', ['--', '>#', '#>'])
def test_parse_typed_docstring_line_accepts_name_only(marker):
    data = _crawler()._parse_typed_docstring_line(f'{marker} request', marker)

    assert data == {
        'name': 'request',
        'remapping': 'request',
        'type': 'unknown',
        'description': '',
    }


def test_parse_typed_docstring_line_accepts_type_and_description():
    data = _crawler()._parse_typed_docstring_line(
        '># request\tstring\tRequest input',
        '>#',
    )

    assert data == {
        'name': 'request',
        'remapping': 'request',
        'type': 'string',
        'description': 'Request input',
    }


@pytest.mark.parametrize('line', ['># request', '#> result'])
def test_behavior_userdata_assignment_ignores_docstring_lines_without_equals(line):
    assert _crawler()._parse_behavior_userdata_assignment(line) is None


def test_behavior_userdata_assignment_parses_generated_default():
    data = _crawler()._parse_behavior_userdata_assignment(
        '##_state_machine.userdata.count = 2'
    )

    assert data == {
        'name': 'count',
        'remapping': 'count',
        'type': 'unknown',
        'data': '2',
    }


def test_preprocess_returns_empty_output_list(monkeypatch, tmp_path):
    """Workspace crawler writes its artifact but returns an empty output list."""
    package_dir = tmp_path / 'demo_pkg'
    package_dir.mkdir()
    (package_dir / '__init__.py').write_text('')
    (package_dir / 'demo_state.py').write_text(
        textwrap.dedent(
            '''\
            from flexbe_core import EventState


            class DemoState(EventState):
                """Demo state.

                <= done completed
                """
            '''
        )
    )
    package = type(
        'Package',
        (),
        {
            'name': 'demo_pkg',
            'exports': [type('Export', (), {'tagname': 'flexbe_states'})()],
        },
    )()
    spec = type('Spec', (), {'origin': str(package_dir / '__init__.py')})()
    monkeypatch.setattr(
        workspace_crawler,
        'get_packages_with_prefixes',
        lambda: {'demo_pkg': str(tmp_path)},
    )
    monkeypatch.setattr(workspace_crawler, 'parse_package', lambda path: package)
    monkeypatch.setattr(
        workspace_crawler.importlib.util,
        'find_spec',
        lambda package_name: spec,
    )
    crawler = _crawler()
    crawler.synthesis_home = str(tmp_path / 'synthesis_home')

    assert crawler.preprocess() == [[]]
    assert (tmp_path / 'synthesis_home' / 'workspace_defn.yaml').exists()


def test_main_warns_for_ignored_inputs(capsys):
    """Workspace crawler entry point should warn when configured with inputs."""
    crawler = workspace_crawler.main(['unexpected'])

    captured = capsys.readouterr()
    assert isinstance(crawler, WorkspaceCrawler)
    assert 'WARNING: WorkspaceCrawler ignores plugin inputs' in captured.out


def test_main_accepts_empty_inputs_without_warning(capsys):
    """Empty pipeline input lists are expected for workspace crawler."""
    crawler = workspace_crawler.main([])

    captured = capsys.readouterr()
    assert isinstance(crawler, WorkspaceCrawler)
    assert 'WARNING: WorkspaceCrawler ignores plugin inputs' not in captured.out
