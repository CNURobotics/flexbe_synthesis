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

"""Run Slugs synthesis and return automaton + error code."""

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.slugs_synthesizer_helper import (
    DEFAULT_SLUGS_TIMEOUT_S,
    SlugsSynthesizerHelper,
)
from pydantic import PrivateAttr


class SlugsSynthesizer(BaseProcess):
    """Wrapper around `SlugsSynthesizerHelper` used by the pipeline."""

    specs_output_dir_path: str
    state_mappings: dict
    synthesis_timeout_s: float = DEFAULT_SLUGS_TIMEOUT_S
    _synthesizer: SlugsSynthesizerHelper | None = PrivateAttr(default=None)

    def process(self):
        """Execute synthesis and print a concise status report."""
        print('\033[32mStarting slugs synthesizer ...\033[0m', flush=True)
        synthesizer = SlugsSynthesizerHelper(
            self.specs_output_dir_path,
            self.state_mappings['transition_outcomes'],
            self.state_mappings['sm_outcome_mappings'],
            verbose=self.verbose,
            show_slugs_output=True,
            slugs_timeout_s=self.synthesis_timeout_s,
        )
        self._synthesizer = synthesizer

        automaton, error_code = synthesizer.handle_slugs_synthesis()
        if automaton.size() > 0:
            print(20 * 'v', 'Synthesized Automaton', 20 * 'v', flush=True)
            print(automaton, flush=True)
            print(
                (
                    f'\033[32mFinished slugs synthesizer with '
                    f'{automaton.size()} states.\033[0m'
                ),
                flush=True,
            )
        else:
            print(
                (
                    f'\033[31m Failed slugs synthesis with ec={error_code.value} '
                    f'(size={automaton.size()}).\033[0m'
                ),
                flush=True,
            )

        return [automaton.to_dict(), error_code]

    def cancel(self):
        """Cancel Slugs synthesis if the external solver is still running."""
        if self._synthesizer is not None:
            self._synthesizer.cancel()


def main(inputs):
    """Create the slugs synthesizer process."""
    synthesis_timeout_s = inputs[2] if len(inputs) > 2 else DEFAULT_SLUGS_TIMEOUT_S
    return SlugsSynthesizer(
        name='Synthesizer',
        specs_output_dir_path=inputs[0],
        state_mappings=inputs[1],
        synthesis_timeout_s=synthesis_timeout_s,
    )
