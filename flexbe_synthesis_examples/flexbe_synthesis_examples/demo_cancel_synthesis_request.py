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

"""Test action cancellation by sending a generic demo request and canceling it."""

from flexbe_synthesis_msgs.action import FlexBESynthesis
from flexbe_synthesis_msgs.msg import FlexBESynthesisRequest, SynthesisErrorCode
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rosidl_runtime_py import message_to_yaml


class FlexBESynthesisCancelClient(Node):
    """Send one synthesis goal, request cancellation, and print the final result."""

    def __init__(self):
        """Initialize the cancel-test client and immediately send its goal."""
        super().__init__('test_cancel_synthesis_request')
        self.declare_parameter('initial_conditions', ['prep_pay_a'])
        self.declare_parameter('goals', ['soda'])
        self.declare_parameter('outcomes', ['finished', 'failed'])
        self.declare_parameter('system_name', 'vending_demo')
        self.declare_parameter('spec_name', 'VendingCancelDemoSM')
        self.declare_parameter('specification_file_name', '')
        self.declare_parameter('synthesis_options', '')
        self.declare_parameter('cancel_after_sec', 1.0)
        self.declare_parameter('server_timeout_sec', 5.0)

        request = FlexBESynthesisRequest()
        request.initial_conditions = self._array_param('initial_conditions')
        request.goals = self._array_param('goals')
        request.sm_outcomes = self._array_param('outcomes')
        request.system_name = self._string_param('system_name')
        request.spec_name = self._string_param('spec_name')
        request.specification_file_name = self._string_param('specification_file_name')

        self.goal_msg = FlexBESynthesis.Goal()
        self.goal_msg.request = request
        self.goal_msg.synthesis_options = self._string_param('synthesis_options')

        self._goal_handle = None
        self._cancel_timer = None
        self._action_client = ActionClient(self, FlexBESynthesis, 'flexbe_synthesis')
        self.send_goal()

    def _string_param(self, name: str) -> str:
        return self.get_parameter(name).get_parameter_value().string_value

    def _array_param(self, name: str):
        return [
            value.strip()
            for value in self.get_parameter(name).get_parameter_value().string_array_value
            if value.strip()
        ]

    def _double_param(self, name: str) -> float:
        return self.get_parameter(name).get_parameter_value().double_value

    def send_goal(self):
        """Send goal to synthesis server and schedule cancellation."""
        timeout_sec = self._double_param('server_timeout_sec')
        self.get_logger().info('Wait for synthesis server ...')
        if not self._action_client.wait_for_server(timeout_sec=timeout_sec):
            self.get_logger().error('Synthesis action server is unavailable!')
            rclpy.shutdown()
            return

        self.get_logger().info(f'Send synthesis request\n{message_to_yaml(self.goal_msg)}')
        future = self._action_client.send_goal_async(self.goal_msg)
        future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        """Handle goal acceptance and start the cancellation timer."""
        self._goal_handle = future.result()
        if not self._goal_handle.accepted:
            self.get_logger().info('Goal rejected')
            rclpy.shutdown()
            return

        delay_sec = max(0.0, self._double_param('cancel_after_sec'))
        self.get_logger().info(f'Goal accepted; canceling in {delay_sec:.2f} seconds ...')
        if delay_sec == 0.0:
            self.cancel_goal()
        else:
            self._cancel_timer = self.create_timer(delay_sec, self.cancel_goal)
        result_future = self._goal_handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def cancel_goal(self):
        """Request cancellation of the accepted goal."""
        if self._cancel_timer is not None:
            self._cancel_timer.cancel()

        if self._goal_handle is None:
            return

        self.get_logger().info('Request goal cancellation ...')
        future = self._goal_handle.cancel_goal_async()
        future.add_done_callback(self.cancel_response_callback)

    def cancel_response_callback(self, future):
        """Log whether the server accepted the cancel request."""
        cancel_response = future.result()
        if len(cancel_response.goals_canceling) > 0:
            self.get_logger().info('Cancel request accepted')
        else:
            self.get_logger().warning('Cancel request rejected or goal already finished')

    def get_result_callback(self, future):
        """Handle final synthesis result after cancellation."""
        result = future.result().result
        if result.error_code.value == SynthesisErrorCode.PREEMPTED:
            self.get_logger().info('Synthesis request canceled successfully')
        else:
            self.get_logger().info(
                f'Final result: ec={result.error_code.value} with {len(result.states)} states'
            )
            print(message_to_yaml(result), flush=True)
        rclpy.shutdown()


def main(args=None):
    """Run generic demo cancel-request test client."""
    rclpy.init(args=args)
    action_client = FlexBESynthesisCancelClient()
    try:
        rclpy.spin(action_client)
    except (RuntimeError, ValueError) as exc:
        print(f'Error: {exc}')
    finally:
        if rclpy.ok():
            rclpy.shutdown()
    print('Done!')


if __name__ == '__main__':
    main()
