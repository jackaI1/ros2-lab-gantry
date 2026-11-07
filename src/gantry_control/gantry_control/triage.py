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


class RunRecorder:
    """Flush a small append-only event journal alongside the existing CSV."""
    def __init__(self, directory, run_id, request, initial_position, sim_time):
        import json
        import time
        from pathlib import Path
        self.started = time.monotonic()
        self.directory = Path(directory)
        self.run_id = run_id
        self.path = self.directory / (run_id + '-run.json')
        self.manifest = {'version': 1, 'run_id': run_id, 'simulated': True,
                         'request': request, 'initial_position': list(initial_position),
                         'start_sim_time_s': sim_time}
        self.path.write_text(json.dumps(self.manifest, indent=2) + '\n')
        self.stream = (self.directory / (run_id + '-events.jsonl')).open('w')

    def event(self, kind, sim_time, **fields):
        import json
        import time
        record = dict(kind=kind, sim_time_s=sim_time,
                      elapsed_s=time.monotonic()-self.started, **fields)
        self.stream.write(json.dumps(record, allow_nan=False) + '\n')
        self.stream.flush()

    def close(self):
        self.stream.close()


def load_run(manifest_path):
    import csv
    import json
    from pathlib import Path
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    if manifest.get('version') != 1 or manifest.get('simulated') is not True:
        raise ValueError('Only version 1 simulated gantry runs are supported')
    run_id = manifest['run_id']
    if path.name != run_id + '-run.json' or not run_id.isalnum():
        raise ValueError('Run identifier must match manifest filename')
    events = [json.loads(line) for line in
              (path.parent / (run_id + '-events.jsonl')).read_text().splitlines()]
    with (path.parent / (run_id + '-tracking.csv')).open() as stream:
        rows = list(csv.DictReader(stream))
    return manifest, events, rows


def report(manifest_path):
    manifest, events, rows = load_run(manifest_path)
    faults = [e for e in events if e['kind'] == 'fault']
    groups = group_events(faults)
    lines = [f"# Gantry run {manifest['run_id']}", '',
             'Recorded simulation; signatures classify evidence, not a proven root cause.', '']
    for cause, items in groups.items():
        lines += [f'## {cause} ({len(items)})',
                  f'Playbook: docs/playbook/{cause}.md', '']
        for event in items:
            lines += [f"At {event['sim_time_s']:.3f} simulation seconds: {event['reason']}",
                      '```json']
            import json
            lines += [json.dumps({'event': event, 'preceding_tracking':
                       tracking_context(rows, event['sim_time_s'], 12)}, indent=2), '```', '']
    if not groups:
        lines += ['No latched faults recorded.']
    return '\n'.join(lines) + '\n'


def replay_schedule(events):
    """Only real input-service injections can be replayed automatically."""
    inputs = [e for e in events if e['kind'] == 'input']
    faults = [e for e in events if e['kind'] == 'fault']
    if not faults or not inputs:
        raise ValueError('No supported injected input in this run; use its playbook')
    for e in inputs:
        if e['name'] not in ('emergency_stop', 'limit_switch') or type(e['value']) is not bool:
            raise ValueError('Unsupported input event')
        if not 0 <= e['elapsed_s'] <= 600:
            raise ValueError('Input time outside bounded replay window')
    supported = {SIGNATURES.get(e['name']) for e in inputs if e['value']}
    if any(SIGNATURES.get(e['reason'], 'unknown') not in supported for e in faults):
        raise ValueError('Fault has no supported input injection; manual reproduction required')
    return sorted(inputs, key=lambda e: e['elapsed_s'])


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Inspect a recorded gantry run')
    parser.add_argument('manifest')
    args = parser.parse_args()
    print(report(args.manifest))


if __name__ == '__main__':
    main()
