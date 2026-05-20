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

"""Base class for FlexBE synthesis process implementations."""

import abc

from flexbe_synthesis_core import predefined_strings as fpths
from pydantic import BaseModel, Field


class BaseProcess(BaseModel, abc.ABC):
    """
    Base class for FlexBE Synthesis processes.

    Each concrete subclass must be accompanied by a module-level factory::

        def main(inputs):
            return MyProcess(name='MyProcess', arg=inputs[0], ...)

    The ``main(inputs)`` function — not the class — must be registered as the
    entry-point in the package's ``setup.py`` under the
    ``FlexBESynthesis.processes`` group.  Registering the class directly will
    be caught at load time with a ``ValidationError(kind=PLUGIN_INTERFACE)``.
    """

    name: str
    verbose: bool = False
    # Injected by the manager after construction; default covers standalone use.
    synthesis_home: str = Field(default_factory=fpths.get_synthesis_home)
    # Accumulated diagnostic messages (warnings, errors) surfaced to the UI.
    messages: list = Field(default_factory=list)

    @abc.abstractmethod
    def process(self):
        """
        Execute this pipeline stage and return outputs in declared order.

        Must return a list or tuple whose elements correspond positionally to
        the ``outputs:`` keys declared in the pipeline YAML for this plugin.
        If any returned element is a ``SynthesisErrorCode`` whose value is not
        ``SynthesisErrorCode.SUCCESS``, the pipeline manager halts immediately
        after storing this plugin's outputs and does not execute subsequent stages.
        """
        pass

    def cancel(self):
        """
        Request cancellation of any work owned by this process.

        Must be idempotent: the manager may call this more than once per request.
        """
        pass

    def get_name(self) -> str:
        """Return the configured process name."""
        return self.name
