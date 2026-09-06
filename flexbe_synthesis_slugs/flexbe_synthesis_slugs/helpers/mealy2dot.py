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
Generate a GraphViz dot representation of a Mealy automaton from Slugs output.

Reads a .slugsin spec file and the JSON strategy produced by slugs, and writes
a .dot file (plus optional PDF/PNG via the graphviz Python package).

Compatible with both strategy types:
  - ``slugs --explicitStrategy --jsonOutput``  (realizable specs)
  - ``slugs --counterStrategy --jsonOutput``   (unrealizable specs)

For counter-strategies the environment is the strategic player, so the
system-choice and environment-choice edge colors reflect automaton structure
rather than player roles. Deadlock states (where the system has no valid move)
are rendered with empty output-variable labels.

Usage:
    mealy2dot.py <spec.slugsin> <strategy.json>

If arguments are omitted and tkinter is available, file-chooser dialogs
are shown instead.
"""

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys

from flexbe_synthesis_core.graph_utils import tarjan_scc

try:
    from tkinter.filedialog import askopenfilename

    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False


@dataclasses.dataclass
class GraphStyle:
    """Visual style parameters for the Mealy machine dot output."""

    font: str = 'Liberation Sans'
    font_weight: str = 'bold'
    font_size: int = 6  # label font size for env state variable annotations
    penwidth: float = 2.0  # line width for node borders and edges
    env_node_size: float = 0.4  # env state node diameter (inches)
    sys_node_size: float = 0.1  # sys state filled-dot diameter (inches)
    dpi: int = 150
    show_node_ids: bool = True  # include node ID in env state xlabel
    sys_choice_edge_color: str = 'green'
    env_choice_edge_color: str = 'red'
    trap_env_fillcolor: str = '#ffb347'  # goal-unreachable-trap env node fill
    trap_sys_fillcolor: str = '#b34700'  # goal-unreachable-trap sys node fill


def parse_bit(AP):
    """
    Parse a slugs bit variable of the form ``[!]name@bit[.min.max]``.

    Returns (ap_name, bit_index, min_val, max_val, bit_is_set). The min/max
    metadata is only present for bit 0.
    """
    pattern = r'(!?)([a-zA-Z0-9_]+)@(\d+)(?:\.(-?\d+)\.(-?\d+))?'
    match = re.fullmatch(pattern, AP)
    if match:
        negated, ap, bit_ndx, min_val, max_val = match.groups()
        if bit_ndx != '0' and (min_val is not None or max_val is not None):
            raise ValueError(f"Bit {bit_ndx} of '{ap}' must not carry min/max metadata: {AP}")
        return (
            ap,
            int(bit_ndx),
            (None if min_val is None else int(min_val)),
            (None if max_val is None else int(max_val)),
            negated == '',
        )
    raise ValueError(f"Variable '{AP}' does not match expected bit pattern 'name@bit[.min.max]'")


def load_specs(file_path):
    """
    Parse a .slugsin file into a dict keyed by section header.

    Returns ``{section: [line, ...]}``, e.g. ``{'[INPUT]': ['x', 'y'], ...}``.
    Blank lines and ``#`` comments are skipped, and trailing inline comments
    are removed.
    """
    specs = {}
    with open(file_path) as fin:
        lines = fin.readlines()
        key = None
        for line in lines:
            line = line.split('#', 1)[0].strip()
            if len(line) == 0:
                continue

            if line[0] == '[' and line[-1] == ']':
                key = line
                specs[key] = []
            else:
                if key is None:
                    raise ValueError(
                        f"Content before first section header in '{file_path}': {line!r}"
                    )
                specs[key].append(line)
    return specs


def load_automata(file_path):
    """Load and return the JSON strategy produced by slugs --jsonOutput."""
    with open(file_path) as fin:
        auton = json.load(fin)
    return auton


def build_adjacency(auton, initial):
    """Return (full_adjacency, reachable_node_ids) for the raw Slugs node graph."""
    nodes = auton['nodes']
    adjacency = {
        name: [str(target) for target in state['trans']] for name, state in nodes.items()
    }
    seen = set()
    stack = [initial]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(n for n in adjacency.get(node, []) if n not in seen)
    return adjacency, seen


def find_traps(auton, goal_var, initial='0'):
    """
    Find goal-unreachable-trap SCCs in the reachable strategy graph.

    Mirrors the structural condition ``StrategyAuditor.GOAL_UNREACHABLE_TRAP``
    checks -- see ``docs/auditor.md``, "Goal-Unreachable Trap Detection" --
    computed directly on the raw node graph rather than the auditor's product
    automaton. This is a visualization aid, not a replacement for the
    auditor: it re-derives trap SCCs from the raw strategy graph and a single
    boolean goal proposition, without the auditor's activation/outcome
    protocol monitor, pending-episode failure-bound product construction, or
    configurable goal-label set.

    Returns ``(sccs, trap_indices, adjacency)``. ``sccs`` is the full list of
    strongly-connected components (each a list of raw state ids) of the
    reachable subgraph; ``trap_indices`` indexes into ``sccs`` for components
    that are cyclic and cannot reach a cyclic goal-containing component.

    Raises ``ValueError`` if ``goal_var`` is not among the automaton's
    variables; raises ``KeyError`` if ``initial`` is not a reachable node.
    """
    nodes = auton['nodes']
    variables = auton['variables']
    if goal_var not in variables:
        raise ValueError(f"Goal variable '{goal_var}' not found in automaton variables.")
    goal_ix = variables.index(goal_var)

    adjacency, reachable = build_adjacency(auton, initial)
    # Sorting fixes SCC discovery order (and therefore scc index i)
    # deterministically across process invocations. `reachable` alone is a
    # set of strings, whose iteration order depends on hash randomization
    # (PYTHONHASHSEED), which would otherwise make trap identity unstable
    # between separate calls on the same strategy.
    ordered_reachable = sorted(reachable, key=int)
    reachable_adjacency = {
        n: [m for m in adjacency[n] if m in reachable] for n in ordered_reachable
    }

    sccs = tarjan_scc(ordered_reachable, reachable_adjacency)
    scc_of = {n: i for i, scc in enumerate(sccs) for n in scc}

    def is_cyclic(scc):
        if len(scc) > 1:
            return True
        (only,) = scc
        return only in reachable_adjacency.get(only, [])

    def is_goal(scc):
        return any(nodes[n]['state'][goal_ix] == 1 for n in scc)

    cyclic = [i for i, scc in enumerate(sccs) if is_cyclic(scc)]
    goal_cyclic = {i for i in cyclic if is_goal(sccs[i])}

    condensed_successors = {i: set() for i in range(len(sccs))}
    for node, succs in reachable_adjacency.items():
        for target in succs:
            if scc_of[node] != scc_of[target]:
                condensed_successors[scc_of[node]].add(scc_of[target])
    condensed_predecessors = {i: set() for i in range(len(sccs))}
    for i, succs in condensed_successors.items():
        for j in succs:
            condensed_predecessors[j].add(i)

    can_reach_goal = set(goal_cyclic)
    stack = list(goal_cyclic)
    while stack:
        i = stack.pop()
        for j in condensed_predecessors[i]:
            if j not in can_reach_goal:
                can_reach_goal.add(j)
                stack.append(j)

    trap_indices = [i for i in cyclic if i not in can_reach_goal]
    return sccs, trap_indices, reachable_adjacency


def collect_variables(specs, exact_sections=(), split_prefixes=()):
    """
    Collect variables from exact sections and split-prefix sections.

    Matching sections are returned in spec-file order. Raises ``KeyError`` if no
    matching sections are present.
    """
    exact_section_names = {f'[{section_name}]' for section_name in exact_sections}
    split_prefix_names = tuple(f'[{section_name}_' for section_name in split_prefixes)

    matching_sections = [
        section_name
        for section_name in specs
        if section_name in exact_section_names or section_name.startswith(split_prefix_names)
    ]
    if not matching_sections:
        section_label = exact_sections[0] if exact_sections else split_prefixes[0]
        raise KeyError(f'[{section_label}]')

    variables = []
    for section_name in matching_sections:
        variables.extend(specs[section_name])
    return variables


def collect_input_variables(specs):
    """
    Collect environment variables from supported Slugs input sections.

    Supports plain ``[INPUT]``, split input sections like ``[INPUT_A]``, and
    structured-spec sections such as ``[OBSERVABLE_INPUT]``.
    """
    return collect_variables(
        specs,
        exact_sections=('INPUT', 'OBSERVABLE_INPUT', 'UNOBSERVABLE_INPUT', 'CONTROLLABLE_INPUT'),
        split_prefixes=('INPUT',),
    )


def collect_output_variables(specs):
    """Collect system variables from ``[OUTPUT]`` and split output sections."""
    return collect_variables(specs, exact_sections=('OUTPUT',), split_prefixes=('OUTPUT',))


def open_with_default_viewer(path):
    """
    Open ``path`` in the platform's default viewer.

    Returns True when a launch command was issued, else False.
    """
    if os.name == 'nt':
        try:
            os.startfile(path)
            return True
        except OSError:
            return False

    if sys.platform == 'darwin':
        opener = shutil.which('open')
        if opener:
            subprocess.Popen(
                [opener, path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return True
        return False

    for command in (['xdg-open', path], ['gio', 'open', path], ['open', path]):
        executable = shutil.which(command[0])
        if executable:
            subprocess.Popen(
                [executable, *command[1:]],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return True
    return False


def build_arg_parser():
    """Build the command-line interface for the mealy2dot tool."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Positional / file arguments
    parser.add_argument(
        'specs_file',
        nargs='?',
        help='Path to the .slugsin specification file',
    )
    parser.add_argument(
        'auton_file',
        nargs='?',
        help='Path to the Slugs strategy JSON file',
    )

    # Layout / structure
    parser.add_argument(
        '--layout',
        default='dot',
        help=(
            'GraphViz layout engine (default: %(default)s); '
            'see https://graphviz.org/docs/layouts/'
        ),
    )
    parser.add_argument(
        '--no-splines',
        action='store_true',
        help='Disable spline routing in the generated .dot output',
    )
    parser.add_argument(
        '--no-initial-state',
        action='store_true',
        help='Omit the synthetic Init node and initial edge from the graph',
    )
    parser.add_argument(
        '--hide-node-ids',
        action='store_true',
        help='Omit the state node ID from env state labels',
    )

    # Typography
    parser.add_argument(
        '--font',
        default='Liberation Sans',
        metavar='NAME',
        help='Font family for all text (default: %(default)s)',
    )
    parser.add_argument(
        '--font-weight',
        default='bold',
        metavar='WEIGHT',
        help='Font weight for nodes and edges (default: %(default)s)',
    )
    parser.add_argument(
        '--font-size',
        type=int,
        default=6,
        metavar='PT',
        help='Font size for env state variable labels in points (default: %(default)s)',
    )

    # Line weights
    parser.add_argument(
        '--penwidth',
        type=float,
        default=2.0,
        metavar='W',
        help='Line width for node borders and edges (default: %(default)s)',
    )

    # Node sizes
    parser.add_argument(
        '--env-node-size',
        type=float,
        default=0.4,
        metavar='IN',
        help='Env state node diameter in inches (default: %(default)s)',
    )
    parser.add_argument(
        '--sys-node-size',
        type=float,
        default=0.1,
        metavar='IN',
        help='Sys state filled-dot diameter in inches (default: %(default)s)',
    )

    # Edge colors
    parser.add_argument(
        '--sys-choice-edge-color',
        default='green',
        metavar='COLOR',
        help='Color for system-choice env→sys edges (default: %(default)s)',
    )
    parser.add_argument(
        '--env-choice-edge-color',
        default='red',
        metavar='COLOR',
        help='Color for environment-choice sys→env edges (default: %(default)s)',
    )

    # Goal-unreachable-trap highlighting
    parser.add_argument(
        '--no-highlight-traps',
        dest='highlight_traps',
        action='store_false',
        help=(
            'Do not highlight goal-unreachable-trap SCCs (see docs/auditor.md). '
            'Highlighting is on by default.'
        ),
    )
    parser.add_argument(
        '--goal-var',
        default='finished',
        metavar='NAME',
        help=(
            'Boolean output variable marking goal states, used for trap '
            'highlighting (default: %(default)s). If absent from the '
            'automaton, highlighting is skipped with a warning.'
        ),
    )
    parser.add_argument(
        '--initial',
        default='0',
        metavar='ID',
        help=(
            'Initial raw state id for trap reachability analysis (default: '
            '%(default)s, matching Slugs convention)'
        ),
    )

    # Output
    parser.add_argument(
        '--dpi',
        type=int,
        default=150,
        metavar='N',
        help='Output resolution in DPI (default: %(default)s)',
    )
    parser.add_argument(
        '--no-open',
        action='store_true',
        help='Do not open the rendered PDF after generation',
    )

    return parser


class State:
    """Base class for a node in the Mealy machine GraphViz graph."""

    def __init__(self, name, variables, trans):
        """Initialize a graph state with variables and outgoing transitions."""
        self.name = name
        self.variables = variables
        self.trans = trans

    def __str__(self):
        """Return a concise state summary."""
        return f'{self.__class__.__name__}: {self.name} : {self.variables} : {self.trans}'

    def get_state_label(self, show_node_id=True):
        """
        Return a GraphViz xlabel attribute string listing the state's variable values.

        Boolean variables are shown by name when True; numeric variables as ``name=value``.
        The state node ID is prepended when ``show_node_id`` is True.
        """
        labels = [self.name] if show_node_id else []
        keys = sorted(self.variables.keys())

        numerics = []
        for key in keys:
            if isinstance(self.variables[key], bool):
                if self.variables[key]:
                    labels.append(key)
            else:
                numerics.append(f'{key}={self.variables[key]}')
        labels = labels + numerics
        return f'xlabel="{chr(10).join(labels)}"' if labels else ''


class EnvState(State):
    """A Mealy node representing the environment's variable assignments."""


class SysState(State):
    """A Mealy node representing the system's response (output variables); rendered filled."""


class Mealy:
    """
    Mealy machine built from a Slugs JSON strategy (explicit or counter).

    Each Slugs strategy node is split into an EnvState (environment inputs)
    and a SysState (system outputs), connected by a green env→sys edge.
    SysState transitions back to the next EnvState are drawn in red. The
    initial state is taken from explicit JSON metadata when available and
    otherwise chosen deterministically from the node ids.
    """

    def __init__(self):
        """Initialize an empty Mealy graph."""
        self.env_vars = {}
        self.sys_vars = {}
        self.states = {}
        self.initial_state = None

    def __str__(self):
        """Return a concise text summary of variables and states."""
        string = 30 * '-' + '\n'
        string += str(self.env_vars) + '\n'
        string += str(self.sys_vars) + '\n'
        string += '\n'
        for name, state in self.states.items():
            string += str(state) + '\n'

        return string

    @staticmethod
    def _decode_binaries(binaries):
        """
        Decode a list of signed bit-strings into a dict of {ap_name: integer_value}.

        Each multi-bit variable appears as entries named 'ap@0.min.max'
        (bit 0) through 'ap@N', optionally prefixed with '!' when the bit is 0.
        Bit entries may appear interleaved with other variables as long as the
        bit-0 entry appears somewhere in the list. Conflicting duplicate bit
        assignments raise ``ValueError``.
        """
        grouped_bits = {}
        ranges = {}
        for binary in binaries:
            ap, bit_ndx, min_val, max_val, bit_is_set = parse_bit(binary)
            bits = grouped_bits.setdefault(ap, {})
            previous_value = bits.get(bit_ndx)
            if previous_value is not None and previous_value != bit_is_set:
                raise ValueError(
                    f"Conflicting assignments for '{ap}' bit {bit_ndx} in binaries {binaries}"
                )
            bits[bit_ndx] = bit_is_set
            if bit_ndx == 0:
                if min_val is None or max_val is None:
                    raise ValueError(f"Bit 0 of '{ap}' is missing min/max metadata: {binary}")
                previous_range = ranges.get(ap)
                if previous_range is not None and previous_range != (min_val, max_val):
                    raise ValueError(
                        f"Conflicting ranges for '{ap}' in binaries {binaries}: "
                        f'{previous_range} vs {(min_val, max_val)}'
                    )
                ranges[ap] = (min_val, max_val)

        result = {}
        for ap, bits in grouped_bits.items():
            if ap not in ranges:
                raise ValueError(f"Missing bit-0 metadata for '{ap}' in binaries {binaries}")

            min_val, max_val = ranges[ap]
            difference = max_val - min_val
            if difference < 0:
                raise ValueError(f"Invalid range for '{ap}': min {min_val} exceeds max {max_val}")
            if difference == 0:
                result[ap] = min_val
                continue

            num_bits = 0
            while (1 << num_bits) <= difference:
                num_bits += 1

            missing_bits = [bit for bit in range(num_bits) if bit not in bits]
            if missing_bits:
                raise ValueError(f"Missing bits {missing_bits} of '{ap}' in binaries {binaries}")

            total = min_val
            for bit_ndx in range(num_bits):
                if bits[bit_ndx]:
                    total += 1 << bit_ndx
            result[ap] = total
        return result

    @staticmethod
    def _resolve_initial_node_name(auton):
        """
        Return the initial node name from JSON metadata or deterministic fallback.

        Preference order:
        1. Explicit top-level JSON metadata such as ``initial_node`` or ``init``.
        2. Node ``"0"`` when present, matching Slugs' common convention.
        3. The numerically smallest node id.
        4. The lexicographically smallest node id.
        """
        nodes = auton.get('nodes', {})
        if not nodes:
            raise ValueError('Automaton JSON does not contain any nodes')

        explicit_keys = (
            'initial_node',
            'initialNode',
            'initial_state',
            'initialState',
            'init_state',
            'initState',
            'init',
        )
        for key in explicit_keys:
            if key not in auton:
                continue
            initial_node = auton[key]
            if isinstance(initial_node, list):
                if len(initial_node) != 1:
                    raise ValueError(
                        f"Expected exactly one initial node in '{key}', got {initial_node}"
                    )
                initial_node = initial_node[0]
            initial_node = str(initial_node)
            if initial_node not in nodes:
                raise ValueError(
                    f"Initial node '{initial_node}' from '{key}' is not present in automaton nodes"
                )
            return initial_node

        if '0' in nodes:
            return '0'

        try:
            return min(nodes.keys(), key=lambda name: int(name))
        except ValueError:
            return min(nodes.keys())

    @staticmethod
    def define_mealy(specs, auton):
        """
        Build a Mealy machine from parsed slugsin specs and a JSON automaton.

        Each node in ``auton['nodes']`` becomes an EnvState/SysState pair.
        Multi-bit integer variables (encoded as ``name@bit.min.max``) are
        decoded back to their integer values. The initial state is chosen from
        explicit JSON metadata when present, else by deterministic fallback.
        Input variables are collected from supported Slugs input sections such
        as ``[INPUT]`` and ``[OBSERVABLE_INPUT]``. Output variables are
        collected from ``[OUTPUT]`` and split output sections such as
        ``[OUTPUT_A]`` / ``[OUTPUT_B]``.
        """
        mealy = Mealy()
        initial_node_name = Mealy._resolve_initial_node_name(auton)
        for var in collect_input_variables(specs):
            mealy.env_vars[var] = auton['variables'].index(var)
        for var in collect_output_variables(specs):
            mealy.sys_vars[var] = auton['variables'].index(var)

        for name, state in auton['nodes'].items():
            # Load environmental states
            env_vars = {}
            binaries = []
            for var, ndx in mealy.env_vars.items():
                if '@' in var:
                    binaries.append(f'{"!" if state["state"][ndx] == 0 else ""}{var}')
                else:
                    if state['state'][ndx] == 1:
                        # Only record True Booleans
                        env_vars[var] = True
            env_vars.update(Mealy._decode_binaries(binaries))

            # Load system state
            sys_vars = {}
            binaries = []
            for var, ndx in mealy.sys_vars.items():
                try:
                    if '@' in var:
                        binaries.append(f'{"!" if state["state"][ndx] == 0 else ""}{var}')
                    else:
                        if state['state'][ndx] == 1:
                            # Only record True Booleans
                            sys_vars[var] = True
                except IndexError:
                    print(f"No output for '{var}' (deadlock state {name})")
            sys_vars.update(Mealy._decode_binaries(binaries))

            env_state = EnvState(name, env_vars, [f'{name}_sys'])
            sys_state = SysState(f'{name}_sys', sys_vars, [str(tran) for tran in state['trans']])

            if name == initial_node_name:
                mealy.initial_state = env_state

            mealy.states[env_state.name] = env_state
            mealy.states[sys_state.name] = sys_state

        if mealy.initial_state is None:
            raise ValueError(
                f"Initial node '{initial_node_name}' was not materialized in the Mealy machine"
            )

        return mealy

    @staticmethod
    def mealy_from_slugs_automaton(automaton):
        """Define Mealy structure from a `SlugsAutomaton` instance."""
        mealy = Mealy()

        for var in automaton.output_variables:
            mealy.sys_vars[var] = -1

        for var in automaton.input_variables:
            mealy.env_vars[var] = -1

        for state in automaton.automaton:
            name = state.name

            env_vars = {var: True for var in state.input_variables}
            env_vars.update(state.input_values)

            sys_vars = {var: True for var in state.output_variables}
            sys_vars.update(state.output_values)

            env_state = EnvState(name, env_vars, [f'{name}_sys'])
            sys_state = SysState(
                f'{name}_sys',
                sys_vars,
                [str(transition) for transition in state.transitions],
            )

            if mealy.initial_state is None:
                mealy.initial_state = env_state

            mealy.states[env_state.name] = env_state
            mealy.states[sys_state.name] = sys_state

        return mealy

    def to_dot(self, layout='dot', splines=True, initial_state=True, style=None, trap_states=None):
        """
        Return a GraphViz dot string for this Mealy machine.

        The layout argument selects the GraphViz layout engine. When
        ``initial_state`` is true, a point-shaped Init node is prepended with an
        edge to the recorded initial environment state. The optional style
        argument controls fonts, colors, and sizes. ``trap_states``, when
        given, is a set of raw strategy state ids (as returned by
        ``find_traps``); the corresponding env/sys node pairs are filled with
        ``style.trap_env_fillcolor``/``style.trap_sys_fillcolor``.
        """
        if style is None:
            style = GraphStyle()

        dot = 'digraph StateMachine {\n'
        dot += '  outputorder="edgesfirst";\n'
        dot += f'  layout="{layout}";\n'

        if splines:
            dot += '  splines=true;\n'

        dot += '  rankdir=LR;\n'  # or 'TB' for top-to-bottom
        dot += '  nodesep=0.8;\n'  # horizontal distance between nodes
        dot += '  ranksep=1.2;\n'  # vertical spacing between ranks
        dot += '  overlap=false;\n'
        dot += f'  dpi={style.dpi};\n'
        dot += f'  fontname="{style.font}";\n'
        dot += (
            f'  node [fontname="{style.font}", fontweight="{style.font_weight}", '
            f'penwidth={style.penwidth}];\n'
        )
        dot += (
            f'  edge [fontname="{style.font}", fontweight="{style.font_weight}", '
            f'penwidth={style.penwidth}];\n'
        )

        if initial_state:
            dot += '  "Init" [shape=point];\n'

        for state_name, state in self.states.items():
            attributes = []
            is_sys = isinstance(state, SysState)
            raw_id = state_name[:-len('_sys')] if is_sys else state_name
            is_trap = trap_states is not None and raw_id in trap_states

            if is_sys:
                attributes.append(f'width={style.sys_node_size}')
                attributes.append(f'height={style.sys_node_size}')
                attributes.append('style=filled')
                fillcolor = f'"{style.trap_sys_fillcolor}"' if is_trap else 'black'
                attributes.append(f'fillcolor={fillcolor}')
                attributes.append(f'fontsize={style.font_size}')
                state_label = state.get_state_label(show_node_id=style.show_node_ids)
                if state_label:
                    attributes.append(state_label)
                attributes.append('label=""')
            else:  # EnvState
                attributes.append(f'width={style.env_node_size}')
                attributes.append(f'height={style.env_node_size}')
                attributes.append(f'fontsize={style.font_size}')
                state_label = state.get_state_label(show_node_id=style.show_node_ids)
                if state_label:
                    attributes.append(state_label)
                if is_trap:
                    attributes.append('style=filled')
                    attributes.append(f'fillcolor="{style.trap_env_fillcolor}"')
                    attributes.append(f'penwidth={style.penwidth * 1.75}')

            dot += f'  "{state_name}" [{", ".join(attributes)}];\n'

        if initial_state and self.initial_state is not None:
            dot += f'  "Init" -> "{self.initial_state.name}";\n'

        for state_name, state in self.states.items():
            if isinstance(state, EnvState):
                if len(state.trans) != 1:
                    raise ValueError(
                        f"EnvState '{state_name}' has {len(state.trans)} transitions; "
                        'expected exactly 1'
                    )
                for target_state in state.trans:
                    dot += (
                        f'  "{state_name}" -> "{target_state}" '
                        f'[color="{style.sys_choice_edge_color}"];\n'
                    )
            elif isinstance(state, SysState):
                for target_state in state.trans:
                    dot += (
                        f'  "{state_name}" -> "{target_state}" '
                        f'[color="{style.env_choice_edge_color}"];\n'
                    )
            else:
                raise TypeError(f'Unknown instance type {state.__class__.__name__}')
        dot += '}'
        return dot

    @staticmethod
    def draw_graph(dot, base_file_name):
        """
        Write the dot source to ``<base_file_name>.dot`` and render PDF/PNG via graphviz.

        Falls back gracefully if graphviz is not installed, printing a link
        to an online renderer. A rendered PDF is treated as success even if PNG
        generation fails afterward.

        Returns the rendered PDF path, or ``None`` if no PDF was produced.
        """
        dot_path = base_file_name + '.dot'
        with open(dot_path, 'w') as f:
            f.write(dot)
        print(f"Done writing '{dot_path}'", flush=True)

        try:
            from graphviz import Source
        except ImportError:
            print(
                'graphviz Python package not installed; try '
                'https://dreampuf.github.io/GraphvizOnline',
                file=sys.stderr,
            )
            return None

        s = Source(dot)
        pdf_path = base_file_name + '.pdf'
        try:
            print('Computing layout and saving as PDF ...', flush=True)
            print('   This is optional, and can be (very) slow for large graphs.')
            print('   Consider `dot -Tpdf -Tpng -O big_graph.dot`', flush=True)
            pdf_data = s.pipe(format='pdf')
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
            print(f'PDF saved to {pdf_path}', flush=True)
        except Exception as exc:
            print(f'Rendering failed: {exc}', file=sys.stderr)
            return None

        try:
            png_data = s.pipe(format='png')
            with open(base_file_name + '.png', 'wb') as f:
                f.write(png_data)
            print('Done saving pdf and png image files!', flush=True)
        except Exception as exc:
            print(f'PNG rendering failed: {exc}', file=sys.stderr)
        return pdf_path


def main():
    """Entry point: load inputs, write the .dot file, and optionally open a rendered PDF."""
    parser = build_arg_parser()
    args = parser.parse_args()
    print('Loading spec and strategy data ...')
    initial_dir = os.path.join(os.path.expanduser('~'), '.flexbe_synthesis')

    if args.specs_file:
        specs_file = args.specs_file
    elif HAS_TKINTER:
        specs_file = askopenfilename(
            title='Select specs',
            initialdir=initial_dir,
            filetypes=[('Slugsin specs', '*.slugsin'), ('All files', '*.*')],
        )
    else:
        print('Error: tkinter is not available. Provide specs file as first argument.')
        sys.exit(1)

    if not specs_file:
        print('No file selected.')
        sys.exit(1)

    specs_folder = os.path.dirname(specs_file)
    base_name = os.path.splitext(os.path.basename(specs_file))[0]
    print(f"Selected file: '{base_name}' - '{specs_file}'")
    print('Folder:', specs_folder)

    if args.auton_file:
        auton_file = args.auton_file
    elif HAS_TKINTER:
        auton_file = askopenfilename(
            title='Select automaton',
            initialdir=specs_folder,
            filetypes=[('Slugs Automaton', '*.json'), ('All files', '*.*')],
        )
    else:
        print('Error: tkinter is not available. Provide automaton file as second argument.')
        sys.exit(1)

    if not auton_file:
        print('No auton file selected.')
        sys.exit(1)

    print(f"Load specs from '{specs_file}' ...")
    slugs_specs = load_specs(specs_file)

    print(f"Load automaton from '{auton_file}' ...")
    slugs_auton = load_automata(auton_file)

    print('Define the Mealy machine ...')
    mealy = Mealy.define_mealy(slugs_specs, slugs_auton)

    style = GraphStyle(
        font=args.font,
        font_weight=args.font_weight,
        font_size=args.font_size,
        penwidth=args.penwidth,
        env_node_size=args.env_node_size,
        sys_node_size=args.sys_node_size,
        dpi=args.dpi,
        show_node_ids=not args.hide_node_ids,
        sys_choice_edge_color=args.sys_choice_edge_color,
        env_choice_edge_color=args.env_choice_edge_color,
    )

    trap_states = None
    if args.highlight_traps:
        if args.goal_var not in slugs_auton.get('variables', []):
            print(
                f"Warning: goal variable '{args.goal_var}' not found in automaton "
                'variables; skipping trap highlighting.',
            )
        else:
            try:
                sccs, trap_indices, _ = find_traps(slugs_auton, args.goal_var, args.initial)
            except (KeyError, ValueError) as exc:
                print(f'Warning: trap analysis failed ({exc}); skipping trap highlighting.')
            else:
                trap_states = {n for i in trap_indices for n in sccs[i]}
                if trap_states:
                    print(
                        f'Found {len(trap_indices)} goal-unreachable trap SCC(s) '
                        f'({len(trap_states)} states); highlighting on the graph.',
                    )
                else:
                    print('No goal-unreachable traps found.')

    print('Converting to dot format ...')
    dot_str = mealy.to_dot(
        layout=args.layout,
        splines=not args.no_splines,
        initial_state=not args.no_initial_state,
        style=style,
        trap_states=trap_states,
    )

    dot_file = os.path.join(specs_folder, base_name)
    pdf_path = mealy.draw_graph(dot_str, dot_file)

    if pdf_path and os.path.exists(pdf_path) and not args.no_open:
        print('Open viewer ...')
        if open_with_default_viewer(pdf_path):
            print('Done!  - Hit enter after viewer opens')
        else:
            print('Could not find a platform opener; open the PDF manually.')
    elif pdf_path and os.path.exists(pdf_path):
        print('Skipping viewer launch because --no-open was requested.')
    else:
        print('Skipping viewer launch because no PDF was produced.')


if __name__ == '__main__':
    main()
