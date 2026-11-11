"""Replay recorded input faults through the real ROS services and controller.

Call only in an isolated Gazebo lab, never against hardware. Playback restores
initial joint position and runs the original protocol, not the measured CSV.
"""
import time
from gantry_control.triage import load_run, replay_schedule, SIGNATURES


def replay(node, manifest_path, *, simulation=False, timeout=90):
    if not simulation:
        raise ValueError('Explicit simulation=True required for active replay')
    import rclpy
    from rclpy.action import ActionClient
    from gantry_interfaces.action import RunProtocol
    from std_srvs.srv import SetBool, Trigger
    from control_msgs.action import FollowJointTrajectory
    from control_msgs.msg import JointTrajectoryControllerState
    from gantry_control.pendant import check_path
    from trajectory_msgs.msg import JointTrajectoryPoint
    from builtin_interfaces.msg import Duration
    from action_msgs.msg import GoalStatus
    from gantry_control.protocol import JOINTS, limit_fault, validate
    manifest, events, _ = load_run(manifest_path)
    schedule = replay_schedule(events)
    request = manifest['request']
    validate(request['wells'], request['volume_ul'], request.get('offset_x_m', 0.0),
             request.get('offset_y_m', 0.0), request.get('yaw_rad', 0.0))
    if limit_fault(manifest['initial_position']):
        raise ValueError('Unsafe initial position')
    clients = []
    measured = []
    def state(msg):
        from gantry_control.protocol import JOINTS
        try:
            position = tuple(msg.feedback.positions[msg.joint_names.index(j)] for j in JOINTS)
        except (ValueError, IndexError):
            return
        measured[:] = [position, time.monotonic()]
    subscription = node.create_subscription(JointTrajectoryControllerState,
        '/gantry_controller/controller_state', state, 10)

    def wait(future, seconds=timeout):
        rclpy.spin_until_future_complete(node, future, timeout_sec=seconds)
        if not future.done():
            raise TimeoutError('Replay transport timeout')
        return future.result()

    def service(name, value=None):
        kind = Trigger if value is None else SetBool
        client = node.create_client(kind, '/gantry/' + name)
        clients.append(client)
        if not client.wait_for_service(timeout_sec=5):
            raise RuntimeError('Missing simulation service ' + name)
        request = Trigger.Request() if value is None else SetBool.Request(data=value)
        result = wait(client.call_async(request), 5)
        if not result.success:
            raise RuntimeError(result.message)

    motion = ActionClient(node, FollowJointTrajectory, '/gantry_controller/follow_joint_trajectory')
    action = ActionClient(node, RunProtocol, '/gantry/run_protocol')
    active = None
    try:
        # A real /clock publisher is a required boundary in addition to opt-in.
        if '/clock' not in dict(node.get_topic_names_and_types()):
            raise RuntimeError('No simulation clock; refusing replay')
        for key in ('emergency_stop', 'limit_switch'):
            service(key, False)
        service('reset_fault')
        if not motion.wait_for_server(timeout_sec=10) or not action.wait_for_server(timeout_sec=10):
            raise RuntimeError('Simulation action servers unavailable')
        deadline = time.monotonic()+5
        while not measured and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.05)
        if not measured or time.monotonic()-measured[1]>.5:
            raise RuntimeError('Fresh measured position required for replay restoration')
        check_path(measured[0], manifest['initial_position'])
        move = FollowJointTrajectory.Goal()
        move.trajectory.joint_names = JOINTS
        move.trajectory.points = [JointTrajectoryPoint(positions=manifest['initial_position'],
            velocities=[0.0]*3, time_from_start=Duration(sec=3))]
        active = wait(motion.send_goal_async(move))
        if not active.accepted or wait(active.get_result_async()).status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError('Could not restore recorded starting position')
        goal = RunProtocol.Goal(**manifest['request'])
        active = wait(action.send_goal_async(goal), 5)
        if not active.accepted:
            raise RuntimeError('Replay protocol rejected')
        started = time.monotonic()
        for event in schedule:
            while time.monotonic()-started < event['elapsed_s']:
                rclpy.spin_once(node, timeout_sec=.01)
            service(event['name'], event['value'])
        result = wait(active.get_result_async())
        expected = [SIGNATURES.get(e['reason'], 'unknown') for e in events if e['kind'] == 'fault']
        actual = SIGNATURES.get(result.result.message, 'unknown')
        return {'reproduced': result.status == GoalStatus.STATUS_ABORTED and actual in expected,
                'expected': expected, 'actual': actual, 'log_path': result.result.log_path}
    finally:
        if active and active.accepted:
            try:
                wait(active.cancel_goal_async(), 5)
            except (RuntimeError, TimeoutError):
                node.get_logger().error('Replay cancellation unconfirmed')
        for key in ('emergency_stop', 'limit_switch'):
            try:
                service(key, False)
            except (RuntimeError, TimeoutError):
                pass
        for client in clients:
            node.destroy_client(client)
        node.destroy_subscription(subscription)
        action.destroy()
        motion.destroy()


def main():
    import argparse
    import json
    import rclpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--simulation', action='store_true', required=True)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node('gantry_fault_replay')
    try:
        result = replay(node, args.manifest, simulation=args.simulation)
        print(json.dumps(result, indent=2))
        if not result['reproduced']:
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
