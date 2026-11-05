import math
import pytest
from gantry_control.protocol import validate, well_xy, waypoints, limit_fault


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
