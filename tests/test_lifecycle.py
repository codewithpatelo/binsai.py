"""Tests for lifecycle.py — FIPA transitions with causal logging."""

import pytest

from binsai.lifecycle import FIPAState, LifecycleManager


class TestTransitions:
    def test_initial_state_is_initiated(self):
        lm = LifecycleManager()
        assert lm.state == FIPAState.INITIATED

    def test_initiated_to_active(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.ACTIVE, cause="start", tick=0)
        assert lm.state == FIPAState.ACTIVE

    def test_transition_requires_nonempty_cause(self):
        lm = LifecycleManager()
        with pytest.raises(ValueError, match="non-empty cause"):
            lm.transition(FIPAState.ACTIVE, cause="", tick=0)

    def test_invalid_transition_raises(self):
        lm = LifecycleManager()
        with pytest.raises(ValueError, match="Invalid lifecycle transition"):
            lm.transition(FIPAState.SUSPENDED, cause="skip", tick=0)

    def test_active_to_suspended(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.ACTIVE,     cause="start",       tick=0)
        lm.transition(FIPAState.SUSPENDED,  cause="sleep",       tick=5)
        assert lm.state == FIPAState.SUSPENDED

    def test_suspended_to_active(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.ACTIVE,    cause="start",  tick=0)
        lm.transition(FIPAState.SUSPENDED, cause="sleep",  tick=1)
        lm.transition(FIPAState.ACTIVE,    cause="wake",   tick=10)
        assert lm.state == FIPAState.ACTIVE

    def test_history_records_all_events(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.ACTIVE,    cause="start", tick=0)
        lm.transition(FIPAState.SUSPENDED, cause="sleep", tick=5)
        assert len(lm.history) == 2
        assert lm.history[0].cause == "start"
        assert lm.history[1].cause == "sleep"

    def test_history_is_immutable_copy(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.ACTIVE, cause="start", tick=0)
        h = lm.history
        h.clear()
        assert len(lm.history) == 1  # original intact

    def test_last_event(self):
        lm = LifecycleManager()
        lm.transition(FIPAState.ACTIVE, cause="start", tick=0)
        ev = lm.last_event()
        assert ev is not None
        assert ev.cause == "start"
        assert ev.tick == 0


class TestCriticalDwell:
    def test_dwell_triggers_critical(self):
        lm = LifecycleManager(T_critical_dwell=3)
        lm.transition(FIPAState.ACTIVE, cause="start", tick=0)
        results = [lm.tick_critical_zone(t) for t in range(1, 4)]
        assert results[-1] is True
        assert lm.state == FIPAState.CRITICAL

    def test_dwell_does_not_trigger_before_threshold(self):
        lm = LifecycleManager(T_critical_dwell=5)
        lm.transition(FIPAState.ACTIVE, cause="start", tick=0)
        for t in range(1, 5):
            assert lm.tick_critical_zone(t) is False
        assert lm.state == FIPAState.ACTIVE

    def test_critical_to_active(self):
        lm = LifecycleManager(T_critical_dwell=2)
        lm.transition(FIPAState.ACTIVE,   cause="start",  tick=0)
        lm.tick_critical_zone(1)
        lm.tick_critical_zone(2)
        assert lm.state == FIPAState.CRITICAL
        lm.transition(FIPAState.ACTIVE, cause="reset", tick=10)
        assert lm.state == FIPAState.ACTIVE

    def test_reset_critical_counter(self):
        lm = LifecycleManager(T_critical_dwell=5)
        lm.transition(FIPAState.ACTIVE, cause="start", tick=0)
        lm.tick_critical_zone(1)
        lm.tick_critical_zone(2)
        lm.reset_critical_counter()
        # After reset, need full dwell again
        for t in range(3, 7):
            lm.tick_critical_zone(t)
        assert lm.state == FIPAState.ACTIVE  # only 4 ticks, need 5
