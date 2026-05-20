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

"""Useful functions for state machine generation."""

from collections.abc import Set

from flexbe_msgs.msg import StateInstantiation


def remove_duplicate_pairs(lst1, lst2):
    """Remove duplicate element-pairs from two aligned lists."""
    if len(lst1) == 0:
        return [], []
    pairs = zip(lst1, lst2)
    pairs = sorted(set(pairs))
    new_lists = zip(*pairs)
    lists_to_return = list(new_lists)
    return lists_to_return[0], lists_to_return[1]


def _message_sequence(values):
    """Return a ROS message sequence without passing deprecated set values."""
    if isinstance(values, Set):
        return sorted(values)
    return list(values)


def new_si(state_path, state_class, behavior_class, outcomes, transitions, initial_state,
           parameters, autonomy=None,
           userdata_keys=None, userdata_remapping=None, verbose=False):
    """Create a new `StateInstantiation` object."""
    si = StateInstantiation()
    si.state_path = state_path
    si.state_class = state_class
    si.behavior_class = behavior_class
    if len(transitions) > 0:  # it's not the top level SM
        if isinstance(outcomes, Set) or isinstance(transitions, Set):
            raise TypeError(
                f"'{state_path}' outcomes and transitions must be ordered sequences "
                'when transitions are provided.'
            )
        outcomes, transitions = remove_duplicate_pairs(outcomes, transitions)
    si.outcomes = _message_sequence(outcomes)
    si.transitions = _message_sequence(transitions)
    if initial_state is not None:
        si.initial_state_name = initial_state
    si.parameter_names = list(parameters)
    si.parameter_values = []
    for key in si.parameter_names:
        if key.startswith('@'):
            raise ValueError(
                f'"{state_path}" parameter name "{key}" is invalid. '
                'Use @ only in parameter values to reference automaton '
                'input/output values.'
            )

        if verbose:
            print(f" '{state_path}' - parameter name '{key}' value=<{parameters[key]}>!")
        si.parameter_values.append(parameters[key])
    si.autonomy = autonomy if autonomy is not None else []
    si.userdata_keys = userdata_keys if userdata_keys is not None else []
    si.userdata_remapping = userdata_remapping if userdata_remapping is not None else []
    return si


def clean_variable(var):
    """Remove the `_*` suffix when present."""
    if len(var) >= 2 and var[-2] == '_':
        return var[:-2]
    return var
