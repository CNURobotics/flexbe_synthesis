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

"""Load a hand-written state machine definition YAML into StateInstantiation messages."""

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
import yaml


class SMLoader(BaseProcess):
    """Deserialize a hand-written SM definition YAML into a StateInstantiation list."""

    automaton_path: str

    def process(self):
        """Load SM YAML and return ``[state_defn, error_code]``."""
        print(f"\033[32mLoading SM definition from '{self.automaton_path}' ...\033[0m", flush=True)

        try:
            with open(self.automaton_path, encoding='utf-8') as fin:
                data = yaml.safe_load(fin)
        except (OSError, yaml.YAMLError) as exc:
            print(f'SMLoader: failed to read SM file: {exc}', flush=True)
            return [[], SynthesisErrorCode(value=SynthesisErrorCode.SM_GENERATION_FAILED)]

        if not isinstance(data, dict) or 'sm' not in data or 'states' not in data:
            print(
                f"SMLoader: '{self.automaton_path}' must have top-level 'sm' and 'states' keys.",
                flush=True,
            )
            return [[], SynthesisErrorCode(value=SynthesisErrorCode.SM_GENERATION_FAILED)]

        try:
            sm_info = data['sm']
            sm_outcomes = list(sm_info.get('outcomes', []))
            initial_state = sm_info.get('initial_state', '')

            root = StateInstantiation()
            root.state_path = '/'
            root.state_class = StateInstantiation.CLASS_STATEMACHINE
            root.behavior_class = ''
            root.outcomes = sm_outcomes
            root.transitions = []
            root.initial_state_name = initial_state
            root.parameter_names = []
            root.parameter_values = []
            root.autonomy = []

            state_defn = [root]

            for state_data in data['states']:
                si = StateInstantiation()
                si.state_path = '/' + state_data['name']
                si.state_class = state_data.get('state_class', '')
                si.behavior_class = state_data.get('behavior_class', '')
                si.outcomes = list(state_data.get('outcomes', []))
                si.transitions = list(state_data.get('transitions', []))
                si.initial_state_name = ''
                params = state_data.get('parameters', {})
                si.parameter_names = list(params.keys())
                si.parameter_values = [str(v) for v in params.values()]
                autonomy = state_data.get('autonomy', [])
                si.autonomy = [int(a) for a in autonomy]
                si.userdata_keys = list(state_data.get('userdata_keys', []))
                si.userdata_remapping = list(state_data.get('userdata_remapping', []))
                state_defn.append(si)
                print(
                    f"  loaded state '{si.state_path}' ({si.state_class}) "
                    f'outcomes={si.outcomes} -> {si.transitions}',
                    flush=True,
                )

            for outcome in sm_outcomes:
                pseudo = StateInstantiation()
                pseudo.state_path = outcome
                pseudo.state_class = StateInstantiation.CLASS_OUTCOME
                pseudo.behavior_class = ''
                pseudo.outcomes = []
                pseudo.transitions = []
                pseudo.initial_state_name = ''
                pseudo.parameter_names = []
                pseudo.parameter_values = []
                pseudo.autonomy = []
                state_defn.append(pseudo)

            print(
                f'SMLoader: loaded {len(state_defn)} state instantiations '
                f'(including {len(sm_outcomes)} outcome pseudo-state(s)).',
                flush=True,
            )
            return [state_defn, SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]

        except (KeyError, TypeError, ValueError) as exc:
            print(f'SMLoader: error building state instantiations: {exc}', flush=True)
            return [[], SynthesisErrorCode(value=SynthesisErrorCode.SM_GENERATION_FAILED)]


def main(inputs):
    """Create sm-loader process for pipeline execution."""
    return SMLoader(name='SM Loader', automaton_path=inputs[0])
