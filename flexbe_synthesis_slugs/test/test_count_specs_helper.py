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

"""Tests for the Slugs spec counting helper CLI."""

from flexbe_synthesis_slugs.helpers.count_specs import (
    count_spec_file,
    main as count_specs_main,
)
import pytest
import yaml


def _write_structuredslugs(path):
    path.write_text(
        """\
[INPUT]
request

[OUTPUT]
done

[SYS_INIT]
!done

[SYS_LIVENESS]
done
""",
        encoding='utf-8',
    )


def test_count_spec_file_appends_structuredslugs_extension(tmp_path):
    """Filenames without an extension should resolve to .structuredslugs."""
    spec_path = tmp_path / 'demo.structuredslugs'
    _write_structuredslugs(spec_path)

    resolved_path, counts = count_spec_file(str(tmp_path / 'demo'))

    assert resolved_path == spec_path
    assert counts == {
        'INPUT': 1,
        'OUTPUT': 1,
        'SYS_INIT': 1,
        'SYS_LIVENESS': 1,
    }


def test_count_specs_cli_prints_text_counts(tmp_path, capsys):
    """The CLI should print readable section counts by default."""
    spec_path = tmp_path / 'demo.structuredslugs'
    _write_structuredslugs(spec_path)

    assert count_specs_main([str(spec_path)]) == 0

    output = capsys.readouterr().out
    assert f"Counts for '{spec_path}'" in output
    assert 'INPUT' in output
    assert 'SYS_LIVENESS' in output


def test_count_specs_cli_prints_yaml_counts(tmp_path, capsys):
    """Structured output should be available for scripts."""
    spec_path = tmp_path / 'demo.structuredslugs'
    _write_structuredslugs(spec_path)

    assert count_specs_main([str(spec_path), '--format', 'yaml']) == 0

    assert yaml.safe_load(capsys.readouterr().out) == {
        'INPUT': 1,
        'OUTPUT': 1,
        'SYS_INIT': 1,
        'SYS_LIVENESS': 1,
    }


def test_count_specs_cli_help_exits_cleanly(capsys):
    """The CLI should provide argparse help instead of treating --help as a file."""
    with pytest.raises(SystemExit) as exc_info:
        count_specs_main(['--help'])

    assert exc_info.value.code == 0
    assert 'Count sections in .structuredslugs or .slugsin files' in capsys.readouterr().out


def test_count_specs_cli_rejects_primed_input(tmp_path, capsys):
    """Invalid INPUT/OUTPUT declarations should produce a clean CLI error."""
    spec_path = tmp_path / 'bad.structuredslugs'
    spec_path.write_text(
        """\
[INPUT]
request'
""",
        encoding='utf-8',
    )

    with pytest.raises(SystemExit) as exc_info:
        count_specs_main([str(spec_path)])

    assert exc_info.value.code == 1
    assert 'contains a prime' in capsys.readouterr().err
