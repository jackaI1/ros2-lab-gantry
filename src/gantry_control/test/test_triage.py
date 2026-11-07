from gantry_control.triage import group_events, tracking_context


def test_fault_events_group_by_explicit_cause_and_preserve_unknown():
    events = [{'reason': 'emergency_stop'}, {'reason': 'limit_switch'},
              {'reason': 'emergency_stop'}, {'reason': 'unexpected failure'}]
    groups = group_events(events)
    assert [e['reason'] for e in groups['emergency_stop']] == ['emergency_stop'] * 2
    assert groups['limit_switch'] == [events[1]]
    assert groups['unknown'] == [events[3]]


def test_tracking_context_selects_nearest_samples_before_fault():
    rows = [{'sim_time_s': str(t), 'joint': 'x_joint'} for t in (1, 2, 3, 4)]
    assert [r['sim_time_s'] for r in tracking_context(rows, 3, 2)] == ['2', '3']


def test_journal_report_and_replay_reject_unknown(tmp_path):
    import pytest
    from gantry_control.triage import RunRecorder, load_run, report, replay_schedule
    recorder = RunRecorder(tmp_path, 'abc', {'wells': ['A1'], 'volume_ul': 20.0}, [.04,.04,.01], 1)
    recorder.event('input', 1.1, name='limit_switch', value=True)
    recorder.event('fault', 1.1, reason='limit_switch')
    recorder.close()
    (tmp_path / 'abc-tracking.csv').write_text('sim_time_s,joint,error_m\n1,x_joint,0.001\n2,x_joint,0.9\n')
    _, events, rows = load_run(tmp_path / 'abc-run.json')
    assert replay_schedule(events)[0]['name'] == 'limit_switch'
    text = report(tmp_path / 'abc-run.json')
    assert 'limit_switch (1)' in text and '0.001' in text and '0.9' not in text
    assert rows[0]['joint'] == 'x_joint'
    with pytest.raises(ValueError, match='manual reproduction'):
        replay_schedule(events + [{'kind':'fault','reason':'new controller fault'}])


def test_context_does_not_guess_unknown_signatures():
    import pytest
    assert 'unknown' in group_events([{'reason':'emergency_stop-ish'}])
    with pytest.raises(ValueError):
        tracking_context([], 1, -1)
    assert tracking_context([{'sim_time_s':'1'}], 1, 0) == []
