# stop_unconfirmed

## Symptoms

A controller stop or late stop could not be confirmed.

## Checks

Keep the run stopped. Read the controller response and action status. A pending stop barrier blocks reset until the late goal reaches a confirmed terminal state.

## Fix

Restore the action server and wait for the terminal result. If it cannot be established, restart the isolated simulator. Never bypass the stop barrier to accept another goal.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 22612f73232f8f2ae6f65c74ab7ecc4941d3e8fcf6dba90e6ad6dd2a69d22419
