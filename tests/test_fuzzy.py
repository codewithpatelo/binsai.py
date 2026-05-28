"""Tests for fuzzy.py — zone memberships and action distributions."""

import math
import random

import pytest

from binsai.fuzzy import (
    ZONES,
    ZONE_CENTERS,
    gaussian_membership,
    zone_memberships,
    compute_action_distribution,
    sample_action,
    ACTIONS_WITH_DEMAND,
    ACTIONS_NO_DEMAND,
)


class TestZoneMemberships:
    def test_sum_to_one(self):
        for delta in [0.0, 0.05, 0.15, 0.30, 0.55, 0.80, 1.0]:
            memberships = zone_memberships(delta)
            assert abs(sum(memberships.values()) - 1.0) < 1e-9, f"sum≠1 for δ={delta}"

    def test_dominant_zone_matches_center(self):
        for zone, center in ZONE_CENTERS.items():
            memberships = zone_memberships(center)
            dominant = max(memberships, key=memberships.__getitem__)
            assert dominant == zone, f"expected {zone} dominant at δ={center}, got {dominant}"

    def test_all_zones_present(self):
        memberships = zone_memberships(0.30)
        assert set(memberships.keys()) == set(ZONES)

    def test_gaussian_membership_at_center(self):
        assert abs(gaussian_membership(0.30, 0.30) - 1.0) < 1e-9

    def test_gaussian_membership_decreases_with_distance(self):
        center = 0.30
        m0 = gaussian_membership(center, center)
        m1 = gaussian_membership(center + 0.12, center)
        m2 = gaussian_membership(center + 0.24, center)
        assert m0 > m1 > m2


class TestActionDistribution:
    def test_sums_to_one_with_demand(self):
        for delta in [0.05, 0.30, 0.80]:
            dist = compute_action_distribution(delta, has_demand=True)
            assert abs(sum(dist.values()) - 1.0) < 1e-9

    def test_sums_to_one_no_demand(self):
        for delta in [0.05, 0.30, 0.80]:
            dist = compute_action_distribution(delta, has_demand=False)
            assert abs(sum(dist.values()) - 1.0) < 1e-9

    def test_no_demand_excludes_demand_actions(self):
        dist = compute_action_distribution(0.30, has_demand=False)
        for a in ["respond_fast", "respond_slow", "defer"]:
            assert a not in dist

    def test_ablation_returns_uniform_with_demand(self):
        dist = compute_action_distribution(0.30, has_demand=True, ablation_off=True)
        n = len(ACTIONS_WITH_DEMAND)
        for a, p in dist.items():
            assert abs(p - 1.0 / n) < 1e-9

    def test_ablation_returns_uniform_no_demand(self):
        dist = compute_action_distribution(0.30, has_demand=False, ablation_off=True)
        n = len(ACTIONS_NO_DEMAND)
        for a, p in dist.items():
            assert abs(p - 1.0 / n) < 1e-9

    def test_monotonic_sleep_increases_with_delta(self):
        """Higher δ (more deficit) → higher sleep probability (with demand)."""
        p_low  = compute_action_distribution(0.10, has_demand=True)["sleep"]
        p_mid  = compute_action_distribution(0.40, has_demand=True)["sleep"]
        p_high = compute_action_distribution(0.80, has_demand=True)["sleep"]
        assert p_low < p_mid < p_high

    def test_proact_decreases_with_delta_no_demand(self):
        """Lower δ (more resources / oversated) → higher proact probability."""
        p_low  = compute_action_distribution(0.05, has_demand=False)["proact"]
        p_mid  = compute_action_distribution(0.30, has_demand=False)["proact"]
        p_high = compute_action_distribution(0.80, has_demand=False)["proact"]
        assert p_low > p_mid > p_high

    def test_seeded_reproducibility(self):
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        dist = compute_action_distribution(0.50, has_demand=True)
        a1 = sample_action(dist, rng1)
        a2 = sample_action(dist, rng2)
        assert a1 == a2

    def test_sample_returns_valid_action(self):
        rng = random.Random(0)
        dist = compute_action_distribution(0.30, has_demand=True)
        for _ in range(100):
            a = sample_action(dist, rng)
            assert a in ACTIONS_WITH_DEMAND
