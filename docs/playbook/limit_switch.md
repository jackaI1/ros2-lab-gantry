# limit_switch

## Symptoms

A limit_switch or named joint limit message stops motion.

## Checks

Read the joint name and the preceding actual_m values. X, Y and Z travel end at 220, 160 and 80 mm. The switch margin is 0.5 mm. Check whether the injected limit input is still true.

## Fix

Clear an injected switch. For a position-derived switch, restore a safe position in the isolated simulator before reset. Check the taught point or plate move. Do not enlarge limits to hide a bad target.

## Confirm recovery

Confirm the input is clear, feedback is fresh, the robot is idle and the fault reset succeeds. Run a short safe move and inspect its new tracking CSV. This simulation stop is not a certified hardware safety function.

Contract: 99c0dcb38bbbe65e1d3392989abe5b9d3e361315f19527a98cfd5e977d87a8db
