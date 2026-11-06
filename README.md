I built a simulated lab pipetting robot because I wanted a way to check plate motion and failure recovery without a physical robot. It moves a pipette over a 96-well plate, visits the wells I choose, and records where the three moving axes actually went compared with where I asked them to go.

This is a **simulation**, with no hardware connection. Each dispense is a recorded event with a well name and volume; it does not simulate liquid flow or prove dispensing accuracy. The robot lifts before moving sideways, lowers at each well, records the dose, and lifts again. I can also teach named positions by jogging the robot, replay a small program, wait for a simulated sensor, and switch a simulated output. I use this to check a motion sequence around fixed equipment before putting it into a plate routine. I can cancel a run or trigger an emergency stop to check how it stops.

To try it, install Docker with a running Linux container engine, then run:

```sh
git clone https://github.com/jackaI1/ros2-lab-gantry.git
cd ros2-lab-gantry
docker build -t lab-gantry .
mkdir -p logs
docker run --rm --name gantry-demo -v "$PWD/logs:/logs" lab-gantry \
  /ws/tools/demo.sh --wells A1 A2 B2 --volume 50
```

The first build downloads the robot software and can take several minutes. The demo runs without a window, prints each motion phase, saves CSV files in `logs/`, and stops the simulator when it finishes. `--volume` is in microlitres, up to 200 per well. Wells run in the order supplied, from A1 through H12. Duplicate wells and invalid volumes are rejected before motion.

## What I can inspect

Each run produces two files with a shared random run identifier:

- `*-dispenses.csv`: the wells actually reached, requested volumes, and a flag saying the dispense was simulated. A dose counts after lowering finishes, even if a later retract is interrupted.
- `*-tracking.csv`: simulation time, well, motion phase, joint, requested position, measured position, and signed error in metres. Error is requested minus measured position, rather than distance from the final destination.

I use the tracking file to see lag during a move and check whether the robot settles at a well. These are simulation measurements, not calibration results for a real machine.

## Run it interactively

ROS 2 passes messages between the simulator, controller, and protocol runner. An action is a request that reports progress and can be canceled. To leave the simulation running for experiments:

```sh
docker run --rm -it --name gantry-sim -v "$PWD/logs:/logs" lab-gantry \
  ros2 launch gantry_control simulation.launch.py log_dir:=/logs
```

In another terminal:

```sh
docker exec gantry-sim /ws/tools/entrypoint.sh \
  ros2 run gantry_control run_plate --wells A1 H12 --volume 25

# Trigger the simulated emergency stop while a protocol is moving.
docker exec gantry-sim /ws/tools/entrypoint.sh \
  ros2 service call /gantry/emergency_stop std_srvs/srv/SetBool '{data: true}'

# Clear the input, then explicitly reset the latched fault.
docker exec gantry-sim /ws/tools/entrypoint.sh \
  ros2 service call /gantry/emergency_stop std_srvs/srv/SetBool '{data: false}'
docker exec gantry-sim /ws/tools/entrypoint.sh \
  ros2 service call /gantry/reset_fault std_srvs/srv/Trigger '{}'
```

`/gantry/limit_switch` has the same boolean service interface for testing a switch trip. `/gantry/fault` reports the current fault or `OK`. Stop the interactive simulator with Ctrl-C or `docker stop gantry-sim`.

For the raw action interface, including feedback:

```sh
docker exec gantry-sim /ws/tools/entrypoint.sh \
  ros2 action send_goal /gantry/run_protocol gantry_interfaces/action/RunProtocol \
  '{wells: [A1, B2], volume_ul: 50.0}' --feedback
```

## Teach a motion sequence

I use the command-line pendant, a set of controls for moving the robot and remembering positions. A taught point is a named location captured from the robot's measured position. I can add a small offset, an adjustment in metres, without changing the original location.

Start the interactive simulator above. From another terminal, copy the example program into the container and teach its two locations:

```sh
docker cp examples/taught-cycle.json gantry-sim:/tmp/cycle.json
# The commands below run inside the simulator container.
docker exec -it gantry-sim /ws/tools/entrypoint.sh bash
ros2 run gantry_control pendant mode teach
ros2 run gantry_control pendant jog joint 0.005 0 0
ros2 run gantry_control pendant jog world 0 0.005 0
ros2 run gantry_control pendant jog tool 0 0 0.005
ros2 run gantry_control pendant record approach --frame world
ros2 run gantry_control pendant jog tool 0 0 0.010
ros2 run gantry_control pendant record dispense --frame tool --offset 0 0 0.001
ros2 run gantry_control pendant status
```

The three frames are directions for interpreting a move. **Joint** follows the three slides, with positive Z going down. **World** follows the room, with positive Z going up. **Tool** follows the fixed pipette: X points along world X, Y points opposite world Y, and Z points down the tip. The pipette cannot rotate, so tool orientation stays fixed. Each jog is limited to 10 mm per axis.

Teach mode runs one instruction I select, at up to 10 mm/s. Auto mode runs the whole program, at up to 40 mm/s. Instructions are numbered from zero:

```sh
# Still inside the container: try only the approach move in teach mode.
ros2 run gantry_control pendant run /tmp/cycle.json --step 1
# Auto waits at instruction zero until I simulate a ready sensor.
ros2 run gantry_control pendant di 0 true
ros2 run gantry_control pendant mode auto
ros2 run gantry_control pendant run /tmp/cycle.json
ros2 run gantry_control pendant status
exit
```

The program waits for digital input 0 (a simulated on/off sensor), visits the approach and dispense points, turns digital output 1 on, retracts, then turns it off. Outputs are simulated on/off signals, not a pump or a physical controller. I can leave input 0 false to see the program wait, then change it from another terminal. Ctrl-C cancels a running program. The emergency-stop and reset commands above work in both modes, including during an input wait; faults turn all outputs off. Clearing the stop never resumes motion.

Points stay in the running server until it stops. Duplicate names are rejected; `pendant delete dispense` removes a point so I can teach it again. Point offsets use the frame chosen when recording. A move can add another offset in that same frame. I keep the JSON instruction file separately so the sequence is repeatable after teaching.

A red fixed tool stand occupies the far corner of the simulated work area. Before moving, I check the entire straight path against an interference zone around that stand, including clearance for the pipette body. Clear endpoints alone are not enough. I must teach a raised approach to go over it. Auto checks the whole program before any output changes, and all motion is checked again against current measured positions. The plate runner uses the same check and the same motion slot, so it cannot run alongside the pendant. See [the pendant reference](docs/pendant.md) for the program format and boundaries.

## How I arranged the robot

The URDF, an XML description of the robot's parts and joints, defines three sliding axes: X travels 220 mm, Y travels 160 mm, and Z travels 80 mm downward. Gazebo Harmonic runs the model's physics. The `gz_ros2_control` plugin connects its measured joint positions to `ros2_control`, which provides the controller interface. A position-based trajectory controller follows timed moves for all three joints together.

My protocol server sends each lift, sideways move, lower, and retract as a separate controller action. It only records a simulated dispense after the lower action succeeds. A plate has 9 mm well spacing, with A1 at X = 40 mm and Y = 35 mm. Travel uses Z = 10 mm; dispensing uses Z = 60 mm. All plate and pendant moves use a trapezoidal speed profile: accelerate, travel at steady speed, then slow to a stop. Short moves use a triangular profile with no steady-speed section. The axes move together along a straight path, with acceleration limited to 80 mm/s².

The server rejects overlapping runs and watches measured positions for six end-of-travel switches. It also latches an emergency stop, an injected limit switch, stale controller feedback, and sustained tracking error. A fault cancels the active trajectory and prevents another protocol until the fault input is clear and I reset it. A wall-clock watchdog still runs when simulation time stops. More detail, including the boundaries of this stop behavior, is in [the design notes](docs/design.md).

## Tests and CI

```sh
docker run --rm --name gantry-test lab-gantry /ws/tools/test.sh
```

The test suite builds and runs the real Gazebo model. The 52 unit cases check plate geometry, safe move ordering, invalid inputs, all axis limits, frame directions, point offsets, full-path tooling checks, and speed and acceleration limits. Ten launch cases bring up the full system and check a two-well run, measured motion and tracking CSVs, cancellation, overlapping goals, emergency stop, injected and position-derived limit trips, recovery, paused-simulator feedback loss, measured pendant jogging and replay, teach stepping, digital input waits, digital outputs, E-stop in both pendant modes, and rejected unsafe programs.

GitHub Actions builds the Docker image and runs the same tests on Linux for pull requests and commits to `main`. I keep the container headless so the tests need neither a display nor a GPU. The detailed test count and measured tracking results are recorded in [validation](docs/validation.md).
