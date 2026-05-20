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

import logging
import os

from flexbe_synthesis_core.base_preprocess import BasePreProcess
from flexbe_synthesis_core.validation_error import MappingValidationError
import yaml

logger = logging.getLogger(__name__)


class WorkspaceParser(BasePreProcess):
    """Compile workspace definition using loaded state outcome mappings."""

    state_mappings: dict

    def preprocess(self):
        """Load workspace definition and remap state/behavior outcomes."""
        logger.info('Starting %s ...', self.name)
        if (
            self.state_mappings is None
            or len(self.state_mappings) == 0
            or 'state_outcome_mappings' not in self.state_mappings
        ):
            print(

                    '\033[31mWARNING: Workspace_Parser Preprocess - No valid '
                    'state_mappings!\n\033[0m'
                    'At least one state_mappings dictionary with '
                    'state_outcome_mappings key must be loaded!'

            )
            raise ValueError('Invalid state outcome mappings!')

        state_outcome_mappings = self.state_mappings['state_outcome_mappings']
        if not isinstance(state_outcome_mappings, dict):
            raise MappingValidationError(
                'Invalid state_outcome_mappings: expected mapping.'
            )

        hidden_dir = self.synthesis_home
        if not os.path.exists(hidden_dir):
            raise FileNotFoundError(
                'The directory where workspace definitions should be found does not '
                'exist. Ensure workspace_crawler has run prior to workspace_parser.'
            )

        workspace_defn_fpath = os.path.join(hidden_dir, 'workspace_defn.yaml')
        if not os.path.isfile(workspace_defn_fpath):
            raise FileNotFoundError(
                'The workspace definition was not found in the hidden directory.'
            )

        with open(workspace_defn_fpath) as stream:
            workspace_defn = yaml.safe_load(stream)

        skipped = []

        skip_states = set()
        for implementation, state_info in workspace_defn['states'].items():
            for out in state_info['outcomes']:
                if out not in state_outcome_mappings:
                    skipped.append(
                        f"  state '{implementation}' outcome '{out}' — no mapping defined"
                    )
                    skip_states.add(implementation)
                    break
        for implementation in skip_states:
            del workspace_defn['states'][implementation]
        for implementation, state_info in workspace_defn['states'].items():
            for out in state_info['outcomes']:
                state_info['outcomes'][out]['remapping'] = state_outcome_mappings[out]

        skip_behaviors = set()
        for behavior, behavior_info in workspace_defn['behaviors'].items():
            for out in behavior_info['outcomes']:
                if out not in state_outcome_mappings:
                    skipped.append(
                        f"  behavior '{behavior}' outcome '{out}' — no mapping defined"
                    )
                    skip_behaviors.add(behavior)
                    break
        for behavior in skip_behaviors:
            del workspace_defn['behaviors'][behavior]
        for behavior, behavior_info in workspace_defn['behaviors'].items():
            for out in behavior_info['outcomes']:
                behavior_info['outcomes'][out]['remapping'] = state_outcome_mappings[out]

        if skipped:
            print(
                f'\033[33mWorkspaceParser: skipped {len(skipped)} implementation(s) with '
                f'unmapped outcomes — see pre-synthesis summary.\033[0m'
            )

        return [workspace_defn, skipped]


def main(inputs):
    """Create workspace parser preprocessor from pipeline inputs."""
    return WorkspaceParser(
        name='Workspace Parser',
        state_mappings=inputs[0],
    )


if __name__ == '__main__':
    state_outcome_mappings = {
        'done': 'completed',
        'received': 'completed',
        'true': 'completed',
        'unavailable': 'failure',
        'false': 'failure',
        'canceled': 'failure',
        'failed': 'failure',
        'empty': 'failure',
        'aborted': 'failure',
        'timeout': 'failure',
    }
    parser = main(
        [
            {'state_outcome_mappings': state_outcome_mappings},
        ]
    )
    outputs = parser.preprocess()
    for category, values in outputs[0].items():
        print(f' --- {category} ---')
        print(yaml.dump(values, default_flow_style=False))
        print('---\n')
