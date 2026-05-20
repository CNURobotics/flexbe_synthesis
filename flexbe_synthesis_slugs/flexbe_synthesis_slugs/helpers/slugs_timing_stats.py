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
Run Slugs repeatedly and report average synthesis metrics.

For a given BASE name, this collects stderr logs with Slugs stats, parses them
via flexbe_synthesis_slugs.helpers.slugs_stats_helper, and reports averages.

Expected inputs and outputs:

  SLUGSIN = f"{BASE}.slugsin"
  JSON    = f"{BASE}_{i}.json"
  ERR     = f"{BASE}_{i}.err"

Example commands include:

  python slugs_timing_stats.py coffee_out -n 10
  python slugs_timing_stats.py /path/to/coffee_out -n 30 --slugs-bin /path/to/slugs

This script assumes `parse_slugs_log(path)` returns either a dataclass-like
object with attributes or a dict of metrics.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any

from flexbe_synthesis_slugs.helpers.slugs_stats_helper import parse_slugs_log

# --------------------------
# Utilities
# --------------------------


def _metrics_obj_to_dict(m: Any) -> dict[str, Any]:
    """Accept dict or dataclass-like object; return a plain dict."""
    if m is None:
        return {}
    if isinstance(m, dict):
        return m
    if is_dataclass(m):
        return asdict(m)
    # Fallback: best-effort attribute extraction
    out: dict[str, Any] = {}
    for k in dir(m):
        if k.startswith('_'):
            continue
        try:
            v = getattr(m, k)
        except Exception:
            continue
        # Skip methods / callables
        if callable(v):
            continue
        out[k] = v
    return out


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _summarize_numeric(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {'n': 0, 'mean': None, 'stdev': None, 'min': None, 'max': None}
    if len(values) == 1:
        v = float(values[0])
        return {'n': 1, 'mean': v, 'stdev': 0.0, 'min': v, 'max': v}
    return {
        'n': len(values),
        'mean': float(statistics.mean(values)),
        'stdev': float(statistics.stdev(values)),
        'min': float(min(values)),
        'max': float(max(values)),
    }


def _print_block(title: str) -> None:
    print('\n' + '=' * 80)
    print(title)
    print('=' * 80)


def _format_stat_line(name: str, stats: dict[str, float | None], units: str = '') -> str:
    n = stats['n']
    mean = stats['mean']
    stdev = stats['stdev']
    vmin = stats['min']
    vmax = stats['max']

    if mean is None:
        return f'{name:<32}  n={n:<3}  (no data)'
    u = f' {units}' if units else ''
    return (
        f'{name:<32}  n={n:<3}  mean={mean:.6g}{u}  '
        f'stdev={stdev:.6g}{u}  min={vmin:.6g}{u}  max={vmax:.6g}{u}'
    )


# --------------------------
# Core run loop
# --------------------------

DEFAULT_FIELDS_OF_INTEREST: list[tuple[str, str]] = [
    # (field_name_in_metrics, units)
    ('realizable', ''),
    ('ap_i', ''),
    ('ap_o', ''),
    ('cudd_var_count', ''),
    ('synthesis_time_s', 's'),
    ('explicit_extraction_time_s', 's'),
    ('cudd_peak_nodes', 'nodes'),
    ('cudd_live_nodes', 'nodes'),
    ('winning_region_dag_size', ''),
    ('strategy_bdd_dag_size', ''),
    ('explicit_states', ''),
    ('explicit_transitions', ''),
    ('max_out_degree', ''),
    ('avg_out_degree', ''),
    ('controller_complexity', ''),
    ('normalized_symbolic_complexity', ''),
]


def run_slugs_once(
    slugs_bin: str,
    slugsin: Path,
    json_out: Path,
    err_out: Path,
    extra_args: list[str],
    cwd: Path | None = None,
) -> int:
    """
    Run Slugs once.

    Command: slugs <slugsin> --explicitStrategy --jsonOutput
    stdout -> json_out
    stderr -> err_out
    returns process return code.
    """
    cmd = [slugs_bin, str(slugsin), '--explicitStrategy', '--jsonOutput'] + extra_args

    json_out.parent.mkdir(parents=True, exist_ok=True)
    err_out.parent.mkdir(parents=True, exist_ok=True)

    with json_out.open('wb') as f_out, err_out.open('wb') as f_err:
        proc = subprocess.run(
            cmd,
            stdout=f_out,
            stderr=f_err,
            cwd=str(cwd) if cwd else None,
        )
    return int(proc.returncode)


def main() -> None:
    """Run the Slugs timing statistics CLI."""
    ap = argparse.ArgumentParser(description='Run Slugs N times and average key synthesis/controller metrics.')
    ap.add_argument('base', help='Base name (path without extension). SLUGSIN = BASE + .slugsin')
    ap.add_argument('-n', '--num-runs', type=int, default=10, help='Number of Slugs runs (default: 10)')
    ap.add_argument('--slugs-bin', default='slugs', help='Path to slugs binary (default: slugs on PATH)')
    ap.add_argument('--out-dir', default=None, help='Directory for outputs; default is BASE directory')
    ap.add_argument('--keep-json', action='store_true', help='Keep per-run JSON outputs (default: keep)')
    ap.add_argument('--rm-json', action='store_true', help='Remove per-run JSON outputs after parsing')
    ap.add_argument('--extra-arg', action='append', default=[], help='Extra arg to pass to slugs (repeatable)')
    ap.add_argument('--save-raw-metrics', default=None, help='Write per-run parsed metrics to this JSON file')
    args = ap.parse_args()

    if args.num_runs <= 0:
        print('ERROR: --num-runs must be >= 1')
        sys.exit(2)

    base = Path(args.base)
    slugsin = base.with_suffix('.slugsin')
    if not slugsin.exists():
        print(f'ERROR: SLUGSIN not found: {slugsin}')
        sys.exit(2)

    out_dir = Path(args.out_dir) if args.out_dir else base.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect per-run parsed metrics
    parsed_runs: list[dict[str, Any]] = []
    return_codes: list[int] = []

    _print_block(f'Running Slugs N={args.num_runs} times')
    print(f'SLUGSIN: {slugsin}')
    print(f'slugs:   {args.slugs_bin}')
    print(f'out_dir: {out_dir}')
    if args.extra_arg:
        print(f'extra:   {args.extra_arg}')

    for i in range(args.num_runs):
        err_out = out_dir / f'{base.name}_{i}.err'
        json_out = out_dir / f'{base.name}_{i}.json'

        rc = run_slugs_once(
            slugs_bin=args.slugs_bin,
            slugsin=slugsin,
            json_out=json_out,
            err_out=err_out,
            extra_args=args.extra_arg,
            cwd=base.parent,
        )
        return_codes.append(rc)

        # Parse stderr stats via helper
        try:
            m_obj = parse_slugs_log(err_out)  # your helper should parse the text log
            m = _metrics_obj_to_dict(m_obj)
        except Exception as e:
            m = {'file': str(err_out), 'parse_error': str(e)}

        m['run_index'] = i
        m['return_code'] = rc
        m['err_file'] = str(err_out)
        m['json_file'] = str(json_out)
        parsed_runs.append(m)

        # Optionally remove JSON outputs
        if args.rm_json:
            try:
                json_out.unlink(missing_ok=True)
            except Exception:
                pass

        # Lightweight progress
        realizable = m.get('realizable', None)
        synth_t = m.get('synthesis_time_s', None)
        peak = m.get('cudd_peak_nodes', None)
        print(f'  run {i:02d}: rc={rc} realizable={realizable} synth={synth_t} peak_nodes={peak}')

    # Save raw per-run parsed metrics if requested
    if args.save_raw_metrics:
        Path(args.save_raw_metrics).write_text(json.dumps(parsed_runs, indent=2))

    _print_block('Return codes')
    rc_stats = _summarize_numeric([float(rc) for rc in return_codes])
    print(_format_stat_line('return_code', rc_stats, units=''))

    # Aggregate numeric fields of interest
    _print_block('Averages (key fields)')

    # Also report how many runs are realizable/unrealizable if present
    realizable_vals = [r.get('realizable', None) for r in parsed_runs]
    realizable_true = sum(1 for v in realizable_vals if v is True)
    realizable_false = sum(1 for v in realizable_vals if v is False)
    realizable_none = sum(1 for v in realizable_vals if v is None)
    print(f'realizable counts: True={realizable_true}, False={realizable_false}, None={realizable_none}')

    for field, units in DEFAULT_FIELDS_OF_INTEREST:
        # realizable is non-numeric; we already printed counts
        if field == 'realizable':
            continue
        vals: list[float] = []
        for r in parsed_runs:
            v = r.get(field, None)
            if _is_number(v):
                vals.append(float(v))
        stats = _summarize_numeric(vals)
        print(_format_stat_line(field, stats, units=units))

    # Composite metric sanity: if your helper doesn't compute these, you can compute them here.
    # We'll compute "controller_complexity" and "normalized_symbolic_complexity" if missing.
    for r in parsed_runs:
        if r.get('controller_complexity') is None:
            s = r.get('explicit_states')
            t = r.get('explicit_transitions')
            if _is_number(s) and _is_number(t):
                r['controller_complexity'] = int(s) + int(t)
        if r.get('normalized_symbolic_complexity') is None:
            sb = r.get('strategy_bdd_dag_size')
            wr = r.get('winning_region_dag_size')
            if _is_number(sb) and _is_number(wr) and float(wr) != 0.0:
                r['normalized_symbolic_complexity'] = float(sb) / float(wr)

    # Print composite metric summaries explicitly (useful for papers)
    _print_block('Suggested composite metrics (explicit)')
    for field, units in [
        ('controller_complexity', ''),
        ('normalized_symbolic_complexity', ''),
        ('cudd_peak_nodes', 'nodes'),
        ('synthesis_time_s', 's'),
        ('explicit_extraction_time_s', 's'),
    ]:
        vals = [float(r[field]) for r in parsed_runs if _is_number(r.get(field))]
        stats = _summarize_numeric(vals)
        print(_format_stat_line(field, stats, units=units))

    print('\nDone.')
    print(f'Per-run logs: {out_dir}/{base.name}_{{0..{args.num_runs - 1}}}.err')
    if not args.rm_json:
        print(f'Per-run JSON: {out_dir}/{base.name}_{{0..{args.num_runs - 1}}}.json')
    if args.save_raw_metrics:
        print(f'Per-run parsed metrics: {args.save_raw_metrics}')


if __name__ == '__main__':
    main()
