"""End-to-end tests against real Gazebo, never mock hardware."""
import csv
from pathlib import Path
import tempfile
import time
import unittest

import launch
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from rclpy.action import ActionClient
from ament_index_python.packages import get_package_share_directory
from action_msgs.msg import GoalStatus
from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTrajectoryControllerState
from gantry_interfaces.action import RunProtocol
from std_srvs.srv import SetBool, Trigger
from trajectory_msgs.msg import JointTrajectoryPoint
from builtin_interfaces.msg import Duration


@pytest.mark.launch_test
def generate_test_description():
    logs = tempfile.mkdtemp(prefix='gantry-launch-')
    path = Path(get_package_share_directory('gantry_control')) / 'launch/simulation.launch.py'
    return launch.LaunchDescription([
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(path)),
                                 launch_arguments={'log_dir': logs}.items()),
        launch_testing.actions.ReadyToTest(),
    ])


class TestSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('simulation_test')
        cls.action = ActionClient(cls.node, RunProtocol, '/gantry/run_protocol')
        cls.motion = ActionClient(cls.node, FollowJointTrajectory, '/gantry_controller/follow_joint_trajectory')
        cls.position = None
        cls.node.create_subscription(JointTrajectoryControllerState,
            '/gantry_controller/controller_state', cls.state, 10)
        assert cls.action.wait_for_server(timeout_sec=90)
        assert cls.motion.wait_for_server(timeout_sec=90)
        deadline = time.monotonic() + 15
        while cls.position is None and time.monotonic() < deadline:
            rclpy.spin_once(cls.node, timeout_sec=.1)
        assert cls.position is not None

    @classmethod
    def state(cls, msg):
        cls.position = tuple(msg.feedback.positions)

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def wait(self, future, timeout=30):
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        self.assertTrue(future.done(), 'ROS request timed out')
        return future.result()

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=.02)

    def service(self, name, value=None):
        kind = Trigger if value is None else SetBool
        client = self.node.create_client(kind, '/gantry/' + name)
        try:
            self.assertTrue(client.wait_for_service(timeout_sec=5))
            request = Trigger.Request() if value is None else SetBool.Request(data=value)
            return self.wait(client.call_async(request), 5)
        finally:
            self.node.destroy_client(client)

    def send(self, wells=('A1',), volume=50.0):
        return self.wait(self.action.send_goal_async(RunProtocol.Goal(wells=list(wells), volume_ul=volume)), 5)

    def test_01_complete_protocol_and_measure_motion(self):
        self.assertTrue(self.service('reset_fault').success)
        phases = []
        goal = self.wait(self.action.send_goal_async(
            RunProtocol.Goal(wells=['A1', 'B2'], volume_ul=50.0),
            feedback_callback=lambda msg: phases.append((msg.feedback.well, msg.feedback.phase))))
        self.assertTrue(goal.accepted)
        result = self.wait(goal.get_result_async(), 45)
        self.assertEqual(result.status, GoalStatus.STATUS_SUCCEEDED)
        self.assertTrue(result.result.success)
        self.assertEqual(result.result.completed_wells, 2)
        self.assertEqual(phases, [(w, p) for w in ['A1', 'B2'] for p in ['lift', 'travel', 'lower', 'retract']])
        rows = list(csv.DictReader(Path(result.result.log_path).open()))
        self.assertGreater(len(rows), 100)
        self.assertEqual({r['joint'] for r in rows}, {'x_joint', 'y_joint', 'z_joint'})
        self.assertTrue(all(abs(float(r['reference_m']) - float(r['actual_m']) - float(r['error_m'])) < 1e-9 for r in rows))
        errors = [float(r['error_m']) for r in rows]
        peak = max(map(abs, errors))
        rms = (sum(e*e for e in errors)/len(errors))**.5
        self.assertLess(peak, .015)
        self.assertTrue(any(float(r['actual_m']) > .045 for r in rows if r['joint'] == 'z_joint'))
        self.pump(.2)
        for actual, expected in zip(self.position, (.049, .044, .01)):
            self.assertAlmostEqual(actual, expected, delta=.002)
        doses = list(csv.DictReader(Path(result.result.log_path.replace('-tracking', '-dispenses')).open()))
        self.assertEqual([r['well'] for r in doses], ['A1', 'B2'])
        self.assertTrue(all(float(r['volume_ul']) == 50 for r in doses))
        print(f'MEASURED tracking samples={len(rows)} peak_m={peak:.6f} rms_m={rms:.6f}', flush=True)

    def test_02_reject_malformed_and_overlapping_goals(self):
        self.assertFalse(self.send(('Z99',)).accepted)
        self.assertFalse(self.send(volume=float('nan')).accepted)
        first = self.send(('H12',))
        self.assertTrue(first.accepted)
        self.assertFalse(self.send().accepted)
        self.wait(first.cancel_goal_async())
        self.assertEqual(self.wait(first.get_result_async()).status, GoalStatus.STATUS_CANCELED)
        self.pump(.3)
        before = self.position
        self.pump(.4)
        self.assertLess(max(abs(a-b) for a, b in zip(before, self.position)), .001)

    def test_03_emergency_stop_latches_and_requires_clear(self):
        goal = self.send(('H12',))
        self.assertTrue(goal.accepted)
        self.pump(.3)
        self.assertTrue(self.service('emergency_stop', True).success)
        result = self.wait(goal.get_result_async())
        self.assertEqual(result.status, GoalStatus.STATUS_ABORTED)
        self.assertIn('emergency_stop', result.result.message)
        self.assertEqual(result.result.completed_wells, 0)
        self.assertFalse(self.send().accepted)
        self.assertFalse(self.service('reset_fault').success)
        self.service('emergency_stop', False)
        self.assertFalse(self.send().accepted)
        self.assertTrue(self.service('reset_fault').success)
        self.pump(.3)
        before = self.position
        self.pump(.4)
        self.assertLess(max(abs(a-b) for a, b in zip(before, self.position)), .001)

    def test_04_injected_limit_switch_aborts(self):
        goal = self.send(('A1',))
        self.assertTrue(goal.accepted)
        self.service('limit_switch', True)
        result = self.wait(goal.get_result_async())
        self.assertEqual(result.status, GoalStatus.STATUS_ABORTED)
        self.assertIn('limit_switch', result.result.message)
        self.assertFalse(self.service('reset_fault').success)
        self.service('limit_switch', False)
        self.assertTrue(self.service('reset_fault').success)

    def test_05_feedback_limit_detects_external_controller_motion(self):
        # Bypass the protocol deliberately to exercise position-derived switches.
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = ['x_joint', 'y_joint', 'z_joint']
        target = list(self.position)
        target[0] = .22
        goal.trajectory.points = [JointTrajectoryPoint(positions=target,
            velocities=[0.0]*3, time_from_start=Duration(sec=5))]
        child = self.wait(self.motion.send_goal_async(goal))
        self.assertTrue(child.accepted)
        self.wait(child.get_result_async(), 15)
        self.pump(.5)
        self.assertFalse(self.send().accepted)
        self.assertFalse(self.service('reset_fault').success)
        target[0] = .04
        goal.trajectory.points[0].positions = target
        child = self.wait(self.motion.send_goal_async(goal))
        self.wait(child.get_result_async(), 15)
        self.pump(.5)
        self.assertTrue(self.service('reset_fault').success)
        recovered = self.send()
        self.assertTrue(recovered.accepted)
        self.assertTrue(self.wait(recovered.get_result_async(), 30).result.success)

    def test_06_paused_simulation_trips_wall_clock_watchdog(self):
        import subprocess

        def pause(value):
            response = subprocess.run(['gz', 'service', '-s', '/world/lab/control',
                '--reqtype', 'gz.msgs.WorldControl', '--reptype', 'gz.msgs.Boolean',
                '--timeout', '2000', '--req', f'pause: {value}'],
                capture_output=True, text=True, timeout=5)
            self.assertEqual(response.returncode, 0, response.stderr)
            self.assertIn('true', response.stdout)

        goal = self.send(('H12',))
        self.assertTrue(goal.accepted)
        self.pump(.2)
        try:
            pause('true')
            self.pump(1.4)
            self.assertFalse(self.send().accepted)
        finally:
            pause('false')
        result = self.wait(goal.get_result_async(), 10)
        self.assertEqual(result.status, GoalStatus.STATUS_ABORTED)
        self.assertIn('stale', result.result.message)
        self.pump(.2)
        self.assertTrue(self.service('reset_fault').success)
