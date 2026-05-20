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

"""Compile structured Slugs specifications into `.slugsin` files."""

import os

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
from flexbe_synthesis_slugs.helpers.structured_slugs_parser import (
    compiler as slugs_compiler,
)


class SlugsSpecCompiler(BaseProcess):
    """Compile structured specification artifacts used by Slugs."""

    gr1_specification: dict
    specs_output_dir_path: str

    def process(self):
        """Write structured specs and compile them into `.slugsin` format."""
        spec_name = os.path.basename(os.path.normpath(self.specs_output_dir_path))
        print(f"\033[32mStarting slugs compiler for '{spec_name}' ...\033[0m", flush=True)

        if spec_name != self.gr1_specification['spec_name']:
            print(
                (
                    f'\033[33mWarning: Mismatched spec name '
                    f"'{self.gr1_specification['spec_name']}' vs path '{spec_name}' "
                    f"('{self.specs_output_dir_path}').\033[0m"
                ),
                flush=True,
            )

        gr1_spec = GR1Specification(self.gr1_specification['spec_name'])
        gr1_spec.merge_gr1_specification(self.gr1_specification)

        full_specs_output_dir_path = os.path.join(
            self.specs_output_dir_path, 'synthesis_byproducts'
        )
        gr1_spec.write_structured_slugs_file(full_specs_output_dir_path)

        try:
            structured_slugs_file_path = os.path.join(
                full_specs_output_dir_path,
                gr1_spec.spec_name + '.structuredslugs',
            )
            slugsin_file_name = os.path.join(
                full_specs_output_dir_path,
                gr1_spec.spec_name + '.slugsin',
            )
            print(f"Convert to '{slugsin_file_name}' ...", flush=True)
            with open(slugsin_file_name, 'w', encoding='utf-8') as fout:
                slugs_compiler.performConversion(
                    structured_slugs_file_path,
                    thoroughly=True,
                    fout=fout,
                )
        except Exception as exc:
            msg = f"Could not compile '{spec_name}' to slugsin: {exc}"
            print(f'\033[33m{msg}\033[0m', flush=True)
            raise RuntimeError(msg) from exc

        return [SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]


def main(inputs):
    """Create the Slugs spec compiler process."""
    return SlugsSpecCompiler(
        name='SlugsSpecCompiler',
        gr1_specification=inputs[0],
        specs_output_dir_path=inputs[1],
    )
