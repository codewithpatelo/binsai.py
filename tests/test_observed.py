"""Tests for observed.py — ObservedVariable level+pace pressure (EPA §4)."""

import pytest

from binsai.observed import (
    ObservedVariable, VariableKind, RateEstimator, load_contract,
)
from binsai.events import SENSOR_INVALID, ZONE_CHANGED


class TestLevelPressure:
    def test_budget_at_origin_has_zero_pressure(self):
        v = ObservedVariable(name="spend", kind="budget", limit=150.0)
        v.observe(t=0.0, value=0.0)
        assert v.last_level_pressure == pytest.approx(0.0, abs=1e-3)

    def test_budget_approaching_limit_grows(self):
        v = ObservedVariable(name="spend", kind="budget", limit=150.0)
        v.observe(t=0.0, value=10.0)
        p_low = v.pressure(t=0.0)
        v.observe(t=1.0, value=140.0)
        p_high = v.pressure(t=1.0)
        assert p_high > p_low
        assert p_high > 10.0   # barrier grows fast near the limit

    def test_floor_low_value_is_high_pressure(self):
        v = ObservedVariable(name="ram_free", kind="floor",
                             limit=2.0, set_point=12.0)
        v.observe(t=0.0, value=11.0)
        p_ok = v.pressure(t=0.0)
        v.observe(t=1.0, value=2.5)
        p_low = v.pressure(t=1.0)
        assert p_low > p_ok

    def test_band_two_sided(self):
        v = ObservedVariable(name="temp", kind="band", limit=(15.0, 30.0),
                             set_point=22.0)
        v.observe(t=0.0, value=22.0)
        p_eq = v.pressure(t=0.0)
        v.observe(t=1.0, value=29.0)
        p_hi = v.pressure(t=1.0)
        v.observe(t=2.0, value=16.0)
        p_lo = v.pressure(t=2.0)
        assert p_hi > p_eq and p_lo > p_eq


class TestPacePressure:
    def test_budget_ratio_mode(self):
        """Sustainable rate = remaining / time_left. Overspend → pace pressure."""
        v = ObservedVariable(name="spend", kind="budget", limit=150.0,
                             window=10.0, pacing_mode="ratio",
                             rate_estimator={"type": "window", "span": 2.0})
        # Spend 60 in 1h at t=1: rate=60/h, sustainable=90/9=10/h → over
        v.observe(t=0.0, value=0.0)
        v.observe(t=1.0, value=60.0)
        p = v.pace_pressure(t=1.0)
        assert p is not None and p > 0

    def test_floor_sustainable_rate(self):
        """RAM free 11.8GB, floor 2GB, 6h left → sustainable ≈ 1.6 GB/h."""
        v = ObservedVariable(name="ram_free", kind="floor",
                             limit=2.0, set_point=12.0, window=6.0)
        v.observe(t=0.0, value=11.8)
        r = v.sustainable_rate(t=0.0)
        assert r == pytest.approx(9.8 / 6.0, rel=1e-3)

    def test_target_required_rate(self):
        """2 deliveries needed, 0 done, 8h left → required = 0.25/h."""
        v = ObservedVariable(name="deliveries", kind="target", limit=2.0,
                             window=8.0)
        v.observe(t=0.0, value=0.0)
        r = v.sustainable_rate(t=0.0)
        assert r == pytest.approx(0.25)

    def test_time_to_violation_mode(self):
        """τ = margin / rate_toward_limit; p = 1 − τ/(T_rec+T_react)."""
        v = ObservedVariable(name="spend", kind="budget", limit=150.0,
                             window=20.0, pacing_mode="time_to_violation",
                             recovery_time=1.0, reaction_time=0.5,
                             rate_estimator={"type": "window", "span": 2.0})
        # spending 10/h, margin 140 → τ = 14h; correction needs 1.5h → p ≈ 0
        v.observe(t=0.0, value=0.0)
        v.observe(t=1.0, value=10.0)
        p_slow = v.pace_pressure(t=1.0)
        # spending 100/h, margin 40 → τ = 0.4h < 1.5h correction → p ≈ 0.73
        v2 = ObservedVariable(name="spend", kind="budget", limit=150.0,
                              window=20.0, pacing_mode="time_to_violation",
                              recovery_time=1.0, reaction_time=0.5,
                              rate_estimator={"type": "window", "span": 2.0})
        v2.observe(t=0.0, value=0.0)
        v2.observe(t=1.0, value=110.0)
        p_fast = v2.pace_pressure(t=1.0)
        assert p_fast is not None and p_slow is not None
        assert p_fast > p_slow


class TestSensorValidity:
    def test_no_samples_is_invalid(self):
        v = ObservedVariable(name="x", kind="budget", limit=100.0)
        assert not v.is_valid
        assert v.invalid_reason == "no samples"

    def test_out_of_range_emits_sensor_invalid(self):
        v = ObservedVariable(name="x", kind="budget", limit=100.0,
                             valid_range=(0.0, 200.0))
        events = []
        v.on(SENSOR_INVALID, lambda p: events.append(p))
        v.observe(t=0.0, value=999.0)
        assert len(events) == 1
        assert "above physical range" in events[0]["reason"]
        assert not v.is_valid

    def test_staleness_emits_sensor_invalid(self):
        v = ObservedVariable(name="x", kind="budget", limit=100.0,
                             max_staleness=1.0)
        v.observe(t=0.0, value=10.0)
        events = []
        v.on(SENSOR_INVALID, lambda p: events.append(p))
        p = v.pressure(t=5.0)   # 5 units since last sample > max_staleness
        assert p is None
        assert len(events) == 1
        assert "stale" in events[0]["reason"]

    def test_invalid_contributes_nothing(self):
        """An invalid sensor is not assumed green — it contributes nothing."""
        v = ObservedVariable(name="x", kind="budget", limit=100.0)
        assert v.pressure(t=0.0) is None


class TestZones:
    def test_zone_changed_event(self):
        v = ObservedVariable(name="x", kind="budget", limit=100.0)
        events = []
        v.on(ZONE_CHANGED, lambda p: events.append(p))
        v.observe(t=0.0, value=5.0)     # low pressure → equilibrium
        v.observe(t=1.0, value=90.0)    # high pressure → deficit zone
        assert len(events) >= 2
        assert events[-1]["zone"] != events[0]["zone"]

    def test_zone_names_use_canonical_sides(self):
        v = ObservedVariable(name="x", kind="budget", limit=100.0)
        v.observe(t=0.0, value=90.0)
        zone = v.zone
        assert "deficit" in zone or zone == "equilibrium"


class TestRateEstimator:
    def test_window_estimator(self):
        est = RateEstimator(type="window", span=2.0)
        samples = [(0.0, 0.0), (1.0, 10.0), (2.0, 20.0)]
        rate, cov = est.estimate(samples, monotonic=True)
        assert rate == pytest.approx(10.0)
        assert cov == pytest.approx(1.0)

    def test_monotonic_reset_not_negative(self):
        """A drop in an accumulated series is a source reset, not negative rate."""
        est = RateEstimator(type="window", span=10.0)
        samples = [(0.0, 100.0), (1.0, 5.0), (2.0, 15.0)]  # reset at t=1
        rate, _ = est.estimate(samples, monotonic=True)
        assert rate > 0   # 5 + 10 = 15 increase over 2 units, not −85

    def test_ewma(self):
        est = RateEstimator(type="ewma", alpha=0.5)
        samples = [(0.0, 0.0), (1.0, 10.0), (2.0, 30.0)]
        rate, cov = est.estimate(samples, monotonic=True)
        assert rate > 0
        assert cov == 1.0


class TestContractLoader:
    def test_load_contract(self, tmp_path):
        contract = {
            "variables": [{
                "name": "gasto_api", "kind": "budget", "unit": "USD",
                "limit": 150.0, "window": 11.5,
                "pacing_mode": "time_to_violation",
                "recovery_time": 0.5, "reaction_time": 0.1,
                "rate_estimator": {"type": "window", "span": 1.0},
                "monotonic": True, "max_staleness": 0.25,
                "valid_range": [0, None],
                "source": "dashboard.billed",
                "provenance": "measurement",
            }]
        }
        p = tmp_path / "viability-contract.json"
        p.write_text(__import__("json").dumps(contract))
        vars_ = load_contract(p)
        assert len(vars_) == 1
        v = vars_[0]
        assert v.name == "gasto_api"
        assert v.kind == VariableKind.BUDGET
        assert v.pacing_mode == "time_to_violation"
