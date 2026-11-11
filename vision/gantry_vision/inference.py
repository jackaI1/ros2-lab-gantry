"""Run the exported ONNX detector. This module does not import torch, so the ROS node stays light."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_MIN_CONFIDENCE = 0.8
OFFSET_SCALE = 0.01    # the network predicts offsets in units of 10 mm
YAW_SCALE = 0.05       # and yaw in units of 0.05 rad


@dataclass(frozen=True)
class Detection:
    offset_x_m: float
    offset_y_m: float
    yaw_rad: float
    confidence: float

    def trusted(self, minimum=DEFAULT_MIN_CONFIDENCE):
        return self.confidence >= minimum


def decode(raw):
    """Turn the network's four raw outputs into metres, radians and a probability."""
    raw = np.asarray(raw, float).reshape(-1)
    return Detection(offset_x_m=float(raw[0] * OFFSET_SCALE), offset_y_m=float(raw[1] * OFFSET_SCALE),
                     yaw_rad=float(raw[2] * YAW_SCALE), confidence=float(1 / (1 + np.exp(-raw[3]))))


def preprocess(bgr):
    """Same layout as training: BGR, scaled to 0 to 1, channels first, with a batch axis."""
    return (np.asarray(bgr, np.float32) / 255.0).transpose(2, 0, 1)[None]


class PlateDetector:
    def __init__(self, model_path):
        import onnxruntime as ort
        self.session = ort.InferenceSession(str(Path(model_path)), providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, bgr):
        raw = self.session.run(None, {self.input_name: preprocess(bgr)})[0]
        return decode(raw)
