#!/bin/bash
set -euo pipefail
ros2 launch gantry_control simulation.launch.py log_dir:=/logs &
launch_pid=$!
cleanup() { kill -INT "$launch_pid" 2>/dev/null || true; wait "$launch_pid" || true; }
trap cleanup EXIT
trap 'exit 130' INT TERM
ros2 run gantry_control run_plate "$@"
