"""Bounded, interruption-aware waits at the controller transport boundary."""
import time


def wait_acceptance(future, interrupted, timeout=5):
    deadline = time.monotonic()+timeout
    while not future.done():
        reason = interrupted()
        if reason:
            raise RuntimeError(reason + '; controller acceptance pending; stop unconfirmed')
        if time.monotonic() > deadline:
            raise RuntimeError('controller goal response timed out; stop unconfirmed')
        time.sleep(.01)
    return future.result()


class StopBarrier:
    """Block reset until every late goal is rejected or confirmed terminal.

    Futures and goal handles are the action client's real transport objects.
    Callbacks never block an executor thread waiting for another ROS callback.
    """
    def __init__(self, lock, fail, terminal_statuses):
        self.lock = lock
        self.fail = fail
        self.terminal_statuses = terminal_statuses
        self.pending = set()

    def arm(self, future):
        with self.lock:
            self.pending.add(future)
        future.add_done_callback(self.accepted)

    def wait(self, timeout=3):
        """Wait outside the executor lock for an acknowledged terminal stop."""
        deadline = time.monotonic()+timeout
        while True:
            with self.lock:
                if not self.pending:
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(.01)

    def accepted(self, future):
        try:
            child = future.result()
            if not child.accepted:
                self.release(future)
                return
            result = child.get_result_async()
            child.cancel_goal_async()
            result.add_done_callback(lambda done: self.stopped(future, done))
        except Exception:
            self.fail('controller late stop unconfirmed')

    def stopped(self, pending, result):
        try:
            if result.result().status not in self.terminal_statuses:
                raise RuntimeError('unexpected controller terminal status')
            self.release(pending)
        except Exception:
            self.fail('controller late stop unconfirmed')

    def release(self, future):
        with self.lock:
            self.pending.discard(future)
