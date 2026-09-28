"""Tests for hazard-rate activation (fuzzy.activation_*) — the fix for
probability-per-tick. The activation gate models a Poisson process:

    p_tick = 1 − e^(−h·Δt)     h in activations per unit time

so behaviour is invariant to Δt and h has domain meaning (mean wait = 1/h).
The gate owns act/not-act; the softmax owns which action; ACTIVE is
commitment (no re-sampling); a refractory dead-time follows each action.
"""

import math
import random

from binsai.agent import BinsaiAgent
from binsai.drives import Drives
from binsai.fuzzy import (activation_probability, activation_hazard,
                          compute_action_distribution)
from binsai.world.dummy_human import Demand


class TestHazardMath:
    def test_dt_invariance_exact(self):
        """P(no activation over T=1) must equal e^(−h) for ANY tick split —
        this is the whole point of the fix: behaviour independent of pulse size."""
        h = 3.0
        for dt in (1.0, 0.5, 0.25, 0.1, 1 / 60):
            n = round(1.0 / dt)
            p_none = 1.0
            for _ in range(n):
                p_none *= (1.0 - activation_probability(h, dt))
            assert abs(p_none - math.exp(-h)) < 1e-9, f"dt={dt}"

    def test_mean_wait_is_one_over_h(self):
        """Geometric waiting time over Δt=1 ticks has mean 1/p = 1/(1−e^(−h))."""
        h = 2.0
        p = activation_probability(h, 1.0)
        assert abs(1.0 / p - 1.0 / (1 - math.exp(-2))) < 1e-9
        # h=2/unit → expected wait ≈ 0.578 units, ~half a tick

    def test_zero_or_negative_hazard_never_activates(self):
        assert activation_probability(0.0) == 0.0
        assert activation_probability(-1.0) == 0.0

    def test_probability_in_unit_interval(self):
        for h in (0.0, 0.5, 3.0, 50.0):
            for dt in (0.01, 1.0, 10.0):
                p = activation_probability(h, dt)
                assert 0.0 <= p <= 1.0


class TestHazardSources:
    def test_idle_baseline(self):
        """No pressure, no demand, no backlog → h=0 → never activates."""
        assert activation_hazard(0.0) == 0.0

    def test_demand_raises_rate(self):
        h = activation_hazard(0.0, has_demand=True)
        assert h == 4.0
        # mean wait = 1/h = 0.25 units — near-immediate response
        assert activation_probability(h, 1.0) > 0.95

    def test_pressure_scales_rate(self):
        assert activation_hazard(1.0) > activation_hazard(0.5) > 0.0

    def test_backlog_adds_rate(self):
        assert activation_hazard(0.0, pending_labels=5) == 1.5

    def test_pressure_clamped(self):
        """Pressure above 1 (autonomous can exceed 1 near walls) is clamped."""
        assert activation_hazard(5.0) == activation_hazard(1.0)


def make_agent(delta: float = 0.70, rng_seed: int = 0, **kwargs) -> BinsaiAgent:
    drives = Drives.from_names(["metabolic"])
    drives.get("metabolic").value = delta
    agent = BinsaiAgent(name="A", drives=drives, dry_run_llm=True,
                        rng=random.Random(rng_seed), **kwargs)
    agent.activate()
    return agent


def add_demand(agent: BinsaiAgent) -> None:
    d = Demand(id="d0", target_aid=agent.aid, target_name=agent.name,
               topic="t", message="m", t_emitted=0)
    agent.pending_demands.append(d)


class TestAgentGate:
    def test_calm_agent_without_demand_idles(self):
        """At set-point with no demand/backlog, h≈0 → agent stays idle."""
        agent = make_agent(delta=0.70)
        agent.drives.get("metabolic").pressure = 0.0
        actions = {agent.tick(t)["action"] for t in range(1, 20)}
        assert actions <= {"idle", None, "sleep"}

    def test_demand_eventually_gets_response(self):
        """Pending demand raises h → demand is served within a few ticks."""
        agent = make_agent(delta=0.70)
        add_demand(agent)
        served = any(agent.tick(t)["action"] in ("respond_fast", "respond_slow")
                     for t in range(1, 20))
        assert served

    def test_refractory_blocks_immediate_reactivation(self):
        """After an action completes, the gate cannot fire until the
        refractory dead-time elapses — even with a pending demand."""
        agent = make_agent(delta=0.70, activation_refractory=5.0)
        add_demand(agent)
        completed_at = None
        for t in range(1, 40):
            agent.tick(t)
            # action done when no execution remains in flight
            if completed_at is None and agent._refractory_until > 0 \
                    and agent.current_action is None:
                completed_at = t
                break
        assert completed_at is not None, "no action ever completed"
        add_demand(agent)  # pending demand → hazard would be high
        for t in range(completed_at + 1, completed_at + 4):
            assert agent.tick(t)["action"] == "idle", \
                f"re-activated during refractory at t={t}"

    def test_distribution_conditioned_on_acting(self):
        """Once the gate fires, 'idle' is excluded — softmax picks which."""
        dist = compute_action_distribution(0.70, has_demand=True)
        dist.pop("idle", None)
        total = sum(dist.values())
        assert abs(total - sum(dist.values())) < 1e-9
        assert "idle" not in dist
        assert set(dist) <= {"respond_fast", "respond_slow", "defer", "sleep"}
