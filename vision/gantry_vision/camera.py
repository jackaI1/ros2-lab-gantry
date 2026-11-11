"""Pinhole camera read from the Gazebo world, so rendered training images use the simulated lens."""
from dataclasses import dataclass
from pathlib import Path
import math
import xml.etree.ElementTree as ET

import numpy as np

WORLD = Path(__file__).resolve().parents[2] / 'src/gantry_description/worlds/lab_vision.sdf'


@dataclass(frozen=True)
class Camera:
    position: np.ndarray   # world metres
    rotation: np.ndarray   # camera-to-world, columns are camera x (forward), y (left), z (up)
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


def rpy_matrix(roll, pitch, yaw):
    """Gazebo's fixed-axis roll, pitch, yaw convention: R = Rz(yaw) Ry(pitch) Rx(roll)."""
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    return rz @ ry @ rx


def load_camera(world=None):
    """Read the overhead camera's pose, field of view and image size from the SDF world.

    Defaults to the lab_vision.sdf in this repository. Installed copies must pass their world file.
    """
    root = ET.parse(Path(world) if world else WORLD).getroot()
    model = next(m for m in root.iter('model') if m.get('name') == 'overhead_camera')
    pose = np.array([float(v) for v in model.findtext('pose').split()])
    sensor = next(s for s in model.iter('sensor') if s.get('type') == 'camera')
    camera = sensor.find('camera')
    width = int(camera.findtext('image/width'))
    height = int(camera.findtext('image/height'))
    fov = float(camera.findtext('horizontal_fov'))
    focal = (width / 2) / math.tan(fov / 2)
    return Camera(position=pose[:3], rotation=rpy_matrix(*pose[3:]), fx=focal, fy=focal,
                  cx=width / 2, cy=height / 2, width=width, height=height)


def project(camera, points):
    """Gazebo image convention: +u points to the image right (camera -y), +v down (camera -z)."""
    points = np.asarray(points, float).reshape(-1, 3)
    local = (points - camera.position) @ camera.rotation  # world -> camera axes
    with np.errstate(divide='ignore', invalid='ignore'):
        u = camera.cx - camera.fx * local[:, 1] / local[:, 0]
        v = camera.cy - camera.fy * local[:, 2] / local[:, 0]
    pixels = np.stack([u, v], axis=1)
    pixels[local[:, 0] <= 1e-6] = np.nan
    return pixels
