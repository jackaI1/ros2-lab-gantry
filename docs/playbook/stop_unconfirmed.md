# stop_unconfirmed

## Symptoms

A controller stop or late stop could not be confirmed.

## Checks

Keep the run stopped. Read the controller response and action status. A pending stop barrier blocks reset and new runs until the late goal reaches a confirmed terminal state. A normal client cancellation waits up to three seconds for a late accepted goal to stop; a timeout becomes a latched stop-unconfirmed fault.

## Fix

Restore the action server and wait for the terminal result. If it cannot be established, restart the isolated simulator. Never bypass the stop barrier to accept another goal.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 312725e6d8da27db2eaee841da649aa412121a4f3108047c23c3437a23cdcd85
