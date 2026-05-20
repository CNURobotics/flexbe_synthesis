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

"""Tests for compact Slugs integer variable expansion."""

from flexbe_synthesis_slugs.helpers.binary_variables import expand_binary_variables
from flexbe_synthesis_slugs.helpers.slugs_automaton_checker import SlugsAutomatonChecker
from flexbe_synthesis_slugs.helpers.slugs_synthesizer_helper import SlugsSynthesizerHelper


def test_expand_binary_variables_handles_multi_digit_ranges():
    """Integer ranges above 9 should expand to the required bit variables."""
    variables = ['request', 'item:0...15', 'done']

    binary_variables = expand_binary_variables(variables)

    assert binary_variables == {'item': (0, 15)}
    assert variables == ['request', 'item@0', 'item@1', 'item@2', 'item@3', 'done']


def test_expand_binary_wrappers_share_behavior(tmp_path):
    """Synthesizer and checker helpers should expand ranges consistently."""
    synth_variables = ['count:0...10']
    checker_variables = ['count:0...10']

    synth_binary = SlugsSynthesizerHelper(str(tmp_path / 'demo'), []).expand_binary(
        synth_variables
    )
    checker_binary = SlugsAutomatonChecker().expand_binary(checker_variables)

    assert synth_binary == checker_binary == {'count': (0, 10)}
    assert synth_variables == checker_variables == [
        'count@0',
        'count@1',
        'count@2',
        'count@3',
    ]
