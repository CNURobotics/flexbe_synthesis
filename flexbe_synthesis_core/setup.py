"""Setuptools entrypoint for the `flexbe_synthesis_core` package."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'flexbe_synthesis_core'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (
            os.path.join('share', package_name, 'pipeline'),
            glob(os.path.join('pipeline', '*.yaml')),
        ),
        (os.path.join('share', package_name), glob(os.path.join('launch', '*.launch.py'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    author='Joshua Luzier',
    maintainer='David Conner',
    maintainer_email='robotics@cnu.edu',
    description=(
        'Core synthesis manager, plugin interfaces, and pipeline utilities '
        'for FlexBE Synthesis.'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'flexbe_synthesis_server = flexbe_synthesis_core.synthesis_manager:main',
            'request_synthesis = flexbe_synthesis_core.request_synthesis:main',
        ],
    },
)
