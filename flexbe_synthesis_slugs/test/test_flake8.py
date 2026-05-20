# Copyright 2017 Open Source Robotics Foundation, Inc.
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

import ament_flake8.main as ament_flake8_main
import pytest


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    original_style_guide = ament_flake8_main.get_flake8_style_guide

    def _single_job_style_guide(argv):
        return original_style_guide(list(argv) + ['--jobs=1'])

    ament_flake8_main.get_flake8_style_guide = _single_job_style_guide
    try:
        rc, errors = ament_flake8_main.main_with_errors(argv=['--linelength', '135'])
    finally:
        ament_flake8_main.get_flake8_style_guide = original_style_guide

    assert rc == 0, \
        'Found %d code style errors / warnings:\n' % len(errors) + \
        '\n'.join(errors)
