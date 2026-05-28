"""Tests for world/dummy_human.py — Poisson demand generation, uniform targeting."""

import random
import math

import pytest

from binsai.agent import BinsaiAgent
from binsai.drives import Drives
from binsai.world.dummy_human import DummyHuman, Demand


def make_agents(n: int, seed: int = 0) -> list[BinsaiAgent]:
    agents = []
    for i in range(n):
        drives = Drives.from_names(["metabolic"])
        a = BinsaiAgent(name=f"Agent{i}", drives=drives, rng=random.Random(seed + i))
        a.activate()
        agents.append(a)
    return agents


class TestDemandGeneration:
    def test_returns_list(self):
        agents = make_agents(2)
        dh = DummyHuman(targets=agents, lambda_demand=1.0, rng=random.Random(0))
        demands = dh.tick(t=1)
        assert isinstance(demands, list)

    def test_demand_has_required_fields(self):
        agents = make_agents(1)
        dh = DummyHuman(targets=agents, lambda_demand=5.0, rng=random.Random(1))
        demands = dh.tick(t=3)
        if demands:
            d = demands[0]
            assert d.id
            assert d.target_aid == agents[0].aid
            assert d.topic
            assert d.t_emitted == 3
            assert d.t_received is None

    def test_empty_targets_raises(self):
        with pytest.raises(ValueError):
            DummyHuman(targets=[], lambda_demand=1.0)

    def test_zero_lambda_rarely_produces(self):
        agents = make_agents(1)
        dh = DummyHuman(targets=agents, lambda_demand=0.0, rng=random.Random(0))
        total = sum(len(dh.tick(t)) for t in range(1000))
        assert total == 0

    def test_total_sent_increments(self):
        agents = make_agents(2)
        dh = DummyHuman(targets=agents, lambda_demand=2.0, rng=random.Random(42))
        total = 0
        for t in range(50):
            demands = dh.tick(t)
            total += len(demands)
        assert dh.total_sent == total

    def test_mark_received(self):
        agents = make_agents(1)
        dh = DummyHuman(targets=agents, lambda_demand=5.0, rng=random.Random(0))
        demands = dh.tick(t=1)
        if demands:
            demands[0].mark_received(5)
            assert demands[0].t_received == 5


class TestTargetDistribution:
    def test_uniform_distribution_chi_square(self):
        """Over N=5000 ticks at λ=2, target counts should be uniform (chi-square test)."""
        n_agents = 3
        agents = make_agents(n_agents, seed=0)
        dh = DummyHuman(targets=agents, lambda_demand=2.0, rng=random.Random(99))

        counts = {a.aid: 0 for a in agents}
        for t in range(5000):
            for d in dh.tick(t):
                if d.target_aid in counts:
                    counts[d.target_aid] += 1

        total = sum(counts.values())
        if total < 100:
            pytest.skip("Too few demands generated for chi-square test")

        expected = total / n_agents
        chi2 = sum((c - expected) ** 2 / expected for c in counts.values())
        # χ² critical value at p=0.001 with df=2 is ~13.8; uniform should score much lower
        assert chi2 < 15.0, f"Chi-square={chi2:.2f} — distribution may not be uniform"

    def test_all_targets_receive_demands(self):
        """Every agent should receive at least one demand over many ticks."""
        agents = make_agents(3)
        dh = DummyHuman(targets=agents, lambda_demand=1.0, rng=random.Random(7))
        received = set()
        for t in range(500):
            for d in dh.tick(t):
                received.add(d.target_aid)
        assert received == {a.aid for a in agents}
