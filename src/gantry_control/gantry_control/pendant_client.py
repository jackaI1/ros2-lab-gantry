"""Command-line teach pendant; all motion goes through the cancellable server."""
import argparse
import json
import signal
from pathlib import Path
import rclpy
from rclpy.action import ActionClient
from rclpy.signals import SignalHandlerOptions
from gantry_interfaces.action import RunProgram
from gantry_interfaces.srv import PendantCommand


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='op', required=True)
    sub.add_parser('status')
    mode = sub.add_parser('mode')
    mode.add_argument('mode', choices=['teach','auto'])
    for name in ('record','delete'):
        p = sub.add_parser(name)
        p.add_argument('name')
        if name == 'record':
            p.add_argument('--frame', choices=['joint','world','tool'], default='joint')
            p.add_argument('--offset', nargs=3, type=float, default=[0,0,0])
    di = sub.add_parser('di')
    di.add_argument('channel', type=int)
    di.add_argument('value', choices=['true','false'])
    jog = sub.add_parser('jog')
    jog.add_argument('frame', choices=['joint','world','tool'])
    jog.add_argument('delta', nargs=3, type=float)
    run = sub.add_parser('run')
    run.add_argument('file', type=Path)
    run.add_argument('--step', type=int, default=0)
    args = parser.parse_args()
    # Keep ROS alive long enough to cancel and confirm the active action on Ctrl-C.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)

    def interrupt(signum, frame):
        raise KeyboardInterrupt()

    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    node = rclpy.create_node('pendant_client')
    client = goal = pending = None

    def wait(future, timeout):
        rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
        if not future.done():
            raise RuntimeError('ROS response timed out')
        return future.result()

    try:
        if args.op in ('jog','run'):
            instructions = ([{'op':'jog','frame':args.frame,'delta':args.delta}]
                            if args.op == 'jog' else json.loads(args.file.read_text()))
            client = ActionClient(node, RunProgram, '/gantry/pendant/run')
            if not client.wait_for_server(timeout_sec=15):
                raise RuntimeError('Start the simulator first')
            pending = client.send_goal_async(RunProgram.Goal(
                instructions_json=json.dumps(instructions), step=getattr(args,'step',0)),
                feedback_callback=lambda msg: print(
                    f'{msg.feedback.index}: {msg.feedback.instruction}', flush=True))
            goal = wait(pending, 10)
            if not goal.accepted:
                raise RuntimeError('Program rejected; inspect pendant status and server output')
            future = goal.get_result_async()
            while not future.done():
                rclpy.spin_once(node, timeout_sec=.1)
            result = future.result().result
            print(f'{result.message}; completed={result.completed}')
            if not result.success:
                raise RuntimeError(result.message)
        else:
            command = vars(args).copy()
            if args.op == 'di':
                command['value'] = args.value == 'true'
            client = node.create_client(PendantCommand, '/gantry/pendant/command')
            if not client.wait_for_service(timeout_sec=15):
                raise RuntimeError('Start the simulator first')
            response = wait(client.call_async(PendantCommand.Request(json=json.dumps(command))),10)
            print(json.dumps(json.loads(response.state_json), indent=2))
            if not response.success:
                raise RuntimeError(response.message)
    except KeyboardInterrupt:
        if goal is None and pending is not None:
            goal = wait(pending, 10)
        if goal is not None and goal.accepted:
            wait(goal.cancel_goal_async(), 5)
            wait(goal.get_result_async(), 8)
        raise SystemExit(130)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f'{exc}\n')
    finally:
        if isinstance(client, ActionClient):
            client.destroy()
        elif client is not None:
            node.destroy_client(client)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
