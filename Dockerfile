# Stage 1 trains the well-plate detector on CPU and exports ONNX. Linux only; GitHub Actions builds it.
FROM python:3.11-slim-bookworm AS trainer
COPY vision /vision
COPY src/gantry_description/worlds/lab_vision.sdf /world/lab_vision.sdf
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir '/vision[learning]' && \
    python -m gantry_vision.train --output /models --epochs 12 --samples 1200 --world /world/lab_vision.sdf

FROM ros:jazzy-ros-base
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-ros-gz ros-jazzy-gz-ros2-control ros-jazzy-ros2-controllers \
    ros-jazzy-robot-state-publisher ros-jazzy-xacro \
    ros-jazzy-launch-testing-ament-cmake ros-jazzy-launch-testing-ros \
    python3-colcon-common-extensions python3-pytest ros-jazzy-ament-cmake-gtest \
    libegl1 libgl1-mesa-dri && rm -rf /var/lib/apt/lists/*
# Inference only: the node does not need torch.
RUN pip3 install --no-cache-dir --break-system-packages onnxruntime==1.20.1 numpy==1.26.4 opencv-python-headless==4.10.0.84
WORKDIR /ws
COPY src src
RUN source /opt/ros/jazzy/setup.bash && colcon build --event-handlers console_direct+
COPY tools /ws/tools
COPY examples /ws/examples
COPY vision /ws/vision
COPY --from=trainer /models /ws/models
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ENV PYTHONPATH=/ws/vision
ENV GANTRY_PLATE_MODEL=/ws/models/well_detector.onnx
ENTRYPOINT ["/ws/tools/entrypoint.sh"]
CMD ["ros2", "launch", "gantry_control", "simulation.launch.py"]
