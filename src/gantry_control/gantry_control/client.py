import argparse
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from gantry_interfaces.action import RunProtocol


def main():
    parser = argparse.ArgumentParser(description='Run a simulated 96-well plate dispense protocol')
    parser.add_argument('--wells', nargs='+', default=['A1', 'A2', 'B2'])
    parser.add_argument('--volume', type=float, default=50.0)
    args = parser.parse_args()
    rclpy.init()
    node = Node('run_plate')
    try:
        client = ActionClient(node, RunProtocol, '/gantry/run_protocol')
        if not client.wait_for_server(timeout_sec=90):
            raise SystemExit('Protocol server not found')
        # Wait for the controller and a state sample without resetting latched faults.
        from control_msgs.action import FollowJointTrajectory
        from control_msgs.msg import JointTrajectoryControllerState
        motion = ActionClient(node, FollowJointTrajectory, '/gantry_controller/follow_joint_trajectory')
        if not motion.wait_for_server(timeout_sec=90):
            raise SystemExit('Motion controller not found')
        ready = []
        subscription = node.create_subscription(JointTrajectoryControllerState,
            '/gantry_controller/controller_state', lambda _: ready.append(True), 1)
        import time
        deadline = time.monotonic() + 10
        while not ready and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        node.destroy_subscription(subscription)
        if not ready:
            raise SystemExit('No controller feedback')
        goal = client.send_goal_async(RunProtocol.Goal(wells=args.wells, volume_ul=args.volume),
            feedback_callback=lambda msg: print(f'{msg.feedback.well}: {msg.feedback.phase}', flush=True))
        rclpy.spin_until_future_complete(node, goal, timeout_sec=10)
        if not goal.done() or not goal.result().accepted:
            raise SystemExit('Protocol rejected: check wells, volume, controller readiness and latched faults')
        result = goal.result().get_result_async()
        rclpy.spin_until_future_complete(node, result)
        report = result.result().result
        print(f'{report.message}; completed={report.completed_wells}; tracking={report.log_path}')
        if not report.success:
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
