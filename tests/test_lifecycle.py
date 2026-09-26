"""Tests for lifecycle.py — FIPA transitions with causal logging.

State model (EPA spec §6.1):
    INITIATED --invoke--> WAITING --execute--> ACTIVE --done|abort--> WAITING
    WAITING <--suspend/resume--> SUSPENDED
    WAITING|ACTIVE --dwell--> CRITICAL (Binsai extension) --reset--> WAITING
    any --quit--> TERMINATED
"""

import pytest

from binsai.lifecycle import FIPAState, LifecycleManager


class TestTransitions:
    def test_initial_state_is_initiated(self):
        lm = LifecycleManager()
        assert lm.state == FIPAState.INITIATED

    def test_initiated_to_waiting(self):
        """invoke: INITIATED → WAITING (was ACTIVE pre-0.2)."""
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        assert lm.state == FIPAState.WAITING

    def test_initiated_cannot_skip_to_active(self):
        """ACTIVE is only reachable from WAITING via execute."""
        lm = LifecycleManager()
        with pytest.raises(ValueError, match="Invalid lifecycle transition"):
            lm.transition(FIPAState.ACTIVE, cause="start", tick=0)

    def test_transition_requires_nonempty_cause(self):
        lm = LifecycleManager()
        with pytest.raises(ValueError, match="non-empty cause"):
            lm.transition(FIPAState.WAITING, cause="", tick=0)

    def test_invalid_transition_raises(self):
        lm = LifecycleManager()
        with pytest.raises(ValueError, match="Invalid lifecycle transition"):
            lm.transition(FIPAState.SUSPENDED, cause="skip", tick=0)

    def test_waiting_to_active_execute(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        lm.transition(FIPAState.ACTIVE,  cause="execute: respond_slow", tick=1)
        assert lm.state == FIPAState.ACTIVE

    def test_active_done_returns_to_waiting(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke",  tick=0)
        lm.transition(FIPAState.ACTIVE,  cause="execute", tick=1)
        lm.transition(FIPAState.WAITING, cause="done",    tick=4)
        assert lm.state == FIPAState.WAITING

    def test_active_abort_returns_to_waiting(self):
        """Red-zone interrupt aborts the committed action."""
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke",  tick=0)
        lm.transition(FIPAState.ACTIVE,  cause="execute", tick=1)
        lm.transition(FIPAState.WAITING, cause="abort: critical interrupt", tick=2)
        assert lm.state == FIPAState.WAITING

    def test_waiting_to_suspended(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING,   cause="invoke", tick=0)
        lm.transition(FIPAState.SUSPENDED, cause="suspend", tick=5)
        assert lm.state == FIPAState.SUSPENDED

    def test_suspended_resumes_to_waiting(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING,   cause="invoke", tick=0)
        lm.transition(FIPAState.SUSPENDED, cause="suspend", tick=1)
        lm.transition(FIPAState.WAITING,   cause="resume", tick=10)
        assert lm.state == FIPAState.WAITING

    def test_quit_from_any_state(self):
        for state_path in [
            [FIPAState.WAITING],
            [FIPAState.WAITING, FIPAState.ACTIVE],
            [FIPAState.WAITING, FIPAState.SUSPENDED],
        ]:
            lm = LifecycleManager()
            for s in state_path:
                lm.transition(s, cause="go", tick=0)
            lm.transition(FIPAState.TERMINATED, cause="quit", tick=99)
            assert lm.state == FIPAState.TERMINATED

    def test_history_records_all_events(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING,   cause="invoke",  tick=0)
        lm.transition(FIPAState.SUSPENDED, cause="suspend", tick=5)
        assert len(lm.history) == 2
        assert lm.history[0].cause == "invoke"
        assert lm.history[1].cause == "suspend"

    def test_history_is_immutable_copy(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        h = lm.history
        h.clear()
        assert len(lm.history) == 1

    def test_last_event(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        ev = lm.last_event()
        assert ev is not None
        assert ev.cause == "invoke"
        assert ev.tick == 0

    def test_transit_reserved(self):
        """TRANSIT is declared but has no enabled transitions."""
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        with pytest.raises(ValueError, match="Invalid lifecycle transition"):
            lm.transition(FIPAState.TRANSIT, cause="migrate", tick=1)


class TestStatePredicates:
    def test_waiting_predicate(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        assert lm.is_waiting() and lm.is_operational() and not lm.is_active()

    def test_active_predicate(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING, cause="invoke",  tick=0)
        lm.transition(FIPAState.ACTIVE,  cause="execute", tick=1)
        assert lm.is_active() and lm.is_operational() and not lm.is_waiting()

    def test_suspended_not_operational(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.WAITING,   cause="invoke",  tick=0)
        lm.transition(FIPAState.SUSPENDED, cause="suspend", tick=1)
        assert lm.is_suspended() and not lm.is_operational()


class TestCriticalDwell:
    def test_dwell_triggers_critical_from_waiting(self):
        lm = LifecycleManager(T_critical_dwell=3)
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        results = [lm.tick_critical_zone(t) for t in range(1, 4)]
        assert results[-1] is True
        assert lm.state == FIPAState.CRITICAL

    def test_dwell_triggers_critical_from_active(self):
        lm = LifecycleManager(T_critical_dwell=2)
        lm.transition(FIPAState.WAITING, cause="invoke",  tick=0)
        lm.transition(FIPAState.ACTIVE,  cause="execute", tick=1)
        lm.tick_critical_zone(2)
        assert lm.tick_critical_zone(3) is True
        assert lm.state == FIPAState.CRITICAL

    def test_dwell_does_not_trigger_before_threshold(self):
        lm = LifecycleManager(T_critical_dwell=5)
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        for t in range(1, 5):
            assert lm.tick_critical_zone(t) is False
        assert lm.state == FIPAState.WAITING

    def test_critical_resets_to_waiting(self):
        lm = LifecycleManager(T_critical_dwell=2)
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        lm.tick_critical_zone(1)
        lm.tick_critical_zone(2)
        assert lm.state == FIPAState.CRITICAL
        lm.transition(FIPAState.WAITING, cause="reset", tick=10)
        assert lm.state == FIPAState.WAITING

    def test_critical_can_suspend(self):
        """Forced consolidation from the alarm state is allowed."""
        lm = LifecycleManager(T_critical_dwell=1)
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        lm.tick_critical_zone(1)
        lm.transition(FIPAState.SUSPENDED, cause="suspend", tick=2)
        assert lm.state == FIPAState.SUSPENDED

    def test_reset_critical_counter(self):
        lm = LifecycleManager(T_critical_dwell=5)
        lm.transition(FIPAState.WAITING, cause="invoke", tick=0)
        lm.tick_critical_zone(1)
        lm.tick_critical_zone(2)
        lm.reset_critical_counter()
        for t in range(3, 7):
            lm.tick_critical_zone(t)
        assert lm.state == FIPAState.WAITING  # only 4 ticks, need 5
