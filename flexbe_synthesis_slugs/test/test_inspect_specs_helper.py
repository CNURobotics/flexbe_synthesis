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

"""Tests for the Slugs YAML spec inspection helper."""

import flexbe_synthesis_slugs.helpers.inspect_specs as inspect_specs
from flexbe_synthesis_slugs.helpers.inspect_specs import (
    analyze_formula_block,
    expressions_equivalent,
    load_sympy,
    main as inspect_specs_main,
    parse_formula,
    SYMPY_INSTALL_HINT,
)

import pytest


def _write_spec(path, formulas):
    quoted_formulas = '\n'.join(f'      - "{formula}"' for formula in formulas)
    path.write_text(
        f"""\
specs:
    INPUT:
      - "request"
    OUTPUT:
      - "done"
    SYS_TRANS:
{quoted_formulas}
""",
        encoding='utf-8',
    )


def test_analyze_formula_block_detects_equivalent_duplicates():
    """Equivalent formulas in one block should be reported as duplicates."""
    analysis = analyze_formula_block(['a & b', 'b & a'])

    assert analysis.ok is False
    assert analysis.duplicates == [(1, 0, 'b & a')]


def test_inspect_specs_single_file_strict_fails_on_duplicate(tmp_path, capsys):
    """Single-file mode should preserve the old internal consistency check."""
    spec_path = tmp_path / 'duplicate.yaml'
    _write_spec(spec_path, ['a & b', 'b & a'])

    assert inspect_specs_main([str(spec_path)]) == 0
    assert inspect_specs_main([str(spec_path), '--strict']) == 1

    output = capsys.readouterr().out
    assert 'Duplicate at index 1 matches index 0' in output


def test_inspect_specs_compares_equivalent_files(tmp_path, capsys):
    """Two-file mode should compare formulas by logical equivalence."""
    spec1_path = tmp_path / 'spec1.yaml'
    spec2_path = tmp_path / 'spec2.yaml'
    _write_spec(spec1_path, ['a & b'])
    _write_spec(spec2_path, ['b & a'])

    assert inspect_specs_main([str(spec1_path), str(spec2_path), '--strict']) == 0

    output = capsys.readouterr().out
    assert 'Spec 1 has 0 unmatched specs' in output
    assert 'Spec 2 has 0 unmatched specs' in output


def test_inspect_specs_compares_different_files_strict(tmp_path, capsys):
    """Strict two-file mode should fail when formulas are unmatched."""
    spec1_path = tmp_path / 'spec1.yaml'
    spec2_path = tmp_path / 'spec2.yaml'
    _write_spec(spec1_path, ['a'])
    _write_spec(spec2_path, ['b'])

    assert inspect_specs_main([str(spec1_path), str(spec2_path), '--strict']) == 1

    output = capsys.readouterr().out
    assert 'has no equivalent' in output


def test_inspect_specs_help_exits_cleanly(capsys):
    """The CLI should provide argparse help."""
    with pytest.raises(SystemExit) as exc_info:
        inspect_specs_main(['--help'])

    assert exc_info.value.code == 0
    assert 'Inspect one Slugs YAML spec' in capsys.readouterr().out


def test_inspect_specs_does_not_crash_on_unsupported_equivalence():
    """Biconditional forms should compare against expanded boolean formulas."""
    analysis = analyze_formula_block(['a <-> b', '(a & b) | (!a & !b)'])

    assert analysis.invalid == []
    assert analysis.duplicates == [(1, 0, '(a & b) | (!a & !b)')]


def test_parse_formula_handles_common_slugs_operators():
    """Formula parsing should preserve Slugs operator semantics."""
    _normalized, implication = parse_formula('a -> b')
    _normalized, expanded_implication = parse_formula('!a | b')
    _normalized, tautology = parse_formula('a | !a')
    _normalized, true_literal = parse_formula('True')
    _normalized, contradiction = parse_formula('a & !a')
    _normalized, false_literal = parse_formula('False')
    _normalized, prime = parse_formula("done'")
    _normalized, next_call = parse_formula('next(done)')
    _normalized, neg_next_call = parse_formula('next(!done)')
    _normalized, neg_next = parse_formula('!next(done)')

    assert expressions_equivalent(implication, expanded_implication)
    assert expressions_equivalent(tautology, true_literal)
    assert expressions_equivalent(contradiction, false_literal)
    assert expressions_equivalent(prime, next_call)
    assert expressions_equivalent(neg_next_call, neg_next)


def test_load_sympy_reports_install_hint(monkeypatch):
    """Missing optional SymPy should produce an actionable error."""
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == 'sympy':
            raise ImportError('missing sympy')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(inspect_specs, '_SYMPY_SYMBOLS', None)
    monkeypatch.setattr(inspect_specs, '_SYMPY_BOOLALG', None)
    monkeypatch.setattr('builtins.__import__', fake_import)

    with pytest.raises(RuntimeError, match='SymPy is required'):
        load_sympy()

    assert 'python3-sympy' in SYMPY_INSTALL_HINT


def test_inspect_specs_reports_missing_sympy_without_traceback(tmp_path, monkeypatch, capsys):
    """A real inspection run should fail cleanly when optional SymPy is missing."""
    spec_path = tmp_path / 'spec.yaml'
    _write_spec(spec_path, ['a'])
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == 'sympy':
            raise ImportError('missing sympy')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(inspect_specs, '_SYMPY_SYMBOLS', None)
    monkeypatch.setattr(inspect_specs, '_SYMPY_BOOLALG', None)
    monkeypatch.setattr('builtins.__import__', fake_import)

    with pytest.raises(SystemExit) as exc_info:
        inspect_specs_main([str(spec_path)])

    assert exc_info.value.code == 1
    assert 'SymPy is required' in capsys.readouterr().err
