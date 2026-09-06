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

"""Generate Coffee experiment matrix YAML for the generic batch harness."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

# Coffee capability set -> the paper's leading column digit (2 = base, 3 = extended).
_CAP_DIGIT = {
    'coffee_capabilities.yaml': '2',
    'coffee_capabilities_extended.yaml': '3',
}


def repo_root() -> Path:
    """Return repository root from this source file."""
    return Path(__file__).resolve().parents[3]


def coffee_root() -> Path:
    """Return the in-repo Coffee example directory."""
    return repo_root() / 'flexbe_synthesis_examples' / 'example' / 'coffee_maker'


def _reordering_treatments():
    """
    Return Coffee CUDD reordering policies.

    The `auto` policy (Slugs default sifting) was dropped: prior-run data showed
    it is effectively identical to `off` at these BDD sizes (default sifting
    rarely fires), while `threshold_250` never lost to it and often won 3-4x. We
    keep `off` as the no-reorder floor/control and `threshold_250` as the tuned
    policy.
    """
    return [
        {
            'reordering_enabled': False,
            'reordering_threshold': None,
        },
        {
            'reordering_enabled': True,
            'reordering_threshold': 250,
        },
    ]


def ordering_rows(full=False, random_seeds=40):
    """Return ordering treatments for Coffee."""
    rows = [
        {
            'ordering_mode': ordering_mode,
            'ordering_seed': None,
            **reordering,
        }
        for ordering_mode in ('alphabetic', 'domain')
        for reordering in _reordering_treatments()
    ]
    if full:
        rows.extend(
            {
                'ordering_mode': 'random',
                'ordering_seed': seed,
                **reordering,
            }
            for reordering in _reordering_treatments()
            for seed in range(random_seeds)
        )
    else:
        rows.extend(
            {
                'ordering_mode': 'random',
                'ordering_seed': 0,
                **reordering,
            }
            for reordering in _reordering_treatments()
        )
    return rows


def _full_spec_row(root, ordering, n_trials):
    """
    Build one hand-written full-spec baseline row (paper Table I column 1).

    The loaded spec is already complete, so `full_spec: True` tells the harness
    to skip the capability/liveness/pending generation and only bind the request
    goal (mirroring full_spec_processes_def.yaml). It still goes through the same
    compiler and synthesizer, so the variable-ordering and CUDD-reordering sweep
    applies. Sentinel encoding/liveness values keep it a distinct cell in
    master.csv, the summary, and the plots; encoding/liveness/pending are not
    swept for it. It loads coffee_capabilities.yaml only to satisfy request-spec
    binding, matching coffee_full_spec_example.launch.py.
    """
    return {
        'example': 'coffee',
        'system_name': 'coffee_maker',
        'spec_name': 'CoffeeSM',
        'spec_path': str(root / 'specs' / 'coffee_full_spec.yaml'),
        'capabilities_path': str(root / 'capabilities' / 'coffee_capabilities.yaml'),
        'encoding': 'full_spec',
        'liveness': 'na',
        'pending': False,
        'column_indicator': '1',
        'full_spec': True,
        'initial_conditions': ['bd_a'],
        'goals': ['br_c'],
        'sm_outcomes': [],
        'n_trials': n_trials,
        **ordering,
    }


def build_matrix(full=False, random_seeds=40, smoke=False, n_trials=5):
    """Build Coffee matrix rows."""
    root = coffee_root()
    spec_path = root / 'specs' / 'coffee_demo_capabilities_spec.yaml'
    capability_files = [
        root / 'capabilities' / 'coffee_capabilities.yaml',
        root / 'capabilities' / 'coffee_capabilities_extended.yaml',
    ]
    rows = []
    for capability_file in capability_files:
        digit = _CAP_DIGIT[capability_file.name]
        for encoding in ('one-hot', 'enumerated'):
            for liveness in ('S', 'F'):
                for pending in (False, True):
                    column_indicator = f"{digit}{liveness}{'P' if pending else ''}"
                    for ordering in ordering_rows(full=full, random_seeds=random_seeds):
                        rows.append({
                            'example': 'coffee',
                            'system_name': 'coffee_maker',
                            'spec_name': 'CoffeeSM',
                            'spec_path': str(spec_path),
                            'capabilities_path': str(capability_file),
                            'encoding': encoding,
                            'liveness': liveness,
                            'pending': pending,
                            'column_indicator': column_indicator,
                            'initial_conditions': ['bd_a'],
                            'goals': ['br_c'],
                            'sm_outcomes': [],
                            'n_trials': n_trials,
                            **ordering,
                        })
                        if smoke:
                            # Also exercise the hand-written baseline build path.
                            rows.append(_full_spec_row(root, ordering, n_trials))
                            return {'rows': rows}

    # Hand-written full-spec baseline (paper Table I column 1): one extra combo
    # swept across the same orderings and reordering policies as the 16
    # capability combos, but with no encoding/liveness/pending axes.
    for ordering in ordering_rows(full=full, random_seeds=random_seeds):
        rows.append(_full_spec_row(root, ordering, n_trials))
    return {'rows': rows}


def main():
    """Run the Coffee matrix generator CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', help='Matrix YAML output path.')
    parser.add_argument(
        '--full',
        action='store_true',
        help='Generate the full 1428-row Coffee ordering matrix '
             '(16 capability combos + 1 hand-written baseline, off + '
             'threshold_250 policies, 40 random seeds).',
    )
    parser.add_argument(
        '--smoke',
        action='store_true',
        help='Generate one representative Coffee row for terminal smoke testing.',
    )
    parser.add_argument(
        '--random-seeds',
        type=int,
        default=40,
        help='Number of random ordering seeds for --full.',
    )
    parser.add_argument(
        '--n-trials',
        type=int,
        default=5,
        help='Exact repeated trials per matrix row.',
    )
    args = parser.parse_args()

    matrix = build_matrix(
        full=args.full,
        random_seeds=args.random_seeds,
        smoke=args.smoke,
        n_trials=args.n_trials,
    )
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(matrix, sort_keys=False), encoding='utf-8')
    print(f"Wrote {len(matrix['rows'])} Coffee matrix row(s) to '{output}'")


if __name__ == '__main__':
    main()
