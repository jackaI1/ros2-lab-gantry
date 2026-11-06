"""Protocol action server. Wall-clock watchdogs remain live if Gazebo is paused."""
import csv
import math
import json
from pathlib import Path
import threading
import time
import uuid

import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
from rclpy.node import Node
from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTrajectoryControllerState
from gantry_interfaces.action import RunProtocol, RunProgram
from gantry_interfaces.srv import PendantCommand
from std_msgs.msg import String
from std_srvs.srv import SetBool, Trigger
from trajectory_msgs.msg import JointTrajectoryPoint
from gantry_control.protocol import JOINTS, limit_fault, validate, waypoints
from gantry_control.pendant import Pendant, channel, check_path
from gantry_control.trajectory import trapezoid
from gantry_control.motion import StopBarrier, wait_acceptance


class ProtocolServer(Node):
    def __init__(self):
        super().__init__('protocol_server')
        self.group = ReentrantCallbackGroup()
        self.lock = threading.RLock()
        self.pendant = Pendant()
        self.prepared = []
        self.program_speed = .01
        self.busy = False
        self.fault = ''
        self.stop_barrier = StopBarrier(self.lock, self.latch,
            {GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_CANCELED})
        self.inputs = {'emergency_stop': False, 'limit_switch': False}
        self.position = None
        self.last_state = 0.0
        self.bad_tracking_since = None
        self.log = None
        self.writer = None
        self.well = ''
        self.phase = ''
        self.log_dir = Path(self.declare_parameter('log_dir', '/tmp/gantry-logs').value)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.client = ActionClient(self, FollowJointTrajectory,
                                   '/gantry_controller/follow_joint_trajectory', callback_group=self.group)
        self.create_subscription(JointTrajectoryControllerState, '/gantry_controller/controller_state',
                                 self.state, 10, callback_group=self.group)
        self.status = self.create_publisher(String, '/gantry/fault', 10)
        for name in self.inputs:
            self.create_service(SetBool, '/gantry/' + name,
                                lambda req, res, key=name: self.set_input(key, req, res),
                                callback_group=self.group)
        self.create_service(Trigger, '/gantry/reset_fault', self.reset, callback_group=self.group)
        self.create_timer(0.05, self.watchdog, callback_group=self.group)
        self.pendant_status = self.create_publisher(String, '/gantry/pendant/state', 10)
        self.create_service(PendantCommand, '/gantry/pendant/command', self.pendant_command,
                            callback_group=self.group)
        self.program_server = ActionServer(self, RunProgram, '/gantry/pendant/run',
            execute_callback=self.execute_program, goal_callback=self.program_goal,
            cancel_callback=lambda _: CancelResponse.ACCEPT, callback_group=self.group)
        self.server = ActionServer(self, RunProtocol, '/gantry/run_protocol',
                                   execute_callback=self.execute, goal_callback=self.goal,
                                   cancel_callback=lambda _: CancelResponse.ACCEPT,
                                   callback_group=self.group)

    def latch(self, reason):
        with self.lock:
            if not self.fault:
                self.fault = reason
                self.pendant.do = [False]*8
                self.get_logger().error(reason)

    def state(self, msg):
        with self.lock:
            try:
                indices = [msg.joint_names.index(j) for j in JOINTS]
                position = tuple(msg.feedback.positions[i] for i in indices)
                reference = tuple(msg.reference.positions[i] for i in indices)
            except (ValueError, IndexError):
                self.latch('invalid controller feedback')
                return
            self.last_state = time.monotonic()
            self.position = position
            reason = limit_fault(position)
            if reason:
                self.latch(reason)
            errors = tuple(r - p for r, p in zip(reference, position))
            if not all(math.isfinite(r) for r in reference):
                self.latch('invalid reference feedback')
            if self.busy and max(map(abs, errors)) > 0.015:
                self.bad_tracking_since = self.bad_tracking_since or time.monotonic()
                if time.monotonic() - self.bad_tracking_since > 0.5:
                    self.latch('tracking error over 15 mm for 0.5 s')
            else:
                self.bad_tracking_since = None
            if self.writer:
                stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
                try:
                    for joint, ref, actual, error in zip(JOINTS, reference, position, errors):
                        self.writer.writerow([stamp, self.well, self.phase, joint, ref, actual, error])
                    self.log.flush()
                except OSError:
                    self.writer = None
                    self.latch('tracking log write failed')

    def watchdog(self):
        with self.lock:
            if self.busy and time.monotonic() - self.last_state > 1.0:
                self.latch('controller feedback stale for 1 s')
            self.status.publish(String(data=self.fault or 'OK'))
            self.pendant_status.publish(String(data=json.dumps(self.pendant_state())))

    def set_input(self, key, req, res):
        with self.lock:
            self.inputs[key] = req.data
            if req.data:
                self.latch(key)
            res.success = True
            res.message = self.fault or 'input cleared; reset required'
            return res

    def reset(self, req, res):
        with self.lock:
            reason = (self.busy or self.stop_barrier.pending or any(self.inputs.values()) or self.position is None
                      or time.monotonic() - self.last_state > 1.0 or limit_fault(self.position))
            res.success = not bool(reason)
            res.message = 'clear inputs, stop protocol and restore healthy feedback first' if reason else 'reset'
            if res.success:
                self.fault = ''
                self.bad_tracking_since = None
            return res

    def goal(self, request):
        try:
            validate(request.wells, request.volume_ul)
        except ValueError as exc:
            self.get_logger().warning(str(exc))
            return GoalResponse.REJECT
        with self.lock:
            if (self.busy or self.fault or self.position is None
                    or time.monotonic() - self.last_state > 1.0 or not self.client.server_is_ready()):
                return GoalResponse.REJECT
            self.busy = True  # Reserve before the execute callback can be scheduled.
            return GoalResponse.ACCEPT

    @staticmethod
    def wait(future, timeout):
        deadline = time.monotonic() + timeout
        while not future.done():
            if time.monotonic() > deadline:
                raise RuntimeError('controller response timed out')
            time.sleep(0.01)
        return future.result()

    def interrupted(self, handle):
        with self.lock:
            if self.fault:
                return self.fault
        return 'canceled by client' if handle.is_cancel_requested else ''

    def move(self, target, handle, speed=.04):
        with self.lock:
            current = self.position
        check_path(current, target)
        reason = self.interrupted(handle)
        if reason:
            raise RuntimeError(reason)
        samples = trapezoid(current, target, speed)
        duration = samples[-1][0]
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = JOINTS
        for stamp, positions, velocities in samples:
            nanos = round(stamp*1e9)
            goal.trajectory.points.append(JointTrajectoryPoint(
                positions=list(positions), velocities=list(velocities),
                time_from_start=Duration(sec=nanos//10**9, nanosec=nanos%10**9)))
        pending = self.client.send_goal_async(goal)
        try:
            child = wait_acceptance(pending, lambda: self.interrupted(handle))
        except RuntimeError as exc:
            self.stop_barrier.arm(pending)
            self.latch(str(exc))
            raise
        if not child.accepted:
            raise RuntimeError('controller rejected trajectory')
        result = child.get_result_async()
        deadline = time.monotonic() + duration + 6
        while not result.done():
            reason = self.interrupted(handle)
            if reason or time.monotonic() > deadline:
                # JTC cancellation switches to holding the current position.
                try:
                    ack = self.wait(child.cancel_goal_async(), 3)
                    stopped = self.wait(result, 3)
                    if not ack.goals_canceling and stopped.status != GoalStatus.STATUS_SUCCEEDED:
                        raise RuntimeError('controller did not acknowledge stop')
                except RuntimeError:
                    self.latch('controller stop unconfirmed')
                    raise
                raise RuntimeError(reason or 'trajectory timed out')
            time.sleep(0.01)
        response = result.result()
        if response.status != GoalStatus.STATUS_SUCCEEDED or response.result.error_code != 0:
            raise RuntimeError('trajectory failed: ' + response.result.error_string)
        if self.interrupted(handle):
            raise RuntimeError(self.interrupted(handle))

    def pendant_state(self):
        return {'mode': self.pendant.mode, 'position': self.position,
                'points': self.pendant.points, 'di': self.pendant.di, 'do': self.pendant.do,
                'busy': self.busy, 'fault': self.fault,
                'stop_unconfirmed': bool(self.stop_barrier.pending)}

    def pendant_command(self, req, res):
        with self.lock:
            try:
                command = json.loads(req.json)
                if not isinstance(command, dict):
                    raise ValueError('Command must be an object')
                op = command.get('op')
                if op == 'status':
                    pass
                elif op == 'di':
                    index = channel(command.get('channel'))
                    if type(command.get('value')) is not bool:
                        raise ValueError('Digital value must be true or false')
                    self.pendant.di[index] = command['value']
                else:
                    if self.busy:
                        raise ValueError('Stop the active run before changing pendant configuration')
                    if op == 'mode':
                        mode = command.get('mode')
                        if mode not in ('teach', 'auto'):
                            raise ValueError('Mode must be teach or auto')
                        self.pendant.mode = mode
                    elif op == 'record':
                        if self.pendant.mode != 'teach' or self.fault or self.position is None or time.monotonic()-self.last_state > 1:
                            raise ValueError('Recording requires healthy idle teach mode')
                        self.pendant.record(command.get('name'), self.position,
                            command.get('frame', 'joint'), command.get('offset', [0,0,0]))
                    elif op == 'delete':
                        name = command.get('name')
                        if not isinstance(name, str) or name not in self.pendant.points:
                            raise ValueError('Unknown point')
                        del self.pendant.points[name]
                    else:
                        raise ValueError('Unknown pendant command')
                res.success, res.message = True, 'OK'
            except (ValueError, TypeError) as exc:
                res.success, res.message = False, str(exc)
            res.state_json = json.dumps(self.pendant_state())
            return res

    def program_goal(self, request):
        with self.lock:
            if (self.busy or self.fault or self.position is None or
                    time.monotonic()-self.last_state > 1 or not self.client.server_is_ready()):
                return GoalResponse.REJECT
            try:
                self.prepared = self.pendant.prepare(json.loads(request.instructions_json),
                                                      self.position, request.step)
            except (ValueError, TypeError) as exc:
                self.get_logger().warning(str(exc))
                return GoalResponse.REJECT
            self.program_speed = .01 if self.pendant.mode == 'teach' else .04
            self.busy = True
            return GoalResponse.ACCEPT

    def execute_program(self, handle):
        result = RunProgram.Result()
        try:
            for index, item in self.prepared:
                reason = self.interrupted(handle)
                if reason:
                    raise RuntimeError(reason)
                op = item['op']
                handle.publish_feedback(RunProgram.Feedback(index=index, instruction=op))
                if op in ('move', 'jog'):
                    self.move(item['target'], handle, self.program_speed)
                elif op == 'set_do':
                    with self.lock:
                        reason = self.interrupted(handle)
                        if reason:
                            raise RuntimeError(reason)
                        self.pendant.do[item['channel']] = item['value']
                elif op == 'wait_di':
                    deadline = time.monotonic()+item['timeout']
                    while True:
                        with self.lock:
                            reason = self.interrupted(handle)
                            ready = self.pendant.di[item['channel']] == item['value']
                        if reason:
                            raise RuntimeError(reason)
                        if ready:
                            break
                        if time.monotonic() > deadline:
                            raise RuntimeError('Digital input wait timed out')
                        time.sleep(.01)
                result.completed += 1
            if self.interrupted(handle):
                raise RuntimeError(self.interrupted(handle))
            result.success, result.message = True, 'Program complete'
            handle.succeed()
        except Exception as exc:
            result.message = str(exc)
            if handle.is_cancel_requested and not self.fault:
                handle.canceled()
            else:
                self.latch(str(exc))
                handle.abort()
        finally:
            with self.lock:
                self.busy = False
        return result

    def execute(self, handle):
        result = RunProtocol.Result()
        run_id = uuid.uuid4().hex
        path = self.log_dir / f'{run_id}-tracking.csv'
        result.log_path = str(path)
        try:
            with self.lock:
                self.log = path.open('w', newline='')
                self.writer = csv.writer(self.log)
                self.writer.writerow(['sim_time_s', 'well', 'phase', 'joint',
                                      'reference_m', 'actual_m', 'error_m'])
            with (self.log_dir / f'{run_id}-dispenses.csv').open('w', newline='') as events:
                doses = csv.writer(events)
                doses.writerow(['well', 'volume_ul', 'simulated'])
                for well in handle.request.wells:
                    with self.lock:
                        current = self.position
                    for phase, target in waypoints(well, current):
                        reason = self.interrupted(handle)
                        if reason:
                            raise RuntimeError(reason)
                        with self.lock:
                            self.well, self.phase = well, phase
                        handle.publish_feedback(RunProtocol.Feedback(
                            well=well, phase=phase, completed_wells=result.completed_wells))
                        self.move(target, handle)
                        if phase == 'lower':
                            # No pump is modelled: this records a simulated dose only after arrival.
                            doses.writerow([well, handle.request.volume_ul, True])
                            events.flush()
                            result.completed_wells += 1
            result.success = True
            result.message = 'simulated protocol complete'
            handle.succeed()
        except Exception as exc:
            result.message = str(exc)
            if handle.is_cancel_requested and not self.fault:
                handle.canceled()
            else:
                self.latch(str(exc))
                handle.abort()
        finally:
            with self.lock:
                self.writer = None
                if self.log:
                    self.log.close()
                self.log = None
                self.busy = False
        return result


def main():
    rclpy.init()
    node = ProtocolServer()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
