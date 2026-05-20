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

"""Data structures for representing a slugs-generated finite-state automaton."""


def _copy_sequence_or_value(value):
    """Copy list-like values while preserving scalar valuations."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _valuation_as_int(val):
    """Return output_valuation as an integer regardless of whether it is a list or int."""
    if isinstance(val, (list, tuple)):
        return sum(1 << i for i, b in enumerate(val) if b)
    return val if val is not None else 0


class SlugsAutomaton:
    """Container for Mealy-machine states and input/output variable metadata."""

    def __init__(self, output_variables=None, input_variables=None, states=None):
        self.output_variables = list(output_variables) if output_variables is not None else []
        self.input_variables = list(input_variables) if input_variables is not None else []
        # Single insertion-ordered dict replaces the parallel list + lookup map.
        # Keys are state names; Python 3.7+ dicts preserve insertion order.
        self._states: dict = {}
        if states:
            for state in states:
                self._states[state.name] = state

    @property
    def automaton(self):
        """Ordered list view of all states (read-only; mutate via add_state / pop)."""
        return list(self._states.values())

    def add_state(self, state):
        """Insert or replace a state, keyed by its current name."""
        self._states[state.name] = state

    def reset_states(self):
        """Remove all states."""
        self._states = {}

    @classmethod
    def from_dict(cls, data):
        """Create a `SlugsAutomaton` from plain dictionary data."""
        if isinstance(data, SlugsAutomaton):
            return data
        if not isinstance(data, dict):
            raise TypeError('Slugs automaton data must be a dictionary.')

        states = [
            SlugsAutomatonState.from_dict(state)
            for state in data.get('automaton', [])
        ]
        automaton = cls(
            output_variables=data.get('output_variables', []),
            input_variables=data.get('input_variables', []),
            states=states,
        )
        automaton.update_state_map()
        return automaton

    def to_dict(self):
        """Return a plain dictionary representation safe for YAML serialization."""
        return {
            'output_variables': list(self.output_variables),
            'input_variables': list(self.input_variables),
            'automaton': [state.to_dict() for state in self._states.values()],
        }

    def update_state_map(self):
        """Re-key _states by current name and rebuild incoming-transition lists."""
        self._states = {state.name: state for state in self._states.values()}

        for state in self._states.values():
            state.incoming = []

        for state in self._states.values():
            state.transitions = sorted(set(state.transitions))
            for target_name in state.transitions:
                if target_name not in self._states:
                    raise ValueError(
                        f"Automaton state '{state.name}' has transition to missing "
                        f"target '{target_name}'."
                    )
                self._states[target_name].incoming.append(state.name)

    def __str__(self):
        return (
            f'Automaton with {len(self._states)} states, '
            f'{len(self.input_variables)} inputs, and '
            f'{len(self.output_variables)} outputs.'
        )

    def __getitem__(self, key):
        return self._states.get(key)

    def __iter__(self):
        return iter(self._states)

    def pop(self, key):
        """Remove and return a state by name, or None if not present."""
        return self._states.pop(key, None)

    def size(self):
        """Return number of states in the automaton."""
        return len(self._states)


class SlugsAutomatonState:
    """Single automaton state with valuations, transitions, and derived variables."""

    def __init__(
        self,
        name,
        output_valuation=None,
        input_valuation=None,
        transitions=None,
        rank=0,
    ):
        self.name = name
        self.output_valuation = _copy_sequence_or_value(output_valuation)
        self.input_valuation = _copy_sequence_or_value(input_valuation)
        self.transitions = list(transitions) if transitions is not None else []
        self.rank = rank

        self.output_variables = []
        self.input_variables = []
        self.output_values = {}
        self.input_values = {}
        self.incoming = []
        self.is_initial = False

    @classmethod
    def from_dict(cls, data):
        """Create a `SlugsAutomatonState` from plain dictionary data."""
        if isinstance(data, SlugsAutomatonState):
            return data
        if not isinstance(data, dict):
            raise TypeError('Slugs automaton state data must be a dictionary.')

        state = cls(
            name=str(data['name']),
            output_valuation=data.get('output_valuation', []),
            input_valuation=data.get('input_valuation', []),
            transitions=data.get('transitions', []),
            rank=data.get('rank', 0),
        )
        state.output_variables = list(data.get('output_variables', []))
        state.input_variables = list(data.get('input_variables', []))
        state.output_values = dict(data.get('output_values', {}))
        state.input_values = dict(data.get('input_values', {}))
        state.incoming = list(data.get('incoming', []))
        state.is_initial = bool(data.get('is_initial', False))
        return state

    def to_dict(self):
        """Return a plain dictionary representation safe for YAML serialization."""
        return {
            'name': self.name,
            'output_valuation': _copy_sequence_or_value(self.output_valuation),
            'input_valuation': _copy_sequence_or_value(self.input_valuation),
            'transitions': list(self.transitions),
            'rank': self.rank,
            'output_variables': list(self.output_variables),
            'input_variables': list(self.input_variables),
            'output_values': dict(self.output_values),
            'input_values': dict(self.input_values),
            'incoming': list(self.incoming),
            'is_initial': self.is_initial,
        }

    def equals(self, other, pending_mask=0, verbose=False):
        """
        Return True when output valuation and transitions are equivalent.

        input_valuation is intentionally ignored: states reachable from different
        environment conditions but producing the same outputs and successors are
        equivalent for SM generation purposes.

        pending_mask is a bitmask of output-variable positions that carry pending
        flags (variables whose name ends in ``_p``).  These bits are masked out
        before comparing output_valuation so that states differing only in whether
        an action was "just activated" vs "already pending" are treated as the same
        SM state — the pending flag is set on entry and has no SM-level significance.
        """
        if not isinstance(other, SlugsAutomatonState):
            if other is not None:
                print(f'    other is not a SlugsAutomatonState! ({type(other)}')
            return False

        mask = ~pending_mask
        if (_valuation_as_int(self.output_valuation) & mask) != (
            _valuation_as_int(other.output_valuation) & mask
        ):
            return False

        if self.transitions != other.transitions:
            return False

        if verbose and self.input_valuation != other.input_valuation:
            print(
                f'    Input valuation differs (expected for equivalent states): '
                f"'{self.name}' ({self.input_valuation}) vs "
                f"'{other.name}' ({other.input_valuation})"
            )

        if verbose:
            print(
                f"    SlugsAutomatonState '{self.name}' and '{other.name}' are equivalent!",
                flush=True,
            )
        return True

    def update_variables(
        self,
        binary_input_variables,
        input_variables,
        binary_output_variables,
        output_variables,
        activation_tag,
        outcome_tags,
        outcome_names,
        sm_outcomes,
        verbose=False,
    ):
        """Populate variable/value caches from raw bit-vector valuations."""
        if not isinstance(self.input_valuation, list):
            raise RuntimeError(
                f"update_variables called on already-processed state '{self.name}'"
            )
        try:
            for ap in binary_input_variables:
                self.input_values[ap] = binary_input_variables[ap][0]

            for ap in binary_output_variables:
                self.output_values[ap] = binary_output_variables[ap][0]
        except IndexError as exc:
            print(
                f' index error processing binary variables {exc}\n'
                f'   lengths: inputs={len(binary_input_variables)}\n'
                f'            outputs={len(binary_output_variables)}\n'
            )
            raise exc

        try:
            value = 0
            for index, val in enumerate(self.input_valuation):
                if val:
                    value += 1 << index
                    var = input_variables[index]
                    if '@' in var:
                        ap, bit = var.split('@')
                        self.input_values[ap] += 1 << int(bit)
                    elif var in outcome_names:
                        if verbose:
                            print(f"  '{var}' is generic input variable (outcome)")
                        self.input_variables.append(var)
                    elif len(var) < 3 or var[-2:] not in outcome_tags:
                        if verbose:
                            print(f"  '{var}' is sensor variable")
                        self.input_values[var] = True
                    else:
                        if verbose:
                            print(f"  '{var}' is input variable (outcome of prior activation)")
                        self.input_variables.append(var)

            self.input_valuation = value
        except IndexError as exc:
            print(
                f' index error processing inputs {exc}: {index} {val}\n'
                f'   lengths: valuation={len(self.input_valuation)}\n'
                f'            variables={len(input_variables)}\n'
                f'   {input_variables}'
            )
            raise exc

        try:
            value = 0
            for index, val in enumerate(self.output_valuation):
                if val:
                    value += 1 << index
                    var = output_variables[index]
                    if '@' in var:
                        ap, bit = var.split('@')
                        self.output_values[ap] += 1 << int(bit)
                    elif var in sm_outcomes:
                        if verbose:
                            print(f"  '{var}' is sm outcome variable")
                        self.output_variables.append(var)
                    elif len(var) < 3 or var[-2:] != activation_tag:
                        if verbose:
                            print(f"  '{var}' is output variable")
                        self.output_values[var] = True
                    else:
                        if verbose:
                            print(f"  '{var}' is activation variable")
                        self.output_variables.append(var)

            self.output_valuation = value
        except IndexError as exc:
            print(
                f' index error processing outputs {exc} {index} {val}\n'
                f'   lengths: valuation={len(self.output_valuation)}\n'
                f'            variables={len(output_variables)}\n'
                f'   {output_variables}\n'
            )
            raise exc

    def __str__(self):
        def int_to_bits(val):
            bits = []
            if val == 0:
                return bits
            while val:
                bits.append(val & 1)
                val >>= 1
            return bits

        return (
            f"  - state '{self.name}' (rank={self.rank}) :\n"
            f'      out: {self.output_valuation} '
            f'{int_to_bits(self.output_valuation)}\n'
            f'      out vars: {self.output_variables}\n'
            f'      out vals: {self.output_values}\n'
            f'      in : {self.input_valuation} '
            f'{int_to_bits(self.input_valuation)}\n'
            f'      in vars: {self.input_variables}\n'
            f'      in vals: {self.input_values}\n'
            f'      trans to: {self.transitions}\n'
            f'      incoming: {self.incoming}'
        )
