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

"""Load merged system capability and transition-relations YAML files."""

import logging
import os

from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_core.base_process import BaseProcess
from pydantic import Field
import yaml

logger = logging.getLogger(__name__)


class SystemCapabilityLoader(BaseProcess):
    """Load full system capabilities dictionary for synthesis processes."""

    system_name: str
    slugs_specification: dict = Field(default_factory=dict)

    def process(self):
        """Load capability + transition configuration and return merged dict."""
        if not isinstance(self.slugs_specification, dict):
            raise TypeError(
                'system_capabilities_loader input slugs_specification must be a '
                f'mapping, got {type(self.slugs_specification).__name__}.'
            )
        spec_system_name = self.slugs_specification.get('system_name', '')
        if spec_system_name and spec_system_name != self.system_name:
            raise ValueError(
                f'system_name mismatch: specification was loaded for '
                f"'{spec_system_name}' but capabilities are being loaded for "
                f"'{self.system_name}' — check that spec_name and system_name "
                f'in your pipeline data file refer to the same system.'
            )

        capabilities_path = os.path.join(self.synthesis_home, self.system_name, 'configs')
        if not os.path.exists(capabilities_path):
            raise FileNotFoundError(
                f"defined capabilities_path '{capabilities_path}' does not exist!"
            )

        capabilities_file = os.path.join(
            capabilities_path,
            self.system_name + fpths._SYSTEM_CAPABILITIES_CONFIG_EXT,
        )
        if not os.path.isfile(capabilities_file):
            print(
                f"\033[31mdefined capabilities file '{capabilities_file}' does not exist!\033[0m"
            )
            raise FileNotFoundError(
                f"defined capabilities file '{capabilities_file}' does not exist!"
            )

        print(f"Loading capabilities from '{capabilities_path}'", flush=True)
        with open(capabilities_file) as stream:
            capabilities = yaml.safe_load(stream)
        if not isinstance(capabilities, dict):
            raise TypeError(
                (
                    f"System capabilities file '{capabilities_file}' must contain a "
                    f'top-level mapping, got {type(capabilities).__name__}.'
                )
            )

        cap_file_name = capabilities.pop('name', None)
        if cap_file_name is not None and cap_file_name != self.system_name:
            logger.warning(
                "Capabilities file 'name' field '%s' does not match system_name '%s'.",
                cap_file_name, self.system_name,
            )

        config_file = self.system_name + fpths._TRANSITION_RELATIONS_CONFIG_EXT
        config_file_path = os.path.join(capabilities_path, config_file)
        print(f"Loading transition relations from '{config_file_path}'")
        try:
            with open(config_file_path) as stream:
                config = yaml.safe_load(stream)
            if not isinstance(config, dict):
                raise TypeError(
                    (
                        f"Transition relations file '{config_file_path}' must contain a "
                        f'top-level mapping, got {type(config).__name__}.'
                    )
                )
            tr_file_name = config.pop('name', None)
            if tr_file_name is not None and tr_file_name != self.system_name:
                logger.warning(
                    "Transition relations file 'name' field '%s' does not match "
                    "system_name '%s'.",
                    tr_file_name, self.system_name,
                )
            capabilities.update(config)
        except OSError as exc:
            msg = f"Failed to load transition relation '{config_file}'! {exc}"
            print(f'\033[31m{msg}\033[0m')
            raise OSError(msg) from exc

        capabilities['name'] = self.system_name

        if self.verbose:
            print(f"Loaded system capabilities for '{self.system_name}':")
            print(yaml.dump(capabilities, default_flow_style=False), flush=True)
        return [capabilities]


def main(inputs):
    """Create the capabilities loader process."""
    slugs_specification = {}
    verbose = False
    if len(inputs) > 1:
        if isinstance(inputs[1], bool):
            verbose = inputs[1]
        else:
            slugs_specification = inputs[1]
    if len(inputs) > 2:
        verbose = inputs[2]

    return SystemCapabilityLoader(
        name='CapabilityLoader',
        system_name=inputs[0],
        slugs_specification=slugs_specification,
        verbose=verbose,
    )


if __name__ == '__main__':
    capability_name = 'vending_demo'
    print(f"Try to load capabilities for '{capability_name}' ...", flush=True)
    try:
        outputs = main([capability_name, {}]).process()
        print('Returned capabilities:')
        print(yaml.dump(outputs[0], default_flow_style=False))
    except (OSError, ValueError, TypeError) as exc:
        print(exc)
        import traceback

        traceback.print_exc()
