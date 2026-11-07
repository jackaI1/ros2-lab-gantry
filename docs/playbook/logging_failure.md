# logging_failure

## Symptoms

The tracking CSV cannot be written. The run faults rather than continuing without evidence.

## Checks

Check the log directory exists, is writable, and has free space. Preserve completed CSV and event files.

## Fix

Use a writable log_dir and free space by removing only disposable output. Start a new run; do not treat the incomplete CSV as a complete measurement.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: aac9389f8c351b0f5fd0f3de8ca37d7eeb1d88d965a8e7a58002ee5771b4852f
