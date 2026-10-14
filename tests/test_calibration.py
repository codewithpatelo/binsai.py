"""EPA v2.1 — calibrating drives that exist.

Every test here starts from a Drive, a Drives collection or an agent, and the
calibrator reads what it needs off them. Nothing builds a world of its own: the
counterfactual is a copy of the drive under test, released from its set-point
with u = 0, which is what v2.1 §4 says a TTD is.
"""

import math
import random

import pytest

from binsai import BinsaiAgent
from binsai.calibration import (
    Calibration, ShapeRatios, basal_time_to_death, grip, resting_point,
)
from binsai.drives import Drive, Drives, Perturbation, PerturbationEnvelope

HORIZON = 690.0         # ticks; the unit is whatever the caller's clock is
MARGIN = 0.45
SP = 0.5


def make(direction: float = 1.0, **kw) -> Drive:
    """A bare drive with room between its set-point and its walls."""
    kw.setdefault("lambda_rate", math.copysign(0.001, direction))
    kw.setdefault("basal_direction", "recover" if direction > 0 else "decay")
    return Drive(name=kw.pop("name", "d"), set_point=SP, value=SP,
                 spring="magnetic-2nd", viability=(SP - MARGIN, SP + MARGIN),
                 dt=1.0, horizon=HORIZON, **kw)


def flat() -> Drive:
    """No drift, no spring: only the envelope shows."""
    return make(name="plano", kappa=0.0, lambda_rate=0.0, basal_direction=None,
                damping=0.0, spring_fatigue=0.0)


# ── the entry points operate on what exists ──────────────────────────────────

def test_drive_calibrates_itself_and_keeps_the_result():
    d = make()
    cal = d.calibrate(mortality=0.8)
    assert cal.ttd_basal == pytest.approx(0.8 * HORIZON, rel=0.03)
    assert d.kappa == cal.kappa and d.spring_fatigue == cal.fatigue
    assert d.spring_reach == cal.w and d.lambda_rate == cal.lambda0
    assert basal_time_to_death(d) == pytest.approx(cal.ttd_basal, rel=0.02)


def test_calibration_reads_the_drive_not_arguments():
    """Margin, set-point and drift sign come off the drive as it stands."""
    narrow = Drive(name="narrow", set_point=0.5, value=0.5, lambda_rate=-0.001,
                   basal_direction="decay", spring="magnetic-2nd",
                   viability=(0.3, 0.7), dt=1.0, horizon=HORIZON)
    cal = narrow.calibrate(mortality=0.8)
    assert cal.margin == pytest.approx(0.2)
    assert cal.set_point == 0.5
    assert cal.lambda0 < 0, "a decaying drive must keep decaying"


def test_drives_collection_calibrates_each_on_its_own_date():
    push, pull = make(-1.0, name="service"), make(+1.0, name="metabolic")
    drives = Drives([push, pull])
    report = drives.calibrate(mortality={"service": 0.67, "metabolic": 0.8})
    assert report["service"].ttd_basal < report["metabolic"].ttd_basal
    assert all(c.sound for c in report.values())


def test_agent_calibrates_all_of_its_drives():
    """The one call an operator needs."""
    agent = BinsaiAgent(name="probe")
    report = agent.calibrate(mortality=0.8)
    assert len(report) == len(agent.drives._drives)
    assert all(c.sound for c in report.values())
    for name, cal in report.items():
        assert agent.drives._drives[name].spring_fatigue == cal.fatigue


def test_apply_false_leaves_the_drive_alone():
    d = make()
    before = (d.kappa, d.spring_fatigue, d.lambda_rate)
    d.calibrate(mortality=0.8, apply=False)
    assert (d.kappa, d.spring_fatigue, d.lambda_rate) == before


# ── phase 1 and phase 2 are orthogonal ───────────────────────────────────────

def test_fatigue_alone_moves_the_death_date():
    shapes, fatigues = set(), []
    for mortality in (0.35, 0.5, 0.7, 0.9):
        c = make().calibrate(mortality=mortality)
        shapes.add((round(c.kappa, 8), round(c.w, 6),
                    round(abs(c.lambda0), 9), round(c.damping, 6)))
        fatigues.append(c.fatigue)
        assert c.ttd_basal == pytest.approx(mortality * HORIZON, rel=0.03)
    assert len(shapes) == 1, "geometry moved with the death target"
    assert fatigues == sorted(fatigues, reverse=True), "more fatigue must die sooner"


def test_both_inequalities_hold():
    c = make().calibrate(mortality=0.8)
    assert c.grip_ratio > 1.0            # the spring holds
    assert c.ttd_basal < HORIZON         # fatigue eats it
    assert c.overshoot_over_reach < 1.0  # it does not escape by inertia first
    assert c.sound


def test_without_fatigue_negligence_never_kills():
    """binsai's own `equilibrium` says it: with f = 0 the rest point is permanent."""
    d = make()
    d.calibrate(mortality=0.8)
    assert basal_time_to_death(d, fatigue=0.0) is None


def test_the_spring_postpones_it_does_not_save():
    d = make()
    d.calibrate(mortality=0.8)
    with_spring = basal_time_to_death(d)
    d.kappa = 0.0
    without = basal_time_to_death(d)
    assert without is not None and with_spring is not None
    assert with_spring > 3 * without


def test_mortality_is_a_fraction_of_the_horizon():
    with pytest.raises(ValueError, match="fraction of the horizon"):
        make().calibrate(mortality=1.4)


def test_a_drive_with_no_margin_cannot_be_calibrated():
    flat = Drive(name="flat", set_point=0.5, value=0.5, lambda_rate=0.001,
                 spring="magnetic-2nd", viability=(0.5, 0.5), dt=1.0)
    with pytest.raises(ValueError, match="no room"):
        flat.calibrate(mortality=0.8)


def test_derived_quantities_agree_with_the_formulas():
    c = make().calibrate(mortality=0.8)
    assert c.grip == pytest.approx(grip(c.kappa, c.w))
    assert c.grip_ratio == pytest.approx(c.grip / abs(c.lambda0))
    assert resting_point(c.kappa, c.w, c.lambda0) == pytest.approx(c.rest_point, rel=0.02)


def test_calibration_is_scale_free():
    """Nothing in the calibrator knows what an hour is.

    The same ratios and the same mortality, read against another clock and
    another ruler, give the same dimensionless groups — so one calibration
    describes an overnight window, a trading session and a servo loop.
    """
    base = make().calibrate(mortality=0.8)
    ref = base.dimensionless(HORIZON)
    for margin, horizon in ((0.45, 69.0), (0.20, 6900.0), (0.40, 240.0)):
        d = Drive(name="other", set_point=SP, value=SP, lambda_rate=0.001,
                  basal_direction="recover", spring="magnetic-2nd",
                  viability=(SP - margin, SP + margin), dt=1.0, horizon=horizon)
        got = d.calibrate(mortality=0.8).dimensionless(horizon)
        for key, value in ref.items():
            # The five analytic groups are exact. f*M*T is bisected against a
            # discrete integration, so it inherits the tick resolution.
            tol = 0.05 if key == "f*M*T" else 1e-9
            assert got[key] == pytest.approx(value, rel=tol), f"{key} moved with the scale"


# ── phase 3 measures, or refuses ─────────────────────────────────────────────

def test_phase_three_refuses_to_guess_the_arrival_rate():
    """Only the product of arrivals and magnitude sets the budget."""
    d = make()
    d.calibrate(mortality=0.8)
    with pytest.raises(ValueError, match="cannot be measured"):
        d.calibrate_perturbation(exploratory_budget=0.35)


def test_sparse_arrivals_make_phase_three_ill_posed():
    """Below ~10 arrivals per oscillation period the spring absorbs everything."""
    d = make()
    d.calibrate(mortality=0.8)
    with pytest.raises(ValueError, match="per oscillation period"):
        d.calibrate_perturbation(exploratory_budget=0.35, arrivals_per_horizon=17.0)


def test_phase_three_sizes_the_impulses_and_applies_them():
    d = make()
    d.calibrate(mortality=0.8)
    iotas = d.calibrate_perturbation(exploratory_budget=0.35, arrivals_per_horizon=400.0)
    assert d.impulse_iota == iotas
    assert 0.0 < iotas[2] < 1.0, "a severe hit must be a sensible slice of the margin"
    assert iotas[0] < iotas[1] < iotas[2]


def test_a_tighter_budget_needs_a_bigger_hit():
    d = make()
    d.calibrate(mortality=0.8)
    loose = d.calibrate_perturbation(exploratory_budget=0.6, arrivals_per_horizon=400.0,
                                     apply=False)
    tight = d.calibrate_perturbation(exploratory_budget=0.25, arrivals_per_horizon=400.0,
                                     apply=False)
    assert tight[2] > loose[2]


def test_the_rate_can_be_measured_from_what_the_drive_received():
    """An arrival rate is an observation, and the drive keeps the observation."""
    d = make()
    d.calibrate(mortality=0.8)
    assert d.measured_arrival_rate() is None
    r = random.Random(3)
    for t in range(1, 301):
        if r.random() < 0.5:
            d.open_perturbation(t, 2, +1.0)
        d.update(tick=t)
    measured = d.measured_arrival_rate()
    assert measured is not None
    # ~0.5 per tick over a 690-tick horizon
    assert measured == pytest.approx(0.5 * HORIZON, rel=0.25)


# ── the envelope, through the drive's own channel ────────────────────────────

def test_an_event_climbs_and_then_holds_until_an_action_closes_it():
    """A3: el mundo no devuelve nada por su cuenta.

    El evento sube durante el ataque y después SOSTIENE. Un sustain por debajo
    del pico sería el mundo regalando parte de la perturbación sin que ninguna
    acción la haya corregido, que es un release sin calidad medida.
    """
    d = flat()
    d.open_perturbation(1, 3, +1.0)
    trace = []
    for t in range(1, 400):
        d.update(tick=t)
        trace.append(d.perturbation_load)
    peak = max(trace)
    assert trace[2] < trace[8] <= peak                        # A
    assert trace[60] == pytest.approx(peak, rel=1e-6)         # S = pico
    assert trace[-1] == pytest.approx(trace[-60], rel=0.02)   # y sostiene
    assert d.open_perturbations == 1


def test_only_a_measured_correction_closes_an_event():
    d = flat()
    d.open_perturbation(1, 3, +1.0)
    for t in range(1, 60):
        d.update(tick=t)
    assert d.correct(60, g=0.0) == 0, "an action that satiates nothing closes nothing"
    assert d.open_perturbations == 1
    assert d.correct(61, g=1.0) == 1
    assert d.open_perturbations == 0


def test_direction_is_the_world_not_the_drive_side():
    for start in (SP - 0.2, SP + 0.2):
        d = flat()
        d.value = start
        d.open_perturbation(1, 3, -1.0)
        for t in range(1, 40):
            d.update(tick=t)
        assert d.value < start, "the event must push down from either side"


def test_the_envelope_is_scale_free_too():
    def shape(horizon: float) -> list[float]:
        d = flat()
        d.horizon = horizon
        d.open_perturbation(1, 3, +1.0)
        trace = []
        for t in range(1, int(horizon) + 1):
            d.update(tick=t)
            trace.append(d.perturbation_load)
        return [trace[int(f * (horizon - 1))] for f in (0.02, 0.05, 0.2, 0.6, 0.95)]
    for a, b in zip(shape(690.0), shape(6900.0)):
        assert a == pytest.approx(b, rel=0.01)


# ── los axiomas, como tests ──────────────────────────────────────────────────

def test_a2_the_rate_reads_the_drive_not_its_sensors():
    """A2: una variable saturada no puede fijar la tasa con el drive en equilibrio."""
    from binsai.fuzzy import homeostatic_error
    from binsai.observed import ObservedVariable

    d = make()
    techo = ObservedVariable("gasto", "budget", 50.0, window=11.5,
                             levels={"verde": 5, "amarillo": 10, "ambar": 25, "rojo": 50})
    d.observed = [techo]
    techo.observe(1.0, 104.0)                    # el gasto duplicó su techo y no vuelve
    assert techo.level_zone(104.0) == "rojo"
    assert d.value == d.set_point
    assert homeostatic_error(d) == 0.0, "en el set-point la tasa es cero, mire lo que mire el sensor"


def test_a6_perfect_equilibrium_has_no_impulse():
    from binsai.fuzzy import activation_hazard, homeostatic_error
    d = make()
    assert activation_hazard(homeostatic_error(d)) == 0.0
    d.value = d.set_point + 0.5 * (d.viability[1] - d.set_point)
    assert activation_hazard(homeostatic_error(d)) > 0.0


def test_contract_levels_are_units_not_ratios():
    from binsai.observed import ObservedVariable
    piso = ObservedVariable("ram_libre", "floor", 2.0, window=11.5,
                            levels={"verde": 8, "amarillo": 4, "ambar": 3,
                                    "rojo": 2, "muerte": 1})
    assert [piso.level_severity(x) for x in (9, 5, 3.5, 2.5, 2.0, 0.9)] == [0, 0, 1, 2, 3, 4]
    techo = ObservedVariable("usd", "budget", 50.0, window=11.5,
                             levels={"amarillo": 10, "ambar": 25, "rojo": 50})
    assert [techo.level_severity(x) for x in (0, 20, 49, 50, 104)] == [0, 1, 2, 3, 3]


def test_contract_levels_must_be_monotonic():
    from binsai.observed import ObservedVariable
    with pytest.raises(ValueError, match="monotonic"):
        ObservedVariable("x", "budget", 50.0, window=1.0,
                         levels={"amarillo": 30, "ambar": 10, "rojo": 50})
    with pytest.raises(ValueError, match="at least two"):
        ObservedVariable("x", "budget", 50.0, window=1.0, levels={"rojo": 50})


def test_a2_in_the_agent_gate():
    """El portón de activación del agente lee desvíos, no presiones."""
    from binsai.observed import ObservedVariable
    agent = BinsaiAgent(name="probe")
    for d in agent.drives:
        d.value = d.set_point
        d.observed = [ObservedVariable(f"techo_{d.name}", "budget", 50.0, window=11.5,
                                       levels={"amarillo": 10, "ambar": 25, "rojo": 50})]
        d.observed[0].observe(1.0, 104.0)        # saturada y sin retorno
    from binsai.fuzzy import homeostatic_error
    assert max(homeostatic_error(d) for d in agent.drives) == 0.0


def test_a2_1_aggregation_is_max_not_mean():
    """A2.1: una necesidad muerta y otra en equilibrio no promedian a media presión."""
    from binsai.fuzzy import homeostatic_error
    viva, muerta = make(+1.0, name="viva"), make(-1.0, name="muerta")
    muerta.value = muerta.viability[0]                 # cruzó su límite
    assert homeostatic_error(viva) == 0.0
    assert homeostatic_error(muerta) >= 1.0
    señal = max(homeostatic_error(d) for d in (viva, muerta))
    assert señal >= 1.0, "el máximo no se diluye con la necesidad tranquila"
    assert señal > sum(homeostatic_error(d) for d in (viva, muerta))/2


def test_a2_the_impulse_is_symmetric_in_the_hemispheres():
    """A7 borrador: lo único cerrado es que el superávit activa igual que el déficit."""
    from binsai.fuzzy import homeostatic_error
    d = make()
    margen = d.viability[1] - d.set_point
    d.value = d.set_point + 0.4*margen
    superavit = homeostatic_error(d)
    d.value = d.set_point - 0.4*(d.set_point - d.viability[0])
    deficit = homeostatic_error(d)
    assert superavit == pytest.approx(deficit), "el impulso no puede mirar un solo hemisferio"


def test_a4_1_the_first_crossing_kills_the_agent():
    """A4.1 — viabilidad conjuntiva."""
    viva, cruza = make(+1.0, name="viva"), make(-1.0, name="cruza")
    drives = Drives([viva, cruza])
    assert drives.dead is None
    cruza.value = cruza.viability[0]
    assert drives.dead == "cruza"


def test_a3_an_action_only_closes_what_it_attended():
    d = flat()
    d.open_perturbation(1, 3, -1.0, source="ram")
    d.open_perturbation(2, 3, -1.0, source="gasto")
    assert d.open_perturbations == 2
    assert d.correct(10, g=1.0, source="ram") == 1
    assert d.open_perturbations == 1, "la acción sobre ram no cierra el evento de gasto"


def test_a3_the_release_is_a_phase_not_a_jump():
    d = flat()
    p = d.open_perturbation(1, 3, -1.0, source="v")
    for t in range(1, 60):
        d.update(tick=t)
    antes = abs(p.level(60))
    d.correct(60, g=1.0, source="v")
    fade = p.envelope.release * p.horizon / p.dt
    medio = abs(p.level(60 + int(fade/2)))
    assert 0.0 < medio < antes, "la R baja a lo largo del release, no de un salto"
    assert abs(p.level(60 + int(fade) + 1)) == 0.0
