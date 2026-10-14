"""EPA v2.1 (docs/paov2.1.md) — acceptance tests, one per §12 item.

Each test is anchored to the spec section it accepts. §12.1 ("v2 carga")
targets the TS harness signature (updatePersistentDrives/integrateProaction)
and lives in multiply-overnight; the rest are here. The 2026-10-09 night:
first-order Hooke's law with a ±1 wall (EPA v2 never ran), rate null
166/166, sources computed for the report but not read by the wake
aggregator, an activation log whose "probability" field stored a pacing
delta, a guard that parked a diagnosed fix on a REAL disagreement, and a
causal chain of seven steps with zero first-class events.
"""
import math

import pytest

from binsai import (
    BinsaiAgent, Drive, Drives, ExpectedEffect, Guard, ObservedVariable,
    ViabilityContract, G_MEASURED, ACTIVATION_FAILED, EXPECTED_EFFECT,
    PERTURBED, DRIVE_SATURATED, GUARD_SIGNAL_UNCAL, CONTRACT_REINJECTED,
    CONTRACT_VERIFIED,
)


def make_drive(name="svc", value=None, **kw):
    base = dict(name=name, set_point=0.50, viability=(0.0, 1.0),
                lambda_rate=-0.005, basal_direction="decay",
                spring="magnetic-2nd", kappa=0.6,
                spring_reach=Drive.design_spring_reach(0.6, 0.005, 0.25),
                spring_fatigue=0.0, allostatic_recovery=0.0,
                damping=0.1, dt=1.0, velocity=0.0)
    base.update(kw)
    if value is not None:
        base["value"] = value
    return Drive(**base)


class TestPerturbationIsAnImpulse:
    """§12.1 — the perturbation is visible: a zone crossing hits the
    acceleration channel and v keeps moving away after the impulse decayed."""

    def test_zone_crossing_opens_an_event_on_the_level_channel(self):
        """v2.1 §1 — a crossing opens an ADSR event, it does not poke `u`.

        A sustained term in the acceleration channel is integrated twice and
        accumulates without bound, so an unattended run collapses in a
        fraction of its horizon however the drive is tuned. The envelope
        presses on the level, where the magnetic spring can fight it.
        """
        var = ObservedVariable(
            name="ram_free_gb", kind="floor", limit=(0.0, 10.0),
            set_point=10.0, pressure_fn="linear", window=None,
        )
        drive = make_drive(value=0.50)
        drive.observed = [var]
        var.observe(0.0, 10.0)          # green anchor
        drive.update(tick=0)
        assert drive.open_perturbations == 0

        var.observe(1.0, 1.0)           # green -> red: the world hits
        drive.update(tick=1)
        assert drive.open_perturbations == 1
        assert not drive.impulses, "the envelope must not enter the acceleration channel"
        assert drive.perturbation_load == 0.0, "the attack starts at zero and climbs"

        # A: it ramps to the peak over `rise` and then HOLDS there. A sustain
        # below the peak would be the world handing back part of the event
        # without any corrective action, which A3 forbids.
        loads = []
        for t in range(2, 40):
            drive.update(tick=t)
            loads.append(abs(drive.perturbation_load))
        assert loads[0] < loads[4], "the attack must climb"
        assert loads[-1] == pytest.approx(max(loads), rel=1e-6), "y después sostiene"

        # S: it keeps pressing — the world never closes an event
        for t in range(40, 300):
            drive.update(tick=t)
        assert drive.open_perturbations == 1
        assert abs(drive.perturbation_load) > 0.0

    def test_only_a_measured_correction_closes_an_event(self):
        """ADS is the world's, R is the agent's, and the grade is measured g."""
        var = ObservedVariable(
            name="ram_free_gb", kind="floor", limit=(0.0, 10.0),
            set_point=10.0, pressure_fn="linear", window=None,
        )
        drive = make_drive(value=0.50)
        drive.observed = [var]
        var.observe(0.0, 10.0)
        drive.update(tick=0)
        var.observe(1.0, 1.0)
        drive.update(tick=1)

        assert drive.correct(tick=2, g=0.0) == 0, "an action that satiates nothing closes nothing"
        assert drive.open_perturbations == 1

        assert drive.correct(tick=3, g=1.0) == 1
        assert drive.open_perturbations == 0

    def test_the_world_easing_off_neither_opens_nor_releases(self):
        """A3 — el release es lo que aporta una acción de calidad, y nada más.

        Un cruce hacia la zona estable no abre un evento espejado ni apaga el
        que está abierto. Si lo apagara, el agente se llevaría crédito por la
        suerte del mundo y el axioma 3 no existiría. Lo que sí hace es bajar la
        condición: la próxima salida de verde abre un evento nuevo, porque es
        otra perturbación.
        """
        var = ObservedVariable(
            name="ram_free_gb", kind="floor", limit=(0.0, 10.0),
            set_point=10.0, pressure_fn="linear", window=None,
        )
        drive = make_drive(value=0.50)
        drive.observed = [var]
        var.observe(0.0, 10.0)
        drive.update(tick=0)
        var.observe(1.0, 1.0)           # verde -> rojo: abre
        drive.update(tick=1)
        assert drive.open_perturbations == 1
        abierto = drive._open[-1]

        var.observe(2.0, 10.0)          # el mundo aflojó: no abre ni libera
        drive.update(tick=2)
        assert drive.open_perturbations == 1
        assert drive._open[-1] is abierto
        assert abierto.g == 0.0, "nadie actuó: la saciedad es cero"
        assert abierto.closed_at is None

        var.observe(3.0, 1.0)           # vuelve a salir: ES otra perturbación
        drive.update(tick=3)
        assert drive.open_perturbations == 2

    def test_a_worse_band_escalates_instead_of_opening_another(self):
        """La condición es una; el evento también, mientras siga fuera."""
        var = ObservedVariable(
            name="ram_free_gb", kind="floor", limit=(0.0, 10.0),
            set_point=10.0, pressure_fn="linear", window=None,
        )
        drive = make_drive(value=0.50)
        drive.observed = [var]
        var.observe(0.0, 10.0)
        drive.update(tick=0)
        var.observe(1.0, 6.0)           # verde -> amarillo
        drive.update(tick=1)
        assert drive.open_perturbations == 1
        sev1 = drive._open[-1].severity
        var.observe(2.0, 1.0)           # empeora sin volver: escala
        drive.update(tick=2)
        assert drive.open_perturbations == 1, "la misma condición no abre otro evento"
        assert drive._open[-1].severity > sev1


class TestPressureNormalizationAndAggregation:
    """§12.3, §12.4, §12.5."""

    def test_uncalibrated_source_excluded_and_registered(self):
        drive = make_drive(value=0.40, lambda_rate=0.0, basal_direction=None,
                           kappa=0.0)   # frozen dynamics: value stays put
        drive.update(tick=0)
        pc = drive.pressure_components()
        assert pc["pace"] is None
        assert "pace" in pc["uncalibrated"]
        # level alone carries the pressure — never averaged down by a
        # missing source counting as zero
        assert pc["pressure"] == pytest.approx(pc["level"], rel=1e-9)
        assert pc["pressure"] == pytest.approx(0.10 / 0.50, rel=1e-9)

    def test_sources_enter_pressure_not_distance_alone(self):
        """§12.3 — the drive's pressure is the max over its calibrated
        sources. With the drive AT the set-point (distance pressure 0) and
        a wired sensor whose pace is in the red, the pressure is the pace
        source, not the distance."""
        var = ObservedVariable(
            name="spend_usd", kind="budget", limit=10.0, set_point=0.0,
            unit="USD", window=10.0, window_start=0.0,
            pressure_fn="linear", pacing_mode="ratio",
        )
        drive = make_drive(value=0.50, lambda_rate=0.0, basal_direction=None,
                           kappa=0.0)   # at set-point, frozen
        drive.observed = [var]
        var.observe(0.0, 0.0)           # spend 0 at window open
        # burst: spent 9 of 10 with the window barely open → r_obs ≫ r_sust
        var.observe(0.5, 9.0)
        # aggregate WITHOUT a drive update: the crossing's perturbation
        # impulse is a different channel (§1) and must not muddy §2.
        pc = drive.pressure_components()
        assert pc["level"] == 0.0               # distance alone says calm
        assert pc["pace"] is not None
        assert pc["pressure"] == pytest.approx(min(1.0, pc["pace"]), rel=1e-9)
        assert pc["pressure"] > 0.0             # the source entered the max

    def test_conjunctive_aggregation(self):
        """A dead drive + a healthy one → system pressure 1, not 0.5."""
        dead = make_drive(name="metabolic", value=1.0, lambda_rate=0.0,
                          basal_direction=None, kappa=0.0)  # pinned at hi
        ok = make_drive(name="social", value=0.50, lambda_rate=0.0,
                        basal_direction=None, kappa=0.0)     # at set-point
        dead.update(tick=0)
        ok.update(tick=0)
        assert dead.pressure == 1.0      # saturated: |d| = margin
        drives = Drives([dead, ok])
        assert drives.pressure == 1.0

    def test_every_source_in_01(self):
        for value, velocity in [(0.0, -0.5), (0.5, 0.0), (1.0, 0.5)]:
            d = make_drive(value=value, velocity=velocity)
            d.update(tick=0)
            pc = d.pressure_components()
            for k in ("level", "autonomous", "pressure"):
                assert 0.0 <= pc[k] <= 1.0, (value, velocity, k, pc[k])


class TestQualitySignalG:
    """§12.5 — null g: no satiation, activation not consumed, ι₂ impulse,
    and the pressure rises."""

    def _agent(self):
        d = make_drive(name="metabolic", value=0.30, lambda_rate=0.0,
                       basal_direction=None, kappa=0.0)   # frozen: only
        agent = BinsaiAgent(name="A", drives=Drives([d]), dry_run_llm=True)  # impulses/actions move it
        agent.activate()
        return agent, d

    def test_null_g_no_satiation_no_consumption(self):
        agent, d = self._agent()
        events = {"activation_failed": [], "g_measured": [], "perturbed": []}
        agent.on("ActivationFailed", lambda p: events["activation_failed"].append(p))
        agent.on("GMeasured", lambda p: events["g_measured"].append(p))
        agent.on("Perturbed", lambda p: events["perturbed"].append(p))

        ee = agent.declare_expected_effect(
            drive_id="metabolic", delta_expected=0.10, by_when=1.0,
            action="respond_fast", fault="topic_x")
        assert ee.baseline == d.value
        # nothing moves the drive → Δ_obs = 0 → g = 0 → null
        d.update(tick=1)
        agent.tick(t=1)
        assert events["g_measured"], "g must be measured at byWhen"
        gm = events["g_measured"][-1]
        assert gm["result"] == "null"
        # the ι₂ perturbation impulse went away from the set-point
        assert events["perturbed"], "a null g must perturb with ι₂"
        away = [p for p in events["perturbed"]
                if p.get("direction") == "away"]
        assert away and abs(away[-1]["impulse"]) == pytest.approx(0.06)
        # activation NOT consumed: no refractory was applied
        assert agent._refractory_until == 0.0
        assert events["activation_failed"][-1]["reason"] == "null_effect"

    def test_ok_g_satiates_on_measured_effect(self):
        agent, d = self._agent()
        agent.on("Perturbed", lambda p: agent._seen.append(p))
        agent._seen = []
        agent.declare_expected_effect("metabolic", 0.10, by_when=1.0,
                                      action="respond_fast")
        d.impulse(0.08, expected=0.08)          # the fix actually worked
        d.update(tick=1)
        agent.tick(t=1)
        toward = [p for p in agent._seen if p.get("direction") == "toward"]
        assert toward, "a working action satiates (toward impulse)"
        assert agent._refractory_until > 0      # activation consumed

    def test_harmful_g_disables_action_in_window(self):
        agent, d = self._agent()
        agent.declare_expected_effect("metabolic", 0.10, by_when=1.0,
                                      action="respond_fast", fault="f1")
        d.deplete(0.15)                         # it got worse: Δ_obs = −0.15
        d.update(tick=1)
        agent.tick(t=1)
        assert ("f1", "respond_fast") in agent._disabled_attempts
        assert agent.attempts[-1]["result"] == "harmful"
        assert agent._refractory_until == 0.0   # not consumed


def mk(**kw):
    """Basal TTD test drive: magnetic-2nd, λ=0, κ=0.6, w=1.0, f=0.01."""
    base = dict(name="d", set_point=0.5, viability=(0.0, 1.0),
                lambda_rate=0.0, spring="magnetic-2nd", kappa=0.6,
                spring_reach=1.0, spring_fatigue=0.01,
                allostatic_recovery=0.0, damping=0.1, dt=1.0)
    base.update(kw)
    return Drive(**base)


class TestTTDProjection:
    """§12.7 — TTD is a counterfactual forward integration with u = 0:
    well-defined at the wall, tells a dying drive from one the spring
    recovers, and integrates the allostatic load forward."""

    def test_basal_ttd_at_the_wall_dying(self):
        """At the wall with the drift still pushing outward: TTD ~ 0."""
        d = mk(value=0.15, set_point=0.15, lambda_rate=0.35)
        for t in range(1, 121):
            d.update(tick=t)
        assert d.saturated
        ttd = Drives([d]).time_to_death(horizon_ticks=600)
        assert ttd is not None and ttd <= 2 * d.dt

    def test_basal_ttd_at_the_wall_recovering(self):
        """At the wall but the spring recovers it: TTD ∞. A saturation-flag
        patch would return 0 and lie."""
        d = mk(value=0.0, set_point=0.5, lambda_rate=0.0,
               spring_reach=1.0, damping=0.3)
        d._history = [(i, 0.0) for i in range(40)]
        assert Drives([d]).time_to_death(horizon_ticks=600) is None

    def test_basal_ttd_names_the_wall(self):
        d = mk(value=0.15, set_point=0.15, lambda_rate=0.35)
        for t in range(1, 21):
            d.update(tick=t)
        assert Drives([d]).project_basal(600)[d.name][1] == "upper"

    def test_fatigue_brings_projected_death_closer(self):
        """The projection integrates Λ forward: two drives identical except
        for the accumulated allostatic load cannot give the same TTD."""
        rested = mk(value=0.5, set_point=0.15, lambda_rate=0.05)
        tired = mk(value=0.5, set_point=0.15, lambda_rate=0.05)
        tired._allostatic = 5.0
        for d in (rested, tired):
            d._history = [(0, 0.5)]
        t_rested = Drives([rested]).time_to_death(horizon_ticks=5000)
        t_tired = Drives([tired]).time_to_death(horizon_ticks=5000)
        assert t_tired is not None and (t_rested is None or t_tired < t_rested)

    def test_rate_respects_the_horizon(self):
        """TTD ≈ 12 min, θ = 0.2 → E[wait] = 1/h ≤ θ·TTD at the gate."""
        d = make_drive(name="metabolic", value=0.50, dt=1 / 60,
                       lambda_rate=0.0, basal_direction=None, kappa=0.0,
                       damping=0.0, velocity=2.5)   # coast to the wall in 12 min
        d._history = [(0, 0.50)]
        assert Drives([d]).time_to_death(horizon_ticks=600) == pytest.approx(12 / 60, rel=1e-9)

        agent = BinsaiAgent(name="A", drives=Drives([d]), dry_run_llm=True,
                            activation_theta=0.2)
        agent.activate()
        draws = []
        agent.on("ActivationDraw", lambda p: draws.append(p))
        agent.tick(t=1)
        h = draws[-1]["h"]
        assert draws[-1]["ttd"] is not None
        # event fields are rounded for the log: compare within its precision
        assert 1.0 / h <= 0.2 * draws[-1]["ttd"] + 1e-4


class TestGuards:
    """§12.8 — (a) the guard does not block with an absent signal;
    (b) a real disagreement between live signals keeps the incident but a
    corrective action justified by root cause still executes."""

    def test_uncalibrated_signal_skips_not_blocks(self):
        # service red (calibrated), pace absent (no observed vars)
        red = make_drive(name="service", value=0.02)
        red.update(tick=0)
        agent = BinsaiAgent(name="A", drives=Drives([red]), dry_run_llm=True,
                            guards=[Guard(
                                "contradiction_guard",
                                lambda s: ("signals_contradict"
                                           if s["service.level"] > 0.5
                                           and (s["service.pace"] or 0) < 0.5
                                           else None),
                                risk="corrective")])
        agent.activate()
        skipped = []
        agent.on("GuardSignalUncalibrated", lambda p: skipped.append(p))
        verdict = agent.guard_check("corrective", t=1)
        assert verdict is None, "absent signal must not block"
        assert skipped and "service.pace" in skipped[-1]["uncalibrated"]

    def test_real_disagreement_blocks_and_is_traced(self):
        """§12.8b — both signals calibrated and alive: the guard blocks and
        the rejection is first-class (the prompt side of the acceptance is
        the harness's, paov2.1 §7.2)."""
        # pace source calibrated: wire a sensor with a pace signal
        var = ObservedVariable(
            name="spend_usd", kind="budget", limit=10.0, set_point=0.0,
            window=10.0, window_start=0.0, pressure_fn="linear",
            pacing_mode="ratio")
        red = make_drive(name="service", value=0.02)
        red.observed = [var]
        var.observe(0.0, 0.0)
        var.observe(0.5, 9.0)          # pacing through the roof (red)
        assert red.pressure_components()["pace"] is not None

        agent = BinsaiAgent(name="A", drives=Drives([red]), dry_run_llm=True,
                            guards=[Guard(
                                "contradiction_guard",
                                lambda s: ("signals_contradict"
                                           if s["service.level"] > 0.5
                                           and s["service.pace"] > 0.5
                                           else None),
                                risk="corrective")])
        agent.activate()
        rejected = []
        agent.on("ActionRejected", lambda p: rejected.append(p))
        verdict = agent.guard_check("corrective", t=1)
        assert verdict is not None and verdict.reason == "signals_contradict"
        assert rejected


class TestContractSurvives:
    """§12.9 — the contract block is verbatim after a lossy compaction."""

    def test_verify_reinject_roundtrip(self):
        contract = ViabilityContract({
            "drives": {"service": {"limit": 1.0, "set_point": 0.15}},
            "zones": [0.33, 0.55, 0.80],
        })
        agent = BinsaiAgent(name="A", drives=Drives(
            [make_drive(name="metabolic", value=0.5)]),
            dry_run_llm=True, contract=contract)
        events = []
        agent.on("ContractReinjected", lambda p: events.append(("reinjected", p)))
        agent.on("ContractVerified", lambda p: events.append(("verified", p)))

        compacted = "task plan... context anxiety... (lossy summary)"
        assert agent.verify_contract_block(compacted) is False
        reinjected = compacted + "\n" + contract.block()
        assert agent.verify_contract_block(reinjected) is True
        assert [k for k, _ in events] == ["reinjected", "verified"]


class TestPersistenceDeclared:
    """§12.11 — persistence is declared per drive; nothing is inherited or
    reset implicitly."""

    def test_reset_is_the_declared_default(self):
        d = make_drive()                    # value=None, persist_state=None
        assert d.persist_state is not True
        assert d.value == d.set_point       # reset: x(t₀) = x*

    def test_persisted_state_must_be_declared(self):
        # persisted drive without inherited state → the contract is invalid
        with pytest.raises(ValueError, match="persist_state"):
            make_drive(persist_state=True)

    def test_persisted_state_carries_value_and_velocity(self):
        d = make_drive(value=0.462, velocity=-0.229, persist_state=True,
                       state_origin="persisted from 2026-10-09 21:30")
        assert d.value == 0.462
        assert d.velocity == -0.229
        assert "2026-10-09" in d.state_origin

    def test_explicit_value_without_persistence_is_a_declared_initial_state(self):
        d = make_drive(value=0.462)         # declared, hence justified
        assert d.value == 0.462


class TestCircuitBreakerIsNotABrake:
    """§12.13 (11b) — exhausting the attempts without the deviation dropping
    leaves the activation failed, the pressure up, and the refractory off."""

    def test_null_g_failed_activation_raises_pressure(self):
        d = make_drive(name="metabolic", value=0.30, lambda_rate=0.0,
                       basal_direction=None, kappa=0.0, damping=0.0)
        agent = BinsaiAgent(name="A", drives=Drives([d]), dry_run_llm=True)
        agent.activate()
        d.update(tick=0)
        p_before = d.pressure
        agent.declare_expected_effect("metabolic", 0.10, by_when=1.0,
                                      action="respond_fast", fault="f1")
        d.update(tick=1)
        agent.tick(t=1)                     # verify → null → ι₂ away impulse
        assert agent.attempts[-1]["result"] == "null"
        assert agent._refractory_until == 0.0   # activation NOT consumed
        # the ι₂ impulse keeps pushing the drive away: pressure rises
        for t in range(2, 8):
            d.update(tick=t)
        assert d.pressure > p_before


class TestLogDoesNotLie:
    """§12.9 (8b) — the draw event's fields recompute exactly from the
    contract: pressure, h, p_tick and the drawn number each mean what they
    name."""

    def test_draw_fields_recompute_from_contract(self):
        import random as _random
        from binsai.fuzzy import activation_hazard, activation_probability

        d = make_drive(name="metabolic", value=0.30, lambda_rate=0.0,
                       basal_direction=None, kappa=0.0)
        d.update(tick=0)
        agent = BinsaiAgent(name="A", drives=Drives([d]), dry_run_llm=True,
                            rng=_random.Random(7))
        agent.activate()
        draws = []
        agent.on("ActivationDraw", lambda p: draws.append(p))
        agent.tick(t=1)

        ev = draws[-1]
        # recompute by hand from the contract
        comps = d.pressure_components()
        p_expected = comps["pressure"]
        h_expected = activation_hazard(p_expected, has_demand=False,
                                       pending_labels=0)
        ttd = Drives([d]).time_to_death(horizon_ticks=600)   # frozen → None
        dt = d.dt
        assert ev["dt"] == dt
        assert ev["pressure"] == pytest.approx(p_expected, rel=1e-6)
        assert ev["ttd"] is None if ttd is None else True
        assert ev["h"] == pytest.approx(h_expected, rel=1e-6)
        p_tick_expected = activation_probability(h_expected, dt)
        assert ev["p_tick"] == pytest.approx(p_tick_expected, rel=1e-6)
        # the drawn number decides, and the result matches it
        assert ev["acted"] == (ev["draw"] < ev["p_tick"])
        # dominant source recorded
        assert ev["dominant_drive"] == "metabolic"
        assert ev["dominant_source"] == "level"


class TestSaturation:
    """§12.12 — pinned at the wall: DriveSaturated + accumulated duration."""

    def test_saturation_emits_and_accumulates(self):
        d = make_drive(value=0.50, lambda_rate=0.0, basal_direction=None,
                       spring="linear", kappa=0.0)
        saturated = []
        d.on("DriveSaturated", lambda p: saturated.append(p))
        d.update(tick=0)
        d.value = 0.0                      # pinned at lo
        d.update(tick=1)
        assert saturated and saturated[-1]["drive"] == "svc"
        d.update(tick=2)
        d.update(tick=3)
        d.value = 0.4
        d.update(tick=4)                   # released
        assert d.saturation_time == pytest.approx(3.0)   # ticks 1..3 pinned


class TestTraces:
    """§12.12 — the causal chain is reconstructible from first-class events
    alone, without reading any free-text field."""

    def test_failure_chain_is_all_events(self):
        d = make_drive(name="metabolic", value=0.30, lambda_rate=0.0,
                       basal_direction=None, kappa=0.0)
        agent = BinsaiAgent(name="A", drives=Drives([d]), dry_run_llm=True)
        agent.activate()
        log = []
        agent.on_any(lambda env: log.append(env))

        agent.declare_expected_effect("metabolic", 0.10, by_when=1.0,
                                      action="respond_fast", fault="f1")
        d.update(tick=1)
        agent.tick(t=1)

        types = [e["type"] for e in log]
        # causal chain, first-class events only:
        assert "ExpectedEffect" in types
        assert "GMeasured" in types
        assert "ActivationFailed" in types
        assert "Perturbed" in types      # the ι₂ consequence
        # and no link of the chain lives only in prose:
        gm = next(e for e in log if e["type"] == "GMeasured")["payload"]
        af = next(e for e in log if e["type"] == "ActivationFailed")["payload"]
        assert gm["delta_expected"] == 0.10
        assert gm["delta_observed"] == 0.0
        assert af["reason"] == "null_effect"