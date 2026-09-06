"""Setuptools entrypoint for `flexbe_synthesis_slugs`."""

from setuptools import find_packages, setup

package_name = 'flexbe_synthesis_slugs'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name, ['THIRD_PARTY_LICENSES.md']),
        (
            'share/' + package_name + '/docs',
            [
                'docs/auditor.md',
                'docs/batch_run_harness.md',
                'docs/clause_ordering_check.md',
                'docs/coffee_experiment_runbook.md',
                'docs/fairness_livelock_detection.md',
                'docs/multi_run_sampling.md',
                'docs/ordering_study_figure.md',
                'docs/state_generation.md',
                'docs/variable_ordering.md',
                'docs/variable_ordering_study.md',
                'docs/well_separation_analyzer.md',
            ],
        ),
        ('share/' + package_name + '/scripts', ['scripts/install_slugs.sh']),
        (
            'share/' + package_name + '/licenses/structured_slugs_parser',
            ['flexbe_synthesis_slugs/helpers/structured_slugs_parser/LICENSE.txt'],
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    author='Joshua Luzier',
    maintainer='David Conner',
    maintainer_email='robotics@cnu.edu',
    description=(
        'Slugs-based GR(1) synthesis backend, specification helpers, and state machine '
        'generation for FlexBE Synthesis.'
    ),
    license='Apache-2.0 AND BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            (
                'validate_slugs_install = '
                'flexbe_synthesis_slugs.preprocesses.validate_slugs_install:stand_alone'
            ),
            (
                'check_slugs_automaton = '
                'flexbe_synthesis_slugs.helpers.slugs_automaton_checker:main'
            ),
            'count_slugs_specs = flexbe_synthesis_slugs.helpers.count_specs:main',
            (
                'slugs_experiment_postprocess = '
                'flexbe_synthesis_slugs.helpers.experiment_postprocess:main'
            ),
            'inspect_slugs_specs = flexbe_synthesis_slugs.helpers.inspect_specs:main',
            'mealy2dot = flexbe_synthesis_slugs.helpers.mealy2dot:main',
            'slugs_batch_run_harness = flexbe_synthesis_slugs.helpers.batch_run_harness:main',
            'slugs_coffee_matrix = flexbe_synthesis_slugs.helpers.coffee_matrix:main',
            'slugs_stats_helper = flexbe_synthesis_slugs.helpers.slugs_stats_helper:main',
            'slugs_timing_stats = flexbe_synthesis_slugs.helpers.slugs_timing_stats:main',
            'trap_excerpt = flexbe_synthesis_slugs.helpers.trap_excerpt:main',
        ],
        'FlexBESynthesis.preprocesses': [
            (
                'validate_slugs_install = '
                'flexbe_synthesis_slugs.preprocesses.validate_slugs_install:main'
            ),
        ],
        'FlexBESynthesis.processes': [
            (
                'slugs_automaton_loader = '
                'flexbe_synthesis_slugs.processes.slugs_automaton_loader:main'
            ),
            'slugs_mealy_graph = flexbe_synthesis_slugs.processes.slugs_mealy_graph:main',
            'slugs_sm_generator = flexbe_synthesis_slugs.processes.slugs_sm_generator:main',
            'slugs_sm_reducer = flexbe_synthesis_slugs.processes.slugs_sm_reducer:main',
            'slugs_spec_compiler = flexbe_synthesis_slugs.processes.slugs_spec_compiler:main',
            (
                'slugs_well_separation_analyzer = '
                'flexbe_synthesis_slugs.processes.slugs_well_separation_analyzer:main'
            ),
            'slugs_count_specs = flexbe_synthesis_slugs.processes.slugs_count_specs:main',
            'slugs_spec_loader = flexbe_synthesis_slugs.processes.slugs_spec_loader:main',
            'slugs_synthesizer = flexbe_synthesis_slugs.processes.slugs_synthesizer:main',
            'strategy_auditor = flexbe_synthesis_slugs.processes.strategy_auditor:main',
            # Specification generation processes
            (
                'slugs_capability_specification = '
                'flexbe_synthesis_slugs.processes.slugs_capability_specification:main'
            ),
            (
                'slugs_request_specification = '
                'flexbe_synthesis_slugs.processes.slugs_request_specification:main'
            ),
            (
                'slugs_transition_system_specification = '
                'flexbe_synthesis_slugs.processes.slugs_transition_system_specification:main'
            ),
            (
                'slugs_pending_specification = '
                'flexbe_synthesis_slugs.processes.slugs_pending_specification:main'
            ),
            (
                'slugs_system_goal_liveness = '
                'flexbe_synthesis_slugs.processes.slugs_system_goal_liveness:main'
            ),
            (
                'slugs_fair_outcome_liveness = '
                'flexbe_synthesis_slugs.processes.slugs_fair_outcome_liveness:main'
            ),
            (
                'slugs_activation_specification_parsed = '
                'flexbe_synthesis_slugs.processes.slugs_activation_specification_parsed:main'
            ),
        ],
    },
)
