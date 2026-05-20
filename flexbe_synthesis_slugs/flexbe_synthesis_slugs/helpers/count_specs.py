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
Count and validate sections in Slugs specification files.

The parser accepts both `.structuredslugs` and `.slugsin` files. It counts the
number of formulas or propositions in each `[SECTION]`, reports duplicate lines,
and rejects invalid input/output declarations such as primed variables.

This module is used by the `slugs_count_specs` pipeline process and can also be
run from the command line:

  ros2 run flexbe_synthesis_slugs count_slugs_specs path/to/spec.structuredslugs
"""

import argparse
import json
from pathlib import Path

import yaml


def parse_slugs_specs(filename):
    """Parse a Slugs specification file into section-name to line-list blocks."""
    blocks = {}
    current_block = None

    with open(filename, encoding='utf-8') as spec_file:
        for line_number, raw in enumerate(spec_file, start=1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue

            if line.startswith('[') and line.endswith(']'):
                current_block = line.strip('[]')
                blocks[current_block] = []
                continue

            if not current_block:
                continue

            data = line.split('#')[0].strip()
            if not data:
                continue

            if data in blocks[current_block]:
                print(
                    f'\033[31m"{data}" is duplicated in "{current_block}"!\033[0m',
                    flush=True,
                )

            if current_block in ('INPUT', 'OUTPUT'):
                if "'" in data:
                    raise ValueError(
                        f'"{data}" contains a prime in "{current_block}" '
                        f'at line {line_number}: <{line}>'
                    )

                if data in blocks.get('INPUT', []):
                    raise ValueError(
                        f'"{data}" is duplicated in "INPUT" at line '
                        f'{line_number}: <{line}>'
                    )

                if data in blocks.get('OUTPUT', []):
                    raise ValueError(
                        f'"{data}" is duplicated in "OUTPUT" at line '
                        f'{line_number}: <{line}>'
                    )

            blocks[current_block].append(data)

    return blocks


def count_specs(blocks):
    """Return the number of entries in each parsed Slugs specification section."""
    counts = {}
    for key, value in blocks.items():
        try:
            counts[key] = len(value)
        except TypeError:
            counts[key] = 0

    return counts


def resolve_spec_path(path_text):
    """Return an existing spec path, appending `.structuredslugs` when omitted."""
    path = Path(path_text).expanduser()
    if path.suffix:
        return path
    return path.with_suffix('.structuredslugs')


def count_spec_file(path_text):
    """Parse and count one Slugs spec file."""
    path = resolve_spec_path(path_text)
    blocks = parse_slugs_specs(path)
    return path, count_specs(blocks)


def build_argument_parser():
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            'Count sections in .structuredslugs or .slugsin files and validate '
            'INPUT/OUTPUT declarations.'
        ),
    )
    parser.add_argument(
        'spec',
        nargs='+',
        help=(
            'Slugs spec file to inspect. If no extension is provided, '
            '.structuredslugs is appended.'
        ),
    )
    parser.add_argument(
        '--format',
        choices=('text', 'yaml', 'json'),
        default='text',
        help='Output format for counts (default: text).',
    )
    return parser


def print_text_counts(results):
    """Print section counts in a compact human-readable format."""
    for path, counts in results:
        print(f"Counts for '{path}':")
        for section, count in counts.items():
            print(f'  {section:20s} {count:4d}')


def structured_counts(results):
    """Return counts as a path-keyed dictionary for structured output formats."""
    if len(results) == 1:
        return results[0][1]
    return {str(path): counts for path, counts in results}


def main(argv=None):
    """Run the Slugs section counter command-line tool."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    results = []
    for spec in args.spec:
        try:
            results.append(count_spec_file(spec))
        except (OSError, ValueError) as exc:
            parser.exit(1, f'error: {exc}\n')

    if args.format == 'json':
        print(json.dumps(structured_counts(results), indent=2, sort_keys=True))
    elif args.format == 'yaml':
        print(yaml.safe_dump(structured_counts(results), sort_keys=True), end='')
    else:
        print_text_counts(results)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
