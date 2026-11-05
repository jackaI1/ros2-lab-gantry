# Validation

The CI command is `docker run --rm lab-gantry /ws/tools/test.sh`. It builds on the image's three compiled ROS packages and runs unit tests plus launch tests against Gazebo Harmonic and the position trajectory controller. There is no mock-hardware substitute in these launch tests.

Local measurements and the final CI links are added after the full run completes.
