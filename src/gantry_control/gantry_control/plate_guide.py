"""Use the overhead camera to find where the plate really is, then run RunProtocol there.

The decision logic is plain Python so it can be unit tested without ROS. The ROS parts are
imported only inside main(). When the camera is unsure, the protocol runs at the taught pose.
"""
from dataclasses import dataclass
import math
import statistics
import time

from gantry_control.protocol import validate, validate_pose

MIN_CONFIDENCE = 0.8     # same threshold as gantry_vision.inference.DEFAULT_MIN_CONFIDENCE
MAX_AGE_S = 2.0          # an estimate older than this does not describe the plate any more
FRAMES_NEEDED = 5        # agreeing frames required before the camera is trusted
AGREE_MM = 1.5           # frames must agree within this spread...
AGREE_DEG = 0.5          # ...and this turn


@dataclass(frozen=True)
class PlatePose:
    offset_x_m: float
    offset_y_m: float
    yaw_rad: float
    confidence: float
    stamp: float         # monotonic seconds when the frame arrived


@dataclass(frozen=True)
class Choice:
    offset_x_m: float
    offset_y_m: float
    yaw_rad: float
    source: str          # 'camera' or 'taught'
    reason: str


def taught(reason):
    return Choice(0.0, 0.0, 0.0, 'taught', reason)


def choose_pose(history, now, min_confidence=MIN_CONFIDENCE):
    """Pick the plate pose for the next run from recent frames, newest last.

    The camera is used only when the last FRAMES_NEEDED frames are all recent, confident,
    inside the allowed plate move and agree with each other. Otherwise the taught pose is used.
    """
    recent = [p for p in history if now - p.stamp <= MAX_AGE_S]
    if len(recent) < FRAMES_NEEDED:
        return taught(f'{len(recent)} of {FRAMES_NEEDED} recent camera frames')
    frames = recent[-FRAMES_NEEDED:]
    weakest = min(p.confidence for p in frames)
    if weakest < min_confidence:
        return taught(f'camera confidence {weakest:.2f} is below {min_confidence:.2f}')
    for p in frames:
        try:
            validate_pose(p.offset_x_m, p.offset_y_m, p.yaw_rad)
        except ValueError as exc:
            return taught(f'camera estimate rejected: {exc}')
    spread_mm = 1000 * max(math.hypot(a.offset_x_m - b.offset_x_m, a.offset_y_m - b.offset_y_m)
                           for a in frames for b in frames)
    turn_deg = math.degrees(max(abs(a.yaw_rad - b.yaw_rad) for a in frames for b in frames))
    if spread_mm > AGREE_MM or turn_deg > AGREE_DEG:
        return taught(f'camera frames disagree by {spread_mm:.1f} mm and {turn_deg:.2f} deg')
    return Choice(statistics.median(p.offset_x_m for p in frames),
                  statistics.median(p.offset_y_m for p in frames),
                  statistics.median(p.yaw_rad for p in frames), 'camera', 'frames agree')


def frame_to_bgr(data, height, width, step, encoding):
    """Convert a ROS image's bytes to a BGR array, as used by OpenCV and the detector."""
    import numpy as np
    rows = np.frombuffer(bytes(data), np.uint8).reshape(height, step)[:, :width * 3].reshape(height, width, 3)
    if encoding == 'rgb8':
        return rows[:, :, ::-1].copy()
    if encoding == 'bgr8':
        return rows.copy()
    raise ValueError(f'Unsupported camera encoding {encoding}')


def main(argv=None):
    import argparse
    import os
    import numpy as np
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from gantry_interfaces.action import RunProtocol
    from gantry_vision.inference import PlateDetector

    parser = argparse.ArgumentParser(description='Run a dispense protocol at the plate position the camera sees')
    parser.add_argument('--wells', nargs='+', default=['A1', 'A2', 'B2'])
    parser.add_argument('--volume', type=float, default=50.0)
    parser.add_argument('--model', default=os.environ.get('GANTRY_PLATE_MODEL', '/ws/models/well_detector.onnx'))
    parser.add_argument('--image-topic', default='/overhead/image')
    parser.add_argument('--timeout', type=float, default=15.0)
    parser.add_argument('--once', action='store_true', help='print the decision and do not move the gantry')
    args = parser.parse_args(argv)

    detector = PlateDetector(args.model)
    history = []
    rclpy.init()
    node = Node('plate_guide')
    try:
        def frame(msg):
            image = frame_to_bgr(msg.data, msg.height, msg.width, msg.step, msg.encoding)
            found = detector.detect(image)
            history.append(PlatePose(found.offset_x_m, found.offset_y_m, found.yaw_rad,
                                     found.confidence, time.monotonic()))
            del history[:-20]
        node.create_subscription(Image, args.image_topic, frame, 5)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and len(history) < FRAMES_NEEDED:
            rclpy.spin_once(node, timeout_sec=0.1)
        choice = choose_pose(history, time.monotonic())
        print(f'plate pose from {choice.source}: x={choice.offset_x_m * 1000:.2f} mm '
              f'y={choice.offset_y_m * 1000:.2f} mm yaw={math.degrees(choice.yaw_rad):.2f} deg ({choice.reason})',
              flush=True)
        if args.once:
            return
        validate(args.wells, args.volume, choice.offset_x_m, choice.offset_y_m, choice.yaw_rad)
        client = ActionClient(node, RunProtocol, '/gantry/run_protocol')
        if not client.wait_for_server(timeout_sec=90):
            raise SystemExit('Protocol server not found')
        goal = client.send_goal_async(
            RunProtocol.Goal(wells=args.wells, volume_ul=args.volume, offset_x_m=choice.offset_x_m,
                             offset_y_m=choice.offset_y_m, yaw_rad=choice.yaw_rad),
            feedback_callback=lambda msg: print(f'{msg.feedback.well}: {msg.feedback.phase}', flush=True))
        rclpy.spin_until_future_complete(node, goal, timeout_sec=10)
        if not goal.done() or not goal.result().accepted:
            raise SystemExit('Protocol rejected: check wells, volume, controller readiness and latched faults')
        result = goal.result().get_result_async()
        rclpy.spin_until_future_complete(node, result)
        report = result.result().result
        print(f'{report.message}; completed={report.completed_wells}; tracking={report.log_path}')
        if not report.success:
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
