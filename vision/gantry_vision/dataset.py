"""Seeded scene sampler. Each sample is one rendered image plus its exact labels."""
from dataclasses import dataclass

import numpy as np

from gantry_vision.plate import OFFSET_LIMIT, YAW_LIMIT
from gantry_vision.render import Lighting, Scene, render


@dataclass(frozen=True)
class Sample:
    image: np.ndarray        # BGR uint8, camera size
    target: np.ndarray       # [dx / 0.01 m, dy / 0.01 m, yaw / 0.05 rad, usable, plate present]
    wells: np.ndarray        # (96, 2) pixel centres, NaN when absent
    scene: Scene


def sample_scene(rng, spread=1.0, negatives=0.25):
    """spread=1 is the training range; held-out scenes use spread>1 to test beyond it."""
    present = rng.random() >= negatives * 0.6
    occluded = present and rng.random() < negatives * 0.4
    if rng.random() < 0.5:
        highlight = (rng.uniform(0, 320), rng.uniform(0, 240), rng.uniform(0, 60))
    else:
        highlight = (0.0, 0.0, 0.0)
    lighting = Lighting(gain=rng.uniform(0.45, 1.35), gradient=tuple(rng.uniform(-0.35, 0.35, 2)),
                        tint=tuple(rng.uniform(0.85, 1.15, 3)), highlight=highlight,
                        noise=rng.uniform(0.5, 6.0))
    return Scene(dx=rng.uniform(-OFFSET_LIMIT, OFFSET_LIMIT) * spread,
                 dy=rng.uniform(-OFFSET_LIMIT, OFFSET_LIMIT) * spread,
                 yaw=rng.uniform(-YAW_LIMIT, YAW_LIMIT) * spread,
                 tilt=tuple(rng.uniform(-np.radians(3.0), np.radians(3.0), 2) * spread),
                 present=present, occluded=occluded, lighting=lighting,
                 clutter_seed=int(rng.integers(0, 2**31)))


def make_sample(camera, rng, spread=1.0, negatives=0.25):
    scene = sample_scene(rng, spread, negatives)
    image, wells = render(camera, scene)
    usable = scene.present and not scene.occluded
    target = np.array([scene.dx / 0.01, scene.dy / 0.01, scene.yaw / 0.05, float(usable),
                       float(scene.present)], np.float32)
    if wells is None:
        wells = np.full((96, 2), np.nan)
    return Sample(image=image, target=target, wells=wells, scene=scene)


def make_set(camera, count, seed, spread=1.0, negatives=0.25):
    rng = np.random.default_rng(seed)
    return [make_sample(camera, rng, spread, negatives) for _ in range(count)]
