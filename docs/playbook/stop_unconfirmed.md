# stop_unconfirmed

## Symptoms

A controller stop or late stop could not be confirmed.

## Checks

Keep the run stopped. Read the controller response and action status. A pending stop barrier blocks reset and new runs until the late goal reaches a confirmed terminal state. A normal client cancellation waits up to three seconds for a late accepted goal to stop; a timeout becomes a latched stop-unconfirmed fault.

## Fix

Restore the action server and wait for the terminal result. If it cannot be established, restart the isolated simulator. Never bypass the stop barrier to accept another goal.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 61259b67102a541ef6e202c6550c628898aacd5c55c41d6f1ca450a56b5c8ea7
