FROM ros:jazzy-ros-base
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-ros-gz ros-jazzy-gz-ros2-control ros-jazzy-ros2-controllers \
    ros-jazzy-robot-state-publisher ros-jazzy-xacro \
    ros-jazzy-launch-testing-ament-cmake ros-jazzy-launch-testing-ros \
    python3-colcon-common-extensions python3-pytest && rm -rf /var/lib/apt/lists/*
WORKDIR /ws
COPY src src
RUN source /opt/ros/jazzy/setup.bash && colcon build --event-handlers console_direct+
COPY tools /ws/tools
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ENTRYPOINT ["/ws/tools/entrypoint.sh"]
CMD ["ros2", "launch", "gantry_control", "simulation.launch.py"]
