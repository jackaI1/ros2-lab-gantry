import numpy as np

from gantry_vision.inference import DEFAULT_MIN_CONFIDENCE, decode, preprocess


def test_decode_converts_units_and_confidence():
    detection = decode([1.5, -2.0, 0.4, 4.0])
    assert abs(detection.offset_x_m - 0.015) < 1e-9
    assert abs(detection.offset_y_m + 0.02) < 1e-9
    assert abs(detection.yaw_rad - 0.02) < 1e-9
    assert detection.confidence > 0.98


def test_low_confidence_is_not_trusted():
    assert not decode([0, 0, 0, -1.0]).trusted(DEFAULT_MIN_CONFIDENCE)
    assert decode([0, 0, 0, 3.0]).trusted(DEFAULT_MIN_CONFIDENCE)


def test_preprocess_matches_training_layout():
    image = np.full((240, 320, 3), 255, np.uint8)
    tensor = preprocess(image)
    assert tensor.shape == (1, 3, 240, 320) and tensor.dtype == np.float32
    assert tensor.max() == 1.0
