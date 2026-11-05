#!/usr/bin/env python3
"""Run a protocol and always reap the simulator's owned process group."""
import os
import signal
import subprocess
import sys


def stop(process):
    if process is None:
        return
    # The process is a session leader. Its group contains only this demo's children.
    for sig, grace in [(signal.SIGINT, 12), (signal.SIGTERM, 5), (signal.SIGKILL, 5)]:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue
        # Reap the leader and terminate any remaining descendants in its owned group.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        break
    process.wait(timeout=5)


def main():
    simulator = client = None
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        simulator = subprocess.Popen(['ros2', 'launch', 'gantry_control',
            'simulation.launch.py', 'log_dir:=/logs'], start_new_session=True)
        print(f'Demo owns simulator process group {simulator.pid}; no host ports', flush=True)
        client = subprocess.Popen(['ros2', 'run', 'gantry_control', 'run_plate', *sys.argv[1:]],
                                  start_new_session=True)
        return client.wait(timeout=1200)
    except KeyboardInterrupt:
        return 130
    except subprocess.TimeoutExpired:
        print('Demo timed out', file=sys.stderr)
        return 1
    finally:
        stop(client)
        stop(simulator)


if __name__ == '__main__':
    sys.exit(main())
