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

"""Audit Slugs strategy automata against semantic progress expectations."""

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.strategy_auditor import (
    default_spec_path,
    PROTOCOL_DISABLED_REDUCED_WARNING,
    PROTOCOL_DISABLED_SHAPE_WARNING,
    StrategyAuditor,
)


# Imported from helpers.strategy_auditor rather than duplicated as literal text,
# so a future wording edit to those warnings can't silently desync this filter.
TERMINAL_ONLY_WARNINGS = (
    PROTOCOL_DISABLED_REDUCED_WARNING,
    PROTOCOL_DISABLED_SHAPE_WARNING,
)


class StrategyAuditorProcess(BaseProcess):
    """Pipeline wrapper for explicit-state strategy auditing."""

    synthesized_automaton: dict
    specs_output_dir_path: str
    spec_name: str
    system_capabilities: dict
    state_mappings: dict
    slugs_specification: dict
    strategy_auditor_spec_path: str
    strategy_auditor_goal_outcomes: list
    strategy_auditor_timeout_s: float

    def process(self):
        """Run the strategy audit and return `[result, error_code]`."""
        spec_path = self.strategy_auditor_spec_path
        if not spec_path:
            spec_path = default_spec_path(self.specs_output_dir_path, self.spec_name)

        print(
            f"\033[32mStarting StrategyAuditor for '{self.spec_name}' ...\033[0m",
            flush=True,
        )
        print(f"    compiled spec: '{spec_path}'", flush=True)
        print(
            f'    timeout: {self.strategy_auditor_timeout_s:g}s',
            flush=True,
        )

        auditor = StrategyAuditor(timeout_s=self.strategy_auditor_timeout_s)
        result = auditor.audit(
            self.synthesized_automaton,
            spec_path,
            self.system_capabilities,
            self.state_mappings,
            self.slugs_specification,
            self.strategy_auditor_goal_outcomes,
        )
        pipeline_warnings = []
        for warning in result.get('warnings', []):
            if warning in TERMINAL_ONLY_WARNINGS:
                print(f'\033[33m    {warning}\033[0m', flush=True)
            else:
                pipeline_warnings.append(warning)
        result['warnings'] = pipeline_warnings
        self.messages.extend(pipeline_warnings)

        if result.get('incomplete'):
            print(
                '\033[33mStrategyAuditor timed out; audit incomplete, '
                'result unverified.\033[0m',
                flush=True,
            )
            return [result, SynthesisErrorCode(value=SynthesisErrorCode.AUDIT_INCOMPLETE)]

        if not result.get('valid'):
            print(
                '\033[31mStrategyAuditor found invalid strategy semantics: '
                f"{result.get('failure_kind')} - {result.get('message')}\033[0m",
                flush=True,
            )
            return [result, SynthesisErrorCode(value=SynthesisErrorCode.AUTOMATON_INVALID)]

        print('\033[32mStrategyAuditor passed.\033[0m', flush=True)
        return [result, SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]


def main(inputs):
    """Create the strategy-auditor process for pipeline execution."""
    return StrategyAuditorProcess(
        name='StrategyAuditor',
        synthesized_automaton=inputs[0],
        specs_output_dir_path=inputs[1],
        spec_name=inputs[2],
        system_capabilities=inputs[3],
        state_mappings=inputs[4],
        slugs_specification=inputs[5],
        strategy_auditor_spec_path=inputs[6],
        strategy_auditor_goal_outcomes=inputs[7],
        strategy_auditor_timeout_s=inputs[8],
    )
