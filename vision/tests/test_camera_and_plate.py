import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from gantry_vision.camera import WORLD, load_camera, project
from gantry_vision.plate import PLATE_CENTRE, nominal_wells, wells_at, wells_3d

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def camera():
    return load_camera()


def test_camera_reads_the_gazebo_world(camera):
    assert (camera.width, camera.height) == (320, 240)
    np.testing.assert_allclose(camera.position, [0.0895, 0.0665, 0.35])
    assert abs(camera.fx - 160 / np.tan(np.radians(30))) < 1e-3


def test_camera_looks_straight_down_with_known_image_axes(camera):
    centre = project(camera, [[0.0895, 0.0665, 0.025]])[0]
    np.testing.assert_allclose(centre, [160, 120], atol=1e-6)
    # Image up is world +X, image right is world -Y (Gazebo camera frame: x forward, y left, z up).
    up = project(camera, [[0.0995, 0.0665, 0.025]])[0]
    right = project(camera, [[0.0895, 0.0565, 0.025]])[0]
    assert up[1] < centre[1] and abs(up[0] - centre[0]) < 1e-6
    assert right[0] > centre[0] and abs(right[1] - centre[1]) < 1e-6


def test_points_behind_camera_are_nan(camera):
    assert np.isnan(project(camera, [[0.0895, 0.0665, 0.5]])[0]).all()


def test_gazebo_world_wells_match_detector_geometry():
    root = ET.parse(WORLD).getroot()
    plate = next(m for m in root.iter('model') if m.get('name') == 'plate')
    visuals = {v.get('name'): v for v in plate.iter('visual') if v.get('name', '').startswith('well_')}
    assert len(visuals) == 96
    names = [f'{r}{c}' for r in 'ABCDEFGH' for c in range(1, 13)]
    expected = nominal_wells()
    for i, name in enumerate(names):
        local = np.array([float(v) for v in visuals[f'well_{name}'].findtext('pose').split()[:2]])
        np.testing.assert_allclose(PLATE_CENTRE + local, expected[i], atol=1e-4)


def test_plate_geometry_matches_protocol_well_positions():
    sys.path.insert(0, str(ROOT / 'src/gantry_control'))
    from gantry_control.protocol import well_xy, well_xy_at
    for row in 'ABCDEFGH':
        for col in range(1, 13):
            name = f'{row}{col}'
            np.testing.assert_allclose(wells_at(0, 0, 0)[(ord(row) - 65) * 12 + col - 1], well_xy(name), atol=1e-12)
            np.testing.assert_allclose(well_xy_at(name, 0.003, -0.002, 0.02),
                                       wells_at(0.003, -0.002, 0.02)[(ord(row) - 65) * 12 + col - 1], atol=1e-12)
    sys.path.remove(str(ROOT / 'src/gantry_control'))


def test_three_degree_tilt_shifts_top_face_by_about_a_millimetre_in_plan():
    # The top face sits 10 mm above the plate centre, so a 3 degree tilt moves it about 0.5 mm per axis.
    flat = wells_3d(0, 0, 0)[:, :2]
    tilted = wells_3d(0, 0, 0, tilt=(np.radians(3), np.radians(-3)))[:, :2]
    assert 0.0004 < np.max(np.linalg.norm(flat - tilted, axis=1)) < 0.001
