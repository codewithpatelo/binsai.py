"""Tests for EPA features in drives.py — push/pull, hysteresis, viability,
canonical events, drive-level subscriptions, coupling sources."""

import pytest

from binsai.drives import Drive, Drives, ZoneSpec
from binsai.events import (
    ZONE_CHANGED, SATIATED, COUPLED, VIABILITY_BREACHED, PRESSURE_UPDATED,
)
from binsai.observed import ObservedVariable


class TestPushPullCategory:
    def test_default_is_push(self):
        d = Drive(name="x")
        assert d.category == "push"

    def test_pull_accepted(self):
        d = Drive(name="x", category="pull")
        assert d.category == "pull"

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="push.*pull"):
            Drive(name="x", category="sideways")

    def test_viability_minimum_check(self):
        d_all_pull = Drives([Drive(name="a", category="pull"),
                             Drive(name="b", category="pull")])
        warnings = d_all_pull.check_viability_minimum()
        assert any("push" in w for w in warnings)

        d_mixed = Drives([Drive(name="a", category="pull"),
                          Drive(name="b", category="push")])
        assert d_mixed.check_viability_minimum() == []


class TestBasalDirection:
    def test_recover_forces_positive_lambda(self):
        d = Drive(name="hunger", lambda_rate=-0.005, basal_direction="recover")
        assert d.lambda_rate > 0

    def test_decay_forces_negative_lambda(self):
        d = Drive(name="energy_debt", lambda_rate=0.005, basal_direction="decay")
        assert d.lambda_rate < 0

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="decay.*recover"):
            Drive(name="x", basal_direction="sideways")


class TestHysteresis:
    def test_no_hysteresis_switches_on_dominance(self):
        """Default α_in=0, α_out=1 → zone follows dominant membership."""
        d = Drive(name="x", value=0.10, lambda_rate=0.0, kappa=0.0, zones=[
            ZoneSpec("low",  0.10, 0.10),
            ZoneSpec("mid",  0.50, 0.10),
            ZoneSpec("high", 0.90, 0.10),
        ])
        d.update(tick=0)
        assert d._last_zone == "low"
        d.value = 0.88
        d.update(tick=1)
        assert d._last_zone == "high"

    def test_hysteresis_holds_incumbent(self):
        """With α_in=0.9, a barely-dominant new zone cannot displace the old."""
        d = Drive(name="x", value=0.28, lambda_rate=0.0, kappa=0.0,
                  alpha_in=0.9, alpha_out=0.0, zones=[
            ZoneSpec("low",  0.25, 0.08),
            ZoneSpec("high", 0.35, 0.08),
        ])
        d.update(tick=0)
        assert d._last_zone == "low"
        # Move to 0.32 — "high" membership ≈ 0.93 vs low ≈ 0.93 (nearly tied)
        # Actually at 0.32: d=0.03 from high (μ≈0.93), d=0.07 from low (μ≈0.68)
        # With alpha_in=0.9 high qualifies... use 0.30: μ_high≈0.86 < 0.9 → stays
        d.value = 0.30
        d.update(tick=1)
        assert d._last_zone == "low"   # hysteresis held


class TestViabilityLimit:
    def test_breach_emits_event(self):
        d = Drive(name="x", value=0.90, viability=(0.05, 0.85),
                  lambda_rate=0.05, kappa=0.0)
        events = []
        d.on(VIABILITY_BREACHED, lambda p: events.append(p))
        d.update(tick=0)   # drift pushes past 0.85
        assert len(events) == 1
        assert events[0]["side"] == "high"

    def test_within_limits_no_event(self):
        d = Drive(name="x", value=0.50, viability=(0.05, 0.85),
                  lambda_rate=0.0, kappa=0.0)
        events = []
        d.on(VIABILITY_BREACHED, lambda p: events.append(p))
        d.update(tick=0)
        assert len(events) == 0


class TestCanonicalEvents:
    def test_zone_changed_payload(self):
        d = Drive(name="hunger", value=0.70)
        events = []
        d.on(ZONE_CHANGED, lambda p: events.append(p))
        d.update(tick=0)
        assert len(events) == 1
        e = events[0]
        assert e["drive"] == "hunger"
        assert e["zone"] == "equilibrium"
        assert e["side"] == "equilibrium"
        assert "membership" in e

    def test_zone_changed_deficit_is_low_side(self):
        """Satisfaction convention: deficit zones live at LOW x."""
        d = Drive(name="hunger", value=0.15)
        events = []
        d.on(ZONE_CHANGED, lambda p: events.append(p))
        d.update(tick=0)
        assert events[0]["zone"] == "critical_deficit"
        assert events[0]["side"] == "deficit"

    def test_satiated_event(self):
        d = Drive(name="hunger", value=0.60)
        events = []
        d.on(SATIATED, lambda p: events.append(p))
        d.satiate(0.5)
        assert len(events) == 1
        assert events[0]["reduction"] > 0

    def test_coupled_event_with_sources(self):
        drives = Drives([
            Drive(name="ctx", value=0.80, set_point=0.30),
            Drive(name="bl",  value=0.30, set_point=0.30),
        ])
        drives.set_coupling({"ctx": {"bl": 1.0}})
        events = []
        drives.get("bl").on(COUPLED, lambda p: events.append(p))
        drives.update_all(tick=1)
        assert len(events) == 1
        assert "ctx" in events[0]["sources"]

    def test_pressure_updated_with_observed(self):
        var = ObservedVariable(name="spend", kind="budget", limit=100.0)
        var.observe(t=0.0, value=80.0)
        d = Drive(name="metabolic", value=0.30, observed=[var])
        events = []
        d.on(PRESSURE_UPDATED, lambda p: events.append(p))
        d.update(tick=1)
        assert len(events) == 1
        assert events[0]["driving_variable"] == "spend"
        assert d.pressure is not None


class TestSubscriptions:
    def test_subscribe_returns_id_and_receives(self):
        a = Drive(name="a", value=0.30)
        b = Drive(name="b", value=0.30)
        received = []
        sub_id = b.subscribe(a, ZONE_CHANGED, lambda p: received.append(p))
        assert isinstance(sub_id, int)
        a.update(tick=0)
        assert len(received) == 1

    def test_unsubscribe_stops_events(self):
        a = Drive(name="a", value=0.30)
        b = Drive(name="b", value=0.30)
        received = []
        sub_id = b.subscribe(a, ZONE_CHANGED, lambda p: received.append(p))
        b.unsubscribe(sub_id)
        a.update(tick=0)
        assert len(received) == 0

    def test_filtered_by_event_type(self):
        a = Drive(name="a", value=0.30)
        b = Drive(name="b", value=0.30)
        satiated_events = []
        b.subscribe(a, SATIATED, lambda p: satiated_events.append(p))
        a.update(tick=0)    # ZoneChanged — not subscribed
        assert len(satiated_events) == 0
        a.satiate(0.1)
        assert len(satiated_events) == 1
