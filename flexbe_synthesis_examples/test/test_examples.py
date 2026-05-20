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

"""Regression tests for checked-in generic synthesis examples."""

from copy import deepcopy
import importlib.util
from pathlib import Path

from flexbe_synthesis_generic.preprocesses.capability_loader import (
    main as capability_loader_main,
)
from flexbe_synthesis_generic.preprocesses.generate_discrete_abstraction import (
    main as generate_discrete_abstraction_main,
)
from flexbe_synthesis_generic.preprocesses.generate_transition_relations import (
    main as generate_transition_relations_main,
)
from launch import LaunchDescription
import pytest
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
GENERIC_PACKAGE_ROOT = PACKAGE_ROOT.parent / 'flexbe_synthesis_generic'
YAML_ROOTS = (
    PACKAGE_ROOT / 'example',
    GENERIC_PACKAGE_ROOT / 'mappings',
)
EXAMPLE_CAPABILITIES = (
    PACKAGE_ROOT / 'example' / 'hello_world' / 'capabilities' / 'hello_world_capabilities.yaml',
    PACKAGE_ROOT / 'example' / 'coffee_maker' / 'capabilities' / 'coffee_capabilities.yaml',
    PACKAGE_ROOT / 'example' / 'vending_demo' / 'capabilities' / 'vending_capabilities.yaml',
)
SLUGS_LAUNCH_FILES = tuple(
    sorted((PACKAGE_ROOT / 'launch').glob('*.launch.py'))
)

STATE_MAPPINGS = {
    'state_outcome_mappings': {
        'aborted': 'failure',
        'canceled': 'failure',
        'done': 'completed',
        'empty': 'failure',
        'failed': 'failure',
        'false': 'failure',
        'received': 'completed',
        'timeout': 'failure',
        'true': 'completed',
        'unavailable': 'failure',
    },
    'sm_outcome_mappings': {
        'failed': 'failed',
        'finished': 'finished',
    },
    'transition_outcomes': [
        'completed',
        'failure',
    ],
}


def _yaml_files():
    for yaml_root in YAML_ROOTS:
        if not yaml_root.exists():
            raise FileNotFoundError(
                f'YAML root not found: {yaml_root} — '
                'ensure flexbe_synthesis_generic is present as a sibling package'
            )
        yield from sorted(yaml_root.rglob('*.yaml'))


def _pipeline_files():
    yield from sorted((PACKAGE_ROOT / 'example').rglob('*_def.yaml'))


def _workspace_data():
    return {
        'states': {
            'LogState': {
                'name': 'LogState',
                'package': 'flexbe_states',
                'parameters': {
                    'text': {
                        'type': 'str',
                    },
                },
                'outcomes': {
                    'done': {
                        'remapping': 'completed',
                    },
                },
                'userdata_in': {},
                'userdata_out': {},
            },
        },
        'behaviors': {},
    }


def _load_launch_file(launch_path):
    spec = importlib.util.spec_from_file_location(launch_path.stem, launch_path)
    launch_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch_module)
    return launch_module


def _pipeline_input_keys(pipeline_path):
    with pipeline_path.open('r') as stream:
        pipeline_config = yaml.safe_load(stream)

    input_keys = set()
    for pipeline_step in pipeline_config['/pipeline']:
        inputs = pipeline_step['entry_point'].get('inputs', {})
        input_keys.update(inputs)
    return input_keys


@pytest.mark.parametrize('launch_path', SLUGS_LAUNCH_FILES, ids=lambda path: path.name)
def test_slugs_launch_files_generate_launch_descriptions(
    launch_path,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv('ROS_LOG_DIR', str(tmp_path / 'ros_logs'))
    launch_module = _load_launch_file(launch_path)

    launch_description = launch_module.generate_launch_description()

    assert isinstance(launch_description, LaunchDescription)


@pytest.mark.parametrize('yaml_path', _yaml_files(), ids=lambda path: str(path.name))
def test_checked_in_yaml_examples_parse(yaml_path):
    with yaml_path.open('r') as stream:
        assert yaml.safe_load(stream) is not None


@pytest.mark.parametrize('pipeline_path', _pipeline_files(), ids=lambda path: path.name)
def test_checked_in_pipeline_examples_define_list_pipeline(pipeline_path):
    with pipeline_path.open('r') as stream:
        pipeline_config = yaml.safe_load(stream)

    assert isinstance(pipeline_config.get('/pipeline'), list)


def test_coffee_extended_button_autonomy_matches_declared_outcome():
    capabilities_path = PACKAGE_ROOT / 'example' / 'coffee_maker' / 'capabilities' / (
        'coffee_capabilities_extended.yaml'
    )

    with capabilities_path.open('r') as stream:
        capabilities = yaml.safe_load(stream)

    bd_capability = capabilities['capabilities']['bd']
    declared_outcomes = set(bd_capability['parameters']['outcomes'])
    autonomy_keys = set(bd_capability['autonomy'])

    assert 'button' in autonomy_keys
    assert autonomy_keys <= declared_outcomes


def test_vending_extended_snack_suggestion_matches_declared_outcome():
    capabilities_path = PACKAGE_ROOT / 'example' / 'vending_demo' / 'capabilities' / (
        'vending_capabilities_extended.yaml'
    )

    with capabilities_path.open('r') as stream:
        capabilities = yaml.safe_load(stream)

    snack_capability = capabilities['capabilities']['snack']
    declared_outcomes = set(snack_capability['parameters']['outcomes'])

    assert snack_capability['parameters']['suggestion'] == 'snack'
    assert snack_capability['parameters']['suggestion'] in declared_outcomes


@pytest.mark.parametrize(
    ('pipeline_path', 'data_path'),
    (
        (
            PACKAGE_ROOT / 'example' / 'common' / 'pipelines' / 'preprocesses_def.yaml',
            PACKAGE_ROOT / 'example' / 'common' / 'pipelines' / 'preprocesses_data.yaml',
        ),
        (
            PACKAGE_ROOT / 'example' / 'common' / 'pipelines'
            / 'slugs_preprocesses_def.yaml',
            PACKAGE_ROOT / 'example' / 'vending_demo' / 'pipelines'
            / 'preprocesses_data.yaml',
        ),
        (
            PACKAGE_ROOT / 'example' / 'common' / 'pipelines'
            / 'slugs_preprocesses_def.yaml',
            PACKAGE_ROOT / 'example' / 'coffee_maker' / 'pipelines'
            / 'preprocesses_data.yaml',
        ),
    ),
    ids=lambda path: path.name,
)
def test_preprocess_data_keys_match_pipeline_inputs(pipeline_path, data_path):
    with data_path.open('r') as stream:
        data_config = yaml.safe_load(stream)

    assert set(data_config['/data']) <= _pipeline_input_keys(pipeline_path)


@pytest.mark.parametrize(
    'capabilities_path',
    EXAMPLE_CAPABILITIES,
    ids=lambda path: path.stem,
)
def test_generic_examples_generate_parseable_yaml(capabilities_path, tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(tmp_path))

    with capabilities_path.open('r') as stream:
        system_name = yaml.safe_load(stream)['name']

    capability_loader = capability_loader_main(
        [
            system_name,
            str(capabilities_path),
            _workspace_data(),
            deepcopy(STATE_MAPPINGS),
        ]
    )
    (
        system_capabilities,
        state_implementations_used,
        behavior_implementations_used,
    ) = capability_loader.preprocess()

    discrete_abstraction = generate_discrete_abstraction_main(
        [
            system_name,
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
        ]
    )
    discrete_abstraction.preprocess()

    transition_relations = generate_transition_relations_main(
        [
            system_name,
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
            _workspace_data(),
        ]
    )
    transition_relations.preprocess()

    generated_configs = sorted((tmp_path / system_name / 'configs').glob('*.yaml'))
    assert generated_configs
    for generated_config in generated_configs:
        with generated_config.open('r') as stream:
            assert yaml.safe_load(stream) is not None


def test_unmet_preconditions_generate_parseable_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(tmp_path))

    capabilities_path = tmp_path / 'unmet_capabilities.yaml'
    capabilities_path.write_text(
        """\
name: unmet_demo
capabilities:
    blocked:
        interface: LogState
        parameters:
            text: "Blocked"
        preconditions:
            - missing_capability
"""
    )

    capability_loader = capability_loader_main(
        [
            'unmet_demo',
            str(capabilities_path),
            _workspace_data(),
            deepcopy(STATE_MAPPINGS),
        ]
    )
    (
        system_capabilities,
        state_implementations_used,
        behavior_implementations_used,
    ) = capability_loader.preprocess()

    transition_relations = generate_transition_relations_main(
        [
            'unmet_demo',
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
            _workspace_data(),
        ]
    )
    transition_relations.preprocess()

    transition_config = (
        tmp_path / 'unmet_demo' / 'configs' / 'unmet_demo_transition_relations.yaml'
    )
    with transition_config.open('r') as stream:
        parsed_config = yaml.safe_load(stream)

    assert parsed_config['unmet_needs'] == ['missing_capability']


def test_transition_relation_variable_postcondition_satisfies_precondition(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(tmp_path))

    capabilities_path = tmp_path / 'variable_transition_capabilities.yaml'
    capabilities_path.write_text(
        """\
name: variable_transition_demo
transition_outcomes:
    - success
capabilities:
    choose:
        interface: LogState
        parameters:
            text: "Choose"
        transition_relation:
            success:
                - '@item'
    use_choice:
        interface: LogState
        parameters:
            text: "Use choice"
        preconditions:
            - item
"""
    )
    state_mappings = deepcopy(STATE_MAPPINGS)
    state_mappings['transition_outcomes'].append('success')

    capability_loader = capability_loader_main(
        [
            'variable_transition_demo',
            str(capabilities_path),
            _workspace_data(),
            state_mappings,
        ]
    )
    (
        system_capabilities,
        state_implementations_used,
        behavior_implementations_used,
    ) = capability_loader.preprocess()

    transition_relations = generate_transition_relations_main(
        [
            'variable_transition_demo',
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
            _workspace_data(),
        ]
    )
    transition_relations.preprocess()

    transition_config = (
        tmp_path
        / 'variable_transition_demo'
        / 'configs'
        / 'variable_transition_demo_transition_relations.yaml'
    )
    with transition_config.open('r') as stream:
        parsed_config = yaml.safe_load(stream)

    assert 'unmet_needs' not in parsed_config


def test_invalid_transition_relation_target_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(tmp_path))

    capabilities_path = tmp_path / 'invalid_transition_capabilities.yaml'
    capabilities_path.write_text(
        """\
name: invalid_transition_demo
capabilities:
    choose:
        interface: LogState
        parameters:
            text: "Choose"
        transition_relation:
            completed:
                - typo_target
"""
    )

    capability_loader = capability_loader_main(
        [
            'invalid_transition_demo',
            str(capabilities_path),
            _workspace_data(),
            deepcopy(STATE_MAPPINGS),
        ]
    )
    (
        system_capabilities,
        state_implementations_used,
        behavior_implementations_used,
    ) = capability_loader.preprocess()

    transition_relations = generate_transition_relations_main(
        [
            'invalid_transition_demo',
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
            _workspace_data(),
        ]
    )

    with pytest.raises(ValueError, match='typo_target'):
        transition_relations.preprocess()


def test_generated_yaml_preserves_special_character_strings(tmp_path, monkeypatch):
    monkeypatch.setenv('FLEXBE_SYNTHESIS_HOME', str(tmp_path))

    capabilities_path = tmp_path / 'special_strings_capabilities.yaml'
    capabilities_path.write_text(
        """\
name: special_strings_demo
capabilities:
    say_text:
        interface: LogState
        parameters:
            text: "Ready: go # keep this text"
        postconditions:
            - "mode=ready:go#ok"
"""
    )

    capability_loader = capability_loader_main(
        [
            'special_strings_demo',
            str(capabilities_path),
            _workspace_data(),
            deepcopy(STATE_MAPPINGS),
        ]
    )
    (
        system_capabilities,
        state_implementations_used,
        behavior_implementations_used,
    ) = capability_loader.preprocess()

    discrete_abstraction = generate_discrete_abstraction_main(
        [
            'special_strings_demo',
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
        ]
    )
    discrete_abstraction.preprocess()

    transition_relations = generate_transition_relations_main(
        [
            'special_strings_demo',
            system_capabilities,
            state_implementations_used,
            behavior_implementations_used,
            _workspace_data(),
        ]
    )
    transition_relations.preprocess()

    discrete_config = (
        tmp_path
        / 'special_strings_demo'
        / 'configs'
        / 'special_strings_demo_discrete_abstraction.yaml'
    )
    transition_config = (
        tmp_path
        / 'special_strings_demo'
        / 'configs'
        / 'special_strings_demo_transition_relations.yaml'
    )

    with discrete_config.open('r') as stream:
        parsed_discrete_config = yaml.safe_load(stream)
    with transition_config.open('r') as stream:
        parsed_transition_config = yaml.safe_load(stream)

    assert (
        parsed_discrete_config['say_text_a']['class_decl']['parameters']['text']
        == 'Ready: go # keep this text'
    )
    assert parsed_transition_config['action_postconditions']['say_text'][
        'completed'
    ] == ['mode=ready:go#ok']
