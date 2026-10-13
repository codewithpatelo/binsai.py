"""EPA v2.1 — ADSR perturbation envelope and the two-phase calibrator.

Two things live here, and they are not independent.

1. :class:`Perturbation` — an event emitted by an observed variable to a drive.
   The event is punctual; what it *carries* is an ADSR envelope with a
   lifetime:

       A  attack    x jumps by a fraction of the viability margin, in one sample
       D  decay     the peak falls toward the sustain level, time constant tau
       S  sustain   the condition keeps pressing while it holds
       R  release   ONLY a corrective action closes it, with grade g

   ADS belongs to the world, R belongs to the agent. The world never closes an
   event on its own.

   **The envelope acts on the level channel (x), not on the acceleration
   channel (u).** This is the structural result behind agentic slack: a
   sustained term in `a` is integrated twice and accumulates without bound, so
   an unattended night collapses in a fraction of the window no matter how the
   drive is tuned. A level displacement is bounded, and the magnetic spring can
   fight it. Use :meth:`Drive.sustain` for genuinely sustained *acceleration*
   (a standing load), not for perturbation events.

2. :func:`calibrate` — chooses (kappa, w, lambda, c, f) from what the operator
   actually wants to decide: where the drive rests, how visibly it oscillates,
   when basal negligence kills, and how much room the agent has to be wrong.

   Phase 1 fixes the geometry (how it regulates) from four shape ratios.
   Phase 2 bisects the fatigue f (when it dies) against the forward
   integration with u = 0. The two are orthogonal: in verification, kappa, w,
   lambda and c do not move for any death target; only f does.

   The acceptance tests are two inequalities that must hold together:

       R0 = kappa*w/(e*lambda0) > 1     the spring holds  -> regulating is possible
       TTD_basal < window               fatigue eats it   -> negligence kills (A4)

   If only the first holds, doing nothing is safe and the drive never generates
   pressure. If only the second holds, there is nothing the agent can sustain.

Both were derived against the magnetic-2nd spring with fatigue. With
``spring_fatigue = 0`` there is a permanent equilibrium and A4 cannot hold at
all — see :attr:`Drive.equilibrium`, which returns the viability bound as soon
as fatigue is present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from .drives import Drive, ZoneSpec

__all__ = [
    "Perturbation", "PerturbationSpec", "ShapeRatios", "Calibration",
    "calibrate", "basal_time_to_death", "grip", "resting_point",
]


# ── ADSR perturbation (v2.1 §1, level channel) ───────────────────────────────

@dataclass
class PerturbationSpec:
    """Envelope shape. Every field is a fraction — of the margin, or of the horizon.

    A spec carries no clock and no ruler. `attack` and `sustain` are fractions
    of the drive's viability margin; `rise`, `decay` and `release` are
    fractions of its regulation horizon. The same spec therefore describes a
    disk filling over a night and a queue backing up over a second.
    """
    attack:  float = 0.16           # peak displacement, fraction of the margin
    sustain: float = 0.04           # held displacement, fraction of the margin
    rise:    float = 0.010          # time to the peak, fraction of the horizon
    decay:   float = 0.0015         # peak -> sustain time constant, idem
    release: float = 0.036          # fade-out once an action closed it, idem
    zeta:    float = 0.64           # improving satiates less than worsening perturbs
    severity_scale: tuple[float, float, float] = (0.11, 0.33, 1.0)

    def at(self, horizon: float) -> "_Timed":
        """Resolve the fractions against a horizon, in whatever clock it uses."""
        return _Timed(self, max(horizon, 1e-9))

    def magnitude(self, severity: int) -> float:
        return self.attack * self.severity_scale[max(0, min(2, severity - 1))]

    def sustain_level(self, severity: int) -> float:
        return self.sustain * self.severity_scale[max(0, min(2, severity - 1))]


@dataclass(frozen=True)
class _Timed:
    """A spec read against a horizon: fractions become durations."""
    spec: PerturbationSpec
    horizon: float

    @property
    def rise(self) -> float: return max(self.spec.rise * self.horizon, 1e-9)
    @property
    def decay(self) -> float: return max(self.spec.decay * self.horizon, 1e-9)
    @property
    def release(self) -> float: return max(self.spec.release * self.horizon, 1e-9)


@dataclass
class Perturbation:
    """One open event. Lives until an action closes it.

    `g` is the accumulated release grade: 0 = untouched, 1 = fully closed. It
    is the measured quality of the corrective action (Delta_observed /
    Delta_expected), not a declaration — see :meth:`Drive.impulse`.
    """
    severity: int
    direction: float                # +1 toward surplus, -1 toward deficit; the
    #                                 world's semantics, never the drive's side
    born_at: int
    spec: PerturbationSpec
    margin: float
    horizon: float = 1.0
    g: float = 0.0
    closed_at: Optional[int] = None

    def level(self, tick: int) -> float:
        """Signed displacement this event contributes at `tick`."""
        s = tick - self.born_at
        if s < 0:
            return 0.0
        T = self.spec.at(self.horizon)
        a = self.spec.magnitude(self.severity) * self.margin
        su = self.spec.sustain_level(self.severity) * self.margin
        if s < T.rise:                                   # A
            v = a * (s / T.rise)
        else:                                            # D then S
            v = su + (a - su) * math.exp(-(s - T.rise) / T.decay)
        if self.closed_at is not None:                   # R
            v *= max(0.0, 1.0 - (tick - self.closed_at) / T.release)
        return self.direction * v * (1.0 - self.g)

    def release(self, g: float, tick: int) -> float:
        """Apply a corrective action of measured quality `g`. Returns the new grade.

        g = 0 is an action that ran and satiated nothing: the event stays open
        at full strength. That is where the satiation problem lives.
        """
        self.g = min(1.0, self.g + max(0.0, g) * (1.0 - self.g))
        if self.g >= 0.98 and self.closed_at is None:
            self.closed_at = tick
        return self.g

    def expired(self, tick: int) -> bool:
        return (self.closed_at is not None
                and tick - self.closed_at > self.spec.at(self.horizon).release)


class PerturbationChannel:
    """The open events of one drive, and their net displacement.

    Apply it by calling :meth:`settle` once per pulse, after `drive.update`.
    It writes the net level, so the spring sees the displacement and can pull
    against it.
    """

    def __init__(self, drive: Drive, spec: PerturbationSpec, margin: float,
                 horizon: float) -> None:
        self.drive = drive
        self.spec = spec
        self.margin = margin
        self.horizon = horizon
        self.open: list[Perturbation] = []
        self._applied = 0.0

    def fire(self, tick: int, severity: int, direction: float) -> Perturbation:
        """Emit an event. `direction` is the world's, not the drive's side."""
        p = Perturbation(severity=severity, direction=math.copysign(1.0, direction),
                         born_at=tick, spec=self.spec, margin=self.margin,
                         horizon=self.horizon)
        self.open.append(p)
        self.drive.record_event(tick, "shock" if severity >= 3 else "pert")
        return p

    def relieve(self, tick: int, severity: int, direction: float) -> None:
        """The world eased: a crossing back toward the set-point, scaled by zeta."""
        p = self.fire(tick, severity, -direction)
        p.spec = PerturbationSpec(**{**self.spec.__dict__,
                                     "attack": self.spec.attack * self.spec.zeta,
                                     "sustain": self.spec.sustain * self.spec.zeta})

    def correct(self, tick: int, g: float) -> int:
        """A corrective action of measured quality `g`. Returns events it closed."""
        closed = 0
        for p in self.open:
            if p.closed_at is None:
                before = p.g
                p.release(g, tick)
                if p.closed_at is not None and before < 0.98:
                    closed += 1
        if closed:
            self.drive.record_event(tick, "sat")
        return closed

    @property
    def load(self) -> float:
        """Events still open — the agent's outstanding debt."""
        return sum(1 for p in self.open if p.closed_at is None)

    def settle(self, tick: int) -> float:
        """Write this pulse's net displacement onto the drive. Returns it."""
        self.open = [p for p in self.open if not p.expired(tick)]
        total = sum(p.level(tick) for p in self.open)
        delta = total - self._applied
        self._applied = total
        if delta:
            self.drive.impulse(delta)
        return total


# ── calibration ──────────────────────────────────────────────────────────────

def grip(kappa: float, w: float) -> float:
    """G = kappa*w/e — the most the magnetic spring can ever pull."""
    return kappa * w / math.e


def resting_point(kappa: float, w: float, lambda0: float) -> Optional[float]:
    """Temporary rest |d| where lambda = kappa*d*e^(-d/w). None when the spring
    has already lost (lambda >= G): then there is no rest at all."""
    lam = abs(lambda0)
    if grip(kappa, w) <= lam:
        return None
    lo, hi = 1e-9, w
    for _ in range(80):
        m = 0.5 * (lo + hi)
        if kappa * m * math.exp(-m / w) < lam:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


@dataclass
class ShapeRatios:
    """Phase 1 — how the drive regulates. Every field is dimensionless.

    Nothing here mentions hours or a night. A drive is specified relative to
    two scales it carries anyway: its viability `margin` (the length scale)
    and its regulation `horizon` (the time scale) — how long the thing it
    regulates is supposed to hold together without outside help. An overnight
    agent's horizon is its window; a long-running service's is its shift; a
    control loop's is its settling budget. The calibration is invariant under
    rescaling either one (see `test_calibration_is_scale_free`).

    The defaults are **one measured prior**, not canon: they come from a human
    operator tuning a long-horizon coding agent on 2026-10-13 until the five
    acceptance checks held. They are a documented starting point with a shape
    known to work, and nothing here claims they are optimal or universal.
    Other domains should expect different ratios and are expected to say so.
    """
    rest_fraction:   float = 0.18   # d_eq / margin
    reach_fraction:  float = 1.18   # w / margin   (~6.6 * d_eq)
    period_fraction: float = 0.13   # T_osc / horizon — ~7 cycles per horizon
    damping_ratio:   float = 0.33   # zeta: rings, but the overshoot stays inside w
    load_recovery:   float = 7.0    # rho_Lambda * horizon — load settles within it


@dataclass
class Calibration:
    kappa: float
    w: float
    lambda0: float
    damping: float
    fatigue: float
    allostatic_recovery: float
    set_point: float
    margin: float
    # derived, for the contract and for the boot assertion
    grip: float
    grip_ratio: float               # R0 = G / |lambda0|; must be > 1
    rest_point: float
    omega: float
    period: float
    overshoot_over_reach: float     # must be < 1 or it escapes by inertia
    ttd_basal: Optional[float]      # measured, not predicted
    holds: bool                     # R0 > 1
    kills: bool                     # TTD_basal inside the window  (A4)

    def dimensionless(self, horizon: float) -> dict[str, float]:
        """The groups that actually define this calibration.

        A calibration is these six numbers; `margin` and `horizon` only say
        what clock and what ruler they are read against. Two drives with the
        same groups behave identically after rescaling.
        """
        M, T = self.margin, horizon
        return {
            "kappa*T^2":    self.kappa * T * T,
            "c*T":          self.damping * T,
            "lambda*T^2/M": abs(self.lambda0) * T * T / M,
            "rho*T":        self.allostatic_recovery * T,
            "f*M*T":        self.fatigue * M * T,
            "w/M":          self.w / M,
        }

    @property
    def sound(self) -> bool:
        return self.holds and self.kills and self.overshoot_over_reach < 1.0

    def as_contract(self) -> dict:
        return {
            "kappa": round(self.kappa, 6), "springReach": round(self.w, 6),
            "lambdaRate": round(self.lambda0, 6), "damping": round(self.damping, 6),
            "springFatigue": round(self.fatigue, 6),
            "allostaticRecovery": round(self.allostatic_recovery, 6),
            "setPoint": self.set_point, "margin": self.margin,
            "derived": {
                "G": round(self.grip, 6), "gripRatio": round(self.grip_ratio, 4),
                "restPoint": round(self.rest_point, 6),
                "oscillationPeriod": round(self.period, 4),
                "overshootOverReach": round(self.overshoot_over_reach, 4),
                "ttdBasal": None if self.ttd_basal is None else round(self.ttd_basal, 3),
            },
        }


def _drive_for(c: dict, direction: float, zones: Optional[Sequence[ZoneSpec]], dt: float) -> Drive:
    return Drive(
        name="calib", set_point=c["set_point"], value=c["set_point"],
        kappa=c["kappa"], lambda_rate=math.copysign(c["lambda0"], direction),
        basal_direction="recover" if direction > 0 else "decay",
        spring="magnetic-2nd", spring_reach=c["w"], damping=c["damping"],
        spring_fatigue=c["fatigue"], allostatic_recovery=c["rho"],
        drift_shape=c["drift_shape"], drift_gamma=c["drift_gamma"], dt=dt,
        zones=list(zones) if zones else None,
        viability=(c["set_point"] - c["margin"], c["set_point"] + c["margin"]),
    )


def basal_time_to_death(
    *, kappa: float, w: float, lambda0: float, damping: float, fatigue: float,
    allostatic_recovery: float, set_point: float, margin: float, direction: float = 1.0,
    window: float = 11.5, dt: float = 1.0, drift_shape: str = "linear",
    drift_gamma: float = 1.0, horizon_factor: float = 3.0,
) -> Optional[float]:
    """Forward counterfactual integration with u = 0 — v2.1 §4.

    Not a slope fit: the allostatic load keeps integrating, so the spring is
    allowed to lose. Returns time to the viability wall, or None if the drive
    survives `horizon_factor * window`.
    """
    d = _drive_for(dict(kappa=kappa, w=w, lambda0=abs(lambda0), damping=damping,
                        fatigue=fatigue, rho=allostatic_recovery, set_point=set_point,
                        margin=margin, drift_shape=drift_shape, drift_gamma=drift_gamma),
                   direction, None, dt)
    lo, hi = set_point - margin, set_point + margin
    steps = int(round(horizon_factor * window / dt))
    for t in range(1, steps + 1):
        d.update(tick=t)
        if not (lo < d.value < hi):
            return t * dt
    return None


def calibrate(
    *, margin: float, horizon: float, mortality: float,
    direction: float = 1.0, set_point: float = 0.0,
    shape: ShapeRatios = ShapeRatios(), allostatic_recovery: Optional[float] = None,
    dt: float = 1.0, drift_shape: str = "linear", drift_gamma: float = 1.0,
    fatigue_bounds: tuple[float, float] = (1e-5, 20.0), iterations: int = 60,
) -> Calibration:
    """Phase 1 (geometry) then phase 2 (fatigue), for one drive.

    Args:
        margin:    distance from the set-point to the viability wall.
        horizon:   the drive's regulation horizon, in the same clock as `dt`.
        mortality: **the thing you actually decide** — at what fraction of the
                   horizon basal negligence kills, with nobody acting. Below
                   1.0 or A4 does not hold; not so small that there is no time
                   to work. 0.8 means the drive reaches four fifths of its
                   horizon alone and then dies.

    `margin` and `horizon` are scales, not settings: the calibration is
    invariant under rescaling either, so the same `ShapeRatios` and the same
    `mortality` describe an overnight window, a trading session and a servo
    loop. Nothing in here knows what an hour is.
    """
    if not (0.0 < set_point - margin and set_point + margin < 1.0):
        raise ValueError(
            f"viability band [{set_point - margin:.3f}, {set_point + margin:.3f}] touches the "
            "drive's [0,1] state bound: the wall becomes a clip and the drive can never cross "
            "it. Calibrate inside the coordinate (e.g. set_point=0.5, margin<=0.45) and scale "
            "the result: kappa, c and rho are invariant, lambda and w scale with the margin, "
            "f scales with its inverse.")
    if not (0.0 < mortality < 1.0):
        raise ValueError(
            f"mortality must be a fraction of the horizon in (0, 1), got {mortality}: "
            "at 1.0 or above the drive outlives its own horizon and A4 cannot hold.")
    ttd_basal = mortality * horizon
    rho = (allostatic_recovery if allostatic_recovery is not None
           else shape.load_recovery / horizon)
    d_eq = shape.rest_fraction * margin
    w = shape.reach_fraction * margin
    period = shape.period_fraction * horizon
    omega = 2.0 * math.pi / period
    kappa = omega ** 2
    lambda0 = kappa * d_eq * math.exp(-d_eq / w)
    damping = 2.0 * shape.damping_ratio * omega

    # phase 2 — more fatigue dies sooner; bisect against the integration itself,
    # because the closed form for the release date does not match simulation.
    def ttd(f: float) -> Optional[float]:
        return basal_time_to_death(
            kappa=kappa, w=w, lambda0=lambda0, damping=damping, fatigue=f,
            allostatic_recovery=rho, set_point=set_point, margin=margin,
            direction=direction, window=horizon, dt=dt,
            drift_shape=drift_shape, drift_gamma=drift_gamma)

    lo, hi = fatigue_bounds
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        t = ttd(mid)
        if t is None or t > ttd_basal:
            lo = mid            # survives too long -> needs more fatigue
        else:
            hi = mid
    fatigue = 0.5 * (lo + hi)
    measured = ttd(fatigue)

    G = grip(kappa, w)
    zeta = damping / (2.0 * omega)
    overshoot = d_eq * (1.0 + math.exp(-math.pi * zeta / math.sqrt(max(1e-9, 1 - zeta ** 2))))
    return Calibration(
        kappa=kappa, w=w, lambda0=math.copysign(lambda0, direction), damping=damping,
        fatigue=fatigue, allostatic_recovery=rho, set_point=set_point, margin=margin,
        grip=G, grip_ratio=G / lambda0, rest_point=d_eq, omega=omega, period=period,
        overshoot_over_reach=overshoot / w, ttd_basal=measured,
        holds=G / lambda0 > 1.0,
        kills=measured is not None and measured < horizon,
    )


def calibrate_perturbation(
    cal: Calibration, *, horizon: float, exploratory_budget: float,
    arrivals_per_horizon: float = 400.0,
    spec: PerturbationSpec = PerturbationSpec(),
    severities: Sequence[int] = (1, 2, 3), dt: float = 1.0, seed: int = 11,
    bounds: tuple[float, float] = (1e-4, 2.0), iterations: int = 36,
) -> PerturbationSpec:
    """Phase 3 — size the envelope so an unattended run lasts that long.

    Args:
        exploratory_budget: fraction of the horizon the drive survives while
            nobody closes any event. It is the room the agent has to act and
            be wrong: every action that measures g = 0 is spent out of it.
        arrivals_per_horizon: expected events over one horizon. **Not a
            calibration choice** — it is a property of the environment, and it
            must be measured from the observed variables' crossing rate. Only
            the product of arrivals and magnitude sets the budget, so guessing
            one of them silently decides the other.

    The trade is a square root: a budget twice as long needs a quarter of the
    load. Solve it, do not guess it.

    Raises:
        ValueError: when arrivals are too sparse for the problem to be well
            posed. The spring absorbs a displacement within its own period, so
            if events arrive slower than that they are each absorbed before the
            next one lands and *no* magnitude shortens the budget — the solver
            would otherwise answer with a hit the size of the whole margin.
            The governing number is arrivals per oscillation period: below
            about ten the load cannot accumulate at all. Measure the real
            crossing rate, or widen the horizon, or soften the spring.
    """
    import random

    per_period = arrivals_per_horizon * cal.period / horizon
    if per_period < 10.0:
        raise ValueError(
            f"{arrivals_per_horizon:g} arrivals per horizon is {per_period:.1f} per "
            f"oscillation period ({cal.period:g}): the spring absorbs each displacement "
            "before the next lands, so no magnitude shortens the exploratory budget. "
            "This is not a solver failure — the problem is not well posed. Measure the "
            "real crossing rate of the observed variables before sizing the envelope.")

    window = horizon
    target_ttd = exploratory_budget * horizon

    def ttd_unattended(attack: float) -> float:
        s = PerturbationSpec(**{**spec.__dict__, "attack": attack,
                                "sustain": spec.sustain * attack / max(spec.attack, 1e-9)})
        r = random.Random(seed)
        d = _drive_for(dict(kappa=cal.kappa, w=cal.w, lambda0=abs(cal.lambda0),
                            damping=cal.damping, fatigue=cal.fatigue,
                            rho=cal.allostatic_recovery, set_point=cal.set_point,
                            margin=cal.margin, drift_shape="linear", drift_gamma=1.0),
                       math.copysign(1.0, cal.lambda0), None, dt)
        ch = PerturbationChannel(d, s, cal.margin, window)
        lo, hi = cal.set_point - cal.margin, cal.set_point + cal.margin
        steps = int(round(window / dt))
        # arrivals_per_horizon is dimensionless: expected events over one horizon.
        p_tick = 1.0 - math.exp(-arrivals_per_horizon * dt / window)
        for t in range(1, steps + 1):
            if r.random() < p_tick:
                ch.fire(t, r.choice(list(severities)), math.copysign(1.0, cal.lambda0))
            ch.settle(t)
            d.update(tick=t)
            if not (lo < d.value < hi):
                return t * dt
        return window

    lo, hi = bounds
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if ttd_unattended(mid) > target_ttd:
            lo = mid                  # too gentle -> hit harder
        else:
            hi = mid
    attack = 0.5 * (lo + hi)
    return PerturbationSpec(**{**spec.__dict__, "attack": attack,
                               "sustain": spec.sustain * attack / max(spec.attack, 1e-9)})
