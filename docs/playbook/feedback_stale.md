# feedback_stale

## Symptoms

The run stops after controller feedback is missing for more than one wall-clock second.

## Checks

Check whether Gazebo is paused, then check /clock and /gantry_controller/controller_state. The wall-clock watchdog still runs when simulation time freezes.

## Fix

Unpause Gazebo and restore the controller publisher. Wait for fresh healthy feedback, then reset. Do not disable the watchdog.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 22612f73232f8f2ae6f65c74ab7ecc4941d3e8fcf6dba90e6ad6dd2a69d22419
