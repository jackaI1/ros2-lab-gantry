import math

import numpy as np
import pytest

from gantry_control.plate_guide import (FRAMES_NEEDED, MAX_AGE_S, MIN_CONFIDENCE, PlatePose,
                                        choose_pose, frame_to_bgr)

NOW = 100.0


def frame(x=0.001, y=-0.002, yaw=0.01, confidence=0.95, age=0.1):
    return PlatePose(x, y, yaw, confidence, NOW - age)


def run(frames):
    return choose_pose(frames, NOW)


def test_no_frames_uses_taught_pose():
    choice = run([])
    assert choice.source == 'taught' and (choice.offset_x_m, choice.offset_y_m, choice.yaw_rad) == (0, 0, 0)


def test_too_few_frames_uses_taught_pose():
    assert run([frame()] * (FRAMES_NEEDED - 1)).source == 'taught'


def test_stale_frames_do_not_count():
    assert run([frame(age=MAX_AGE_S + 0.5)] * FRAMES_NEEDED).source == 'taught'


def test_one_low_confidence_frame_blocks_the_camera():
    frames = [frame()] * (FRAMES_NEEDED - 1) + [frame(confidence=MIN_CONFIDENCE - 0.01)]
    choice = run(frames)
    assert choice.source == 'taught' and 'confidence' in choice.reason


def test_frames_that_disagree_fall_back():
    frames = [frame(x=0.0)] * (FRAMES_NEEDED - 1) + [frame(x=0.004)]
    choice = run(frames)
    assert choice.source == 'taught' and 'disagree' in choice.reason


def test_agreeing_frames_use_the_median_pose():
    # Spread of 0.8 mm and 0.1 mm, inside the 1.5 mm and 0.5 degree agreement limits.
    frames = [frame(x=0.001 + 0.0002 * k, y=0.0, yaw=0.01 + 0.00005 * k) for k in (1, 2, 3, 4, 5)]
    choice = run(frames)
    assert choice.source == 'camera'
    assert choice.offset_x_m == pytest.approx(0.0016)
    assert choice.yaw_rad == pytest.approx(0.01 + 0.00015)


def test_move_outside_the_protocol_limit_is_rejected():
    choice = run([frame(x=0.02)] * FRAMES_NEEDED)
    assert choice.source == 'taught' and 'rejected' in choice.reason


def test_nan_estimate_is_rejected():
    choice = run([frame(x=math.nan)] * FRAMES_NEEDED)
    assert choice.source == 'taught'


def test_confidence_threshold_matches_detector_default():
    from pathlib import Path
    import re
    source = (Path(__file__).resolve().parents[3] / 'vision/gantry_vision/inference.py').read_text()
    assert float(re.search(r'DEFAULT_MIN_CONFIDENCE = ([0-9.]+)', source).group(1)) == MIN_CONFIDENCE


def test_rgb_frames_are_converted_to_bgr():
    rgb = np.zeros((2, 3, 3), np.uint8)
    rgb[..., 0] = 255   # red channel
    bgr = frame_to_bgr(rgb.tobytes(), 2, 3, 9, 'rgb8')
    assert bgr[0, 0].tolist() == [0, 0, 255]


def test_bgr_frames_keep_channel_order_and_padded_rows():
    raw = np.zeros((2, 16), np.uint8)   # 3 pixels per row padded to 16 bytes
    raw[0, :3] = [1, 2, 3]
    bgr = frame_to_bgr(raw.tobytes(), 2, 3, 16, 'bgr8')
    assert bgr.shape == (2, 3, 3) and bgr[0, 0].tolist() == [1, 2, 3]


def test_unknown_encoding_is_refused():
    with pytest.raises(ValueError):
        frame_to_bgr(bytes(12), 2, 2, 6, 'mono16')
