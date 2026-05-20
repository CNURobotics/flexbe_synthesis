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

"""Export synthesized Slugs automata to DOT/graph artifacts."""

import os
import traceback

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
import flexbe_synthesis_slugs.helpers.mealy2dot as mealy2dot
from flexbe_synthesis_slugs.helpers.slugs_automaton import SlugsAutomaton
from pydantic import Field


class SlugsMealyGraph(BaseProcess):
    """Create a Mealy-graph representation for a synthesized automaton."""

    synthesized_automaton: dict
    output_dir_path: str
    file_name: str
    draw_graph: bool
    graph_config: dict = Field(default_factory=dict)

    def _graph_style(self):
        """Build GraphStyle from optional pipeline configuration."""
        return mealy2dot.GraphStyle(
            font=self.graph_config.get('font', mealy2dot.GraphStyle.font),
            font_weight=self.graph_config.get(
                'font_weight',
                mealy2dot.GraphStyle.font_weight,
            ),
            font_size=self.graph_config.get('font_size', mealy2dot.GraphStyle.font_size),
            penwidth=self.graph_config.get('penwidth', mealy2dot.GraphStyle.penwidth),
            env_node_size=self.graph_config.get(
                'env_node_size',
                mealy2dot.GraphStyle.env_node_size,
            ),
            sys_node_size=self.graph_config.get(
                'sys_node_size',
                mealy2dot.GraphStyle.sys_node_size,
            ),
            dpi=self.graph_config.get('dpi', mealy2dot.GraphStyle.dpi),
            show_node_ids=self.graph_config.get(
                'show_node_ids',
                mealy2dot.GraphStyle.show_node_ids,
            ),
            sys_choice_edge_color=self.graph_config.get(
                'sys_choice_edge_color',
                mealy2dot.GraphStyle.sys_choice_edge_color,
            ),
            env_choice_edge_color=self.graph_config.get(
                'env_choice_edge_color',
                mealy2dot.GraphStyle.env_choice_edge_color,
            ),
        )

    def process(self):
        """Write DOT output and optionally render graph images."""
        try:
            sa = SlugsAutomaton.from_dict(self.synthesized_automaton)
            print(f'Starting with {sa} ...', flush=True)

            mealy = mealy2dot.Mealy.mealy_from_slugs_automaton(sa)
            dot_str = mealy.to_dot(
                layout=self.graph_config.get('layout', 'dot'),
                splines=self.graph_config.get('splines', True),
                initial_state=self.graph_config.get('initial_state', True),
                style=self._graph_style(),
            )

            base_file_path = os.path.join(self.output_dir_path, self.file_name)
            print(f"Save dot as text file to '{base_file_path}' ...", flush=True)
            with open(base_file_path + '.dot', 'w', encoding='utf-8') as file:
                file.write(dot_str)

            if self.draw_graph:
                mealy.draw_graph(dot_str, base_file_path)
            else:
                print(
                    '\033[32m Skipping drawing Slugs Mealy graph\n'
                    f'   Consider using `dot -Tpdf -Tpng -O {base_file_path}.dot` '
                    '\033[0m',
                    flush=True,
                )

            return [SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]

        except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
            print(f'slugs_sm_generation Error: {exc}', flush=True)
            traceback.print_exc()
            return [SynthesisErrorCode(value=SynthesisErrorCode.FAILURE)]


def main(inputs):
    """Create process instance for pipeline usage."""
    file_name = inputs[2] if len(inputs) > 2 else 'slugs_automaton'
    graph_config = inputs[3] if len(inputs) > 3 else {}

    return SlugsMealyGraph(
        name='SlugsMealyGraph',
        synthesized_automaton=inputs[0],
        output_dir_path=inputs[1],
        file_name=file_name,
        draw_graph=bool(graph_config.get('draw_graph', False)),
        graph_config=graph_config,
    )


if __name__ == '__main__':
    """Stand-alone test file."""
    from ament_index_python.packages import get_package_share_directory
    from flexbe_synthesis_slugs.processes.slugs_automaton_loader import (
        main as loader_main,
    )

    package_path = get_package_share_directory('pyrobosim_flexbe_synthesis')
    print(package_path)

    automaton_path = os.path.join(
        package_path,
        'slugs',
        'pyrobosim_slugs_p0_automaton.yaml',
    )
    print(f"Try to load automaton from '{automaton_path}' ...", flush=True)
    loader = loader_main([automaton_path])
    automaton, code = loader.process()
    print(f"{len(automaton['automaton'])} states in loaded automaton")
    print(code)

    print('Try saving automaton as dot ...', flush=True)
    out_path = os.path.join(
        os.path.expanduser('~'),
        '.flexbe_p0_automatonsynthesis/pyrobosim_demo/pyrobosim',
    )
    try:
        mealy = main([automaton, out_path, 'p0_automaton'])
        code2 = mealy.process()
        print(code2)
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        print(exc)
        traceback.print_exc()
