"""Inject a journal IO failure without a ROS executor; exercise actual stop logic."""
import threading
from types import SimpleNamespace, MethodType
from gantry_control.server import ProtocolServer


def test_full_event_disk_never_prevents_latched_stop():
    def fail(*args,**kwargs):
        raise OSError('injected full disk')
    errors=[]
    state=SimpleNamespace(lock=threading.RLock(),fault='',pendant=SimpleNamespace(do=[True]*8),
        recorder=SimpleNamespace(event=fail),sim_time=4.,well='A1',phase='travel',
        get_logger=lambda:SimpleNamespace(error=errors.append))
    state.record_event=MethodType(ProtocolServer.record_event,state)
    ProtocolServer.latch(state,'emergency_stop')
    assert state.fault=='emergency_stop'
    assert state.pendant.do==[False]*8
    assert 'event journal write failed' in errors[0]
    assert errors[-1]=='emergency_stop'
