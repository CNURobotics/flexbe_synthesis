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

"""Reduce synthesized Slugs automata by pruning and merging equivalent states."""

import traceback

from flexbe_synthesis_core.base_process import BaseProcess
from flexbe_synthesis_msgs.msg import SynthesisErrorCode
from flexbe_synthesis_slugs.helpers.slugs_automaton import SlugsAutomaton


class SlugsSMReducer(BaseProcess):
    """Pipeline process that simplifies an automaton in-place."""

    synthesized_automaton: dict

    def process(self):
        """Reduce the automaton and return `[automaton_dict, error_code]`."""
        try:
            sa = SlugsAutomaton.from_dict(self.synthesized_automaton)
            print(f'Starting with {sa} ...', flush=True)

            # Identify the initial state before pruning.
            # Honor the synthesizer's is_initial tag; fall back to the lowest-rank
            # zero-incoming candidate so selection is deterministic regardless of
            # the order states appear in the automaton dict.
            pre_tagged = [sa[n] for n in sa if sa[n].is_initial and not sa[n].incoming]
            if pre_tagged:
                initial = min(pre_tagged, key=lambda s: s.rank)
                initial.incoming.append('/')  # sentinel: protect from the pruning loop
                if self.verbose:
                    print(
                        f"    Keeping pre-tagged initial state '{initial.name}'.",
                        flush=True,
                    )
            else:
                candidates = sorted(
                    (sa[n] for n in sa if not sa[n].incoming),
                    key=lambda s: s.rank,
                )
                if candidates:
                    initial = candidates[0]
                    initial.is_initial = True
                    initial.incoming.append('/')  # sentinel
                    print(
                        f'Warning: no pre-tagged initial state; '
                        f"selecting '{initial.name}' by rank.",
                        flush=True,
                    )

            # Remove states with no incoming edges (unreachable roots).
            # The initial state is protected by its sentinel incoming entry.
            removed_one = True
            count = 0
            while removed_one and sa.size() > 0:
                removed_one = False
                if self.verbose:
                    print(
                        '    Removing unreachable states with no incoming transitions '
                        f'(count {count}) ... ',
                        flush=True,
                    )
                count += 1

                state_keys = list(sa)
                for idx, name in enumerate(state_keys):
                    state = sa[name]
                    if len(state.incoming) != 0:
                        continue

                    if self.verbose:
                        print(
                            f"    Removing {idx} '{state.name}' with zero incoming connections.",
                            flush=True,
                        )
                    for out_name in state.transitions:
                        next_state = sa[out_name]
                        if next_state is None:
                            print(
                                f"\033[31mFailed to remove '{state.name}' with "
                                'zero incoming transitions\033[0m',
                                flush=True,
                            )
                            print(
                                f"\033[31m   Unknown transition to '{out_name}'\033[0m",
                                flush=True,
                            )
                            raise IndexError(
                                f"Failed to remove '{state.name}' with transition to '{out_name}'"
                            )
                        next_state.incoming.remove(state.name)

                    removed_state = sa.pop(state.name)
                    if removed_state is not state:
                        raise ValueError(
                            f"Removed wrong state instance for '{state.name}'."
                        )
                    removed_one = True

            sa.update_state_map()
            print('Now process automaton and identify identical states ...', flush=True)

            # Pending bits (_p suffix) track "action was activated this step" — they are
            # set on entry to an action and carry no SM-level meaning.  Mask them out so
            # states that differ only in whether an action is "just activated" vs "already
            # pending" are treated as equivalent and merged into one SM state.
            pending_mask = 0
            for bit_index, var in enumerate(sa.output_variables):
                if var.endswith('_p'):
                    pending_mask |= 1 << bit_index
            if self.verbose and pending_mask:
                print(
                    f'    Pending-bit mask for equivalence: 0x{pending_mask:x} '
                    f'({[v for v in sa.output_variables if v.endswith("_p")]})',
                    flush=True,
                )

            state_keys = list(sa)
            for idx, name in enumerate(state_keys):
                state = sa[name]
                if state is None:
                    if self.verbose:
                        print(
                            f"    Already removed '{name}' from this automaton ...", flush=True
                        )
                    continue

                if self.verbose:
                    print(f"    Checking '{state.name}' for equivalents ...", flush=True)
                for idx2 in range(idx + 1, len(state_keys)):
                    other_name = state_keys[idx2]
                    state2 = sa[other_name]
                    if state2 is None or not state.equals(state2, pending_mask,
                                                          verbose=self.verbose):
                        continue

                    if self.verbose:
                        print(
                            f"    Removing equivalent state {idx2} '{state2.name}' to '{state.name}'",
                            flush=True,
                        )

                    for incoming_name in state2.incoming:
                        state3 = sa[incoming_name]
                        if state3 is None:
                            print(
                                f"\033[31mFailed to remove '{state2.name}' equal "
                                f"to '{state.name}'\033[0m",
                                flush=True,
                            )
                            print(
                                f"\033[31m   Unknown transition from '{incoming_name}'\033[0m",
                                flush=True,
                            )
                            raise IndexError(
                                f"Failed to remove '{state2.name}' equal to '{state.name}'"
                            )

                        for idx3, trans in enumerate(state3.transitions):
                            if trans != state2.name:
                                continue
                            if self.verbose:
                                print(
                                    f"        Updating '{state3.name}' transition {idx3} "
                                    f"({state3.transitions[idx3]}) with '{state.name}'",
                                    flush=True,
                                )
                            state3.transitions[idx3] = state.name
                            if state3.name not in state.incoming:
                                if self.verbose:
                                    print(
                                        f"    Adding '{state3.name}' to incoming list "
                                        f"for '{state.name}'",
                                        flush=True,
                                    )
                                state.incoming.append(state3.name)

                    for idx3, out_name in enumerate(state2.transitions):
                        if state.transitions[idx3] != out_name:
                            raise ValueError(
                                f"Mismatch on transitions for '{state.name}' "
                                f"and '{state2.name}'"
                            )
                        state3 = sa[out_name]
                        if state3 is None:
                            print(
                                f"\033[31mFailed to remove '{state2.name}' equal "
                                f"to '{state.name}'\033[0m",
                                flush=True,
                            )
                            print(
                                f"\033[31m   Unknown transition to '{out_name}'\033[0m",
                                flush=True,
                            )
                            raise IndexError(
                                f"Failed to remove '{state2.name}' equal to '{state.name}'"
                            )

                        for idx4, trans in enumerate(state3.incoming):
                            if trans == state2.name:
                                if self.verbose:
                                    print(
                                        f"        Updating '{state3.name}' incoming "
                                        f"[{idx4}] ({state3.incoming[idx4]}) with '{state.name}'",
                                        flush=True,
                                    )
                                state3.incoming[idx4] = state.name

                    # Preserve all activation predicates carried by equivalent states.
                    state.input_variables = sorted(
                        set(state.input_variables + state2.input_variables)
                    )
                    if state2.is_initial:
                        state.is_initial = True

                    removed_state = sa.pop(state2.name)
                    if removed_state is not state2:
                        raise ValueError(
                            f"Removed wrong state instance for '{state2.name}'."
                        )

            sa.update_state_map()
            print(f'Ending with reduced {sa} ...', flush=True)
            return [sa.to_dict(), SynthesisErrorCode(value=SynthesisErrorCode.SUCCESS)]

        except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError) as exc:
            print(f'slugs_sm_generation Error: {exc}', flush=True)
            traceback.print_exc()
            return [
                SlugsAutomaton().to_dict(),
                SynthesisErrorCode(value=SynthesisErrorCode.SM_GENERATION_FAILED),
            ]


def main(inputs):
    """Create process instance for pipeline usage."""
    return SlugsSMReducer(
        name='SlugsSMReducer',
        synthesized_automaton=inputs[0],
    )


def _standalone_smoke_automaton():
    """Return a tiny in-repo automaton for manual reducer smoke tests."""
    return {
        'output_variables': ['step_a'],
        'input_variables': ['completed', 'failure'],
        'automaton': [
            {
                'name': 'S0',
                'output_valuation': [1],
                'input_valuation': [0, 0],
                'transitions': ['S1', 'S2'],
                'rank': 0,
                'output_variables': ['step_a'],
                'input_variables': [],
                'output_values': {'step_a': True},
                'input_values': {},
                'incoming': [],
                'is_initial': True,
            },
            {
                'name': 'S1',
                'output_valuation': [0],
                'input_valuation': [1, 0],
                'transitions': [],
                'rank': 1,
                'output_variables': [],
                'input_variables': ['completed'],
                'output_values': {},
                'input_values': {'completed': True},
                'incoming': [],
                'is_initial': False,
            },
            {
                'name': 'S2',
                'output_valuation': [0],
                'input_valuation': [0, 1],
                'transitions': [],
                'rank': 2,
                'output_variables': [],
                'input_variables': ['failure'],
                'output_values': {},
                'input_values': {'failure': True},
                'incoming': [],
                'is_initial': False,
            },
        ],
    }


def _run_standalone_smoke():
    """Run a reducer smoke test without depending on external demo packages."""
    automaton = _standalone_smoke_automaton()
    print(f"{len(automaton['automaton'])} states in smoke-test automaton")
    automaton2, code = main([automaton]).process()
    print(f"{len(automaton2['automaton'])} states in reduced automaton")
    print(code)
    return automaton2, code


if __name__ == '__main__':  # pragma: no cover
    _run_standalone_smoke()
