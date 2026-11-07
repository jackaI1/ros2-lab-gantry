# feedback_stale

## Symptoms

The run stops after controller feedback is missing for more than one wall-clock second.

## Checks

Check whether Gazebo is paused, then check /clock and /gantry_controller/controller_state. The wall-clock watchdog still runs when simulation time freezes.

## Fix

Unpause Gazebo and restore the controller publisher. Wait for fresh healthy feedback, then reset. Do not disable the watchdog.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 99c0dcb38bbbe65e1d3392989abe5b9d3e361315f19527a98cfd5e977d87a8db
