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

"""Load a pre-synthesized Slugs automaton from YAML into message-compatible form."""

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.slugs_automaton import SlugsAutomaton
import yaml


class SlugsAutomatonLoader(BaseProcess):
    """Load and validate a serialized automaton from disk."""

    automaton_path: str

    def process(self):
        """Load automaton YAML and return `[automaton_dict, error_code]`."""
        print(
            f"\033[32mLoading slugs automaton from '{self.automaton_path}' ...\033[0m",
            flush=True,
        )

        try:
            with open(self.automaton_path, encoding='utf-8') as fin:
                data = yaml.safe_load(fin)

            if data is None:
                print(
                    f"Error loading pre-synthesized automaton from '{self.automaton_path}'",
                    flush=True,
                )
                return [
                    SlugsAutomaton().to_dict(),
                    SynthesisErrorCode(value=SynthesisErrorCode.AUTOMATON_INVALID),
                ]

            if not isinstance(data, dict):
                print(
                    f"Data from '{self.automaton_path}' is not a valid SlugsAutomaton!",
                    flush=True,
                )
                return [
                    SlugsAutomaton().to_dict(),
                    SynthesisErrorCode(value=SynthesisErrorCode.AUTOMATON_INVALID),
                ]

            try:
                sa = SlugsAutomaton.from_dict(data)
            except (KeyError, TypeError, ValueError) as exc:
                print(
                    f"Data from '{self.automaton_path}' has invalid automaton data: {exc}",
                    flush=True,
                )
                return [
                    SlugsAutomaton().to_dict(),
                    SynthesisErrorCode(value=SynthesisErrorCode.AUTOMATON_INVALID),
                ]

            return [sa.to_dict(), SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]

        except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            print(f'Error loading pre-synthesized automaton!\n    {exc}', flush=True)

        return [
            SlugsAutomaton().to_dict(),
            SynthesisErrorCode(value=SynthesisErrorCode.AUTOMATON_INVALID),
        ]


def main(inputs):
    """Create process instance for pipeline usage."""
    return SlugsAutomatonLoader(
        name='SlugsAutomatonLoader',
        automaton_path=inputs[0],
    )


if __name__ == '__main__':
    """Stand-alone test entry point."""
    import os

    from ament_index_python.packages import get_package_share_directory

    package_path = get_package_share_directory('flexbe_synthesis_slugs')
    print(package_path)

    automaton_path = os.path.join(package_path, 'example', 'slugs', 'vending_demo.yaml')
    print(f"Try to load automaton from '{automaton_path}' ...", flush=True)
    loader = main([automaton_path])
    automaton, code = loader.process()

    print(automaton)
    print(code)
