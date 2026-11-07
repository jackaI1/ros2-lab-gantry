# overspeed

## Symptoms

The independent C++ monitor publishes a named joint overspeed warning and requests a stop. This is an advisory output; the protocol server does not subscribe to it as an interlock.

## Checks

Read the joint name and measured velocity on /joint_states. The monitor requests a stop above 0.06 m/s in either direction. Normal protocol speed is at most 0.04 m/s, and teach speed is 0.01 m/s. Check whether another trajectory client bypassed the protocol.

## Fix

Cancel the active trajectory in the isolated simulator. Remove the competing client or correct its units and speed. Preserve the measurements and retry a short safe move. Do not raise the warning threshold to hide unexpected motion.

## Confirm recovery

Confirm all joints are inside travel bounds, measured speed is below the threshold, and /gantry/safety_warning returns OK. This monitor is advisory and not a certified hardware safety function.

Contract: aac9389f8c351b0f5fd0f3de8ca37d7eeb1d88d965a8e7a58002ee5771b4852f
