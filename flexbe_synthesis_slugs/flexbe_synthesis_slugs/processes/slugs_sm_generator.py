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

"""Generate FlexBE state-machine definitions from synthesized Slugs automata."""

import traceback

from flexbe_msgs.msg import StateInstantiation
from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_util import new_si
from flexbe_synthesis_slugs.helpers.sm_generation_helpers import SMGenerationHelpers


class SM_Generator(BaseProcess):
    """Pipeline process wrapper around `SMGenerationHelpers`."""

    synthesized_automaton: dict
    system_capabilities_name: str

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    def process(self):
        """Build state instantiations and append explicit outcome pseudo-states."""
        try:
            sm_gen = SMGenerationHelpers()
            state_defs, error_code, gen_messages = sm_gen.generate_sm(
                self.synthesized_automaton,
                self.system_capabilities_name,
                verbose=self.verbose,
            )
            self.messages.extend(gen_messages)

            if not state_defs:
                print('\033[38;5;208m Error: No states generated! \033[0m', flush=True)
                if error_code == SynthesisErrorCode.SUCCESS:
                    error_code = SynthesisErrorCode.AUTOMATON_INVALID
                return [[], SynthesisErrorCode(value=error_code)]

            if self.verbose:
                print('SM Generator finished!', flush=True)
            top_level = state_defs[0]
            for out in top_level.outcomes:
                if self.verbose:
                    print(f"    add state for outcome '{out}'")
                out_state = new_si(
                    out,
                    StateInstantiation.CLASS_OUTCOME,
                    '',
                    [],
                    [],
                    '',
                    {},
                    [],
                )
                state_defs.append(out_state)

            return [state_defs, SynthesisErrorCode(value=error_code)]

        except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
            print(f'slugs_sm_generation Error: {exc}', flush=True)
            traceback.print_exc()
            self.messages.append(
                f'SM generation failed: {type(exc).__name__}: {exc}'
            )
            return [[], SynthesisErrorCode(value=SynthesisErrorCode.SM_GENERATION_FAILED)]


def main(inputs):
    """Create process instance for pipeline usage."""
    return SM_Generator(
        name='SM Generator',
        synthesized_automaton=inputs[0],
        system_capabilities_name=inputs[1],
    )
