"""Pendant geometry and program preflight, independent of ROS.

This fixed pipette has no rotary axes. World Z is up; tool Z points down,
with tool Y reversed to form a right-handed frame (180 degrees about X).
The exclusion box covers the pipette's swept body plus 6 mm clearance.
"""
import math
import re
from gantry_control.protocol import limit_fault

TOOLING = ((.164, .104, .024), (.206, .146, .0795))


def vector(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3 or
            any(type(v) not in (int, float) or abs(v) > 1 or not math.isfinite(v) for v in value)):
        raise ValueError('Expected three finite numbers within +/-1 metre')
    return tuple(value)


def delta_joint(value, frame):
    x,y,z = vector(value)
    if frame == 'joint':
        return x,y,z
    if frame == 'world':
        return x,y,-z
    if frame == 'tool':
        return x,-y,z
    raise ValueError('Frame must be joint, world or tool')


def check_path(start, target):
    start, target = vector(start), vector(target)
    if limit_fault(start) or limit_fault(target):
        raise ValueError('Path exceeds axis switch margins')
    # Slab intersection checks the entire closed line segment, not just endpoints.
    enter, leave = 0., 1.
    for a,b,lo,hi in zip(start, target, *TOOLING):
        if abs(b-a) < 1e-12:
            if a < lo or a > hi:
                return
        else:
            t0,t1 = sorted(((lo-a)/(b-a), (hi-a)/(b-a)))
            enter, leave = max(enter,t0), min(leave,t1)
            if enter > leave:
                return
    raise ValueError('Path intersects fixed tooling interference zone')


def channel(value):
    if type(value) is not int or not 0 <= value < 8:
        raise ValueError('Digital channel must be 0 through 7')
    return value


class Pendant:
    def __init__(self):
        self.mode = 'teach'
        self.points = {}
        self.di = [False]*8
        self.do = [False]*8

    def record(self, name, position, frame, offset):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', name):
            raise ValueError('Point name must be a short letter-led identifier')
        if name in self.points:
            raise ValueError('Point already exists; delete it explicitly first')
        offset = delta_joint(offset, frame)
        target = tuple(a+b for a,b in zip(vector(position), offset))
        check_path(target, target)
        self.points[name] = {'joint': tuple(position), 'frame': frame, 'offset_joint': offset}

    def target(self, instruction):
        name = instruction.get('point')
        if not isinstance(name, str) or name not in self.points:
            raise ValueError('Unknown taught point')
        point = self.points[name]
        offset = delta_joint(instruction.get('offset', [0,0,0]), point['frame'])
        return tuple(a+b+c for a,b,c in zip(point['joint'], point['offset_joint'], offset))

    def prepare(self, program, current, step):
        if not isinstance(program, list) or not 1 <= len(program) <= 256:
            raise ValueError('Program must contain 1 to 256 instructions')
        if type(step) is not int or not 0 <= step < len(program):
            raise ValueError('Step is outside program')
        if self.mode == 'auto' and step != 0:
            raise ValueError('Auto starts at instruction zero')
        selected = list(enumerate(program)) if self.mode == 'auto' else [(step, program[step])]
        prepared = []
        for index, instruction in selected:
            if not isinstance(instruction, dict):
                raise ValueError('Instruction must be an object')
            op = instruction.get('op')
            item = dict(instruction)
            if op == 'move':
                target = self.target(item)
                check_path(current, target)
                item['target'] = target
                current = target
            elif op == 'jog':
                if self.mode != 'teach':
                    raise ValueError('Jog is available only in teach mode')
                delta = delta_joint(item.get('delta'), item.get('frame'))
                if max(map(abs, delta)) > .01:
                    raise ValueError('Jog increment is limited to 10 mm per axis')
                target = tuple(a+b for a,b in zip(current,delta))
                check_path(current,target)
                item['target'] = target
                current = target
            elif op in ('set_do', 'wait_di'):
                channel(item.get('channel'))
                if type(item.get('value')) is not bool:
                    raise ValueError('Digital value must be true or false')
                if op == 'wait_di':
                    timeout = item.get('timeout')
                    if type(timeout) not in (int,float) or not 0 < timeout <= 300 or not math.isfinite(timeout):
                        raise ValueError('Input wait needs a timeout above 0 and at most 300 seconds')
            else:
                raise ValueError('Unknown instruction')
            prepared.append((index,item))
        return prepared
