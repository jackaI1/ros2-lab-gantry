"""Draw a well plate through the simulated camera, with lighting, clutter and sensor noise."""
from dataclasses import dataclass

import cv2
import numpy as np

from gantry_vision.camera import project
from gantry_vision.plate import plate_corners_3d, wells_3d

WELL_RADIUS = 0.003
BENCH = np.array([118, 112, 108], float)   # BGR grey
PLATE = np.array([160, 96, 40], float)     # BGR blue plastic
WELL = np.array([35, 35, 35], float)


@dataclass(frozen=True)
class Lighting:
    gain: float          # overall brightness
    gradient: tuple      # brightness slope across the image (x, y)
    tint: tuple          # per-channel gain, BGR
    highlight: tuple     # specular centre (u, v) in pixels and strength
    noise: float         # sensor noise, grey levels


@dataclass(frozen=True)
class Scene:
    dx: float            # plate centre offset, metres
    dy: float
    yaw: float           # plate rotation about its centre, radians
    tilt: tuple          # small roll and pitch of the plate, radians
    present: bool        # False: no plate in view
    occluded: bool       # True: an opaque box hides part of the plate
    lighting: Lighting
    clutter_seed: int


def _polygon(camera, points3d):
    pixels = project(camera, points3d)
    return np.round(pixels).astype(np.int32)


def render(camera, scene):
    """Return (BGR image, 96 well centres in pixels or None when the plate is absent)."""
    image = np.empty((camera.height, camera.width, 3), float)
    image[:] = BENCH
    rng = np.random.default_rng(scene.clutter_seed)
    for _ in range(int(rng.integers(0, 4))):   # distractor objects on the bench
        u, v = rng.uniform(20, camera.width - 20), rng.uniform(20, camera.height - 20)
        size = int(rng.integers(6, 18))
        colour = tuple(int(c) for c in rng.integers(20, 200, 3))
        cv2.rectangle(image, (int(u), int(v)), (int(u) + size, int(v) + size), colour, -1)
    wells = None
    if scene.present:
        body = _polygon(camera, plate_corners_3d(scene.dx, scene.dy, scene.yaw, scene.tilt))
        cv2.fillConvexPoly(image, body, PLATE.tolist())
        centres = wells_3d(scene.dx, scene.dy, scene.yaw, scene.tilt)
        angles = np.linspace(0, 2 * np.pi, 12, endpoint=False)
        for centre in centres:
            ring = centre + np.column_stack([WELL_RADIUS * np.cos(angles), WELL_RADIUS * np.sin(angles),
                                             np.zeros(12)])
            cv2.fillConvexPoly(image, _polygon(camera, ring), WELL.tolist())
        wells = project(camera, centres)
        if scene.occluded:
            box = np.round(body.reshape(-1, 2)).astype(int)
            x0, y0 = box.min(axis=0)
            x1, y1 = box.max(axis=0)
            # Cover a large part of the plate with an opaque grey box.
            cover = (x0 + int((x1 - x0) * 0.1), y0 + int((y1 - y0) * 0.1),
                     x1 - int((x1 - x0) * 0.05), y1 - int((y1 - y0) * 0.05))
            cv2.rectangle(image, cover[:2], cover[2:], (90, 90, 90), -1)
    image = _light(image, camera, scene.lighting, rng)
    return image.astype(np.uint8), wells


def _light(image, camera, lighting, rng):
    h, w = image.shape[:2]
    v, u = np.mgrid[0:h, 0:w]
    slope = 1 + lighting.gradient[0] * (u / w - 0.5) + lighting.gradient[1] * (v / h - 0.5)
    spot = np.exp(-((u - lighting.highlight[0]) ** 2 + (v - lighting.highlight[1]) ** 2) /
                  (2 * (0.12 * w) ** 2))
    lit = image * (lighting.gain * slope)[..., None] * np.asarray(lighting.tint)
    lit += lighting.highlight[2] * spot[..., None]
    lit += rng.normal(0, lighting.noise, image.shape)
    return np.clip(lit, 0, 255)
