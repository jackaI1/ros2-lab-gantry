# Simulation design

## Packages and message flow

`gantry_description` installs the URDF, headless Gazebo world, and controller configuration. `gantry_interfaces` generates the `RunProtocol` ROS action. `gantry_control` installs the Python server, command-line client, launch file, and tests.

```text
RunProtocol client -> protocol server -> FollowJointTrajectory action
                                           |
                                 joint_trajectory_controller
                                           |
                                    gz_ros2_control
                                           |
                                  Gazebo sliding joints
                                           |
               CSV logger <--- controller_state feedback
```

Gazebo owns the controller manager. The joint-state broadcaster publishes the joint state, and the robot-state publisher publishes the model's transforms. A bridge supplies simulation time. The protocol server deliberately uses wall time for health deadlines, because a paused simulator cannot advance a simulation-time watchdog.

## Protocol and dimensions

Only a dispense schedule is modelled. There is no aspiration, pump, tip exchange, reservoir, fluid solver or volume calibration. The plate is a visual reference, not a detailed collision mesh of each well. The tip stops above the plate surface. A simulated dose is an event after the lower move reaches its target, and the server flushes a separate dispense CSV immediately.

Plate coordinates are fixed, not camera-derived. X = 0.040 + 0.009(column - 1), Y = 0.035 + 0.009(row - A), in metres. Each well uses lift, travel, lower, retract. Only the travel segment changes X/Y, and that segment runs at the raised Z. Initial simulated positions are X/Y = 0.020 m and Z = 0.010 m, away from switches. This is a known simulation starting state, not a physical homing routine.

The shared trajectory planner uses a synchronized trapezoidal velocity profile with 0.04 m/s maximum axis speed and 0.08 m/s² acceleration. Teach mode limits speed to 0.01 m/s. Short moves are triangular. Position and velocity knots at zero, acceleration end, cruise end and arrival let the controller reproduce each quadratic or linear position segment through cubic interpolation, with continuous velocity. Acceleration changes at the phase boundaries; jerk is not limited. Position commands are converted into simulator joint motion by the Gazebo plugin's proportional position behavior. I use a gain of 0.5 at 100 Hz, below the plugin's documented no-oscillation bound of 1. This is not a tuned motor/drive model. The URDF supplies masses, inertia, collisions, damping and travel limits. Simulation tracking error should not be interpreted as expected hardware precision.

## Fault state and cancellation

The server reserves its single-run slot during goal acceptance under a lock. The executor has four threads so state updates, fault services and the nested controller action can run while a protocol waits. Invalid well names, repeated wells, non-finite or out-of-range volume, missing feedback, existing faults, and concurrent runs are rejected before executing.

Measured joint positions within 0.5 mm of either mechanical travel endpoint trip a virtual switch. `/gantry/limit_switch` lets me inject a switch trip independently. `/gantry/emergency_stop` is another simulated boolean input. Both latch until cleared and reset. Error above 15 mm for more than 0.5 seconds, invalid feedback, feedback older than one wall-clock second during a protocol, controller rejection, and trajectory failure also latch faults.

The execution loop asks the controller to cancel on fault or client cancel, waits for its cancellation response and terminal result, then reports the protocol aborted or canceled. The controller's cancellation behavior holds the current position, so cancellation does not automatically retract the pipette. A stop that cannot be confirmed becomes its own latched fault. Reset requires no running protocol, both injected inputs clear, recent feedback, and measured positions inside the switches. Protocol progress is never automatically resumed.

These are application-level simulation interlocks, not safety-rated emergency stops. Direct access to the controller can bypass the protocol. The limit test deliberately does this to prove that measured positions trigger the switches; the server prevents subsequent protocols but does not claim to govern arbitrary external controller clients. If Gazebo itself is stalled, the server can detect that and request cancellation, but cannot make an unresponsive simulator move or hold. It reports an unconfirmed stop if the controller does not respond. There is no physical safety claim.

## Tracking data

The controller publishes the interpolated position reference and measured position in each `controller_state` message. For every sample the logger writes one row per joint and calculates `error_m = reference_m - actual_m`. CSV rows include the controller's simulation timestamp and the current well/phase. A random run identifier prevents file collisions. The log path is returned in the action result, including a failed or canceled result. Logging I/O failures abort the protocol; these short educational runs do not use a real-time logging pipeline.

## Dependencies

The container uses ROS 2 Jazzy on Ubuntu 24.04 and its supported Gazebo Harmonic pairing. I followed the [Gazebo control integration documentation](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html) and the [trajectory controller interface](https://control.ros.org/jazzy/doc/ros2_controllers/joint_trajectory_controller/doc/userdoc.html). Package versions come from the ROS apt repository when the image is built, so the image is not a bit-for-bit locked environment.

## Pendant programs

The [pendant reference](pendant.md) describes the frames, program preflight, simulated I/O, mode handling and fixed tooling geometry. The original plate action and the pendant action share the same server lock, busy reservation, watchdog, fault latch and cancellable controller move function. No second controller client is created for the pendant.
