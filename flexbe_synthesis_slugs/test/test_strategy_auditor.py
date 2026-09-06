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

"""Unit tests for the StrategyAuditor process."""

from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers import strategy_auditor as auditor_helper
from flexbe_synthesis_slugs.processes.strategy_auditor import main as auditor_main


def _write_slugsin(tmp_path):
    spec_path = tmp_path / 'demo.slugsin'
    spec_path.write_text(
        """\
[INPUT]
step_c
step_f
[OUTPUT]
step_a
finished
[SYS_LIVENESS]
finished
""",
        encoding='utf-8',
    )
    return spec_path


def _state(name, outputs=None, inputs=None, transitions=None, initial=False):
    return {
        'name': name,
        'output_valuation': [],
        'input_valuation': [],
        'transitions': transitions or [],
        'rank': 0,
        'output_variables': outputs or [],
        'input_variables': inputs or [],
        'output_values': {var: True for var in outputs or []},
        'input_values': {var: True for var in inputs or []},
        'incoming': [],
        'is_initial': initial,
    }


def _automaton(*states):
    return {
        'output_variables': ['step_a', 'finished'],
        'input_variables': ['step_c', 'step_f'],
        'automaton': list(states),
    }


def _parsed_state(
    name,
    capability,
    outputs=None,
    inputs=None,
    transitions=None,
    initial=False,
):
    state = _state(
        name,
        outputs=outputs,
        inputs=inputs,
        transitions=transitions,
        initial=initial,
    )
    state['output_values']['capability'] = capability
    return state


def _parsed_automaton(*states):
    return {
        'output_variables': ['capability@0', 'capability@1', 'finished'],
        'input_variables': ['completed', 'failure'],
        'automaton': list(states),
    }


def _system_capabilities():
    return {
        'transition_outcomes': ['completed', 'failure'],
        'sm_outcome_mappings': {'finished': 'finished'},
        'capabilities': {
            'step': {
                'state': {
                    'outcomes': {
                        'done': {'remapping': 'completed'},
                        'failed': {'remapping': 'failure'},
                    },
                },
            },
        },
    }


def _bounded_system_capabilities(limit):
    data = _system_capabilities()
    data['capabilities']['step']['max_consecutive_failures'] = limit
    return data


def _two_capability_system_capabilities():
    data = _system_capabilities()
    data['capabilities']['other'] = {
        'state': {
            'outcomes': {
                'done': {'remapping': 'completed'},
            },
        },
    }
    return data


def _bounded_two_capability_system_capabilities(limit):
    data = _two_capability_system_capabilities()
    data['capabilities']['step']['max_consecutive_failures'] = limit
    return data


def _state_mappings():
    return {
        'transition_outcomes': ['completed', 'failure'],
        'sm_outcome_mappings': {'finished': 'finished'},
    }


def _run(tmp_path, automaton, timeout_s=5.0, goal_outcomes=None):
    spec_path = _write_slugsin(tmp_path)
    return _run_with_system(tmp_path, automaton, _system_capabilities(), spec_path,
                            timeout_s, goal_outcomes=goal_outcomes)


def _run_with_system(
    tmp_path,
    automaton,
    system_capabilities,
    spec_path,
    timeout_s=5.0,
    goal_outcomes=None,
):
    slugs_specification = {
        'env_trans': ["step_a -> step_c'", "!step_a -> !step_c'"],
        'sys_liveness': ['finished'],
    }
    return _run_with_spec(
        tmp_path,
        automaton,
        system_capabilities,
        spec_path,
        slugs_specification,
        timeout_s,
        goal_outcomes=goal_outcomes,
    )


def _run_with_spec(
    tmp_path,
    automaton,
    system_capabilities,
    spec_path,
    slugs_specification,
    timeout_s=5.0,
    goal_outcomes=None,
):
    return auditor_main([
        automaton,
        str(tmp_path),
        'demo',
        system_capabilities,
        _state_mappings(),
        slugs_specification,
        str(spec_path),
        goal_outcomes or [],
        timeout_s,
    ]).process()


def test_strategy_auditor_accepts_reaching_goal_after_declared_outcome(tmp_path):
    """Activation followed by declared outcome and goal should pass."""
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['finished'], inputs=['step_c'], transitions=['S2']),
        _state('S2', outputs=['finished'], transitions=['S2']),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_rejects_missing_outcome_after_activation(tmp_path):
    """A capability activation must observe a declared outcome on the next step."""
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['finished'], transitions=['S1']),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.PROTOCOL_VIOLATION
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_rejects_multiple_outcomes_after_activation(tmp_path):
    """Multiple declared outcomes after one activation are protocol failures."""
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state(
            'S1',
            outputs=['finished'],
            inputs=['step_c', 'step_f'],
            transitions=['S1'],
        ),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.PROTOCOL_VIOLATION
    assert 'multiple outcomes' in result['message']
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_rejects_unreachable_goal(tmp_path):
    """Reachable strategies with no goal outcome should fail goal reachability."""
    automaton = _automaton(
        _state('S0', transitions=['S0'], initial=True),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.GOAL_UNREACHABLE
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_timeout_is_incomplete_non_fatal(tmp_path, monkeypatch):
    """Timeouts report a distinct non-fatal status rather than SUCCESS or a violation."""
    automaton = _automaton(
        _state('S0', transitions=['S0'], initial=True),
    )

    def _timeout(_self):
        raise auditor_helper.AuditTimeout()

    monkeypatch.setattr(auditor_helper.StrategyAuditor, '_check_timeout', _timeout)

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is True
    assert result['incomplete'] is True
    assert error_code.value == SynthesisErrorCode.AUDIT_INCOMPLETE


def test_strategy_auditor_rejects_goal_free_reachable_cycle(tmp_path):
    """A reachable non-goal SCC is a trap even when another path reaches the goal."""
    automaton = _automaton(
        _state('S0', transitions=['S1', 'S2'], initial=True),
        _state('S1', transitions=['S1']),
        _state('S2', outputs=['finished'], transitions=['S2']),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.GOAL_UNREACHABLE_TRAP
    assert result['bad_scc_states'] == ['S1']
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_allows_cycle_that_can_reach_goal(tmp_path):
    """A cyclic SCC with an exit path to a goal is not a goal-unreachable trap."""
    automaton = _automaton(
        _state('S0', transitions=['S1'], initial=True),
        _state('S1', transitions=['S1', 'S2']),
        _state('S2', outputs=['finished'], transitions=['S2']),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_rejects_cycle_that_only_visits_goal_once(tmp_path):
    """A single non-recurring visit to the goal does not clear a cyclic SCC.

    S1 can reach the goal state S2, but S2 is visited at most once (it is not
    itself cyclic and has no path back to S1) before the execution is forced
    into S3, an absorbing non-goal cycle. Reaching the goal once is not the
    same as the goal recurring, so S1 must still be flagged as a goal-unreachable trap:
    every execution from S1 either loops in S1 forever without ever reaching
    the goal, or visits the goal exactly once via S2 and then is permanently
    stuck in S3. Seeding backward reachability from every goal-containing
    component regardless of cyclicity (rather than only cyclic ones) would
    under-report this case if S1 had no other reachable trap to be caught by;
    empirically, for this specific shape, the exhaustive per-SCC scan still
    finds S3 either way, so this test locks in the corrected reasoning as a
    property of the check rather than as an old/new differential.
    """
    automaton = _automaton(
        _state('S0', transitions=['S1'], initial=True),
        _state('S1', transitions=['S1', 'S2']),
        _state('S2', outputs=['finished'], transitions=['S3']),
        _state('S3', transitions=['S3']),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.GOAL_UNREACHABLE_TRAP
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_allows_cycle_that_can_reach_input_side_goal(tmp_path):
    """goal_outcomes may name an environment input, not just a system output.

    Some examples (e.g. coffee) have no sm_outcome_mappings and are designed to
    cycle forever; their only observable progress signal is an environment-reported
    completion input rather than a system-asserted SM outcome.
    """
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['step_a'], inputs=['step_c'], transitions=['S1', 'S2']),
        _state('S2', outputs=['step_a'], inputs=['step_c'], transitions=['S2']),
    )

    result, error_code = _run(tmp_path, automaton, goal_outcomes=['step_c'])

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_rejects_goal_free_cycle_with_input_side_goal(tmp_path):
    """A reachable non-goal SCC is still a goal-unreachable trap when the goal is input-side."""
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1', 'S2'], initial=True),
        _state('S1', outputs=['step_a'], inputs=['step_f'], transitions=['S1']),
        _state('S2', outputs=['step_a'], inputs=['step_c'], transitions=['S2']),
    )

    result, error_code = _run(tmp_path, automaton, goal_outcomes=['step_c'])

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.GOAL_UNREACHABLE_TRAP
    assert result['bad_scc_states'] == ['S1']
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_rejects_bounded_failure_violation(tmp_path):
    """Capability failure counters are tracked per attempt."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['step_a'], inputs=['step_f'], transitions=['S2']),
        _state('S2', outputs=['step_a'], inputs=['step_f'], transitions=['S3']),
        _state('S3', outputs=['finished'], inputs=['step_f'], transitions=['S3']),
    )

    result, error_code = _run_with_system(
        tmp_path,
        automaton,
        _bounded_system_capabilities(limit=1),
        spec_path,
    )

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.BOUNDED_FAILURE_VIOLATION
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_allows_bounded_failure_at_limit(tmp_path):
    """Exactly the configured number of consecutive failures is still valid."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['step_a'], inputs=['step_f'], transitions=['S2']),
        _state('S2', outputs=['finished'], inputs=['step_c'], transitions=['S3']),
        _state('S3', outputs=['finished'], transitions=['S3']),
    )

    result, error_code = _run_with_system(
        tmp_path,
        automaton,
        _bounded_system_capabilities(limit=1),
        spec_path,
    )

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_resets_failure_streak_on_interrupting_capability(tmp_path):
    """Failures separated by an unrelated capability's episode are not consecutive.

    `step` fails, then `other` is activated and succeeds, then `step` is
    activated again and fails a second time. With max_consecutive_failures=1,
    this must NOT trip a violation: the two `step` failures are separated by
    `other`'s entire activation-to-resolution episode, so `step`'s streak was
    broken and restarted, not continued.
    """
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['other_a'], inputs=['step_f'], transitions=['S2']),
        _state('S2', outputs=['step_a'], inputs=['other_c'], transitions=['S3']),
        _state('S3', outputs=['finished'], inputs=['step_f'], transitions=['S4']),
        _state('S4', outputs=['finished'], transitions=['S4']),
    )

    result, error_code = _run_with_system(
        tmp_path,
        automaton,
        _bounded_two_capability_system_capabilities(limit=1),
        spec_path,
    )

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_reports_invalid_transition(tmp_path):
    """Transitions to missing strategy states get their own failure kind."""
    automaton = _automaton(
        _state('S0', transitions=['missing'], initial=True),
    )

    result, error_code = _run(tmp_path, automaton)

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.INVALID_TRANSITION
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_rejects_multiple_simultaneous_activations(tmp_path):
    """A single product monitor state cannot track two new activations."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state(
            'S0',
            outputs=['step_a', 'other_a'],
            transitions=['S1'],
            initial=True,
        ),
        _state('S1', outputs=['finished'], transitions=['S1']),
    )

    result, error_code = _run_with_system(
        tmp_path,
        automaton,
        _two_capability_system_capabilities(),
        spec_path,
    )

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.PROTOCOL_VIOLATION
    assert 'multiple capabilities' in result['message']
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_rejects_wrong_capability_outcome_on_goal(tmp_path):
    """Terminal SM outcomes do not exempt capability-protocol violations."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['finished'], inputs=['other_c'], transitions=['S1']),
    )

    result, error_code = _run_with_system(
        tmp_path,
        automaton,
        _two_capability_system_capabilities(),
        spec_path,
    )

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.PROTOCOL_VIOLATION
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_skips_protocol_without_immediate_outcome_rules(tmp_path):
    """Full specs may allow activated states without unconditional next outcomes."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state('S0', outputs=['step_a'], transitions=['S1'], initial=True),
        _state('S1', outputs=['finished'], transitions=['S1']),
    )

    result, error_code = _run_with_spec(
        tmp_path,
        automaton,
        _system_capabilities(),
        spec_path,
        {'env_trans': ["step_c' <-> request' & step_a"], 'sys_liveness': ['finished']},
    )

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_process_surfaces_warnings(tmp_path):
    """Warnings returned in the result are also exposed on BaseProcess.messages."""
    spec_path = tmp_path / 'demo.slugsin'
    spec_path.write_text(
        """\
[OUTPUT]
step_a
finished
[SYS_LIVENESS]
finished
""",
        encoding='utf-8',
    )
    automaton = _automaton(
        _state('S0', outputs=['finished'], transitions=['S0'], initial=True),
    )
    process = auditor_main([
        automaton,
        str(tmp_path),
        'demo',
        _system_capabilities(),
        _state_mappings(),
        {'env_trans': [], 'sys_liveness': ['finished']},
        str(spec_path),
        [],
        5.0,
    ])

    result, error_code = process.process()

    assert result['valid'] is True
    assert error_code.value == SynthesisErrorCode.SUCCESS
    assert any('no [INPUT]' in warning for warning in process.messages)


def test_strategy_auditor_keeps_protocol_relaxation_warnings_terminal_only(
        tmp_path, capsys, monkeypatch):
    """Expected protocol-relaxation notices do not enter pipeline results."""
    process = auditor_main([
        {},
        str(tmp_path),
        'demo',
        {},
        {},
        {},
        '',
        [],
        5.0,
    ])
    warnings = [
        'Protocol enforcement disabled: reduced automata store merged state '
        'input labels, not concrete per-edge outcome observations.',
        'Protocol enforcement disabled: automaton/spec shape does not expose '
        'strict one-step activation/outcome semantics.',
        'A warning that should reach the pipeline.',
    ]
    monkeypatch.setattr(
        auditor_helper.StrategyAuditor,
        'audit',
        lambda *args, **kwargs: {
            **auditor_helper.empty_result(),
            'warnings': warnings,
        },
    )

    result, error_code = process.process()

    terminal = capsys.readouterr().out
    assert warnings[0] in terminal
    assert warnings[1] in terminal
    assert result['warnings'] == [warnings[2]]
    assert process.messages == [warnings[2]]
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_treats_liveness_disjunction_as_goals(tmp_path):
    """Simple sys-liveness disjunctions expose each named SM outcome as a goal."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _automaton(
        _state('S0', transitions=['S1'], initial=True),
        _state('S1', outputs=['failed'], transitions=['S1']),
    )
    automaton['output_variables'].append('failed')
    system_capabilities = _system_capabilities()
    system_capabilities['sm_outcome_mappings'] = {}

    result, error_code = _run_with_spec(
        tmp_path,
        automaton,
        system_capabilities,
        spec_path,
        {
            'env_trans': [],
            'sys_props': {'finished', 'failed', 'step_a'},
            'sys_liveness': ['(finished | failed)'],
        },
    )

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_enforces_protocol_for_parsed_activation(tmp_path):
    """Parsed `capability=N` activation is normalized to capability names."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _parsed_automaton(
        _parsed_state('S0', 0, transitions=['S1'], initial=True),
        _parsed_state('S1', 1, transitions=['S2']),
        _parsed_state('S2', 1, inputs=['completed'], outputs=['finished'],
                      transitions=['S2']),
    )

    result, error_code = _run_with_spec(
        tmp_path,
        automaton,
        _system_capabilities(),
        spec_path,
        {
            'env_trans': ["(capability=1) -> completed'"],
            'sys_props': {
                'capability:0...1',
                'item:0...3',
                '# 0: null',
                '# 1: step',
                'finished',
            },
            'sys_liveness': ['finished'],
        },
    )

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_maps_parsed_generic_success_to_concrete_goal(tmp_path):
    """A generic parsed completion should satisfy its capability-specific goal."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _parsed_automaton(
        _parsed_state('S0', 0, transitions=['S1'], initial=True),
        _parsed_state('S1', 1, transitions=['S2']),
        _parsed_state('S2', 1, inputs=['completed'], transitions=['S2']),
    )

    result, error_code = _run_with_spec(
        tmp_path,
        automaton,
        _system_capabilities(),
        spec_path,
        {
            'env_trans': ["(capability=1) -> completed'"],
            'sys_props': {
                'capability:0...1',
                '# 0: null',
                '# 1: step',
            },
            'sys_liveness': [],
        },
        goal_outcomes=['step_c'],
    )

    assert result['valid'] is True
    assert result['failure_kinds'] == []
    assert error_code.value == SynthesisErrorCode.SUCCESS


def test_strategy_auditor_rejects_missing_outcome_for_parsed_activation(tmp_path):
    """Parsed activation still must produce a declared outcome when checkable."""
    spec_path = _write_slugsin(tmp_path)
    automaton = _parsed_automaton(
        _parsed_state('S0', 0, transitions=['S1'], initial=True),
        _parsed_state('S1', 1, transitions=['S2']),
        _parsed_state('S2', 1, outputs=['finished'], transitions=['S2']),
    )

    result, error_code = _run_with_spec(
        tmp_path,
        automaton,
        _system_capabilities(),
        spec_path,
        {
            'env_trans': ["(capability=1) -> completed'"],
            'sys_props': {'capability:0...1', '# 0: null', '# 1: step', 'finished'},
            'sys_liveness': ['finished'],
        },
    )

    assert result['valid'] is False
    assert result['failure_kind'] == auditor_helper.PROTOCOL_VIOLATION
    assert error_code.value == SynthesisErrorCode.AUTOMATON_INVALID


def test_strategy_auditor_allows_generic_outcome_before_first_activation_parsed(tmp_path):
    """A generic parsed outcome observed while leaving the null start state is inert.

    Parsed/enumerated specs only constrain the generic outcome props relative
    to the *current* real capability (`(capability=i) -> completed'` for
    i >= 1); nothing constrains them out of the null start state
    (`capability=0`), so Slugs can legally branch on an env-asserted outcome
    there before any real capability has ever run. This mirrors a real Coffee
    strategy (enumerated encoding, Fair-Outcome liveness) where the state
    leaving the null start observed `failure` despite nothing pending -- a
    harmless don't-care branch, not a protocol violation.
    """
    spec_path = _write_slugsin(tmp_path)
    automaton = _parsed_automaton(
        _parsed_state('S0', 0, transitions=['S1'], initial=True),
        _parsed_state('S1', 1, inputs=['completed'], outputs=['finished'],
                      transitions=['S1']),
    )

    result, error_code = _run_with_spec(
        tmp_path,
        automaton,
        _system_capabilities(),
        spec_path,
        {
            'env_trans': ["(capability=1) -> completed'"],
            'sys_props': {'capability:0...1', '# 0: null', '# 1: step', 'finished'},
            'sys_liveness': ['finished'],
        },
    )

    assert result['valid'] is True
    assert error_code.value == SynthesisErrorCode.SUCCESS
