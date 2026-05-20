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

"""Map synthesis error codes to human-readable status text."""

from flexbe_synthesis_msgs.msg import SynthesisErrorCode

ERROR_CODE_MAP = {
    0: 'UNKNOWN',
    1: 'SUCCESS',
    -9999: 'FAILURE',
    -1: 'BEHAVIOR_SYNTHESIS_FAILED',
    -2: 'INVALID_REQUEST',
    -3: 'PIPELINE_INVALID',
    -4: 'MAPPING_INVALID',
    -5: 'USERDATA_INVALID',
    -9: 'PREEMPTED',
    -10: 'SPEC_COMPILATION_FAILED',
    -11: 'INVALID_COMPILER',
    -20: 'SYNTHESIS_FAILED',
    -21: 'SPEC_UNSYNTHESIZABLE',
    -22: 'INVALID_SYNTHESIZER',
    -30: 'SM_GENERATION_FAILED',
    -31: 'NO_SYSTEMS_FILE',
    -32: 'NO_SYSTEM_CONFIG',
    -33: 'SYSTEM_CONFIG_NOT_FOUND',
    -34: 'CONFIG_FILE_INVALID',
    -35: 'CONFIG_AUTONOMY_INVALID',
    -36: 'CONFIG_VARIABLE_CONFIG_INVALID',
    -37: 'AUTOMATON_INVALID',
    -38: 'AUTOMATON_NO_INITIAL_STATE',
    -39: 'AUTOMATON_NEXT_STATE_INVALID',
    -40: 'AUTOMATON_INPUT_VALUATION_INVALID',
    -41: 'AUTOMATON_OUTPUT_VALUATION_INVALID',
    -42: 'CONFIG_USERDATA_INVALID',
    -43: 'INVALID_SM_GENERATOR',
}


def get_error_code_text(ec):
    """Return text for a `SynthesisErrorCode` value or raw integer-like value."""
    if isinstance(ec, SynthesisErrorCode):
        return ERROR_CODE_MAP.get(ec.value, f'Unknown Error code ({ec.value})')

    try:
        return ERROR_CODE_MAP.get(int(ec), f'Unknown Error code ({ec})')
    except (TypeError, ValueError):
        return f'Unknown Error code ({ec})'


if __name__ == '__main__':
    for i in range(1, -51, -1):
        print(f'{i:3d} : {get_error_code_text(SynthesisErrorCode(value=i))}')
