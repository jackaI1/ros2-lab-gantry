# Validation

The command is `docker run --rm lab-gantry /ws/tools/test.sh`. It runs 58 unit cases and ten launch cases against the real Gazebo Harmonic model and position trajectory controller. Colcon also counts CTest wrappers separately from the individual cases. There is no mock-hardware substitute in the launch tests.

The [pendant Docker run](https://github.com/jackaI1/ros2-lab-gantry/actions/runs/42134428069) built all three packages and passed 68 behavioral cases: 58 unit/transport cases and ten real Gazebo cases. Colcon reported 72 entries including four wrappers, with zero errors, failures or skips. The original two-well tracking test recorded 2,673 joint samples, with 0.440 mm peak absolute error and 0.174 mm root-mean-square error. The separate documented demo completed all three wells. These are simulation measurements, not hardware accuracy claims.

Before I added the pendant, the [Linux Docker test run on November 5, 2026](https://github.com/jackaI1/ros2-lab-gantry/actions/runs/41976269412) built all three ROS packages and passed the original 28 cases. Its two-well protocol recorded 2,550 joint samples, with 0.659 mm peak absolute tracking error and 0.206 mm root-mean-square error across the three axes. These numbers describe this simulation run, not hardware accuracy. The run also completed all three demo wells but exposed a shutdown hang in the original shell wrapper; the process-group cleanup fixes that hang.

The launch cases verify:

1. A1/B2 completion, all eight motion phases, actual axis positions, two dose events, and signed CSV error values.
2. Invalid well/volume rejection, overlapping-goal rejection, cancellation, and a stationary hold afterward.
3. Emergency-stop abort, blocked restart/reset while the input is asserted, and an explicit reset after clearing it.
4. Injected limit-switch abort and reset rules.
5. A measured X-axis endpoint trip caused through the low-level controller, followed by movement back inside the range, reset, and a successful protocol.
6. A paused Gazebo clock triggering the wall-clock feedback watchdog, followed by simulator resume and fault reset.
7. Measured joint/world/tool jogging, teaching three points with offsets, one-instruction teach replay, complete auto replay, sensor release, outputs and motion/configuration exclusivity.
8. E-stop during taught motion in both modes, blocked restart, stationary hold, outputs cleared, input timeout, E-stop during a wait and cancellation of a wait.
9. Full-program rejection before output changes when a target enters tooling, plus malformed commands and oversized numeric inputs without losing the server.
10. The installed pendant CLI receiving Ctrl-C during a real ROS input wait, confirming cancellation before exit, and leaving the server idle without a fault.

The numerical cases also check straight paths crossing or touching the tooling box with clear endpoints, frame-specific offsets, triangular and trapezoidal profiles, velocity continuity and acceleration limits. Controller-transport tests cover interruption before acceptance, bounded timeout, late cancellation, and reset remaining blocked until a terminal result confirms the stop. These transport tests control only the acknowledgement boundary; the launch tests use real Gazebo motion.

The workflow also runs the exact documented three-well demo separately and uploads its dose/tracking CSVs and test logs as `simulation-evidence`. The [workflow history](https://github.com/jackaI1/ros2-lab-gantry/actions/workflows/simulation.yml) shows the final results, including runs on `main`.

All 58 local numerical and controller-transport cases passed on macOS. The original local Docker build was stopped after the host ran out of disk space, so full-system validation uses GitHub's Linux runners. That dedicated local VM was stopped and removed, with its processes and forwarding port verified gone.

For the pendant extension, the local Docker daemon was unavailable, so full-system execution runs on GitHub Actions while the numerical and transport cases also run locally.
