"""Tests for signed basal drift (β = lambda_rate ∈ ℝ) in drives.py."""

import pytest

from binsai.drives import Drive, Stratum


def make_drive(**kw) -> Drive:
    defaults = dict(
        name="d",
        stratum=Stratum.MATERIAL,
        value=0.50,
        set_point=0.30,
        kappa=0.05,
        lambda_rate=0.005,
        spring="linear",   # these tests pin the legacy damper semantics
    )
    defaults.update(kw)
    return Drive(**defaults)


class TestSignedDrift:
    def test_positive_lambda_raises_value(self):
        """β > 0: inaction accumulates need (classic hunger drift).

        Start AT the set-point: the spring is neutral there, so β is the
        only force and its sign decides the first movement direction.
        """
        d = make_drive(value=0.30)
        d.update(tick=1)
        assert d.value > 0.30

    def test_negative_lambda_lowers_value(self):
        """β < 0: inaction is restorative (sleep / energy recovery)."""
        d = make_drive(value=0.30, lambda_rate=-0.005)
        d.update(tick=1)
        assert d.value < 0.30

    def test_zero_lambda_only_spring_moves(self):
        """β = 0 above set-point: only the spring pulls back toward ε."""
        d = make_drive(lambda_rate=0.0)
        d.update(tick=1)
        assert d.value < 0.50

    def test_resting_level_formula(self):
        """x_rest = ε + β/κ."""
        d = make_drive(lambda_rate=0.005, kappa=0.05)
        assert abs(d.resting_level - (0.30 + 0.005 / 0.05)) < 1e-9

    def test_resting_level_below_setpoint_for_restorative(self):
        """Negative β settles the drive on the surplus side of ε."""
        d = make_drive(lambda_rate=-0.005, kappa=0.05)
        assert d.resting_level < 0.30

    def test_update_balanced_at_resting_level(self):
        """At x_rest the spring and the drift cancel exactly."""
        d = make_drive(value=0.40, lambda_rate=0.005, kappa=0.05)
        d.update(tick=1)
        assert abs(d.value - 0.40) < 1e-9

    def test_converges_to_resting_level_from_deficit(self):
        """Unforced drive relaxes to x_rest from a deficit."""
        d = make_drive(value=0.80, lambda_rate=0.005, kappa=0.05)
        for t in range(200):
            d.update(tick=t)
        assert abs(d.value - 0.40) < 0.01

    def test_restorative_inaction_lowers_deficit_to_rest(self):
        """Negative β: a stressed drive recovers passively to x_rest < ε."""
        d = make_drive(value=0.60, lambda_rate=-0.005, kappa=0.05)
        for t in range(200):
            d.update(tick=t)
        assert abs(d.value - 0.20) < 0.01

    def test_no_spring_positive_drifts_to_upper_bound(self):
        """κ = 0, β > 0: pure integrator, inaction maxes the drive out."""
        d = make_drive(value=0.30, kappa=0.0, lambda_rate=0.005)
        for t in range(500):
            d.update(tick=t)
        assert d.value == pytest.approx(1.0)

    def test_no_spring_negative_drifts_to_lower_bound(self):
        """κ = 0, β < 0: pure integrator downward, hits the surplus floor."""
        d = make_drive(value=0.30, kappa=0.0, lambda_rate=-0.005)
        for t in range(500):
            d.update(tick=t)
        assert d.value == pytest.approx(0.0)

    def test_resting_level_no_spring(self):
        """Without spring, resting_level reports the boundary β points to."""
        assert make_drive(kappa=0.0, lambda_rate=0.005).resting_level == 1.0
        assert make_drive(kappa=0.0, lambda_rate=-0.005).resting_level == 0.0

    def test_positive_lambda_reaches_superavit_zones(self):
        """Recover drift (λ>0) settles above x* → superavit zones
        (satisfaction convention: high x = slack). Custom zones aligned to
        this drive's set_point=0.30."""
        from binsai.drives import ZoneSpec
        d = make_drive(value=0.20, lambda_rate=0.005, kappa=0.05, zones=[
            ZoneSpec("critical_deficit",   0.05, 0.10),
            ZoneSpec("equilibrium",        0.30, 0.10),
            ZoneSpec("moderate_superavit", 0.45, 0.10),
            ZoneSpec("critical_superavit", 0.90, 0.10),
        ])
        for t in range(200):
            d.update(tick=t)
        # x_rest = 0.30 + 0.005/0.05 = 0.40 → superavit side of x*
        assert "superavit" in d.get_zone()