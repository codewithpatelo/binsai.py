"""Needs (drives) — EPA state equation with algedonic zones.

The Pro-Action Equation (EPA), per need i, per pulse:

    x_i(t+1) = x_i(t) + λ_i(x_i, t) − κ_i·(x_i(t) − x_i*) + u_i(t)
               + Σ_j W_ij·(x_j(t) − x_j*)

    x_i   level of the need          | the state being regulated
    x_i*  set-point                  | theoretical harmony point
    λ_i   basal drift                | what happens if nothing happens
    κ_i   elastic spring             | pulls toward set-point, keeps oscillation alive
    u_i   stimuli & actions          | satiate (α>0, reduces deviation) or perturb (α<0)
    W_ij  coupling                   | how much another need's deviation moves this one

Semantics (satisfaction convention — see docs/EPA.md §2):
    x ∈ [0, 1] is the SATISFACTION level of the need — not the deficit
    magnitude:  HIGH = satisfied / slack  |  LOW = deficit = urgency
    set_point (x*) is the homeostatic target (equilibrium zone center ≈ 0.70).

    deplete(amount)  → lowers x  (resource consumed: tokens spent, work done)
    satiate(amount)  → raises x  (need satisfied: delivery made, consolidation)
    update()         → applies λ + spring release + coupling per pulse.
                       λ = lambda_rate is SIGNED (or set via basal_direction):
                         "recover" / λ > 0 → inaction replenishes (pull needs:
                                             budget windows refill, memory frees)
                         "decay"   / λ < 0 → inaction starves (push needs:
                                             hunger, service backlog build up)
                         λ = 0            → only stimuli and actions move the need

Need categories (EPA §2.4):
    push — moves toward activation: the longer you wait, the more pressure
    pull — moves toward inhibition: the more you consume, the more it pulls
           back. A pull need can still ACTIVATE the agent — inhibiting often
           means doing a preservation task (kill processes, compact context).
    A minimally viable system needs at least one of each.

10 canonical drives across 6 Bunge-Romero strata are importable presets —
defaults, not constraints. Only δ_metabolic (S1) is active in MVP1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .events import (
    EventEmitter, ZONE_CHANGED, PRESSURE_UPDATED, SATIATED, COUPLED,
    VIABILITY_BREACHED, TENSION_RELEASED,
)


@dataclass
class ZoneSpec:
    """A named fuzzy algedonic zone with center and width (Gaussian σ)."""
    name:   str
    center: float
    width:  float = 0.12


class Stratum(Enum):
    """Bunge-Romero ontological levels (descriptive taxonomy — optional)."""
    MATERIAL       = "material"        # S1
    CHEMICAL       = "chemical"        # S2 (empty for AI)
    BIOLOGICAL     = "biological"      # S3
    TECHNICAL      = "technical"       # S4
    SOCIAL         = "social"          # S5
    TECHNOLOGICAL  = "technological"   # S6 (Romero extension)


@dataclass
class Drive(EventEmitter):
    """A need with bilateral set-point regulation (EPA state equation).

    Discrete-time dynamics (one pulse):
        x(t+1) = x(t) + λ(x,t) − r(t) + u(t) + Σ_j W_j·(x_j(t−τ) − x_j*)

    where r(t) is the spring term — κ(x−x*) under spring="linear", or a
    tension-release pulse (σ charges with displacement, discharges past θ)
    under spring="pulsatile" (default; see docs/SPRING.md).

    update() applies the autonomous terms (basal drift + spring + coupling).
    satiate() / deplete() apply the action-feedback term u.

    Attributes:
        name:            Need identifier
        category:        "push" (accumulates pressure → activates) or
                         "pull" (protects a resource → inhibits/preserves)
        stratum:         Ontological level (Bunge-Romero) — optional taxonomy
        value:           Current x ∈ [0, 1]  (satisfaction level; low = deficit)
        set_point:       Homeostatic target x*
        kappa:           Spring coefficient κ. Under "linear" it is the elastic
                         return rate; under "pulsatile" it is the tension
                         charge rate (σ += κ·d·e^(−|d|/w) per pulse)
        lambda_rate:     Basal flux λ per pulse, SIGNED (or via basal_direction)
        basal_direction: Optional semantic alias: "recover" forces λ>0 (the need
                         replenishes under inaction — pull/resource drives),
                         "decay" forces λ<0 (satisfaction decays under neglect —
                         push drives like hunger or service backlog)
        satiation_rate:  Multiplier applied in satiate()
        alpha_in:        Hysteresis — membership needed to ENTER a new zone
        alpha_out:       Hysteresis — current zone held while its membership
                         stays above this (α_in/α_out; spec §3)
        viability:       (lo, hi) viability limits — crossing is operational
                         death; emits ViabilityBreached (conjunctive over needs)
        observed:        ObservedVariable list — operational variables this
                         need senses (level + pace pressure; spec §4)
        subdrives:       Child needs for recursive decomposition
        description:     Human-readable explanation
    """
    name:           str
    stratum:        Optional[Stratum] = None  # descriptive taxonomy, does not affect simulation
    value:          float = 0.70
    set_point:      float = 0.70
    kappa:          float = 0.05
    lambda_rate:    float = 0.005
    satiation_rate: float = 0.10
    category:       str   = "push"     # "push" | "pull" (EPA §2.4)
    basal_direction: Optional[str] = None  # "decay" | "recover" — sets sign of λ
    subdrives:      list["Drive"] = field(default_factory=list)
    description:    str   = ""
    drift:          str   = "constant"  # "constant" | "linear" | "exponential" | "circadian" | callable
    drift_period:   int   = 120        # circadian period in ticks
    drift_k:        float = 1.0        # exponential drift coefficient
    satiation:      str   = "linear"   # "linear" | "saturating" | "sigmoid" | callable
    spring:         str   = "pulsatile"  # "pulsatile" | "linear" | callable
    spring_threshold: float = 0.10     # θ — tension σ that triggers a release pulse
    spring_release: float = 1.0        # ρ — fraction of σ discharged per pulse
    spring_reach:   float = 0.30       # w — grip peaks at |d|=w then decays (inf = no escape)
    zones:          Optional[list[ZoneSpec]] = None  # None = default 7 algedonic bands
    alpha_in:       float = 0.0        # hysteresis: μ needed to enter a new zone
    alpha_out:      float = 1.0        # hysteresis: exit old zone when μ ≤ this
    viability:      tuple[float, float] = (0.0, 1.0)  # viability limits
    observed:       list  = field(default_factory=list)  # list[ObservedVariable]
    history_limit:  int   = 0     # max ticks retained in .history.
    # Default 0 = retain everything — measurement integrity first: any
    # structure that discards data must say so. Set an explicit limit when
    # memory matters; when it acts, `history_dropped` counts the discarded
    # ticks and a warning is emitted once.

    # Internal: not part of public API
    _history: list[tuple[int, float]] = field(default_factory=list, repr=False)
    _events:  list[tuple[int, str]]  = field(default_factory=list, repr=False)
    _tension: float = field(default=0.0, repr=False)  # pulsatile spring tension σ
    _history_dropped: int = field(default=0, repr=False)
    _history_warned:  bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self._init_bus()
        self.value     = float(self.value)
        self.set_point = float(self.set_point)
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Drive value must be in [0,1], got {self.value}")
        if not 0.0 <= self.set_point <= 1.0:
            raise ValueError(f"Set point must be in [0,1], got {self.set_point}")
        if self.category not in ("push", "pull"):
            raise ValueError(f"Drive category must be 'push' or 'pull', got {self.category!r}")
        # basal_direction fixes the sign of λ semantically
        if self.basal_direction == "recover":
            self.lambda_rate = abs(self.lambda_rate)
        elif self.basal_direction == "decay":
            self.lambda_rate = -abs(self.lambda_rate)
        elif self.basal_direction is not None:
            raise ValueError(
                f"basal_direction must be 'decay' or 'recover', got {self.basal_direction!r}"
            )
        # Resolve drift to callable if it's a named policy
        if isinstance(self.drift, str):
            self._drift_fn = self._resolve_drift(self.drift)
        else:
            self._drift_fn = self.drift
        # Resolve spring policy: "linear" (legacy damper) or "pulsatile"
        # (tension σ integrates displacement, discharges past threshold θ)
        if isinstance(self.spring, str):
            if self.spring not in ("linear", "pulsatile"):
                raise ValueError(
                    f"spring must be 'pulsatile', 'linear' or a callable, got {self.spring!r}"
                )
        if not (0.0 < self.spring_release <= 1.0):
            raise ValueError("spring_release must be in (0, 1]")
        if self.spring_reach is not None and not (
            self.spring_reach > 0 or self.spring_reach == float("inf")
        ):
            raise ValueError("spring_reach must be > 0 (or inf for unbounded grip)")
        # Resolve satiation to callable if it's a named policy
        if isinstance(self.satiation, str):
            self._satiation_fn = self._resolve_satiation(self.satiation)
        else:
            self._satiation_fn = self.satiation
        # Observed-variable pressure state (EPA §4.8)
        self.pressure:         Optional[float] = None
        self.driving_variable: Optional[str]   = None
        # Default zones if none provided — 7 interpretable bands.
        # Satisfaction convention: low x = deficit (scarcity), high x =
        # superavit (slack). The deficit side is the wide operative region —
        # that's where risk lives under basal neglect.
        if self.zones is None:
            self.zones = [
                ZoneSpec("critical_deficit",     0.20, 0.12),
                ZoneSpec("high_deficit",         0.45, 0.10),
                ZoneSpec("moderate_deficit",     0.60, 0.08),
                ZoneSpec("equilibrium",          0.70, 0.08),
                ZoneSpec("moderate_superavit",   0.78, 0.08),
                ZoneSpec("high_superavit",       0.87, 0.08),
                ZoneSpec("critical_superavit",   0.95, 0.08),
            ]
        self._last_zone = None  # Force first update() to emit zone.enter

    def _resolve_drift(self, name: str):
        import math
        if name == "constant":
            return lambda v, s, t, lam, k: lam
        elif name == "linear":
            return lambda v, s, t, lam, k: lam * (1.0 + max(0.0, (v - s) / max(0.01, s)))
        elif name == "exponential":
            return lambda v, s, t, lam, k: lam * math.exp(k * max(0.0, v - s))
        elif name == "circadian":
            period = self.drift_period
            return lambda v, s, t, lam, k: lam * (1.0 + math.sin(2 * math.pi * t / period)) / 2.0
        else:
            raise ValueError(f"Unknown drift policy: {name!r}. Use 'constant', 'linear', 'exponential', 'circadian', or a callable.")

    def _spring_charge(self, deviation: float) -> float:
        """Pulsatile tension charge rate: κ·d·e^(−|d|/w) — the "magnet" curve.

        Grip peaks at |d| = w (max κw/e) then decays — the spring has finite
        reach, so drift can escape it past that point. w = inf disables the
        decay (plain κ·d charge → bounded oscillating ceiling).
        """
        import math
        d = deviation
        if self.spring_reach is not None and self.spring_reach != float("inf"):
            d *= math.exp(-abs(d) / self.spring_reach)
        return self.kappa * d

    def _spring_step(self, tick: int) -> float:
        """Restoring term for this pulse — depends on the spring policy.

        "linear":    continuous damper −κ(x−x*) (legacy behaviour)
        "pulsatile": charge tension σ, discharge ρ·σ when |σ| ≥ θ
        callable:    user-defined f(deviation) → restoring delta
        """
        d = self.value - self.set_point
        if callable(self.spring):
            return self.spring(d)
        if self.spring == "linear":
            return -self.kappa * d
        # pulsatile: integrate displacement into tension, release in pulses
        self._tension += self._spring_charge(d)
        if abs(self._tension) >= self.spring_threshold:
            release = self.spring_release * self._tension
            self._tension -= release
            self.emit(TENSION_RELEASED, {
                "drive":   self.name,
                "tension": round(release, 6),
                "value":   round(self.value, 4),
                "tick":    tick,
            })
            self.record_event(tick, "release")
            return -release
        return 0.0

    @property
    def deviation(self) -> float:
        """Signed deviation from set-point (satisfaction convention:
        negative = deficit, positive = superavit)."""
        return self.value - self.set_point

    @property
    def urgency(self) -> float:
        """Absolute urgency: 0 at set-point, 1 at maximum deviation."""
        return abs(self.deviation)

    @property
    def resting_level(self) -> float:
        """Where the drive settles under inaction (basal flux vs spring).

        "linear" spring:  x_rest = x* + λ/κ — damper cancellation point.
        "pulsatile" spring: the tension cycle nets +λ per release interval;
        the oscillating ceiling sits ~x* + λ/(κ·ρ) when the grip can hold —
        i.e. λ ≤ κρw/e (the magnet's max charge rate). If λ exceeds the grip,
        the drive escapes toward the viability bound.
        """
        if callable(self.spring):
            return self.value  # user-defined spring: unknowable a priori
        if self.spring == "pulsatile":
            import math
            if self.lambda_rate == 0:
                return self.set_point  # releases only pull toward x*
            w = self.spring_reach
            grip = (self.kappa * w / math.e) if (w and w != float("inf")) else float("inf")
            lam = abs(self.lambda_rate)
            bound = 1.0 if self.lambda_rate > 0 else 0.0
            if lam > grip * self.spring_release:
                return bound  # drift escapes the spring — viability bound
            ceiling = self.set_point + self.lambda_rate / (self.kappa * self.spring_release)
            return max(0.0, min(1.0, ceiling))
        if self.kappa > 0:
            return self.set_point + self.lambda_rate / self.kappa
        if self.lambda_rate > 0:
            return 1.0
        if self.lambda_rate < 0:
            return 0.0
        return self.value

    @property
    def tension(self) -> float:
        """Accumulated spring tension σ (pulsatile policy). 0 under "linear"."""
        return self._tension

    def pressure_components(self) -> dict:
        """Traceable split of what is pushing this drive right now.

        Three separate sources — kept distinct on purpose:
            level:   observed-variable level pressure (where you are)
            pace:    observed-variable pacing pressure (how fast it degrades)
            tension: accumulated autonomous tension σ (where it trends under
                     basal neglect — this is what makes satiation meaningful)
        """
        level = pace = None
        for var in self.observed:
            lp = var.last_level_pressure
            if lp is not None and (level is None or lp > level):
                level = lp
            pp = var.last_pace_pressure
            if pp is not None and (pace is None or pp > pace):
                pace = pp
        return {"level": level, "pace": pace, "tension": self._tension}

    @property
    def history(self) -> list[tuple[int, float]]:
        """Trajectory as (tick, value) pairs, oldest first (read-only copy)."""
        return list(self._history)

    @property
    def history_dropped(self) -> int:
        """Ticks discarded by history_limit so far. >0 means some consumer of
        .history is seeing a window, not the full run."""
        return self._history_dropped

    @property
    def events(self) -> list[tuple[int, str]]:
        """Recorded events as (tick, kind) pairs, oldest first (read-only copy).

        kind is one of ``"sat"`` (action that satiated), ``"pert"`` (action that
        perturbed), ``"alarm"`` (entered the red zone) or ``"shock"``.
        """
        return list(self._events)

    def record_event(self, tick: int, kind: str) -> None:
        """Append an event for visualisation (e.g. an action that satiates/perturbs)."""
        self._events.append((int(tick), kind))

    def update(self, tick: int = 0, coupling: float = 0.0,
               coupling_sources: Optional[dict[str, float]] = None) -> list[tuple[str, str]] | None:
        """Apply autonomous terms: basal drift + elastic return to x* + coupling.

            x(t+1) = x(t) + λ(x,t) − κ·(x(t) − x*) + Σ_j W_j·(x_j(t−τ) − x_j*)

        The drift term is λ (lambda_rate, signed) shaped by the configured
        drift policy: for "constant", it is exactly λ per pulse, so a
        negative λ lowers x under inaction (restorative need).

        Emits on this drive's own event bus:
            ZoneChanged        — algedonic band transition (with hysteresis)
            PressureUpdated    — every pulse when observed variables exist
            ViabilityBreached  — x crossed a viability limit
            Coupled            — coupling term ≠ 0 moved this drive

        Also returns legacy [(event_type, zone_name)] transitions for the
        agent's dot-syntax re-emission (e.g. "zone.enter" → drive.hunger.<zone>).
        """
        old_zone = self._last_zone
        spring_delta = self._spring_step(tick)
        drift_amount = self._drift_fn(self.value, self.set_point, tick, self.lambda_rate, self.drift_k)
        self.value = max(0.0, min(1.0, self.value + spring_delta + drift_amount + coupling))
        self._history.append((tick, self.value))
        if self.history_limit and len(self._history) > self.history_limit:
            dropped = len(self._history) - self.history_limit
            self._history_dropped += dropped
            self._history = self._history[-self.history_limit:]
            if not self._history_warned:
                import warnings
                warnings.warn(
                    f"Drive '{self.name}': history_limit={self.history_limit} "
                    f"discarded {dropped} tick(s) — every truncated tick makes "
                    f"comparative figures lie. Set history_limit=0 (default) to "
                    f"retain the full trajectory.",
                    stacklevel=2,
                )
                self._history_warned = True

        # Coupled event — the deviation of another need moved this one via W
        if abs(coupling) > 1e-9:
            self.emit(COUPLED, {
                "drive":    self.name,
                "amount":   round(coupling, 6),
                "sources":  coupling_sources or {},
                "tick":     tick,
            })

        # Viability limit — crossing is operational death (conjunctive)
        lo_v, hi_v = self.viability
        if self.value <= lo_v or self.value >= hi_v:
            self.emit(VIABILITY_BREACHED, {
                "drive":  self.name,
                "value":  round(self.value, 4),
                "limit":  lo_v if self.value <= lo_v else hi_v,
                "side":   "low" if self.value <= lo_v else "high",
                "tick":   tick,
            })

        # Observed variables: need pressure = max over valid sensors (§4.8)
        if self.observed:
            self._poll_observed(tick)

        new_zone = self._zone_with_hysteresis()
        memberships = self.zone_memberships()
        if old_zone is None:
            self._last_zone = new_zone
            self._emit_zone_changed(None, new_zone, memberships, tick)
            return [("zone.enter", new_zone)]
        if old_zone != new_zone:
            self._last_zone = new_zone
            self._emit_zone_changed(old_zone, new_zone, memberships, tick)
            return [("zone.exit", old_zone), ("zone.enter", new_zone)]
        return None

    def _zone_with_hysteresis(self) -> str:
        """Dominant zone with α_in/α_out hysteresis (spec §3).

        A new zone must reach membership ≥ α_in to be entered, AND the
        incumbent is held while its membership stays above α_out — so a need
        oscillating near a cut does not flicker events.
        Defaults (α_in=0, α_out=1) = pure dominant-zone switching.
        """
        candidate = self.get_zone()
        if self._last_zone is None or candidate == self._last_zone:
            return candidate
        m = self.zone_memberships()
        if m.get(candidate, 0.0) >= self.alpha_in and m.get(self._last_zone, 0.0) <= self.alpha_out:
            return candidate
        return self._last_zone

    def _emit_zone_changed(self, prev: Optional[str], new: str,
                           memberships: dict[str, float], tick: int) -> None:
        side = ("deficit" if "deficit" in new
                else "superavit" if "superavit" in new else "equilibrium")
        self.emit(ZONE_CHANGED, {
            "drive":       self.name,
            "prev_zone":   prev,
            "zone":        new,
            "side":        side,
            "membership":  round(memberships.get(new, 0.0), 4),
            "value":       round(self.value, 4),
            "tick":        tick,
        })

    def _poll_observed(self, tick: int) -> None:
        """Aggregate pressure from observed variables — max (non-fungible)."""
        best_p, best_var = None, None
        invalid: list[str] = []
        for var in self.observed:
            p = var.pressure(tick)
            if p is None:
                invalid.append(var.name)
                continue
            if best_p is None or p > best_p:
                best_p, best_var = p, var.name
        self.pressure = best_p
        self.driving_variable = best_var
        self.emit(PRESSURE_UPDATED, {
            "drive":             self.name,
            "pressure":          round(best_p, 4) if best_p is not None else None,
            "driving_variable":  best_var,
            "invalid_sensors":   invalid,
            "tick":              tick,
        })

    def _resolve_satiation(self, name: str):
        import math
        if name == "linear":
            return lambda v, a, r: a * r
        elif name == "saturating":
            # diminishing returns: large amounts give less per-unit benefit
            return lambda v, a, r: r * (1.0 - math.exp(-a))
        elif name == "sigmoid":
            # steepest near set-point, gentle at extremes
            return lambda v, a, r: r * a / (1.0 + abs(v - self.set_point) * 5.0)
        else:
            raise ValueError(f"Unknown satiation policy: {name!r}. Use 'linear', 'saturating', 'sigmoid', or a callable.")

    def satiate(self, amount: float) -> None:
        """Raise satisfaction using the configured satiation function g.

        Linear (default): value += amount * satiation_rate
        Saturating: diminishing returns for large amounts
        Sigmoid: strongest effect near set-point

        Emits Satiated with the deviation actually closed (the quality
        signal g — how much the action reduced |x − x*|).
        """
        before = self.value
        increase = self._satiation_fn(self.value, amount, self.satiation_rate)
        self.value = min(1.0, self.value + increase)
        self.emit(SATIATED, {
            "drive":      self.name,
            "amount":     round(amount, 4),
            "reduction":  round(abs(before - self.set_point)
                                - abs(self.value - self.set_point), 4),
            "value":      round(self.value, 4),
        })

    def deplete(self, amount: float) -> None:
        """Lower x by amount (resource consumed: tokens spent, work done)."""
        self.value = max(0.0, self.value - amount)

    def get_zone(self) -> str:
        """Dominant zone name (highest Gaussian membership)."""
        memberships = self.zone_memberships()
        return max(memberships, key=memberships.__getitem__)

    def zone_memberships(self) -> dict[str, float]:
        """Gaussian memberships over the drive's configured zones. Values sum to 1.0."""
        import math
        raw = {z.name: math.exp(-0.5 * ((self.value - z.center) / z.width) ** 2) for z in (self.zones or [])}
        total = sum(raw.values()) or 1.0
        return {z: v / total for z, v in raw.items()}

    @property
    def aggregated_value(self) -> float:
        """If subdrives exist, return mean of their values; otherwise own value."""
        if self.subdrives:
            return sum(d.value for d in self.subdrives) / len(self.subdrives)
        return self.value

    def to_dict(self) -> dict:
        memberships = self.zone_memberships()
        result = {
            "value":       round(self.value, 4),
            "set_point":   self.set_point,
            "deviation":   round(self.deviation, 4),
            "urgency":     round(self.urgency, 4),
            "zone":        self.get_zone(),
            "memberships": {k: round(v, 4) for k, v in memberships.items()},
            "stratum":     self.stratum.value if self.stratum else None,
            "category":    self.category,
        }
        if self.observed:
            result["pressure"]         = self.pressure
            result["driving_variable"] = self.driving_variable
            result["observed"]         = [v.to_dict() for v in self.observed]
        if self.subdrives:
            result["subdrives"] = [d.to_dict() for d in self.subdrives]
        return result


class Drives:
    """Collection of stratified drives with factory methods."""

    def __init__(self, drives: Optional[list[Drive]] = None) -> None:
        self._drives: dict[str, Drive] = {}
        self._coupling: dict[str, dict[str, float]] = {}  # W: {src: {tgt: weight}}
        self._coupling_tau: int = 0  # delay in ticks for φ(x_{t-τ})
        if drives:
            for d in drives:
                self._drives[d.name] = d

    def set_coupling(self, matrix: dict[str, dict[str, float]], tau: int = 0) -> None:
        """Set coupling matrix W where W[src][tgt] = weight, with optional delay tau."""
        self._coupling = matrix
        self._coupling_tau = tau

    @classmethod
    def stratified(cls, subset: Optional[list[str]] = None) -> "Drives":
        """Create all 10 canonical drives (or a named subset).

        Satisfaction convention (x = satisfaction level, deficit = low x):
        metabolic is the canonical PULL drive — basal drift "recover"
        (λ>0: slack replenishes when idle, work drains it). All others are
        PUSH drives with basal drift "decay" (λ<0: satisfaction decays under
        neglect — the need re-emerges).
        Non-metabolic drives use conservative defaults; their |λ| is small
        since MVP2+ will tune them properly.
        """
        all_drives: list[Drive] = [
            # S1 Material — active MVP1, canonical pull
            Drive(
                name="metabolic",
                stratum=Stratum.MATERIAL,
                category="pull",
                basal_direction="recover",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.005,
                satiation_rate=0.10,
                description="Resource economy: tokens, energy, latency, API cost",
            ),
            # S3 Biological — MVP2+, push (satisfaction decays under neglect)
            Drive(
                name="safety",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.003,
                satiation_rate=0.15,
                description="Integrity: error-avoidance, alignment, harm prevention",
            ),
            Drive(
                name="epistemic",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.002,
                satiation_rate=0.20,
                description="Curiosity: uncertainty reduction, information seeking",
            ),
            Drive(
                name="coherence",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.002,
                satiation_rate=0.20,
                description="Narrative integrity: contextual integration, consistency",
            ),
            Drive(
                name="competence",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.002,
                satiation_rate=0.25,
                description="Self-efficacy: mastery, skill development",
            ),
            # S4 Technical — MVP2+
            Drive(
                name="artifact_integrity",
                stratum=Stratum.TECHNICAL,
                category="push",
                basal_direction="decay",
                value=0.80,
                set_point=0.80,
                lambda_rate=0.001,
                satiation_rate=0.10,
                description="Cybersecurity/Safe AI: prompt-injection resistance, state integrity",
            ),
            Drive(
                name="niche_construction",
                stratum=Stratum.TECHNICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.002,
                satiation_rate=0.15,
                description="Creative capacity: modifying environment vs pure adaptation",
            ),
            # S5 Social — MVP3+
            Drive(
                name="relatedness",
                stratum=Stratum.SOCIAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.003,
                satiation_rate=0.25,
                description="Bonding: trust, reciprocity, social connection",
            ),
            Drive(
                name="autonomy",
                stratum=Stratum.SOCIAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.002,
                satiation_rate=0.15,
                description="Self-determination: agency with mutual respect",
            ),
            # S6 Technological — MVP3+
            Drive(
                name="meaning",
                stratum=Stratum.TECHNOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.001,
                satiation_rate=0.10,
                description="Purpose: alignment with cultural-technological values",
            ),
        ]

        if subset:
            all_drives = [d for d in all_drives if d.name in subset]

        return cls(all_drives)

    @classmethod
    def from_names(cls, names: list[str]) -> "Drives":
        """Create a subset of canonical drives by name."""
        return cls.stratified(subset=names)

    def add(self, drive: Drive) -> None:
        """Add a custom drive."""
        self._drives[drive.name] = drive

    def get(self, name: str) -> Optional[Drive]:
        """Get drive by name; returns None if absent."""
        return self._drives.get(name)

    def __getitem__(self, name: str) -> Drive:
        return self._drives[name]

    def __iter__(self):
        return iter(self._drives.values())

    def update_all(self, tick: int = 0) -> dict[str, list[tuple[str, str]]]:
        """Apply one pulse of basal drift to all drives. Returns zone transitions."""
        transitions: dict[str, list[tuple[str, str]]] = {}
        for name, drive in self._drives.items():
            coupling_term, sources = self._compute_coupling(name, tick)
            evts = drive.update(tick=tick, coupling=coupling_term,
                                coupling_sources=sources)
            if evts:
                transitions[name] = evts
        return transitions

    def _compute_coupling(self, target_name: str, tick: int) -> tuple[float, dict[str, float]]:
        """Compute Σ_j W_{j→target} · (x_j(t−τ) − x_j*) and per-source contributions."""
        total = 0.0
        sources: dict[str, float] = {}
        for src_name, weights in self._coupling.items():
            w = weights.get(target_name, 0.0)
            if w == 0.0:
                continue
            src_drive = self._drives.get(src_name)
            if src_drive is None:
                continue
            # Use delayed value if tau > 0 and history available
            if self._coupling_tau > 0 and len(src_drive._history) > self._coupling_tau:
                x_delayed = src_drive._history[-self._coupling_tau - 1][1]
            else:
                if self._coupling_tau > 0 and not getattr(src_drive, "_tau_warned", False):
                    import warnings
                    warnings.warn(
                        f"coupling_tau={self._coupling_tau} exceeds "
                        f"history of '{src_drive.name}' "
                        f"({len(src_drive._history)} ticks retained) — delay "
                        f"silently disabled, using current value. Raise "
                        f"src_drive.history_limit or lower coupling_tau.",
                        stacklevel=2,
                    )
                    src_drive._tau_warned = True
                x_delayed = src_drive.value
            contribution = w * (x_delayed - src_drive.set_point)
            sources[src_name] = round(contribution, 6)
            total += contribution
        return total, sources

    def check_viability_minimum(self) -> list[str]:
        """Spec §2.4: a minimally viable system needs ≥1 push and ≥1 pull need.

        Returns warnings for categories that are missing. If all needs are pull,
        the optimal policy is inaction — the healthy equilibrium must be a
        sustainable *rhythm*, not a level.
        """
        cats = {d.category for d in self._drives.values()}
        warnings = []
        if "push" not in cats:
            warnings.append("no 'push' need — nothing activates the agent")
        if "pull" not in cats:
            warnings.append("no 'pull' need — nothing inhibits consumption")
        return warnings

    def to_dict(self) -> dict[str, dict]:
        """Export drive states for prompts / serialization."""
        return {name: d.to_dict() for name, d in self._drives.items()}

    def by_stratum(self, stratum: Stratum) -> list[Drive]:
        """All drives at a given ontological level."""
        return [d for d in self._drives.values() if d.stratum == stratum]

    @property
    def all(self) -> dict[str, Drive]:
        """All drives as a dict (read-only view)."""
        return dict(self._drives)

    def get_dominant(self, n: int = 3) -> list[Drive]:
        """Top N drives by urgency (largest absolute deviation from set-point)."""
        return sorted(self._drives.values(), key=lambda d: d.urgency, reverse=True)[:n]
