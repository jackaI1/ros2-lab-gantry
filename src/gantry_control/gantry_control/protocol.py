"""Plate geometry in metres; dispense amounts are simulated events in microlitres."""
import math
import re

JOINTS = ['x_joint', 'y_joint', 'z_joint']
UPPER = (0.22, 0.16, 0.08)
SAFE_Z = 0.01
DOSE_Z = 0.06


def validate(wells, volume):
    if not 1 <= len(wells) <= 96:
        raise ValueError('Use 1 to 96 wells')
    if len(set(wells)) != len(wells):
        raise ValueError('Duplicate wells would dispense twice')
    if not math.isfinite(volume) or not 0 < volume <= 200:
        raise ValueError('Volume must be finite, above 0 and at most 200 uL')
    for well in wells:
        if not re.fullmatch(r'[A-H]([1-9]|1[0-2])', well):
            raise ValueError('Wells must be A1 through H12')


def well_xy(well):
    return (0.04 + (int(well[1:]) - 1) * 0.009,
            0.035 + (ord(well[0]) - ord('A')) * 0.009)


def waypoints(well, current):
    x, y = well_xy(well)
    return [('lift', (current[0], current[1], SAFE_Z)),
            ('travel', (x, y, SAFE_Z)), ('lower', (x, y, DOSE_Z)),
            ('retract', (x, y, SAFE_Z))]


def limit_fault(position):
    if len(position) != 3 or not all(math.isfinite(p) for p in position):
        return 'invalid joint feedback'
    for name, p, upper in zip(JOINTS, position, UPPER):
        if p <= 0.0005 or p >= upper - 0.0005:
            return f'{name} limit switch'
    return ''
