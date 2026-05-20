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

"""Launch preprocessing-only demo pipeline for vending example."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Create launch description for generic preprocessing demo."""
    declared_arguments = [
        DeclareLaunchArgument(
            'system_name',
            default_value='vending_demo',
            description='System name used by the preprocessing pipeline',
        ),
        DeclareLaunchArgument(
            'global_mappings_path',
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare('flexbe_synthesis_generic'),
                    'mappings',
                    'global_mappings.yaml',
                ]
            ),
            description='Path to global outcome mapping file',
        ),
        DeclareLaunchArgument(
            'capabilities_path',
            default_value=PathJoinSubstitution(
                [
                    FindPackageShare('flexbe_synthesis_examples'),
                    'example',
                    'vending_demo',
                    'capabilities',
                    'vending_capabilities.yaml',
                ]
            ),
            description='Path to capabilities file',
        ),
    ]

    synthesis_node = Node(
        package='flexbe_synthesis_core',
        executable='flexbe_synthesis_server',
        name='flexbe_synthesis',
        output='screen',
        parameters=[
            {
                'custom_mappings_path': '',
                'system_name': LaunchConfiguration('system_name'),
                'capabilities_path': LaunchConfiguration('capabilities_path'),
                'processes_filepath': PathJoinSubstitution(
                    [
                        FindPackageShare('flexbe_synthesis_examples'),
                        'example',
                        'common',
                        'pipelines',
                        'empty_processes_def.yaml',
                    ]
                ),
                'processes_data_filepath': PathJoinSubstitution(
                    [
                        FindPackageShare('flexbe_synthesis_examples'),
                        'example',
                        'common',
                        'pipelines',
                        'empty_processes_data.yaml',
                    ]
                ),
                'preprocesses_filepath': PathJoinSubstitution(
                    [
                        FindPackageShare('flexbe_synthesis_examples'),
                        'example',
                        'common',
                        'pipelines',
                        'preprocesses_def.yaml',
                    ]
                ),
                'preprocesses_data_filepath': PathJoinSubstitution(
                    [
                        FindPackageShare('flexbe_synthesis_examples'),
                        'example',
                        'common',
                        'pipelines',
                        'preprocesses_data.yaml',
                    ]
                ),
                'global_mappings_path': LaunchConfiguration('global_mappings_path'),
            }
        ],
    )

    return LaunchDescription(declared_arguments + [synthesis_node])
