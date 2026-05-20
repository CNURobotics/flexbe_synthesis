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

"""Count formulas in generated `.structuredslugs` and optional `.slugsin` specs."""

import os

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_slugs.helpers.count_specs import count_specs, parse_slugs_specs
import yaml


class SlugsCountSpecs(BaseProcess):
    """Count per-section formulas for generated Slugs spec artifacts."""

    specs_output_dir_path: str

    def process(self):
        """Return section-count dictionaries for structuredslugs and slugsin files."""
        spec_name = os.path.basename(self.specs_output_dir_path.rstrip('/'))
        counts_dict = {}
        byproducts_dir = os.path.join(self.specs_output_dir_path, 'synthesis_byproducts')

        structuredslugs_path = os.path.join(byproducts_dir, f'{spec_name}.structuredslugs')
        if not os.path.exists(structuredslugs_path):
            raise FileNotFoundError(
                f"Missing structuredslugs file '{structuredslugs_path}' for '{spec_name}'."
            )

        print(
            f"\033[32mCounting spec sections for '{structuredslugs_path}' ...\033[0m",
            flush=True,
        )
        counts_dict['structuredslugs'] = count_specs(parse_slugs_specs(structuredslugs_path))

        slugsin_path = os.path.join(byproducts_dir, f'{spec_name}.slugsin')
        if os.path.exists(slugsin_path):
            print(f"\033[32mCounting spec sections for '{slugsin_path}' ...\033[0m", flush=True)
            counts_dict['slugsin'] = count_specs(parse_slugs_specs(slugsin_path))
        else:
            print(
                f"\033[33mNo slugsin file found at '{slugsin_path}' (skipping).\033[0m",
                flush=True,
            )

        counts_path = os.path.join(byproducts_dir, f'{spec_name}.counts')
        with open(counts_path, 'w', encoding='utf-8') as fout:
            yaml.safe_dump(
                counts_dict,
                fout,
                width=120,
                default_flow_style=False,
                sort_keys=True,
            )
        print(f"\033[32mWrote counts YAML to '{counts_path}'.\033[0m", flush=True)

        return [counts_dict]


def main(inputs):
    """Create the Slugs count-specs process."""
    return SlugsCountSpecs(
        name='SlugsCountSpecs',
        specs_output_dir_path=inputs[0],
    )
