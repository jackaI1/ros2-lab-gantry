"""Classify recorded gantry faults without guessing at unknown messages."""
from collections import defaultdict

# Match complete messages: a new message must be reviewed instead of silently
# being assigned to a familiar cause.
SIGNATURES = {
    'emergency_stop': 'emergency_stop',
    'limit_switch': 'limit_switch',
    'x_joint limit switch': 'limit_switch',
    'y_joint limit switch': 'limit_switch',
    'z_joint limit switch': 'limit_switch',
    'controller feedback stale for 1 s': 'feedback_stale',
    'tracking error over 15 mm for 0.5 s': 'tracking_error',
    'invalid joint feedback': 'invalid_feedback',
    'invalid controller feedback': 'invalid_feedback',
    'invalid reference feedback': 'invalid_feedback',
    'tracking log write failed': 'logging_failure',
    'controller stop unconfirmed': 'stop_unconfirmed',
    'controller late stop unconfirmed': 'stop_unconfirmed',
}


def group_events(events):
    groups = defaultdict(list)
    for event in events:
        groups[SIGNATURES.get(event['reason'], 'unknown')].append(event)
    return dict(groups)


def tracking_context(rows, sim_time, count=10):
    if count < 0:
        raise ValueError('count must be non-negative')
    eligible = [r for r in rows if float(r['sim_time_s']) <= sim_time]
    return sorted(eligible, key=lambda r: float(r['sim_time_s']))[-count:] if count else []
