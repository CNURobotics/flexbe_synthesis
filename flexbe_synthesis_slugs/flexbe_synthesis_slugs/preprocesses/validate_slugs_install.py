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

"""Preprocess helper to validate that the Slugs binary is installed."""

from flexbe_synthesis_core.base_preprocess import BasePreProcess
from flexbe_synthesis_slugs.helpers.slugs_binary import (
    find_slugs_binary,
    slugs_install_hint,
)


class ValidateSlugsInstall(BasePreProcess):
    """Validate that the `slugs` executable is available on the system path."""

    def preprocess(self):
        """Check for Slugs and raise a clear error if it is unavailable."""
        path_to_slugs = find_slugs_binary()
        if path_to_slugs:
            print(f'Found slugs installation at: {path_to_slugs}', flush=True)
        else:
            raise FileNotFoundError(
                '\033[31m\nThe synthesizer (SLUGS) is NOT installed.\n'
                'Please use the install_slugs.sh script.\n'
                f'{slugs_install_hint()}\n'
                'The synthesizer will not be available until installed.\033[0m'
            )


def main(inputs):
    """Create the standalone preprocess instance."""
    _ = inputs
    return ValidateSlugsInstall(name='Validate Slugs Install')


def stand_alone():
    """Run the install validator from command line."""
    # Run slugs install validator from command line
    validator = main([])
    try:
        validator.preprocess()
    except FileNotFoundError as exc:
        print(exc)


if __name__ == '__main__':
    stand_alone()
