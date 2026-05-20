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

"""
Generic FlexBE synthesis action client.

All request fields are ROS 2 parameters and can be overridden at the command
line with ``--ros-args -p key:=value``.  Predefined wrappers (``request_vending``,
``request_coffee``) supply demo-specific defaults; running ``request_synthesis``
directly requires explicit ``--ros-args`` parameters.
"""

from flexbe_synthesis_msgs.action import FlexBESynthesis
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rosidl_runtime_py import message_to_yaml


class FlexBESynthesisActionClient(Node):
    """Send one synthesis goal and print the response."""

    def __init__(self, defaults=None):
        """Declare ROS 2 parameters, applying defaults before any --ros-args overrides."""
        super().__init__('request_synthesis')
        d = defaults or {}
        self.declare_parameter('initial_conditions', d.get('initial_conditions', []))
        self.declare_parameter('goals', d.get('goals', []))
        self.declare_parameter('outcomes', d.get('outcomes', []))
        self.declare_parameter('system_name', d.get('system_name', ''))
        self.declare_parameter('spec_name', d.get('spec_name', ''))
        self.declare_parameter('specification_file_name', d.get('specification_file_name', ''))
        self.declare_parameter('synthesis_timeout_s', d.get('synthesis_timeout_s', 0.0))
        self.declare_parameter('synthesis_options', d.get('synthesis_options', ''))
        self.declare_parameter('server_timeout_sec', d.get('server_timeout_sec', 10.0))

        request = FlexBESynthesisRequest()
        request.initial_conditions = self._array_param('initial_conditions')
        request.goals = self._array_param('goals')
        request.sm_outcomes = self._array_param('outcomes')
        request.system_name = self._string_param('system_name')
        request.spec_name = self._string_param('spec_name')
        request.specification_file_name = self._string_param('specification_file_name')
        request.synthesis_timeout_s = self._double_param('synthesis_timeout_s')

        self.goal_msg = FlexBESynthesis.Goal()
        self.goal_msg.request = request
        self.goal_msg.synthesis_options = self._string_param('synthesis_options')

        self._action_client = ActionClient(self, FlexBESynthesis, 'flexbe_synthesis')
        self.request_complete = False

    def _string_param(self, name):
        return self.get_parameter(name).get_parameter_value().string_value

    def _array_param(self, name):
        return [
            v.strip()
            for v in self.get_parameter(name).get_parameter_value().string_array_value
            if v.strip()
        ]

    def _double_param(self, name):
        return self.get_parameter(name).get_parameter_value().double_value

    def connect_and_send(self):
        """Wait for the action server and send the goal; return False on timeout."""
        timeout_sec = self._double_param('server_timeout_sec')
        self.get_logger().info('Wait for synthesis server ...')
        if not self._action_client.wait_for_server(timeout_sec=timeout_sec):
            self.get_logger().error(
                f'Synthesis action server is unavailable after {timeout_sec:.1f} seconds!'
            )
            return False
        self.get_logger().info(f'Send synthesis request\n{message_to_yaml(self.goal_msg)}')
        future = self._action_client.send_goal_async(self.goal_msg)
        future.add_done_callback(self.goal_response_callback)
        return True

    def goal_response_callback(self, future):
        """Handle goal-acceptance response."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected')
            self.request_complete = True
            return
        self.get_logger().info('Goal accepted ...')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        """Handle final synthesis result."""
        result = future.result().result
        if result.error_code.value == SynthesisErrorCode.SUCCESS:
            print(20 * '=', 'Success', 20 * '=')
            print(message_to_yaml(result), flush=True)
            print(30 * '-')
            self.get_logger().info(
                f'Result received: ec={result.error_code.value} '
                f'with {len(result.states)} states'
            )
            self.get_logger().info('Success')
        else:
            self.get_logger().info('Failed to synthesize state machine')
            self.get_logger().info(
                f'   ec={result.error_code.value} with {len(result.states)} states'
            )
        self.request_complete = True


def run_synthesis_client(args, defaults=None):
    """Initialize rclpy, build a client with defaults, spin until done."""
    rclpy.init(args=args)
    action_client = FlexBESynthesisActionClient(defaults=defaults)
    try:
        if action_client.connect_and_send():
            while rclpy.ok() and not action_client.request_complete:
                rclpy.spin_once(action_client, timeout_sec=0.1)
    except (RuntimeError, ValueError) as exc:
        print(f'Error: {exc}')
    finally:
        if rclpy.ok():
            action_client.destroy_node()
            rclpy.shutdown()
    print('Done!')


def main(args=None):
    """Run generic synthesis request client; all fields must be set via --ros-args."""
    run_synthesis_client(args)


if __name__ == '__main__':
    main()
