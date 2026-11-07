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
