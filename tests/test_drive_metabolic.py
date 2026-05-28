"""Tests for drives.py — inverted semantics, 5-zone system, tick-based decay."""

import pytest

from binsai.drives import Drive, Drives, Stratum


def make_metabolic(value: float = 0.30) -> Drive:
    return Drive(
        name="metabolic",
        stratum=Stratum.MATERIAL,
        value=value,
        set_point=0.30,
        lambda_rate=0.005,
        satiation_rate=0.10,
    )


class TestDriveSemantics:
    def test_deplete_raises_delta(self):
        """deplete() consumes resources → δ goes UP."""
        d = make_metabolic(0.30)
        d.deplete(0.10)
        assert d.value > 0.30

    def test_satiate_lowers_delta(self):
        """satiate() restores resources → δ goes DOWN."""
        d = make_metabolic(0.50)
        d.satiate(1.0)
        assert d.value < 0.50

    def test_update_increases_delta(self):
        """Basal decay per tick raises δ (metabolic cost of being alive)."""
        d = make_metabolic(0.30)
        before = d.value
        d.update(tick=1)
        assert d.value > before

    def test_update_increases_by_lambda(self):
        d = make_metabolic(0.30)
        d.update(tick=1)
        assert abs(d.value - (0.30 + d.lambda_rate)) < 1e-9

    def test_value_clamped_upper(self):
        d = make_metabolic(0.99)
        d.deplete(0.10)
        assert d.value <= 1.0

    def test_value_clamped_lower(self):
        d = make_metabolic(0.05)
        d.satiate(10.0)
        assert d.value >= 0.0

    def test_invalid_initial_value_raises(self):
        with pytest.raises(ValueError):
            Drive(name="x", stratum=Stratum.MATERIAL, value=1.5)

    def test_deviation_positive_when_above_setpoint(self):
        """High δ = positive deviation from set-point."""
        d = make_metabolic(0.60)
        assert d.deviation > 0

    def test_deviation_negative_when_below_setpoint(self):
        """Low δ = negative deviation (oversated)."""
        d = make_metabolic(0.10)
        assert d.deviation < 0


class TestZoneSystem:
    def test_zone_at_critical_center(self):
        d = make_metabolic(0.80)
        assert d.get_zone() == "critical"

    def test_zone_at_nominal_center(self):
        d = make_metabolic(0.30)
        assert d.get_zone() == "nominal"

    def test_zone_at_oversated_center(self):
        d = make_metabolic(0.05)
        assert d.get_zone() == "oversated"

    def test_zone_memberships_sum_to_one(self):
        for val in [0.05, 0.15, 0.30, 0.55, 0.80]:
            d = make_metabolic(val)
            total = sum(d.zone_memberships().values())
            assert abs(total - 1.0) < 1e-9

    def test_zone_memberships_keys(self):
        d = make_metabolic(0.30)
        assert set(d.zone_memberships().keys()) == {"oversated", "sated", "nominal", "loaded", "critical"}


class TestDrivesCollection:
    def test_from_names_metabolic(self):
        drives = Drives.from_names(["metabolic"])
        assert drives.get("metabolic") is not None
        assert drives.get("safety") is None

    def test_update_all_increases_metabolic(self):
        drives = Drives.from_names(["metabolic"])
        m = drives.get("metabolic")
        before = m.value
        drives.update_all(tick=1)
        assert m.value > before

    def test_to_dict_contains_zone(self):
        drives = Drives.from_names(["metabolic"])
        d = drives.to_dict()
        assert "zone" in d["metabolic"]
        assert "memberships" in d["metabolic"]
