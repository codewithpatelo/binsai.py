"""Tests for sleep.py — ConsolidationWorker, WakeGuard, causal AND-wake."""

import random

import pytest

from binsai.agent import BinsaiAgent
from binsai.drives import Drive, Drives, Stratum
from binsai.lifecycle import FIPAState
from binsai.sleep import ConsolidationWorker, WakeGuard, maybe_wake
from binsai.world.dummy_human import Demand


def make_agent(delta: float = 0.50) -> BinsaiAgent:
    drives = Drives.from_names(["metabolic"])
    m = drives.get("metabolic")
    m.value = delta
    agent = BinsaiAgent(name="TestAgent", drives=drives, dry_run_llm=True, rng=random.Random(0))
    agent.activate()
    return agent


def add_demands(agent: BinsaiAgent, n: int) -> None:
    for i in range(n):
        d = Demand(id=f"d{i}", target_aid=agent.aid, topic="test", t_emitted=0)
        agent.pending_demands.append(d)


class TestConsolidationWorker:
    def test_processes_one_item_per_tick(self):
        agent = make_agent()
        add_demands(agent, 3)
        worker = ConsolidationWorker()
        worker.tick(agent, agent.drives.get("metabolic"), t=1)
        assert len(agent.pending_demands) == 2

    def test_lowers_delta_on_process(self):
        agent = make_agent(0.50)
        add_demands(agent, 1)
        before = agent.drives.get("metabolic").value
        worker = ConsolidationWorker(recovery_per_item=0.03)
        worker.tick(agent, agent.drives.get("metabolic"), t=1)
        assert agent.drives.get("metabolic").value < before

    def test_returns_false_on_empty_queue(self):
        agent = make_agent()
        worker = ConsolidationWorker()
        result = worker.tick(agent, agent.drives.get("metabolic"), t=1)
        assert result is False

    def test_emits_consolidation_event(self):
        events = []
        agent = make_agent()
        agent.on("consolidation.item.processed", events.append)
        add_demands(agent, 1)
        worker = ConsolidationWorker()
        worker.tick(agent, agent.drives.get("metabolic"), t=5)
        assert len(events) == 1
        assert events[0]["tick"] == 5


class TestWakeGuard:
    def test_wake_requires_both_conditions(self):
        """Only wakes when BOTH δ ≤ threshold AND queue empty."""
        guard = WakeGuard()

        # Condition A met, B not met (queue non-empty)
        agent = make_agent(delta=0.10)  # δ below wake_threshold=0.20
        add_demands(agent, 2)
        assert guard.check(agent, agent.drives.get("metabolic"), t=1) is False

        # Condition B met, A not met (δ too high)
        agent2 = make_agent(delta=0.50)  # δ above wake_threshold
        assert guard.check(agent2, agent2.drives.get("metabolic"), t=1) is False

    def test_wake_when_both_conditions_met(self):
        guard = WakeGuard()
        agent = make_agent(delta=0.10)  # δ ≤ wake_threshold=0.20, queue empty
        result = guard.check(agent, agent.drives.get("metabolic"), t=10)
        assert result is True

    def test_wake_emits_cycle_completed_event(self):
        events = []
        agent = make_agent(delta=0.10)
        agent.on("sleep.cycle.completed", events.append)
        guard = WakeGuard()
        guard.check(agent, agent.drives.get("metabolic"), t=7)
        assert len(events) == 1
        assert events[0]["tick"] == 7

    def test_wake_applies_delta_bonus(self):
        agent = make_agent(delta=0.10)
        before = agent.drives.get("metabolic").value
        guard = WakeGuard()
        guard.check(agent, agent.drives.get("metabolic"), t=1)
        assert agent.drives.get("metabolic").value < before  # bonus lowers δ further


class TestMaybeWake:
    def test_does_not_wake_if_queue_not_empty(self):
        agent = make_agent(delta=0.10)
        add_demands(agent, 3)
        # even with δ low, queue must drain first
        result = maybe_wake(agent, agent.drives.get("metabolic"), t=1)
        # first call processes 1 item, then checks — still 2 items, won't wake
        assert result is False

    def test_wakes_after_queue_drained(self):
        agent = make_agent(delta=0.10)
        add_demands(agent, 1)
        # first call processes the 1 item, checks — queue now empty, δ low → wake
        result = maybe_wake(agent, agent.drives.get("metabolic"), t=1)
        assert result is True
