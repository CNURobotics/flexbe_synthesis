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

"""Post-process Slugs experiment CSVs into LaTeX tables and ordering plots."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any

from flexbe_synthesis_slugs.helpers.csv_summary_helpers import (
    realizable_summary as _realizable_summary,
    reordering_policy as _reordering_policy,
    text_summary as _text_summary,
)


FIXED_ORDERING_MODES = ('alphabetic', 'domain')
PLOT_POLICY_ORDER = [
    ('off', 'no reorder'),
    ('auto', 'auto'),
    ('threshold_250', 'threshold 250'),
]
TIME_METRICS = [
    ('realizability_time_s', 'Slugs realizability time (s)'),
    ('overall_pipeline_time_s', 'Overall pipeline time (s)'),
]
SUMMARY_KEYS = [
    'capability_file',
    'encoding',
    'liveness',
    'pending',
    'column_indicator',
    'ordering_mode',
    'reordering_enabled',
    'reordering_threshold',
    'reordering_policy',
]
SUMMARY_NUMERIC_FIELDS = [
    'cudd_peak_nodes',
    'cudd_live_nodes',
    'realizability_time_s',
    'extraction_time_s',
    'original_auditor_time_s',
    'auditor_time_s',
    'mealy_graph_time_s',
    'reduction_time_s',
    'reduced_mealy_graph_time_s',
    'sm_generation_time_s',
    'sm_layout_time_s',
    'count_specs_time_s',
    'well_separation_analyzer_time_s',
    'generate_specs_time_s',
    'realize_hfsm_time_s',
    'overall_pipeline_time_s',
    'max_non_slugs_time_s',
    'non_slugs_total_time_s',
    'slugs_sm_size',
    'reduced_sm_size',
    'state_defn_size',
    'ap_i',
    'ap_o',
    'env_init_count',
    'sys_init_count',
    'env_trans_count',
    'sys_trans_count',
    'env_liveness_count',
    'sys_liveness_count',
    'cudd_reorderings',
    'cudd_next_reordering',
    'cudd_reordering_time_s',
    'slugs_reported_elapsed_time_s',
    'slugs_timing_total_s',
    'core_minimization_s',
    'core_candidate_count',
    'core_solver_calls',
    'core_size',
]
SUMMARY_TEXT_FIELDS = [
    'flexbe_hfsm_realized',
    'well_separation_status',
    'well_separation_complete',
    'violated_assumption_type',
    'core_enabled',
    'core_complete',
    'max_non_slugs_stage',
]
TABLE_GROUP_KEYS = [
    'capability_file',
    'encoding',
    'liveness',
    'pending',
]

GENERATE_SPECS_STAGE_TIME_FIELDS = [
    'spec_loader_time_s',
    'capability_spec_time_s',
    'transition_spec_time_s',
    'request_spec_time_s',
    'system_goal_liveness_time_s',
    'fair_outcome_liveness_time_s',
    'pending_spec_time_s',
    'activation_spec_time_s',
    'compiler_time_s',
]

REALIZE_HFSM_STAGE_TIME_FIELDS = [
    'reduced_mealy_graph_time_s',
    'sm_generation_time_s',
    'sm_layout_time_s',
    'count_specs_time_s',
]


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read CSV rows as dictionaries."""
    with path.open(newline='', encoding='utf-8') as csv_file:
        return list(csv.DictReader(csv_file))


def _float_value(value: Any) -> float | None:
    """Return a float for a CSV cell, or None when missing/non-numeric."""
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: Any, precision: int) -> str:
    """Format a numeric table value compactly."""
    number = _float_value(value)
    if number is None:
        return '--'
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    text = f'{number:.{precision}f}'
    # Only trim trailing zeros in the fractional part; never strip a significant
    # trailing zero from an integer-formatted value (e.g. 250.45 -> "250").
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


def _decimal_value(value: Any) -> Decimal | None:
    """Return a Decimal for exact table rounding, or None when unavailable."""
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_half_up_decimal(value: Any, places: int = 1) -> str:
    """Format a numeric value with fixed-place ROUND_HALF_UP rounding."""
    number = _decimal_value(value)
    if number is None:
        return '--'
    quantizer = Decimal('1') if places == 0 else Decimal('1').scaleb(-places)
    return f'{number.quantize(quantizer, rounding=ROUND_HALF_UP):.{places}f}'


def _is_identical_integer_mean(
    row: dict[str, str],
    metric: str,
    mean: Decimal,
    scale: Decimal = Decimal('1'),
) -> bool:
    """Return true when all displayed contributing values are the same integer."""
    scaled_mean = mean * scale
    if scaled_mean != scaled_mean.to_integral_value():
        return False
    stdev = _decimal_value(row.get(f'{metric}_stdev'))
    if stdev is not None:
        return stdev == 0
    minimum = _decimal_value(row.get(f'{metric}_min'))
    maximum = _decimal_value(row.get(f'{metric}_max'))
    if minimum is not None and maximum is not None:
        return minimum * scale == maximum * scale == scaled_mean
    n = _float_value(row.get('n')) or 0
    return n <= 1


def _format_mean_number(
    row: dict[str, str],
    metric: str,
    scale: float = 1.0,
    places: int = 1,
) -> str:
    """Format a mean table value with fixed decimal precision."""
    mean = _decimal_value(row.get(f'{metric}_mean'))
    if mean is None:
        return '--'
    scale_decimal = Decimal(str(scale))
    scaled_mean = mean * scale_decimal
    if places > 0 and _is_identical_integer_mean(row, metric, mean, scale_decimal):
        return _format_half_up_decimal(scaled_mean, 0)
    return _format_half_up_decimal(scaled_mean, places)


def _format_stdev_number(
    row: dict[str, str],
    metric: str,
    scale: float = 1.0,
    places: int = 1,
) -> str:
    r"""
    Format a "$\pm$ stdev" companion-row value.

    Blank when the cell's mean came from a single trial (`n <= 1`, e.g. a
    fixed ordering with no repeats) or when every contributing trial gave the
    identical value (stdev == 0) -- there's no spread to report in either
    case, so the companion row stays empty rather than showing a redundant
    "$\pm$ 0".
    """
    n = _float_value(row.get('n')) or 0
    stdev = _decimal_value(row.get(f'{metric}_stdev'))
    if n <= 1 or stdev is None or stdev == 0:
        return ''
    scale_decimal = Decimal(str(scale))
    return f'$\\pm$ {_format_half_up_decimal(stdev * scale_decimal, places)}'


def _well_separated_label(status: str) -> str:
    """
    Return the paper's Yes/No label for a group's well_separation_status.

    'Mixed' (disagreement across a group's orderings) passes through
    unchanged rather than collapsing to Yes/No: it isn't a completed
    well-separation determination, and papers reporting it have historically
    annotated the fraction of orderings actually resolved (e.g. "Yes (9/22)")
    directly in prose rather than in this cell, so this label deliberately
    stays literal instead of guessing at that annotation.

    'ANALYSIS_INCOMPLETE' displays as 'TIME OUT' -- every occurrence seen in
    practice has been the analyzer's subprocess timing out, though the
    underlying status also covers a missing Slugs binary or the process
    being canceled (see slugs_well_separation_analyzer.py); those would need
    a different label if they ever actually show up in a results table.
    """
    if status == 'WELL_SEPARATED':
        return 'Yes'
    if status == 'NON_WELL_SEPARATED':
        return 'No'
    if status == 'ANALYSIS_INCOMPLETE':
        return 'TIME OUT'
    return status


def _stage_time_sum(row: dict[str, str], fields: list[str]) -> str:
    """Return a derived timing sum from present stage timing fields."""
    stage_timings = _stage_timings_for_row(row)
    values = []
    for field in fields:
        value = row.get(field)
        if value in (None, ''):
            value = stage_timings.get(field)
        values.append(_float_value(value))
    values = [value for value in values if value is not None]
    return str(sum(values)) if values else ''


def _stage_timings_for_row(row: dict[str, str]) -> dict[str, Any]:
    """Read detailed stage timings for rows from older compact master CSVs."""
    path_text = row.get('stage_timing_json_file')
    if not path_text:
        return {}
    path = Path(path_text).expanduser()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _derive_master_fields(row: dict[str, str]) -> None:
    """Populate postprocess-only derived fields for older master CSVs."""
    if row.get('well_separation_analyzer_time_s', '') in (None, ''):
        row['well_separation_analyzer_time_s'] = (
            row.get('slugs_timing_total_s')
            or row.get('slugs_reported_elapsed_time_s')
            or ''
        )
    if row.get('generate_specs_time_s', '') in (None, ''):
        row['generate_specs_time_s'] = _stage_time_sum(
            row,
            GENERATE_SPECS_STAGE_TIME_FIELDS,
        )
    if row.get('realize_hfsm_time_s', '') in (None, ''):
        row['realize_hfsm_time_s'] = _stage_time_sum(
            row,
            REALIZE_HFSM_STAGE_TIME_FIELDS,
        )
    if row.get('flexbe_hfsm_realized', '') in (None, ''):
        state_defn_size = _float_value(row.get('state_defn_size'))
        row['flexbe_hfsm_realized'] = (
            'Yes' if state_defn_size is not None and state_defn_size > 0 else 'No'
        )


def _policy_values(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Return plotted reordering policies present in rows."""
    present = {_reordering_policy(row) for row in rows}
    preferred = {policy for policy, _ in PLOT_POLICY_ORDER}
    values = [
        (policy, label)
        for policy, label in PLOT_POLICY_ORDER
        if policy in present
    ]
    values.extend(
        (policy, policy.replace('_', ' '))
        for policy in sorted(present - preferred)
    )
    return values


def _capability_label(path: str) -> str:
    """Return a compact label for a capability-file path."""
    stem = Path(path).stem
    stem = stem.replace('coffee_capabilities_extended', 'Coffee extended')
    stem = stem.replace('coffee_capabilities', 'Coffee base')
    return stem.replace('_', r'\_')


def _latex_escape(value: Any) -> str:
    """Escape a value for a small LaTeX table."""
    text = str(value)
    return (
        text.replace('\\', r'\textbackslash{}')
        .replace('&', r'\&')
        .replace('%', r'\%')
        .replace('$', r'\$')
        .replace('#', r'\#')
        .replace('_', r'\_')
        .replace('{', r'\{')
        .replace('}', r'\}')
        .replace('~', r'\textasciitilde{}')
        .replace('^', r'\textasciicircum{}')
    )


def _metric_column(metric: str, stat: str) -> str:
    """Return the summary CSV column for a metric/stat pair."""
    return f'{metric}_{stat}'


def _policy_label(policy: str) -> str:
    """Return a compact human-readable label for a reordering policy."""
    labels = dict(PLOT_POLICY_ORDER)
    if policy in labels:
        return labels[policy]
    if policy.startswith('threshold_'):
        return 'threshold ' + policy.split('_', 1)[1]
    return policy.replace('_', ' ')


def _ordering_label(ordering_mode: str) -> str:
    """Return a compact table heading label for an ordering mode."""
    labels = {
        'alphabetic': 'Alpha',
        'domain': 'Domain',
        'random': 'Random',
    }
    return labels.get(ordering_mode, ordering_mode.title())


def _table_treatments(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Return ordering/policy columns present in summary rows."""
    mode_order = {mode: index for index, mode in enumerate([
        'alphabetic',
        'domain',
        'random',
    ])}
    policy_order = {policy: index for index, (policy, _) in enumerate(PLOT_POLICY_ORDER)}
    treatments = {
        (row.get('ordering_mode', ''), _reordering_policy(row))
        for row in rows
        if row.get('ordering_mode', '')
    }
    return sorted(
        treatments,
        key=lambda item: (
            mode_order.get(item[0], len(mode_order)),
            item[0],
            policy_order.get(item[1], len(policy_order)),
            item[1],
        ),
    )


def _treatment_key(row: dict[str, str]) -> tuple[str, str]:
    """Return the plotted treatment key for a CSV row."""
    return row.get('ordering_mode', ''), _reordering_policy(row)


def write_summary(master_path: Path, summary_path: Path) -> Path:
    """Write grouped summary statistics from the raw master CSV."""
    rows = _read_rows(master_path)
    if not rows:
        return summary_path

    groups: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in rows:
        _derive_master_fields(row)
        row['reordering_policy'] = _reordering_policy(row)
        key = tuple(row.get(field, '') for field in SUMMARY_KEYS)
        groups.setdefault(key, []).append(row)

    fieldnames = list(SUMMARY_KEYS) + [
        'n',
        'failures',
        'realizable',
        *SUMMARY_TEXT_FIELDS,
        'well_separated_label',
    ]
    for field in SUMMARY_NUMERIC_FIELDS:
        fieldnames.extend([
            f'{field}_mean',
            f'{field}_min',
            f'{field}_max',
            f'{field}_stdev',
        ])

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open('w', newline='', encoding='utf-8') as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()
        for key, group_rows in sorted(groups.items()):
            output: dict[str, Any] = dict(zip(SUMMARY_KEYS, key))
            output['n'] = len(group_rows)
            output['failures'] = sum(
                1 for row in group_rows
                if row.get('failure') or row.get('return_code') not in ('0', 0)
            )
            output['realizable'] = _realizable_summary(group_rows)
            for field in SUMMARY_TEXT_FIELDS:
                output[field] = _text_summary(group_rows, field)
            output['well_separated_label'] = _well_separated_label(
                output.get('well_separation_status', ''),
            )
            for field in SUMMARY_NUMERIC_FIELDS:
                values = [
                    value for value in (
                        _float_value(row.get(field)) for row in group_rows
                    )
                    if value is not None
                ]
                output[f'{field}_mean'] = (
                    statistics.mean(values) if values else ''
                )
                output[f'{field}_min'] = min(values) if values else ''
                output[f'{field}_max'] = max(values) if values else ''
                output[f'{field}_stdev'] = (
                    statistics.stdev(values) if len(values) > 1 else 0
                    if values else ''
                )
            writer.writerow(output)
    return summary_path


def _group_key(row: dict[str, str]) -> tuple[str, ...]:
    """Return the LaTeX table grouping key for a summary row."""
    return tuple(row.get(field, '') for field in TABLE_GROUP_KEYS)


def write_latex_table(
    summary_path: Path,
    output_path: Path,
    metric: str = 'cudd_peak_nodes',
    stat: str = 'mean',
    precision: int = 2,
    caption: str | None = None,
    label: str | None = None,
) -> Path:
    """Write a compact LaTeX table from a grouped summary CSV."""
    rows = _read_rows(summary_path)
    metric_column = _metric_column(metric, stat)
    if rows and metric_column not in rows[0]:
        raise ValueError(
            f"Summary file '{summary_path}' does not contain column "
            f"'{metric_column}'."
        )

    grouped: dict[tuple[str, ...], dict[str, dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(_group_key(row), {})[_treatment_key(row)] = row

    output_path.parent.mkdir(parents=True, exist_ok=True)
    caption = caption or f'{metric} {stat} by Coffee experiment axis.'
    label = label or f'tab:{_safe_slug(metric)}-{stat}'
    treatments = _table_treatments(rows)
    treatment_labels = [
        f'{_ordering_label(mode)} {_policy_label(policy)}'
        for mode, policy in treatments
    ]
    column_spec = 'llll' + ('r' * (len(treatments) + 2))

    lines = [
        r'\begin{table}[t]',
        r'\centering',
        r'\small',
        f'\\begin{{tabular}}{{{column_spec}}}',
        r'\toprule',
        ' & '.join([
            'Capabilities',
            'Encoding',
            'Live.',
            'Pending',
            *(_latex_escape(text) for text in treatment_labels),
            '$N$',
            'Failures',
        ]) + r' \\',
        r'\midrule',
    ]

    for key in sorted(grouped):
        rows_by_ordering = grouped[key]
        capability_file, encoding, liveness, pending = key
        n_total = 0
        failures_total = 0
        values = []
        for treatment in treatments:
            row = rows_by_ordering.get(treatment, {})
            if stat == 'mean':
                values.append(_format_mean_number(row, metric, places=1))
            else:
                values.append(_format_number(row.get(metric_column), precision))
            n_total += int(float(row.get('n') or 0))
            failures_total += int(float(row.get('failures') or 0))

        line = ' & '.join([
            _capability_label(capability_file),
            _latex_escape(encoding),
            _latex_escape(liveness),
            _latex_escape(pending),
            *values,
            str(n_total),
            str(failures_total),
        ])
        lines.append(f'{line} \\\\')

    lines.extend([
        r'\bottomrule',
        r'\end{tabular}',
        f'\\caption{{{_latex_escape(caption)}}}',
        f'\\label{{{_latex_escape(label)}}}',
        r'\end{table}',
        '',
    ])
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    return output_path


# Paper-table rows: (LaTeX row label, summary metric, kind). 'int' uses one
# decimal place for count means/stdevs unless all values are the same integer;
# 'time1' uses one decimal in the table's selected time unit; 'time3' keeps
# three decimal places. All timing rows use 'time3': at Coffee's scale,
# 'time1' silently rounds real sub-0.05ms measurements down to a
# misleading "0.0", so every timing row uses the precision that can't lose
# that signal regardless of which domain's scale it's rendering (a
# three-decimal value at Two-Rivers/PyRoboSim/Crazyflie scale is merely more
# digits than strictly needed, never misleading). 'time1' is kept as an
# available kind for any future row where that tradeoff is actually wanted.
# 'text' takes the summary field's value verbatim. Labels mirror the paper's
# Coffee Tables I/II, with Extraction (previously commented out) and Auditing
# (new) timing rows now active. The seven timing rows are ordered to match
# the pipeline sequence from Fig. 2 (pipeline-overview): Generate Specs, Well
# Separation, Realizability, Extraction, Auditing, Realize HFSM, Overall.
PAPER_TABLE_ROW_SPECS = [
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Well\\Separated}}',
        'well_separated_label',
        'text',
    ),
    (r'\textbf{Realizable}', 'realizable', 'text'),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{FlexBE HFSM\\Realized}}',
        'flexbe_hfsm_realized',
        'text',
    ),
    (r'\textbf{$\left|AP_I\right|$}', 'ap_i', 'int'),
    (r'\textbf{$\left|AP_O\right|$}', 'ap_o', 'int'),
    (r'\textbf{$\left|\varphi_i^a\right|$}', 'env_init_count', 'int'),
    (r'\textbf{$\left|\varphi_i^g\right|$}', 'sys_init_count', 'int'),
    (r'\textbf{$\left|\varphi_s^a\right|$}', 'env_trans_count', 'int'),
    (r'\textbf{$\left|\varphi_s^g\right|$}', 'sys_trans_count', 'int'),
    (r'\textbf{$\left|\varphi_l^a\right|$}', 'env_liveness_count', 'int'),
    (r'\textbf{$\left|\varphi_l^g\right|$}', 'sys_liveness_count', 'int'),
    (r'\rule{0pt}{4ex}\textbf{\shortstack{CUDD Live\\BDD Nodes}}', 'cudd_live_nodes', 'int'),
    (r'\rule{0pt}{4ex}\textbf{\shortstack{CUDD Peak\\BDD Nodes}}', 'cudd_peak_nodes', 'int'),
    (r'\textbf{\textbar{}Slugs SM\textbar}', 'slugs_sm_size', 'int'),
    (r'\textbf{\textbar{}Reduced\textbar}', 'reduced_sm_size', 'int'),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Generate\\Specs (%s)}}',
        'generate_specs_time_s',
        'time3',
    ),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Well Separation\\(%s)}}',
        'well_separation_analyzer_time_s',
        'time3',
    ),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Realizability\\(%s)}}',
        'realizability_time_s',
        'time3',
    ),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Extraction\\(%s)}}',
        'extraction_time_s',
        'time3',
    ),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Auditing\\(%s)}}',
        'auditor_time_s',
        'time3',
    ),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Realize\\HFSM (%s)}}',
        'realize_hfsm_time_s',
        'time3',
    ),
    (
        r'\rule{0pt}{4ex}\textbf{\shortstack{Overall\\(%s)}}',
        'overall_pipeline_time_s',
        'time3',
    ),
]


# The Discussion-section "*_summary.tex" row subset -- verified against every
# domain's committed summary table (Coffee/Two-Rivers/PyRoboSim P0+P1/Crazyflie
# all use exactly this set, in this order). --compact filters PAPER_TABLE_ROW_SPECS
# down to these metric keys; the Appendix-facing full table (the default) keeps
# every row.
COMPACT_METRICS = frozenset({
    'well_separated_label',
    'realizable',
    'flexbe_hfsm_realized',
    'ap_i',
    'ap_o',
    'slugs_sm_size',
    'reduced_sm_size',
    'realizability_time_s',
    'realize_hfsm_time_s',
    'overall_pipeline_time_s',
})


def _paper_time_unit_for_run(run_dir: Path, requested: str = 'auto') -> str:
    """Return the paper-table time unit for a run directory."""
    if requested != 'auto':
        return requested
    text = str(run_dir).lower()
    if any(token in text for token in ('pyrobosim', 'drone', 'crazyflie')):
        return 's'
    return 'ms'


def _summary_row_key(row: dict[str, str]) -> tuple[str, ...]:
    """Return the stable key used to compare summary rows across runs."""
    return tuple(row.get(field, '') for field in SUMMARY_KEYS)


def compare_summary_means(
    baseline_path: Path,
    current_path: Path,
    factor: float = 10.0,
) -> list[str]:
    """Return warnings for matching summary means that changed by a large factor."""
    if not baseline_path.exists() or not current_path.exists():
        return []
    return _compare_summary_mean_rows(
        _read_rows(baseline_path),
        _read_rows(current_path),
        factor,
    )


def _compare_summary_mean_rows(
    baseline_rows: list[dict[str, str]],
    current_rows: list[dict[str, str]],
    factor: float,
) -> list[str]:
    """Return warnings for large mean changes in two summary row sets."""
    baseline_by_key = {
        _summary_row_key(row): row
        for row in baseline_rows
    }
    current_by_key = {
        _summary_row_key(row): row
        for row in current_rows
    }
    warnings = []
    for key in sorted(set(baseline_by_key) & set(current_by_key)):
        baseline = baseline_by_key[key]
        current = current_by_key[key]
        for column in sorted(set(baseline) & set(current)):
            if not column.endswith('_mean'):
                continue
            old = _float_value(baseline.get(column))
            new = _float_value(current.get(column))
            if old is None or new is None or old <= 0 or new <= 0:
                continue
            ratio = max(old / new, new / old)
            if ratio >= factor:
                warnings.append(
                    f'{column} changed by {ratio:.1f}x for {key}: '
                    f'{old:g} -> {new:g}'
                )
    return warnings


def _paper_rows(time_unit: str, compact: bool = False) -> list[tuple[str, str, str]]:
    """
    Return paper-table rows with timing labels specialized to the unit.

    `compact` restricts to COMPACT_METRICS (the Discussion-section summary-table
    row subset) instead of every PAPER_TABLE_ROW_SPECS row.
    """
    return [
        (label % time_unit if '%s' in label else label, metric, kind)
        for label, metric, kind in PAPER_TABLE_ROW_SPECS
        if not compact or metric in COMPACT_METRICS
    ]


# A column_indicator like '2FP' or '1S' -> (digit, liveness letter, pending flag).
# Bare labels that don't match (e.g. a hand-written baseline's 'Full', 'MoveOnly',
# or Coffee's '1') aren't scenario cells and sort before anything that does.
_INDICATOR_RE = re.compile(r'^(\d+)([A-Za-z]+?)(P)?$')

# Explicit ordering for specific baseline (non-scenario) labels that must sort ahead of
# their alphabetic position -- PyRoboSim's smaller move-only baseline is listed before
# its full-spec baseline despite "Full" < "MoveOnly" alphabetically. Labels not listed
# here (Coffee's '1', PyRoboSim's 'FullP1', ...) keep sorting alphabetically among
# themselves and after any label listed here.
_BASELINE_ORDER_OVERRIDE = {'MoveOnly': 0, 'Full': 1}


def _indicator_sort_key(indicator: str):
    """
    Return a sort key for ordering paper-table columns.

    Reproduces the column order every case-study table actually uses:
    non-scenario labels (baselines) first -- in `_BASELINE_ORDER_OVERRIDE`
    order where listed, then their own alphabetical order -- then scenario
    cells grouped by pending (no-P before P), then liveness (S before F),
    then encoding/capability digit. Derived entirely from the indicator
    string -- no per-demo table needed.
    """
    match = _INDICATOR_RE.match(indicator)
    if not match:
        return (0, _BASELINE_ORDER_OVERRIDE.get(indicator, 1), indicator)
    digit, liveness, pending = match.groups()
    liveness_rank = {'S': 0, 'F': 1}.get(liveness.upper(), 2)
    return (1, 1 if pending else 0, liveness_rank, int(digit), indicator)


def _paper_row_identity(row: dict[str, str]) -> str:
    """Return a compact label for duplicate paper-table source rows."""
    capability = _capability_label(row.get('capability_file', ''))
    encoding = row.get('encoding', '')
    liveness = row.get('liveness', '')
    pending = row.get('pending', '')
    return f'{capability}/{encoding}/{liveness}/pending={pending}'


def _time_scale(time_unit: str) -> Decimal:
    """Return multiplier from seconds to the displayed table time unit."""
    return Decimal('1000') if time_unit == 'ms' else Decimal('1')


def _paper_cell(
    row: dict[str, str],
    metric: str,
    kind: str,
    precision: int,
    time_unit: str = 'ms',
) -> str:
    """Format one summary-mean value for the paper table."""
    if kind == 'time1':
        return _format_mean_number(
            row,
            metric,
            scale=float(_time_scale(time_unit)),
            places=1,
        )
    if kind == 'time3':
        # Routed through the same integer-collapse-aware helper as 'time1'
        # (just at `precision` places instead of 1), so a mean that happens
        # to be an identical whole number across every trial still renders
        # as a clean "600" rather than "600.000" -- only means with real
        # fractional variance get the extra decimal places.
        return _format_mean_number(
            row,
            metric,
            scale=float(_time_scale(time_unit)),
            places=precision,
        )
    if kind == 'text':
        return _latex_escape(row.get(metric) or '--')
    return _format_mean_number(row, metric, places=1)


def _paper_stdev_cell(
    row: dict[str, str],
    metric: str,
    kind: str,
    time_unit: str = 'ms',
) -> str:
    """Format one summary-stdev value for a paper-table dispersion companion row."""
    if kind == 'time3':
        return _format_stdev_number(
            row,
            metric,
            scale=float(_time_scale(time_unit)),
            places=3,
        )
    if kind == 'time1':
        return _format_stdev_number(
            row,
            metric,
            scale=float(_time_scale(time_unit)),
            places=1,
        )
    return _format_stdev_number(row, metric, places=1)


def write_paper_table(
    summary_path: Path,
    output_path: Path,
    encoding: str | None = None,
    policy: str = 'threshold_250',
    ordering: str = 'random',
    precision: int = 3,
    caption: str | None = None,
    label: str | None = None,
    include_baseline: bool | None = None,
    time_unit: str = 'ms',
    compact: bool = False,
) -> Path:
    """
    Write a paper-style results table from a summary CSV.

    Rows are the reported metrics (Realizable, AP/formula counts, BDD nodes,
    SM sizes, and pipeline timing in ``time_unit``). Pass ``compact=True`` to
    restrict to the Discussion-section summary-table row subset (see
    ``COMPACT_METRICS``) instead of every row -- the full row set is meant for
    the Appendix-facing detail table.
    Columns are every distinct ``column_indicator`` present at the chosen
    ``ordering``/``policy`` treatment (each summary row's matrix generator
    supplies this label directly, e.g. ``2FP`` or ``Full`` -- see
    e.g. ``coffee_matrix.py``/``pyrobosim_matrix.py``), ordered by
    `_indicator_sort_key` -- this reproduces the observed column order in
    every case-study table without per-demo logic. Each value is the mean
    over the ``ordering`` distribution under the chosen reordering ``policy``.

    Pass ``encoding`` to additionally filter to one encoding and optionally
    fold in baseline (``full_spec``) rows via ``include_baseline`` -- Coffee's
    convention of one table per encoding (Table I one-hot, Table II
    enumerated), with the hand-written baseline as column ``1`` in Table I
    only. Leave ``encoding`` as ``None`` (the default) for a single combined
    table with every encoding's columns side by side -- the convention used
    by PyRoboSim, Two-Rivers, and drone_demo, where the column_indicator's
    leading digit already distinguishes encoding.
    """
    rows = _read_rows(summary_path)
    if include_baseline is None:
        include_baseline = encoding is None or encoding == 'one-hot'

    selected: dict[str, dict[str, str]] = {}
    duplicates: dict[str, list[str]] = {}
    for row in rows:
        if _reordering_policy(row) != policy or row.get('ordering_mode', '') != ordering:
            continue
        if encoding is not None:
            is_baseline = row.get('encoding') == 'full_spec'
            if is_baseline:
                if not include_baseline:
                    continue
            elif row.get('encoding') != encoding:
                continue
        indicator = (row.get('column_indicator') or '').strip()
        if not indicator:
            continue
        if indicator in selected:
            duplicates.setdefault(indicator, [
                _paper_row_identity(selected[indicator]),
            ]).append(_paper_row_identity(row))
        selected[indicator] = row
    if duplicates:
        duplicate_text = '; '.join(
            f'{indicator}: {", ".join(values)}'
            for indicator, values in sorted(duplicates.items())
        )
        table_desc = 'combined table' if encoding is None else f"'{encoding}' table"
        suggestion = (
            'Use --split-encoding-tables for Coffee or choose unique '
            'column_indicator values.' if encoding is None
            else 'Choose unique column_indicator values for this encoding.'
        )
        raise ValueError(
            f'Paper table has duplicate column_indicator rows for the {table_desc} '
            f'({duplicate_text}). {suggestion}'
        )
    columns = [
        (indicator, selected[indicator])
        for indicator in sorted(selected, key=_indicator_sort_key)
    ]

    if encoding is not None:
        kind_name = 'One-hot Labeling' if encoding == 'one-hot' else 'Enumerated Capabilities'
        caption = caption or (
            f'Coffee Synthesis Demonstration with {kind_name} '
            f'({_policy_label(policy)}, mean over {ordering} orderings).'
        )
        label = label or f'tbl:coffee-{"1hot" if encoding == "one-hot" else "enumerated"}-results'
    else:
        caption = caption or (
            f'Synthesis results ({_policy_label(policy)}, mean over {ordering} orderings).'
        )
        label = label or 'tbl:results'
    column_spec = '|c|' + 'r|' * len(columns)

    lines = [
        r'\begin{table}[htbp]',
        r'\centering',
        f'\\caption{{{caption}}}',
        f'\\label{{{label}}}',
        r'\renewcommand{\arraystretch}{1.4}',
        r'\setlength{\tabcolsep}{3pt}',
        f'\\begin{{tabular}}{{{column_spec}}}',
        r'\hline',
        ' & '.join(['', *(f'\\textbf{{{lab}}}' for lab, _ in columns)]) + r' \\',
        r'\hline',
    ]
    for row_label, metric, kind in _paper_rows(time_unit, compact=compact):
        cells = [
            _paper_cell(row, metric, kind, precision, time_unit)
            for _, row in columns
        ]
        lines.append(' & '.join([row_label, *cells]) + r' \\')
        lines.append(r'\hline')
        if kind in ('int', 'time1', 'time3'):
            # Dispersion companion row, directly beneath its mean row -- only
            # emitted when at least one column actually has spread to show
            # (n > 1 and not every trial gave the identical value).
            stdev_cells = [
                _paper_stdev_cell(row, metric, kind, time_unit)
                for _, row in columns
            ]
            if any(stdev_cells):
                lines.append(' & '.join(['', *stdev_cells]) + r' \\')
                lines.append(r'\hline')
    lines.extend([r'\end{tabular}', r'\end{table}', ''])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    return output_path


def _safe_slug(value: str) -> str:
    """Return a filesystem-safe slug."""
    return re.sub(r'[^A-Za-z0-9]+', '_', value).strip('_').lower()


def _unique_values(rows: list[dict[str, str]], field: str) -> list[str]:
    """Return sorted unique non-empty values for a CSV field."""
    return sorted({row.get(field, '') for row in rows if row.get(field, '')})


def _plot_title(capability_file, liveness, pending, metric):
    """Return a readable plot title."""
    return (
        f'{Path(capability_file).stem}, '
        f'liveness={liveness}, pending={pending}, '
        f'metric={metric}'
    )


def _plot_panel_title(capability_file, liveness, pending):
    """Return a compact title for one subplot panel."""
    pending_label = 'pending' if str(pending).lower() == 'true' else 'no pending'
    return (
        f'{Path(capability_file).stem}\n'
        f'{liveness}, {pending_label}'
    )


def _facet_rows(rows, facet_keys, facet):
    """Return rows matching a facet tuple."""
    return [
        row for row in rows
        if tuple(row.get(field, '') for field in facet_keys) == facet
    ]


def _plot_groups(rows, encodings):
    """Return horizontal plot groups as (reordering policy, encoding, position)."""
    groups = []
    position = 1
    for policy, _ in _policy_values(rows):
        for encoding in encodings:
            groups.append((
                policy,
                encoding,
                position,
            ))
            position += 1
        position += 1
    return groups


def _reorder_group_centers(groups):
    """Return centered x positions for reordering policy group labels."""
    centers = []
    labels = dict(PLOT_POLICY_ORDER)
    for reorder_value, reorder_label in [
        (policy, labels.get(policy, policy.replace('_', ' ')))
        for policy in dict.fromkeys(group[0] for group in groups)
    ]:
        positions = [
            position for group_reorder, _, position in groups
            if group_reorder == reorder_value
        ]
        if positions:
            centers.append((sum(positions) / len(positions), reorder_label))
    return centers


def _random_values_by_group(rows, groups, metric):
    """Return random-ordering metric values grouped by policy and encoding."""
    return [
        [
            value for value in (
                _float_value(row.get(metric))
                for row in rows
                if row.get('encoding') == encoding
                and row.get('ordering_mode') == 'random'
                and _reordering_policy(row) == reorder_value
            )
            if value is not None
        ]
        for reorder_value, encoding, _ in groups
    ]


def _random_mean_by_group(rows, groups, metric):
    """Return random-ordering metric means grouped by policy and encoding."""
    values_by_group = _random_values_by_group(rows, groups, metric)
    return [
        statistics.mean(values) if values else None
        for values in values_by_group
    ]


def _fixed_values_by_mode(rows, groups, metric, ordering_mode):
    """Return x/y coordinates for a fixed ordering mode overlay."""
    xs = []
    ys = []
    for reorder_value, encoding, position in groups:
        mode_values = [
            value for value in (
                _float_value(row.get(metric))
                for row in rows
                if row.get('encoding') == encoding
                and row.get('ordering_mode') == ordering_mode
                and _reordering_policy(row) == reorder_value
            )
            if value is not None
        ]
        if mode_values:
            xs.append(position)
            ys.append(mode_values[0])
    return xs, ys


def _metric_values(rows, metric):
    """Return positive numeric metric values for log-scale plotting."""
    return [
        value for value in (_float_value(row.get(metric)) for row in rows)
        if value is not None and value > 0
    ]


def _log_ylim(rows, metric):
    """Return explicit padded log-scale y-limits for a set of rows."""
    values = _metric_values(rows, metric)
    if not values:
        return None

    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        return min_value / 1.12, max_value * 1.12

    padding = (max_value / min_value) ** 0.08
    return min_value / padding, max_value * padding


def _summary_grid_ylim(rows, metric, share_y):
    """Return the y-range for a summary grid or None for per-panel ranges."""
    if not share_y:
        return None
    return _log_ylim(rows, metric)


def _draw_ordering_panel(ax, rows, encodings, metric, marker_by_mode,
                         show_legend=False):
    """Draw one ordering-distribution panel on an existing axes."""
    groups = _plot_groups(rows, encodings)
    random_values = _random_values_by_group(rows, groups, metric)
    if not any(random_values):
        return None

    ax.boxplot(
        random_values,
        positions=[position for _, _, position in groups],
        widths=0.55,
        showfliers=True,
        patch_artist=True,
        boxprops={'facecolor': '#d7e8f7', 'edgecolor': '#2d5f87'},
        medianprops={'color': '#111111', 'linewidth': 1.4},
        whiskerprops={'color': '#2d5f87'},
        capprops={'color': '#2d5f87'},
        flierprops={
            'marker': 'o',
            'markerfacecolor': 'none',
            'markeredgecolor': '#111111',
            'markersize': 4.0,
            'linestyle': 'none',
        },
    )
    ax.set_xticks(
        [position for _, _, position in groups],
        [encoding for _, encoding, _ in groups],
    )
    ax.tick_params(axis='x', labelrotation=25)
    for center, label in _reorder_group_centers(groups):
        ax.text(
            center,
            -0.30,
            label,
            ha='center',
            va='top',
            transform=ax.get_xaxis_transform(),
            clip_on=False,
        )

    handles = []
    for ordering_mode in FIXED_ORDERING_MODES:
        marker, color = marker_by_mode[ordering_mode]
        xs, ys = _fixed_values_by_mode(rows, groups, metric, ordering_mode)
        if xs:
            handle = ax.scatter(
                xs,
                ys,
                marker=marker,
                color=color,
                label=ordering_mode,
                zorder=3,
            )
            handles.append(handle)

    ax.set_yscale('log')
    ax.grid(axis='y', linestyle=':', linewidth=0.6)
    if show_legend and handles:
        ax.legend(handles=_legend_handles(marker_by_mode), loc='best')
    return handles


def _draw_time_overlay(ax, rows, encodings, time_metric, time_ylim=None,
                       show_ylabel=False):
    """Draw random-ordering mean time on a right-side y axis."""
    groups = _plot_groups(rows, encodings)
    time_means = _random_mean_by_group(rows, groups, time_metric)
    points = [
        (position, value)
        for (_, _, position), value in zip(groups, time_means)
        if value is not None and value > 0
    ]
    if not points:
        return None

    time_ax = ax.twinx()
    xs, ys = zip(*points)
    line = time_ax.plot(
        xs,
        ys,
        color='#8c4b19',
        marker='D',
        markersize=3.5,
        linewidth=1.2,
        linestyle='--',
        label='mean pipeline time',
        zorder=2,
    )[0]
    time_ax.set_yscale('log')
    if time_ylim:
        time_ax.set_ylim(*time_ylim)
    if show_ylabel:
        time_ax.set_ylabel(time_metric.replace('_', ' '))
    else:
        time_ax.tick_params(axis='y', labelright=False)
    time_ax.grid(False)
    return line


def _rightmost_panel_indexes(panel_count: int, ncols: int) -> set[int]:
    """Return panel indexes that should carry right-side y-axis labels."""
    indexes = set()
    for row_start in range(0, panel_count, ncols):
        indexes.add(min(row_start + ncols - 1, panel_count - 1))
    return indexes


def _legend_handles(marker_by_mode):
    """Return stable legend handles for random and fixed ordering modes."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    handles = [
        Patch(
            facecolor='#d7e8f7',
            edgecolor='#2d5f87',
            label='random',
        )
    ]
    for ordering_mode in FIXED_ORDERING_MODES:
        marker, color = marker_by_mode[ordering_mode]
        handles.append(
            Line2D(
                [0],
                [0],
                marker=marker,
                color='none',
                markerfacecolor=color,
                markeredgecolor=color,
                linestyle='none',
                label=ordering_mode,
            )
        )
    handles.append(
        Line2D(
            [0],
            [0],
            marker='o',
            color='none',
            markerfacecolor='none',
            markeredgecolor='#111111',
            linestyle='none',
            label='random outlier',
        )
    )
    return handles


def _ordering_facets(rows):
    """Return facet keys and sorted facet values used by ordering plots."""
    facet_keys = [
        'capability_file',
        'liveness',
        'pending',
    ]
    facets = sorted({
        tuple(row.get(field, '') for field in facet_keys)
        for row in rows
    })
    return facet_keys, facets


def _marker_by_mode():
    """Return fixed-ordering marker styles."""
    return {
        'alphabetic': ('o', 'tab:blue'),
        'domain': ('^', 'tab:green'),
    }


def write_ordering_plots(
    master_path: Path,
    output_dir: Path,
    metric: str = 'cudd_peak_nodes',
    formats: tuple[str, ...] = ('pdf', 'png'),
) -> list[Path]:
    """Write ordering distribution plots from the raw master CSV."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            'matplotlib is required for plot generation. Install it or run with '
            '--no-plots.'
        ) from exc

    rows = _read_rows(master_path)
    if rows and metric not in rows[0]:
        raise ValueError(f"Master file '{master_path}' does not contain '{metric}'.")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    facet_keys, facets = _ordering_facets(rows)
    marker_by_mode = _marker_by_mode()

    for facet in facets:
        facet_rows = _facet_rows(rows, facet_keys, facet)
        encodings = _unique_values(facet_rows, 'encoding')
        if not encodings:
            continue

        fig, ax = plt.subplots(figsize=(max(5.0, 1.5 * len(encodings)), 3.8))
        handles = _draw_ordering_panel(
            ax,
            facet_rows,
            encodings,
            metric,
            marker_by_mode,
            show_legend=True,
        )
        if handles is None:
            plt.close(fig)
            continue

        ylim = _log_ylim(facet_rows, metric)
        if ylim:
            ax.set_ylim(*ylim)

        capability_file, liveness, pending = facet
        ax.set_title(
            _plot_title(capability_file, liveness, pending, metric)
        )
        # No set_xlabel: the rotated encoding ticks and the reorder-policy
        # group labels drawn by _draw_ordering_panel already occupy the
        # space directly below the axis, and a default-positioned xlabel
        # collides with the group labels at typical figure heights.
        ax.set_ylabel(metric.replace('_', ' '))
        ax.set_yscale('log')
        ax.grid(axis='y', linestyle=':', linewidth=0.6)
        fig.tight_layout(rect=(0, 0.08, 1, 1))

        stem = '__'.join([
            Path(capability_file).stem,
            f'liveness_{_safe_slug(liveness)}',
            f'pending_{_safe_slug(pending)}',
            _safe_slug(metric),
        ])
        for fmt in formats:
            path = output_dir / f'{stem}.{fmt}'
            fig.savefig(path, bbox_inches='tight')
            written.append(path)
        plt.close(fig)

    return written


def write_ordering_summary_plot(
    master_path: Path,
    output_dir: Path,
    metric: str = 'cudd_peak_nodes',
    time_metric: str = 'overall_pipeline_time_s',
    include_time_axis: bool = True,
    formats: tuple[str, ...] = ('pdf', 'png'),
    output_stem: str = 'ordering_summary',
    max_cols: int = 4,
    split_by: str = '',
    split_share_y: bool = True,
) -> list[Path]:
    """Write one multi-panel ordering summary figure suitable for a paper."""
    rows = _read_rows(master_path)
    if rows and metric not in rows[0]:
        raise ValueError(f"Master file '{master_path}' does not contain '{metric}'.")
    if split_by and rows and split_by not in rows[0]:
        raise ValueError(f"Master file '{master_path}' does not contain '{split_by}'.")

    written = _write_ordering_summary_plot_from_rows(
        rows,
        output_dir,
        metric,
        formats,
        output_stem,
        max_cols,
        share_y=True,
        time_metric=time_metric,
        include_time_axis=include_time_axis,
    )

    if split_by:
        split_values = _unique_values(rows, split_by)
        for value in split_values:
            split_rows = [row for row in rows if row.get(split_by, '') == value]
            split_stem = f'{output_stem}_{_safe_slug(split_by)}_{_safe_slug(value)}'
            written.extend(
                _write_ordering_summary_plot_from_rows(
                    split_rows,
                    output_dir,
                    metric,
                    formats,
                    split_stem,
                    max_cols,
                    title_suffix=_capability_label(value).replace(r'\_', '_'),
                    share_y=split_share_y,
                    time_metric=time_metric,
                    include_time_axis=include_time_axis,
                )
            )
        return written

    return written


def _write_ordering_summary_plot_from_rows(
    rows: list[dict[str, str]],
    output_dir: Path,
    metric: str,
    formats: tuple[str, ...],
    output_stem: str,
    max_cols: int,
    title_suffix: str = '',
    share_y: bool = True,
    time_metric: str = 'overall_pipeline_time_s',
    include_time_axis: bool = True,
) -> list[Path]:
    """Write one multi-panel ordering summary figure from already-filtered rows."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            'matplotlib is required for plot generation. Install it or run with '
            '--no-plots.'
        ) from exc

    facet_keys, facets = _ordering_facets(rows)
    panels = []
    all_encodings = _unique_values(rows, 'encoding')
    for facet in facets:
        facet_rows = _facet_rows(rows, facet_keys, facet)
        encodings = _unique_values(facet_rows, 'encoding') or all_encodings
        groups = _plot_groups(facet_rows, encodings)
        if any(_random_values_by_group(facet_rows, groups, metric)):
            panels.append((facet, facet_rows, encodings))

    if not panels:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    ncols = min(max_cols, len(panels))
    nrows = (len(panels) + ncols - 1) // ncols
    fig_width = max(7.0, 2.7 * ncols)
    fig_height = max(3.8, 2.7 * nrows + 0.9)
    figure_ylim = _summary_grid_ylim(rows, metric, share_y)
    use_time_axis = include_time_axis and rows and time_metric in rows[0]
    figure_time_ylim = (
        _summary_grid_ylim(rows, time_metric, share_y)
        if use_time_axis else None
    )
    with plt.rc_context({
        'font.size': 8,
        'axes.titlesize': 8,
        'axes.labelsize': 8,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'legend.fontsize': 7,
        'figure.titlesize': 10,
    }):
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(fig_width, fig_height),
            sharey=share_y,
            squeeze=False,
        )
        marker_by_mode = _marker_by_mode()
        right_label_indexes = _rightmost_panel_indexes(len(panels), ncols)

        for index, (facet, facet_rows, encodings) in enumerate(panels):
            ax = axes[index // ncols][index % ncols]
            _draw_ordering_panel(
                ax,
                facet_rows,
                encodings,
                metric,
                marker_by_mode,
            )
            panel_ylim = figure_ylim if share_y else _log_ylim(facet_rows, metric)
            if panel_ylim:
                ax.set_ylim(*panel_ylim)
            if use_time_axis:
                panel_time_ylim = (
                    figure_time_ylim if share_y else _log_ylim(facet_rows, time_metric)
                )
                _draw_time_overlay(
                    ax,
                    facet_rows,
                    encodings,
                    time_metric,
                    time_ylim=panel_time_ylim,
                    show_ylabel=index in right_label_indexes,
                )
            capability_file, liveness, pending = facet
            ax.set_title(
                _plot_panel_title(
                    capability_file,
                    liveness,
                    pending,
                )
            )
            if index % ncols == 0:
                ax.set_ylabel(metric.replace('_', ' '))

        for index in range(len(panels), nrows * ncols):
            axes[index // ncols][index % ncols].axis('off')

        legend_handles = _legend_handles(marker_by_mode)
        if use_time_axis:
            from matplotlib.lines import Line2D

            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    color='#8c4b19',
                    marker='D',
                    markersize=3.5,
                    linewidth=1.2,
                    linestyle='--',
                    label='mean pipeline time',
                )
            )
        fig.legend(
            legend_handles,
            [handle.get_label() for handle in legend_handles],
            loc='upper center',
            bbox_to_anchor=(0.5, 0.945),
            ncol=len(legend_handles),
            frameon=False,
        )
        title = f'{metric.replace("_", " ")} by variable ordering'
        if title_suffix:
            title = f'{title}: {title_suffix}'
        fig.suptitle(title, y=0.99)
        fig.tight_layout(rect=(0, 0.04, 1, 0.88))

        written = []
        for fmt in formats:
            path = output_dir / f'{output_stem}_{_safe_slug(metric)}.{fmt}'
            fig.savefig(path, bbox_inches='tight')
            written.append(path)
        plt.close(fig)
    return written


def _scatter_style(row):
    """Return color/marker for timing scatter rows."""
    colors = {
        'alphabetic': 'tab:blue',
        'domain': 'tab:green',
        'random': '#6f6f6f',
    }
    markers = {
        'off': 'x',
        'auto': 'o',
        'threshold_250': '^',
    }
    marker = markers.get(_reordering_policy(row), 's')
    return colors.get(row.get('ordering_mode'), 'tab:gray'), marker


def write_complexity_time_plot(
    master_path: Path,
    output_dir: Path,
    x_metric: str = 'cudd_peak_nodes',
    time_metrics: tuple[tuple[str, str], ...] = tuple(TIME_METRICS),
    formats: tuple[str, ...] = ('pdf', 'png'),
    output_stem: str = 'complexity_time',
) -> list[Path]:
    """Write a scatter plot relating BDD size to clock-time metrics."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            'matplotlib is required for plot generation. Install it or run with '
            '--no-plots.'
        ) from exc

    rows = _read_rows(master_path)
    if rows and x_metric not in rows[0]:
        raise ValueError(f"Master file '{master_path}' does not contain '{x_metric}'.")

    usable_time_metrics = [
        (field, label) for field, label in time_metrics
        if rows and field in rows[0]
    ]
    if not usable_time_metrics:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({
        'font.size': 8,
        'axes.titlesize': 8,
        'axes.labelsize': 8,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'legend.fontsize': 7,
        'figure.titlesize': 10,
    }):
        fig, axes = plt.subplots(
            1,
            len(usable_time_metrics),
            figsize=(4.2 * len(usable_time_metrics), 3.2),
            squeeze=False,
        )
        legend_items = {}
        for ax, (time_metric, time_label) in zip(axes[0], usable_time_metrics):
            grouped_points: dict[tuple[str, str, str], tuple[list[float], list[float]]] = {}
            for row in rows:
                x_value = _float_value(row.get(x_metric))
                y_value = _float_value(row.get(time_metric))
                if x_value is None or y_value is None or x_value <= 0 or y_value <= 0:
                    continue
                color, marker = _scatter_style(row)
                label = (
                    f"{row.get('ordering_mode', 'unknown')}, "
                    f"{_reordering_policy(row).replace('_', ' ')}"
                )
                xs, ys = grouped_points.setdefault((label, color, marker), ([], []))
                xs.append(x_value)
                ys.append(y_value)

            for (label, color, marker), (xs, ys) in grouped_points.items():
                artist = ax.scatter(
                    xs,
                    ys,
                    color=color,
                    marker=marker,
                    alpha=0.55,
                    s=18,
                    linewidths=0.8,
                    label=label,
                    rasterized=True,
                )
                legend_items.setdefault(label, artist)
            ax.set_xscale('log')
            ax.set_yscale('log')
            ax.set_xlabel(x_metric.replace('_', ' '))
            ax.set_ylabel(time_label)
            ax.grid(axis='both', linestyle=':', linewidth=0.6)

        if legend_items:
            fig.legend(
                legend_items.values(),
                legend_items.keys(),
                loc='upper center',
                bbox_to_anchor=(0.5, 0.98),
                ncol=min(3, len(legend_items)),
                frameon=False,
            )
        fig.suptitle('Clock time versus peak BDD nodes', y=1.05)
        fig.tight_layout(rect=(0, 0, 1, 0.86))

        written = []
        for fmt in formats:
            path = output_dir / f'{output_stem}_{_safe_slug(x_metric)}.{fmt}'
            fig.savefig(path, bbox_inches='tight')
            written.append(path)
        plt.close(fig)
    return written


def postprocess(args) -> tuple[Path, Path, list[Path]]:
    """Run requested post-processing steps."""
    run_dir = Path(args.run_dir).expanduser()
    master_path = Path(args.master).expanduser() if args.master else run_dir / 'master.csv'
    summary_path = (
        Path(args.summary).expanduser() if args.summary else run_dir / 'summary.csv'
    )
    compare_summary_path = (
        Path(args.compare_summary).expanduser()
        if args.compare_summary else None
    )
    baseline_summary_rows = None
    if (
        compare_summary_path is not None
        and compare_summary_path.exists()
        and compare_summary_path.resolve() == summary_path.resolve()
    ):
        baseline_summary_rows = _read_rows(compare_summary_path)

    if args.refresh_summary or not summary_path.exists():
        write_summary(master_path, summary_path)

    if compare_summary_path is not None:
        if baseline_summary_rows is None:
            warnings = compare_summary_means(
                compare_summary_path,
                summary_path,
                factor=args.summary_regression_factor,
            )
        else:
            warnings = _compare_summary_mean_rows(
                baseline_summary_rows,
                _read_rows(summary_path),
                args.summary_regression_factor,
            )
        for warning in warnings:
            print(f'WARNING: summary mean regression check: {warning}', file=sys.stderr)

    table_path = Path()
    if not args.no_table:
        table_path = (
            Path(args.table_out).expanduser()
            if args.table_out else
            run_dir / 'tables' / f'{_safe_slug(args.metric)}_{args.stat}.tex'
        )
        write_latex_table(
            summary_path,
            table_path,
            metric=args.metric,
            stat=args.stat,
            precision=args.precision,
            caption=args.caption,
            label=args.label,
        )

    if not args.no_paper_tables:
        tables_dir = run_dir / 'tables'
        paper_time_unit = _paper_time_unit_for_run(run_dir, args.paper_time_unit)
        # Suffix distinguishes --compact output from the default (full) output so
        # generating both from the same run-dir (as publish_paper_tables.sh does,
        # once per mode) doesn't have the second run silently overwrite the first.
        compact_suffix = '_compact' if args.compact else ''
        if args.split_encoding_tables:
            split_prefix = args.split_prefix or _safe_slug(run_dir.name)
            for enc in ('one-hot', 'enumerated'):
                paper_path = write_paper_table(
                    summary_path,
                    tables_dir / f'{split_prefix}_{_safe_slug(enc)}{compact_suffix}_results.tex',
                    encoding=enc,
                    policy=args.table_policy,
                    ordering=args.table_ordering,
                    time_unit=paper_time_unit,
                    compact=args.compact,
                )
                print(f'Wrote paper table: {paper_path}', flush=True)
        else:
            paper_path = write_paper_table(
                summary_path,
                tables_dir / f'{_safe_slug(run_dir.name)}{compact_suffix}_results.tex',
                policy=args.table_policy,
                ordering=args.table_ordering,
                time_unit=paper_time_unit,
                compact=args.compact,
            )
            print(f'Wrote paper table: {paper_path}', flush=True)

    plot_paths: list[Path] = []
    if not args.no_plots:
        plot_dir = (
            Path(args.plot_dir).expanduser()
            if args.plot_dir else run_dir / 'plots'
        )
        formats = tuple(args.plot_format or ['pdf', 'png'])
        if not args.summary_plot_only:
            plot_paths.extend(
                write_ordering_plots(
                    master_path,
                    plot_dir,
                    metric=args.metric,
                    formats=formats,
                )
            )
        if args.summary_plot or args.summary_plot_only:
            plot_paths.extend(
                write_ordering_summary_plot(
                    master_path,
                    plot_dir,
                    metric=args.metric,
                    time_metric=args.summary_time_metric,
                    include_time_axis=not args.summary_plot_no_time_axis,
                    formats=formats,
                    output_stem=args.summary_plot_stem,
                    max_cols=args.summary_plot_cols,
                    split_share_y=not args.summary_plot_split_independent_y,
                    split_by=(
                        ''
                        if args.summary_plot_split == 'none' else args.summary_plot_split
                    ),
                )
            )
        if not args.no_time_plot:
            plot_paths.extend(
                write_complexity_time_plot(
                    master_path,
                    plot_dir,
                    x_metric=args.time_x_metric,
                    formats=formats,
                )
            )

    return summary_path, table_path, plot_paths


def main():
    """Run the experiment post-processing CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, help='Directory containing master.csv.')
    parser.add_argument('--master', default='', help='Override master CSV path.')
    parser.add_argument('--summary', default='', help='Override summary CSV path.')
    parser.add_argument(
        '--refresh-summary',
        action='store_true',
        help='Regenerate summary.csv before writing tables/plots.',
    )
    parser.add_argument('--metric', default='cudd_peak_nodes', help='Metric to report.')
    parser.add_argument(
        '--stat',
        default='mean',
        choices=['mean', 'min', 'max', 'stdev'],
        help='Summary statistic for the LaTeX table.',
    )
    parser.add_argument('--precision', type=int, default=2, help='Decimal places.')
    parser.add_argument('--caption', default='', help='Optional LaTeX caption.')
    parser.add_argument('--label', default='', help='Optional LaTeX label.')
    parser.add_argument('--table-out', default='', help='Output .tex path.')
    parser.add_argument(
        '--no-paper-tables',
        action='store_true',
        help='Skip the paper-style results table (.tex) generation.',
    )
    parser.add_argument(
        '--split-encoding-tables',
        action='store_true',
        help="Write one table per encoding (Coffee's Table I one-hot / Table II "
             'enumerated convention, output as <prefix>_one-hot_results.tex / '
             '<prefix>_enumerated_results.tex, prefix from --split-prefix) '
             'instead of a single combined table with every column_indicator '
             'side by side (the PyRoboSim/Two-Rivers/drone_demo convention).',
    )
    parser.add_argument(
        '--split-prefix',
        default='',
        help='Filename prefix for --split-encoding-tables output (default: '
             'the run directory name, slugified). Coffee callers should pass '
             "'coffee' explicitly to keep its existing coffee_one-hot_results.tex "
             '/ coffee_enumerated_results.tex filenames, since its run '
             "directory name (coffee_full_rerun) doesn't match.",
    )
    parser.add_argument(
        '--table-policy',
        default='threshold_250',
        help='Reordering policy whose values fill the paper table cells.',
    )
    parser.add_argument(
        '--table-ordering',
        default='random',
        help='Ordering mode whose per-cell mean fills the paper table.',
    )
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Restrict the paper table to the Discussion-section row subset '
             '(Well Separated, Realizable, FlexBE HFSM Realized, |AP_I|, '
             '|AP_O|, |Slugs SM|, |Reduced|, Realizability, Realize HFSM, '
             'Overall) instead of every PAPER_TABLE_ROW_SPECS row -- the '
             'condensed table convention used by each domain-specific '
             '*_summary.tex in the paper (full detail stays in the '
             'Appendix-facing default).',
    )
    parser.add_argument(
        '--paper-time-unit',
        default='auto',
        choices=['auto', 'ms', 's'],
        help=(
            'Time unit for paper-style timing rows. auto uses seconds for '
            'PyRoboSim/drone/Crazyflie runs and milliseconds otherwise.'
        ),
    )
    parser.add_argument(
        '--compare-summary',
        default='',
        help=(
            'Optional baseline summary.csv to compare against after regeneration; '
            'large per-column mean changes are printed as warnings.'
        ),
    )
    parser.add_argument(
        '--summary-regression-factor',
        type=float,
        default=10.0,
        help='Warn when a matching summary mean changes by at least this factor.',
    )
    parser.add_argument('--plot-dir', default='', help='Directory for generated plots.')
    parser.add_argument(
        '--plot-format',
        action='append',
        default=None,
        help='Plot file format; repeat for multiple formats.',
    )
    parser.add_argument(
        '--summary-plot',
        action='store_true',
        help='Also write one multi-panel summary plot for paper figures.',
    )
    parser.add_argument(
        '--summary-plot-only',
        action='store_true',
        help='Write only the multi-panel summary plot, not per-facet plots.',
    )
    parser.add_argument(
        '--summary-plot-stem',
        default='ordering_summary',
        help='Filename stem for the multi-panel summary plot.',
    )
    parser.add_argument(
        '--summary-plot-cols',
        type=int,
        default=4,
        help='Maximum subplot columns in the multi-panel summary plot.',
    )
    parser.add_argument(
        '--summary-plot-split',
        default='capability_file',
        choices=['none', 'capability_file'],
        help='Also write one summary plot per selected field value.',
    )
    parser.add_argument(
        '--summary-plot-split-independent-y',
        action='store_true',
        help='Use independent y axes inside each split summary plot.',
    )
    parser.add_argument(
        '--summary-time-metric',
        default='overall_pipeline_time_s',
        help='Right-axis timing metric for summary plots.',
    )
    parser.add_argument(
        '--summary-plot-no-time-axis',
        action='store_true',
        help='Do not overlay timing data on the summary plot right axis.',
    )
    parser.add_argument(
        '--no-time-plot',
        action='store_true',
        help='Skip clock-time versus BDD-size scatter plots.',
    )
    parser.add_argument(
        '--time-x-metric',
        default='cudd_peak_nodes',
        help='X-axis metric for clock-time scatter plots.',
    )
    parser.add_argument('--no-table', action='store_true', help='Skip LaTeX output.')
    parser.add_argument('--no-plots', action='store_true', help='Skip plot output.')
    summary_path, table_path, plot_paths = postprocess(parser.parse_args())

    print(f"Wrote summary CSV '{summary_path}'", flush=True)
    if table_path:
        print(f"Wrote LaTeX table '{table_path}'", flush=True)
    for plot_path in plot_paths:
        print(f"Wrote plot '{plot_path}'", flush=True)


if __name__ == '__main__':
    main()
