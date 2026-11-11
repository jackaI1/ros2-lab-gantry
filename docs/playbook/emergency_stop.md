# emergency_stop

## Symptoms

The run stops and the pendant shows emergency_stop. Outputs turn off.

## Checks

Check the stop input and the recorded input event. Keep clear of the simulated motion area.

## Fix

Clear the emergency_stop input using its SetBool service with data false. Request reset_fault explicitly. Clearing an input alone does not restart.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: ee6f9d3e8e291b0bf31ea9493515295b5c88272ce194da9d5a136febd0f33066
