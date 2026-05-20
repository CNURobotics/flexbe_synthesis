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

"""Tests for predefined path helpers."""

import os

from flexbe_synthesis_core import predefined_strings


def test_get_synthesis_home_prefers_explicit_override(monkeypatch, tmp_path):
    """An explicit path should win over the environment setting."""
    env_home = tmp_path / 'env_home'
    override_home = tmp_path / 'override_home'
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(env_home))

    assert predefined_strings.get_synthesis_home(str(override_home)) == str(
        override_home
    )


def test_get_synthesis_home_uses_environment(monkeypatch, tmp_path):
    """The environment should configure artifact output when no override is set."""
    env_home = tmp_path / 'env_home'
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(env_home))

    assert predefined_strings.get_synthesis_home() == str(env_home)


def test_get_synthesis_home_defaults_to_user_home(monkeypatch):
    """The default should remain user-home based for normal local runs."""
    monkeypatch.delenv('FLEXBE_SYNTHESIS_HOME', raising=False)

    expected = os.path.abspath(os.path.expanduser('~/.flexbe_synthesis'))
    assert predefined_strings.get_synthesis_home() == expected
