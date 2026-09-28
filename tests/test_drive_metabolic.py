"""Tests for drives.py — satisfaction convention, 7-zone system, tick drift.

Convention (docs/EPA.md §2): x is the satisfaction level of the need —
HIGH = slack/satisfied, LOW = deficit. Pull drives (metabolic) have
basal_direction="recover" (λ>0: slack replenishes when idle); push drives
use "decay" (λ<0: satisfaction decays under neglect).
"""

import pytest

from binsai.drives import Drive, Drives, Stratum, ZoneSpec


def make_metabolic(value: float = 0.70) -> Drive:
    return Drive(
        name="metabolic",
        stratum=Stratum.MATERIAL,
        category="pull",
        basal_direction="recover",
        value=value,
        set_point=0.70,
        lambda_rate=0.005,
        satiation_rate=0.10,
    )


class TestDriveSemantics:
    def test_deplete_lowers_satisfaction(self):
        """deplete() consumes resources → satisfaction x goes DOWN."""
        d = make_metabolic(0.70)
        d.deplete(0.10)
        assert d.value < 0.70

    def test_satiate_raises_satisfaction(self):
        """satiate() restores resources → satisfaction x goes UP."""
        d = make_metabolic(0.40)
        d.satiate(1.0)
        assert d.value > 0.40

    def test_update_recovers_pull_drive(self):
        """Pull drive under inaction: slack replenishes (recover)."""
        d = make_metabolic(0.60)
        before = d.value
        d.update(tick=1)
        assert d.value > before

    def test_update_increases_by_lambda(self):
        """Basal drift alone (κ=0, no spring) moves x by λ·Δt² on the first
        pulse under second-order dynamics (v += a·Δt, then x += v·Δt)."""
        with pytest.warns(UserWarning):   # κ=0 → grip 0 < λ⁰: drift wins
            d = Drive(name="metabolic", stratum=Stratum.MATERIAL,
                      category="pull", basal_direction="recover",
                      value=0.60, set_point=0.70, lambda_rate=0.005,
                      kappa=0.0)
        d.update(tick=1)
        assert abs(d.value - (0.60 + d.lambda_rate)) < 1e-9

    def test_push_drive_decays_under_neglect(self):
        """Push drive under inaction: satisfaction decays toward deficit."""
        d = Drive(name="service", category="push", basal_direction="decay",
                  value=0.70, set_point=0.70, lambda_rate=0.005,
                  kappa=0.0)
        d.update(tick=1)
        assert d.value < 0.70

    def test_value_clamped_upper(self):
        d = make_metabolic(0.99)
        d.satiate(10.0)
        assert d.value <= 1.0

    def test_value_clamped_lower(self):
        d = make_metabolic(0.05)
        d.deplete(0.10)
        assert d.value >= 0.0

    def test_invalid_initial_value_raises(self):
        with pytest.raises(ValueError):
            Drive(name="x", stratum=Stratum.MATERIAL, value=1.5)

    def test_deviation_positive_when_above_setpoint(self):
        """Satisfaction above set-point = positive deviation (slack)."""
        d = make_metabolic(0.80)
        assert d.deviation > 0

    def test_deviation_negative_when_below_setpoint(self):
        """Satisfaction below set-point = deficit."""
        d = make_metabolic(0.40)
        assert d.deviation < 0


class TestZoneSystem:
    def test_zone_at_critical_deficit(self):
        """Critical deficit sits at LOW x under the satisfaction convention."""
        d = make_metabolic(0.20)
        assert d.get_zone() == "critical_deficit"

    def test_zone_at_equilibrium(self):
        d = make_metabolic(0.70)
        assert d.get_zone() == "equilibrium"

    def test_zone_at_critical_superavit(self):
        d = make_metabolic(0.95)
        assert d.get_zone() == "critical_superavit"

    def test_zone_memberships_sum_to_one(self):
        for val in [0.05, 0.20, 0.45, 0.60, 0.70, 0.87, 0.95]:
            d = make_metabolic(val)
            total = sum(d.zone_memberships().values())
            assert abs(total - 1.0) < 1e-9

    def test_zone_memberships_keys(self):
        d = make_metabolic(0.70)
        assert set(d.zone_memberships().keys()) == {
            "critical_superavit", "high_superavit", "moderate_superavit",
            "equilibrium", "moderate_deficit", "high_deficit", "critical_deficit",
        }

    def test_custom_zones_other_convention(self):
        """Users can still model a deficit-magnitude axis: custom zones put
        deficit names at HIGH x and get_zone/side resolve correctly."""
        d = Drive(name="hunger", value=0.85, set_point=0.30, zones=[
            ZoneSpec("equilibrium", 0.30, 0.10),
            ZoneSpec("critical_deficit", 0.85, 0.12),
        ])
        assert d.get_zone() == "critical_deficit"


class TestDrivesCollection:
    def test_from_names_metabolic(self):
        drives = Drives.from_names(["metabolic"])
        assert drives.get("metabolic") is not None
        assert drives.get("safety") is None

    def test_update_all_recovers_metabolic(self):
        """Pull metabolic under inaction → satisfaction rises."""
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

    def test_viability_minimum_categories(self):
        """Canonical set must contain ≥1 push and ≥1 pull drive."""
        drives = Drives.stratified()
        assert drives.check_viability_minimum() == []
        cats = {d.category for d in drives.all.values()}
        assert "push" in cats and "pull" in cats
