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


def test_pending_acceptance_cancel_confirms_stop_without_latching_fault():
    """Control only transport timing; real cancellation motion is tested in Gazebo."""
    from concurrent.futures import Future
    import pytest
    from gantry_control.motion import StopBarrier
    errors=[];timers=[]
    handle=SimpleNamespace(is_cancel_requested=False)
    result=Future()
    child=SimpleNamespace(accepted=True,get_result_async=lambda:result)
    canceled=[]
    def cancel():
        canceled.append(True)
        result.set_result(SimpleNamespace(status=5))
        return Future()
    child.cancel_goal_async=cancel
    def send(goal):
        assert len(goal.trajectory.points)>=2
        pending=Future()
        handle.is_cancel_requested=True
        timer=threading.Timer(.02,lambda:pending.set_result(child))
        timers.append(timer);timer.start()
        return pending
    state=SimpleNamespace(lock=threading.RLock(),fault='',position=(.04,.04,.01),
        latch=errors.append,client=SimpleNamespace(send_goal_async=send))
    state.stop_barrier=StopBarrier(state.lock,errors.append,{4,5})
    state.interrupted=MethodType(ProtocolServer.interrupted,state)
    try:
        with pytest.raises(RuntimeError,match='canceled by client'):
            ProtocolServer.move(state,(.041,.04,.01),handle)
        assert canceled and not state.stop_barrier.pending and not errors
    finally:
        for timer in timers:timer.join(timeout=.5)


def test_unconfirmed_stop_blocks_new_protocol_and_program():
    import time
    from rclpy.action import GoalResponse
    state=SimpleNamespace(lock=threading.RLock(),busy=False,fault='',position=(.04,.04,.01),
        last_state=time.monotonic(),stop_barrier=SimpleNamespace(pending={object()}))
    request=SimpleNamespace(wells=['A1'],volume_ul=20.,offset_x_m=0.,offset_y_m=0.,yaw_rad=0.)
    assert ProtocolServer.goal(state,request)==GoalResponse.REJECT
    assert ProtocolServer.program_goal(state,SimpleNamespace())==GoalResponse.REJECT
