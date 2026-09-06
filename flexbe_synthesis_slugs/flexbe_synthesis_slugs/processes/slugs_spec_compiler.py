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

import json
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
    variable_ordering_mode: str = 'alphabetic'
    variable_ordering_seed: int | None = None
    reordering_enabled: bool = True

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
        gr1_spec.write_structured_slugs_file(
            full_specs_output_dir_path,
            variable_ordering_mode=self.variable_ordering_mode,
            variable_ordering_seed=self.variable_ordering_seed,
        )
        self._write_variable_order_sidecar(gr1_spec, full_specs_output_dir_path)

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

    def _write_variable_order_sidecar(self, gr1_spec, output_dir):
        """Write requested variable-order metadata for experiment harnesses."""
        order_path = os.path.join(
            output_dir,
            gr1_spec.spec_name + '.variable_order.json',
        )
        payload = {
            'mode': self.variable_ordering_mode,
            'seed': self.variable_ordering_seed,
            'reordering_enabled': self.reordering_enabled,
            'requested_input_order': gr1_spec.last_variable_order.get('input_order', []),
            'requested_output_order': gr1_spec.last_variable_order.get('output_order', []),
        }
        with open(order_path, 'w', encoding='utf-8') as order_file:
            json.dump(payload, order_file, indent=2)
            order_file.write('\n')
        print(f"Wrote variable-order metadata to '{order_path}'", flush=True)


def main(inputs):
    """Create the Slugs spec compiler process."""
    variable_ordering_mode = inputs[2] if len(inputs) > 2 else 'alphabetic'
    variable_ordering_seed = inputs[3] if len(inputs) > 3 else None
    reordering_enabled = inputs[4] if len(inputs) > 4 else True
    return SlugsSpecCompiler(
        name='SlugsSpecCompiler',
        gr1_specification=inputs[0],
        specs_output_dir_path=inputs[1],
        variable_ordering_mode=variable_ordering_mode,
        variable_ordering_seed=variable_ordering_seed,
        reordering_enabled=reordering_enabled,
    )
