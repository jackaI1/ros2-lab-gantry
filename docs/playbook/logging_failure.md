# logging_failure

## Symptoms

The tracking CSV cannot be written. The run faults rather than continuing without evidence.

## Checks

Check the log directory exists, is writable, and has free space. Preserve completed CSV and event files.

## Fix

Use a writable log_dir and free space by removing only disposable output. Start a new run; do not treat the incomplete CSV as a complete measurement.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: ee6f9d3e8e291b0bf31ea9493515295b5c88272ce194da9d5a136febd0f33066
