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

"""Lightweight tests for Slugs processes that do not require the Slugs binary."""

import csv
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode
from flexbe_synthesis_slugs.helpers import (
    batch_run_harness,
    experiment_postprocess,
    slugs_binary,
    slugs_synthesizer_helper,
    sm_generation_helpers,
)
from flexbe_synthesis_slugs.helpers.gr1_formula import (
    get_vars_from_eqn,
    replace_var_in_eqn,
)
from flexbe_synthesis_slugs.helpers.gr1_specification import GR1Specification
from flexbe_synthesis_slugs.helpers.slugs_automaton import (
    SlugsAutomaton,
    SlugsAutomatonState,
)
from flexbe_synthesis_slugs.helpers.slugs_synthesizer_helper import SlugsSynthesizerHelper
from flexbe_synthesis_slugs.helpers.sm_gen.sm_gen_config import SMGenConfig
from flexbe_synthesis_slugs.helpers.strategy_auditor import (
    PROTOCOL_VIOLATION,
    StrategyAuditor,
)
from flexbe_synthesis_slugs.helpers.structured_slugs_parser import compiler as slugs_compiler
from flexbe_synthesis_slugs.processes import (
    slugs_mealy_graph,
    slugs_sm_generator,
    slugs_synthesizer,
    slugs_well_separation_analyzer,
)
from flexbe_synthesis_slugs.processes.slugs_activation_specification_parsed import (
    main as activation_spec_parsed_main,
    SlugsActivationSpecificationParsed,
)
from flexbe_synthesis_slugs.processes.slugs_automaton_loader import (
    main as automaton_loader_main,
)
from flexbe_synthesis_slugs.processes.slugs_capability_specification import (
    ONEHOT_MUTEX_MARKER,
)
from flexbe_synthesis_slugs.processes.slugs_count_specs import main as count_specs_main
from flexbe_synthesis_slugs.processes.slugs_request_specification import (
    main as request_spec_main,
)
from flexbe_synthesis_slugs.processes.slugs_sm_reducer import (
    _run_standalone_smoke,
    main as sm_reducer_main,
    SlugsSMReducer,
)
from flexbe_synthesis_slugs.processes.slugs_spec_compiler import (
    main as spec_compiler_main,
    SlugsSpecCompiler,
)
from flexbe_synthesis_slugs.processes.slugs_spec_loader import main as spec_loader_main
from flexbe_synthesis_slugs.processes.slugs_transition_system_specification import (
    main as transition_spec_main,
)
import pytest
import yaml


class _FakeSlugsProcess:
    """Small `Popen` stand-in for Slugs subprocess tests."""

    instances = []

    def __init__(self, args, stdout_text, returncode, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.stdout_text = stdout_text
        self.returncode = returncode
        self.terminated = False
        self.instances.append(self)

    def communicate(self, timeout=None):
        del timeout
        return self.stdout_text, None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15


class _BlockingSlugsProcess:
    """Blocking `Popen` stand-in that exits only after termination."""

    instances = []

    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.returncode = None
        self.started = threading.Event()
        self.released = threading.Event()
        self.terminated = False
        self.instances.append(self)

    def communicate(self, timeout=None):
        self.started.set()
        if not self.released.wait(timeout):
            raise subprocess.TimeoutExpired(self.args, timeout)
        return '', None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self.released.set()


class _FinishedAtDeadlineProcess:
    """Finished `Popen` stand-in that mimics a zero-timeout race."""

    def __init__(self):
        self.args = ['/usr/bin/slugs']
        self.returncode = 0
        self.terminated = False
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if timeout == 0.0:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return 'RESULT: Specification is realizable.', None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15


def _patch_fake_slugs_process(monkeypatch, stdout_text, returncode):
    """Patch Slugs helper `Popen` with a deterministic fake process."""
    _FakeSlugsProcess.instances = []

    def _popen(args, **kwargs):
        return _FakeSlugsProcess(args, stdout_text, returncode, **kwargs)

    monkeypatch.setattr(slugs_synthesizer_helper.subprocess, 'Popen', _popen)


def _patch_fake_well_separation_process(monkeypatch, result_payload, returncode=0):
    """Patch well-separation `Popen` and write the requested JSON artifact."""
    _FakeSlugsProcess.instances = []

    def _popen(args, **kwargs):
        if result_payload is not None:
            output_path = os.path.join(kwargs['cwd'], args[-1])
            with open(output_path, 'w', encoding='utf-8') as output_file:
                json.dump(result_payload, output_file)
        return _FakeSlugsProcess(args, 'well separation done', returncode, **kwargs)

    monkeypatch.setattr(slugs_well_separation_analyzer.subprocess, 'Popen', _popen)


def test_slugs_spec_loader_loads_yaml_spec(tmp_path):
    """Spec loader should merge a YAML GR(1) spec without invoking Slugs."""
    spec_path = tmp_path / 'demo_spec.yaml'
    spec_path.write_text(
        """\
spec_name: demo_spec
specs:
  INPUT:
    - request
  OUTPUT:
    - done
  ENV_INIT:
    - "!request"
  SYS_INIT:
    - "!done"
  SYS_LIVENESS:
    - done
""",
        encoding='utf-8',
    )

    (specification,) = spec_loader_main(
        ['demo_spec', 'demo_system', str(spec_path)]
    ).process()

    assert specification['spec_name'] == 'demo_spec'
    assert 'request' in specification['env_props']
    assert 'done' in specification['sys_props']
    assert specification['sys_liveness'] == ['done']


def test_slugs_spec_loader_accepts_null_specs_field(tmp_path):
    """A spec file with specs: null should load without error, merging nothing."""
    spec_path = tmp_path / 'caps_spec.yaml'
    spec_path.write_text(
        'spec_name: caps_spec\nspecs:\n',
        encoding='utf-8',
    )

    (specification,) = spec_loader_main(
        ['caps_spec', 'demo_system', str(spec_path)]
    ).process()

    assert specification['spec_name'] == 'caps_spec'
    assert specification['env_props'] == set()
    assert specification['sys_props'] == set()


def test_gr1_specification_to_dict_omits_private_derived_props():
    """GR(1) pipeline payloads should not leak private composite-prop caches."""
    spec = GR1Specification('demo', env_props={'request:high'}, sys_props={'done'})
    spec.custom_note = 'kept'

    payload = spec.to_dict()

    assert payload['spec_name'] == 'demo'
    assert payload['env_props'] == {'request:high'}
    assert payload['sys_props'] == {'done'}
    assert payload['custom_note'] == 'kept'
    assert 'verbose' not in payload
    assert '_GR1Specification__env_composite_props' not in payload
    assert '_GR1Specification__sys_composite_props' not in payload


def test_gr1_specification_merge_ignores_legacy_private_cache_keys(capsys):
    """Older saved spec payloads may include private caches; merging should skip them."""
    spec = GR1Specification('demo')

    spec.merge_gr1_specification(
        {
            'env_props': ['request'],
            '_GR1Specification__env_composite_props': {'stale'},
            '_GR1Specification__sys_composite_props': {'stale'},
        }
    )

    assert 'request' in spec.env_props
    assert 'Unknown GR1 specification key' not in capsys.readouterr().out


def test_gr1_specification_merge_keeps_unknown_keys_as_custom_data():
    """Unknown public keys should round-trip without becoming instance attributes."""
    spec = GR1Specification('demo')

    spec.merge_gr1_specification({'custom_note': 'kept'})

    assert not hasattr(spec, 'custom_note')
    assert spec.to_dict()['custom_note'] == 'kept'


def test_gr1_specification_custom_data_is_quiet_by_default(capsys):
    """Custom metadata round-trips should not warn during normal pipeline passes."""
    spec = GR1Specification('demo')

    spec.merge_gr1_specification({'custom_note': 'kept'})

    assert spec.to_dict()['custom_note'] == 'kept'
    assert capsys.readouterr().out == ''


def test_gr1_specification_to_dict_prefers_custom_data_over_direct_attribute():
    """Merged custom metadata should win over ad hoc direct attributes."""
    spec = GR1Specification('demo')

    spec.merge_gr1_specification({'custom_note': 'from_merge'})
    spec.custom_note = 'from_attribute'

    assert spec.to_dict()['custom_note'] == 'from_merge'


def test_gr1_specification_merge_rejects_reserved_unknown_keys():
    """Unknown keys must not clobber runtime fields or class methods."""
    spec = GR1Specification('demo')

    with pytest.raises(ValueError, match='reserved GR1Specification name'):
        spec.merge_gr1_specification({'summary': 'not callable anymore'})
    with pytest.raises(ValueError, match='reserved GR1Specification name'):
        spec.merge_gr1_specification({'verbose': True})

    assert callable(spec.summary)
    assert spec.verbose is False


def test_slugs_spec_loader_returns_schema_payload_without_private_keys(tmp_path):
    """Spec loader output should use the public GR(1) schema, not raw __dict__."""
    spec_path = tmp_path / 'demo_spec.yaml'
    spec_path.write_text(
        """\
spec_name: demo_spec
specs:
  INPUT:
    - request
  OUTPUT:
    - done
""",
        encoding='utf-8',
    )

    (specification,) = spec_loader_main(
        ['demo_spec', 'demo_system', str(spec_path)]
    ).process()

    assert '_GR1Specification__env_composite_props' not in specification
    assert '_GR1Specification__sys_composite_props' not in specification


def test_slugs_count_specs_counts_structuredslugs_sections(tmp_path):
    """Count process should summarize generated structuredslugs artifacts."""
    spec_dir = tmp_path / 'demo_spec'
    byproducts_dir = spec_dir / 'synthesis_byproducts'
    byproducts_dir.mkdir(parents=True)
    structured_path = byproducts_dir / 'demo_spec.structuredslugs'
    structured_path.write_text(
        """\
[INPUT]
request

[OUTPUT]
done

[SYS_INIT]
!done

[SYS_LIVENESS]
done
""",
        encoding='utf-8',
    )

    (counts,) = count_specs_main([str(spec_dir)]).process()

    assert counts == {
        'structuredslugs': {
            'INPUT': 1,
            'OUTPUT': 1,
            'SYS_INIT': 1,
            'SYS_LIVENESS': 1,
        },
    }
    counts_path = byproducts_dir / 'demo_spec.counts'
    with counts_path.open(encoding='utf-8') as counts_file:
        assert yaml.safe_load(counts_file) == counts


def test_slugs_count_specs_accepts_explicit_spec_name(tmp_path):
    """Batch trial dirs are named trial_NN, so count_specs needs explicit spec name."""
    trial_dir = tmp_path / 'trial_00'
    byproducts_dir = trial_dir / 'synthesis_byproducts'
    byproducts_dir.mkdir(parents=True)
    structured_path = byproducts_dir / 'CoffeeSM.structuredslugs'
    structured_path.write_text(
        """\
[INPUT]
request

[OUTPUT]
done
""",
        encoding='utf-8',
    )

    (counts,) = count_specs_main([str(trial_dir), 'CoffeeSM']).process()

    assert counts['structuredslugs'] == {'INPUT': 1, 'OUTPUT': 1}
    assert (byproducts_dir / 'CoffeeSM.counts').exists()


def test_batch_harness_resolves_workspace_root_state_mappings(tmp_path, monkeypatch):
    """Resolve documented state-mapping paths from the workspace root."""
    workspace = tmp_path / 'workspace'
    mapping_path = (
        workspace
        / 'src'
        / 'flexbe_synthesis'
        / 'flexbe_synthesis_generic'
        / 'mappings'
        / 'infinite_mappings.yaml'
    )
    mapping_path.parent.mkdir(parents=True)
    mapping_path.write_text('sm_outcome_mappings: {}\n', encoding='utf-8')
    monkeypatch.chdir(workspace)

    resolved = batch_run_harness.resolve_state_mappings_path(
        Path('flexbe_synthesis_generic/mappings/infinite_mappings.yaml')
    )

    assert resolved == mapping_path


def test_batch_harness_rejects_empty_state_mappings_path():
    """Empty --state-mappings values should not resolve to cwd."""
    with pytest.raises(FileNotFoundError, match='path is empty'):
        batch_run_harness.resolve_state_mappings_path('')


def test_batch_harness_rejects_state_mappings_directory(tmp_path):
    """State mappings resolution should require a YAML file, not a directory."""
    with pytest.raises(FileNotFoundError, match='not found'):
        batch_run_harness.resolve_state_mappings_path(tmp_path)


def test_slugs_spec_compiler_does_not_change_cwd(tmp_path, monkeypatch):
    """Spec compilation should not mutate process-global cwd."""
    cwd = tmp_path / 'caller_cwd'
    cwd.mkdir()
    spec_dir = tmp_path / 'demo_spec'
    monkeypatch.chdir(cwd)
    original_cwd = os.getcwd()
    gr1_specification = {
        'spec_name': 'demo_spec',
        'env_props': {'request'},
        'sys_props': {'done'},
        'env_init': ['!request'],
        'sys_init': ['!done'],
        'sys_liveness': ['done'],
    }

    (error_code,) = spec_compiler_main([gr1_specification, str(spec_dir)]).process()

    assert os.getcwd() == original_cwd
    assert error_code.value == SynthesisErrorCode.SUCCESS
    slugsin_path = spec_dir / 'synthesis_byproducts' / 'demo_spec.slugsin'
    assert slugsin_path.exists()
    assert '[INPUT]' in slugsin_path.read_text(encoding='utf-8')


def test_slugs_spec_compiler_warns_on_mismatched_spec_name(tmp_path, capsys):
    """Mismatched spec name uses the gr1_specification name for output files."""
    spec_dir = tmp_path / 'demo_spec'
    gr1_specification = {
        'spec_name': 'other_name',
        'env_props': {'request'},
        'sys_props': {'done'},
        'sys_liveness': ['done'],
    }

    (error_code,) = spec_compiler_main([gr1_specification, str(spec_dir)]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    out = capsys.readouterr().out
    assert 'Mismatched spec name' in out
    assert 'other_name' in out
    slugsin_path = spec_dir / 'synthesis_byproducts' / 'other_name.slugsin'
    assert slugsin_path.exists()


def test_slugs_spec_compiler_accepts_primed_bool_guarding_numeric_copy(tmp_path):
    """Primed Boolean propositions should not be tokenized as numeric IDs."""
    spec_dir = tmp_path / 'demo_spec'
    gr1_specification = {
        'spec_name': 'demo_spec',
        'env_props': {'x:0...2', 'done'},
        'sys_props': {'act'},
        'env_init': ['x = 0', '!done'],
        'env_trans': ["!done' -> (x' = x)"],
        'sys_init': ['!act'],
        'sys_liveness': ['act'],
    }

    (error_code,) = spec_compiler_main([gr1_specification, str(spec_dir)]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    slugsin_path = spec_dir / 'synthesis_byproducts' / 'demo_spec.slugsin'
    assert slugsin_path.exists()


def test_structured_slugs_compiler_resets_globals_between_conversions(tmp_path):
    """A Boolean AP in one conversion must not poison a later numeric AP of the same name."""
    bool_spec = tmp_path / 'bool.structuredslugs'
    bool_spec.write_text(
        '\n'.join([
            '[INPUT]',
            'x',
            '[OUTPUT]',
            'done',
            '[SYS_LIVENESS]',
            'done',
        ]),
        encoding='utf-8',
    )
    numeric_spec = tmp_path / 'numeric.structuredslugs'
    numeric_spec.write_text(
        '\n'.join([
            '[INPUT]',
            'x:0...2',
            '[OUTPUT]',
            'done',
            '[ENV_INIT]',
            'x = 0',
            '[ENV_TRANS]',
            "done' -> (x' = x)",
            '[SYS_LIVENESS]',
            'done',
        ]),
        encoding='utf-8',
    )

    slugs_compiler.performConversion(str(bool_spec), thoroughly=True, fout=StringIO())
    out = StringIO()
    slugs_compiler.performConversion(str(numeric_spec), thoroughly=True, fout=out)

    assert '[INPUT]' in out.getvalue()


def test_slugs_spec_compiler_raises_on_conversion_oserror(tmp_path, monkeypatch):
    """An OSError from performConversion is wrapped as a compiler RuntimeError."""
    spec_dir = tmp_path / 'demo_spec'
    gr1_specification = {
        'spec_name': 'demo_spec',
        'env_props': {'request'},
        'sys_props': {'done'},
        'sys_liveness': ['done'],
    }
    monkeypatch.setattr(
        slugs_compiler,
        'performConversion',
        lambda *a, **kw: (_ for _ in ()).throw(OSError('disk full')),
    )

    with pytest.raises(RuntimeError, match="Could not compile 'demo_spec' to slugsin"):
        spec_compiler_main([gr1_specification, str(spec_dir)]).process()


def test_slugs_spec_compiler_main_binds_inputs():
    """main() factory should wire gr1_specification and specs_output_dir_path."""
    gr1_spec = {'spec_name': 'demo_spec'}
    compiler = spec_compiler_main([gr1_spec, '/some/path'])

    assert isinstance(compiler, SlugsSpecCompiler)
    assert compiler.gr1_specification == gr1_spec
    assert compiler.specs_output_dir_path == '/some/path'


def _request_specification_for_success_outcome(requested_outcomes, outcome_mappings):
    request = FlexBESynthesisRequest()
    request.goals = ['goal']
    request.sm_outcomes = requested_outcomes
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'goal'},
        'sys_props': set(outcome_mappings.values()) | {'finished', 'failed'},
    }
    system_capabilities = {'sm_outcome_mappings': outcome_mappings}

    (specification,) = request_spec_main(
        ['demo_spec', request, system_capabilities, current_spec]
    ).process()
    return specification


def _sys_trans_text(specification):
    return '\n'.join(str(formula) for formula in specification['sys_trans'])


def _transition_specification_for_sm_outcome_target(target):
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'choose_c'},
        'sys_props': {'choose_a', 'done'},
    }
    system_capabilities = {
        'capabilities': {
            'choose': {},
        },
        'sm_outcome_mappings': {
            'finished': 'done',
        },
        'transition_relations': {
            'choose': {
                'completed': [target],
            },
        },
    }

    (specification,) = transition_spec_main(
        ['demo_spec', system_capabilities, current_spec]
    ).process()
    return specification


def _transition_specification_with(extra_capability_data):
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': set(),
        'sys_props': {'choose_a'},
    }
    system_capabilities = {
        'capabilities': {
            'choose': {},
        },
        'sm_outcome_mappings': {},
    }
    system_capabilities.update(extra_capability_data)
    return transition_spec_main(['demo_spec', system_capabilities, current_spec]).process()


def test_transition_specification_maps_sm_outcome_targets_to_props():
    """Transition relations should use mapped SM outcome propositions."""
    specification = _transition_specification_for_sm_outcome_target('finished')

    sys_trans = _sys_trans_text(specification)
    assert "choose_c' -> done'" in sys_trans
    assert "choose_c' -> finished'" not in sys_trans


def test_transition_specification_maps_negated_sm_outcome_targets_to_props():
    """Negated SM outcome targets should preserve negation after mapping."""
    specification = _transition_specification_for_sm_outcome_target('!finished')

    sys_trans = _sys_trans_text(specification)
    assert "choose_c' -> !done'" in sys_trans
    assert "choose_c' -> !finished'" not in sys_trans


def test_transition_specification_rejects_composite_precondition_as_value_error():
    """Backend composite-condition guard should produce a controlled pipeline error."""
    with pytest.raises(ValueError, match='Composite precondition'):
        _transition_specification_with(
            {
                'action_preconditions': {
                    'choose': ['missing & other'],
                },
            }
        )


def test_transition_specification_rejects_invalid_at_postcondition_as_value_error():
    """Unsupported postcondition guards should use errors caught by the manager."""
    with pytest.raises(ValueError, match='not env_ or sys_prop'):
        _transition_specification_with(
            {
                'action_postconditions': {
                    'choose': {
                        'completed': ['@missing'],
                    },
                },
            }
        )


def test_transition_specification_replaces_plain_props_with_numeric_mappings(tmp_path):
    """Numeric variable mappings should not leave duplicate Boolean declarations."""
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'choose_c'},
        'sys_props': {'choose_a'},
        'env_init': ['x=0'],
        'env_trans': ["!choose_c' -> (x' = x)"],
        'sys_liveness': ['choose_a'],
    }
    system_capabilities = {
        'capabilities': {
            'choose': {},
        },
        'sm_outcome_mappings': {},
        'variable_mappings': {
            'env_props': {
                'x': {
                    0: 'zero',
                    1: 'one',
                    2: 'two',
                },
            },
        },
        'action_postconditions': {
            'choose': {
                'completed': ['@x'],
            },
        },
    }

    (specification,) = transition_spec_main(
        ['demo_spec', system_capabilities, current_spec]
    ).process()

    assert 'x:0...2' in specification['env_props']
    assert 'x' not in specification['env_props']

    (error_code,) = spec_compiler_main([specification, str(tmp_path / 'demo_spec')]).process()
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_request_specification_defaults_empty_success_outcome_to_finished():
    """Empty request outcomes should use mapped `finished` as the success target."""
    specification = _request_specification_for_success_outcome(
        [],
        {
            'failed': 'failed',
            'finished': 'done',
        },
    )

    sys_trans = _sys_trans_text(specification)
    assert "-> done'  # success!" in sys_trans
    assert "-> finished'  # success!" not in sys_trans


def test_request_specification_uses_requested_success_outcome():
    """The first non-failure request outcome should become the success target."""
    specification = _request_specification_for_success_outcome(
        ['failed', 'succeeded'],
        {
            'failed': 'failed',
            'succeeded': 'done',
            'finished': 'finished',
        },
    )

    sys_trans = _sys_trans_text(specification)
    assert "-> done'  # success!" in sys_trans
    assert "-> finished'  # success!" not in sys_trans


def test_request_specification_logs_log_finished_design_case(capsys):
    """The log-finished redirect should be explicit because it is intentional."""
    request = FlexBESynthesisRequest()
    request.goals = ['goal']
    request.sm_outcomes = []
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'goal'},
        'sys_props': {'finished', 'log_finished_a', 'log_finished_c'},
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    (specification,) = request_spec_main(
        ['demo_spec', request, system_capabilities, current_spec]
    ).process()

    output = capsys.readouterr().out
    assert "Handling 'log_finished_a' design case" in output
    sys_trans = _sys_trans_text(specification)
    assert "-> log_finished_a'  # success!" in sys_trans
    assert "-> !finished'  # finished only after log_finished_c" in sys_trans


def test_request_specification_rejects_unmapped_success_outcome():
    """Requested success outcomes must exist in the system outcome mapping."""
    with pytest.raises(ValueError, match='not one of the mapped SM outcomes'):
        _request_specification_for_success_outcome(
            ['unknown', 'failed'],
            {
                'failed': 'failed',
                'finished': 'finished',
            },
        )


def test_request_specification_rejects_structuredslugs_injection():
    """Request ICs/goals must not inject structured-slugs section markers."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = []
    request.goals = [']\n[SYS_LIVENESS]\nmalicious']
    request.sm_outcomes = ['finished']
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': set(),
        'sys_props': {'finished', 'malicious'},
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    with pytest.raises(ValueError, match='structured-slugs metacharacters'):
        request_spec_main(
            ['demo_spec', request, system_capabilities, current_spec]
        ).process()


def test_request_specification_allows_basic_primed_variables():
    """Request formula validation should allow a trailing prime decorator."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = ["ready'"]
    request.goals = []
    request.sm_outcomes = ['finished']
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'ready'},
        'sys_props': {'finished'},
        'sys_liveness': ['finished'],
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    (specification,) = request_spec_main(
        ['demo_spec', request, system_capabilities, current_spec]
    ).process()

    assert specification['env_init'][('ready',)].startswith("ready'")


def test_request_specification_allows_integer_equality_formulas():
    """Integer literals on the RHS of an equality (e.g. item=0) should be accepted."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = ['item=0']
    request.goals = ['action=3']
    request.sm_outcomes = ['finished']
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'item'},
        'sys_props': {'finished', 'action'},
        'sys_liveness': ['finished'],
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    (specification,) = request_spec_main(
        ['demo_spec', request, system_capabilities, current_spec]
    ).process()

    assert any('item=0' in str(f) for f in specification.get('env_init', {}).values())


def test_request_specification_rejects_non_basic_variable_tokens():
    """Request variables should be plain identifiers plus optional prime."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = ['next(ready)']
    request.goals = []
    request.sm_outcomes = ['finished']
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'ready'},
        'sys_props': {'finished'},
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    with pytest.raises(ValueError, match='not a basic variable'):
        request_spec_main(
            ['demo_spec', request, system_capabilities, current_spec]
        ).process()


def test_request_specification_allows_empty_goals_with_finite_outcomes():
    """Empty goals should preserve existing specs without adding request goals."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = ['ready']
    request.goals = []
    request.sm_outcomes = ['finished']
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'ready'},
        'sys_props': {'finished'},
        'sys_liveness': ['finished'],
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    (specification,) = request_spec_main(
        ['demo_spec', request, system_capabilities, current_spec]
    ).process()

    assert specification['env_init'][('ready',)].startswith('ready')
    assert '# IC from request' in specification['env_init'][('ready',)]
    assert specification['sys_liveness'] == ['finished']
    assert 'success!' not in _sys_trans_text(specification)


def test_replace_var_in_eqn_is_token_aware():
    """Variable replacement should not rewrite longer identifiers."""
    assert (
        replace_var_in_eqn("done & done_fast & next(done') # done comment", 'done', 'done_m')
        == "done_m & done_fast & next(done_m') # done comment"
    )


def test_get_vars_from_eqn_extracts_negated_composite_leaves():
    """Strict spec validation should see props inside negated mutex clauses."""
    assert get_vars_from_eqn("!(bd_a' & br_a')") == ['bd_a', 'br_a']


def test_get_vars_from_eqn_extracts_next_equality_variable():
    """Strict spec validation should treat next(value=...) as a value prop use."""
    assert get_vars_from_eqn("!(next(item=1) & select_m') -> !soda_a'") == [
        'item',
        'select_m',
        'soda_a',
    ]


def test_request_specification_memory_prop_replacement_is_token_aware():
    """Memory-prop fallback should not rewrite propositions containing the token."""
    request = FlexBESynthesisRequest()
    request.initial_conditions = ['done & done_fast']
    request.goals = []
    request.sm_outcomes = ['finished']
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'done_fast'},
        'sys_props': {'done_m', 'finished'},
        'sys_liveness': ['finished'],
    }
    system_capabilities = {
        'sm_outcome_mappings': {
            'finished': 'finished',
        },
    }

    (specification,) = request_spec_main(
        ['demo_spec', request, system_capabilities, current_spec]
    ).process()

    sys_init = '\n'.join(str(formula) for formula in specification['sys_init'].values())
    assert 'done_m & done_fast' in sys_init
    assert 'done_m_fast' not in sys_init


def test_activation_specification_parsed_uses_sorted_capability_order():
    """Parsed action indices should match capability-spec sorted activation order."""
    system_capabilities = {
        'capabilities': {
            'zeta': {},
            'alpha': {},
        },
        'transition_outcomes': ['completed', 'failure'],
    }
    current_spec = {
        'spec_name': 'demo_spec',
        'env_props': {'alpha_c', 'alpha_f', 'zeta_c', 'zeta_f'},
        'sys_props': {'alpha_a', 'zeta_a'},
        'sys_trans': [
            "alpha_a -> alpha_c'",   # outcome implication — outside the one-hot block
            "zeta_a -> zeta_c'",     # outcome implication — outside the one-hot block
            ONEHOT_MUTEX_MARKER,     # one-hot block starts here
            "alpha_a' -> !zeta_a'",  # mutex rule — inside block, dropped by rewriter
            "zeta_a' -> !alpha_a'",  # mutex rule — inside block, dropped by rewriter
        ],
    }

    (specification,) = activation_spec_parsed_main(
        ['demo_spec', system_capabilities, current_spec]
    ).process()

    assert '# 0: null (startup slot)' in specification['sys_props']
    assert '# 1: alpha' in specification['sys_props']
    assert '# 2: zeta' in specification['sys_props']
    # Outcome rules outside the block survive and verify numeric indices.
    assert "(capability=1) -> completed'" in specification['sys_trans']
    assert "(capability=2) -> completed'" in specification['sys_trans']
    # One-hot mutex rules inside the block are dropped; replaced by the non-idle rule.
    assert any("capability'!=0" in f for f in specification['sys_trans'] if isinstance(f, str))


def test_activation_specification_parsed_handles_three_transition_outcomes():
    """Three distinct transition outcomes all appear as generic props and env_init ICs."""
    system_capabilities = {
        'capabilities': {'step': {}},
        'transition_outcomes': ['completed', 'failure', 'waiting'],
    }
    current_spec = {
        'spec_name': 'demo',
        'env_props': {'step_c', 'step_f', 'step_w'},
        'sys_props': {'step_a'},
        'sys_trans': [ONEHOT_MUTEX_MARKER],
    }

    (spec,) = activation_spec_parsed_main(
        ['demo', system_capabilities, current_spec]
    ).process()

    assert 'completed' in spec['env_props']
    assert 'failure' in spec['env_props']
    assert 'waiting' in spec['env_props']
    assert not {'step_c', 'step_f', 'step_w'} & spec['env_props']
    env_init_exprs = set(spec['env_init'].values())
    assert any('!completed' in e for e in env_init_exprs)
    assert any('!failure' in e for e in env_init_exprs)
    assert any('!waiting' in e for e in env_init_exprs)


def test_rewrite_outcome_implication_rhs_handles_non_standard_outcome():
    """_rewrite_outcome_implication_rhs must handle outcomes beyond completed/failure."""
    inst = SlugsActivationSpecificationParsed(
        name='test',
        spec_name='demo',
        system_capabilities={},
        current_specification={},
    )
    expr = "waiting' -> (capability=0)"
    result = inst._rewrite_outcome_implication_rhs(expr, ['completed', 'failure', 'waiting'])
    assert "(capability'=0)" in result


def _make_activation_spec_inst(action_variable_name='capability'):
    return SlugsActivationSpecificationParsed(
        name='test',
        spec_name='demo',
        system_capabilities={},
        current_specification={},
        action_variable_name=action_variable_name,
    )


@pytest.mark.parametrize(
    ('expr', 'expected'),
    [
        # (cap=i) -> ((cap=i) & completed')  =>  (cap=i) -> completed'
        (
            "(capability=0) -> ((capability=0) & completed')",
            "(capability=0) -> completed'",
        ),
        # !(cap=i) -> !((cap=i) & completed') is tautological; drop it
        (
            "!(capability=0) -> !((capability=0) & completed')",
            None,
        ),
        # (cap=i) -> (((cap=i) & A) | ((cap=i) & B))  =>  (cap=i) -> (A | B)
        (
            "(capability=0) -> (((capability=0) & completed') | ((capability=0) & failure'))",
            "(capability=0) -> (completed' | failure')",
        ),
        # (cap=i) -> !(((cap=i) & A) & ((cap=i) & B))  =>  (cap=i) -> !(A & B)
        (
            "(capability=0) -> !(((capability=0) & completed') & ((capability=0) & failure'))",
            "(capability=0) -> !(completed' & failure')",
        ),
        # No match — expression passes through unchanged
        (
            '(capability=0) -> some_other_formula',
            '(capability=0) -> some_other_formula',
        ),
        # No implication — passes through unchanged
        (
            "!completed'",
            "!completed'",
        ),
    ],
)
def test_simplify_duplicate_capability_rhs(expr, expected):
    """Each duplicate-capability RHS simplification branch produces expected output."""
    assert _make_activation_spec_inst()._simplify_duplicate_capability_rhs(expr) == expected


def test_rewrite_outcomes_to_generic_replaces_outcome_tokens_in_formulas():
    """Per-capability outcome tokens in env_trans are rewritten to generic outcome formulas."""
    system_capabilities = {
        'capabilities': {'step': {}},
        'transition_outcomes': ['completed', 'failure'],
    }
    current_spec = {
        'spec_name': 'demo',
        'env_props': {'step_c', 'step_f'},
        'sys_props': {'step_a'},
        'env_trans': ['(step_c -> (capability=0))'],
        'sys_trans': [ONEHOT_MUTEX_MARKER],
    }

    (spec,) = activation_spec_parsed_main(['demo', system_capabilities, current_spec]).process()

    env_trans_str = ' '.join(line for line in spec['env_trans'] if isinstance(line, str))
    assert 'step_c' not in env_trans_str
    assert 'completed' in env_trans_str


def test_add_generic_outcome_uniqueness_adds_mutual_exclusion():
    """_add_generic_outcome_uniqueness inserts pairwise exclusion rules into env_trans."""
    gr1_spec = GR1Specification('demo')
    gr1_spec.env_trans = []

    _make_activation_spec_inst()._add_generic_outcome_uniqueness(
        gr1_spec, ['completed', 'failure']
    )

    assert any("!(completed' & failure')" in line for line in gr1_spec.env_trans)


def test_add_generic_outcome_uniqueness_skips_single_outcome():
    """_add_generic_outcome_uniqueness is a no-op when there is only one generic outcome."""
    gr1_spec = GR1Specification('demo')
    gr1_spec.env_trans = []

    _make_activation_spec_inst()._add_generic_outcome_uniqueness(gr1_spec, ['completed'])

    assert gr1_spec.env_trans == []


def test_find_slugs_binary_prefers_env_install_dir(tmp_path, monkeypatch):
    """Slugs lookup should honor SLUGS_INSTALL_DIR before PATH."""
    install_dir = tmp_path / 'slugs-bin'
    install_dir.mkdir()
    slugs_path = install_dir / 'slugs'
    slugs_path.write_text('#!/bin/sh\n', encoding='utf-8')
    slugs_path.chmod(0o755)

    monkeypatch.setenv('SLUGS_INSTALL_DIR', str(install_dir))
    monkeypatch.setenv('PATH', os.defpath)

    assert slugs_binary.find_slugs_binary() == str(slugs_path)


def test_find_slugs_binary_uses_default_install_dir(tmp_path, monkeypatch):
    """Slugs lookup should use the default install dir when env is absent."""
    install_dir = tmp_path / 'default-bin'
    install_dir.mkdir()
    slugs_path = install_dir / 'slugs'
    slugs_path.write_text('#!/bin/sh\n', encoding='utf-8')
    slugs_path.chmod(0o755)

    monkeypatch.delenv('SLUGS_INSTALL_DIR', raising=False)
    monkeypatch.setattr(slugs_binary, 'DEFAULT_SLUGS_INSTALL_DIR', str(install_dir))
    monkeypatch.setenv('PATH', os.defpath)

    assert slugs_binary.find_slugs_binary() == str(slugs_path)


def test_find_slugs_binary_falls_back_to_path(tmp_path, monkeypatch):
    """Slugs lookup should still support normal PATH installs."""
    path_dir = tmp_path / 'path-bin'
    path_dir.mkdir()
    slugs_path = path_dir / 'slugs'
    slugs_path.write_text('#!/bin/sh\n', encoding='utf-8')
    slugs_path.chmod(0o755)

    monkeypatch.delenv('SLUGS_INSTALL_DIR', raising=False)
    monkeypatch.setattr(
        slugs_binary,
        'DEFAULT_SLUGS_INSTALL_DIR',
        str(tmp_path / 'missing-default-bin'),
    )
    monkeypatch.setenv('PATH', str(path_dir))

    assert slugs_binary.find_slugs_binary() == str(slugs_path)


def test_slugs_synthesizer_reports_missing_binary_as_failure(tmp_path, monkeypatch):
    """Missing Slugs should be a tool failure, not an unrealizable spec."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    monkeypatch.setattr(slugs_synthesizer_helper, 'find_slugs_binary', lambda: None)

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert automaton_file == ''
    assert error_code.value == SynthesisErrorCode.SYNTHESIS_FAILED


def test_well_separation_analyzer_warns_and_continues_on_non_well_separated(
    tmp_path,
    monkeypatch,
):
    """Default policy should report non-well-separated specs without aborting."""
    byproducts = tmp_path / 'demo' / 'synthesis_byproducts'
    byproducts.mkdir(parents=True)
    (byproducts / 'demo.slugsin').write_text('[INPUT]\nrequest\n', encoding='utf-8')
    monkeypatch.setattr(
        slugs_well_separation_analyzer,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_well_separation_process(
        monkeypatch,
        {
            'format_version': '0.1',
            'status': 'NON_WELL_SEPARATED',
            'complete': True,
            'violated_assumption_type': 'env_safety',
        },
    )

    process = slugs_well_separation_analyzer.SlugsWellSeparationAnalyzer(
        name='WellSep',
        specs_output_dir_path=str(tmp_path / 'demo'),
        spec_name='demo',
    )
    result, error_code = process.process()

    assert result['status'] == 'NON_WELL_SEPARATED'
    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert any('not well separated' in message for message in process.messages)


def test_well_separation_analyzer_can_fail_on_non_well_separated(
    tmp_path,
    monkeypatch,
):
    """Fatal policy should stop the pipeline before synthesis."""
    byproducts = tmp_path / 'demo' / 'synthesis_byproducts'
    byproducts.mkdir(parents=True)
    (byproducts / 'demo.slugsin').write_text('[INPUT]\nrequest\n', encoding='utf-8')
    monkeypatch.setattr(
        slugs_well_separation_analyzer,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_well_separation_process(
        monkeypatch,
        {'status': 'NON_WELL_SEPARATED', 'complete': True},
    )

    process = slugs_well_separation_analyzer.SlugsWellSeparationAnalyzer(
        name='WellSep',
        specs_output_dir_path=str(tmp_path / 'demo'),
        spec_name='demo',
        fail_on_non_well_separated=True,
    )
    _, error_code = process.process()

    assert error_code.value == SynthesisErrorCode.SYNTHESIS_FAILED


def test_well_separation_analyzer_defaults_to_fatal_on_incomplete(
    tmp_path,
    monkeypatch,
):
    """Analyzer execution errors should fail by default under the Slugs-version contract."""
    byproducts = tmp_path / 'demo' / 'synthesis_byproducts'
    byproducts.mkdir(parents=True)
    (byproducts / 'demo.slugsin').write_text('[INPUT]\nrequest\n', encoding='utf-8')
    monkeypatch.setattr(
        slugs_well_separation_analyzer,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_well_separation_process(monkeypatch, None, returncode=2)

    process = slugs_well_separation_analyzer.SlugsWellSeparationAnalyzer(
        name='WellSep',
        specs_output_dir_path=str(tmp_path / 'demo'),
        spec_name='demo',
    )
    result, error_code = process.process()

    assert result['status'] == 'ANALYSIS_ERROR'
    assert error_code.value == SynthesisErrorCode.SYNTHESIS_FAILED


def test_well_separation_analyzer_passes_minimize_core_flag(tmp_path, monkeypatch):
    """Core reporting should be opt-in through the Slugs command flag."""
    byproducts = tmp_path / 'demo' / 'synthesis_byproducts'
    byproducts.mkdir(parents=True)
    (byproducts / 'demo.slugsin').write_text('[INPUT]\nrequest\n', encoding='utf-8')
    monkeypatch.setattr(
        slugs_well_separation_analyzer,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_well_separation_process(
        monkeypatch,
        {'status': 'WELL_SEPARATED', 'complete': True},
    )

    process = slugs_well_separation_analyzer.SlugsWellSeparationAnalyzer(
        name='WellSep',
        specs_output_dir_path=str(tmp_path / 'demo'),
        spec_name='demo',
        minimize_core=True,
    )
    result, error_code = process.process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert result['minimize_core_requested'] is True
    assert '--minimizeWellSeparationCore' in _FakeSlugsProcess.instances[0].args


def test_slugs_synthesizer_reports_nonzero_status_as_failure(tmp_path, monkeypatch):
    """Slugs command crashes should not be reported as unrealizable specs."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_slugs_process(monkeypatch, 'compiler crash', 2)

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert automaton_file == ''
    assert error_code.value == SynthesisErrorCode.SYNTHESIS_FAILED


def test_slugs_synthesizer_reports_clean_unrealizable_spec(tmp_path, monkeypatch):
    """A clean Slugs unrealizable result should keep its specific error code."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_slugs_process(
        monkeypatch,
        'RESULT: Specification is unrealizable.',
        0,
    )

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert automaton_file == ''
    assert error_code.value == SynthesisErrorCode.SPEC_UNSYNTHESIZABLE


def test_slugs_synthesizer_reports_unrecognized_output_as_failure(tmp_path, monkeypatch):
    """Status-zero Slugs output without a result marker should be a tool failure."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_slugs_process(monkeypatch, 'unexpected output', 0)

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert automaton_file == ''
    assert error_code.value == SynthesisErrorCode.SYNTHESIS_FAILED


def test_slugs_synthesizer_passes_reordering_threshold(tmp_path, monkeypatch):
    """Requested CUDD reorder threshold should be passed through to Slugs."""
    helper = SlugsSynthesizerHelper(
        str(tmp_path / 'demo'),
        ['completed', 'failure'],
        reordering_threshold=250,
    )
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_slugs_process(
        monkeypatch,
        'RESULT: Specification is realizable.',
        0,
    )

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert automaton_file == os.path.join(helper.specs_output_dir_path, 'demo.json')
    assert '--reorder-threshold' in _FakeSlugsProcess.instances[0].args
    assert '250' in _FakeSlugsProcess.instances[0].args


def test_slugs_synthesizer_preserves_zero_next_reordering(tmp_path, monkeypatch):
    """A reported CUDD next-reordering threshold of 0 should not be dropped."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_slugs_process(
        monkeypatch,
        'RESULT: Specification is realizable.\nCudd_ReadNextReordering: 0\n',
        0,
    )

    _, error_code = helper.call_slugs_synthesizer('demo')

    assert error_code.value == SynthesisErrorCode.SUCCESS
    order_path = tmp_path / 'demo' / 'synthesis_byproducts' / 'demo.variable_order.json'
    assert json.loads(order_path.read_text())['cudd_next_reordering'] == 0


def test_matrix_row_parses_quoted_boolean_values(tmp_path):
    """Quoted YAML booleans should not become truthy merely because they are strings."""
    row = batch_run_harness.MatrixRow.from_dict({
        'system_name': 'demo_system',
        'spec_name': 'DemoSpec',
        'spec_path': str(tmp_path / 'spec.yaml'),
        'capabilities_path': str(tmp_path / 'capabilities.yaml'),
        'encoding': 'one-hot',
        'liveness': 'S',
        'pending': 'False',
        'reordering_enabled': 'False',
    })

    assert row.pending is False
    assert row.reordering_enabled is False
    assert row.reordering_policy == 'off'
    assert row.audit_goals == row.goals


def test_matrix_row_allows_separate_audit_goals(tmp_path):
    """Matrix rows may separate request formulas from semantic audit outcomes."""
    row = batch_run_harness.MatrixRow.from_dict({
        'system_name': 'demo_system',
        'spec_name': 'DemoSpec',
        'spec_path': str(tmp_path / 'spec.yaml'),
        'capabilities_path': str(tmp_path / 'capabilities.yaml'),
        'encoding': 'one-hot',
        'liveness': 'S',
        'goals': ['log_finished'],
        'audit_goals': ['finished'],
    })

    assert row.goals == ('log_finished',)
    assert row.audit_goals == ('finished',)


def test_flatten_well_separation_result_reports_core_fields():
    """Well-separation JSON should become stable master.csv-style fields."""
    fields = batch_run_harness.flatten_well_separation({
        'result': {
            'status': 'NON_WELL_SEPARATED',
            'complete': True,
            'violated_assumption_type': 'env_safety',
            'cases': [{'case': 'env_safety_reachable_win'}],
            'responsible_assumptions': [{'name': 'safe'}],
            'warnings': ['auxiliary variables not separated'],
            'elapsed_time': 1.25,
            'timing': {'total': 1.25, 'core_minimization': 0.5},
            'core_enabled': True,
            'core_complete': True,
            'core_candidate_count': 4,
            'core_solver_calls': 7,
            'core_assumptions': [
                {'kind': 'ENV_TRANS', 'index': 2, 'source_index': 8, 'line': 42},
                {'kind': 'ENV_INIT', 'index': 1, 'source_index': 3, 'line': 11},
            ],
            'artifact_path': '/tmp/demo.well_separation.json',
            'output_path': '/tmp/demo.well_separation.output',
        },
        'error_code': SynthesisErrorCode.SUCCESS,
    })

    assert fields['well_separation_status'] == 'NON_WELL_SEPARATED'
    assert fields['slugs_reported_elapsed_time_s'] == 1.25
    assert fields['core_minimization_s'] == 0.5
    assert fields['core_size'] == 2
    assert fields['core_kinds'] == 'ENV_TRANS;ENV_INIT'
    assert fields['core_indices'] == '2;1'
    assert fields['core_source_indices'] == '8;3'
    assert fields['core_lines'] == '42;11'
    assert fields['well_separation_json_file'] == '/tmp/demo.well_separation.json'


def test_extracted_sm_size_requires_realizable():
    """An automaton dict alone can't tell 'no strategy' from 'a real one'.

    `compile_and_synthesize` returns a dict-shaped `automaton` (e.g. `{}` or
    `{'automaton': []}`) even on an unrealizable/fatal outcome, so
    `slugs_sm_size`/`reduced_sm_size` must also gate on the `realizable` flag
    -- otherwise unrealizable trials report a literal state count of `0`
    instead of the `--` master.csv/table convention for "no strategy exists."
    """
    populated = {'automaton': [{'state': 0}, {'state': 1}, {'state': 2}]}

    assert batch_run_harness._extracted_sm_size(populated, True) == 3
    assert batch_run_harness._extracted_sm_size(populated, False) is None
    assert batch_run_harness._extracted_sm_size({}, False) is None
    assert batch_run_harness._extracted_sm_size({'automaton': []}, False) is None
    assert batch_run_harness._extracted_sm_size(None, True) is None


def test_batch_summary_includes_well_separation_fields(tmp_path):
    """Grouped summaries should carry well-separation status and timing stats."""
    master_path = tmp_path / 'master.csv'
    summary_path = tmp_path / 'summary.csv'
    refreshed_summary_path = tmp_path / 'refreshed_summary.csv'
    rows = []
    for elapsed in (1.0, 3.0):
        row = {field: '' for field in batch_run_harness.CSV_FIELDNAMES}
        row.update({
            'capability_file': 'capabilities.yaml',
            'encoding': 'one-hot',
            'liveness': 'S',
            'pending': 'False',
            'ordering_mode': 'random',
            'reordering_enabled': 'True',
            'reordering_threshold': '250',
            'reordering_policy': 'threshold_250',
            'return_code': '0',
            'realizable': 'True',
            'well_separation_status': 'WELL_SEPARATED',
            'well_separation_complete': 'True',
            'slugs_reported_elapsed_time_s': str(elapsed),
            'slugs_timing_total_s': str(elapsed),
            'well_separation_wrapper_wall_time_s': '99.0',
            'core_size': '0',
            'spec_loader_time_s': '0.1',
            'capability_spec_time_s': '0.2',
            'compiler_time_s': '0.3',
            'reduced_mealy_graph_time_s': '0.4',
            'sm_generation_time_s': '0.5',
            'sm_layout_time_s': '0.6',
            'count_specs_time_s': '0.7',
            'state_defn_size': '3',
            'max_non_slugs_stage': 'sm_layout',
            'max_non_slugs_time_s': str(5.0 + elapsed),
            'non_slugs_total_time_s': str(6.0 + elapsed),
        })
        rows.append(row)
    batch_run_harness.write_rows(master_path, rows)

    batch_run_harness.write_summary(master_path, summary_path)

    summary_rows = list(csv.DictReader(
        summary_path.open(newline='', encoding='utf-8')
    ))
    assert len(summary_rows) == 1
    summary = summary_rows[0]
    assert summary['well_separation_status'] == 'WELL_SEPARATED'
    assert summary['well_separation_complete'] == 'True'
    assert summary['flexbe_hfsm_realized'] == 'Yes'
    assert summary['generate_specs_time_s_mean'] == '0.6'
    assert summary['realize_hfsm_time_s_mean'] == '2.2'
    assert summary['well_separation_analyzer_time_s_mean'] == '2.0'
    assert summary['slugs_reported_elapsed_time_s_mean'] == '2.0'
    assert summary['slugs_reported_elapsed_time_s_min'] == '1.0'
    assert summary['slugs_reported_elapsed_time_s_max'] == '3.0'
    assert summary['max_non_slugs_stage'] == 'sm_layout'
    assert summary['max_non_slugs_time_s_mean'] == '7.0'

    experiment_postprocess.write_summary(master_path, refreshed_summary_path)
    refreshed_rows = list(csv.DictReader(
        refreshed_summary_path.open(newline='', encoding='utf-8')
    ))
    refreshed = refreshed_rows[0]
    assert refreshed['well_separation_status'] == 'WELL_SEPARATED'
    assert refreshed['flexbe_hfsm_realized'] == 'Yes'
    assert refreshed['generate_specs_time_s_mean'] == '0.6'
    assert refreshed['realize_hfsm_time_s_mean'] == '2.2'
    assert refreshed['well_separation_analyzer_time_s_mean'] == '2.0'
    assert refreshed['slugs_reported_elapsed_time_s_mean'] == '2.0'
    assert refreshed['max_non_slugs_stage'] == 'sm_layout'
    assert refreshed['max_non_slugs_time_s_mean'] == '7.0'


def test_paper_table_rejects_duplicate_combined_indicators(tmp_path):
    """Combined paper tables should not silently overwrite Coffee columns."""
    summary_path = tmp_path / 'summary.csv'
    table_path = tmp_path / 'table.tex'
    fieldnames = [
        'capability_file',
        'encoding',
        'liveness',
        'pending',
        'column_indicator',
        'ordering_mode',
        'reordering_policy',
        'realizable',
    ]
    rows = [
        {
            'capability_file': 'coffee_capabilities.yaml',
            'encoding': 'enumerated',
            'liveness': 'S',
            'pending': 'False',
            'column_indicator': '2S',
            'ordering_mode': 'random',
            'reordering_policy': 'threshold_250',
            'realizable': 'Yes',
        },
        {
            'capability_file': 'coffee_capabilities.yaml',
            'encoding': 'one-hot',
            'liveness': 'S',
            'pending': 'False',
            'column_indicator': '2S',
            'ordering_mode': 'random',
            'reordering_policy': 'threshold_250',
            'realizable': 'Yes',
        },
    ]
    with summary_path.open('w', newline='', encoding='utf-8') as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match='--split-encoding-tables'):
        experiment_postprocess.write_paper_table(summary_path, table_path)


def test_paper_table_preserves_count_decimal_spread(tmp_path):
    """Paper count rows should not hide random-ordering strategy-size spread."""
    summary_path = tmp_path / 'summary.csv'
    table_path = tmp_path / 'table.tex'
    fieldnames = [
        'capability_file',
        'encoding',
        'liveness',
        'pending',
        'column_indicator',
        'ordering_mode',
        'reordering_policy',
        'realizable',
        'n',
        'slugs_sm_size_mean',
        'slugs_sm_size_min',
        'slugs_sm_size_max',
        'slugs_sm_size_stdev',
    ]
    rows = [
        {
            'capability_file': 'coffee_capabilities.yaml',
            'encoding': 'one-hot',
            'liveness': 'S',
            'pending': 'False',
            'column_indicator': '2S',
            'ordering_mode': 'random',
            'reordering_policy': 'threshold_250',
            'realizable': 'Yes',
            'n': '200',
            'slugs_sm_size_mean': '4.45',
            'slugs_sm_size_min': '4',
            'slugs_sm_size_max': '5',
            'slugs_sm_size_stdev': '0.49874213637205833',
        },
        {
            'capability_file': 'coffee_capabilities_extended.yaml',
            'encoding': 'one-hot',
            'liveness': 'S',
            'pending': 'False',
            'column_indicator': '3S',
            'ordering_mode': 'random',
            'reordering_policy': 'threshold_250',
            'realizable': 'Yes',
            'n': '200',
            'slugs_sm_size_mean': '7.0',
            'slugs_sm_size_min': '7',
            'slugs_sm_size_max': '7',
            'slugs_sm_size_stdev': '0.0',
        },
    ]
    with summary_path.open('w', newline='', encoding='utf-8') as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    experiment_postprocess.write_paper_table(
        summary_path,
        table_path,
        encoding='one-hot',
    )

    table = table_path.read_text(encoding='utf-8')
    assert r'\textbf{\textbar{}Slugs SM\textbar} & 4.5 & 7 \\' in table
    assert r'$\pm$ 0.5' in table
    assert '7.0' not in table


def test_paper_table_uses_ms_precision_for_coffee_scale_times(tmp_path):
    """Coffee-scale timing rows should not collapse to whole-millisecond zeros."""
    summary_path = tmp_path / 'summary.csv'
    table_path = tmp_path / 'table.tex'
    fieldnames = [
        'capability_file',
        'encoding',
        'liveness',
        'pending',
        'column_indicator',
        'ordering_mode',
        'reordering_policy',
        'realizable',
        'n',
        'realizability_time_s_mean',
        'realizability_time_s_min',
        'realizability_time_s_max',
        'realizability_time_s_stdev',
        'well_separation_analyzer_time_s_mean',
        'well_separation_analyzer_time_s_stdev',
    ]
    row = {
        'capability_file': 'coffee_capabilities.yaml',
        'encoding': 'one-hot',
        'liveness': 'S',
        'pending': 'False',
        'column_indicator': '2S',
        'ordering_mode': 'random',
        'reordering_policy': 'threshold_250',
        'realizable': 'Yes',
        'n': '10',
        'realizability_time_s_mean': '0.00056',
        'realizability_time_s_min': '0.00056',
        'realizability_time_s_max': '0.00056',
        'realizability_time_s_stdev': '0',
        'well_separation_analyzer_time_s_mean': '0.000028',
        'well_separation_analyzer_time_s_stdev': '0',
    }
    with summary_path.open('w', newline='', encoding='utf-8') as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    experiment_postprocess.write_paper_table(
        summary_path,
        table_path,
        encoding='one-hot',
        time_unit='ms',
    )

    table = table_path.read_text(encoding='utf-8')
    assert r'\shortstack{Realizability\\(ms)}} & 0.560 \\' in table
    assert r'\shortstack{Well Separation\\(ms)}} & 0.028 \\' in table


def test_paper_table_can_report_large_domain_times_in_seconds(tmp_path):
    """PyRoboSim/Crazyflie-style tables should avoid accidental ms scaling."""
    summary_path = tmp_path / 'summary.csv'
    table_path = tmp_path / 'table.tex'
    fieldnames = [
        'capability_file',
        'encoding',
        'liveness',
        'pending',
        'column_indicator',
        'ordering_mode',
        'reordering_policy',
        'realizable',
        'n',
        'overall_pipeline_time_s_mean',
        'overall_pipeline_time_s_min',
        'overall_pipeline_time_s_max',
        'overall_pipeline_time_s_stdev',
    ]
    row = {
        'capability_file': 'pyrobosim_capabilities.yaml',
        'encoding': 'one-hot',
        'liveness': 'S',
        'pending': 'False',
        'column_indicator': '2S',
        'ordering_mode': 'random',
        'reordering_policy': 'threshold_250',
        'realizable': 'Yes',
        'n': '3',
        'overall_pipeline_time_s_mean': '600.0',
        'overall_pipeline_time_s_min': '600.0',
        'overall_pipeline_time_s_max': '600.0',
        'overall_pipeline_time_s_stdev': '0',
    }
    with summary_path.open('w', newline='', encoding='utf-8') as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    experiment_postprocess.write_paper_table(
        summary_path,
        table_path,
        time_unit='s',
    )

    table = table_path.read_text(encoding='utf-8')
    assert r'\shortstack{Overall\\(s)}} & 600 \\' in table
    assert '600000' not in table


def test_compare_summary_means_flags_order_of_magnitude_changes(tmp_path):
    """Postprocess can warn when regenerated summary means drift dramatically."""
    baseline_path = tmp_path / 'baseline.csv'
    current_path = tmp_path / 'current.csv'
    fieldnames = [
        *experiment_postprocess.SUMMARY_KEYS,
        'realizability_time_s_mean',
    ]
    base_row = {field: '' for field in fieldnames}
    base_row.update({
        'capability_file': 'coffee_capabilities.yaml',
        'encoding': 'one-hot',
        'liveness': 'S',
        'pending': 'False',
        'column_indicator': '2S',
        'ordering_mode': 'random',
        'reordering_policy': 'threshold_250',
        'realizability_time_s_mean': '0.001',
    })
    current_row = dict(base_row)
    current_row['realizability_time_s_mean'] = '0.02'
    for path, row in ((baseline_path, base_row), (current_path, current_row)):
        with path.open('w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(row)

    warnings = experiment_postprocess.compare_summary_means(
        baseline_path,
        current_path,
        factor=10.0,
    )

    assert len(warnings) == 1
    assert 'realizability_time_s_mean changed by 20.0x' in warnings[0]


def test_batch_harness_runs_manager_like_post_synthesis_pipeline(monkeypatch, tmp_path):
    """Batch trials should execute the same post-synthesis chain as manager requests."""
    calls = []
    automaton = {'automaton': [{'id': 0}]}
    reduced_automaton = {'automaton': [{'id': 0}], 'reduced_automaton': True}
    state_defn = [object(), object()]

    class FakeProcess:
        """Minimal process stand-in that records call order."""

        def __init__(self, name, outputs):
            self.name = name
            self.outputs = outputs

        def process(self):
            calls.append(self.name)
            return self.outputs

    def fake_auditor(inputs):
        name = 'reduced_audit' if inputs[0].get('reduced_automaton') else 'original_audit'
        return FakeProcess(name, [
            {'valid': True, 'incomplete': False, 'failure_kind': None},
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ])

    row = batch_run_harness.MatrixRow.from_dict({
        'system_name': 'demo_system',
        'spec_name': 'DemoSpec',
        'spec_path': str(tmp_path / 'spec.yaml'),
        'capabilities_path': str(tmp_path / 'capabilities.yaml'),
        'encoding': 'one-hot',
        'liveness': 'S',
    })
    args = SimpleNamespace(
        skip_well_separation=True,
        synthesis_timeout_s=60.0,
        slugs_bin='slugs',
        auditor_timeout_s=60.0,
        mealy_graph_config={},
        reduced_automaton_name='reduced_automaton',
        use_fallback_layout=True,
    )

    def fake_build_spec(_row, _state_mappings, _system_capabilities, stage_times):
        stage_times['spec_loader_time_s'] = 0.01
        stage_times['request_spec_time_s'] = 0.02
        return {}

    monkeypatch.setattr(batch_run_harness, 'build_spec', fake_build_spec)
    monkeypatch.setattr(
        batch_run_harness,
        'compiler_main',
        lambda inputs: FakeProcess('compiler', [
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'synthesizer_main',
        lambda inputs: FakeProcess('synthesizer', [
            automaton,
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(batch_run_harness, 'strategy_auditor_main', fake_auditor)
    monkeypatch.setattr(
        batch_run_harness,
        'mealy_graph_main',
        lambda inputs: FakeProcess(f'mealy:{inputs[2]}', [
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'reducer_main',
        lambda inputs: FakeProcess('reducer', [
            reduced_automaton,
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'sm_generator_main',
        lambda inputs: FakeProcess('sm_generator', [
            state_defn,
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'sm_layout_main',
        lambda inputs: FakeProcess('sm_layout', [
            inputs[0],
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'count_specs_main',
        lambda inputs: FakeProcess('count_specs', [{}]),
    )

    (
        result_automaton,
        result_reduced,
        error_code,
        original_audit,
        reduced_audit,
        _well_separation,
        stage_times,
        result_state_defn,
        _count_specs,
    ) = batch_run_harness.compile_and_synthesize(
        row, tmp_path, {}, {}, args,
    )

    assert result_automaton is automaton
    assert result_reduced is reduced_automaton
    assert error_code == SynthesisErrorCode.SUCCESS
    assert original_audit['audit_valid'] is True
    assert reduced_audit['audit_valid'] is True
    assert result_state_defn == state_defn
    assert calls == [
        'compiler',
        'synthesizer',
        'original_audit',
        'mealy:DemoSpec',
        'reducer',
        'reduced_audit',
        'mealy:reduced_automaton',
        'sm_generator',
        'sm_layout',
        'count_specs',
    ]
    expected_timed_fields = [
        'spec_loader_time_s',
        'request_spec_time_s',
        'compiler_time_s',
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
    for field in expected_timed_fields:
        assert isinstance(stage_times[field], float)
    assert stage_times['well_separation_analyzer_time_s'] is None


def test_batch_harness_original_auditor_failure_preempts_reduction(monkeypatch, tmp_path):
    """Invalid original automata should stop before reduction or reduced audit."""
    calls = []
    automaton = {'automaton': [{'id': 0}]}

    class FakeProcess:
        """Minimal process stand-in that records call order."""

        def __init__(self, name, outputs):
            self.name = name
            self.outputs = outputs

        def process(self):
            calls.append(self.name)
            return self.outputs

    row = batch_run_harness.MatrixRow.from_dict({
        'system_name': 'demo_system',
        'spec_name': 'DemoSpec',
        'spec_path': str(tmp_path / 'spec.yaml'),
        'capabilities_path': str(tmp_path / 'capabilities.yaml'),
        'encoding': 'enumerated',
        'liveness': 'S',
    })
    args = SimpleNamespace(
        skip_well_separation=True,
        synthesis_timeout_s=60.0,
        slugs_bin='slugs',
        auditor_timeout_s=60.0,
    )

    monkeypatch.setattr(
        batch_run_harness,
        'build_spec',
        lambda _row, _state_mappings, _system_capabilities, _stage_times: {},
    )
    monkeypatch.setattr(
        batch_run_harness,
        'compiler_main',
        lambda inputs: FakeProcess('compiler', [
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'synthesizer_main',
        lambda inputs: FakeProcess('synthesizer', [
            automaton,
            SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS),
        ]),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'strategy_auditor_main',
        lambda inputs: FakeProcess('original_audit', [
            {
                'valid': False,
                'incomplete': False,
                'failure_kind': 'GOAL_UNREACHABLE',
            },
            SynthesisErrorCode(value=SynthesisErrorCode.AUTOMATON_INVALID),
        ]),
    )

    def fail_if_reduced(_inputs):
        raise AssertionError('reducer should not run after original audit failure')

    monkeypatch.setattr(batch_run_harness, 'reducer_main', fail_if_reduced)

    (
        result_automaton,
        result_reduced,
        error_code,
        original_audit,
        reduced_audit,
        _well_separation,
        stage_times,
        _state_defn,
        _count_specs,
    ) = batch_run_harness.compile_and_synthesize(
        row, tmp_path, {}, {}, args,
    )

    assert result_automaton is automaton
    assert result_reduced is None
    assert error_code == SynthesisErrorCode.AUTOMATON_INVALID
    assert original_audit['audit_failure_kind'] == 'GOAL_UNREACHABLE'
    assert reduced_audit == batch_run_harness.empty_audit()
    assert calls == ['compiler', 'synthesizer', 'original_audit']
    assert isinstance(stage_times['original_auditor_time_s'], float)
    assert stage_times['reduction_time_s'] is None


def test_batch_harness_summarizes_and_writes_stage_timings(tmp_path):
    """Detailed timings go to JSON while CSV carries the non-Slugs max stage."""
    stage_times = batch_run_harness.empty_stage_times()
    stage_times.update({
        'spec_loader_time_s': 0.1,
        'compiler_time_s': 0.4,
        'synthesizer_time_s': 10.0,
        'well_separation_analyzer_time_s': 9.0,
        'sm_layout_time_s': 1.2,
    })

    summary = batch_run_harness.non_slugs_timing_summary(stage_times)
    output_path = tmp_path / 'stage_timings.json'
    batch_run_harness.write_stage_timing_json(output_path, stage_times)

    assert summary['max_non_slugs_stage'] == 'sm_layout'
    assert summary['max_non_slugs_time_s'] == 1.2
    assert summary['non_slugs_total_time_s'] == pytest.approx(1.7)
    payload = json.loads(output_path.read_text(encoding='utf-8'))
    assert payload['synthesizer_time_s'] == 10.0
    assert payload['sm_layout_time_s'] == 1.2


def test_batch_harness_prepares_discrete_abstraction(monkeypatch, tmp_path):
    """Batch preprocessing should generate the SM-generation abstraction artifact."""
    calls = []
    row = batch_run_harness.MatrixRow.from_dict({
        'system_name': 'demo_system',
        'spec_name': 'DemoSpec',
        'spec_path': str(tmp_path / 'spec.yaml'),
        'capabilities_path': str(tmp_path / 'capabilities.yaml'),
        'encoding': 'one-hot',
        'liveness': 'S',
    })

    class FakeWorkspaceParser:
        """Workspace-parser stand-in."""

        def __init__(self, inputs):
            self.inputs = inputs

        def preprocess(self):
            return {'workspace': True}, []

    class FakeCapabilityLoader:
        """Capability-loader stand-in."""

        def __init__(self, inputs):
            self.inputs = inputs

        def preprocess(self):
            return (
                {'capabilities': {}, 'sm_outcome_mappings': {}},
                {'states': 'before'},
                {'behaviors': 'before'},
            )

    class FakeTransitionGenerator:
        """Transition-generator stand-in."""

        def __init__(self, inputs):
            self.inputs = inputs

        def preprocess(self):
            return (
                self.inputs[1],
                {},
                {},
                {},
                {'states': 'after'},
                {'behaviors': 'after'},
            )

    class FakeDiscreteGenerator:
        """Discrete-abstraction-generator stand-in."""

        def __init__(self, inputs):
            self.inputs = inputs
            self.synthesis_home = ''

        def preprocess(self):
            calls.append((self.inputs, self.synthesis_home))

    monkeypatch.setattr(
        batch_run_harness,
        'workspace_parser_main',
        lambda inputs: FakeWorkspaceParser(inputs),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'capability_loader_main',
        lambda inputs: FakeCapabilityLoader(inputs),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'transition_relations_main',
        lambda inputs: FakeTransitionGenerator(inputs),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'discrete_abstraction_main',
        lambda inputs: FakeDiscreteGenerator(inputs),
    )
    monkeypatch.setattr(
        batch_run_harness,
        'load_yaml',
        lambda path: {'name': 'demo_system', 'transition_relations': {}},
    )

    batch_run_harness.prepare_system_capabilities(row, {}, synthesis_home=tmp_path)

    assert calls == [([
        'demo_system',
        {'capabilities': {}, 'sm_outcome_mappings': {}, 'transition_relations': {}},
        {'states': 'after'},
        {'behaviors': 'after'},
    ], tmp_path)]


def test_batch_harness_skip_long_filters_pyrobosim_and_drone_rows(tmp_path):
    """--skip-long should remove the expensive pyrobosim and drone examples."""
    rows = [
        batch_run_harness.MatrixRow.from_dict({
            'example': 'coffee',
            'system_name': 'coffee_maker',
            'spec_name': 'CoffeeSpec',
            'spec_path': str(tmp_path / 'coffee_spec.yaml'),
            'capabilities_path': str(tmp_path / 'coffee_capabilities.yaml'),
            'encoding': 'one-hot',
            'liveness': 'S',
        }),
        batch_run_harness.MatrixRow.from_dict({
            'example': 'pyrobosim',
            'system_name': 'pyrobosim_demo',
            'spec_name': 'PyRoboSpec',
            'spec_path': str(tmp_path / 'pyro_spec.yaml'),
            'capabilities_path': str(tmp_path / 'pyro_capabilities.yaml'),
            'encoding': 'one-hot',
            'liveness': 'S',
        }),
        batch_run_harness.MatrixRow.from_dict({
            'example': 'two_rivers',
            'system_name': 'river_demo',
            'spec_name': 'DroneSurvey',
            'spec_path': str(tmp_path / 'drone_spec.yaml'),
            'capabilities_path': str(tmp_path / 'drone_capabilities.yaml'),
            'encoding': 'one-hot',
            'liveness': 'S',
        }),
    ]

    filtered = batch_run_harness.filter_matrix_rows(rows, skip_long=True)

    assert [row.example for row in filtered] == ['coffee']
    assert batch_run_harness.filter_matrix_rows(rows, skip_long=False) == rows


def test_latex_table_columns_are_data_driven_for_reordering_policies(tmp_path):
    """Future threshold policies should appear without hard-coded table columns."""
    summary_path = tmp_path / 'summary.csv'
    output_path = tmp_path / 'table.tex'
    fieldnames = [
        *experiment_postprocess.SUMMARY_KEYS,
        'n',
        'failures',
        'cudd_peak_nodes_mean',
        'cudd_peak_nodes_min',
        'cudd_peak_nodes_max',
    ]
    rows = [
        {
            'capability_file': 'capabilities.yaml',
            'encoding': 'one-hot',
            'liveness': 'S',
            'pending': 'False',
            'ordering_mode': 'random',
            'reordering_enabled': 'True',
            'reordering_threshold': '1000',
            'reordering_policy': 'threshold_1000',
            'n': '3',
            'failures': '0',
            'cudd_peak_nodes_mean': '42',
            'cudd_peak_nodes_min': '42',
            'cudd_peak_nodes_max': '42',
        },
    ]
    with summary_path.open('w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    experiment_postprocess.write_latex_table(summary_path, output_path)

    table = output_path.read_text(encoding='utf-8')
    assert 'Random threshold 1000' in table
    assert 'T250' not in table
    assert '42' in table


def test_latex_table_mean_values_use_one_decimal_for_varied_runs(tmp_path):
    """Mean table cells distinguish sampled averages from identical integer runs."""
    summary_path = tmp_path / 'summary.csv'
    output_path = tmp_path / 'table.tex'
    fieldnames = [
        *experiment_postprocess.SUMMARY_KEYS,
        'n',
        'failures',
        'cudd_peak_nodes_mean',
        'cudd_peak_nodes_min',
        'cudd_peak_nodes_max',
    ]
    rows = [
        {
            'capability_file': 'capabilities.yaml',
            'encoding': 'one-hot',
            'liveness': 'S',
            'pending': 'False',
            'ordering_mode': 'random',
            'reordering_enabled': 'True',
            'reordering_threshold': '250',
            'reordering_policy': 'threshold_250',
            'n': '4',
            'failures': '0',
            'cudd_peak_nodes_mean': '42.25',
            'cudd_peak_nodes_min': '41',
            'cudd_peak_nodes_max': '43',
        },
    ]
    with summary_path.open('w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    experiment_postprocess.write_latex_table(summary_path, output_path)

    table = output_path.read_text(encoding='utf-8')
    assert '42.3' in table
    assert '42.25' not in table


def test_slugs_synthesizer_uses_cwd_without_changing_process_cwd(tmp_path, monkeypatch):
    """Slugs should run in the artifact directory without mutating global cwd."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    original_cwd = os.getcwd()
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _patch_fake_slugs_process(
        monkeypatch,
        'RESULT: Specification is realizable.',
        0,
    )

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert os.getcwd() == original_cwd
    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert automaton_file == os.path.join(helper.specs_output_dir_path, 'demo.json')
    assert _FakeSlugsProcess.instances[0].kwargs['cwd'] == helper.specs_output_dir_path
    assert (tmp_path / 'demo' / 'synthesis_byproducts' / 'demo.output').exists()


def test_slugs_synthesizer_cancel_terminates_running_slugs(tmp_path, monkeypatch):
    """Canceling the helper should terminate a running Slugs subprocess."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _BlockingSlugsProcess.instances = []

    process_created = threading.Event()

    def _popen(args, **kwargs):
        process = _BlockingSlugsProcess(args, **kwargs)
        process_created.set()
        return process

    monkeypatch.setattr(
        slugs_synthesizer_helper.subprocess,
        'Popen',
        _popen,
    )
    result = {}

    def _run_synthesis():
        result['value'] = helper.call_slugs_synthesizer('demo')

    thread = threading.Thread(target=_run_synthesis, daemon=True)
    thread.start()
    assert process_created.wait(timeout=1.0)
    process = _BlockingSlugsProcess.instances[0]
    assert process.started.wait(timeout=1.0)

    helper.cancel()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert process.terminated
    assert result['value'][0] == ''
    assert result['value'][1].value == SynthesisErrorCode.PREEMPTED


def test_slugs_synthesizer_timeout_terminates_slugs_with_helpful_output(
    tmp_path,
    monkeypatch,
):
    """A hung Slugs process should fail with a configurable-timeout hint."""
    helper = SlugsSynthesizerHelper(
        str(tmp_path / 'demo'),
        ['completed', 'failure'],
        slugs_timeout_s=0.01,
    )
    monkeypatch.setattr(
        slugs_synthesizer_helper,
        'find_slugs_binary',
        lambda: '/usr/bin/slugs',
    )
    _BlockingSlugsProcess.instances = []

    def _popen(args, **kwargs):
        return _BlockingSlugsProcess(args, **kwargs)

    monkeypatch.setattr(
        slugs_synthesizer_helper.subprocess,
        'Popen',
        _popen,
    )

    automaton_file, error_code = helper.call_slugs_synthesizer('demo')

    assert automaton_file == ''
    assert error_code.value == SynthesisErrorCode.SYNTHESIS_FAILED
    assert _BlockingSlugsProcess.instances[0].terminated
    output = (tmp_path / 'demo' / 'synthesis_byproducts' / 'demo.output').read_text(
        encoding='utf-8',
    )
    assert 'SLUGS synthesis timed out after 0.01 seconds' in output
    assert "'synthesis_timeout_s' value in your process pipeline data file" in output


def test_slugs_synthesizer_deadline_race_collects_finished_process(tmp_path):
    """A process that exits at the deadline should not be killed as timed out."""
    helper = SlugsSynthesizerHelper(str(tmp_path / 'demo'), ['completed', 'failure'])
    helper.slugs_timeout_s = 0.0
    process = _FinishedAtDeadlineProcess()

    output, status, timed_out = helper._wait_for_slugs_process(process)

    assert output == 'RESULT: Specification is realizable.'
    assert status == 0
    assert timed_out is False
    assert process.terminated is False
    assert process.communicate_calls == 2


def test_slugs_synthesizer_status_prints_elapsed_and_remaining(tmp_path, capsys):
    """Status line should include elapsed/remaining times and optional RSS."""
    helper = SlugsSynthesizerHelper(
        str(tmp_path / 'demo'), ['completed', 'failure'], slugs_timeout_s=900.0,
    )

    helper._print_synthesis_status(elapsed_s=42.0, remaining_s=858.0, pid=os.getpid())

    captured = capsys.readouterr()
    assert 'elapsed=42s' in captured.out
    assert 'remaining=858s' in captured.out
    assert 'of 900s' in captured.out


def test_slugs_synthesizer_status_omits_rss_when_unavailable(tmp_path, capsys, monkeypatch):
    """Status line should not show RSS when /proc is unavailable."""
    helper = SlugsSynthesizerHelper(
        str(tmp_path / 'demo'), ['completed', 'failure'], slugs_timeout_s=60.0,
    )
    monkeypatch.setattr(helper, '_get_process_rss_mb', staticmethod(lambda pid: None))

    helper._print_synthesis_status(elapsed_s=5.0, remaining_s=55.0, pid=0)

    captured = capsys.readouterr()
    assert 'elapsed=5s' in captured.out
    assert 'Memory' not in captured.out


def test_slugs_synthesizer_process_accepts_optional_timeout():
    """The process wrapper should default the Slugs timeout and allow override."""
    default_process = slugs_synthesizer.main(
        [
            '/tmp/demo',
            {
                'transition_outcomes': ['completed', 'failure'],
                'sm_outcome_mappings': ['finished', 'failed'],
            },
        ],
    )
    override_process = slugs_synthesizer.main(
        [
            '/tmp/demo',
            {
                'transition_outcomes': ['completed', 'failure'],
                'sm_outcome_mappings': ['finished', 'failed'],
            },
            60.0,
        ],
    )

    assert default_process.synthesis_timeout_s == 900
    assert override_process.synthesis_timeout_s == 60.0


def test_slugs_automaton_round_trips_as_safe_dict():
    """Automata should serialize without Python object tags."""
    state = SlugsAutomatonState(
        name='0',
        output_valuation=1,
        input_valuation=0,
        transitions=['0'],
    )
    state.output_variables = ['done']
    state.output_values = {'done': True}
    automaton = SlugsAutomaton(
        output_variables=['done'],
        input_variables=[],
        states=[state],
    )
    automaton.update_state_map()

    data = automaton.to_dict()
    loaded = SlugsAutomaton.from_dict(yaml.safe_load(yaml.safe_dump(data)))

    assert loaded.to_dict() == data


def test_slugs_automaton_update_state_map_rejects_missing_transition_target():
    """Dangling transition references should fail with source/target context."""
    state = SlugsAutomatonState(
        name='S0',
        output_valuation=0,
        input_valuation=0,
        transitions=['missing'],
    )
    automaton = SlugsAutomaton(states=[state])

    with pytest.raises(ValueError, match='S0.*missing'):
        automaton.update_state_map()


def test_slugs_automaton_loader_uses_safe_yaml(tmp_path):
    """Automaton loader should read plain YAML without unsafe object tags."""
    automaton_path = tmp_path / 'automaton.yaml'
    automaton_path.write_text(
        yaml.safe_dump(
            {
                'output_variables': ['done'],
                'input_variables': [],
                'automaton': [
                    {
                        'name': '0',
                        'output_valuation': 1,
                        'input_valuation': 0,
                        'transitions': ['0'],
                        'rank': 0,
                        'output_variables': ['done'],
                        'input_variables': [],
                        'output_values': {'done': True},
                        'input_values': {},
                        'incoming': [],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )

    automaton, error_code = automaton_loader_main([str(automaton_path)]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert automaton['automaton'][0]['name'] == '0'
    assert isinstance(automaton['automaton'][0], dict)


def test_gr1_proposition_merge_validates_inputs():
    """GR(1) proposition merging should not rely on Python assert."""
    spec = GR1Specification('demo')

    try:
        spec.merge_env_propositions(['not-a-set'])
    except TypeError as exc:
        assert 'set of strings' in str(exc)
    else:
        raise AssertionError('Expected invalid environment propositions to fail.')

    try:
        spec.merge_sys_propositions({1})
    except TypeError as exc:
        assert 'set of strings' in str(exc)
    else:
        raise AssertionError('Expected invalid system propositions to fail.')


def test_slugs_mealy_graph_uses_pipeline_graph_config(tmp_path):
    """Mealy graph process should apply DOT style options from pipeline data."""
    state = SlugsAutomatonState(
        name='0',
        output_valuation=1,
        input_valuation=0,
        transitions=['0'],
    )
    state.output_variables = ['done']
    state.output_values = {'done': True}
    automaton = SlugsAutomaton(
        output_variables=['done'],
        input_variables=[],
        states=[state],
    )
    automaton.update_state_map()

    process = slugs_mealy_graph.main(
        [
            automaton.to_dict(),
            str(tmp_path),
            'demo_graph',
            {
                'font_size': 10,
                'penwidth': 3.5,
                'env_node_size': 0.6,
                'sys_node_size': 0.2,
                'sys_choice_edge_color': 'blue',
                'env_choice_edge_color': 'orange',
                'show_node_ids': False,
            },
        ]
    )
    (error_code,) = process.process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    dot_text = (tmp_path / 'demo_graph.dot').read_text(encoding='utf-8')
    assert 'penwidth=3.5' in dot_text
    assert 'fontsize=10' in dot_text
    assert 'width=0.6' in dot_text
    assert 'width=0.2' in dot_text
    assert 'color="blue"' in dot_text
    assert 'color="orange"' in dot_text


def test_sm_generation_reports_missing_initial_state(tmp_path, monkeypatch):
    """SM generation should use the specific no-initial-state error."""
    system_name = 'demo_system'
    config_dir = tmp_path / system_name / 'configs'
    config_dir.mkdir(parents=True)
    (config_dir / f'{system_name}_system_capabilities.yaml').write_text(
        'capabilities: {}\n',
        encoding='utf-8',
    )
    (config_dir / f'{system_name}_discrete_abstraction.yaml').write_text(
        'output: {}\n',
        encoding='utf-8',
    )

    class EmptyInitialStateConfig:
        """Test double that simulates an automaton with no initial state."""

        def __init__(self, *args, **kwargs):
            pass

        def get_init_states(self):
            return []

    monkeypatch.setattr(
        sm_generation_helpers.fpths,
        'get_synthesis_home',
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        sm_generation_helpers,
        'SMGenConfig',
        EmptyInitialStateConfig,
    )

    _, error_code, _warnings = sm_generation_helpers.SMGenerationHelpers().generate_sm(
        SlugsAutomaton().to_dict(),
        system_name,
    )

    assert error_code == SynthesisErrorCode.AUTOMATON_NO_INITIAL_STATE


def test_sm_generation_rejects_malformed_loaded_system_capabilities(tmp_path, monkeypatch):
    """SM generation file loader should validate capability config shape."""
    system_name = 'demo_system'
    config_dir = tmp_path / system_name / 'configs'
    config_dir.mkdir(parents=True)
    (config_dir / f'{system_name}_system_capabilities.yaml').write_text(
        '- invalid\n',
        encoding='utf-8',
    )
    (config_dir / f'{system_name}_discrete_abstraction.yaml').write_text(
        'output: {}\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(
        sm_generation_helpers.fpths,
        'get_synthesis_home',
        lambda *args, **kwargs: str(tmp_path),
    )

    _, error_code, _warnings = sm_generation_helpers.SMGenerationHelpers().generate_sm(
        SlugsAutomaton().to_dict(),
        system_name,
    )

    assert error_code == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_generation_rejects_loaded_discrete_abstraction_without_output(
    tmp_path,
    monkeypatch,
):
    """SM generation file loader should validate discrete abstraction essentials."""
    system_name = 'demo_system'
    config_dir = tmp_path / system_name / 'configs'
    config_dir.mkdir(parents=True)
    (config_dir / f'{system_name}_system_capabilities.yaml').write_text(
        'capabilities: {}\n',
        encoding='utf-8',
    )
    (config_dir / f'{system_name}_discrete_abstraction.yaml').write_text(
        'name: demo_system\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(
        sm_generation_helpers.fpths,
        'get_synthesis_home',
        lambda *args, **kwargs: str(tmp_path),
    )

    _, error_code, _warnings = sm_generation_helpers.SMGenerationHelpers().generate_sm(
        SlugsAutomaton().to_dict(),
        system_name,
    )

    assert error_code == SynthesisErrorCode.SM_GENERATION_FAILED


@pytest.mark.parametrize(
    'value',
    [
        'demo_system',
        'VendingDemoSM',
        'spec-1.2_3',
    ],
)
def test_sm_generation_path_component_validation_accepts_safe_names(value):
    """SM generation should allow ordinary hidden-artifact directory names."""
    assert (
        sm_generation_helpers.SMGenerationHelpers._validate_path_component(
            value,
            'system_name',
        )
        == value
    )


@pytest.mark.parametrize(
    'value',
    [
        '',
        '.',
        '..',
        '../escape',
        'nested/spec',
        'nested\\spec',
        'name with spaces',
        'name:$bad',
    ],
)
def test_sm_generation_path_component_validation_rejects_unsafe_names(value):
    """SM generation should reject traversal and unsupported system names."""
    with pytest.raises(ValueError, match='Invalid system_name'):
        sm_generation_helpers.SMGenerationHelpers._validate_path_component(
            value,
            'system_name',
        )


def test_sm_generation_rejects_unsafe_system_name_before_path_join(tmp_path, monkeypatch):
    """Unsafe system names should fail before reading hidden config paths."""
    monkeypatch.setattr(
        sm_generation_helpers.fpths,
        'get_synthesis_home',
        lambda *args, **kwargs: str(tmp_path),
    )

    _, error_code, _warnings = sm_generation_helpers.SMGenerationHelpers().generate_sm(
        SlugsAutomaton().to_dict(),
        '../escape',
    )

    assert error_code == SynthesisErrorCode.SM_GENERATION_FAILED
    assert not (tmp_path.parent / 'escape').exists()


def test_sm_generation_normalizes_begin_game_bootstrap_variables():
    """begin_game_a is the initial state and should not need a FlexBE mapping."""
    initial = SlugsAutomatonState(
        name='S0',
        output_valuation=1,
        input_valuation=0,
        transitions=['S1'],
    )
    initial.output_variables = ['begin_game_a']
    initial.output_values = {'begin_game_a': True}
    initial.is_initial = True

    action = SlugsAutomatonState(
        name='S1',
        output_valuation=2,
        input_valuation=1,
        transitions=['S1'],
    )
    action.input_variables = ['begin_game_c', 'begin_game_f', 'step_c']
    action.input_values = {
        'begin_game_c': True,
        'begin_game_f': False,
        'step_c': True,
    }
    action.output_variables = ['step_a']
    action.output_values = {'step_a': True}

    automaton = SlugsAutomaton(
        output_variables=['begin_game_a', 'step_a'],
        input_variables=['begin_game_c', 'begin_game_f', 'step_c'],
        states=[initial, action],
    )
    automaton.update_state_map()

    sm_generation_helpers.SMGenerationHelpers().normalize_bootstrap_begin_game(automaton)

    assert automaton.output_variables == ['step_a']
    assert automaton.input_variables == ['step_c']
    assert automaton['S0'].output_variables == []
    assert automaton['S0'].output_values == {}
    assert automaton['S1'].input_variables == ['step_c']
    assert automaton['S1'].input_values == {'step_c': True}


def test_parsed_sm_generation_preserves_action_userdata_remapping():
    """Parsed actions materialized from outcomes retain their userdata map."""
    initial = _make_sm_state(
        'S0',
        output_values={'capability': 1},
        transitions=['S1'],
    )
    initial.is_initial = True
    completed = _make_sm_state(
        'S1',
        input_variables=['step_c'],
        input_values={'step_c': True},
        output_values={'capability': 1},
        transitions=['S1'],
    )
    automaton = SlugsAutomaton(
        output_variables=['capability:0...1'],
        input_variables=['step_c'],
        states=[initial, completed],
    )
    automaton.update_state_map()
    discrete_abstraction = {
        'output': {},
        'parsed_action_map': {'capability': {1: 'step_a'}},
        'step_a': {
            'class_decl': {'name': 'StepState', 'parameters': {}},
            'state_outcome_mapping': {'step_c': ['done']},
            'autonomy': 1,
            'userdata_in': {'avoidance_radius': 'gate_radius'},
        },
    }

    state_defs, error_code, warnings = (
        sm_generation_helpers.SMGenerationHelpers().generate_sm_from_data(
            automaton.to_dict(),
            {},
            discrete_abstraction,
        )
    )

    step_state = next(state for state in state_defs if state.state_class == 'StepState')
    assert step_state.userdata_keys == ['avoidance_radius']
    assert step_state.userdata_remapping == ['gate_radius']
    assert error_code == SynthesisErrorCode.SUCCESS
    assert warnings == []


def test_sm_generation_strips_begin_game_outcomes_when_action_never_fires():
    """Hand-written specs that force '!begin_game_a' still expose begin_game_c/f."""
    initial = SlugsAutomatonState(
        name='S0',
        output_valuation=0,
        input_valuation=0,
        transitions=['S1'],
    )
    initial.is_initial = True

    action = SlugsAutomatonState(
        name='S1',
        output_valuation=1,
        input_valuation=1,
        transitions=['S1'],
    )
    action.input_variables = ['begin_game_c', 'begin_game_f', 'step_c']
    action.input_values = {
        'begin_game_c': True,
        'begin_game_f': False,
        'step_c': True,
    }
    action.output_variables = ['step_a']
    action.output_values = {'step_a': True}

    automaton = SlugsAutomaton(
        output_variables=['step_a'],
        input_variables=['begin_game_c', 'begin_game_f', 'step_c'],
        states=[initial, action],
    )
    automaton.update_state_map()

    sm_generation_helpers.SMGenerationHelpers().normalize_bootstrap_begin_game(automaton)

    assert automaton.output_variables == ['step_a']
    assert automaton.input_variables == ['step_c']
    assert automaton['S1'].input_variables == ['step_c']
    assert automaton['S1'].input_values == {'step_c': True}


def test_sm_generation_rejects_non_initial_begin_game_activation():
    """begin_game_a should correspond to the initial state only."""
    initial = SlugsAutomatonState(
        name='S0',
        output_valuation=0,
        input_valuation=0,
        transitions=['S1'],
    )
    initial.is_initial = True

    action = SlugsAutomatonState(
        name='S1',
        output_valuation=1,
        input_valuation=0,
        transitions=[],
    )
    action.output_variables = ['begin_game_a']
    action.output_values = {'begin_game_a': True}

    automaton = SlugsAutomaton(
        output_variables=['begin_game_a'],
        input_variables=[],
        states=[initial, action],
    )
    automaton.update_state_map()

    with pytest.raises(ValueError, match='solver output violates'):
        sm_generation_helpers.SMGenerationHelpers().normalize_bootstrap_begin_game(automaton)


def test_sm_generation_rejects_inconsistent_begin_game_output_variables():
    """begin_game_a on the initial state must also be declared globally."""
    initial = SlugsAutomatonState(
        name='S0',
        output_valuation=1,
        input_valuation=0,
        transitions=[],
    )
    initial.output_variables = ['begin_game_a']
    initial.output_values = {'begin_game_a': True}
    initial.is_initial = True

    automaton = SlugsAutomaton(
        output_variables=[],
        input_variables=[],
        states=[initial],
    )
    automaton.update_state_map()

    with pytest.raises(ValueError, match='missing from automaton output_variables'):
        sm_generation_helpers.SMGenerationHelpers().normalize_bootstrap_begin_game(automaton)


def test_sm_generator_failure_output_is_always_list(monkeypatch):
    """SM generator failure should keep the StateInstantiation output list-typed."""

    class FailingSMGenerationHelpers:
        """Test double that forces the SM generator exception path."""

        def generate_sm(self, *args):
            raise ValueError('bad automaton')

    monkeypatch.setattr(
        slugs_sm_generator,
        'SMGenerationHelpers',
        FailingSMGenerationHelpers,
    )

    state_defs, error_code = slugs_sm_generator.SM_Generator(
        name='SM Generator',
        synthesized_automaton={},
        system_capabilities_name='demo_system',
    ).process()

    assert state_defs == []
    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def _make_sm_gen_config_stub(activation_var, response_map):
    """Build a minimal SMGenConfig-like object for _get_next_state_input_conditions tests."""
    config = object.__new__(SMGenConfig)
    # Map response vars (e.g. 'foo_c', 'foo_f') to their activation var so
    # _map_generic_outcome_to_response can recognise them as concrete.
    config.in_var_to_class_decl = {rv: {} for rv in response_map}
    config.activation_to_out_map = {activation_var: response_map}
    config.parsed_action_variable = None
    config.parsed_index_to_action = {}
    config.in_var_to_out_var = {rv: activation_var for rv in response_map}
    return config


def _make_sm_state(name, *, input_variables=None, input_values=None, output_variables=None,
                   output_values=None, transitions=None):
    """Build a minimal SlugsAutomatonState for condition-lookup tests."""
    state = SlugsAutomatonState(
        name=name,
        output_valuation=0,
        input_valuation=0,
        transitions=transitions or [],
    )
    state.input_variables = input_variables or []
    state.input_values = input_values or {}
    state.output_variables = output_variables or []
    state.output_values = output_values or {}
    return state


def test_get_next_state_input_conditions_uses_input_values_when_input_variables_empty():
    """
    A forward edge whose target has empty input_variables picks up input_values.

    Regression: before the fix, only self-transitions used input_values, so a
    failure-retry state (input_variables=[], input_values={'failure': True}) produced
    empty conditions when reached via a forward edge, silently dropping the transition.
    """
    config = _make_sm_gen_config_stub('foo_a', {'foo_c': ['done'], 'foo_f': ['failed']})
    source = _make_sm_state('S0', output_variables=['foo_a'])
    # Target: failure-retry state — condition lives only in input_values, not input_variables.
    target = _make_sm_state('S1', input_variables=[], input_values={'failure': True})

    result = config._get_next_state_input_conditions(source, target)

    assert result == ['failure'], (
        'failure condition must be returned for a forward edge to a state '
        'that stores its condition only in input_values'
    )


def test_get_next_state_input_conditions_ignores_input_values_when_input_variables_populated():
    """
    A forward edge whose target already has input_variables does NOT use input_values.

    Regression guard: after a reducer merge the surviving state may carry both
    input_variables (the forward condition) and input_values (the failure-retry
    condition of the absorbed state).  Using input_values there would contaminate
    the forward edge with a spurious failure condition.
    """
    config = _make_sm_gen_config_stub('foo_a', {'foo_c': ['done'], 'foo_f': ['failed']})
    source = _make_sm_state('S0', output_variables=['foo_a'])
    # Target: merged state with forward condition in input_variables AND stale
    # failure indicator in input_values.
    target = _make_sm_state(
        'S1',
        input_variables=['foo_c'],
        input_values={'failure': True},
    )

    result = config._get_next_state_input_conditions(source, target)

    assert result == ['foo_c'], (
        'input_values must be ignored on a forward edge when input_variables is already set '
        '(prevents contaminating the forward condition with the failure-retry condition)'
    )


# ── StrategyAuditor ───────────────────────────────────────────────────────────


def _write_auditor_protocol_spec(tmp_path):
    """Write a minimal spec that exposes activation -> next outcome semantics."""
    spec_path = tmp_path / 'demo.slugsin'
    spec_path.write_text(
        '\n'.join([
            '[INPUT]',
            'log_failed_c',
            '[OUTPUT]',
            'log_failed_a',
            '[ENV_TRANS]',
            "log_failed_a -> log_failed_c'",
            '',
        ]),
        encoding='utf-8',
    )
    return spec_path


def _auditor_protocol_fixture():
    system_capabilities = {
        'transition_outcomes': ['completed'],
        'capabilities': {
            'log_failed': {
                'state': {
                    'outcomes': {
                        'done': {'remapping': 'completed'},
                    },
                },
            },
        },
    }
    slugs_specification = {
        'env_trans': ["log_failed_a -> log_failed_c'"],
    }
    automaton = {
        'output_variables': ['log_failed_a'],
        'input_variables': ['log_failed_c'],
        'automaton': [
            {
                'name': 'S0',
                'output_valuation': [0],
                'input_valuation': [0],
                'transitions': ['S1'],
                'rank': 0,
                'output_variables': [],
                'input_variables': [],
                'output_values': {},
                'input_values': {},
                'incoming': [],
                'is_initial': True,
            },
            {
                'name': 'S1',
                'output_valuation': [0],
                'input_valuation': [1],
                'transitions': ['S1'],
                'rank': 1,
                'output_variables': [],
                'input_variables': ['log_failed_c'],
                'output_values': {},
                'input_values': {'log_failed_c': True},
                'incoming': [],
                'is_initial': False,
            },
        ],
    }
    return automaton, system_capabilities, slugs_specification


def test_strategy_auditor_flags_unexpected_outcome_on_raw_automaton(tmp_path):
    """Raw strategies still enforce activation/outcome protocol strictly."""
    spec_path = _write_auditor_protocol_spec(tmp_path)
    automaton, system_capabilities, slugs_specification = _auditor_protocol_fixture()

    result = StrategyAuditor(timeout_s=0).audit(
        automaton,
        str(spec_path),
        system_capabilities,
        {},
        slugs_specification,
        [],
    )

    assert result['valid'] is False
    assert result['failure_kind'] == PROTOCOL_VIOLATION


def test_strategy_auditor_relaxes_protocol_for_reduced_automaton(tmp_path):
    """Reduced automata merge state input labels, so protocol audit relaxes them."""
    spec_path = _write_auditor_protocol_spec(tmp_path)
    automaton, system_capabilities, slugs_specification = _auditor_protocol_fixture()
    automaton['reduced_automaton'] = True

    result = StrategyAuditor(timeout_s=0).audit(
        automaton,
        str(spec_path),
        system_capabilities,
        {},
        slugs_specification,
        [],
    )

    assert result['valid'] is True
    assert any('reduced automata' in warning for warning in result['warnings'])


# ── SlugsSMReducer ────────────────────────────────────────────────────────────


def _make_automaton_dict(*state_specs):
    """Build a minimal automaton dict from (name, output_valuation, transitions) tuples."""
    states = []
    for name, out_val, transitions in state_specs:
        states.append({
            'name': name,
            'output_valuation': out_val,
            'input_valuation': [],
            'transitions': transitions,
            'rank': 0,
            'output_variables': [],
            'input_variables': [],
            'output_values': {},
            'input_values': {},
            'incoming': [],
        })
    return {'output_variables': [], 'input_variables': [], 'automaton': states}


def test_sm_reducer_empty_automaton_returns_success():
    """An empty automaton reduces to an empty automaton with SUCCESS."""
    automaton_dict, error_code = sm_reducer_main(
        [{'output_variables': [], 'input_variables': [], 'automaton': []}]
    ).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert automaton_dict['automaton'] == []


def test_sm_reducer_removes_unreachable_state():
    """States with no incoming edges (beyond the chosen initial state) are pruned."""
    automaton = _make_automaton_dict(
        ('S0', [0], ['S1']),
        ('S1', [1], []),
        ('S2', [0], []),  # unreachable — no other state transitions here
    )

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    names = {s['name'] for s in result_dict['automaton']}
    assert names == {'S0', 'S1'}
    assert 'S2' not in names


def test_sm_reducer_keeps_first_root_as_initial_state():
    """The first root candidate (no incoming edges) is kept and tagged is_initial=True."""
    automaton = _make_automaton_dict(
        ('S0', [0], ['S1']),
        ('S1', [1], []),
        ('S_root2', [0], []),  # second root — must be pruned, not S0
    )

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    names = {s['name'] for s in result_dict['automaton']}
    assert 'S0' in names
    assert 'S_root2' not in names
    s0 = next(s for s in result_dict['automaton'] if s['name'] == 'S0')
    assert s0['is_initial'] is True
    non_initial = [s for s in result_dict['automaton'] if s['name'] != 'S0']
    assert all(not s['is_initial'] for s in non_initial)


def test_sm_reducer_merges_equivalent_states():
    """Two states with identical output_valuation and transitions are merged into one."""
    automaton = _make_automaton_dict(
        ('S0', [0], ['S1', 'S2']),
        ('S1', [1], []),
        ('S2', [1], []),  # identical to S1
    )

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    names = {s['name'] for s in result_dict['automaton']}
    assert len(names) == 2
    assert 'S0' in names
    # S1 or S2 — one survives
    assert names & {'S1', 'S2'}


def test_sm_reducer_merges_input_variables_from_equivalent_states():
    """Merging equivalent states unions their input_variables lists."""
    automaton = _make_automaton_dict(
        ('S0', [0], ['S1', 'S2']),
        ('S1', [1], []),
        ('S2', [1], []),
    )
    # Give each equivalent state a distinct activation predicate.
    automaton['automaton'][1]['input_variables'] = ['step_a']
    automaton['automaton'][2]['input_variables'] = ['other_a']

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    survivor = next(s for s in result_dict['automaton'] if s['name'] in {'S1', 'S2'})
    assert survivor['input_variables'] == ['other_a', 'step_a']


def test_sm_reducer_merges_states_with_different_input_valuations():
    """
    Merge failure/completion variants with identical outputs and transitions.

    input_valuation is deliberately ignored by equals(): two states that produce the
    same outputs and have the same successors are equivalent for SM generation, even
    when one was reached via 'completed' and the other via 'failure'.  The resulting
    merged state unions their input_variables so get_transitions can later emit the
    correct failure/completion outcomes from a single reduced state.
    """
    automaton = _make_automaton_dict(
        ('S0', [0], ['S1', 'S2']),
        ('S1', [1], []),
        ('S2', [1], []),
    )
    automaton['automaton'][1]['input_valuation'] = 1
    automaton['automaton'][1]['input_variables'] = ['completed']
    automaton['automaton'][2]['input_valuation'] = 2
    automaton['automaton'][2]['input_values'] = {'failure': True}

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    names = {s['name'] for s in result_dict['automaton']}
    # S1 and S2 are equivalent (same output_valuation=1, same transitions=[])
    # so the reducer merges them into one survivor.
    assert len(names) == 2
    assert 'S0' in names


def test_sm_reducer_does_not_merge_states_with_crossed_outcome_routing():
    """
    Two states must not merge just because their successor *names* end up equal.

    P routes completed->A, failure->B. Q routes completed->B, failure->A --
    crossed relative to P. A and B each separately, legitimately absorb one of
    Q's own raw targets (M1 into A, M2 into B), because that collapse is
    exactly what equals() is designed to allow: a leaf state that activates
    the same next capability regardless of which outcome reached it is sound
    to merge. But that means A and B end up reachable via both outcomes, so
    P's and Q's transitions lists can end up equal as plain ordered lists
    (['A', 'B'] == ['A', 'B']) purely as a side effect of M1/M2's names
    sorting the same way A/B's do -- even though P and Q still route those two
    outcomes to opposite targets.

    Comparing raw `.transitions` (as the reducer did before this test was
    added) would merge P and Q here. That is not just an academic risk: had
    it happened, get_transitions would attach both 'completed' and 'failure'
    as conditions to *both* of the merged state's outgoing edges, and
    ConcurrentStateGenerator.add_internal_outcome_and_transition would
    silently drop one of them (it no-ops when an outcome name is already
    registered) -- an FlexBE SM with a transition silently missing or
    misrouted, with no error raised anywhere in the pipeline.

    equals() instead compares outcome_targets, computed once from the
    pristine automaton before any target-side merging could introduce this
    ambiguity, so P and Q must be judged distinct here.
    """
    automaton = _make_automaton_dict(
        ('A', [0, 1, 0], []),
        ('M1', [0, 1, 0], []),   # merges into A: same output, both terminal
        ('B', [0, 0, 1], []),
        ('M2', [0, 0, 1], []),   # merges into B: same output, both terminal
        ('P', [1, 0, 0], ['A', 'B']),
        ('Q', [1, 0, 0], ['M1', 'M2']),
        # Root so P and Q are reachable and survive the unreachable-state
        # pruning phase -- neither has any other incoming edge.
        ('ROOT', [0, 0, 0, 1], ['P', 'Q']),
    )
    automaton['automaton'][0]['input_variables'] = ['completed']  # A
    automaton['automaton'][1]['input_variables'] = ['failure']    # M1: Q's failure target
    automaton['automaton'][2]['input_variables'] = ['failure']    # B
    automaton['automaton'][3]['input_variables'] = ['completed']  # M2: Q's completed target
    automaton['automaton'][4]['input_variables'] = ['branch_p']   # P: ROOT's edge to P
    automaton['automaton'][5]['input_variables'] = ['branch_q']   # Q: ROOT's edge to Q

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    names = {s['name'] for s in result_dict['automaton']}
    # A absorbs M1, B absorbs M2: 7 raw states -> 5 survivors, not 3.
    assert len(names) == 5
    # P and Q must NOT have been merged, despite ending up with the same
    # successor-name set -- their per-outcome routing is opposite.
    assert 'P' in names
    assert 'Q' in names


def test_sm_reducer_merges_states_differing_only_in_pending_bits():
    """
    States that differ only in pending (_p) output bits are merged into one SM state.

    Reproduces the '0_bd' / '1_bd' pattern in the coffee automaton: both states run
    the same capability action but one has the pending flag set (action was activated
    on the previous step) while the other does not.  The pending flag is an on-entry
    artefact with no SM-level meaning; masking it out during equivalence lets the
    reducer collapse the two states into one state with a proper self-loop on failure.

    output_variables layout: [cap@0, act_p]  (bit 0 = capability, bit 1 = pending)
    S0_first: output_valuation=1  (cap bit set, pending bit clear)
    S0_retry: output_valuation=3  (cap bit set, pending bit set)
    Both transition to [S0_retry, S1].
    """
    automaton = _make_automaton_dict(
        ('S0_first', [1], ['S0_retry', 'S1']),
        ('S0_retry', [1, 1], ['S0_retry', 'S1']),
        ('S1', [0, 0], []),
    )
    automaton['output_variables'] = ['cap@0', 'act_p']

    result_dict, error_code = sm_reducer_main([automaton]).process()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    names = {s['name'] for s in result_dict['automaton']}
    # S0_first and S0_retry are equivalent ignoring the pending bit → merged.
    assert len(names) == 2
    assert 'S1' in names
    survivor = next(s for s in result_dict['automaton'] if s['name'] in {'S0_first', 'S0_retry'})
    # Merged state must self-loop (retry) and forward to S1.
    assert set(survivor['transitions']) == {'S1', survivor['name']}


def test_sm_reducer_returns_failure_on_exception(monkeypatch):
    """Caught exceptions during reduction are returned as SM_GENERATION_FAILED."""
    monkeypatch.setattr(
        SlugsAutomaton,
        'from_dict',
        staticmethod(
            lambda d: (_ for _ in ()).throw(ValueError('synthetic failure'))
        ),
    )

    result_dict, error_code = sm_reducer_main(
        [{'output_variables': [], 'input_variables': [], 'automaton': []}]
    ).process()

    assert error_code.value == SynthesisErrorCode.SM_GENERATION_FAILED


def test_sm_reducer_main_binds_inputs():
    """main() factory wires synthesized_automaton from pipeline inputs."""
    automaton = {'output_variables': [], 'input_variables': [], 'automaton': []}
    reducer = sm_reducer_main([automaton])

    assert isinstance(reducer, SlugsSMReducer)
    assert reducer.synthesized_automaton == automaton


def test_sm_reducer_standalone_smoke_uses_in_repo_automaton():
    """The module-level smoke runner should not depend on external demo packages."""
    automaton_dict, error_code = _run_standalone_smoke()

    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert len(automaton_dict['automaton']) == 2
