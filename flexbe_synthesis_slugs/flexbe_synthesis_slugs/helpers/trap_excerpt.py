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
Render a GraphViz excerpt around a goal-unreachable-trap SCC in a Slugs strategy.

Given a compiled ``.slugsin`` spec and its synthesized strategy ``.json``, this
finds one goal-unreachable-trap SCC (via ``mealy2dot.find_traps``, see that
module for the algorithm and its caveats -- also the function backing
``mealy2dot --highlight-traps``, on by default there) and renders a small
dot/PDF/PNG excerpt of it plus its immediate predecessor context, with the
trap states highlighted. Use this instead of the full-graph highlighting when
the whole strategy is too large to read and you want a small, paper-figure-
sized excerpt around one specific trap.

Usage:
    trap_excerpt.py <spec.slugsin> <strategy.json> [--goal-var finished]
"""

import argparse
import sys

from flexbe_synthesis_slugs.helpers.mealy2dot import find_traps, GraphStyle, load_automata
from flexbe_synthesis_slugs.helpers.mealy2dot import load_specs, Mealy


def context_predecessors(adjacency, trap_states, hops):
    """Return raw ids reaching ``trap_states`` within ``hops`` steps, excluding the trap itself."""
    reverse = {}
    for node, succs in adjacency.items():
        for target in succs:
            reverse.setdefault(target, set()).add(node)

    frontier = set(trap_states)
    context = set()
    for _ in range(hops):
        next_frontier = set()
        for node in frontier:
            for pred in reverse.get(node, ()):
                if pred not in trap_states and pred not in context:
                    context.add(pred)
                    next_frontier.add(pred)
        frontier = next_frontier
        if not frontier:
            break
    return context


def _stub_node(name, style):
    """Return a dot declaration for a truncated 'elsewhere' stub node.

    Drawn as a bold ellipsis rather than a filled dot or a specific state
    id, so it reads as a cut/break in the graph rather than a real,
    identifiable state.
    """
    return (
        f'  "{name}" [shape=plaintext, label=<<B>...</B>>, '
        f'fontsize={style.font_size}];\n'
    )


def render_excerpt(specs_path, auton_path, keep_ids, trap_ids, adjacency, out_base, style=None):
    """Write a highlighted dot excerpt for ``keep_ids`` (trap states in ``trap_ids``)."""
    if style is None:
        style = GraphStyle(font_size=11, env_node_size=0.55, sys_node_size=0.14, penwidth=2.2)

    specs = load_specs(specs_path)
    auton = load_automata(auton_path)
    mealy = Mealy.define_mealy(specs, auton)

    keep_ids = list(keep_ids)
    keep_id_set = set(keep_ids)
    keep_names = {n for raw_id in keep_ids for n in (raw_id, f'{raw_id}_sys')}
    trap_names = {n for raw_id in trap_ids for n in (raw_id, f'{raw_id}_sys')}

    dot = 'digraph StateMachine {\n'
    dot += '  outputorder="edgesfirst";\n'
    dot += '  rankdir=LR;\n'
    dot += '  nodesep=0.6;\n'
    dot += '  ranksep=1.0;\n'
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

    for state_name, state in mealy.states.items():
        if state_name not in keep_names:
            continue
        is_sys = state_name.endswith('_sys')
        is_trap = state_name in trap_names
        attributes = []
        if is_sys:
            sys_fill = '"#b34700"' if is_trap else 'black'
            attributes += [
                f'width={style.sys_node_size}', f'height={style.sys_node_size}',
                'style=filled', f'fillcolor={sys_fill}',
                f'fontsize={style.font_size}',
            ]
            label = state.get_state_label(show_node_id=style.show_node_ids)
            if label:
                attributes.append(label)
            attributes.append('label=""')
        else:
            attributes += [
                f'width={style.env_node_size}',
                f'height={style.env_node_size}',
                f'fontsize={style.font_size}',
            ]
            label = state.get_state_label(show_node_id=style.show_node_ids)
            if label:
                attributes.append(label)
            if is_trap:
                attributes += ['style=filled', 'fillcolor="#ffb347"', 'penwidth=3.5']

        dot += f'  "{state_name}" [{", ".join(attributes)}];\n'

    stub_ids = set()
    for state_name, state in mealy.states.items():
        if state_name not in keep_names:
            continue
        for target in state.trans:
            if target not in keep_names and target not in stub_ids:
                dot += _stub_node(target, style)
                stub_ids.add(target)
            color = (
                style.sys_choice_edge_color if not state_name.endswith('_sys')
                else style.env_choice_edge_color
            )
            dot += f'  "{state_name}" -> "{target}" [color="{color}"];\n'

    # Predecessors of kept states that were not themselves kept (typically the
    # context nodes, one hop back from the trap) would otherwise be drawn as
    # roots with no incoming edge, hiding the fact that they -- and hence the
    # whole excerpt -- are reached from the rest of a much larger strategy.
    # Mirror the outgoing-stub treatment above, but for the reverse direction:
    # a small "elsewhere" stub per external in-edge, so the excerpt reads as
    # a cut-out, not the full strategy.
    reverse = {}
    for node, succs in adjacency.items():
        for target in succs:
            reverse.setdefault(target, set()).add(node)

    incoming_stub_ids = set()
    for raw_id in keep_ids:
        for pred in sorted(reverse.get(raw_id, ()), key=int):
            if pred in keep_id_set:
                continue
            stub_name = f'{pred}_in_{raw_id}'
            if stub_name not in incoming_stub_ids:
                dot += _stub_node(stub_name, style)
                incoming_stub_ids.add(stub_name)
            dot += (
                f'  "{stub_name}" -> "{raw_id}" '
                f'[color="{style.env_choice_edge_color}"];\n'
            )

    dot += '}\n'
    return Mealy.draw_graph(dot, out_base)


def build_arg_parser():
    """Build the argparse parser for the trap_excerpt CLI."""
    parser = argparse.ArgumentParser(
        description=(
            'Find and render a goal-unreachable-trap SCC excerpt from a Slugs strategy.'
        ),
    )
    parser.add_argument('specs_file', help='Path to the .slugsin specification file')
    parser.add_argument('auton_file', help='Path to the Slugs strategy JSON file')
    parser.add_argument(
        '--goal-var',
        default='finished',
        help="Boolean output variable marking goal states (default: 'finished')",
    )
    parser.add_argument(
        '--initial',
        default='0',
        help="Initial raw state id (default: '0', matching Slugs convention)",
    )
    parser.add_argument(
        '--context-hops',
        type=int,
        default=1,
        help='Predecessor hops of context to include around the trap (default: 1)',
    )
    parser.add_argument(
        '--trap-index',
        type=int,
        default=None,
        help='Which trap to render (0-based, smallest first). Default: smallest.',
    )
    parser.add_argument(
        '--list-traps',
        action='store_true',
        help='List all found traps and exit without rendering.',
    )
    parser.add_argument(
        '--out',
        default=None,
        help='Output basename for .dot/.pdf/.png (default: <strategy>_trap)',
    )
    return parser


def main():
    """Entry point: find trap SCCs and render a highlighted excerpt."""
    args = build_arg_parser().parse_args()

    auton = load_automata(args.auton_file)
    sccs, trap_indices, adjacency = find_traps(auton, args.goal_var, args.initial)

    if not trap_indices:
        print('No goal-unreachable trap found in the reachable strategy graph.')
        return 0

    # Tie-break on the sorted member-id tuple, not the scc index `i` -- `i`
    # depends only on discovery order, which is now stable within a single
    # process (see `find_traps`) but need not match some other convention;
    # sorting on content keeps `--trap-index` meaning "the Nth-smallest trap,
    # ties broken by its lowest-numbered state" independent of that detail.
    ordered = sorted(trap_indices, key=lambda i: (len(sccs[i]), sorted(sccs[i], key=int)))
    if args.list_traps:
        print(f'Found {len(ordered)} goal-unreachable trap SCC(s):')
        for rank, i in enumerate(ordered):
            states = sorted(sccs[i], key=int)
            print(f'  [{rank}] scc#{i} size={len(states)} states={states}')
        return 0

    choice = args.trap_index if args.trap_index is not None else 0
    if not 0 <= choice < len(ordered):
        print(f'--trap-index {choice} out of range; found {len(ordered)} trap(s).',
              file=sys.stderr)
        return 1
    trap_ids = sorted(sccs[ordered[choice]], key=int)

    context = context_predecessors(adjacency, set(trap_ids), args.context_hops)
    keep_ids = trap_ids + sorted(context, key=int)

    out_base = args.out or args.auton_file.rsplit('.', 1)[0] + '_trap'
    print(f'Rendering trap states {trap_ids} with context {sorted(context, key=int)} ...')
    render_excerpt(args.specs_file, args.auton_file, keep_ids, trap_ids, adjacency, out_base)
    return 0


if __name__ == '__main__':
    sys.exit(main())
