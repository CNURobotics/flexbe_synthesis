#!/usr/bin/env python3

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

"""Run generic Slugs synthesis experiment matrices and emit raw trial rows."""

from __future__ import annotations

import argparse
import contextlib
import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time
from typing import Any

from ament_index_python.packages import get_package_share_directory
from flexbe_synthesis_core import predefined_strings as fpths
from flexbe_synthesis_generic.preprocesses.capability_loader import (
    main as capability_loader_main,
)
from flexbe_synthesis_generic.preprocesses.generate_discrete_abstraction import (
    main as discrete_abstraction_main,
)
from flexbe_synthesis_generic.preprocesses.generate_transition_relations import (
    main as transition_relations_main,
)
from flexbe_synthesis_generic.preprocesses.workspace_parser import main as workspace_parser_main
from flexbe_synthesis_generic.processes.sm_layout import main as sm_layout_main
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.csv_summary_helpers import (
    realizable_summary,
    reordering_policy,
    text_summary,
)
from flexbe_synthesis_slugs.helpers.slugs_stats_helper import parse_slugs_log
from flexbe_synthesis_slugs.processes.slugs_activation_specification_parsed import (
    main as parsed_activation_main,
)
from flexbe_synthesis_slugs.processes.slugs_capability_specification import (
    main as capability_spec_main,
)
from flexbe_synthesis_slugs.processes.slugs_count_specs import main as count_specs_main
from flexbe_synthesis_slugs.processes.slugs_fair_outcome_liveness import (
    main as fair_liveness_main,
)
from flexbe_synthesis_slugs.processes.slugs_mealy_graph import main as mealy_graph_main
from flexbe_synthesis_slugs.processes.slugs_pending_specification import (
    main as pending_spec_main,
)
from flexbe_synthesis_slugs.processes.slugs_request_specification import (
    main as request_spec_main,
)
from flexbe_synthesis_slugs.processes.slugs_sm_generator import main as sm_generator_main
from flexbe_synthesis_slugs.processes.slugs_sm_reducer import main as reducer_main
from flexbe_synthesis_slugs.processes.slugs_spec_compiler import main as compiler_main
from flexbe_synthesis_slugs.processes.slugs_spec_loader import main as spec_loader_main
from flexbe_synthesis_slugs.processes.slugs_synthesizer import main as synthesizer_main
from flexbe_synthesis_slugs.processes.slugs_system_goal_liveness import (
    main as system_goal_liveness_main,
)
from flexbe_synthesis_slugs.processes.slugs_transition_system_specification import (
    main as transition_spec_main,
)
from flexbe_synthesis_slugs.processes.slugs_well_separation_analyzer import (
    main as well_separation_main,
)
from flexbe_synthesis_slugs.processes.strategy_auditor import (
    main as strategy_auditor_main,
)
import yaml


def parse_bool(value: Any, field_name: str) -> bool:
    """Parse YAML/CSV bool-like values without treating non-empty strings as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', 'yes', 'on', '1'):
            return True
        if normalized in ('false', 'no', 'off', '0', ''):
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError(f"Invalid boolean for '{field_name}': {value!r}")


CSV_FIELDNAMES = [
    'example',
    'system_name',
    'spec_name',
    'capability_file',
    'encoding',
    'liveness',
    'pending',
    'column_indicator',
    'ordering_mode',
    'ordering_seed',
    'reordering_enabled',
    'reordering_threshold',
    'reordering_policy',
    'run_index',
    'row_id',
    'timestamp',
    'hostname',
    'git_sha_flexbe_synthesis',
    'git_sha_slugs',
    'return_code',
    'error_code',
    'realizable',
    'ap_i',
    'ap_o',
    'env_init_count',
    'sys_init_count',
    'env_trans_count',
    'sys_trans_count',
    'env_liveness_count',
    'sys_liveness_count',
    'realizability_time_s',
    'extraction_time_s',
    'spec_loader_time_s',
    'capability_spec_time_s',
    'transition_spec_time_s',
    'request_spec_time_s',
    'system_goal_liveness_time_s',
    'fair_outcome_liveness_time_s',
    'pending_spec_time_s',
    'activation_spec_time_s',
    'compiler_time_s',
    'well_separation_analyzer_time_s',
    'well_separation_wrapper_wall_time_s',
    'synthesizer_time_s',
    'original_auditor_time_s',
    'auditor_time_s',
    'mealy_graph_time_s',
    'reduction_time_s',
    'reduced_mealy_graph_time_s',
    'sm_generation_time_s',
    'sm_layout_time_s',
    'count_specs_time_s',
    'generate_specs_time_s',
    'realize_hfsm_time_s',
    'overall_pipeline_time_s',
    'cudd_peak_nodes',
    'cudd_live_nodes',
    'cudd_var_count',
    'cudd_reordering_enabled',
    'cudd_next_reordering',
    'cudd_reorderings',
    'cudd_reordering_time_s',
    'slugs_sm_size',
    'reduced_sm_size',
    'state_defn_size',
    'flexbe_hfsm_realized',
    'original_audit_valid',
    'original_audit_incomplete',
    'original_audit_failure_kind',
    'audit_valid',
    'audit_incomplete',
    'audit_failure_kind',
    'requested_input_order',
    'requested_output_order',
    'final_variable_order',
    'trial_dir',
    'slugs_output_file',
    'slugs_json_file',
    'variable_order_file',
    'stage_timing_json_file',
    'max_non_slugs_stage',
    'max_non_slugs_time_s',
    'non_slugs_total_time_s',
    'well_separation_status',
    'well_separation_complete',
    'violated_assumption_type',
    'well_separation_cases',
    'well_separation_responsible_assumption_count',
    'well_separation_warnings',
    'slugs_reported_elapsed_time_s',
    'slugs_timing_total_s',
    'core_minimization_s',
    'core_enabled',
    'core_complete',
    'core_candidate_count',
    'core_solver_calls',
    'core_size',
    'core_kinds',
    'core_indices',
    'core_source_indices',
    'core_lines',
    'core_assumptions',
    'well_separation_json_file',
    'well_separation_output_file',
    'failure',
]

SUMMARY_KEYS = [
    'capability_file',
    'encoding',
    'liveness',
    'pending',
    'column_indicator',
    'ordering_mode',
    'reordering_enabled',
    'reordering_threshold',
    'reordering_policy',
]

SUMMARY_NUMERIC_FIELDS = [
    'cudd_peak_nodes',
    'cudd_live_nodes',
    'realizability_time_s',
    'extraction_time_s',
    'original_auditor_time_s',
    'auditor_time_s',
    'mealy_graph_time_s',
    'reduction_time_s',
    'reduced_mealy_graph_time_s',
    'sm_generation_time_s',
    'sm_layout_time_s',
    'count_specs_time_s',
    'well_separation_analyzer_time_s',
    'generate_specs_time_s',
    'realize_hfsm_time_s',
    'overall_pipeline_time_s',
    'max_non_slugs_time_s',
    'non_slugs_total_time_s',
    'slugs_sm_size',
    'reduced_sm_size',
    'state_defn_size',
    'ap_i',
    'ap_o',
    'env_init_count',
    'sys_init_count',
    'env_trans_count',
    'sys_trans_count',
    'env_liveness_count',
    'sys_liveness_count',
    'cudd_reorderings',
    'cudd_next_reordering',
    'cudd_reordering_time_s',
    'slugs_reported_elapsed_time_s',
    'slugs_timing_total_s',
    'core_minimization_s',
    'core_candidate_count',
    'core_solver_calls',
    'core_size',
]

SUMMARY_TEXT_FIELDS = [
    'flexbe_hfsm_realized',
    'well_separation_status',
    'well_separation_complete',
    'violated_assumption_type',
    'core_enabled',
    'core_complete',
    'max_non_slugs_stage',
]

NON_FATAL_ERROR_CODES = frozenset({SynthesisErrorCode.AUDIT_INCOMPLETE})

STAGE_TIME_FIELDS = [
    'spec_loader_time_s',
    'capability_spec_time_s',
    'transition_spec_time_s',
    'request_spec_time_s',
    'system_goal_liveness_time_s',
    'fair_outcome_liveness_time_s',
    'pending_spec_time_s',
    'activation_spec_time_s',
    'compiler_time_s',
    'well_separation_analyzer_time_s',
    'well_separation_wrapper_wall_time_s',
    'synthesizer_time_s',
    'original_auditor_time_s',
    'mealy_graph_time_s',
    'reduction_time_s',
    'auditor_time_s',
    'reduced_mealy_graph_time_s',
    'sm_generation_time_s',
    'sm_layout_time_s',
    'count_specs_time_s',
]

NON_SLUGS_STAGE_TIME_FIELDS = [
    field for field in STAGE_TIME_FIELDS
    if field not in (
        'well_separation_analyzer_time_s',
        'well_separation_wrapper_wall_time_s',
        'synthesizer_time_s',
    )
]

GENERATE_SPECS_STAGE_TIME_FIELDS = [
    'spec_loader_time_s',
    'capability_spec_time_s',
    'transition_spec_time_s',
    'request_spec_time_s',
    'system_goal_liveness_time_s',
    'fair_outcome_liveness_time_s',
    'pending_spec_time_s',
    'activation_spec_time_s',
    'compiler_time_s',
]

REALIZE_HFSM_STAGE_TIME_FIELDS = [
    'reduced_mealy_graph_time_s',
    'sm_generation_time_s',
    'sm_layout_time_s',
    'count_specs_time_s',
]


@dataclass
class MatrixRow:
    """One experiment-matrix row, before expanding repeated trials."""

    example: str
    system_name: str
    spec_name: str
    spec_path: Path
    capabilities_path: Path
    encoding: str
    liveness: str
    pending: bool
    column_indicator: str = ''
    ordering_mode: str = 'alphabetic'
    ordering_seed: int | None = None
    reordering_enabled: bool = True
    reordering_threshold: int | None = None
    n_trials: int = 1
    initial_conditions: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    audit_goals: tuple[str, ...] = ()
    sm_outcomes: tuple[str, ...] = ()
    full_spec: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatrixRow:
        """Create a row from YAML config data."""
        capabilities_path = Path(
            data.get('capabilities_path') or data.get('capability_file')
        ).expanduser()
        spec_path = Path(data['spec_path']).expanduser()
        return cls(
            example=str(data.get('example', capabilities_path.parent.name)),
            system_name=str(data['system_name']),
            spec_name=str(data['spec_name']),
            spec_path=spec_path,
            capabilities_path=capabilities_path,
            encoding=str(data['encoding']),
            liveness=str(data['liveness']),
            pending=parse_bool(data.get('pending', False), 'pending'),
            column_indicator=str(data.get('column_indicator', '')),
            ordering_mode=str(data.get('ordering_mode', 'alphabetic')),
            ordering_seed=data.get('ordering_seed'),
            reordering_enabled=parse_bool(
                data.get('reordering_enabled', True),
                'reordering_enabled',
            ),
            reordering_threshold=(
                int(data['reordering_threshold'])
                if data.get('reordering_threshold') not in (None, '') else None
            ),
            n_trials=int(data.get('n_trials', 1)),
            initial_conditions=tuple(data.get('initial_conditions', [])),
            goals=tuple(data.get('goals', [])),
            audit_goals=tuple(data.get('audit_goals', data.get('goals', []))),
            sm_outcomes=tuple(data.get('sm_outcomes', [])),
            full_spec=parse_bool(data.get('full_spec', False), 'full_spec'),
        )

    @property
    def row_id(self):
        """Return stable filesystem slug for this matrix row."""
        cap_stem = self.capabilities_path.stem
        pending_name = 'with_pending' if self.pending else 'no_pending'
        seed = 'none' if self.ordering_seed is None else str(self.ordering_seed)
        return '__'.join([
            self.example,
            cap_stem,
            self.spec_name,
            self.encoding,
            self.liveness,
            pending_name,
            self.ordering_mode,
            f'seed{seed}',
            self.reordering_policy,
        ])

    @property
    def progress_key(self):
        """Return the combo key used for concise progress reporting."""
        return (
            str(self.capabilities_path),
            self.encoding,
            self.liveness,
            self.pending,
            self.ordering_mode,
            self.reordering_policy,
        )

    @property
    def reordering_policy(self):
        """Return the named reordering policy for grouping and reporting."""
        if not self.reordering_enabled:
            return 'off'
        if self.reordering_threshold is not None:
            return f'threshold_{self.reordering_threshold}'
        return 'auto'

    @property
    def progress_title(self):
        """Return a short human-readable combo title."""
        cap_stem = self.capabilities_path.stem
        pending_name = 'pending' if self.pending else 'no pending'
        return (
            f'{cap_stem}, {self.encoding}, {self.liveness}, {pending_name}, '
            f'{self.ordering_mode}, {self.reordering_policy}'
        )


def load_matrix(path: Path) -> list[MatrixRow]:
    """Load matrix rows from YAML."""
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        rows = data.get('rows', [])
    else:
        rows = data
    if not isinstance(rows, list):
        raise ValueError('Matrix YAML must contain a list or a mapping with rows.')
    return [MatrixRow.from_dict(row) for row in rows]


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping."""
    with path.open(encoding='utf-8') as yaml_file:
        data = yaml.safe_load(yaml_file)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file '{path}' must contain a top-level mapping.")
    return data


def default_state_mappings_path() -> Path:
    """Return the installed global mappings path."""
    package_share = Path(get_package_share_directory('flexbe_synthesis_generic'))
    return package_share / 'mappings' / 'global_mappings.yaml'


def resolve_state_mappings_path(path: Path | str) -> Path:
    """Resolve state mappings from cwd, workspace source, or package share."""
    if isinstance(path, str) and not path:
        raise FileNotFoundError(
            'State mappings path is empty; pass --state-mappings or set the '
            'environment variable used by that argument.'
        )
    expanded = Path(path).expanduser()
    candidates = [expanded]
    if not expanded.is_absolute():
        candidates.append(Path.cwd() / 'src' / 'flexbe_synthesis' / expanded)
    if len(expanded.parts) >= 3 and expanded.parts[-3:-1] == (
        'flexbe_synthesis_generic',
        'mappings',
    ):
        package_share = Path(get_package_share_directory('flexbe_synthesis_generic'))
        candidates.append(package_share / 'mappings' / expanded.name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    tried = ', '.join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"State mappings file '{path}' not found; tried {tried}.")


def git_sha(path: Path) -> str:
    """Return git HEAD SHA for a repository path, or empty string."""
    try:
        result = subprocess.run(
            ['git', '-C', str(path), 'rev-parse', 'HEAD'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def build_request(row: MatrixRow) -> FlexBESynthesisRequest:
    """Build the request message consumed by SlugsRequestSpecification."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = list(row.initial_conditions)
    request.goals = list(row.goals)
    request.sm_outcomes = list(row.sm_outcomes)
    request.system_name = row.system_name
    request.spec_name = row.spec_name
    return request


def prepare_system_capabilities(row: MatrixRow, state_mappings, synthesis_home=None):
    """Load capability file and generate transition relation data."""
    if synthesis_home:
        _ensure_workspace_defn(Path(synthesis_home))
    workspace_parser = workspace_parser_main([state_mappings])
    if synthesis_home:
        workspace_parser.synthesis_home = synthesis_home
    workspace_data, _ = workspace_parser.preprocess()
    loader = capability_loader_main([
        row.system_name,
        str(row.capabilities_path),
        workspace_data,
        state_mappings,
    ])
    if synthesis_home:
        loader.synthesis_home = synthesis_home
    system_capabilities, state_impls, behaviors = loader.preprocess()

    transition_gen = transition_relations_main([
        row.system_name,
        system_capabilities,
        state_impls,
        behaviors,
        workspace_data,
    ])
    if synthesis_home:
        transition_gen.synthesis_home = synthesis_home
    (
        system_capabilities,
        _transition_relations,
        _system_preconditions,
        _system_postconditions,
        state_impls,
        behaviors,
    ) = transition_gen.preprocess()

    discrete_gen = discrete_abstraction_main([
        row.system_name,
        system_capabilities,
        state_impls,
        behaviors,
    ])
    if synthesis_home:
        discrete_gen.synthesis_home = synthesis_home
    discrete_gen.preprocess()

    config_path = (
        Path(synthesis_home or fpths.get_synthesis_home())
        / row.system_name
        / 'configs'
        / f'{row.system_name}{fpths._TRANSITION_RELATIONS_CONFIG_EXT}'
    )
    transition_config = load_yaml(config_path)
    transition_config.pop('name', None)
    system_capabilities.update(transition_config)
    return system_capabilities


def _ensure_workspace_defn(synthesis_home: Path):
    """Copy workspace definition into an override synthesis home if needed."""
    synthesis_home.mkdir(parents=True, exist_ok=True)
    target = synthesis_home / 'workspace_defn.yaml'
    if target.exists():
        return
    source = Path(fpths.get_synthesis_home()) / 'workspace_defn.yaml'
    if source.exists():
        shutil.copy2(source, target)


def build_spec(row: MatrixRow, state_mappings, system_capabilities, stage_times=None):
    """Run the Slugs spec-generation process chain for one row."""
    stage_times = stage_times if stage_times is not None else {}
    spec = _time_process(
        'spec_loader_time_s',
        stage_times,
        lambda: spec_loader_main([
            row.spec_name,
            row.system_name,
            str(row.spec_path),
        ]).process()[0],
    )

    if row.full_spec:
        # Hand-written full spec (paper Table I column 1): the loaded spec is
        # already complete, so skip the capability/liveness/pending generation
        # steps and only bind the request goal, mirroring
        # full_spec_processes_def.yaml (spec_loader -> request_spec -> compiler
        # -> synthesizer). Variable ordering and CUDD reordering still apply via
        # the shared compiler/synthesizer path, so this row participates in the
        # ordering sweep like any other; encoding/liveness/pending do not apply.
        return _time_process(
            'request_spec_time_s',
            stage_times,
            lambda: request_spec_main([
                row.spec_name,
                build_request(row),
                system_capabilities,
                spec,
            ]).process()[0],
        )

    spec = _time_process(
        'capability_spec_time_s',
        stage_times,
        lambda: capability_spec_main([
            row.spec_name,
            system_capabilities,
            spec,
        ]).process()[0],
    )
    spec = _time_process(
        'transition_spec_time_s',
        stage_times,
        lambda: transition_spec_main([
            row.spec_name,
            system_capabilities,
            spec,
        ]).process()[0],
    )
    spec = _time_process(
        'request_spec_time_s',
        stage_times,
        lambda: request_spec_main([
            row.spec_name,
            build_request(row),
            system_capabilities,
            spec,
        ]).process()[0],
    )

    if row.liveness.upper() == 'S':
        spec = _time_process(
            'system_goal_liveness_time_s',
            stage_times,
            lambda: system_goal_liveness_main([
                row.spec_name,
                system_capabilities,
                spec,
            ]).process()[0],
        )
    elif row.liveness.upper() == 'F':
        spec = _time_process(
            'fair_outcome_liveness_time_s',
            stage_times,
            lambda: fair_liveness_main([
                row.spec_name,
                system_capabilities,
                spec,
            ]).process()[0],
        )
    else:
        raise ValueError(f"Unknown liveness mode '{row.liveness}'.")

    if row.pending:
        spec = _time_process(
            'pending_spec_time_s',
            stage_times,
            lambda: pending_spec_main([
                row.spec_name,
                system_capabilities,
                spec,
            ]).process()[0],
        )

    if row.encoding in ('enumerated', 'parsed'):
        spec = _time_process(
            'activation_spec_time_s',
            stage_times,
            lambda: parsed_activation_main([
                row.spec_name,
                system_capabilities,
                spec,
            ]).process()[0],
        )
    elif row.encoding != 'one-hot':
        raise ValueError(f"Unknown encoding '{row.encoding}'.")

    return spec


def empty_audit() -> dict[str, Any]:
    """Return a blank audit record for trials that never reach the auditor."""
    return {
        'auditor_time_s': None,
        'audit_valid': None,
        'audit_incomplete': None,
        'audit_failure_kind': '',
    }


def run_audit(automaton, spec, row, trial_dir, state_mappings, system_capabilities, timeout_s):
    """Run the strategy auditor on the synthesized automaton and time it."""
    audit = empty_audit()
    if not isinstance(automaton, dict) or not automaton.get('automaton'):
        return audit
    start = time.monotonic()
    result, _ec = strategy_auditor_main([
        automaton,
        str(trial_dir),
        row.spec_name,
        system_capabilities,
        state_mappings,
        spec,
        '',                   # spec path: use the generated .slugsin
        list(row.audit_goals),  # goal outcomes
        timeout_s,
    ]).process()
    audit['auditor_time_s'] = time.monotonic() - start
    audit['audit_valid'] = result.get('valid')
    audit['audit_incomplete'] = result.get('incomplete')
    audit['audit_failure_kind'] = result.get('failure_kind') or ''
    audit['error_code'] = _code_value(_ec)
    return audit


def prefix_audit(audit: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Return audit fields under a prefixed CSV namespace."""
    return {
        f'{prefix}_auditor_time_s': audit.get('auditor_time_s'),
        f'{prefix}_audit_valid': audit.get('audit_valid'),
        f'{prefix}_audit_incomplete': audit.get('audit_incomplete'),
        f'{prefix}_audit_failure_kind': audit.get('audit_failure_kind', ''),
    }


def empty_stage_times() -> dict[str, Any]:
    """Return blank timings for manager-like post-synthesis stages."""
    return {field: None for field in STAGE_TIME_FIELDS}


def _code_value(error_code) -> int | None:
    """Normalize SynthesisErrorCode messages and raw ints to an integer value."""
    if error_code is None:
        return None
    return getattr(error_code, 'value', error_code)


def _fatal_code(error_code) -> int | None:
    """Return a fatal error code, or None for success/non-fatal degraded codes."""
    code = _code_value(error_code)
    if code in (None, SynthesisErrorCode.SUCCESS) or code in NON_FATAL_ERROR_CODES:
        return None
    return code


def _record_degraded(current: int | None, error_code) -> int | None:
    """Track the first manager-style non-fatal pipeline code."""
    code = _code_value(error_code)
    if current is None and code in NON_FATAL_ERROR_CODES:
        return code
    return current


def _time_process(field: str, stage_times: dict[str, Any], callback):
    """Run one process callback and record wall time under `field`."""
    start = time.monotonic()
    result = callback()
    stage_times[field] = time.monotonic() - start
    return result


def _numeric_stage_times(stage_times: dict[str, Any], fields) -> dict[str, float]:
    """Return present numeric stage timings for the requested fields."""
    values = {}
    for field in fields:
        value = stage_times.get(field)
        if isinstance(value, (int, float)):
            values[field] = float(value)
        elif value not in (None, ''):
            try:
                values[field] = float(value)
            except (TypeError, ValueError):
                pass
    return values


def stage_time_sum(stage_times: dict[str, Any], fields) -> float | str:
    """Return the sum of present stage timings, or blank when none ran."""
    timings = _numeric_stage_times(stage_times, fields)
    return sum(timings.values()) if timings else ''


def non_slugs_timing_summary(stage_times: dict[str, Any]) -> dict[str, Any]:
    """Summarize the largest measured Python-side stage for compact CSV output."""
    timings = _numeric_stage_times(stage_times, NON_SLUGS_STAGE_TIME_FIELDS)
    if not timings:
        return {
            'max_non_slugs_stage': '',
            'max_non_slugs_time_s': '',
            'non_slugs_total_time_s': '',
        }
    max_stage, max_time = max(timings.items(), key=lambda item: item[1])
    return {
        'max_non_slugs_stage': max_stage.removesuffix('_time_s'),
        'max_non_slugs_time_s': max_time,
        'non_slugs_total_time_s': sum(timings.values()),
    }


def write_stage_timing_json(path: Path, stage_times: dict[str, Any]):
    """Write detailed stage timings for one trial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        field: stage_times.get(field)
        for field in STAGE_TIME_FIELDS
        if stage_times.get(field) is not None
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def compact_json(value: Any) -> str:
    """Return compact JSON text for structured CSV fields."""
    if value in (None, ''):
        return ''
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def stable_join(values) -> str:
    """Join present values into a stable semicolon-separated CSV cell."""
    return ';'.join(
        str(value)
        for value in values
        if value not in (None, '')
    )


def empty_well_separation() -> dict[str, Any]:
    """Return a blank well-separation record for trials that never run it."""
    return {
        'result': {},
        'error_code': None,
    }


def run_well_separation(trial_dir, row, args) -> dict[str, Any]:
    """Run the Slugs well-separation analyzer and return its structured result."""
    if getattr(args, 'skip_well_separation', False):
        return empty_well_separation()

    result, error_code = well_separation_main([
        str(trial_dir),
        row.spec_name,
        getattr(args, 'well_separation_timeout_s', 1800.0),
        getattr(args, 'fail_on_non_well_separated', False),
        getattr(args, 'fail_on_incomplete_well_separation', False),
        getattr(args, 'minimize_well_separation_core', False),
        args.slugs_bin,
    ]).process()
    return {
        'result': result if isinstance(result, dict) else {},
        'error_code': error_code.value,
    }


def well_separation_process_time(well_separation: dict[str, Any]) -> float | None:
    """Return Slugs-reported well-separation process time, if available."""
    data = well_separation.get('result') or {}
    timing = data.get('timing') if isinstance(data.get('timing'), dict) else {}
    for value in (timing.get('total'), data.get('elapsed_time')):
        if value in (None, ''):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def flatten_well_separation(well_separation: dict[str, Any]) -> dict[str, Any]:
    """Flatten Slugs well-separation JSON into stable master.csv fields."""
    data = well_separation.get('result') or {}
    fieldnames = [
        'well_separation_status',
        'well_separation_complete',
        'violated_assumption_type',
        'well_separation_cases',
        'well_separation_responsible_assumption_count',
        'well_separation_warnings',
        'slugs_reported_elapsed_time_s',
        'slugs_timing_total_s',
        'core_minimization_s',
        'core_enabled',
        'core_complete',
        'core_candidate_count',
        'core_solver_calls',
        'core_size',
        'core_kinds',
        'core_indices',
        'core_source_indices',
        'core_lines',
        'core_assumptions',
        'well_separation_json_file',
        'well_separation_output_file',
    ]
    if not data:
        return {field: '' for field in fieldnames}

    timing = data.get('timing') if isinstance(data.get('timing'), dict) else {}
    core_assumptions = data.get('core_assumptions')
    if not isinstance(core_assumptions, list):
        core_assumptions = []

    def core_values(key):
        return [assumption.get(key) for assumption in core_assumptions
                if isinstance(assumption, dict)]

    return {
        'well_separation_status': data.get('status', ''),
        'well_separation_complete': data.get('complete', ''),
        'violated_assumption_type': data.get('violated_assumption_type', ''),
        'well_separation_cases': compact_json(data.get('cases')),
        'well_separation_responsible_assumption_count': (
            len(data.get('responsible_assumptions', []))
            if isinstance(data.get('responsible_assumptions'), list) else ''
        ),
        'well_separation_warnings': compact_json(data.get('warnings')),
        'slugs_reported_elapsed_time_s': data.get('elapsed_time', ''),
        'slugs_timing_total_s': timing.get('total', ''),
        'core_minimization_s': timing.get('core_minimization', ''),
        'core_enabled': data.get('core_enabled', ''),
        'core_complete': data.get('core_complete', ''),
        'core_candidate_count': data.get('core_candidate_count', ''),
        'core_solver_calls': data.get('core_solver_calls', ''),
        'core_size': len(core_assumptions),
        'core_kinds': stable_join(core_values('kind')),
        'core_indices': stable_join(core_values('index')),
        'core_source_indices': stable_join(core_values('source_index')),
        'core_lines': stable_join(core_values('line')),
        'core_assumptions': compact_json(core_assumptions),
        'well_separation_json_file': data.get('artifact_path', ''),
        'well_separation_output_file': data.get('output_path', ''),
    }


def _extracted_sm_size(automaton, realizable):
    """Return an extracted automaton's state count, or None if none exists.

    `automaton` may be a dict shell (e.g. `{}` or `{'automaton': []}`) even
    when no strategy exists at all: the synthesizer process returns this same
    shape on an unrealizable/fatal outcome, so `isinstance(automaton, dict)`
    alone can't distinguish "no strategy" from "a real, possibly-small
    strategy." Require the already-authoritative `realizable` flag too.
    """
    if not realizable or not isinstance(automaton, dict):
        return None
    return len(automaton.get('automaton', []))


def compile_and_synthesize(row, trial_dir, state_mappings, system_capabilities, args):
    """Run one request through the same process chain as the Slugs manager pipeline."""
    stage_times = empty_stage_times()
    original_audit = empty_audit()
    reduced_audit = empty_audit()
    state_defn = []
    count_specs = {}
    degraded_code = None

    spec = build_spec(row, state_mappings, system_capabilities, stage_times)
    compiler_ec = _time_process(
        'compiler_time_s',
        stage_times,
        lambda: compiler_main([
            spec,
            str(trial_dir),
            row.ordering_mode,
            row.ordering_seed,
            row.reordering_enabled,
        ]).process()[0],
    )
    if _fatal_code(compiler_ec) is not None:
        return (
            {},
            None,
            compiler_ec.value,
            original_audit,
            reduced_audit,
            empty_well_separation(),
            stage_times,
            state_defn,
            count_specs,
        )

    well_separation = _time_process(
        'well_separation_wrapper_wall_time_s',
        stage_times,
        lambda: run_well_separation(trial_dir, row, args),
    )
    stage_times['well_separation_analyzer_time_s'] = well_separation_process_time(
        well_separation,
    )
    if _fatal_code(well_separation['error_code']) is not None:
        return (
            {},
            None,
            well_separation['error_code'],
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    automaton, synth_ec = _time_process(
        'synthesizer_time_s',
        stage_times,
        lambda: synthesizer_main([
            str(trial_dir),
            state_mappings,
            args.synthesis_timeout_s,
            row.reordering_enabled,
            args.slugs_bin,
            row.spec_name,
            row.reordering_threshold,
        ]).process(),
    )
    if _fatal_code(synth_ec) is not None:
        return (
            automaton,
            None,
            synth_ec.value,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    original_audit = _time_process(
        'original_auditor_time_s',
        stage_times,
        lambda: run_audit(
            automaton, spec, row, trial_dir, state_mappings, system_capabilities,
            args.auditor_timeout_s,
        ),
    )
    degraded_code = _record_degraded(degraded_code, original_audit.get('error_code'))
    fatal = _fatal_code(original_audit.get('error_code'))
    if fatal is not None:
        return (
            automaton,
            None,
            fatal,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    mealy_ec = _time_process(
        'mealy_graph_time_s',
        stage_times,
        lambda: mealy_graph_main([
            automaton,
            str(trial_dir),
            row.spec_name,
            getattr(args, 'mealy_graph_config', {}),
        ]).process()[0],
    )
    if _fatal_code(mealy_ec) is not None:
        return (
            automaton,
            None,
            mealy_ec.value,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    reduced_automaton, reducer_ec = _time_process(
        'reduction_time_s',
        stage_times,
        lambda: reducer_main([automaton]).process(),
    )
    if _fatal_code(reducer_ec) is not None:
        return (
            automaton,
            None,
            reducer_ec.value,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    reduced_audit = _time_process(
        'auditor_time_s',
        stage_times,
        lambda: run_audit(
            reduced_automaton, spec, row, trial_dir, state_mappings, system_capabilities,
            args.auditor_timeout_s,
        ),
    )
    degraded_code = _record_degraded(degraded_code, reduced_audit.get('error_code'))
    fatal = _fatal_code(reduced_audit.get('error_code'))
    if fatal is not None:
        return (
            automaton,
            reduced_automaton,
            fatal,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    reduced_mealy_ec = _time_process(
        'reduced_mealy_graph_time_s',
        stage_times,
        lambda: mealy_graph_main([
            reduced_automaton,
            str(trial_dir),
            getattr(args, 'reduced_automaton_name', 'reduced_automaton'),
            getattr(args, 'mealy_graph_config', {}),
        ]).process()[0],
    )
    if _fatal_code(reduced_mealy_ec) is not None:
        return (
            automaton,
            reduced_automaton,
            reduced_mealy_ec.value,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    state_defn, sm_generator_ec = _time_process(
        'sm_generation_time_s',
        stage_times,
        lambda: sm_generator_main([reduced_automaton, row.system_name]).process(),
    )
    if _fatal_code(sm_generator_ec) is not None:
        return (
            automaton,
            reduced_automaton,
            sm_generator_ec.value,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    state_defn, sm_layout_ec = _time_process(
        'sm_layout_time_s',
        stage_times,
        lambda: sm_layout_main([
            state_defn,
            str(trial_dir),
            getattr(args, 'use_fallback_layout', False),
        ]).process(),
    )
    if _fatal_code(sm_layout_ec) is not None:
        return (
            automaton,
            reduced_automaton,
            sm_layout_ec.value,
            original_audit,
            reduced_audit,
            well_separation,
            stage_times,
            state_defn,
            count_specs,
        )

    (count_specs,) = _time_process(
        'count_specs_time_s',
        stage_times,
        lambda: count_specs_main([str(trial_dir), row.spec_name]).process(),
    )

    return (
        automaton,
        reduced_automaton,
        degraded_code or SynthesisErrorCode.SUCCESS,
        original_audit,
        reduced_audit,
        well_separation,
        stage_times,
        state_defn,
        count_specs,
    )


def read_variable_order(path: Path) -> dict[str, Any]:
    """Read variable-order sidecar when present."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def count_init_clauses(structuredslugs_path: Path) -> dict[str, int | None]:
    """Count [ENV_INIT] / [SYS_INIT] clauses in a compiled .structuredslugs file.

    Slugs reports TRANS/LIVENESS counts in its stats output but not INIT, so the
    init-formula counts (paper's |phi_i^a| / |phi_i^g|) are taken here from the
    compiled spec — the same representation Slugs read the other counts from.
    Counts non-empty, non-comment lines per section; a present-but-empty section
    yields 0, an absent section yields None.
    """
    section_field = {'[ENV_INIT]': 'env_init_count', '[SYS_INIT]': 'sys_init_count'}
    tally = {'env_init_count': 0, 'sys_init_count': 0}
    seen: set[str] = set()
    try:
        text = structuredslugs_path.read_text(encoding='utf-8')
    except OSError:
        return {'env_init_count': None, 'sys_init_count': None}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            current = section_field.get(stripped)
            if current:
                seen.add(current)
            continue
        if current and stripped and not stripped.startswith('#'):
            tally[current] += 1
    return {field: (tally[field] if field in seen else None) for field in tally}


def metrics_from_output(path: Path) -> dict[str, Any]:
    """Parse Slugs output metrics into plain dict."""
    if not path.exists():
        return {}
    try:
        metrics = parse_slugs_log(path)
        return metrics.__dict__
    except (OSError, ValueError, TypeError) as exc:
        return {'failure': f'Could not parse Slugs output: {exc}'}


def _run_with_output_log(log_path: Path, verbose_console: bool, callback):
    """Run callback while sending process chatter to a log unless verbose."""
    if verbose_console:
        return callback()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as log_file:
        log_file.write(f'\n[{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]\n')
        with contextlib.redirect_stdout(log_file), contextlib.redirect_stderr(log_file):
            return callback()


def run_trial(row, run_index, out_dir, state_mappings, system_capabilities, args):
    """Run one matrix trial and return the raw CSV row."""
    trial_dir = out_dir / 'runs' / row.row_id / f'trial_{run_index:02d}'
    trial_dir.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    failure = ''
    automaton = {}
    reduced_automaton = None
    error_code = None
    original_audit = empty_audit()
    audit = empty_audit()
    well_separation = empty_well_separation()
    stage_times = empty_stage_times()
    state_defn = []
    try:
        (
            automaton,
            reduced_automaton,
            error_code,
            original_audit,
            audit,
            well_separation,
            stage_times,
            state_defn,
            _count_specs,
        ) = _run_with_output_log(
            trial_dir / 'harness.log',
            args.verbose_console,
            lambda: compile_and_synthesize(
                row,
                trial_dir,
                state_mappings,
                system_capabilities,
                args,
            ),
        )
    except Exception as exc:
        failure = str(exc)
        error_code = SynthesisErrorCode.SYNTHESIS_FAILED
    elapsed = time.monotonic() - start

    byproducts = trial_dir / 'synthesis_byproducts'
    slugs_output_file = byproducts / f'{row.spec_name}.output'
    slugs_json_file = byproducts / f'{row.spec_name}.json'
    variable_order_file = byproducts / f'{row.spec_name}.variable_order.json'
    structuredslugs_file = byproducts / f'{row.spec_name}.structuredslugs'
    metrics = metrics_from_output(slugs_output_file)
    order_data = read_variable_order(variable_order_file)
    init_counts = count_init_clauses(structuredslugs_file)
    well_separation_fields = flatten_well_separation(well_separation)
    stage_timing_json_file = trial_dir / 'stage_timings.json'
    write_stage_timing_json(stage_timing_json_file, stage_times)
    non_slugs_summary = non_slugs_timing_summary(stage_times)
    generate_specs_time_s = stage_time_sum(stage_times, GENERATE_SPECS_STAGE_TIME_FIELDS)
    realize_hfsm_time_s = stage_time_sum(stage_times, REALIZE_HFSM_STAGE_TIME_FIELDS)
    flexbe_hfsm_realized = 'Yes' if isinstance(state_defn, list) and state_defn else 'No'

    row_data = {
        'example': row.example,
        'system_name': row.system_name,
        'spec_name': row.spec_name,
        'capability_file': str(row.capabilities_path),
        'encoding': row.encoding,
        'liveness': row.liveness,
        'pending': row.pending,
        'column_indicator': row.column_indicator,
        'ordering_mode': row.ordering_mode,
        'ordering_seed': row.ordering_seed,
        'reordering_enabled': row.reordering_enabled,
        'reordering_threshold': row.reordering_threshold,
        'reordering_policy': row.reordering_policy,
        'run_index': run_index,
        'row_id': row.row_id,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'hostname': platform.node(),
        'git_sha_flexbe_synthesis': git_sha(Path(__file__).resolve().parents[3]),
        'git_sha_slugs': git_sha(Path(args.slugs_bin).expanduser().resolve().parent),
        'return_code': 0 if error_code == SynthesisErrorCode.SUCCESS else 1,
        'error_code': error_code,
        'realizable': metrics.get('realizable'),
        'ap_i': metrics.get('ap_i'),
        'ap_o': metrics.get('ap_o'),
        'env_init_count': (
            init_counts['env_init_count'] if init_counts['env_init_count'] is not None
            else metrics.get('env_init_count') or len(metrics.get('env_init', []))
        ),
        'sys_init_count': (
            init_counts['sys_init_count'] if init_counts['sys_init_count'] is not None
            else metrics.get('sys_init_count') or len(metrics.get('sys_init', []))
        ),
        'env_trans_count': metrics.get('env_trans_count'),
        'sys_trans_count': metrics.get('sys_trans_count'),
        'env_liveness_count': metrics.get('env_liveness_count'),
        'sys_liveness_count': metrics.get('sys_liveness_count'),
        'realizability_time_s': metrics.get('synthesis_time_s'),
        'extraction_time_s': metrics.get('explicit_extraction_time_s'),
        'auditor_time_s': audit['auditor_time_s'],
        'generate_specs_time_s': generate_specs_time_s,
        'realize_hfsm_time_s': realize_hfsm_time_s,
        'overall_pipeline_time_s': elapsed,
        'cudd_peak_nodes': metrics.get('cudd_peak_nodes'),
        'cudd_live_nodes': metrics.get('cudd_live_nodes'),
        'cudd_var_count': metrics.get('cudd_var_count'),
        'cudd_reordering_enabled': metrics.get('cudd_reordering_enabled'),
        'cudd_next_reordering': metrics.get('cudd_next_reordering'),
        'cudd_reorderings': metrics.get('cudd_reorderings'),
        'cudd_reordering_time_s': metrics.get('cudd_reordering_time_s'),
        'slugs_sm_size': _extracted_sm_size(automaton, metrics.get('realizable')),
        # reduced_automaton correctly defaults to None (not {}), so it doesn't
        # need the same realizable gate slugs_sm_size does above -- but using
        # the same helper keeps both fields' semantics identical and equally
        # covered by test_extracted_sm_size_requires_realizable below.
        'reduced_sm_size': _extracted_sm_size(reduced_automaton, True),
        'audit_valid': audit['audit_valid'],
        'audit_incomplete': audit['audit_incomplete'],
        'audit_failure_kind': audit['audit_failure_kind'],
        'state_defn_size': len(state_defn) if isinstance(state_defn, list) else None,
        'flexbe_hfsm_realized': flexbe_hfsm_realized,
        'requested_input_order': json.dumps(order_data.get('requested_input_order', [])),
        'requested_output_order': json.dumps(order_data.get('requested_output_order', [])),
        'final_variable_order': json.dumps(order_data.get('final_variable_order', [])),
        'trial_dir': str(trial_dir),
        'slugs_output_file': str(slugs_output_file),
        'slugs_json_file': str(slugs_json_file),
        'variable_order_file': str(variable_order_file),
        'stage_timing_json_file': str(stage_timing_json_file),
        'failure': failure or metrics.get('failure', ''),
    }
    row_data.update(prefix_audit(original_audit, 'original'))
    row_data.update(stage_times)
    row_data.update(non_slugs_summary)
    row_data.update(well_separation_fields)
    return row_data


def write_rows(csv_path: Path, rows: list[dict[str, Any]]):
    """Append rows to master CSV."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.exists()
    with csv_path.open('a', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES, extrasaction='ignore')
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _float_value(value):
    """Return a float for a CSV cell, or None when missing/non-numeric."""
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derive_summary_fields(row: dict[str, Any]) -> None:
    """Populate derived reporting fields for older or partial master rows."""
    if row.get('well_separation_analyzer_time_s', '') in (None, ''):
        row['well_separation_analyzer_time_s'] = (
            row.get('slugs_timing_total_s')
            or row.get('slugs_reported_elapsed_time_s')
            or ''
        )
    if row.get('generate_specs_time_s', '') in (None, ''):
        row['generate_specs_time_s'] = stage_time_sum(
            row,
            GENERATE_SPECS_STAGE_TIME_FIELDS,
        )
    if row.get('realize_hfsm_time_s', '') in (None, ''):
        row['realize_hfsm_time_s'] = stage_time_sum(
            row,
            REALIZE_HFSM_STAGE_TIME_FIELDS,
        )
    if row.get('flexbe_hfsm_realized', '') in (None, ''):
        state_defn_size = _float_value(row.get('state_defn_size'))
        row['flexbe_hfsm_realized'] = (
            'Yes' if state_defn_size is not None and state_defn_size > 0 else 'No'
        )


def write_summary(master_path: Path, summary_path: Path):
    """Write grouped summary statistics from the raw master CSV."""
    if not master_path.exists():
        return

    with master_path.open(newline='', encoding='utf-8') as master_file:
        rows = list(csv.DictReader(master_file))
    if not rows:
        return

    groups = {}
    for row in rows:
        _derive_summary_fields(row)
        row['reordering_policy'] = reordering_policy(row)
        key = tuple(row.get(field, '') for field in SUMMARY_KEYS)
        groups.setdefault(key, []).append(row)

    fieldnames = list(SUMMARY_KEYS) + [
        'n',
        'failures',
        'realizable',
        *SUMMARY_TEXT_FIELDS,
    ]
    for field in SUMMARY_NUMERIC_FIELDS:
        fieldnames.extend([
            f'{field}_mean',
            f'{field}_min',
            f'{field}_max',
            f'{field}_stdev',
        ])

    with summary_path.open('w', newline='', encoding='utf-8') as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()
        for key, group_rows in sorted(groups.items()):
            output = dict(zip(SUMMARY_KEYS, key))
            output['n'] = len(group_rows)
            output['failures'] = sum(
                1 for row in group_rows
                if row.get('failure') or row.get('return_code') not in ('0', 0)
            )
            output['realizable'] = realizable_summary(group_rows)
            for field in SUMMARY_TEXT_FIELDS:
                output[field] = text_summary(group_rows, field)
            for field in SUMMARY_NUMERIC_FIELDS:
                values = [
                    value for value in (_float_value(row.get(field)) for row in group_rows)
                    if value is not None
                ]
                output[f'{field}_mean'] = (
                    statistics.mean(values) if values else ''
                )
                output[f'{field}_min'] = min(values) if values else ''
                output[f'{field}_max'] = max(values) if values else ''
                output[f'{field}_stdev'] = (
                    statistics.stdev(values) if len(values) > 1 else 0 if values else ''
                )
            writer.writerow(output)


def validate_output_paths(out_dir: Path, append: bool):
    """Fail early before mixing old and new matrix data by accident."""
    master_path = out_dir / 'master.csv'
    if master_path.exists() and not append:
        raise FileExistsError(
            f"Refusing to append to existing '{master_path}'. "
            'Use a fresh --out-dir, remove the old run directory, or pass '
            '--append to continue writing into the existing master.csv.'
        )


def is_long_example(row: MatrixRow) -> bool:
    """Return true for matrix rows covered by the coarse --skip-long filter."""
    searchable = ' '.join([
        row.example,
        row.system_name,
        row.spec_name,
        str(row.capabilities_path),
    ]).lower()
    return any(marker in searchable for marker in ('pyrobosim', 'drone', 'drones'))


def filter_matrix_rows(matrix_rows: list[MatrixRow], skip_long: bool) -> list[MatrixRow]:
    """Apply run-level matrix filters."""
    if not skip_long:
        return matrix_rows
    return [row for row in matrix_rows if not is_long_example(row)]


def progress_groups(matrix_rows: list[MatrixRow]) -> dict[int, tuple[int, int, str]]:
    """Return row-indexed progress group ranges for contiguous combo groups."""
    groups = {}
    if not matrix_rows:
        return groups

    test_cursor = 1
    row_index = 0
    while row_index < len(matrix_rows):
        row = matrix_rows[row_index]
        group_key = row.progress_key
        group_start_row = row_index
        group_count = 0
        while (
            row_index < len(matrix_rows)
            and matrix_rows[row_index].progress_key == group_key
        ):
            group_count += matrix_rows[row_index].n_trials
            row_index += 1
        groups[group_start_row] = (
            test_cursor,
            test_cursor + group_count - 1,
            row.progress_title,
        )
        test_cursor += group_count
    return groups


def run_matrix(args):
    """Run all rows from a matrix YAML."""
    matrix_rows = load_matrix(Path(args.matrix).expanduser())
    original_count = len(matrix_rows)
    matrix_rows = filter_matrix_rows(matrix_rows, getattr(args, 'skip_long', False))
    out_dir = Path(args.out_dir).expanduser()
    validate_output_paths(out_dir, args.append)
    state_mappings_path = resolve_state_mappings_path(args.state_mappings)
    state_mappings = load_yaml(state_mappings_path)
    synthesis_home = args.synthesis_home or os.getenv(fpths._SYNTHESIS_HOME_ENV)
    system_cache = {}

    master_path = out_dir / 'master.csv'
    summary_path = out_dir / 'summary.csv'
    run_log_path = out_dir / 'harness.log'
    written = 0
    total_tests = sum(row.n_trials for row in matrix_rows)
    if getattr(args, 'skip_long', False):
        skipped = original_count - len(matrix_rows)
        print(
            (
                f'--skip-long omitted {skipped} pyrobosim/drone row(s) '
                'before generating any trial data.'
            ),
            flush=True,
        )
    grouped_progress = progress_groups(matrix_rows)
    for row_index, row in enumerate(matrix_rows):
        if row_index in grouped_progress:
            start_test, end_test, title = grouped_progress[row_index]
            if start_test == end_test:
                range_text = f'Test {start_test}'
            else:
                range_text = f'Tests {start_test}-{end_test}'
            print(f'{range_text} of {total_tests}: {title}', flush=True)

        cache_key = (row.system_name, str(row.capabilities_path.resolve()))
        if cache_key not in system_cache:
            print(f'Preparing capabilities: {row.capabilities_path}', flush=True)
            system_cache[cache_key] = _run_with_output_log(
                run_log_path,
                args.verbose_console,
                lambda: prepare_system_capabilities(
                    row,
                    state_mappings,
                    synthesis_home=synthesis_home,
                ),
            )
        system_capabilities = system_cache[cache_key]
        trial_rows = []
        for run_index in range(row.n_trials):
            trial_rows.append(
                run_trial(
                    row,
                    run_index,
                    out_dir,
                    state_mappings,
                    system_capabilities,
                    args,
                )
            )
        write_rows(master_path, trial_rows)
        written += len(trial_rows)
    write_summary(master_path, summary_path)
    print(f"Wrote {written} raw row(s) to '{master_path}'", flush=True)
    print(f"Wrote grouped summary to '{summary_path}'", flush=True)
    if not args.verbose_console:
        print(f"Wrote harness log to '{run_log_path}'", flush=True)


def main():
    """Run the batch harness CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', required=True, help='YAML matrix file to run.')
    parser.add_argument('--out-dir', required=True, help='Output directory.')
    parser.add_argument('--slugs-bin', default='slugs', help='Path to Slugs binary.')
    parser.add_argument(
        '--state-mappings',
        default=str(default_state_mappings_path()),
        help='State mappings YAML path.',
    )
    parser.add_argument(
        '--synthesis-timeout-s',
        type=float,
        default=60.0,
        help='Per-trial Slugs timeout.',
    )
    parser.add_argument(
        '--auditor-timeout-s',
        type=float,
        default=60.0,
        help='Per-trial strategy-auditor timeout.',
    )
    parser.add_argument(
        '--well-separation-timeout-s',
        type=float,
        default=1800.0,
        help='Per-trial Slugs well-separation timeout.',
    )
    parser.add_argument(
        '--skip-well-separation',
        action='store_true',
        help='Skip built-in well-separation analysis and leave its CSV fields blank.',
    )
    parser.add_argument(
        '--minimize-well-separation-core',
        action='store_true',
        help='Ask Slugs to minimize the non-well-separated assumption core.',
    )
    parser.add_argument(
        '--fail-on-non-well-separated',
        action='store_true',
        help='Stop a trial when well-separation reports NON_WELL_SEPARATED.',
    )
    parser.add_argument(
        '--fail-on-incomplete-well-separation',
        action='store_true',
        help='Stop a trial when well-separation analysis times out or errors.',
    )
    parser.add_argument(
        '--reduced-automaton-name',
        default='reduced_automaton',
        help='Filename stem for the reduced Mealy graph artifact.',
    )
    parser.add_argument(
        '--use-fallback-layout',
        action='store_true',
        help='Use the rank-based SM layout fallback instead of Graphviz layout.',
    )
    parser.add_argument(
        '--skip-long',
        action='store_true',
        help='Skip pyrobosim and drone rows before generating trial data.',
    )
    parser.add_argument(
        '--synthesis-home',
        default='',
        help='Optional FLEXBE_SYNTHESIS_HOME override.',
    )
    parser.add_argument(
        '--verbose-console',
        action='store_true',
        help='Print process/preprocess output to terminal instead of harness logs.',
    )
    parser.add_argument(
        '--append',
        action='store_true',
        help='Append to an existing master.csv instead of requiring a fresh out-dir.',
    )
    run_matrix(parser.parse_args())


if __name__ == '__main__':
    main()
