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

"""Small graph algorithms shared by synthesis pipeline stages."""


def tarjan_scc(nodes, adjacency):
    """Return strongly-connected components using iterative Tarjan."""
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
