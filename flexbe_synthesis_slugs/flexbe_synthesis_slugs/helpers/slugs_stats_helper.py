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
Parse Slugs stdout/stderr logs and extract key metrics.

This is intended for Slugs stdout/stderr logs when comparing spec-writing
styles. It also computes a couple suggested composite metrics.

Example commands include:

  python slugs_stats_helper.py demo.err
  python slugs_stats_helper.py run1.err run2.err --csv out.csv
  python slugs_stats_helper.py logs/*.err --json out.json

The parser is tolerant of extra lines or different ordering. If a metric is not
found, it is left as None in JSON/CSV.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

# ----------------------------
# Parsing helpers
# ----------------------------

_RE_FLOAT = re.compile(r'([-+]?\d+(?:\.\d+)?)')
_RE_INT = re.compile(r'([-+]?\d+)')
_RE_BYTES = re.compile(r'([-+]?\d+)\s*bytes\b', re.IGNORECASE)


def _find_float(s: str) -> float | None:
    m = _RE_FLOAT.search(s)
    return float(m.group(1)) if m else None


def _find_int(s: str) -> int | None:
    m = _RE_INT.search(s)
    return int(m.group(1)) if m else None


def _find_bytes(s: str) -> int | None:
    m = _RE_BYTES.search(s)
    return int(m.group(1)) if m else None


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ----------------------------
# Metrics schema
# ----------------------------

@dataclass
class SlugsRunMetrics:
    """Store parsed Slugs metrics for one run."""

    file: str

    realizable: bool | None = None

    # Counts / structure
    ap_i: int | None = None
    ap_o: int | None = None
    env_trans_count: int | None = None
    sys_trans_count: int | None = None
    env_liveness_count: int | None = None
    sys_liveness_count: int | None = None

    # Timing
    synthesis_time_s: float | None = None
    explicit_extraction_time_s: float | None = None

    # Symbolic complexity
    cudd_live_nodes: int | None = None
    cudd_peak_nodes: int | None = None
    cudd_var_count: int | None = None
    winning_region_dag_size: int | None = None
    strategy_bdd_dag_size: int | None = None

    # Memory (optional but often handy)
    cudd_memory_in_use_bytes: int | None = None

    # Controller (explicit strategy) complexity
    explicit_states: int | None = None
    explicit_transitions: int | None = None
    max_out_degree: int | None = None
    avg_out_degree: float | None = None

    # Composite metrics
    controller_complexity: int | None = None
    normalized_symbolic_complexity: float | None = None  # strategy_bdd / winning_region

    def finalize(self) -> None:
        """Compute derived metrics after parsing raw fields."""
        # ControllerComplexity = states + transitions
        if self.explicit_states is not None and self.explicit_transitions is not None:
            self.controller_complexity = self.explicit_states + self.explicit_transitions

        # NormalizedSymbolicComplexity = StrategyBDDSize / WinningRegionSize
        if self.strategy_bdd_dag_size is not None and self.winning_region_dag_size is not None:
            self.normalized_symbolic_complexity = _safe_div(
                float(self.strategy_bdd_dag_size),
                float(self.winning_region_dag_size),
            )


# ----------------------------
# Main parser
# ----------------------------

# Maps "label fragments" to parsers + field names
# The log format you showed uses:
#   "  - KEY: VALUE"
# and:
#   "  2) Winning-region DAG size: 50"
#   "Timing:  - ...: 0.035222 s"
_FIELD_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r'\bRESULT:\s+Specification is realizable\b', re.IGNORECASE),
        'realizable',
        'bool_true',
    ),
    (
        re.compile(r'\bRESULT:\s+Specification is unrealizable\b', re.IGNORECASE),
        'realizable',
        'bool_false',
    ),
    (re.compile(r'\bAP_I\b.*?:', re.IGNORECASE), 'ap_i', 'int'),
    (re.compile(r'\bAP_O\b.*?:', re.IGNORECASE), 'ap_o', 'int'),
    (re.compile(r'\|\s*ENV_TRANS\s*\|', re.IGNORECASE), 'env_trans_count', 'int'),
    (re.compile(r'\|\s*SYS_TRANS\s*\|', re.IGNORECASE), 'sys_trans_count', 'int'),
    (re.compile(r'\|\s*ENV_LIVENESS\s*\|', re.IGNORECASE), 'env_liveness_count', 'int'),
    (re.compile(r'\|\s*SYS_LIVENESS\s*\|', re.IGNORECASE), 'sys_liveness_count', 'int'),
    (re.compile(r'Synthesis time\b.*?:', re.IGNORECASE), 'synthesis_time_s', 'float'),
    (
        re.compile(r'Explicit strategy extraction time\b.*?:', re.IGNORECASE),
        'explicit_extraction_time_s',
        'float',
    ),
    (re.compile(r'\bCUDD live node count\b.*?:', re.IGNORECASE), 'cudd_live_nodes', 'int'),
    (re.compile(r'\bCUDD peak node count\b.*?:', re.IGNORECASE), 'cudd_peak_nodes', 'int'),
    (re.compile(r'\bCUDD manager var count\b.*?:', re.IGNORECASE), 'cudd_var_count', 'int'),
    (re.compile(r'\bMemory in use\b.*?:', re.IGNORECASE), 'cudd_memory_in_use_bytes', 'bytes'),
    (
        re.compile(r'\bCUDD memory in use\b.*?:', re.IGNORECASE),
        'cudd_memory_in_use_bytes',
        'bytes',
    ),
    (
        re.compile(r'\bWinning-region DAG size\b.*?:', re.IGNORECASE),
        'winning_region_dag_size',
        'int',
    ),
    (re.compile(r'\bStrategy BDD DAG size\b.*?:', re.IGNORECASE), 'strategy_bdd_dag_size', 'int'),
    (re.compile(r'\bExplicit states\b.*?:', re.IGNORECASE), 'explicit_states', 'int'),
    (re.compile(r'\bExplicit transitions\b.*?:', re.IGNORECASE), 'explicit_transitions', 'int'),
    (re.compile(r'\bMax out-degree\b.*?:', re.IGNORECASE), 'max_out_degree', 'int'),
    (re.compile(r'\bAvg out-degree\b.*?:', re.IGNORECASE), 'avg_out_degree', 'float'),
]


def parse_slugs_log(path: Path) -> SlugsRunMetrics:
    """Parse a Slugs log file into a metrics object."""
    text = path.read_text(errors='replace').splitlines()
    m = SlugsRunMetrics(file=str(path))

    for line in text:
        line_stripped = line.strip()

        for pat, field, kind in _FIELD_PATTERNS:
            if not pat.search(line_stripped):
                continue

            if kind == 'bool_true':
                setattr(m, field, True)
                break
            if kind == 'bool_false':
                setattr(m, field, False)
                break
            if kind == 'int':
                val = _find_int(line_stripped)
                if val is not None:
                    setattr(m, field, val)
                break
            if kind == 'float':
                val = _find_float(line_stripped)
                if val is not None:
                    setattr(m, field, val)
                break
            if kind == 'bytes':
                val = _find_bytes(line_stripped)
                if val is None:
                    # fallback if it looks like "...: 42547112" without "bytes"
                    val = _find_int(line_stripped)
                if val is not None:
                    setattr(m, field, val)
                break

    m.finalize()
    return m


# ----------------------------
# Output
# ----------------------------

def _to_row(d: dict[str, Any], header: list[str]) -> list[Any]:
    return [d.get(h, None) for h in header]


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Write parsed metric rows to a CSV file."""
    if not rows:
        raise ValueError('No rows to write.')
    header = sorted(rows[0].keys())
    with out_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(_to_row(r, header))


def write_json(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Write parsed metric rows to a JSON file."""
    out_path.write_text(json.dumps(rows, indent=2))


# ----------------------------
# CLI
# ----------------------------

def main() -> None:
    """Run the Slugs metrics extraction CLI."""
    ap = argparse.ArgumentParser(description='Extract key Slugs synthesis metrics from log text files.')
    ap.add_argument('files', nargs='+', help='One or more Slugs log files (stdout/stderr dumps).')
    ap.add_argument('--csv', type=str, default=None, help='Write extracted metrics to CSV at this path.')
    ap.add_argument('--json', type=str, default=None, help='Write extracted metrics to JSON at this path.')
    ap.add_argument('--pretty', action='store_true', help='Print a human-friendly summary per file.')
    args = ap.parse_args()

    metrics: list[SlugsRunMetrics] = []
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            raise FileNotFoundError(fp)
        metrics.append(parse_slugs_log(p))

    rows = [asdict(m) for m in metrics]

    if args.csv:
        write_csv(rows, Path(args.csv))
    if args.json:
        write_json(rows, Path(args.json))

    # Default behavior: print concise JSON to stdout if no output requested
    if not args.csv and not args.json and not args.pretty:
        print(json.dumps(rows, indent=2))
        return

    if args.pretty:
        for m in metrics:
            print('=' * 80)
            print(m.file)
            print(f'  realizable: {m.realizable}')
            print(f'  vars: AP_I={m.ap_i}, AP_O={m.ap_o}, BDD_vars={m.cudd_var_count}')
            print(f'  time: synthesis={m.synthesis_time_s}s, extract={m.explicit_extraction_time_s}s')
            print(f'  symbolic: peak_nodes={m.cudd_peak_nodes}, live_nodes={m.cudd_live_nodes}')
            print(
                f'           win_region={m.winning_region_dag_size}, '
                f'strategy_bdd={m.strategy_bdd_dag_size}'
            )
            print(
                f'  controller: states={m.explicit_states}, trans={m.explicit_transitions}, '
                f'max_out={m.max_out_degree}, avg_out={m.avg_out_degree}'
            )
            print(
                f'  composite: controller_complexity={m.controller_complexity}, '
                f'normalized_symbolic={m.normalized_symbolic_complexity}'
            )


if __name__ == '__main__':
    main()
