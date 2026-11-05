#!/bin/bash
set -euo pipefail
colcon test --event-handlers console_direct+ --return-code-on-test-failure
colcon test-result --verbose
