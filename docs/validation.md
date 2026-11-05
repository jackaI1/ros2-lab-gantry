# Validation

The command is `docker run --rm lab-gantry /ws/tools/test.sh`. It runs 22 unit cases and six launch cases against the real Gazebo Harmonic model and position trajectory controller. Colcon reports 30 passing entries because it also includes the two CTest wrappers. There is no mock-hardware substitute in the launch tests.

The [Linux Docker test run on November 5, 2026](https://github.com/jackaI1/ros2-lab-gantry/actions/runs/41976269412) built all three ROS packages and passed those 28 cases. Its two-well protocol recorded 2,550 joint samples, with 0.659 mm peak absolute tracking error and 0.206 mm root-mean-square error across the three axes. These numbers describe this simulation run, not hardware accuracy. The run also completed all three demo wells but exposed a shutdown hang in the original shell wrapper; the process-group cleanup fixes that hang.

The launch cases verify:

1. A1/B2 completion, all eight motion phases, actual axis positions, two dose events, and signed CSV error values.
2. Invalid well/volume rejection, overlapping-goal rejection, cancellation, and a stationary hold afterward.
3. Emergency-stop abort, blocked restart/reset while the input is asserted, and an explicit reset after clearing it.
4. Injected limit-switch abort and reset rules.
5. A measured X-axis endpoint trip caused through the low-level controller, followed by movement back inside the range, reset, and a successful protocol.
6. A paused Gazebo clock triggering the wall-clock feedback watchdog, followed by simulator resume and fault reset.

The workflow also runs the exact documented three-well demo separately and uploads its dose/tracking CSVs and test logs as `simulation-evidence`. The [workflow history](https://github.com/jackaI1/ros2-lab-gantry/actions/workflows/simulation.yml) shows the final results, including runs on `main`.

Local geometry tests passed on macOS. The first local Docker build was stopped after the host ran out of disk space, so full-system validation uses GitHub's Linux runners. The dedicated local VM was stopped and removed, with its processes and forwarding port verified gone.
