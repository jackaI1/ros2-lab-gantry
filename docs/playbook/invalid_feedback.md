# invalid_feedback

## Symptoms

A joint, reference or controller feedback message is invalid.

## Checks

Check all three joint names, position lengths and finite numeric values. Compare the message with the versioned controller configuration.

## Fix

Restore the expected x_joint, y_joint, z_joint messages. Restart the isolated simulator if the publisher has incompatible fields, then confirm healthy feedback before reset.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: ee6f9d3e8e291b0bf31ea9493515295b5c88272ce194da9d5a136febd0f33066
