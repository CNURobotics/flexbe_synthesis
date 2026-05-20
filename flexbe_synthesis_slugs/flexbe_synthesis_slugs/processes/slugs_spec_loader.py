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

"""Load pre-defined GR(1) specifications from YAML and merge current specs."""

import logging
import os

from flexbe_synthesis_core.base_process import BaseProcess
import flexbe_synthesis_core.predefined_strings as fpths
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
import yaml

logger = logging.getLogger(__name__)


class SlugsSpecLoader(BaseProcess):
    """Load a specification file and merge optional existing specs."""

    spec_name: str
    system_name: str
    spec_path: str | None = None
    current_specs: dict | None = None

    def process(self):
        """Load and return merged specification as a serializable dictionary."""
        if self.spec_name is None or self.spec_name == '':
            raise ValueError(f"Invalid specification name '{self.spec_name}'!")

        logger.info('Starting %s for spec %r ...', self.name, self.spec_name)
        spec = GR1Specification(self.spec_name, system_name=self.system_name)
        if self.current_specs:
            print('Loading existing specs before merge ...', flush=True)
            self.load_specs_from_current_msg(spec)

        if self.spec_path is None or self.spec_path == '':
            spec_path = os.path.join(
                fpths.get_synthesis_home(),
                self.system_name,
                'specs',
                self.spec_name + '.yaml',
            )
        else:
            spec_path = self.spec_path

        if not os.path.exists(spec_path):
            raise FileNotFoundError(

                    f"\033[38;5;208mProvided file path '{spec_path}' from "
                    f"'{self.spec_name}' does not exist\033[0m"

            )

        print(
            f"\033[32mLoading spec from '{spec_path}' for '{self.spec_name}' ...\033[0m",
            flush=True,
        )
        try:
            with open(spec_path) as file:
                new_spec = yaml.safe_load(file)
        except OSError as exc:
            raise OSError(f"Could not read spec file '{spec_path}': {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"Spec file '{spec_path}' contains invalid YAML: {exc}") from exc

        file_spec_name = new_spec.get('spec_name') if isinstance(new_spec, dict) else None
        if file_spec_name != self.spec_name:
            logger.warning(
                "Spec name mismatch: expected '%s' but file contains '%s' in '%s'",
                self.spec_name, file_spec_name, spec_path,
            )

        try:
            spec.merge_gr1_specification(new_spec['specs'])
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Malformed spec content in '{spec_path}': {exc}"
            ) from exc

        if self.verbose:
            print(f'Returning from SlugsSpecLoader!\n{spec}', flush=True)
        else:
            print(f'Returning from SlugsSpecLoader!\n{spec.summary()}', flush=True)
        return [spec.to_dict()]

    def load_specs_from_current_msg(self, spec):
        """Merge current specification payload into `spec`."""
        if self.current_specs is None:
            return

        spec.merge_gr1_specification(self.current_specs)
        if self.verbose:
            print('Loaded current specs:', flush=True)
            print(spec, flush=True)
        else:
            print(f'Loaded current specs:\n{spec.summary()}', flush=True)


def main(inputs):
    """Create the Slugs spec loader process."""
    current_specs = None
    spec_path = None
    if len(inputs) > 2:
        spec_path = inputs[2]
    if len(inputs) > 3:
        current_specs = inputs[3]

    return SlugsSpecLoader(
        name='slugs_spec_loader',
        spec_name=inputs[0],
        system_name=inputs[1],
        spec_path=spec_path,
        current_specs=current_specs,
    )
