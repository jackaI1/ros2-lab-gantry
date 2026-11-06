"""Independent numeric expectations for frames, clearance and speed limits."""
import math
import pytest
from gantry_control.pendant import Pendant, check_path, delta_joint
from gantry_control.trajectory import trapezoid


@pytest.mark.parametrize('frame,expected', [('joint', (.001, .002, .003)),
    ('world', (.001, .002, -.003)), ('tool', (.001, -.002, .003))])
def test_frame_jog_directions(frame, expected):
    assert delta_joint((.001, .002, .003), frame) == expected


@pytest.mark.parametrize('frame,expected', [('joint', (.05, .06, .023)),
    ('world', (.05, .06, .017)), ('tool', (.05, .06, .023))])
def test_recorded_point_offsets_preserve_frame(frame, expected):
    pendant = Pendant()
    pendant.record('pickup', (.05, .06, .02), frame, (0, 0, .003))
    assert pendant.target({'point': 'pickup'}) == pytest.approx(expected)
    assert pendant.target({'point': 'pickup', 'offset': [.001, 0, 0]}) == pytest.approx(
        (expected[0]+.001, expected[1], expected[2]))


def test_named_points_do_not_silently_overwrite():
    p = Pendant()
    p.record('a', (.05, .05, .01), 'world', (0, 0, 0))
    with pytest.raises(ValueError):
        p.record('a', (.06, .05, .01), 'world', (0, 0, 0))


@pytest.mark.parametrize('start,end', [((.15,.125,.04),(.215,.125,.04)),
    ((.18,.10,.04),(.18,.15,.04)), ((.18,.125,.01),(.18,.125,.06)),
    ((.164,.10,.04),(.164,.15,.04))])
def test_swept_segment_rejects_crossing_and_touching(start, end):
    with pytest.raises(ValueError, match='tooling'):
        check_path(start, end)


def test_raised_path_clears_fixed_tooling():
    check_path((.15,.125,.01), (.215,.125,.01))


@pytest.mark.parametrize('bad', [[0, 0], [0, 0, math.nan], [True, 0, 0], [0, 0, '1']])
def test_invalid_vectors(bad):
    with pytest.raises(ValueError):
        delta_joint(bad, 'joint')


@pytest.mark.parametrize('end,speed', [((.12,.07,.02),.04), ((.021,.02,.01),.01),
    ((.02,.02,.01),.04), ((.02,.02,.06),.01)])
def test_profile_continuous_velocity_and_bounded_acceleration(end, speed):
    start = (.02,.02,.01)
    samples = trapezoid(start, end, speed)
    assert samples[0][1] == start
    assert samples[-1][1] == pytest.approx(end)
    assert samples[0][2] == (0,0,0)
    assert samples[-1][2] == pytest.approx((0,0,0), abs=1e-10)
    for (t0,p0,v0),(t1,p1,v1) in zip(samples, samples[1:]):
        assert t1 > t0
        for i in range(3):
            assert abs(v1[i]) <= speed + 1e-10
            assert abs(v1[i]-v0[i])/(t1-t0) <= .08 + 1e-9
            assert p1[i]-p0[i] == pytest.approx((v0[i]+v1[i])*(t1-t0)/2, abs=1e-10)


@pytest.mark.parametrize('program', [[{'op':'set_do','channel':0,'value':1}],
    [{'op':'wait_di','channel':8,'value':True,'timeout':1}],
    [{'op':'wait_di','channel':0,'value':True,'timeout':0}],
    [{'op':'move','point':'missing'}], [{'op':'unknown'}], [],
    [{'op':'jog','frame':'world','delta':[0,0,.001]}]])
def test_program_preflight_rejects_bad_instructions(program):
    p = Pendant()
    p.mode = 'auto'
    with pytest.raises(ValueError):
        p.prepare(program, (.02,.02,.01), 0)


def test_teach_selects_one_instruction_auto_preflights_every_segment():
    p = Pendant()
    p.record('a', (.04,.04,.01), 'world', (0,0,0))
    program = [{'op':'set_do','channel':0,'value':True}, {'op':'move','point':'a'}]
    assert len(p.prepare(program, (.02,.02,.01), 1)) == 1
    p.mode = 'auto'
    assert len(p.prepare(program, (.02,.02,.01), 0)) == 2
    with pytest.raises(ValueError):
        p.prepare(program, (.02,.02,.01), 1)
    program.append({'op':'jog','delta':[0,0,0],'frame':'joint'})
    with pytest.raises(ValueError):
        p.prepare(program, (.02,.02,.01), 0)
