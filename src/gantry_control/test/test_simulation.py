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

    def pendant(self, command):
        import json
        from gantry_interfaces.srv import PendantCommand
        client = self.node.create_client(PendantCommand, '/gantry/pendant/command')
        try:
            self.assertTrue(client.wait_for_service(timeout_sec=5))
            response = self.wait(client.call_async(PendantCommand.Request(json=json.dumps(command))), 5)
            return response, json.loads(response.state_json)
        finally:
            self.node.destroy_client(client)

    def program(self, instructions, step=0):
        import json
        from gantry_interfaces.action import RunProgram
        client = ActionClient(self.node, RunProgram, '/gantry/pendant/run')
        self.addCleanup(client.destroy)
        self.assertTrue(client.wait_for_server(timeout_sec=5))
        return self.wait(client.send_goal_async(RunProgram.Goal(
            instructions_json=json.dumps(instructions), step=step)), 5)

    def test_07_teach_measured_frames_points_and_auto_io(self):
        self.assertTrue(self.service('reset_fault').success)
        self.assertTrue(self.pendant({'op':'mode', 'mode':'teach'})[0].success)
        self.pump(.2)
        before = self.position
        for frame in ('joint', 'world', 'tool'):
            goal = self.program([{'op':'jog','frame':frame,'delta':[.002,.002,.002]}])
            self.assertTrue(goal.accepted)
            result = self.wait(goal.get_result_async(), 10)
            self.assertTrue(result.result.success, result.result.message)
            self.pump(.2)
            self.assertTrue(self.pendant({'op':'record', 'name':frame, 'frame':frame,
                                         'offset':[.001,0,0]})[0].success)
        # Joint: +++; world: ++-; tool: +-+. Values come from measured motion.
        for actual, expected in zip(self.position,
                                    (before[0]+.006, before[1]+.002, before[2]+.002)):
            self.assertAlmostEqual(actual, expected, delta=.001)
        instructions = [
            {'op':'wait_di','channel':0,'value':True,'timeout':5},
            {'op':'move','point':'joint'}, {'op':'move','point':'world'},
            {'op':'move','point':'tool','offset':[.001,0,0]},
            {'op':'set_do','channel':1,'value':True}]
        # Teach runs only the selected instruction. The preceding unsatisfied wait is skipped.
        goal = self.program(instructions, step=4)
        self.assertTrue(self.wait(goal.get_result_async()).result.success)
        self.assertTrue(self.pendant({'op':'status'})[1]['do'][1])
        off = self.program([{'op':'set_do','channel':1,'value':False}])
        self.assertTrue(self.wait(off.get_result_async()).result.success)
        self.assertFalse(self.pendant({'op':'status'})[1]['do'][1])
        self.pendant({'op':'mode','mode':'auto'})
        self.assertFalse(self.program([{'op':'jog','frame':'joint','delta':[.001,0,0]}]).accepted)
        goal = self.program(instructions)
        self.assertTrue(goal.accepted)
        self.pump(.2)
        self.assertFalse(self.send().accepted)  # The plate runner shares the same motion slot.
        self.assertFalse(self.pendant({'op':'mode','mode':'teach'})[0].success)
        self.assertFalse(self.pendant({'op':'record','name':'race','frame':'joint'})[0].success)
        self.pendant({'op':'di','channel':0,'value':True})
        result = self.wait(goal.get_result_async(), 30)
        self.assertTrue(result.result.success, result.result.message)
        self.assertEqual(result.result.completed, 5)
        self.pump(.2)
        state = self.pendant({'op':'status'})[1]
        self.assertTrue(state['do'][1], 'Auto must execute the programmed output change')
        expected = state['points']['tool']['joint']
        self.assertAlmostEqual(self.position[0], expected[0]+.002, delta=.001)
        self.assertAlmostEqual(self.position[1], expected[1], delta=.001)
        self.assertAlmostEqual(self.position[2], expected[2], delta=.001)

    def test_08_pendant_estop_both_modes_and_wait_timeout(self):
        for mode in ('teach','auto'):
            self.assertTrue(self.pendant({'op':'mode','mode':'teach'})[0].success)
            # Move far enough to still be moving when the stop arrives.
            self.assertTrue(self.pendant({'op':'record','name':'stop_'+mode,
                'frame':'joint','offset':[.03,0,0]})[0].success)
            self.assertTrue(self.pendant({'op':'mode','mode':mode})[0].success)
            goal = self.program([{'op':'move','point':'stop_'+mode}])
            self.assertTrue(goal.accepted)
            self.pump(.25)
            self.service('emergency_stop',True)
            result = self.wait(goal.get_result_async(), 10)
            self.assertEqual(result.status, GoalStatus.STATUS_ABORTED)
            self.assertIn('emergency_stop', result.result.message)
            self.assertFalse(self.program([{'op':'move','point':'stop_'+mode}]).accepted)
            self.assertFalse(self.service('reset_fault').success)
            self.service('emergency_stop',False)
            self.assertFalse(self.program([{'op':'move','point':'stop_'+mode}]).accepted)
            self.pump(.2)
            before = self.position
            self.pump(.4)
            self.assertLess(max(abs(a-b) for a,b in zip(before,self.position)), .001)
            self.assertFalse(any(self.pendant({'op':'status'})[1]['do']))
            self.assertTrue(self.service('reset_fault').success)
        self.pendant({'op':'di','channel':2,'value':False})
        goal = self.program([{'op':'wait_di','channel':2,'value':True,'timeout':.3},
                             {'op':'set_do','channel':2,'value':True}])
        result = self.wait(goal.get_result_async(), 5)
        self.assertFalse(result.result.success)
        self.assertEqual(result.result.completed,0)
        self.assertFalse(self.pendant({'op':'status'})[1]['do'][2])
        self.assertTrue(self.service('reset_fault').success)
        goal = self.program([{'op':'wait_di','channel':2,'value':True,'timeout':5}])
        self.pump(.1)
        self.service('emergency_stop',True)
        self.assertEqual(self.wait(goal.get_result_async(),5).status, GoalStatus.STATUS_ABORTED)
        self.service('emergency_stop',False)
        self.assertTrue(self.service('reset_fault').success)
        goal = self.program([{'op':'wait_di','channel':2,'value':True,'timeout':5}])
        self.wait(goal.cancel_goal_async())
        self.assertEqual(self.wait(goal.get_result_async(),5).status, GoalStatus.STATUS_CANCELED)

    def test_09_zone_preflight_and_malformed_commands(self):
        # Teach a raised point above the physical fixture, then request an unsafe lower offset.
        self.pendant({'op':'mode','mode':'teach'})
        state = self.pendant({'op':'status'})[1]
        p = state['position']
        offset = [.18-p[0], .125-p[1], .01-p[2]]
        self.assertTrue(self.pendant({'op':'record','name':'fixture','frame':'joint','offset':offset})[0].success)
        self.pendant({'op':'mode','mode':'auto'})
        before = self.position
        goal = self.program([{'op':'set_do','channel':3,'value':True},
            {'op':'move','point':'fixture','offset':[0,0,.04]}])
        self.assertFalse(goal.accepted)
        self.pump(.2)
        self.assertFalse(self.pendant({'op':'status'})[1]['do'][3])
        self.assertLess(max(abs(a-b) for a,b in zip(before,self.position)),.001)
        for command in ({'op':'di','channel':True,'value':True}, {'op':'mode','mode':'fast'},
                        {'op':'di','channel':0,'value':1}, {'op':'nonsense'}, []):
            self.assertFalse(self.pendant(command)[0].success)

        self.pendant({'op':'mode','mode':'teach'})
        self.assertFalse(self.pendant({'op':'record','name':'huge','offset':[10**400,0,0]})[0].success)
        self.assertFalse(self.program([{'op':'jog','frame':'joint','delta':[10**400,0,0]}]).accepted)
        self.assertFalse(self.program([{'op':'wait_di','channel':0,'value':True,'timeout':10**400}]).accepted)
        self.assertTrue(self.pendant({'op':'status'})[0].success)

    def test_10_cli_interrupt_cancels_before_exiting(self):
        import os
        import signal
        import subprocess
        from ament_index_python.packages import get_package_prefix
        self.pendant({'op':'mode','mode':'auto'})
        self.pendant({'op':'di','channel':7,'value':False})
        with tempfile.TemporaryDirectory(prefix='gantry-cli-') as directory:
            path = Path(directory)/'wait.json'
            path.write_text('[{"op":"wait_di","channel":7,"value":true,"timeout":20}]')
            executable = Path(get_package_prefix('gantry_control'))/'lib/gantry_control/pendant'
            with (Path(directory)/'client.log').open('w+') as output:
                process = subprocess.Popen([str(executable),'run',str(path)],
                    stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                print(f'CLI test owns PID/PGID {process.pid}, start={time.time()}, no ports; cleanup=SIGINT then wait', flush=True)
                try:
                    deadline = time.monotonic()+10
                    while not self.pendant({'op':'status'})[1]['busy']:
                        self.assertIsNone(process.poll(), 'CLI exited before starting program')
                        self.assertLess(time.monotonic(), deadline, 'CLI never started program')
                        self.pump(.1)
                    os.killpg(process.pid, signal.SIGINT)
                    self.assertEqual(process.wait(timeout=10), 130)
                    self.pump(.2)
                    state = self.pendant({'op':'status'})[1]
                    self.assertFalse(state['busy'])
                    self.assertFalse(state['fault'], 'Cancellation should leave the server ready')
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)
                    self.assertIsNotNone(process.returncode)
