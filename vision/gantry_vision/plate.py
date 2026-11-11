"""Well-plate geometry in the gantry's world frame, metres. Matches gantry_control.protocol.well_xy."""
import numpy as np

PLATE_CENTRE = np.array([0.0895, 0.0665])   # nominal plate centre, same as the Gazebo plate model
CENTRE_Z = 0.015
TOP_Z = 0.025
WELL_SPACING = 0.009
WELL_ORIGIN = np.array([0.04, 0.035])       # A1 on the nominal plate
WELL_NAMES = [f'{row}{col}' for row in 'ABCDEFGH' for col in range(1, 13)]
PLATE_SIZE = (0.128, 0.086)
# Plate-to-work-plane pose range used for training, metres and radians.
OFFSET_LIMIT = 0.010
YAW_LIMIT = np.radians(4.0)


def nominal_wells():
    """96 well centres on the nominal plate, ordered A1..H12, shape (96, 2)."""
    return np.array([WELL_ORIGIN + [(col - 1) * WELL_SPACING, row * WELL_SPACING]
                     for row in range(8) for col in range(1, 13)])


def wells_at(dx, dy, yaw):
    """Well centres after moving the plate by (dx, dy) and turning it about its centre by yaw."""
    rotation = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
    relative = nominal_wells() - PLATE_CENTRE
    return PLATE_CENTRE + np.array([dx, dy]) + relative @ rotation.T


def wells_3d(dx, dy, yaw, tilt=(0.0, 0.0)):
    """Well centres on the plate's top face in 3D, with a small roll and pitch about the plate centre."""
    planar = wells_at(dx, dy, yaw)
    centre = PLATE_CENTRE + np.array([dx, dy])
    local = np.column_stack([planar - centre, np.full(96, TOP_Z - CENTRE_Z)])
    roll, pitch = tilt
    rotation = np.array([[1, 0, 0], [0, np.cos(roll), -np.sin(roll)], [0, np.sin(roll), np.cos(roll)]]) @ \
        np.array([[np.cos(pitch), 0, np.sin(pitch)], [0, 1, 0], [-np.sin(pitch), 0, np.cos(pitch)]])
    tilted = local @ rotation.T
    return np.column_stack([centre + tilted[:, :2], np.full(96, CENTRE_Z) + tilted[:, 2]])


def plate_corners_3d(dx, dy, yaw, tilt=(0.0, 0.0)):
    """Four top-face corners of the plate body, same tilt rules as wells_3d."""
    half_x, half_y = PLATE_SIZE[0] / 2, PLATE_SIZE[1] / 2
    corners = np.array([[-half_x, -half_y], [half_x, -half_y], [half_x, half_y], [-half_x, half_y]])
    rotation = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
    centre = PLATE_CENTRE + np.array([dx, dy])
    local = np.column_stack([corners @ rotation.T, np.full(4, TOP_Z - CENTRE_Z)])
    roll, pitch = tilt
    rx = np.array([[1, 0, 0], [0, np.cos(roll), -np.sin(roll)], [0, np.sin(roll), np.cos(roll)]])
    ry = np.array([[np.cos(pitch), 0, np.sin(pitch)], [0, 1, 0], [-np.sin(pitch), 0, np.cos(pitch)]])
    tilted = local @ (rx @ ry).T
    return np.column_stack([centre + tilted[:, :2], np.full(4, CENTRE_Z) + tilted[:, 2]])
