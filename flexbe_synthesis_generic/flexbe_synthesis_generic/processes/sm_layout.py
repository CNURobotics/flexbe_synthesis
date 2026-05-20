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

"""Assign graph-based positions to synthesized FlexBE states."""

from collections import defaultdict, deque
import os
import traceback

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode

try:
    import pygraphviz as pgv
    _PYGRAPHVIZ_AVAILABLE = True
except ImportError:
    pgv = None
    _PYGRAPHVIZ_AVAILABLE = False

# Graphviz outputs node positions in points (1 pt = 1/72 inch) with coordinates
# at the node centre.  Half of 72 dpi converts centre-based pt coordinates to the
# top-left origin that FlexBE's UI expects.
_GRAPHVIZ_HALF_DPI = 36.0

# Fallback layout constants (editor canvas pixels, matching flexbe_webui defaults).
_LAYOUT_INIT_NODE = '__flexbe_synthesis_init__'
_LAYOUT_STATE_W, _LAYOUT_STATE_H = 170, 95
_LAYOUT_OUTCOME_W, _LAYOUT_OUTCOME_H = 90, 50
_LAYOUT_GAP_X, _LAYOUT_GAP_Y = 130, 80
_LAYOUT_MARGIN_X, _LAYOUT_MARGIN_Y = 80, 60


def _tarjan_scc(nodes, adjacency):
    """Return strongly-connected components (iterative Tarjan, stdlib only)."""
    index_counter = 0
    stack = []
    on_stack = set()
    indices = {}
    lowlinks = {}
    components = []

    for root in nodes:
        if root in indices:
            continue
        indices[root] = index_counter
        lowlinks[root] = index_counter
        index_counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(adjacency.get(root, [])))]

        while work:
            node, nbrs = work[-1]
            try:
                neighbor = next(nbrs)
            except StopIteration:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlinks[parent] = min(lowlinks[parent], lowlinks[node])
                if lowlinks[node] == indices[node]:
                    component = []
                    while stack:
                        member = stack.pop()
                        on_stack.remove(member)
                        component.append(member)
                        if member == node:
                            break
                    components.append(component)
                continue

            if neighbor not in indices:
                indices[neighbor] = index_counter
                lowlinks[neighbor] = index_counter
                index_counter += 1
                stack.append(neighbor)
                on_stack.add(neighbor)
                work.append((neighbor, iter(adjacency.get(neighbor, []))))
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

    return components


def _neighbor_barycenter(name, neighbors, rank_lookup, order_lookup, target_rank):
    """Return the average order of neighbors at target_rank, or None if none exist."""
    relevant = [
        order_lookup[nb]
        for nb in neighbors.get(name, [])
        if nb in order_lookup and rank_lookup.get(nb) == target_rank
    ]
    return sum(relevant) / len(relevant) if relevant else None


def _fallback_layout(states):
    """
    Rank-based layout when pygraphviz is unavailable.

    Ports the core of flexbe_webui's compute_auto_layout to work directly with
    StateInstantiation objects using stdlib only.  Updates state.position[] in-place
    for states[1:]; states[0] is the root record and is skipped.

    Algorithm (matches flexbe_webui auto_layout):
      1. Build adjacency from state transitions.
      2. Collapse SCCs (Tarjan) so cycles rank as one unit.
      3. Topological-sort the condensed DAG to assign left-to-right ranks.
      4. Force SM-level outcome strings to a final rank.
      5. Refine within-rank order via forward and backward barycenter passes.
      6. Pin the initial state to the top of its rank.
      7. Convert rank + order to editor-canvas (x, y) pixel positions.
    """
    if len(states) < 2:
        return

    root = states[0]
    actual_states = states[1:]
    initial_name = root.initial_state_name
    machine_outcome_set = set(root.outcomes)

    state_names = [s.state_path.split('/')[-1] for s in actual_states]
    all_names = set(state_names) | machine_outcome_set

    adjacency = defaultdict(list)
    reverse_adjacency = defaultdict(list)

    if initial_name and initial_name in all_names:
        adjacency[_LAYOUT_INIT_NODE].append(initial_name)
        reverse_adjacency[initial_name].append(_LAYOUT_INIT_NODE)

    for state, name in zip(actual_states, state_names):
        for target in state.transitions:
            if target in all_names:
                adjacency[name].append(target)
                reverse_adjacency[target].append(name)

    for name in all_names:
        adjacency.setdefault(name, [])
        reverse_adjacency.setdefault(name, [])

    # SCC collapse
    components = _tarjan_scc(all_names, adjacency)
    component_by_node = {node: idx for idx, comp in enumerate(components) for node in comp}

    comp_graph = defaultdict(set)
    rev_comp_graph = defaultdict(set)
    indegree = {i: 0 for i in range(len(components))}
    for name in state_names:
        for target in adjacency.get(name, []):
            sc, dc = component_by_node[name], component_by_node[target]
            if sc == dc or dc in comp_graph[sc]:
                continue
            comp_graph[sc].add(dc)
            rev_comp_graph[dc].add(sc)
            indegree[dc] += 1

    # Topological sort of condensed DAG → rank assignment
    queue = deque(sorted(i for i, d in indegree.items() if d == 0))
    topo_order = []
    work_indegree = indegree.copy()
    while queue:
        ci = queue.popleft()
        topo_order.append(ci)
        for nb in sorted(comp_graph.get(ci, [])):
            work_indegree[nb] -= 1
            if work_indegree[nb] == 0:
                queue.append(nb)
    if len(topo_order) != len(components):
        topo_order = list(range(len(components)))

    comp_rank = {}
    for ci in topo_order:
        pred_ranks = [comp_rank[p] for p in rev_comp_graph.get(ci, set()) if p in comp_rank]
        comp_rank[ci] = (max(pred_ranks) + 1) if pred_ranks else 0

    node_rank = {name: comp_rank[component_by_node[name]] for name in all_names}

    # Force SM-level outcomes to a dedicated final rank
    if machine_outcome_set:
        outcome_rank = max((node_rank[n] for n in state_names), default=0) + 1
        for name in machine_outcome_set:
            node_rank[name] = outcome_rank

    all_ranked = defaultdict(list)
    for name in all_names:
        all_ranked[node_rank[name]].append(name)

    # Seed within-rank order deterministically; initial state pinned to position 0
    order_lookup = {}
    for rank, names in all_ranked.items():
        for order, name in enumerate(sorted(names, key=lambda n: (n != initial_name, n))):
            order_lookup[name] = order

    sorted_ranks = sorted(all_ranked.keys())

    # Forward barycenter pass (left-to-right)
    for rank in sorted_ranks[1:]:
        names = all_ranked[rank]
        names.sort(key=lambda n: (
            *((bc := _neighbor_barycenter(n, reverse_adjacency, node_rank, order_lookup, rank - 1))
              is None, 0.0 if bc is None else bc),
            n,
        ))
        for order, name in enumerate(names):
            order_lookup[name] = order

    # Backward barycenter pass (right-to-left)
    for rank in reversed(sorted_ranks[:-1]):
        names = all_ranked[rank]
        names.sort(key=lambda n: (
            *((bc := _neighbor_barycenter(n, adjacency, node_rank, order_lookup, rank + 1))
              is None, 0.0 if bc is None else bc),
            n,
        ))
        for order, name in enumerate(names):
            order_lookup[name] = order

    # Re-pin initial state after barycenter passes
    if initial_name and initial_name in node_rank:
        rank_list = all_ranked[node_rank[initial_name]]
        idx = next((i for i, n in enumerate(rank_list) if n == initial_name), None)
        if idx is not None and idx > 0:
            rank_list.insert(0, rank_list.pop(idx))
            for order, name in enumerate(rank_list):
                order_lookup[name] = order

    # x position: one column per rank
    cursor_x = float(_LAYOUT_MARGIN_X)
    x_offsets = {}
    for rank in sorted_ranks:
        x_offsets[rank] = cursor_x
        w = (_LAYOUT_OUTCOME_W
             if all(n in machine_outcome_set for n in all_ranked[rank])
             else _LAYOUT_STATE_W)
        cursor_x += w + _LAYOUT_GAP_X

    # y position: stack nodes within each column by order
    pos_y_by_name = {}
    for rank in sorted_ranks:
        cursor_y = float(_LAYOUT_MARGIN_Y)
        for name in sorted(all_ranked[rank], key=lambda n: order_lookup[n]):
            pos_y_by_name[name] = cursor_y
            h = _LAYOUT_OUTCOME_H if name in machine_outcome_set else _LAYOUT_STATE_H
            cursor_y += h + _LAYOUT_GAP_Y

    for state, name in zip(actual_states, state_names):
        state.position[0] = x_offsets[node_rank[name]]
        state.position[1] = pos_y_by_name[name]


def _write_fallback_dot(states, graph_path):
    """
    Write a DOT graph for fallback-layout runs.

    Canvas pixel positions (top-left origin) are converted to Graphviz point
    coordinates (node centre, 72 dpi) by adding half the node dimensions.
    At dpi=72 one editor pixel equals one point, so no additional scaling is needed.
    """
    with open(graph_path + '.dot', 'w', encoding='utf-8') as dot_file:
        dot_file.write('digraph state_machine {\n')
        dot_file.write('  rankdir=LR;\n')
        dot_file.write('  dpi=72;\n')

        if not states:
            dot_file.write('}\n')
            return

        root = states[0]
        machine_outcomes = set(root.outcomes)
        if root.initial_state_name:
            dot_file.write(f'  "/" -> "{root.initial_state_name}";\n')
        for outcome in sorted(machine_outcomes):
            dot_file.write(f'  "{outcome}" [style=filled, fillcolor=lightgray];\n')

        half_w = _LAYOUT_STATE_W / 2
        half_h = _LAYOUT_STATE_H / 2
        for state in states[1:]:
            state_name = state.state_path.split('/')[-1]
            cx = state.position[0] + half_w
            cy = state.position[1] + half_h
            dot_file.write(f'  "{state_name}" [shape=box, pos="{cx},{cy}!"];\n')
            for index, target in enumerate(state.transitions):
                label = state.outcomes[index] if index < len(state.outcomes) else ''
                dot_file.write(f'  "{state_name}" -> "{target}" [label="{label}"];\n')

        dot_file.write('}\n')


class SM_Layout(BaseProcess):
    """Compute state layout using Graphviz and embed positions in states."""

    synthesized_state_machine: list[StateInstantiation]
    specs_output_dir_path: str
    use_fallback_layout: bool = False

    class Config:
        """Allow pydantic to accept ROS message types."""

        arbitrary_types_allowed = True

    def process(self):
        """Return positioned states and synthesis success code."""
        try:
            if not _PYGRAPHVIZ_AVAILABLE or self.use_fallback_layout:
                reason = (
                    'pygraphviz not available'
                    if not _PYGRAPHVIZ_AVAILABLE
                    else 'use_fallback_layout=True'
                )
                print(
                    f'sm_layout: {reason}, using fallback rank-based layout.',
                    flush=True,
                )
                _fallback_layout(self.synthesized_state_machine)
                if self.specs_output_dir_path:
                    graph_path = os.path.join(self.specs_output_dir_path, 'state_machine')
                    print(
                        f"    Saving fallback graph data in '{graph_path}.dot' ...",
                        flush=True,
                    )
                    _write_fallback_dot(self.synthesized_state_machine, graph_path)
                    print('    Fallback layout does not generate a PNG graph.', flush=True)
                return [
                    self.synthesized_state_machine,
                    SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
                ]
            print(
                (
                    'Inside the sm_layout process with '
                    f'{len(self.synthesized_state_machine)} states ...'
                ),
                flush=True,
            )

            dpi = 72
            screen_size = (1200, 780)
            basic_height = 50
            basic_width = 75
            basic_height_inches = basic_height / dpi
            basic_width_inches = basic_width / dpi

            graph = pgv.AGraph(strict=False, directed=True)
            graph.graph_attr['bb'] = f'0,0,{screen_size[0]},{screen_size[1]}'
            graph.graph_attr['dpi'] = f'{dpi}'
            graph.graph_attr['ratio'] = 'fill'
            graph.graph_attr['overlap'] = 'false'
            graph.graph_attr['overlap_scaling'] = '1.5'
            graph.graph_attr['layout'] = 'dot'
            graph.graph_attr['nodesep'] = '1.5'
            graph.graph_attr['ranksep'] = '1.5'
            graph.graph_attr['splines'] = 'polyline'
            graph.graph_attr['esep'] = '5'
            graph.graph_attr['sep'] = '+5'
            graph.graph_attr['orientation'] = 'landscape'
            graph.graph_attr['rankdir'] = 'LR'
            graph.graph_attr['pack'] = 'false'
            graph.graph_attr['packmode'] = 'clust'
            graph.graph_attr['fontname'] = 'Liberation Sans'
            graph.graph_attr['fontweight'] = 'bold'
            graph.node_attr.update(
                {'fontname': 'Liberation Sans', 'fontweight': 'bold', 'penwidth': '2'}
            )
            graph.edge_attr.update(
                {'fontname': 'Liberation Sans', 'fontweight': 'bold', 'penwidth': '2'}
            )

            machine_outcomes = []
            interior_states = []
            for index, state in enumerate(self.synthesized_state_machine):
                state_path = state.state_path.split('/')
                state_name = state_path[-1]
                if len(state_path) > 2:
                    print(
                        f"Non-flat SM '{state.state_path}' - only one layer is handled for now."
                    )

                if index == 0:
                    if self.verbose:
                        print(
                            (
                                f'    {index:3d}: {state_name} initial state '
                                f'{state.initial_state_name} SM outcomes: {state.outcomes}'
                            ),
                            flush=True,
                        )
                    graph.add_edge('/', state.initial_state_name, weight='100')
                    root = graph.get_node('/')
                    root.attr['color'] = 'black'
                    root.attr['fillcolor'] = 'black'
                    root.attr['fill'] = 'true'
                    root.attr['width'] = '0.1'
                    root.attr['height'] = '0.1'
                    graph.add_subgraph(['/', state.initial_state_name], rank='min')

                    machine_outcomes = sorted(state.outcomes)
                    for out in machine_outcomes:
                        graph.add_node(out)
                        graph.get_node(out).attr['fillcolor'] = 'lightgray'
                        graph.get_node(out).attr['fill'] = 'true'
                    graph.add_subgraph(machine_outcomes, rank='max')
                    continue

                if self.verbose:
                    print(
                        f'    {index:3d}: {state_name} transitions: {state.transitions}',
                        flush=True,
                    )
                interior_states.append(state_name)
                for ndx, trans in enumerate(state.transitions):
                    edge_weight = '50' if trans in machine_outcomes else '1'
                    graph.add_edge(
                        state_name,
                        trans,
                        label=f'{state.outcomes[ndx]}',
                        weight=edge_weight,
                    )

                node = graph.get_node(state_name)
                node.attr['label'] = state_name
                node.attr['color'] = 'black'
                node.attr['shape'] = 'box'
                node.attr['width'] = f'{basic_width_inches}'
                node.attr['height'] = f'{basic_height_inches}'
                node.attr['labeljust'] = 'c'

                parameter_text = ''
                for ndx, key in enumerate(state.parameter_names):
                    parameter_text += f'{key}={state.parameter_values[ndx]}\n'
                if parameter_text:
                    node.attr['xlabel'] = parameter_text

            subgraph = graph.add_subgraph(interior_states)
            subgraph.graph_attr['ranksep'] = '1.5'
            subgraph.graph_attr['nodesep'] = '2.0'

            print('    Process graph layout ...', flush=True)
            graph.layout()

            if self.specs_output_dir_path:
                graph_path = os.path.join(self.specs_output_dir_path, 'state_machine')
                print(f"    Saving output graph data in '{graph_path}' ...", flush=True)
                graph.write(graph_path + '.dot')
                graph.draw(graph_path + '.png')

            extents = graph.graph_attr['bb']
            xmin, ymin, xmax, ymax = map(float, extents.split(','))
            del xmin, ymin

            print(
                f'    Extract graph layout positions from final BB={(xmax, ymax)} ...',
                flush=True,
            )
            for index, state in enumerate(self.synthesized_state_machine):
                if index == 0:
                    continue
                state_name = state.state_path.split('/')[-1]
                node = graph.get_node(state_name)
                pos_attr = node.attr['pos']
                if not pos_attr:
                    continue

                x, y = map(float, pos_attr.split(','))
                width_in = float(node.attr['width'])
                height_in = float(node.attr['height'])
                state.position[0] = x - width_in * _GRAPHVIZ_HALF_DPI
                state.position[1] = (ymax - y) - height_in * _GRAPHVIZ_HALF_DPI

            error_code = SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)
            print(
                (
                    'Returning from the sm_layout process with '
                    f'{len(self.synthesized_state_machine)} states and {error_code}.'
                ),
                flush=True,
            )
            return [self.synthesized_state_machine, error_code]
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            print(exc)
            traceback.print_exc()
            return [
                [],
                SynthesisErrorCode(value=SynthesisErrorCode.SM_GENERATION_FAILED),
            ]


def main(inputs):
    """Create sm-layout process for pipeline execution."""
    return SM_Layout(
        name='SM Layout',
        synthesized_state_machine=inputs[0],
        specs_output_dir_path=inputs[1] if len(inputs) > 1 else '',
        use_fallback_layout=inputs[2] if len(inputs) > 2 else False,
    )
