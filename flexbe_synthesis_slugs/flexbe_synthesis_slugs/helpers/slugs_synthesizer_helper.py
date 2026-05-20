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

"""Helpers for invoking slugs and converting synthesized JSON to internal automata."""

import json
import os
import shlex
import subprocess
import threading
import time
import traceback

from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.binary_variables import expand_binary_variables
from flexbe_synthesis_slugs.helpers.slugs_automaton import (
    SlugsAutomaton,
    SlugsAutomatonState,
)
from flexbe_synthesis_slugs.helpers.slugs_binary import (
    find_slugs_binary,
    slugs_install_hint,
)


DEFAULT_SLUGS_TIMEOUT_S = 15 * 60
_STATUS_INTERVAL_S = 10.0


class SlugsSynthesizerHelper:
    """Run slugs synthesis and parse generated automata."""

    def __init__(self, specs_output_dir_path, transition_outcomes, sm_outcomes=None,
                 verbose=False, show_slugs_output=True,
                 slugs_timeout_s=DEFAULT_SLUGS_TIMEOUT_S):
        if sm_outcomes is None:
            sm_outcomes = ['finished', 'failed']
        self.slugs_timeout_s = float(slugs_timeout_s)
        if self.slugs_timeout_s <= 0:
            raise ValueError('slugs_timeout_s must be greater than zero')

        self.spec_name = os.path.basename(specs_output_dir_path)

        self.specs_output_dir_path = os.path.join(
            specs_output_dir_path,
            'synthesis_byproducts',
        )
        print(
            f"\033[32mSlugsSynthesizer: output dir path = '{self.specs_output_dir_path}' "
            '...\033[0m',
            flush=True,
        )
        if not os.path.exists(self.specs_output_dir_path):
            os.makedirs(self.specs_output_dir_path)
            print(
                f"Created directory '{self.specs_output_dir_path}' for processor outputs",
                flush=True,
            )

        self.outcome_tags = [f'_{outcome[0]}' for outcome in transition_outcomes]
        self.outcome_names = set()
        for outcome in transition_outcomes:
            if not outcome:
                continue
            low = outcome.lower()
            if low.startswith('comp'):
                self.outcome_names.add('completed')
            elif low.startswith('fail'):
                self.outcome_names.add('failed')
            else:
                self.outcome_names.add(low)
        self.activation_tag = '_a'
        self.sm_outcomes = sm_outcomes
        self.verbose = verbose
        self.show_slugs_output = show_slugs_output
        self._process = None
        self._process_lock = threading.Lock()
        self._canceled = False

    def cancel(self):
        """Terminate an active Slugs process, if synthesis is in progress."""
        self._canceled = True
        with self._process_lock:
            process = self._process

        if process is not None and process.poll() is None:
            print('[ltl_synthesizer] Terminating SLUGS process ...', flush=True)
            process.terminate()

    def read_structuredslugs(self):
        """Return input and output variables from `<spec_name>.structuredslugs`."""
        slugsin_file_name = os.path.join(
            self.specs_output_dir_path,
            self.spec_name + '.structuredslugs',
        )
        print(
            f"Reading structured slugs file '{slugsin_file_name}' for variables ...",
            flush=True,
        )

        input_vars = []
        output_vars = []
        read_inputs = False
        read_outputs = False

        with open(slugsin_file_name, encoding='utf-8') as fin:
            for line in fin.readlines():
                line = line.strip()
                if line == '' or line[0] == '#':
                    continue

                if '[INPUT]' in line:
                    read_inputs = True
                    read_outputs = False
                    continue

                if '[OUTPUT]' in line:
                    read_outputs = True
                    read_inputs = False
                    continue

                if line.startswith('['):
                    read_inputs = False
                    read_outputs = False
                    continue

                if read_inputs:
                    input_vars.append(line)

                if read_outputs:
                    output_vars.append(line)

        return input_vars, output_vars

    def handle_slugs_synthesis(self):
        """Synthesize automaton from spec and return (`SlugsAutomaton`, error code)."""
        try:
            input_vars, output_vars = self.read_structuredslugs()

            print(f'\033[38;5;208m System Output VARIABLES: {output_vars} \033[0m')
            print(f'\033[38;5;208m Environment Input VARIABLES: {input_vars} \033[0m')

            automaton_file, error_code = self.call_slugs_synthesizer(self.spec_name)
            if error_code.value == SynthesisErrorCode.SUCCESS:
                automaton = self.gen_slugs_automaton_from_json(
                    automaton_file,
                    input_vars,
                    output_vars,
                )
                print(
                    '\033[92mSuccessfully created SlugsAutomaton '
                    'from the synthesized automaton.\033[0m',
                    flush=True,
                )
            else:
                automaton = SlugsAutomaton()
                if error_code.value == SynthesisErrorCode.SPEC_UNSYNTHESIZABLE:
                    print('The GR1 specification was unsynthesizable!', flush=True)
                else:
                    print('SLUGS synthesis failed before producing an automaton.', flush=True)

            return automaton, error_code
        except Exception as exc:
            print(f'\033[33mCould not realize automaton from SLUGS output!\n {exc}')
            traceback.print_exc()
            return SlugsAutomaton(), SynthesisErrorCode(
                value=SynthesisErrorCode.SYNTHESIS_FAILED
            )

    def call_slugs_synthesizer(self, name):
        """Call slugs to synthesize an automaton from `.slugsin` input."""
        options = ['--explicitStrategy', '--jsonOutput']
        slugs_binary = find_slugs_binary()
        if slugs_binary is None:
            message = f'SLUGS is not installed. {slugs_install_hint()}'
            print(f'[ltl_synthesizer] {message}', flush=True)
            return '', SynthesisErrorCode(value=SynthesisErrorCode.SYNTHESIS_FAILED)

        slugs_cmd = [slugs_binary] + options + [name + '.slugsin', name + '.json']
        slugs_cmd_string = shlex.join(slugs_cmd)
        print(f'[ltl_synthesizer] Calling SLUGS: \n\t{slugs_cmd_string}', flush=True)

        process = subprocess.Popen(
            slugs_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=self.specs_output_dir_path,
        )
        with self._process_lock:
            self._process = process
        try:
            slugs_output, status, timed_out = self._wait_for_slugs_process(process)
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None

        output_path = os.path.join(self.specs_output_dir_path, name + '.output')
        with open(output_path, 'w', encoding='utf-8') as output_file:
            output_file.write(f'{slugs_cmd_string}\n\n{slugs_output}')

        if timed_out:
            print(self._timeout_help_message(), flush=True)
            return '', SynthesisErrorCode(value=SynthesisErrorCode.SYNTHESIS_FAILED)

        if self._canceled or status < 0:
            print('[ltl_synthesizer] SLUGS synthesis was canceled.', flush=True)
            return '', SynthesisErrorCode(value=SynthesisErrorCode.PREEMPTED)

        if status == 0:
            print('[ltl_synthesizer] checking SLUGS result ...', flush=True)
            synthesizable = self.determine_synthesizability(slugs_output)
            if synthesizable is True:
                return (
                    os.path.join(self.specs_output_dir_path, name + '.json'),
                    SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
                )

            if synthesizable is False:
                return '', SynthesisErrorCode(value=SynthesisErrorCode.SPEC_UNSYNTHESIZABLE)

            return '', SynthesisErrorCode(value=SynthesisErrorCode.SYNTHESIS_FAILED)
        else:
            print(
                f'[ltl_synthesizer] SLUGS command failed with status: {status}\n'
                f"Have you installed slugs?\n Output: '{slugs_output}'",
                flush=True,
            )
            return '', SynthesisErrorCode(value=SynthesisErrorCode.SYNTHESIS_FAILED)

    @staticmethod
    def _get_process_rss_mb(pid):
        """Return RSS memory in MB for process `pid` via /proc, or None if unavailable."""
        try:
            with open(f'/proc/{pid}/status', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        return int(line.split()[1]) / 1024.0
        except OSError:
            pass
        return None

    def _print_synthesis_status(self, elapsed_s, remaining_s, pid):
        """Print a one-line synthesis progress update to stdout."""
        mem = self._get_process_rss_mb(pid)
        mem_str = f', Memory: {mem:.0f} MB' if mem is not None else ''
        print(
            f'[synthesis] elapsed={elapsed_s:.0f}s, '
            f'remaining={remaining_s:.0f}s (of {self.slugs_timeout_s:.0f}s)'
            f'{mem_str}',
            flush=True,
        )

    def _wait_for_slugs_process(self, process):
        """Wait for Slugs while allowing timeout or `cancel()` to stop the child."""
        output_chunks = []
        start_time = time.monotonic()
        deadline = start_time + self.slugs_timeout_s
        next_status_time = start_time + _STATUS_INTERVAL_S
        terminating = False
        while True:
            try:
                remaining = max(0.0, deadline - time.monotonic())
                output, _ = process.communicate(timeout=min(0.1, remaining))
                output_chunks.append(output or '')
                return ''.join(output_chunks), process.returncode, False
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if not self._canceled and now >= next_status_time:
                    self._print_synthesis_status(now - start_time,
                                                 max(0.0, deadline - now),
                                                 process.pid)
                    next_status_time = now + _STATUS_INTERVAL_S

                if self._canceled and process.poll() is None:
                    if terminating:
                        process.kill()
                    else:
                        process.terminate()
                        terminating = True
                    continue

                if process.poll() is not None:
                    output, _ = process.communicate()
                    output_chunks.append(output or '')
                    return ''.join(output_chunks), process.returncode, False

                if now >= deadline:
                    output_chunks.append(f'\n{self._timeout_help_message()}\n')
                    output_chunks.append(self._terminate_timed_out_process(process))
                    status = process.returncode
                    if status is None:
                        status = -1
                    return ''.join(output_chunks), status, True

    @staticmethod
    def _terminate_timed_out_process(process):
        """Terminate a timed-out Slugs process and collect any final output."""
        if process.poll() is None:
            process.terminate()
        try:
            output, _ = process.communicate(timeout=1.0)
            return output or ''
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            try:
                output, _ = process.communicate(timeout=1.0)
                return output or ''
            except subprocess.TimeoutExpired:
                return ''

    def _timeout_help_message(self):
        """Return the user-facing Slugs timeout message."""
        return (
            '[ltl_synthesizer] WARNING: SLUGS synthesis timed out after '
            f'{self.slugs_timeout_s:g} seconds. Increase the '
            "'synthesis_timeout_s' value in your process pipeline data file "
            'or set it in the synthesis request to allow more time for this specification.'
        )

    def determine_synthesizability(self, slugs_output):
        """Determine synthesizability based on slugs terminal output."""
        if 'RESULT: Specification is realizable.' in slugs_output:
            print(
                '\033[92mSuccessfully synthesized an automaton '
                'from the GR1 specification.\033[0m'
            )
            synthesizable = True
        elif 'RESULT: Specification is unrealizable.' in slugs_output:
            synthesizable = False
        else:
            synthesizable = None
            print(
                '\033[33mSLUGS output did not include a recognized synthesis '
                'result.\033[0m'
            )

        if self.show_slugs_output:
            print('\n\n' + 30 * '=')
            print(f'Slugs output: {slugs_output}')
            print(30 * '=' + '\n\n')
        return synthesizable

    def automaton_state_from_node_info(self, name, info, n_in_vars):
        """Generate one automaton state from a synthesized node record."""
        state = SlugsAutomatonState(name=str(name))

        state.output_valuation = [bool(val) for val in info['state'][n_in_vars:]]
        state.input_valuation = [bool(val) for val in info['state'][:n_in_vars]]

        state.transitions = [str(transition) for transition in info['trans']]
        state.rank = info['rank']

        if self.verbose:
            print(
                f"Creating state '{name}' with {n_in_vars} input vars, "
                f'{len(state.output_valuation)} output vars, '
                f"and {len(info['state'])} total booleans (including memory) ..."
            )

        return state

    def gen_slugs_automaton_from_json(self, json_file, input_vars, output_vars):
        """Generate a `SlugsAutomaton` instance from synthesized JSON output."""
        with open(json_file, encoding='utf-8') as data_file:
            data = json.load(data_file)

        automaton = SlugsAutomaton()

        binary_outputs = self.expand_binary(output_vars)
        automaton.output_variables = output_vars
        if self.verbose:
            print(
                f' Expanded OUTPUT variables {len(automaton.output_variables):2d} '
                f'- {automaton.output_variables}'
            )
            print(f'                 binary outputs {binary_outputs}')

        binary_inputs = self.expand_binary(input_vars)
        automaton.input_variables = input_vars
        n_in_vars = len(input_vars)

        if self.verbose:
            print(f' Expanded INPUT variables {n_in_vars:2d} - {input_vars}')
            print(f'                binary inputs {binary_inputs}')

        states = data['nodes']

        automaton.reset_states()
        for state_name in states:
            state = self.automaton_state_from_node_info(
                state_name,
                states[state_name],
                n_in_vars,
            )
            state.update_variables(
                binary_inputs,
                automaton.input_variables,
                binary_outputs,
                automaton.output_variables,
                self.activation_tag,
                self.outcome_tags,
                self.outcome_names,
                self.sm_outcomes,
                verbose=self.verbose,
            )
            automaton.add_state(state)
            if self.verbose:
                print(state)

        # Populate incoming edges, then tag the unique root (no incoming) as initial.
        automaton.update_state_map()
        initial_state = None
        for state in automaton.automaton:
            if not state.incoming:
                if not state.transitions:
                    print(
                        f"Root state '{state.name}' has no outgoing transitions - skipping.",
                        flush=True,
                    )
                    continue
                if initial_state is None:
                    state.is_initial = True
                    initial_state = state
                    if self.verbose:
                        print(f"Marked initial state: '{state.name}'", flush=True)
                else:
                    print(
                        f"Warning: additional root state '{state.name}' found "
                        '(not marked as initial).',
                        flush=True,
                    )

        return automaton

    def expand_binary(self, var_list):
        """Expand compact binary variable ranges like `x:0...7` into bit terms."""
        original = var_list[:]
        binary_variables = expand_binary_variables(var_list)
        if self.verbose and original != var_list:
            print(f'  expanded variables with binary {var_list}')

        return binary_variables
