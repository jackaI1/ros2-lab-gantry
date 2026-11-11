"""Plate geometry in metres; dispense amounts are simulated events in microlitres."""
import math
import re

JOINTS = ['x_joint', 'y_joint', 'z_joint']
UPPER = (0.22, 0.16, 0.08)
SAFE_Z = 0.01
DOSE_Z = 0.06
PLATE_CENTRE = (0.0895, 0.0665)
# Largest plate move the protocol accepts: 12 mm sideways, 5 degrees of turn.
MAX_OFFSET_M = 0.012
MAX_YAW_RAD = math.radians(5)


def validate(wells, volume, offset_x=0.0, offset_y=0.0, yaw=0.0):
    validate_pose(offset_x, offset_y, yaw)
    if not 1 <= len(wells) <= 96:
        raise ValueError('Use 1 to 96 wells')
    if len(set(wells)) != len(wells):
        raise ValueError('Duplicate wells would dispense twice')
    if not math.isfinite(volume) or not 0 < volume <= 200:
        raise ValueError('Volume must be finite, above 0 and at most 200 uL')
    for well in wells:
        if not re.fullmatch(r'[A-H]([1-9]|1[0-2])', well):
            raise ValueError('Wells must be A1 through H12')


def validate_pose(offset_x, offset_y, yaw):
    values = (offset_x, offset_y, yaw)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Plate pose must be finite')
    if abs(offset_x) > MAX_OFFSET_M or abs(offset_y) > MAX_OFFSET_M or abs(yaw) > MAX_YAW_RAD:
        raise ValueError('Plate move is larger than 12 mm or 5 degrees')


def well_xy(well):
    return (0.04 + (int(well[1:]) - 1) * 0.009,
            0.035 + (ord(well[0]) - ord('A')) * 0.009)


def well_xy_at(well, offset_x=0.0, offset_y=0.0, yaw=0.0):
    """Where a well sits after the plate moves by (offset_x, offset_y) and turns by yaw."""
    x, y = well_xy(well)
    cx, cy = PLATE_CENTRE
    c, s = math.cos(yaw), math.sin(yaw)
    rx, ry = x - cx, y - cy
    return (cx + offset_x + c * rx - s * ry, cy + offset_y + s * rx + c * ry)


def waypoints(well, current, pose=(0.0, 0.0, 0.0)):
    x, y = well_xy_at(well, *pose)
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
