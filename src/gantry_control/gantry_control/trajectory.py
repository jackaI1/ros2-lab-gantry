"""Synchronized trapezoidal velocity, triangular for short moves (SI units)."""
import math


def trapezoid(start, target, speed=.04, acceleration=.08):
    distance = max(abs(b-a) for a, b in zip(start, target))
    if distance < 1e-12:
        return [(0.0, tuple(start), (0.,)*3), (.1, tuple(target), (0.,)*3)]
    ramp = min(speed / acceleration, math.sqrt(distance / acceleration))
    peak = acceleration * ramp
    cruise = max(0., distance / peak - ramp)
    total = 2*ramp + cruise
    times = [0., ramp]
    if cruise > 1e-12:
        times.append(ramp + cruise)
    times.append(total)
    samples = []
    for t in times:
        if t <= ramp:
            s, v = .5*acceleration*t*t, acceleration*t
        elif t <= ramp + cruise:
            s, v = .5*peak*ramp + peak*(t-ramp), peak
        else:
            remaining = total-t
            s, v = distance-.5*acceleration*remaining**2, acceleration*remaining
        ratios = [(b-a)/distance for a,b in zip(start,target)]
        samples.append((t, tuple(a+r*s for a,r in zip(start,ratios)),
                        tuple(r*v for r in ratios)))
    return samples
