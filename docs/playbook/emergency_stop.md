# emergency_stop

## Symptoms

The run stops and the pendant shows emergency_stop. Outputs turn off.

## Checks

Check the stop input and the recorded input event. Keep clear of the simulated motion area.

## Fix

Clear the emergency_stop input using its SetBool service with data false. Request reset_fault explicitly. Clearing an input alone does not restart.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: aac9389f8c351b0f5fd0f3de8ca37d7eeb1d88d965a8e7a58002ee5771b4852f
