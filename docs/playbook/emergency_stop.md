# emergency_stop

## Symptoms

The run stops and the pendant shows emergency_stop. Outputs turn off.

## Checks

Check the stop input and the recorded input event. Keep clear of the simulated motion area.

## Fix

Clear the emergency_stop input using its SetBool service with data false. Request reset_fault explicitly. Clearing an input alone does not restart.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 61259b67102a541ef6e202c6550c628898aacd5c55c41d6f1ca450a56b5c8ea7
