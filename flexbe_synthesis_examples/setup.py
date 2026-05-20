"""Setuptools entrypoint for `flexbe_synthesis_examples`."""

from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'flexbe_synthesis_examples'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('lib', package_name, 'manifest'), glob('manifest/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (
            os.path.join('share', package_name, 'example', 'common', 'pipelines'),
            glob('example/common/pipelines/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'hello_world', 'capabilities'),
            glob('example/hello_world/capabilities/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'hello_world', 'pipelines'),
            glob('example/hello_world/pipelines/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'hello_world', 'sm'),
            glob('example/hello_world/sm/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'coffee_maker', 'capabilities'),
            glob('example/coffee_maker/capabilities/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'coffee_maker', 'pipelines'),
            glob('example/coffee_maker/pipelines/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'coffee_maker', 'specs'),
            glob('example/coffee_maker/specs/*.yaml')
            + glob('example/coffee_maker/specs/*.structuredslugs'),
        ),
        (
            os.path.join('share', package_name, 'example', 'vending_demo', 'capabilities'),
            glob('example/vending_demo/capabilities/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'vending_demo', 'pipelines'),
            glob('example/vending_demo/pipelines/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'example', 'vending_demo', 'specs'),
            glob('example/vending_demo/specs/*.yaml'),
        ),
        (
            os.path.join('share', package_name, 'docs', 'hello_world'),
            glob('docs/hello_world/*.md') + glob('docs/hello_world/*.png'),
        ),
        (
            os.path.join('share', package_name, 'docs', 'vending'),
            glob('docs/vending/*.md') + glob('docs/vending/*.png'),
        ),
        (
            os.path.join('share', package_name, 'docs', 'coffee'),
            glob('docs/coffee/*.md') + glob('docs/coffee/*.png'),
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    author='Joshua Luzier',
    maintainer='David Conner',
    maintainer_email='robotics@cnu.edu',
    description=(
        'Minimal example capability files, launch files, and request clients '
        'for generic and Slugs-backed FlexBE Synthesis workflows.'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            (
                'demo_cancel_synthesis_request = '
                'flexbe_synthesis_examples.demo_cancel_synthesis_request:main'
            ),
            'request_hello_world = flexbe_synthesis_examples.request_hello_world:main',
            'request_vending = flexbe_synthesis_examples.request_vending:main',
            'request_coffee = flexbe_synthesis_examples.request_coffee:main',
        ],
    },
)
