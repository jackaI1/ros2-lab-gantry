# logging_failure

## Symptoms

The tracking CSV cannot be written. The run faults rather than continuing without evidence.

## Checks

Check the log directory exists, is writable, and has free space. Preserve completed CSV and event files.

## Fix

Use a writable log_dir and free space by removing only disposable output. Start a new run; do not treat the incomplete CSV as a complete measurement.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 312725e6d8da27db2eaee841da649aa412121a4f3108047c23c3437a23cdcd85
