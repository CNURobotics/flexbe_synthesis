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

"""Resolve the Slugs executable used by synthesis plugins."""

import os
from pathlib import Path
import shutil

DEFAULT_SLUGS_INSTALL_DIR = '/usr/local/bin'
SLUGS_INSTALL_DIR_ENV = 'SLUGS_INSTALL_DIR'


def find_slugs_binary():
    """Return the best available Slugs executable path, or `None` if missing."""
    install_dir = os.environ.get(SLUGS_INSTALL_DIR_ENV, DEFAULT_SLUGS_INSTALL_DIR)
    install_path = Path(install_dir) / 'slugs'
    if install_path.is_file() and os.access(install_path, os.X_OK):
        return str(install_path)

    path_binary = shutil.which('slugs')
    if path_binary:
        return path_binary

    default_path = Path(DEFAULT_SLUGS_INSTALL_DIR) / 'slugs'
    if install_dir != DEFAULT_SLUGS_INSTALL_DIR and (
        default_path.is_file() and os.access(default_path, os.X_OK)
    ):
        return str(default_path)

    return None


def slugs_install_hint():
    """Return user-facing install guidance for Slugs lookup failures."""
    install_dir = os.environ.get(SLUGS_INSTALL_DIR_ENV, DEFAULT_SLUGS_INSTALL_DIR)
    return (
        f'Expected slugs in ${SLUGS_INSTALL_DIR_ENV} ({install_dir}), on PATH, '
        f'or in {DEFAULT_SLUGS_INSTALL_DIR}. Run install_slugs.sh or set '
        f'{SLUGS_INSTALL_DIR_ENV} to the directory containing the slugs binary.'
    )
