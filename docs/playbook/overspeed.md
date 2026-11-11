# overspeed

## Symptoms

The independent C++ monitor publishes a named joint overspeed warning and requests a stop. This is an advisory output; the protocol server does not subscribe to it as an interlock.

## Checks

Read the joint name and measured velocity on /joint_states. The monitor requests a stop above 0.06 m/s in either direction. Normal protocol speed is at most 0.04 m/s, and teach speed is 0.01 m/s. Check whether another trajectory client bypassed the protocol.

## Fix

Cancel the active trajectory in the isolated simulator. Remove the competing client or correct its units and speed. Preserve the measurements and retry a short safe move. Do not raise the warning threshold to hide unexpected motion.

## Confirm recovery

Confirm all joints are inside travel bounds, measured speed is below the threshold, and /gantry/safety_warning returns OK. This monitor is advisory and not a certified hardware safety function.

Contract: ee6f9d3e8e291b0bf31ea9493515295b5c88272ce194da9d5a136febd0f33066
