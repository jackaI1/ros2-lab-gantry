# Pendant reference

I use the pendant to teach a fixture approach, check it slowly one instruction at a time, and replay the same sequence at normal speed. It runs on the real Gazebo joint controller, not a separate numerical robot.

## Program and commands

`ros2 run gantry_control pendant` prints its subcommands. `run FILE --step N` sends a cancellable `/gantry/pendant/run` action. In teach mode it executes instruction N only. In auto mode N must be zero and the whole list runs. Mode changes, recording and deletion are blocked while either a plate or pendant action owns motion. Jogging and recording require teach mode. Programs contain 1 to 256 instructions.

| Instruction | Required fields | Meaning |
| --- | --- | --- |
| `move` | `point` | Move to a taught point; optional three-number `offset` in its recorded frame |
| `jog` | `frame`, `delta` | Teach-only relative motion, three numbers, at most 0.010 m per axis |
| `wait_di` | `channel`, `value`, `timeout` | Wait for simulated input 0 to 7, boolean value, wall-clock timeout above 0 and at most 300 s |
| `set_do` | `channel`, `value` | Set simulated output 0 to 7 to a boolean value |

See [the complete cycle](../examples/taught-cycle.json). I teach `approach` and `dispense` before running it. `pendant di 0 true` injects a sensor input. `pendant status` reports measured position, remembered points, mode, all eight inputs and outputs, busy state and the latched fault. `/gantry/pendant/state` also publishes that JSON state at 20 Hz. `/gantry/pendant/command` accepts JSON commands for status, mode, record, delete and input changes. Raw service example:

```sh
ros2 service call /gantry/pendant/command gantry_interfaces/srv/PendantCommand \
  '{json: "{\"op\":\"status\"}"}'
```

An input wait holds the program's motion slot even though the axes are stationary. Input changes remain available during a run. A timeout aborts the program, latches a fault, leaves later instructions unexecuted and turns outputs off. Cancellation stops the active trajectory or wait, with no automatic resume. Normal cancellation leaves outputs at their last explicitly programmed values; an emergency stop or other latched fault clears them. Reset requires clear stop inputs, idle motion and recent healthy position feedback.

## Coordinates and taught points

Positions and offsets use metres. Joint coordinates are `(qx,qy,qz)`; the URDF's Z slide points downward. The pipette tip in world coordinates is `(qx,qy,0.095-qz)`. The 0.095 m comes from the fixed joint origins and half of the 0.10 m pipette length. Tool orientation is a fixed 180-degree rotation about world X: its positive Y points opposite world Y and its positive Z points down. This is a right-handed coordinate frame attached to the nonrotating pipette. There are no orientation jogs or rotary joints.

For a displacement `(a,b,c)`, joint increments are `(a,b,c)` in joint mode, `(a,b,-c)` in world mode and `(a,-b,c)` in tool mode. I store the measured joint position, selected frame and converted record-time offset together. Replay adds the stored offset and any per-move offset to the measured taught position. Offsets are displacements, so the world origin translation does not apply. Points live in memory for one simulator session, avoiding accidental reuse of positions after a fixture setup changes.

## Fixed tooling and motion

The visible stand spans world X 0.170 to 0.200 m, Y 0.110 to 0.140 m and Z 0.020 to 0.065 m. The exclusion region in joint coordinates spans `(0.164,0.104,0.024)` to `(0.206,0.146,0.0795)`. It expands X/Y by 6 mm and includes every reachable Z position where the pipette body could overlap the stand. The 6 mm combines the 4 mm pipette half-width with 2 mm clearance. The initial plate layout remains outside this region.

A closed-segment slab intersection rejects crossings and touches, even when both endpoints are outside the box. Preflight checks every selected path before execution; the move function rechecks from current measured feedback immediately before sending a trajectory. It rejects axis-switch margins as well. This is a fixed-fixture interlock, not a general collision planner. It does not discover obstacles, route around them or model all robot-link collisions.

All three slides share a normalized progress function. The longest-moving slide sets duration; shorter slides scale their velocity to arrive together. Acceleration and deceleration are 0.08 m/s² or less; speed is at most 0.010 m/s in teach and 0.040 m/s in auto and plate motion. Zero endpoint velocities keep position and velocity continuous. The [controller's position-plus-velocity cubic interpolation](https://control.ros.org/jazzy/doc/ros2_controllers/joint_trajectory_controller/doc/trajectory.html) reproduces the quadratic ramps between phase knots. Acceleration steps at phase boundaries, so this is not jerk-limited motion.

These are application-level simulation checks. There is no safety-rated hardware E-stop, physical digital wiring, held-to-run enabling switch, physical teach pendant, homing or tooling calibration. A direct low-level controller client can bypass this server. A stalled simulator cannot guarantee a physical stop. I use this to test programming decisions, not to validate a real robot's safety.

If a stop arrives before the controller acknowledges a motion request, I report the stop as unconfirmed, cancel the goal as soon as its acknowledgement arrives, and block fault reset until rejection or a confirmed terminal result. Lost transport leaves reset blocked rather than assuming the command disappeared.
