import math
import pytest
from gantry_control.protocol import validate, well_xy, well_xy_at, waypoints, limit_fault


@pytest.mark.parametrize('wells,volume', [([], 10), (['A0'], 10), (['I1'], 10),
    (['A13'], 10), (['a1'], 10), (['A1', 'A1'], 10), (['A1'], 0),
    (['A1'], -1), (['A1'], 201), (['A1'], math.nan), (['A1'], math.inf)])
def test_reject_invalid_protocol(wells, volume):
    with pytest.raises(ValueError):
        validate(wells, volume)


def test_all_wells_fit_and_travel_at_clearance():
    wells = [f'{r}{c}' for r in 'ABCDEFGH' for c in range(1, 13)]
    validate(wells, 200)
    for well in wells:
        x, y = well_xy(well)
        assert 0.001 < x < 0.219 and 0.001 < y < 0.159
        path = waypoints(well, (0.02, 0.02, 0.06))
        assert path[0] == ('lift', (0.02, 0.02, 0.01))
        assert path[1] == ('travel', (x, y, 0.01))
        assert path[2][1] == (x, y, 0.06)
        assert path[3][1] == (x, y, 0.01)


@pytest.mark.parametrize('position', [(0, .02, .01), (.22, .02, .01),
    (.02, 0, .01), (.02, .16, .01), (.02, .02, 0), (.02, .02, .08),
    (math.nan, .02, .01), (.02, math.inf, .01), (.02,)])
def test_switches_and_invalid_feedback(position):
    assert limit_fault(position)


def test_interior_has_no_switch():
    assert not limit_fault((.02, .02, .01))


def test_zero_plate_pose_is_the_taught_layout():
    for well in ('A1', 'D7', 'H12'):
        assert well_xy_at(well) == pytest.approx(well_xy(well), abs=1e-12)


def test_plate_offset_moves_every_waypoint():
    path = waypoints('B2', (0.02, 0.02, 0.06), (0.003, -0.002, 0.0))
    x, y = well_xy('B2')
    assert path[2][1] == pytest.approx((x + 0.003, y - 0.002, 0.06))


def test_turn_rotates_wells_about_the_plate_centre():
    cx, cy = 0.0895, 0.0665
    x, y = well_xy_at('A1', 0, 0, math.radians(2))
    assert math.hypot(x - cx, y - cy) == pytest.approx(math.hypot(0.04 - cx, 0.035 - cy))


@pytest.mark.parametrize('pose', [(0.013, 0, 0), (0, -0.0121, 0), (0, 0, math.radians(5.1)),
                                  (math.nan, 0, 0), (0, math.inf, 0)])
def test_reject_plate_moves_beyond_the_limits(pose):
    with pytest.raises(ValueError):
        validate(['A1'], 10, *pose)


def test_largest_allowed_move_is_accepted():
    validate(['A1', 'H12'], 10, 0.012, -0.012, math.radians(5))
