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

"""Tests for system capability loading process entry point."""

from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_generic.processes.system_capabilities_loader import (
    main,
    SystemCapabilityLoader,
)
import pytest


def test_main_returns_correctly_spelled_loader_class():
    """Entry point should instantiate the correctly spelled class name."""
    loader = main(['demo_system'])

    assert isinstance(loader, SystemCapabilityLoader)
    assert loader.system_name == 'demo_system'


def test_main_accepts_legacy_verbose_second_argument():
    """Older two-argument pipeline bindings passed verbose as the second input."""
    loader = main(['demo_system', True])

    assert loader.slugs_specification == {}
    assert loader.verbose is True


def test_main_accepts_slugs_specification_and_verbose():
    """New pipeline bindings should pass slugs_specification before verbose."""
    loader = main(['demo_system', {'system_name': 'demo_system'}, True])

    assert loader.slugs_specification == {'system_name': 'demo_system'}
    assert loader.verbose is True


def _write_system_config(tmp_path, system_name, capabilities_text, transitions_text):
    configs_dir = tmp_path / system_name / 'configs'
    configs_dir.mkdir(parents=True)
    capabilities_file = configs_dir / f'{system_name}{fpths._SYSTEM_CAPABILITIES_CONFIG_EXT}'
    transitions_file = configs_dir / f'{system_name}{fpths._TRANSITION_RELATIONS_CONFIG_EXT}'
    capabilities_file.write_text(capabilities_text, encoding='utf-8')
    transitions_file.write_text(transitions_text, encoding='utf-8')


def _loader(tmp_path, system_name='demo'):
    return SystemCapabilityLoader(
        name='CapabilityLoader',
        system_name=system_name,
        synthesis_home=str(tmp_path),
    )


def test_system_capabilities_loader_rejects_non_mapping_capabilities_yaml(tmp_path):
    """Merged capability files must have a top-level mapping."""
    _write_system_config(
        tmp_path,
        'demo',
        '- invalid\n',
        'name: demo\n',
    )

    with pytest.raises(TypeError, match='top-level mapping'):
        _loader(tmp_path).process()


def test_system_capabilities_loader_rejects_non_mapping_transition_yaml(tmp_path):
    """Transition relation files must have a top-level mapping."""
    _write_system_config(
        tmp_path,
        'demo',
        'name: demo\ncapabilities: {}\n',
        '- invalid\n',
    )

    with pytest.raises(TypeError, match='top-level mapping'):
        _loader(tmp_path).process()
