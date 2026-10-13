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

import copy as copy_module
import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from .drives import Drive, ZoneSpec

__all__ = [
    "ShapeRatios", "Calibration",
    "calibrate_drive", "calibrate_drive_perturbation",
    "basal_time_to_death", "grip", "resting_point",
]


# ── ADSR perturbation (v2.1 §1, level channel) ───────────────────────────────

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

    def apply_to(self, drive: Drive) -> Drive:
        """Write this calibration onto a drive. The whole point of calibrating."""
        drive.kappa = self.kappa
        drive.spring_reach = self.w
        drive.lambda_rate = self.lambda0
        drive.damping = self.damping
        drive.spring_fatigue = self.fatigue
        drive.allostatic_recovery = self.allostatic_recovery
        drive.spring = "magnetic-2nd"
        return drive

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


def _clone_for_counterfactual(drive: Drive, *, fatigue: float) -> Drive:
    """A copy of THIS drive, at its set-point, with u = 0 — the v2.1 §4 integration.

    Nothing is invented: every field comes off the drive the caller handed in.
    """
    import copy
    d = copy.copy(drive)
    d._history, d._events, d._impulses, d._open = [], [], [], []
    d._sustained, d._allostatic, d._settled = {}, 0.0, 0.0
    d.value, d.velocity = drive.set_point, 0.0
    d.spring_fatigue = fatigue
    d._init_bus()
    return d


def basal_time_to_death(drive: Drive, *, horizon: Optional[float] = None,
                        fatigue: Optional[float] = None,
                        horizon_factor: float = 3.0) -> Optional[float]:
    """Forward counterfactual integration of **this** drive with u = 0 — v2.1 §4.

    Not a slope fit and not a parallel simulation: a copy of the drive handed
    in, released from its set-point, with the allostatic load still
    integrating so the spring is allowed to lose. Returns the time to the
    viability wall, or None if it survives `horizon_factor` horizons.
    """
    H = horizon if horizon is not None else drive.horizon
    d = _clone_for_counterfactual(
        drive, fatigue=drive.spring_fatigue if fatigue is None else fatigue)
    lo_v, hi_v = drive.viability
    steps = int(round(horizon_factor * H / max(d.dt, 1e-12)))
    for t in range(1, steps + 1):
        d.update(tick=t)
        if not (lo_v < d.value < hi_v):
            return t * d.dt
    return None


def calibrate_drive(
    drive: Drive, *, mortality: float, horizon: Optional[float] = None,
    shape: Optional[ShapeRatios] = None, apply: bool = True,
    fatigue_bounds: tuple[float, float] = (1e-5, 50.0), iterations: int = 60,
) -> Calibration:
    """Calibrate a drive that already exists. This is the entry point.

    The margin, the set-point, the sign of the drift, the clock and the drift
    shape are read off `drive`. Phase 2 integrates a copy of that same drive
    with u = 0 — no parallel world. With `apply=True` the result is written
    back, so `drive.calibrate(mortality=0.8)` leaves the drive calibrated.
    """
    shape = shape or ShapeRatios()
    H = horizon if horizon is not None else drive.horizon
    lo_v, hi_v = drive.viability
    margin = min(abs(drive.set_point - lo_v), abs(hi_v - drive.set_point))
    if not (margin > 0):
        raise ValueError(
            f"drive '{drive.name}' has no room between its set-point and its viability "
            "limits, so there is nothing to calibrate. Set `viability` strictly inside "
            "the drive's [0,1] coordinate first.")
    if not (0.0 < mortality < 1.0):
        raise ValueError(
            f"mortality must be a fraction of the horizon in (0, 1), got {mortality}: "
            "at 1.0 or above the drive outlives its own horizon and A4 cannot hold.")

    direction = 1.0 if drive.lambda_rate >= 0 else -1.0
    d_eq = shape.rest_fraction * margin
    period = shape.period_fraction * H
    omega = 2.0 * math.pi / period
    kappa = omega ** 2
    w = shape.reach_fraction * margin
    lambda0 = kappa * d_eq * math.exp(-d_eq / w)
    damping = 2.0 * shape.damping_ratio * omega
    rho = shape.load_recovery / H

    probe = copy_module.copy(drive)
    probe.kappa, probe.spring_reach, probe.damping = kappa, w, damping
    probe.lambda_rate = math.copysign(lambda0, direction)
    probe.allostatic_recovery = rho
    probe.spring = "magnetic-2nd"

    def ttd(f: float) -> Optional[float]:
        d = _clone_for_counterfactual(probe, fatigue=f)
        steps = int(round(3.0 * H / max(d.dt, 1e-12)))
        for t in range(1, steps + 1):
            d.update(tick=t)
            if not (lo_v < d.value < hi_v):
                return t * d.dt
        return None

    target = mortality * H
    lo, hi = fatigue_bounds
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        t = ttd(mid)
        lo, hi = (mid, hi) if (t is None or t > target) else (lo, mid)
    fatigue = 0.5 * (lo + hi)
    measured = ttd(fatigue)

    G = grip(kappa, w)
    zeta = damping / (2.0 * omega)
    overshoot = d_eq * (1.0 + math.exp(-math.pi * zeta / math.sqrt(max(1e-9, 1 - zeta ** 2))))
    cal = Calibration(
        kappa=kappa, w=w, lambda0=math.copysign(lambda0, direction), damping=damping,
        fatigue=fatigue, allostatic_recovery=rho, set_point=drive.set_point, margin=margin,
        grip=G, grip_ratio=G / lambda0, rest_point=d_eq, omega=omega, period=period,
        overshoot_over_reach=overshoot / w, ttd_basal=measured,
        holds=G / lambda0 > 1.0, kills=measured is not None and measured < H)
    if apply:
        cal.apply_to(drive)
    return cal


def calibrate_drive_perturbation(
    drive: Drive, *, exploratory_budget: float,
    arrivals_per_horizon: Optional[float] = None, horizon: Optional[float] = None,
    severities: Sequence[int] = (1, 2, 3), seed: int = 11, apply: bool = True,
    bounds: tuple[float, float] = (1e-4, 2.0), iterations: int = 36,
) -> tuple[float, float, float]:
    """Phase 3 on a drive that exists — size its impulses from the agent's room.

    Integrates a copy of **this** drive, opening events through its own
    channel, until the unattended run lasts `exploratory_budget` of the
    horizon. The arrival rate is measured off the drive unless given.

    Raises:
        ValueError: when the rate cannot be measured, or when arrivals are too
            sparse for the problem to be well posed. The magnetic spring
            absorbs a displacement within its own period, so events that
            arrive slower than that are each absorbed before the next lands
            and *no* magnitude shortens the budget; the solver would otherwise
            answer with a hit the size of the whole margin. The governing
            number is arrivals per oscillation period, not per unit of clock.
    """
    import random

    H = horizon if horizon is not None else drive.horizon
    if not (0.0 < exploratory_budget < 1.0):
        raise ValueError(
            f"exploratory_budget is a fraction of the horizon in (0, 1), got "
            f"{exploratory_budget}.")
    rate = arrivals_per_horizon
    if rate is None:
        rate = drive.measured_arrival_rate(H)
    if rate is None:
        raise ValueError(
            f"drive '{drive.name}' has received no perturbations, so its arrival rate "
            "cannot be measured. Run it against its observed variables first, or pass "
            "arrivals_per_horizon explicitly — but know that only the product of "
            "arrivals and magnitude sets the exploratory budget, so guessing the rate "
            "silently decides the magnitude of every hit.")

    period = 2.0 * math.pi / math.sqrt(drive.kappa) * drive.dt if drive.kappa > 0 else float("inf")
    per_period = rate * period / H
    if per_period < 10.0:
        raise ValueError(
            f"{rate:g} arrivals per horizon is {per_period:.1f} per oscillation period "
            f"({period:g}): the spring absorbs each displacement before the next lands, "
            "so no magnitude shortens the exploratory budget. This is not a solver "
            "failure — the problem is not well posed. Measure the real crossing rate of "
            "the observed variables, widen the horizon, or soften the spring.")

    lo_v, hi_v = drive.viability
    margin = min(abs(drive.set_point - lo_v), abs(hi_v - drive.set_point))
    away = 1.0 if drive.lambda_rate >= 0 else -1.0

    def unattended(iota3: float) -> float:
        d = _clone_for_counterfactual(drive, fatigue=drive.spring_fatigue)
        d.impulse_iota = (iota3 * 0.11, iota3 * 0.33, iota3)
        r = random.Random(seed)
        p_tick = 1.0 - math.exp(-rate * d.dt / H)
        steps = int(round(H / max(d.dt, 1e-12)))
        for t in range(1, steps + 1):
            if r.random() < p_tick:
                d.open_perturbation(t, r.choice(list(severities)), away)
            d.update(tick=t)
            if not (lo_v < d.value < hi_v):
                return t * d.dt
        return H

    target = exploratory_budget * H
    lo, hi = bounds
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if unattended(mid) > target else (lo, mid)
    iota3 = 0.5 * (lo + hi)
    iotas = (iota3 * 0.11, iota3 * 0.33, iota3)
    if apply:
        drive.impulse_iota = iotas
    return iotas

