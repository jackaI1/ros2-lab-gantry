# tracking_error

## Symptoms

Requested and measured positions differ by more than 15 mm for over 0.5 seconds.

## Checks

Read reference_m, actual_m and error_m before the event. Check controller state and whether another client sent motion. Check speed and acceleration limits.

## Fix

Stop other trajectory clients. Restore the standard controller configuration and retry a short safe move after reset. Investigate a repeat before running a full plate.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: ee6f9d3e8e291b0bf31ea9493515295b5c88272ce194da9d5a136febd0f33066
