"""Controller transport boundary: delayed acceptance must not hide a stop."""
from concurrent.futures import Future
import time
import pytest
from gantry_control.motion import wait_acceptance


def test_stop_interrupts_pending_acceptance_without_waiting_for_deadline():
    future = Future()
    start = time.monotonic()
    with pytest.raises(RuntimeError, match='emergency_stop'):
        wait_acceptance(future, lambda: 'emergency_stop', 5)
    assert time.monotonic()-start < .1
    assert not future.done()


def test_transport_timeout_is_bounded():
    with pytest.raises(RuntimeError, match='timed out'):
        wait_acceptance(Future(), lambda: '', .02)


def test_ready_acceptance_remains_observable_for_cancel_confirmation():
    future = Future()
    future.set_result('accepted')
    assert wait_acceptance(future, lambda: 'emergency_stop', 5) == 'accepted'


class ControllerHandle:
    """Controlled action transport only; geometry/motion are tested in Gazebo."""
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.result = Future()
        self.cancel_requested = False

    def get_result_async(self):
        return self.result

    def cancel_goal_async(self):
        self.cancel_requested = True
        return Future()


def test_late_acceptance_requests_cancel_and_blocks_reset_until_terminal():
    import threading
    from types import SimpleNamespace
    from gantry_control.motion import StopBarrier
    errors = []
    barrier = StopBarrier(threading.RLock(), errors.append, {4,5})
    future = Future()
    barrier.arm(future)
    child = ControllerHandle()
    assert barrier.pending
    future.set_result(child)
    assert child.cancel_requested
    assert barrier.pending  # Cancellation request alone is not proof of a stop.
    child.result.set_result(SimpleNamespace(status=5))
    assert not barrier.pending
    assert not errors


def test_rejected_late_goal_releases_barrier():
    import threading
    from gantry_control.motion import StopBarrier
    barrier = StopBarrier(threading.RLock(), lambda _: None, {4,5})
    future = Future()
    barrier.arm(future)
    future.set_result(ControllerHandle(False))
    assert not barrier.pending


def test_failed_transport_keeps_reset_blocked():
    import threading
    from gantry_control.motion import StopBarrier
    errors = []
    barrier = StopBarrier(threading.RLock(), errors.append, {4,5})
    future = Future()
    barrier.arm(future)
    future.set_exception(RuntimeError('connection lost'))
    assert barrier.pending
    assert errors == ['controller late stop unconfirmed']
