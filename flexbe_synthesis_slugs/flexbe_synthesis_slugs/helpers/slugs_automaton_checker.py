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
Inspect and validate raw Slugs JSON automata.

This command-line helper is intended for backend debugging after a Slugs-backed
synthesis run. Slugs writes a JSON strategy automaton, while FlexBE Synthesis
uses `SlugsAutomaton` objects with named input/output variables. This tool
loads the JSON output, finds or reads the matching `.structuredslugs` variable
declarations, expands compact integer variables such as `capability:0...N`,
filters internal memory outputs, and prints the converted automaton state by
state.

Typical usage after a synthesis request has generated artifacts under
`FLEXBE_SYNTHESIS_HOME` or `~/.flexbe_synthesis`:

  ros2 run flexbe_synthesis_slugs check_slugs_automaton --spec-name coffee_maker

You can also pass explicit files:

  ros2 run flexbe_synthesis_slugs check_slugs_automaton \
    path/to/spec.json --structuredslugs path/to/spec.structuredslugs

By default the checker searches the current directory and synthesis home. Add
`--search-package PACKAGE_NAME` when you want to inspect artifacts installed in a
package share directory.

The tool exits nonzero when required files or variable declarations cannot be
found. It prints an inspection report to stdout; it does not write a replacement
automaton file.
"""

import argparse
import json
from pathlib import Path

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_slugs.helpers.binary_variables import expand_binary_variables
from flexbe_synthesis_slugs.helpers.slugs_automaton import (
    SlugsAutomaton,
    SlugsAutomatonState,
)

DEFAULT_SEARCH_PACKAGES = ()


class SlugsAutomatonChecker:
    """Build and print `SlugsAutomaton` objects from synthesizer JSON outputs."""

    def automaton_state_from_node_info(self, name, info, n_in_vars, mem_idxs):
        """Generate an automaton state from synthesized node info."""
        print(
            f"creating state '{name}' with {n_in_vars} input vars and "
            f"{len(info['state'])} bools..."
        )
        state = SlugsAutomatonState(name=str(name))

        int_bools = info['state'][n_in_vars:]
        state.output_valuation = [bool(val) for val in int_bools]

        # Keep only non-memory output propositions.
        state.output_valuation = [
            value
            for idx, value in enumerate(state.output_valuation)
            if idx not in mem_idxs
        ]
        print(f'   output valuation = {state.output_valuation}')

        int_bools = info['state'][:n_in_vars]
        state.input_valuation = [bool(val) for val in int_bools]
        print(f'    input valuation = {state.input_valuation}')

        state.transitions = [str(t) for t in info['trans']]
        print(f'   transitions = {state.transitions}')
        state.rank = info['rank']

        return state

    def gen_automaton_msg_from_json(
        self,
        json_file,
        input_vars,
        output_vars,
        activation_tag='_a',
        outcome_tags=('_c', '_f'),
        outcome_names=('completed', 'failed'),
        sm_outcomes=('finished', 'failed'),
    ):
        """Generate an automaton message from synthesized JSON automaton file."""
        with open(json_file, encoding='utf-8') as data_file:
            data = json.load(data_file)

        mem_idxs = [idx for idx, output in enumerate(output_vars) if output.endswith('_m')]
        print(f' mem_idxs = {mem_idxs}')

        automaton = SlugsAutomaton()
        binary_outputs = self.expand_binary(output_vars)
        automaton.output_variables = [
            output
            for idx, output in enumerate(output_vars)
            if idx not in mem_idxs
        ]
        print(
            f' Automaton Outputs {len(automaton.output_variables)}\n'
            f'    output vars = {automaton.output_variables}\n'
            f'    binary ({binary_outputs})'
        )

        binary_inputs = self.expand_binary(input_vars)
        automaton.input_variables = input_vars
        n_in_vars = len(input_vars)
        print(
            f' Automaton Inputs {n_in_vars}\n'
            f'    input vars = {automaton.input_variables}\n'
            f'    binary = ({binary_inputs})'
        )

        automaton.reset_states()
        for node_name, node_info in data['nodes'].items():
            state = self.automaton_state_from_node_info(
                node_name,
                node_info,
                n_in_vars,
                mem_idxs,
            )
            raw_input_valuation = list(state.input_valuation)
            raw_output_valuation = list(state.output_valuation)
            state.update_variables(
                binary_inputs,
                automaton.input_variables,
                binary_outputs,
                automaton.output_variables,
                activation_tag,
                outcome_tags,
                outcome_names,
                sm_outcomes,
            )
            print('--- Inputs ---')
            for idx, val in enumerate(raw_input_valuation):
                if val:
                    print(f'  {idx:2d} - {input_vars[idx]}')
            print('--- Outputs ---')
            for idx, val in enumerate(raw_output_valuation):
                if val:
                    print(f'  {idx:2d} - {output_vars[idx]}')
            print(state)
            automaton.add_state(state)

        return automaton

    def expand_binary(self, var_list):
        """Expand compact integer notation (`var:min...max`) into bit propositions."""
        original = var_list[:]
        binary_variables = expand_binary_variables(var_list)
        if original != var_list:
            print(f'  expanded binary [{var_list}]')
        return binary_variables


def package_share_roots(package_names):
    """Return installed package share roots that are available in this workspace."""
    roots = []
    for package_name in package_names:
        try:
            roots.append(Path(get_package_share_directory(package_name)))
        except PackageNotFoundError:
            continue
    return roots


def default_search_roots(package_names=DEFAULT_SEARCH_PACKAGES):
    """Return directories searched for checker inputs."""
    roots = [Path.cwd(), Path(fpths.get_synthesis_home())]
    roots.extend(package_share_roots(package_names))
    return roots


def resolve_existing_path(path_text, search_roots=None):
    """Resolve a path directly or by searching configured roots."""
    path = Path(path_text).expanduser()
    if path.is_absolute() and path.exists():
        return path
    if not path.is_absolute() and path.exists():
        return path.resolve()

    roots = default_search_roots() if search_roots is None else search_roots
    candidates = []
    for root in roots:
        candidates.append(root / path)
        candidates.extend(root.rglob(path.name))

    for candidate in candidates:
        if candidate.exists() and candidate.name == path.name:
            return candidate.resolve()

    searched = '\n  '.join(str(root) for root in roots)
    raise FileNotFoundError(f"Could not find '{path_text}'. Searched:\n  {searched}")


def parse_structuredslugs_variables(spec_path):
    """Return input and output variables from a structured Slugs specification."""
    input_vars = []
    output_vars = []
    read_inputs = False
    read_outputs = False

    with open(spec_path, encoding='utf-8') as spec_file:
        for line in spec_file:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if stripped == '[INPUT]':
                read_inputs = True
                read_outputs = False
                continue
            if stripped == '[OUTPUT]':
                read_inputs = False
                read_outputs = True
                continue
            if stripped.startswith('['):
                read_inputs = False
                read_outputs = False
                continue
            if read_inputs:
                input_vars.append(stripped)
            if read_outputs:
                output_vars.append(stripped)

    return input_vars, output_vars


def matching_structuredslugs_path(json_path, spec_name=None, search_roots=None):
    """Find a matching structuredslugs file for a JSON automaton."""
    stem = spec_name or json_path.stem
    direct = json_path.with_name(f'{stem}.structuredslugs')
    if direct.exists():
        return direct
    return resolve_existing_path(f'{stem}.structuredslugs', search_roots)


def build_argument_parser():
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            'Inspect a Slugs JSON automaton by converting it into a '
            'SlugsAutomaton object.'
        ),
    )
    parser.add_argument(
        'json',
        nargs='?',
        help='Path or searchable filename for the Slugs JSON automaton.',
    )
    parser.add_argument(
        '--spec-name',
        help='Spec name used to infer `<spec-name>.json` and `.structuredslugs`.',
    )
    parser.add_argument(
        '--structuredslugs',
        help='Path or installed filename for variable declarations.',
    )
    parser.add_argument(
        '--input-var',
        action='append',
        default=[],
        help='Input variable. Repeat when no structuredslugs file is available.',
    )
    parser.add_argument(
        '--output-var',
        action='append',
        default=[],
        help='Output variable. Repeat when no structuredslugs file is available.',
    )
    parser.add_argument(
        '--search-package',
        action='append',
        default=[],
        help='Additional installed package share directory to search.',
    )
    return parser


def main(argv=None):
    """Run the automaton checker utility."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    package_names = DEFAULT_SEARCH_PACKAGES + tuple(args.search_package)
    search_roots = default_search_roots(package_names)

    json_name = args.json
    if json_name is None:
        if args.spec_name is None:
            parser.error('provide a JSON file or --spec-name')
        json_name = f'{args.spec_name}.json'
    json_path = resolve_existing_path(json_name, search_roots)

    input_vars = list(args.input_var)
    output_vars = list(args.output_var)
    if not input_vars and not output_vars:
        if args.structuredslugs:
            spec_path = resolve_existing_path(args.structuredslugs, search_roots)
        else:
            spec_path = matching_structuredslugs_path(
                json_path,
                args.spec_name,
                search_roots,
            )
        input_vars, output_vars = parse_structuredslugs_variables(spec_path)

    if not input_vars or not output_vars:
        parser.error(
            'input and output variables are required; provide --structuredslugs '
            'or repeat --input-var/--output-var'
        )

    print(f"Using JSON automaton '{json_path}'")
    checker = SlugsAutomatonChecker()
    automaton = checker.gen_automaton_msg_from_json(
        json_path,
        input_vars,
        output_vars,
    )
    print(automaton)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
