"""Setuptools entrypoint for the `flexbe_synthesis_generic` package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'flexbe_synthesis_generic'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'mappings'), glob('mappings/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    author='Joshua Luzier',
    maintainer='David Conner',
    maintainer_email='robotics@cnu.edu',
    description='Generic preprocessors and pipeline stages for FlexBE Synthesis.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            (
                'workspace_crawler = '
                'flexbe_synthesis_generic.preprocesses.workspace_crawler:stand_alone'
            ),
        ],
        'FlexBESynthesis.preprocesses': [
            (
                'capability_loader = '
                'flexbe_synthesis_generic.preprocesses.capability_loader:main'
            ),
            (
                'generate_transition_relations = '
                'flexbe_synthesis_generic.preprocesses.generate_transition_relations:main'
            ),
            (
                'generate_discrete_abstraction = '
                'flexbe_synthesis_generic.preprocesses.generate_discrete_abstraction:main'
            ),
            'state_mappings = flexbe_synthesis_generic.preprocesses.state_mappings:main',
            'workspace_crawler = flexbe_synthesis_generic.preprocesses.workspace_crawler:main',
            'workspace_parser = flexbe_synthesis_generic.preprocesses.workspace_parser:main',
        ],
        'FlexBESynthesis.processes': [
            'sm_layout = flexbe_synthesis_generic.processes.sm_layout:main',
            'sm_loader = flexbe_synthesis_generic.processes.sm_loader:main',
            (
                'system_capabilities_loader = '
                'flexbe_synthesis_generic.processes.system_capabilities_loader:main'
            ),
        ],
    },
)
