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

"""Shared launch construction for Slugs-backed examples."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _example_path(*parts):
    return PathJoinSubstitution(
        [FindPackageShare('flexbe_synthesis_examples'), *parts]
    )


def _common_pipeline_path(file_name):
    return _example_path('example', 'common', 'pipelines', file_name)


def _demo_pipeline_path(demo, file_name):
    return _example_path('example', demo, 'pipelines', file_name)


def _demo_capabilities_path(demo, file_name):
    return _example_path('example', demo, 'capabilities', file_name)


def _demo_spec_path(demo, file_name):
    return _example_path('example', demo, 'specs', file_name)


def _mappings_path(file_name):
    return _example_path('example', 'mappings', file_name)


def make_slugs_launch_description(
    *,
    demo,
    capabilities_file,
    spec_file,
    processes_file,
    processes_data_file,
    preprocesses_data_file,
    global_mappings_file,
    custom_mappings_file='',
    preprocesses_file='slugs_preprocesses_def.yaml',
):
    """Create the common Slugs synthesis launch description."""
    custom_mappings_default = ''
    if custom_mappings_file:
        custom_mappings_default = _mappings_path(custom_mappings_file)

    declared_arguments = [
        DeclareLaunchArgument(
            'global_mappings_path',
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare('flexbe_synthesis_generic'),
                    'mappings',
                    global_mappings_file,
                ]
            ),
            description='Path to global outcome mapping file',
        ),
        DeclareLaunchArgument(
            'custom_mappings_path',
            default_value=custom_mappings_default,
            description='Optional path to custom outcome mapping overrides',
        ),
        DeclareLaunchArgument(
            'capabilities_path',
            default_value=_demo_capabilities_path(demo, capabilities_file),
            description='Path to capabilities file',
        ),
        DeclareLaunchArgument(
            'spec_path',
            default_value=_demo_spec_path(demo, spec_file),
            description='Path to slugs specification file',
        ),
        DeclareLaunchArgument(
            'preprocesses_path',
            default_value=_common_pipeline_path(preprocesses_file),
            description='Path to preprocess pipeline definition file',
        ),
        DeclareLaunchArgument(
            'preprocesses_data_path',
            default_value=_demo_pipeline_path(demo, preprocesses_data_file),
            description='Path to preprocess pipeline data file',
        ),
        DeclareLaunchArgument(
            'processes_path',
            default_value=_common_pipeline_path(processes_file),
            description='Path to process pipeline definition file',
        ),
        DeclareLaunchArgument(
            'processes_data_path',
            default_value=_demo_pipeline_path(demo, processes_data_file),
            description='Path to process pipeline data file',
        ),
    ]

    synthesis_node = Node(
        package='flexbe_synthesis_core',
        executable='flexbe_synthesis_server',
        name='flexbe_synthesis',
        output='screen',
        parameters=[
            {
                'processes_filepath': LaunchConfiguration('processes_path'),
                'processes_data_filepath': LaunchConfiguration('processes_data_path'),
                'preprocesses_filepath': LaunchConfiguration('preprocesses_path'),
                'preprocesses_data_filepath': LaunchConfiguration('preprocesses_data_path'),
                'global_mappings_path': LaunchConfiguration('global_mappings_path'),
                'custom_mappings_path': LaunchConfiguration('custom_mappings_path'),
                'capabilities_path': LaunchConfiguration('capabilities_path'),
                'spec_path': LaunchConfiguration('spec_path'),
            }
        ],
    )
    return LaunchDescription(declared_arguments + [synthesis_node])
