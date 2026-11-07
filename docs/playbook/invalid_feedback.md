# invalid_feedback

## Symptoms

A joint, reference or controller feedback message is invalid.

## Checks

Check all three joint names, position lengths and finite numeric values. Compare the message with the versioned controller configuration.

## Fix

Restore the expected x_joint, y_joint, z_joint messages. Restart the isolated simulator if the publisher has incompatible fields, then confirm healthy feedback before reset.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 61259b67102a541ef6e202c6550c628898aacd5c55c41d6f1ca450a56b5c8ea7
