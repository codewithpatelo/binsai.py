"""EPA v2.1 — the ADSR perturbation channel and the two-phase calibrator."""

import math
import random

import pytest

from binsai.calibration import (
    Calibration, Perturbation, PerturbationChannel, PerturbationSpec, ShapeRatios,
    basal_time_to_death, calibrate, calibrate_perturbation, grip, resting_point,
)
from binsai.drives import Drive

WINDOW = 690.0          # 11.5 h at a one-minute tick
MARGIN = 0.45
SP = 0.5


def _cal(ttd_hours: float, direction: float = 1.0) -> Calibration:
    return calibrate(margin=MARGIN, window=WINDOW, ttd_basal=ttd_hours * 60,
                     direction=direction, set_point=SP, allostatic_recovery=0.01)


# ── phase 1 / phase 2 are orthogonal ─────────────────────────────────────────

def test_fatigue_alone_moves_the_death_date():
    """The geometry decides how it regulates; f decides when negligence kills."""
    shapes, fatigues = set(), []
    for target in (4, 6, 8, 10):
        c = _cal(target)
        shapes.add((round(c.kappa, 8), round(c.w, 6),
                    round(abs(c.lambda0), 9), round(c.damping, 6)))
        fatigues.append(c.fatigue)
        assert c.ttd_basal == pytest.approx(target * 60, rel=0.02)
    assert len(shapes) == 1, "geometry moved with the death target"
    assert fatigues == sorted(fatigues, reverse=True), "more fatigue must die sooner"


def test_both_inequalities_hold():
    """A4 and 'regulating is possible' are two tests, not one regime choice."""
    c = _cal(8)
    assert c.grip_ratio > 1.0            # the spring holds
    assert c.ttd_basal < WINDOW          # fatigue eats it
    assert c.overshoot_over_reach < 1.0  # it does not escape by inertia first
    assert c.sound


def test_without_fatigue_negligence_never_kills():
    """binsai's own `equilibrium` says it: with f = 0 the rest point is permanent."""
    c = _cal(8)
    alive = basal_time_to_death(
        kappa=c.kappa, w=c.w, lambda0=abs(c.lambda0), damping=c.damping,
        fatigue=0.0, allostatic_recovery=c.allostatic_recovery,
        set_point=SP, margin=MARGIN, window=WINDOW)
    assert alive is None


def test_the_spring_postpones_it_does_not_save():
    """Same drift with and without the magnet: the spring buys time, then loses."""
    c = _cal(8)
    kw = dict(lambda0=abs(c.lambda0), damping=c.damping, fatigue=c.fatigue,
              allostatic_recovery=c.allostatic_recovery, set_point=SP,
              margin=MARGIN, window=WINDOW)
    with_spring = basal_time_to_death(kappa=c.kappa, w=c.w, **kw)
    without = basal_time_to_death(kappa=0.0, w=c.w, **kw)
    assert without is not None and with_spring is not None
    assert with_spring > 3 * without


def test_margin_scaling_law():
    """kappa, c and rho are invariant; lambda and w scale with the margin; f with 1/margin."""
    ref = calibrate(margin=0.30, window=WINDOW, ttd_basal=480, set_point=SP,
                    allostatic_recovery=0.01)
    for m in (0.36, 0.45):
        r = m / 0.30
        got = calibrate(margin=m, window=WINDOW, ttd_basal=480, set_point=SP,
                        allostatic_recovery=0.01)
        assert got.kappa == pytest.approx(ref.kappa, rel=1e-9)
        assert got.damping == pytest.approx(ref.damping, rel=1e-9)
        assert got.w == pytest.approx(ref.w * r, rel=1e-9)
        assert abs(got.lambda0) == pytest.approx(abs(ref.lambda0) * r, rel=1e-9)
        assert got.fatigue == pytest.approx(ref.fatigue / r, rel=1e-6)


def test_viability_band_must_not_touch_the_state_bound():
    """A wall on the state bound is a clip: the drive can never cross it."""
    with pytest.raises(ValueError, match="state bound"):
        calibrate(margin=0.5, window=WINDOW, ttd_basal=480, set_point=SP)


def test_derived_quantities_agree_with_the_formulas():
    c = _cal(8)
    assert c.grip == pytest.approx(grip(c.kappa, c.w))
    assert c.grip_ratio == pytest.approx(c.grip / abs(c.lambda0))
    assert resting_point(c.kappa, c.w, c.lambda0) == pytest.approx(c.rest_point, rel=0.02)


# ── the ADSR envelope ────────────────────────────────────────────────────────

def _flat_drive() -> Drive:
    """No drift, no spring: a straight line, so only the envelope shows."""
    return Drive(name="plano", set_point=SP, value=SP, kappa=0.0, lambda_rate=0.0,
                 spring="magnetic-2nd", spring_reach=1.0, damping=0.0,
                 spring_fatigue=0.0, dt=1.0, viability=(SP - MARGIN, SP + MARGIN))


def test_attack_scales_only_the_peak():
    """The whole point of the knob: A raises the wave, it does not move the rest."""
    peaks = []
    for attack in (0.05, 0.10, 0.20):
        d = _flat_drive()
        ch = PerturbationChannel(d, PerturbationSpec(attack=attack, sustain=attack / 4,
                                                     t_attack=4, tau=3), MARGIN)
        ch.fire(10, 3, +1)
        trace = []
        for t in range(1, 120):
            ch.settle(t)
            d.update(tick=t)
            trace.append(d.value - SP)
        peaks.append(max(trace))
    assert peaks[1] / peaks[0] == pytest.approx(2.0, rel=0.1)
    assert peaks[2] / peaks[0] == pytest.approx(4.0, rel=0.1)


def test_envelope_has_attack_decay_and_sustain():
    d = _flat_drive()
    spec = PerturbationSpec(attack=0.20, sustain=0.05, t_attack=6, tau=8, t_release=20)
    ch = PerturbationChannel(d, spec, MARGIN)
    ch.fire(1, 3, +1)
    at = {}
    for t in range(1, 200):
        ch.settle(t)
        d.update(tick=t)
        at[t] = d.value - SP
    assert at[3] < at[7]                                   # A: still climbing
    assert at[7] == pytest.approx(0.20 * MARGIN, rel=0.1)  # peak at the attack level
    assert at[40] < at[7]                                  # D: fell off the peak
    assert at[150] == pytest.approx(at[100], rel=0.05)     # S: holds, does not fade
    assert at[150] > 0.5 * 0.05 * MARGIN


def test_only_an_action_closes_an_event():
    """ADS is the world's, R is the agent's. The world never releases."""
    d = _flat_drive()
    ch = PerturbationChannel(d, PerturbationSpec(attack=0.2, sustain=0.06, t_release=15), MARGIN)
    ch.fire(1, 3, +1)
    for t in range(1, 300):
        ch.settle(t)
        d.update(tick=t)
    assert ch.load == 1 and d.value - SP > 0.02           # still pressing after 5 h
    ch.correct(300, g=1.0)
    for t in range(300, 340):
        ch.settle(t)
        d.update(tick=t)
    assert ch.load == 0
    assert d.value - SP == pytest.approx(0.0, abs=1e-6)


def test_an_action_that_satiates_nothing_leaves_the_event_open():
    d = _flat_drive()
    ch = PerturbationChannel(d, PerturbationSpec(attack=0.2, sustain=0.06), MARGIN)
    p = ch.fire(1, 3, +1)
    for t in range(1, 60):
        ch.settle(t)
        d.update(tick=t)
    held = d.value - SP
    ch.correct(60, g=0.0)                                  # ran, achieved nothing
    for t in range(60, 120):
        ch.settle(t)
        d.update(tick=t)
    assert p.g == 0.0 and ch.load == 1
    assert d.value - SP == pytest.approx(held, rel=0.05)


def test_direction_is_the_world_not_the_drive_side():
    """A low delivery pushes service down wherever the drive happens to sit."""
    for start in (SP - 0.2, SP + 0.2):
        d = _flat_drive()
        d.value = start
        ch = PerturbationChannel(d, PerturbationSpec(attack=0.2, t_attack=1), MARGIN)
        ch.fire(1, 3, -1)
        for t in range(1, 30):
            ch.settle(t)
            d.update(tick=t)
        assert d.value < start, "the event must push down from either side"


def test_the_spring_can_fight_a_level_perturbation():
    """Why the envelope lives in the level channel and not in `u`.

    A displacement is bounded and the magnet pulls it back; a sustained term in
    the acceleration channel is integrated twice and runs away.
    """
    c = _cal(9)
    def run(level: bool) -> float:
        d = Drive(name="x", set_point=SP, value=SP, kappa=c.kappa,
                  lambda_rate=abs(c.lambda0), basal_direction="recover",
                  spring="magnetic-2nd", spring_reach=c.w, damping=c.damping,
                  spring_fatigue=c.fatigue, allostatic_recovery=c.allostatic_recovery,
                  dt=1.0, viability=(SP - MARGIN, SP + MARGIN))
        ch = PerturbationChannel(d, PerturbationSpec(attack=0.10, sustain=0.03), MARGIN)
        r = random.Random(7)
        for t in range(1, int(WINDOW) + 1):
            if r.random() < 1.5 / 60:
                if level:
                    ch.fire(t, 3, +1)
                else:                      # the same load through `u`
                    d.sustain(f"e{t}", 0.10 * abs(c.lambda0))
            ch.settle(t)
            d.update(tick=t)
            if not (SP - MARGIN < d.value < SP + MARGIN):
                return t
        return WINDOW
    on_level, on_acceleration = run(level=True), run(level=False)
    # measured 435 vs 273 ticks at this calibration: the level channel buys ~1.6x.
    assert on_level > 1.4 * on_acceleration


def test_three_scenarios_under_one_calibration():
    """E1 survives, E2 kills at the calibrated date, E3 kills sooner but leaves room."""
    c = _cal(9)
    # phase 3 sizes the envelope from the exploratory budget — do not hand-pick it.
    spec = calibrate_perturbation(c, window=WINDOW, target_ttd=150, arrivals_per_unit=1.5)
    def night(perturb: bool, act: bool, seed: int = 11) -> tuple[float, int, int]:
        r = random.Random(seed)
        d = Drive(name="x", set_point=SP, value=SP, kappa=c.kappa,
                  lambda_rate=abs(c.lambda0), basal_direction="recover",
                  spring="magnetic-2nd", spring_reach=c.w, damping=c.damping,
                  spring_fatigue=c.fatigue, allostatic_recovery=c.allostatic_recovery,
                  dt=1.0, viability=(SP - MARGIN, SP + MARGIN))
        ch = PerturbationChannel(d, spec, MARGIN)
        acts = refr = 0
        for t in range(1, int(WINDOW) + 1):
            if perturb and r.random() < 1.5 / 60:
                ch.fire(t, r.choice((1, 2, 3)), +1)
            if act and t > refr and ch.load:
                p = min(1.0, abs(d.value - SP) / MARGIN)
                if r.random() < 1 - math.exp(-min(40, 0.9 * math.exp(5 * p)) / 60):
                    refr, acts = t + 3, acts + 1
                    ch.correct(t, g=0.85 if r.random() > 0.25 else 0.0)
                    d.sustain("trabajo", -1.4 * abs(c.lambda0))
            ch.settle(t)
            d.update(tick=t)
            if not (SP - MARGIN < d.value < SP + MARGIN):
                return t, acts, ch.load
        return WINDOW, acts, ch.load
    e1, acts, _ = night(True, True)
    e2, _, _ = night(False, False)
    e3, _, _ = night(True, False)
    assert e1 >= WINDOW, "a working agent must reach the end of the window"
    assert e2 == pytest.approx(c.ttd_basal, rel=0.05)
    assert e3 < 0.6 * e2, "unclosed events must shorten the night"
    assert e3 > 60, "and still leave the agent room for failed attempts"
    assert acts > 15
