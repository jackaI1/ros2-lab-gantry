import numpy as np
import pytest

from gantry_vision.camera import load_camera, project
from gantry_vision.dataset import make_set, make_sample
from gantry_vision.plate import wells_3d
from gantry_vision.render import Lighting, Scene, render

LIGHT = Lighting(gain=1.0, gradient=(0, 0), tint=(1, 1, 1), highlight=(0, 0, 0), noise=0.0)


@pytest.fixture(scope='module')
def camera():
    return load_camera()


def scene(**kwargs):
    base = dict(dx=0, dy=0, yaw=0, tilt=(0, 0), present=True, occluded=False, lighting=LIGHT, clutter_seed=3)
    base.update(kwargs)
    return Scene(**base)


def test_absent_plate_has_no_well_labels(camera):
    image, wells = render(camera, scene(present=False))
    assert wells is None and image.shape == (240, 320, 3) and image.dtype == np.uint8


def test_well_labels_land_on_dark_wells(camera):
    image, wells = render(camera, scene())
    assert wells.shape == (96, 2) and np.isfinite(wells).all()
    grey = image.astype(float).mean(axis=2)
    samples = [grey[int(round(v)), int(round(u))] for u, v in wells]
    # Each label sits on a dark well (about 35 grey), not on the blue plate body (about 110).
    assert np.median(samples) < 60


def test_label_pixels_follow_plate_displacement(camera):
    _, base = render(camera, scene())
    _, moved = render(camera, scene(dx=0.005, dy=-0.004))
    shift = np.median(moved - base, axis=0)
    expected = np.median(project(camera, wells_3d(0.005, -0.004, 0)) - project(camera, wells_3d(0, 0, 0)), axis=0)
    np.testing.assert_allclose(shift, expected, atol=1e-6)


def test_occluded_plate_is_still_labelled_for_geometry_but_marked_unusable(camera):
    rng = np.random.default_rng(5)
    samples = [make_sample(camera, rng, negatives=1.0) for _ in range(40)]
    occluded = [s for s in samples if s.scene.occluded]
    assert occluded, 'occlusion should appear when negatives are forced'
    assert all(s.target[3] == 0 for s in occluded)


def test_dataset_is_seeded_and_targets_match_scenes(camera):
    first = make_set(camera, 6, seed=11)
    second = make_set(camera, 6, seed=11)
    for a, b in zip(first, second):
        np.testing.assert_array_equal(a.image, b.image)
    for s in first:
        if s.scene.present and not s.scene.occluded:
            assert s.target[3] == 1
            np.testing.assert_allclose(s.target[:3], [s.scene.dx / 0.01, s.scene.dy / 0.01, s.scene.yaw / 0.05])
        assert s.target[4] == float(s.scene.present)


def test_training_range_is_within_the_stated_limits(camera):
    samples = make_set(camera, 200, seed=2)
    dx = np.array([s.scene.dx for s in samples])
    assert np.abs(dx).max() <= 0.010 + 1e-12
    assert np.abs([s.scene.yaw for s in samples]).max() <= np.radians(4) + 1e-12
    assert np.mean([not s.scene.present for s in samples]) > 0.05
