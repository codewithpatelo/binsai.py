"""EPA v2 tests — second-order fatigable magnetic spring (docs/paov2.tex).

State (x, v); acceleration a = λ − S − c·v + u + ΣW(x_j − x*_j);
S = κ_ef·d·e^(−|d|/w); κ_ef = κ·e^(−f·Λ); Λ' = |d| − ρ_Λ·Λ.
"""

import math
import warnings

import pytest

from binsai.drives import Drive


def make_drive(**kw) -> Drive:
    base = dict(name="svc", value=0.70, set_point=0.70,
                kappa=0.05, lambda_rate=0.001, basal_direction="decay",
                spring="magnetic-2nd", damping=0.10,
                spring_reach=0.10, viability=(0.05, 0.95))
    base.update(kw)
    return Drive(**base)


class TestSecondOrderState:
    def test_velocity_integrates(self):
        """v += a·dt; x += v·dt — under basal decay, v goes negative."""
        d = make_drive(spring_reach=float("inf"), damping=0.0,
                       spring_fatigue=0.0)
        d.update(tick=1)
        assert d.velocity < 0          # λ<0 accelerates down
        assert d.value < 0.70

    def test_spring_pulls_back_to_setpoint(self):
        """Deficit with no drift: the spring accelerates toward x*."""
        d = make_drive(lambda_rate=0.0, damping=0.20)
        d.deplete(0.20)
        for t in range(400):
            d.update(tick=t)
        assert abs(d.value - 0.70) < 0.05

    def test_damped_oscillation_settles(self):
        """With damping, a displaced system oscillates and settles."""
        d = make_drive(lambda_rate=0.0, damping=0.30,
                       spring_fatigue=0.0, spring_reach=float("inf"))
        d.deplete(0.15)
        for t in range(600):
            d.update(tick=t)
        xs = [v for _, v in d.history[-100:]]
        assert max(xs) - min(xs) < 0.02
        assert abs(d.velocity) < 0.01


class TestFatigueAndAllostatic:
    def test_allostatic_load_grows_under_deviation(self):
        d = make_drive()
        d.deplete(0.20)
        for t in range(50):
            d.update(tick=t)
        assert d.allostatic_load > 0.0

    def test_fatigue_weakens_grip(self):
        """κ_ef = κ·e^(−f·Λ) — grip decays with exposure."""
        d = make_drive(spring_fatigue=0.30)
        d.deplete(0.30)
        for t in range(100):
            d.update(tick=t)
        assert d.kappa_eff < d.kappa

    def test_fatigue_kills_under_prolonged_neglect(self):
        """f>0: sustained deviation wears the spring until drift escapes."""
        d = Drive(name="svc", value=0.70, set_point=0.70, kappa=0.05,
                  lambda_rate=0.001, basal_direction="decay",
                  spring="magnetic-2nd", spring_reach=0.111,
                  damping=0.10, spring_fatigue=0.10,
                  allostatic_recovery=0.002, viability=(0.05, 0.95))
        dead = None
        for t in range(3000):
            d.update(tick=t)
            if d.value <= 0.05:
                dead = t
                break
        assert dead is not None

    def test_no_fatigue_survives_neglect(self):
        """f=0 inside the stable regime: bounded oscillation, no death."""
        d = Drive(name="svc", value=0.70, set_point=0.70, kappa=0.05,
                  lambda_rate=0.001, basal_direction="decay",
                  spring="magnetic-2nd", spring_reach=0.111,
                  damping=0.10, spring_fatigue=0.0,
                  viability=(0.05, 0.95))
        for t in range(2000):
            d.update(tick=t)
        assert d.value > 0.05


class TestFiniteReachEscape:
    def test_shock_beyond_reach_escapes(self):
        """Finite w: past d*, basal drift beats the grip — escape to the wall."""
        # stable regime: d* = 0.30 < margin 0.65
        w = Drive.design_spring_reach(0.05, 0.001, 0.30)
        d = Drive(name="svc", value=0.70, set_point=0.70, kappa=0.05,
                  lambda_rate=0.001, basal_direction="decay",
                  spring="magnetic-2nd", spring_reach=w,
                  damping=0.05, spring_fatigue=0.0,
                  viability=(0.05, 0.95))
        d.impulse(-0.45)               # |d| = 0.45 > d* = 0.30 → past no-return
        for t in range(1500):
            d.update(tick=t)
            if d.value <= 0.05:
                break
        assert d.value <= 0.10         # escaped to the viability wall

    def test_small_shock_recovers(self):
        d = make_drive(spring_fatigue=0.0, lambda_rate=0.0, damping=0.30)
        d.impulse(-0.10)               # inside reach
        for t in range(600):
            d.update(tick=t)
        assert abs(d.value - 0.70) < 0.05


class TestWDesignRule:
    def test_no_return_point_lambert(self):
        """d* = −w·W₋₁(−λ⁰/(κw)) — matches the numeric root of κd·e^(−d/w)=λ."""
        d = make_drive(spring_fatigue=0.0)
        d_star = d.no_return_point()
        assert d_star is not None
        # verify: the grip at d* balances the drift
        grip = d.kappa * d_star * math.exp(-d_star / d.spring_reach)
        assert abs(grip - abs(d.lambda_rate)) < 1e-6

    def test_no_return_none_when_drift_dominates(self):
        d = make_drive(kappa=0.001, lambda_rate=0.05)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d2 = d
        assert d2.no_return_point() is None

    def test_warns_when_d_star_beyond_viability(self):
        with pytest.warns(UserWarning, match="no-return point"):
            Drive(name="bad", value=0.70, set_point=0.70, kappa=0.05,
                  lambda_rate=0.001, basal_direction="decay",
                  spring="magnetic-2nd", spring_reach=0.30,
                  viability=(0.10, 0.95))

    def test_warns_when_drift_dominates(self):
        with pytest.warns(UserWarning, match="drift dominates"):
            Drive(name="bad", value=0.70, set_point=0.70, kappa=0.0,
                  lambda_rate=0.05, basal_direction="decay",
                  spring="magnetic-2nd", spring_reach=0.10)

    def test_no_warning_in_valid_regime(self):
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            make_drive()
        assert not any("no-return" in str(w.message) or "drift dominates"
                       in str(w.message) for w in ws)

    def test_design_spring_reach_roundtrip(self):
        """w = d*/ln(κd*/λ⁰): designed w reproduces the requested d*."""
        w = Drive.design_spring_reach(0.05, 0.001, 0.30)
        d = Drive(name="rt", value=0.70, set_point=0.70, kappa=0.05,
                  lambda_rate=0.001, basal_direction="decay",
                  spring="magnetic-2nd", spring_reach=w,
                  viability=(0.05, 0.95))
        assert abs(d.no_return_point() - 0.30) < 1e-6

    def test_design_spring_reach_infeasible(self):
        with pytest.raises(ValueError):
            Drive.design_spring_reach(0.05, 0.05, 0.05)  # κd*/λ = 0.05 < e


class TestStimulusChannels:
    def test_sustain_enters_acceleration(self):
        """Sustained stimulus contributes to u (acceleration channel)."""
        d = make_drive(lambda_rate=0.0, damping=0.0,
                       spring_reach=float("inf"))
        d.velocity = 0.0
        d.sustain("work", -0.01)
        d.update(tick=1)
        assert d.velocity < 0          # sustained push downward
        d.release_stimulus("work")
        assert not d._sustained

    def test_impulse_jumps_level(self):
        """Impulsive stimulus: instant x jump, no velocity change."""
        d = make_drive()
        v0 = d.velocity
        d.impulse(-0.20)
        assert abs(d.value - 0.50) < 1e-9
        assert d.velocity == v0

    def test_g_full_satisfaction(self):
        d = make_drive()
        g = d.impulse(-0.10, expected=-0.10)
        assert abs(g - 1.0) < 1e-9

    def test_g_partial_satisfaction(self):
        """Clipping at the floor → observed < expected → g < 1."""
        d = make_drive(value=0.10)
        g = d.impulse(-0.20, expected=-0.20)   # only -0.10 effective
        assert 0.0 < g < 1.0

    def test_g_zero_when_nothing_happens(self):
        """Action executes but satiates nothing: g=0."""
        d = make_drive(value=0.0)
        g = d.impulse(-0.10, expected=-0.10)
        assert g == 0.0


class TestDriftShapes:
    def _accel(self, shape, **kw):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # κ=0 warns — intentional here
            d = make_drive(lambda_rate=-0.001, damping=0.0, kappa=0.0,
                           drift_shape=shape, **kw)
        d.value = 0.50   # |d| = 0.20
        d.update(tick=1)
        return d.velocity / d.dt   # ≈ a (κ=0 → no spring term)

    def test_linear_shape_is_constant(self):
        a = self._accel("linear")
        assert abs(a - (-0.001)) < 1e-9

    def test_exponential_shape_amplifies(self):
        a_lin = self._accel("linear")
        a_exp = self._accel("exponential", drift_gamma=2.0)
        assert abs(a_exp) > abs(a_lin)     # e^{γ|d|} > 1

    def test_saturating_shape_diminishes(self):
        a_lin = self._accel("linear")
        a_sat = self._accel("saturating", drift_s=0.10)
        assert abs(a_sat) < abs(a_lin)     # 1−e^{−|d|/s} < 1


class TestAutonomousPressure:
    def test_p_aut_displacement_term(self):
        d = make_drive()
        d.deplete(0.20)                    # |d| = 0.20, margin lo = 0.65
        pc = d.pressure_components()
        assert abs(pc["autonomous"] - 0.20 / 0.65) < 1e-6

    def test_p_aut_velocity_term(self):
        """At equal deviation, a drive falling fast is worse than one at rest."""
        still = make_drive()
        still.deplete(0.20)
        falling = make_drive()
        falling.deplete(0.20)
        falling.velocity = -0.05
        p_still = still.pressure_components()["autonomous"]
        p_fall = falling.pressure_components()["autonomous"]
        assert p_fall > p_still

    def test_p_aut_eta_zero_is_pure_displacement(self):
        d = make_drive(eta=0.0)
        d.deplete(0.20)
        d.velocity = -0.10
        pc = d.pressure_components()
        assert abs(pc["autonomous"] - 0.20 / 0.65) < 1e-6


class TestLegacySprings:
    def test_pulsatile_still_pulses(self):
        d = Drive(name="h", value=0.80, set_point=0.50, kappa=0.1,
                  lambda_rate=0.0, spring="pulsatile", spring_threshold=0.05)
        for t in range(20):
            d.update(tick=t)
        assert any(k == "release" for _, k in d.events)

    def test_linear_still_damps(self):
        d = Drive(name="h", value=0.80, set_point=0.50, kappa=0.1,
                  lambda_rate=0.0, spring="linear")
        d.update(tick=0)
        assert abs(d.value - 0.77) < 1e-9

    def test_pulsatile_keeps_tension_pressure(self):
        """Legacy arm keeps σ as its autonomous pressure."""
        d = Drive(name="h", value=0.80, set_point=0.50, kappa=0.1,
                  lambda_rate=0.0, spring="pulsatile", spring_threshold=0.05)
        d.update(tick=0)
        pc = d.pressure_components()
        assert pc["autonomous"] == abs(pc["tension"])
