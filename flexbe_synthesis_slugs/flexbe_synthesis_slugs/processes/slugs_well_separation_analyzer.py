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

"""Run Slugs well-separation analysis on the compiled `.slugsin` artifact."""

import json
import os
import shlex
import subprocess
import threading

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.slugs_binary import (
    find_slugs_binary,
    slugs_install_hint,
)
from flexbe_synthesis_slugs.helpers.slugs_synthesizer_helper import (
    DEFAULT_SLUGS_TIMEOUT_S,
)
from pydantic import PrivateAttr


STATUS_WELL_SEPARATED = 'WELL_SEPARATED'
STATUS_NON_WELL_SEPARATED = 'NON_WELL_SEPARATED'
STATUS_ANALYSIS_INCOMPLETE = 'ANALYSIS_INCOMPLETE'
STATUS_ANALYSIS_ERROR = 'ANALYSIS_ERROR'


class SlugsWellSeparationAnalyzer(BaseProcess):
    """Wrapper around Slugs `--checkWellSeparation` analysis mode."""

    specs_output_dir_path: str
    spec_name: str | None = None
    well_separation_timeout_s: float = DEFAULT_SLUGS_TIMEOUT_S
    fail_on_non_well_separated: bool = False
    fail_on_incomplete: bool = True
    minimize_core: bool = False
    slugs_binary: str | None = None
    _process: subprocess.Popen | None = PrivateAttr(default=None)
    _process_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _canceled: bool = PrivateAttr(default=False)

    def process(self):
        """Run the analyzer, save JSON/output artifacts, and enforce policy."""
        print('\033[32mStarting Slugs well-separation analyzer ...\033[0m', flush=True)
        result = self._run_analysis()
        status = result.get('status', STATUS_ANALYSIS_ERROR)

        if status == STATUS_NON_WELL_SEPARATED:
            warning = self._non_well_separated_warning(result)
            self.messages.append(warning)
            print(f'\033[33m{warning}\033[0m', flush=True)
            if self.fail_on_non_well_separated:
                return [
                    result,
                    SynthesisErrorCode(value=SynthesisErrorCode.SYNTHESIS_FAILED),
                ]
        elif status in (STATUS_ANALYSIS_INCOMPLETE, STATUS_ANALYSIS_ERROR):
            warning = self._analysis_incomplete_warning(result)
            self.messages.append(warning)
            print(f'\033[33m{warning}\033[0m', flush=True)
            if self.fail_on_incomplete:
                return [
                    result,
                    SynthesisErrorCode(value=SynthesisErrorCode.SYNTHESIS_FAILED),
                ]
        else:
            print('\033[32mWell-separation analysis passed.\033[0m', flush=True)

        return [result, SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]

    def cancel(self):
        """Cancel the active Slugs analysis process, if any."""
        self._canceled = True
        with self._process_lock:
            process = self._process

        if process is not None and process.poll() is None:
            print('[well_separation] Terminating SLUGS process ...', flush=True)
            process.terminate()

    @property
    def _byproducts_dir(self):
        return os.path.join(self.specs_output_dir_path, 'synthesis_byproducts')

    @property
    def _effective_spec_name(self):
        return self.spec_name or os.path.basename(os.path.normpath(self.specs_output_dir_path))

    def _run_analysis(self):
        timeout_s = float(self.well_separation_timeout_s)
        if timeout_s <= 0:
            raise ValueError('well_separation_timeout_s must be greater than zero')

        os.makedirs(self._byproducts_dir, exist_ok=True)
        spec_name = self._effective_spec_name
        slugsin_name = spec_name + '.slugsin'
        result_name = spec_name + '.well_separation.json'
        output_path = os.path.join(self._byproducts_dir, spec_name + '.well_separation.output')

        slugs_binary = self.slugs_binary or find_slugs_binary()
        if slugs_binary is None:
            message = f'SLUGS is not installed. {slugs_install_hint()}'
            result = self._incomplete_result(message)
            self._write_analysis_output(output_path, message)
            return result

        slugs_cmd = [
            slugs_binary,
            '--checkWellSeparation',
            '--jsonOutput',
        ]
        if self.minimize_core:
            slugs_cmd.append('--minimizeWellSeparationCore')
        slugs_cmd.extend([slugsin_name, result_name])
        slugs_cmd_string = shlex.join(slugs_cmd)
        print(f'[well_separation] Calling SLUGS: \n\t{slugs_cmd_string}', flush=True)

        try:
            process = subprocess.Popen(
                slugs_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self._byproducts_dir,
            )
        except OSError as exc:
            message = f'Could not start Slugs well-separation analysis: {exc}'
            result = self._error_result(message)
            self._write_analysis_output(output_path, f'{slugs_cmd_string}\n\n{message}')
            return result

        with self._process_lock:
            self._process = process
        try:
            try:
                slugs_output, _ = process.communicate(timeout=timeout_s)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.terminate()
                slugs_output, _ = process.communicate()
                timed_out = True
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None

        self._write_analysis_output(output_path, f'{slugs_cmd_string}\n\n{slugs_output}')
        if timed_out:
            return self._incomplete_result(
                f'Slugs well-separation analysis timed out after {timeout_s:g}s.'
            )
        # A negative returncode means the process was actually killed by our
        # terminate() call in cancel(); self._canceled alone isn't enough here
        # since it can be set after the subprocess has already exited 0 with a
        # valid result, which must not be discarded as an incomplete analysis.
        if process.returncode < 0:
            return self._incomplete_result('Slugs well-separation analysis was canceled.')
        if process.returncode != 0:
            return self._error_result(
                'Slugs well-separation analysis failed with status '
                f'{process.returncode}. See {output_path}.'
            )

        result_path = os.path.join(self._byproducts_dir, result_name)
        try:
            with open(result_path, encoding='utf-8') as result_file:
                result = json.load(result_file)
        except (OSError, json.JSONDecodeError) as exc:
            return self._error_result(f'Could not read well-separation JSON: {exc}')

        if not isinstance(result, dict):
            return self._error_result('Slugs well-separation JSON was not an object.')

        result.setdefault('artifact_path', result_path)
        result.setdefault('output_path', output_path)
        result.setdefault('minimize_core_requested', self.minimize_core)
        result.setdefault('policy', self._policy_dict())
        return result

    def _policy_dict(self):
        return {
            'fail_on_non_well_separated': self.fail_on_non_well_separated,
            'fail_on_incomplete': self.fail_on_incomplete,
            'minimize_core': self.minimize_core,
        }

    def _incomplete_result(self, warning):
        return {
            'status': STATUS_ANALYSIS_INCOMPLETE,
            'complete': False,
            'warnings': [warning],
            'minimize_core_requested': self.minimize_core,
            'policy': self._policy_dict(),
        }

    def _error_result(self, warning):
        result = self._incomplete_result(warning)
        result['status'] = STATUS_ANALYSIS_ERROR
        return result

    @staticmethod
    def _write_analysis_output(path, text):
        with open(path, 'w', encoding='utf-8') as output_file:
            output_file.write(text)
            if text and not text.endswith('\n'):
                output_file.write('\n')

    def _non_well_separated_warning(self, result):
        details = []
        case = result.get('case') or result.get('violated_case')
        if case:
            details.append(f'case={case}')
        assumption_type = (
            result.get('violated_assumption_type')
            or result.get('assumption_type')
            or result.get('reason')
        )
        if assumption_type:
            details.append(f'assumption={assumption_type}')
        if self.minimize_core:
            core = result.get('core_assumptions') or result.get('minimal_core') or []
            details.append(f'core_size={len(core)}')
        suffix = f" ({', '.join(details)})" if details else ''
        return (
            'Warning: GR(1) specification is not well separated; synthesis will '
            f'continue because fail_on_non_well_separated is false{suffix}.'
        )

    @staticmethod
    def _analysis_incomplete_warning(result):
        warnings = result.get('warnings') or []
        detail = f' {warnings[0]}' if warnings else ''
        return (
            'Warning: well-separation analysis did not produce a definitive result; '
            f'synthesis will continue.{detail}'
        )


def main(inputs):
    """Create the Slugs well-separation analyzer process."""
    spec_name = inputs[1] if len(inputs) > 1 else None
    timeout_s = inputs[2] if len(inputs) > 2 else DEFAULT_SLUGS_TIMEOUT_S
    fail_on_non_well_separated = inputs[3] if len(inputs) > 3 else False
    fail_on_incomplete = inputs[4] if len(inputs) > 4 else True
    minimize_core = inputs[5] if len(inputs) > 5 else False
    slugs_binary = inputs[6] if len(inputs) > 6 else None
    return SlugsWellSeparationAnalyzer(
        name='SlugsWellSeparationAnalyzer',
        specs_output_dir_path=inputs[0],
        spec_name=spec_name,
        well_separation_timeout_s=timeout_s,
        fail_on_non_well_separated=fail_on_non_well_separated,
        fail_on_incomplete=fail_on_incomplete,
        minimize_core=minimize_core,
        slugs_binary=slugs_binary,
    )
