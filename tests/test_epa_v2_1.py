"""EPA v2.1 (docs/paov2.1.md) — acceptance tests, one per §12 item.

Each test is anchored to the spec section it accepts. The 2026-10-09 night
had: zero discontinuities in 166 samples, rate null 166/166, three
uncalibrated sources, aggregate pressure 0.465 with a drive pinned at the
wall, level 1.934, 28 min of saturation, an inherited initial condition,
a manager whose predicted effect nobody measured, zone crossings computed
for the report but not the dynamics, a guard that read absence as
agreement, and a causal chain of seven steps with zero first-class events.
"""
import math

import pytest

from binsai import (
    BinsaiAgent, Drive, Drives, ExpectedEffect, Guard, ObservedVariable,
    ViabilityContract, G_MEASURED, ACTIVATION_FAILED, EXPECTED_EFFECT,
    PERTURBED, DRIVE_SATURATED, GUARD_SKIPPED_UNCAL, CONTRACT_REINJECTED,
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

    def test_zone_crossing_injects_decaying_impulse(self):
        var = ObservedVariable(
            name="ram_free_gb", kind="floor", limit=(0.0, 10.0),
            set_point=10.0, pressure_fn="linear", window=None,
        )
        # frozen dynamics (κ=0, λ=0): the impulse is the only thing acting
        drive = make_drive(value=0.50, lambda_rate=0.0, basal_direction=None,
                           kappa=0.0, damping=0.0)
        drive.observed = [var]
        var.observe(0.0, 10.0)          # anchor: green, p=0
        drive.update(tick=0)            # drive subscribes to Perturbed
        v_before = drive.velocity       # 0

        # free RAM falls 10→4: p = (sp−x)/(sp−lo) = 0.6 → high. The
        # crossing green→high is ι₂ away from the set-point.
        var.observe(1.0, 4.0)
        drive.update(tick=1)
        assert drive.impulses, "no impulse arrived at the drive"
        tk, a_imp = drive.impulses[-1]
        assert tk == 1
        assert abs(abs(a_imp) - 0.06) < 1e-9
        v_after = drive.velocity
        assert v_after != v_before      # acceleration discontinuity: v charged

        # the impulse decays (τ_u=2) but v persists — the memory of the hit
        # outlives the hit. At tick 4 the residual impulse contributes only
        # 0.06·e^(−1.5) ≈ 0.013, yet v ≈ 0.132 > ι₂ itself: the accumulated
        # velocity exceeds the blow. (Later the drive hits the wall — the
        # inelastic clip then zeroes v, which is the correct death.)
        drive.update(tick=2)
        drive.update(tick=3)
        drive.update(tick=4)
        assert drive.velocity == pytest.approx(0.131853, rel=1e-4)
        assert drive.velocity > 0.06

    def test_toward_crossing_is_weaker(self):
        """ζ asymmetry: improving satiates less than worsening perturbs."""
        var = ObservedVariable(
            name="ram_free_gb", kind="floor", limit=(0.0, 10.0),
            set_point=10.0, pressure_fn="linear", window=None,
        )
        drive = make_drive(value=0.50)
        drive.observed = [var]
        var.observe(0.0, 1.0)           # red anchor
        drive.update(tick=0)
        var.observe(1.0, 10.0)          # back to green: toward
        drive.update(tick=1)
        assert drive.impulses
        _, a_imp = drive.impulses[-1]
        # ι₃·ζ = 0.108 — half the worsening hit of the same severity
        assert abs(abs(a_imp) - 0.18 * 0.6) < 1e-9


class TestPressureNormalizationAndAggregation:
    """§12.2, §12.3, §12.4."""

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


class TestTTDProjection:
    """§12.6, §12.7 — TTD from the history; the rate respects the horizon."""

    def test_ttd_matches_manual_slope(self):
        d = make_drive(value=0.99, dt=1 / 60)   # dt = 1 minute
        # fall toward lo at 0.02/ tick from 0.99
        d._history = [(i, 0.99 - i * 0.02) for i in range(40)]
        ttd = d.time_to_death(n=30)
        # window = samples 9..39: slope −0.02/tick, last value 0.21
        expected = (0.99 - 39 * 0.02) / 0.02 * d.dt
        assert ttd == pytest.approx(expected, rel=1e-9)

    def test_system_ttd_is_the_minimum(self):
        fast = make_drive(name="a", value=0.99, dt=1.0)
        fast._history = [(i, 0.99 - i * 0.02) for i in range(40)]
        slow = make_drive(name="b", value=0.99, dt=1.0)
        slow._history = [(i, 0.99 - i * 0.005) for i in range(40)]
        drives = Drives([fast, slow])
        assert drives.time_to_death() == pytest.approx(fast.time_to_death())

    def test_rate_respects_the_horizon(self):
        """TTD = 12 min, θ = 0.2 → E[wait] = 1/h ≤ 2.4 min."""
        d = make_drive(name="metabolic", value=0.84, dt=1 / 60,
                       lambda_rate=0.0, basal_direction=None, kappa=0.0)
        # exactly 31 samples: slope −0.02/tick over the window, last 0.24
        d._history = [(i, 0.84 - i * 0.02) for i in range(31)]
        ttd = d.time_to_death()
        assert ttd == pytest.approx(12 / 60, rel=1e-9)   # 12 minutes

        agent = BinsaiAgent(name="A", drives=Drives([d]), dry_run_llm=True,
                            activation_theta=0.2)
        agent.activate()
        draws = []
        agent.on("ActivationDraw", lambda p: draws.append(p))
        agent.tick(t=31)   # appends (31, 0.24): the window keeps its slope
        h = draws[-1]["h"]
        # the invariant the spec §12.7 accepts: E[wait] ≤ θ·TTD as computed
        # at the gate (exact when h_max does not bind)
        assert 1.0 / h <= 0.2 * draws[-1]["ttd"]
        assert draws[-1]["ttd"] is not None


class TestGuards:
    """§12.8 — the guard does not block with an absent signal."""

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
        agent.on("GuardSkippedUncalibrated", lambda p: skipped.append(p))
        verdict = agent.guard_check("corrective", t=1)
        assert verdict is None, "absent signal must not block"
        assert skipped and "service.pace" in skipped[-1]["uncalibrated"]


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


class TestInitialConditionAndSaturation:
    """§12.10, §12.11."""

    def test_initial_condition_is_the_set_point(self):
        d = make_drive()                    # value=None → x(t₀) = x*
        assert d.value == d.set_point

    def test_explicit_initial_condition_is_kept(self):
        d = make_drive(value=0.462)
        assert d.value == 0.462            # declared, hence justified

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