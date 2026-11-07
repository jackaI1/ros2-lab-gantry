"""Reject stale operator instructions when fault signatures or safety controls change."""
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/gantry_control'))
from gantry_control.triage import SIGNATURES

SOURCES = ['src/gantry_control/gantry_control/server.py',
           'src/gantry_control/gantry_control/protocol.py',
           'src/gantry_control/gantry_control/trajectory.py',
           'src/gantry_description/config/controllers.yaml',
           'src/gantry_monitor/include/gantry_monitor/limits.hpp']


def contract(root=ROOT):
    value = repr(sorted(SIGNATURES.items())).encode()
    for path in SOURCES:
        value += path.encode() + (root / path).read_bytes()
    return hashlib.sha256(value).hexdigest()


def check(root=ROOT):
    errors = []
    for code in sorted(set(SIGNATURES.values()) | {'unknown'}):
        page = root / 'docs/playbook' / (code + '.md')
        if not page.exists():
            errors.append(f'{code}: missing playbook')
            continue
        text = page.read_text()
        for section in ('## Symptoms', '## Checks', '## Fix', '## Confirm recovery'):
            if section not in text:
                errors.append(f'{code}: missing {section}')
        if f'Contract: {contract(root)}' not in text:
            errors.append(f'{code}: safety or controller contract changed; review and update this page')
    return errors


if __name__ == '__main__':
    errors = check()
    print('\n'.join(errors) if errors else 'All playbooks match fault and controller contracts')
    raise SystemExit(bool(errors))
