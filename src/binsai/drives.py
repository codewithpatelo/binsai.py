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
    VIABILITY_BREACHED, TENSION_RELEASED, PERTURBED, DRIVE_SATURATED, G_MEASURED,
)


@dataclass
class ZoneSpec:
    """A named fuzzy algedonic zone with center and width (Gaussian σ)."""
    name:   str
    center: float
    width:  float = 0.12


@dataclass
class PerturbationEnvelope:
    """ADSR — what a perturbation event carries (v2.1 §1).

    ADS belongs to the world, R belongs to the agent. The world never closes
    an event: only a corrective action does, with its measured grade g.

    Magnitudes (`iota`) are fractions of the viability margin and arrive from
    the contract; the timings are fractions of the drive's regulation horizon,
    so one envelope describes a disk filling over a night and a queue backing
    up over a second.
    """
    rise:    float = 0.010          # time to the peak, fraction of the horizon
    decay:   float = 0.0015         # peak -> sustain time constant, idem
    release: float = 0.036          # fade-out once an action closed it, idem
    sustain_fraction: float = 0.25  # sustained level, as a fraction of the peak


@dataclass
class Perturbation:
    """One open event on a drive. It presses until an action closes it.

    `g` is the accumulated release grade (0 = untouched, 1 = closed): the
    measured quality of the corrective action, Δ_observed / Δ_expected, never
    a declaration. An action with g = 0 ran and satiated nothing, and the
    event keeps pressing at full strength — that is the satiation problem.
    """
    severity:  int
    direction: float                # the world's semantics, not the drive's side
    born_at:   int
    magnitude: float                # peak displacement, in drive units
    envelope:  PerturbationEnvelope
    horizon:   float
    source:    str = ""
    g:         float = 0.0
    closed_at: Optional[int] = None

    def level(self, tick: int) -> float:
        """Signed displacement this event contributes at `tick`."""
        import math
        s = tick - self.born_at
        if s < 0:
            return 0.0
        e, H = self.envelope, max(self.horizon, 1e-9)
        rise, decay = max(e.rise * H, 1e-9), max(e.decay * H, 1e-9)
        a = self.magnitude
        su = a * e.sustain_fraction
        v = a * (s / rise) if s < rise else su + (a - su) * math.exp(-(s - rise) / decay)
        if self.closed_at is not None:
            v *= max(0.0, 1.0 - (tick - self.closed_at) / max(e.release * H, 1e-9))
        return self.direction * v * (1.0 - self.g)

    @property
    def open(self) -> bool:
        return self.closed_at is None

    def expired(self, tick: int) -> bool:
        return (self.closed_at is not None
                and tick - self.closed_at > self.envelope.release * max(self.horizon, 1e-9))


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
    value:          Optional[float] = None  # None = contract initial condition x(t₀)=x*
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
    spring:         str   = "magnetic-2nd"  # "magnetic-2nd" (EPA v2, default)
    #                                       | "pulsatile" | "linear" | callable (legacy)
    spring_threshold: float = 0.10     # θ — pulsatile tension σ release pulse (legacy)
    spring_release: float = 1.0        # ρ — fraction of σ discharged per pulse (legacy)
    spring_reach:   float = 0.30       # w — grip peaks at |d|=w then decays (inf = no escape)

    # ── EPA v2 — second-order magnetic spring (docs/paov2.tex) ──
    velocity:       float = 0.0        # v — second component of the (x, v) state
    dt:             float = 1.0        # Δt — pulse duration
    damping:        float = 0.05       # c — brakes accumulated velocity (0 = undamped)
    spring_fatigue: float = 0.0        # f — allostatic wear: κ_ef = κ·e^(−f·Λ)
    allostatic_recovery: float = 0.01  # ρ_Λ — Λ recovery rate under rest
    drift_shape:    str   = "linear"   # φ(|d|): "linear"(=1) | "exponential" | "saturating"
    drift_gamma:    float = 1.0        # γ — exponential drift-shape coefficient
    drift_s:        float = 0.10       # s_i — saturating drift-shape scale
    eta:            float = 0.5        # η — velocity weight in autonomous pressure
    v_ref:          float = 0.10       # reference velocity for p_aut normalization
    zones:          Optional[list[ZoneSpec]] = None  # None = default 7 algedonic bands
    alpha_in:       float = 0.0        # hysteresis: μ needed to enter a new zone
    alpha_out:      float = 1.0        # hysteresis: exit old zone when μ ≤ this
    viability:      tuple[float, float] = (0.0, 1.0)  # viability limits
    observed:       list  = field(default_factory=list)  # list[ObservedVariable]
    history_limit:  int   = 0     # max ticks retained in .history.

    # ── EPA v2.1 (docs/paov2.1.md) — perturbation impulses, TTD, persistence ──
    impulse_iota:   tuple[float, float, float] = (0.02, 0.06, 0.18)  # ι₁ ι₂ ι₃ by crossing severity
    impulse_zeta:   float = 0.6    # ζ — improvement satiates less than worsening perturbs
    impulse_tau:    float = 2.0    # τ_u — decay kernel width, in ticks
    envelope:       "PerturbationEnvelope" = field(default_factory=lambda: PerturbationEnvelope())
    horizon:        float = 690.0  # regulation horizon, in ticks: what the envelope's
    #                                fractions are read against. Not a clock — a scale.
    persist_state:  Optional[bool] = None   # v2.1 §2.5 — does state carry between
    #                                     windows? Declared per drive, never implicit:
    #                                     True → the inherited (value, velocity) MUST be
    #                                     passed explicitly with state_origin saying
    #                                     when it comes from; False/None → reset x(t₀)=x*
    state_origin:   str   = ""     # e.g. "persisted from 2026-10-09 21:30, v0=−0.229"
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
    _allostatic:    float = field(default=0.0, repr=False)  # Λ — allostatic load
    _sustained:     dict[str, float] = field(default_factory=dict, repr=False)  # u stimuli
    _impulses:      list[tuple[int, float]] = field(default_factory=list, repr=False)  # (tick, a_imp)
    _open:          list["Perturbation"] = field(default_factory=list, repr=False)
    _seen:          list["Perturbation"] = field(default_factory=list, repr=False)
    _settled:       float = field(default=0.0, repr=False)  # envelope level already applied
    _saturated_at:  Optional[int] = field(default=None, repr=False)  # tick of entry into saturation
    _saturation_accum: float = field(default=0.0, repr=False)  # Σ ticks spent pinned at the wall

    def __post_init__(self) -> None:
        self._init_bus()
        # v2.1 §2.5 — persistence is DECLARED per drive, never implicit.
        # Nothing is inherited implicitly and nothing is reset implicitly:
        # a persisted drive must arrive with its inherited state and say
        # where it comes from; anything else starts at the set-point.
        self.set_point = float(self.set_point)
        if self.persist_state is True:
            if self.value is None:
                raise ValueError(
                    f"Drive '{self.name}' declares persist_state=True but no "
                    "inherited value — the contract must declare the state "
                    "it carries between windows (and state_origin must say "
                    "when it comes from)."
                )
            if not self.state_origin:
                import warnings
                warnings.warn(
                    f"Drive '{self.name}' persists state without a "
                    "state_origin — the prompt cannot say where it came "
                    "from or with what velocity it entered.",
                    stacklevel=2,
                )
        if self.value is None:
            self.value = self.set_point
        self.value     = float(self.value)
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
        # Resolve spring policy: "magnetic-2nd" (EPA v2 default), "linear"
        # (legacy damper), "pulsatile" (legacy integrate-and-release)
        if isinstance(self.spring, str):
            if self.spring not in ("magnetic-2nd", "linear", "pulsatile"):
                raise ValueError(
                    f"spring must be 'magnetic-2nd', 'pulsatile', 'linear' or a callable, "
                    f"got {self.spring!r}"
                )
            if self.spring == "magnetic-2nd":
                self._validate_magnetic_regime()
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

    # ── EPA v2 helpers ──────────────────────────────────────────────────────

    @staticmethod
    def design_spring_reach(kappa: float, lambda0: float,
                            d_star: float) -> float:
        """w design rule (paov2.tex §3): reach that places the no-return
        point at the desired d*.

            w = d* / ln(κ·d* / λ⁰)

        Valid only when κ·d*/λ⁰ > e (i.e. the resulting w < d*, so d* sits on
        the far branch of the grip curve and is the no-return point, not the
        near equilibrium root). Pick d* strictly inside the viable margin —
        at the margin the reach degenerates (see _validate_magnetic_regime).
        """
        import math
        lam0 = abs(lambda0)
        if lam0 == 0.0:
            raise ValueError("w-rule needs λ⁰ ≠ 0 — no drift, no escape regime")
        ratio = kappa * d_star / lam0
        if ratio <= math.e:
            raise ValueError(
                f"w-rule infeasible: κ·d*/λ⁰={ratio:.3f} ≤ e — a no-return "
                f"point at d*={d_star} is unreachable (the far branch needs "
                f"d* > w). Move d* further out or raise κ."
            )
        w = d_star / math.log(ratio)
        if w >= d_star:  # defensive: same condition, stated geometrically
            raise ValueError("w-rule gave w ≥ d* — d* would be the near root")
        return w

    @staticmethod
    def _lambert_w_minus1(z: float) -> float:
        """Lower (real) branch of Lambert W for z ∈ [−1/e, 0).

        Newton on w·e^w = z from the standard −1-branch asymptotic seed
        ln(−z) − ln(−ln(−z)). The package ships no scipy dependency.
        """
        import math
        if not (-1.0 / math.e <= z < 0.0):
            raise ValueError(f"Lambert W₋₁ domain is [−1/e, 0), got z={z}")
        w = math.log(-z) - math.log(-math.log(-z))
        for _ in range(50):
            ew = math.exp(w)
            f = w * ew - z
            denom = ew * (w + 1.0)
            w -= f / denom
            if abs(f) < 1e-14:
                break
        return w

    def _drift_phi(self, abs_d: float) -> float:
        """Basal-drift shape φ(|d|) — see paov2.tex §2.1."""
        import math
        if self.drift_shape == "linear":
            return 1.0
        if self.drift_shape == "exponential":
            return math.exp(self.drift_gamma * abs_d)
        if self.drift_shape == "saturating":
            return 1.0 - math.exp(-abs_d / self.drift_s)
        raise ValueError(
            f"drift_shape must be 'linear', 'exponential' or 'saturating', "
            f"got {self.drift_shape!r}"
        )

    def no_return_point(self) -> Optional[float]:
        """d* — the no-return deviation of the magnetic spring (paov2 eq. d*).

        Far root of κ·d·e^(−d/w) = |λ⁰|, closed form via Lambert W₋₁:
            d* = −w · W₋₁(−|λ⁰| / (κ·w))
        None when the drift dominates everywhere (G ≤ |λ⁰|): then no stable
        regime exists and every deviation escapes.
        """
        import math
        lam0 = abs(self.lambda_rate)
        w = self.spring_reach
        if lam0 == 0.0 or w is None or w == float("inf") or w <= 0:
            return None
        grip = self.kappa * w / math.e      # G at Λ=0
        if grip <= lam0:
            return None                     # drift always wins — no d*
        return -w * self._lambert_w_minus1(-lam0 / (self.kappa * w))

    def _validate_magnetic_regime(self) -> None:
        """w design rule (paov2.tex §3): d* must land INSIDE the viable range.

        If the no-return point falls on or beyond the viability limit, finite
        reach does nothing — the spring degenerates to ever-growing grip.
        """
        import math, warnings
        lam0 = abs(self.lambda_rate)
        w = self.spring_reach
        if lam0 == 0.0 or w is None or w == float("inf"):
            return
        grip = self.kappa * w / math.e
        if grip <= lam0:
            warnings.warn(
                f"Drive '{self.name}': grip κw/e={grip:.4f} ≤ |λ⁰|={lam0:.4f} — "
                f"drift dominates everywhere, basal negligence always kills "
                f"(no stable regime). Raise κ·w or lower |λ⁰|.",
                stacklevel=3,
            )
            return
        d_star = self.no_return_point()
        # the side the basal drift pushes toward: decay → lo, recover → hi
        lo_v, hi_v = self.viability
        bound = lo_v if self.lambda_rate < 0 else hi_v
        margin = abs(bound - self.set_point)
        if d_star is not None and d_star >= margin:
            warnings.warn(
                f"Drive '{self.name}': no-return point d*={d_star:.3f} ≥ viable "
                f"margin {margin:.3f} (|{bound} − x*|={self.set_point}) — finite "
                f"reach never acts inside the viable range; the spring "
                f"degenerates to ever-growing grip. Lower w per the w-rule "
                f"(docs/SPRING.md §4d).",
                stacklevel=3,
            )

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

    def _update_second_order(self, tick: int, coupling: float) -> None:
        """EPA v2 dynamics (docs/paov2.tex): state (x, v), acceleration

            a = λ(x,t) − S(x,t) − c·v + u + Σ_j W_ij·(x_j − x*_j)

        with the fatigable magnetic spring

            S = κ_ef·d·e^(−|d|/w),   κ_ef = κ·e^(−f·Λ),
            Λ' = |d| − ρ_Λ·Λ        (allostatic load)

        Sustained stimuli enter `a` via `u` (see sustain()); impulsive
        stimuli jump x directly via impulse(). The basal drift is
        σ·λ⁰·φ(|d|) — it applies every pulse, stimuli or not.
        """
        import math
        d = self.value - self.set_point
        # allostatic load: accumulates exposure to |d|, recovers with rest
        self._allostatic += (abs(d) - self.allostatic_recovery
                             * self._allostatic) * self.dt
        self._allostatic = max(0.0, self._allostatic)
        k_eff = self.kappa * math.exp(-self.spring_fatigue * self._allostatic)
        lam = self.lambda_rate * self._drift_phi(abs(d))
        # v2.1 §1 — u(t) = sustained stimuli + decaying event impulses:
        #   u = Σ_k ι_k·ψ(t − t_k),  ψ(s) = e^(−s/τ_u)
        # An impulse is a blow, not a step: the acceleration channel charges
        # v with the memory of the hit, and the spring has to fight acquired
        # velocity — the second order exists for exactly this.
        u = sum(self._sustained.values())
        alive: list[tuple[int, float]] = []
        for tk, a_imp in self._impulses:
            s = (tick - tk) * self.dt
            if s < 0:
                alive.append((tk, a_imp))     # not yet active (declared early)
                continue
            decay = math.exp(-s / max(self.impulse_tau, 1e-9))
            if decay < 1e-3:
                continue                      # impulse exhausted
            alive.append((tk, a_imp))
            u += a_imp * decay
        self._impulses = alive

        # Semi-implicit Euler is unstable for ω·h ≳ 2 (ω ≈ √κ). Subdivide
        # the tick so each substep stays inside the stable region — dt is
        # the pulse length callers see; h is the integration step.
        omega = math.sqrt(k_eff) if k_eff > 0 else 0.0
        n_sub = max(1, math.ceil(omega * self.dt / 0.5)) if omega else 1
        h = self.dt / n_sub
        w = self.spring_reach
        finite = w is not None and w != float("inf")
        for _ in range(n_sub):
            d = self.value - self.set_point
            S = k_eff * d * math.exp(-abs(d) / w) if finite else k_eff * d
            a = lam - S - self.damping * self.velocity + u + coupling
            self.velocity += a * h
            x_new = self.value + self.velocity * h
            if x_new > 1.0:
                # inelastic wall: hitting the clip dissipates outward velocity
                x_new = 1.0
                self.velocity = min(0.0, self.velocity)
            elif x_new < 0.0:
                x_new = 0.0
                self.velocity = max(0.0, self.velocity)
            self.value = x_new

    # ── Stimuli: two channels (paov2.tex §2.3) ───────────────────────────────

    def sustain(self, name: str, alpha: float) -> None:
        """Register a sustained stimulus contributing alpha to u (acceleration
        channel). Call again with the same name to update; use
        :meth:`release_stimulus` to stop it."""
        self._sustained[name] = float(alpha)

    def release_stimulus(self, name: str) -> None:
        self._sustained.pop(name, None)

    def impulse(self, delta: float, expected: Optional[float] = None) -> float:
        """Impulsive stimulus: instant level jump x ← x + Δ.

        Returns the quality signal g = Δ_observed / Δ_expected — what actually
        happened vs what the model predicted. A stimulus can execute and
        satiate nothing (g=0); that is where the satiation problem lives.
        """
        before = self.value
        self.value = max(0.0, min(1.0, self.value + delta))
        observed = self.value - before
        g = (observed / expected) if expected else 1.0
        self.emit(SATIATED, {
            "drive":     self.name,
            "delta":     round(delta, 6),
            "observed":  round(observed, 6),
            "expected":  expected,
            "g":         round(g, 4) if expected else None,
        })
        return g

    def apply_impulse(self, tick: int, magnitude: float, toward: bool = False) -> None:
        """v2.1 §1 — inject a decaying impulse into the acceleration channel.

        An event impulse is a blow, not a step: it enters `a`, charges `v`
        with the memory of the hit, and decays with kernel ψ(s)=e^(−s/τ_u).
        `toward=True` satiates (ι<0, pulls back to x*); `toward=False`
        perturbs (ι>0, pushes away). The sign resolves against the current
        side of the deviation, so the same declaration means the same thing
        in deficit and in superavit.
        """
        d = self.value - self.set_point
        sgn = -1.0 if d < 0 else 1.0
        a_imp = -magnitude * sgn if toward else magnitude * sgn
        self._impulses.append((int(tick), a_imp))
        self.emit(PERTURBED, {
            "drive":     self.name,
            "tick":      int(tick),
            "impulse":   round(magnitude if not toward else -magnitude, 6),
            "direction": "toward" if toward else "away",
            "a_imp":     round(a_imp, 6),
            "tau":       self.impulse_tau,
        })

    @property
    def impulses(self) -> list[tuple[int, float]]:
        """Active/last impulses as (tick, a_imp) — v2.1 §6 prompt material."""
        return list(self._impulses)

    # ── Saturation (v2.1 §2.4) ────────────────────────────────────────────

    @property
    def saturated(self) -> bool:
        """True while pinned at the viability wall (|d| ≥ |L − x*|)."""
        return self._saturated_at is not None

    @property
    def saturation_time(self) -> float:
        """Accumulated time pinned at the wall, in time units (tick·dt)."""
        total = self._saturation_accum
        if self._saturated_at is not None:
            total += (self._history[-1][0] - self._saturated_at) * self.dt \
                if self._history else 0.0
        return total

    # ── Ghost projection (v2.1 §4) ────────────────────────────────────────
    # TTD is a COUNTERFACTUAL INTEGRATION, not a slope fit: see
    # Drives.project_basal / Drives.time_to_death — the forward simulation
    # with u = 0, live coupling, and the allostatic load still integrating.

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
        if self.spring == "magnetic-2nd":
            import math
            if self.lambda_rate == 0:
                return self.set_point
            # fatigue f>0 means grip decays under sustained load → eventual
            # death by negligence even inside the stable regime
            lam0 = abs(self.lambda_rate)
            w = self.spring_reach
            grip = (self.kappa * w / math.e) if (w and w != float("inf")) else float("inf")
            bound = 1.0 if self.lambda_rate > 0 else 0.0
            if self.spring_fatigue > 0 or lam0 >= grip:
                return bound
            # stable regime: oscillates; centre ≈ balance λ⁰ ≈ κ·d·e^(−d/w)
            d_star = self.no_return_point()
            if d_star is None:
                return bound
            # the near root (oscillation centre) is the W0 branch
            z = -lam0 / (self.kappa * w)
            # W0 via Newton from seed -z
            wv = -z
            for _ in range(50):
                ew = math.exp(wv)
                f_ = wv * ew - z
                wv -= f_ / (ew * (wv + 1.0))
                if abs(f_) < 1e-14:
                    break
            d_eq = -w * wv
            return max(0.0, min(1.0, self.set_point + d_eq))
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

    @property
    def allostatic_load(self) -> float:
        """Λ — accumulated exposure to deviation (magnetic-2nd spring)."""
        return self._allostatic

    @property
    def kappa_eff(self) -> float:
        """κ_ef = κ·e^(−f·Λ) — grip after allostatic wear."""
        import math
        return self.kappa * math.exp(-self.spring_fatigue * self._allostatic)

    def pressure_components(self) -> dict:
        """Traceable split of what is pushing this drive right now (v2.1 §2).

        Every source returns a value in [0, 1] — the 2026-10-09 night had
        level = 1.934, which breaks any downstream aggregation. Sources:

            level:      min(1, |d| / |L − x*|)        — drive's own deviation,
                        L on the side the deviation points to (always calibrated)
            pace:       max over observed variables, min(1, p_pace)
                        (None = uncalibrated: no wired sensor has a pace signal)
            autonomous: min(1, η·|v| / v_ref)         — velocity fills the role
                        tension σ had in the pulsatile formulation

        An uncalibrated source is NOT zero — it is excluded from the max and
        reported in `uncalibrated`. Averaging a missing source in lowers the
        pressure by a third; that was the 0.465-with-a-dead-drive night.
        """
        d = self.value - self.set_point
        lo_v, hi_v = self.viability
        bound = lo_v if d < 0 else hi_v
        margin = abs(bound - self.set_point) or 1e-9
        level = min(1.0, abs(d) / margin)

        pace = None
        uncalibrated: list[str] = []
        for var in self.observed:
            pp = var.last_pace_pressure
            if pp is None:
                uncalibrated.append(var.name)
                continue
            pace = min(1.0, pp) if pace is None else max(pace, min(1.0, pp))
        if not self.observed:
            uncalibrated.append("pace")

        if self.spring == "magnetic-2nd":
            autonomous = min(1.0, self.eta * abs(self.velocity) / self.v_ref)
        else:
            autonomous = min(1.0, abs(self._tension))

        calibrated = [p for p in (level, pace, autonomous) if p is not None]
        pressure = max(calibrated) if calibrated else 0.0
        # v2.1 §2.4 — pinned at the wall the level carries no information
        # anymore: the pressure is 1 and the accumulated duration becomes
        # the informative variable (reported via saturation_time).
        saturated = abs(d) >= margin
        if saturated:
            pressure = 1.0
        return {"level": level, "pace": pace, "autonomous": autonomous,
                "tension": self._tension, "pressure": pressure,
                "saturated": saturated, "uncalibrated": uncalibrated}

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
        # The envelope presses on the level before the dynamics run, so the
        # spring sees the displacement this pulse and pulls against it.
        self._settle_perturbations(tick)
        if self.spring == "magnetic-2nd":
            self._update_second_order(tick, coupling)
        else:
            spring_delta = self._spring_step(tick)
            drift_amount = self._drift_fn(self.value, self.set_point, tick,
                                        self.lambda_rate, self.drift_k)
            self.value = max(0.0, min(1.0,
                                      self.value + spring_delta + drift_amount + coupling))
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

        # Observed variables: poll sensors so their level/pace pressures are
        # current for pressure_components() (max over valid sensors, §4.8).
        if self.observed:
            self._poll_observed(tick)
        # v2.1 §2 — pressure = max over CALIBRATED sources, conjunctive
        # saturation at the wall. An uncalibrated source is excluded, never 0.
        comps = self.pressure_components()
        self.pressure = comps["pressure"]

        # v2.1 §2.4 — saturation bookkeeping: the entry instant is an event,
        # the accumulated duration is an observed variable of its own right.
        d = self.value - self.set_point
        margin = abs((lo_v if d < 0 else hi_v) - self.set_point) or 1e-9
        if abs(d) >= margin:
            if self._saturated_at is None:
                self._saturated_at = tick
                self.emit(DRIVE_SATURATED, {
                    "drive":       self.name,
                    "tick":        tick,
                    "value":       round(self.value, 4),
                    "limit":       lo_v if d < 0 else hi_v,
                    "entered_at":  tick,
                })
        elif self._saturated_at is not None:
            self._saturation_accum += (tick - self._saturated_at) * self.dt
            self._saturated_at = None

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
        """Poll sensors so pressure_components() has current level/pace.

        The drive subscribes to each variable's Perturbed events once
        (v2.1 §1: the variable publishes, the drive subscribes, the drive
        never polls the variable for perturbations). `driving_variable` is
        the strongest calibrated sensor this tick.
        """
        best_p, best_var = None, None
        invalid: list[str] = []
        for var in self.observed:
            if not getattr(var, "_perturb_subscribed_drives", None):
                var._perturb_subscribed_drives = set()
            if id(self) not in var._perturb_subscribed_drives:
                var.on(PERTURBED, self._on_perturbation)
                var._perturb_subscribed_drives.add(id(self))
            p = var.pressure(tick)
            if p is None:
                invalid.append(var.name)
                continue
            if best_p is None or p > best_p:
                best_p, best_var = p, var.name
        self.driving_variable = best_var
        self.emit(PRESSURE_UPDATED, {
            "drive":             self.name,
            "pressure":          round(best_p, 4) if best_p is not None else None,
            "driving_variable":  best_var,
            "invalid_sensors":   invalid,
            "tick":              tick,
        })

    def _on_perturbation(self, payload: dict) -> None:
        """Receive a Perturbed event from an observed variable (v2.1 §1.5).

        The variable publishes; the drive subscribes and **opens an event**.
        It does not inject a scalar into the acceleration channel: a sustained
        term in `a` is integrated twice and accumulates without bound, so an
        unattended run collapses in a fraction of its horizon however the
        drive is tuned. The envelope presses on the level instead, where it is
        bounded and the magnetic spring can fight it.

        The variable speaks in time units (payload "t"); the drive converts to
        its own tick grid.
        """
        t_var = float(payload.get("t", payload.get("tick", 0.0)))
        tick = int(round(t_var / self.dt)) if self.dt else int(t_var)
        severity = int(payload.get("severity") or 0)
        if severity < 1:
            return
        toward = payload.get("direction") == "toward"
        margin = self._viability_margin()
        iota = self.impulse_iota[min(2, severity - 1)]
        magnitude = iota * margin * (self.impulse_zeta if toward else 1.0)
        if toward:
            # The world eased off. That relieves, but it does not close an
            # event: only an action does. It opens its own, mirrored.
            self.open_perturbation(tick, severity, -self._away_sign(),
                                   magnitude=magnitude,
                                   source=str(payload.get("variable", "")))
        else:
            self.open_perturbation(tick, severity, self._away_sign(),
                                   magnitude=magnitude,
                                   source=str(payload.get("variable", "")))

    def _viability_margin(self) -> float:
        lo, hi = self.viability
        return min(abs(self.set_point - lo), abs(hi - self.set_point)) or 1.0

    def _away_sign(self) -> float:
        d = self.value - self.set_point
        return -1.0 if d < 0 else 1.0

    # ── Typed perturbation and correction (v2.1 §1) ──────────────────────────

    def open_perturbation(self, tick: int, severity: int, direction: float,
                          magnitude: Optional[float] = None,
                          source: str = "") -> "Perturbation":
        """Open an ADSR event on this drive. The world's direction, not the drive's side."""
        import math
        if magnitude is None:
            magnitude = self.impulse_iota[min(2, max(1, severity) - 1)] * self._viability_margin()
        p = Perturbation(severity=int(severity), direction=math.copysign(1.0, direction),
                         born_at=int(tick), magnitude=float(magnitude),
                         envelope=self.envelope, horizon=self.horizon, source=source)
        self._open.append(p)
        self._seen.append(p)
        self.record_event(int(tick), "shock" if severity >= 3 else "pert")
        self.emit(PERTURBED, {
            "drive": self.name, "tick": int(tick), "severity": int(severity),
            "direction": "away" if p.direction == self._away_sign() else "toward",
            "magnitude": round(p.magnitude, 6), "source": source,
            "open_events": self.open_perturbations,
        })
        return p

    def correct(self, tick: int, g: float, source: str = "") -> int:
        """A corrective action of **measured** quality g. Returns events it closed.

        g = Δ_observed / Δ_expected, from :meth:`impulse` or from the action's
        declared ExpectedEffect. g = 0 closes nothing: the action ran and
        satiated nothing, and every event keeps pressing.
        """
        g = max(0.0, min(1.0, float(g)))
        closed = 0
        for p in self._open:
            if p.open:
                p.g = min(1.0, p.g + g * (1.0 - p.g))
                if p.g >= 0.98:
                    p.closed_at = int(tick)
                    closed += 1
        if closed:
            self.record_event(int(tick), "sat")
        self.emit(G_MEASURED, {
            "drive": self.name, "tick": int(tick), "g": round(g, 4),
            "closed": closed, "still_open": self.open_perturbations, "source": source,
        })
        return closed

    @property
    def perturbation_history(self) -> list["Perturbation"]:
        """Every event this drive has received, open or closed."""
        return list(self._seen)

    def measured_arrival_rate(self, horizon: Optional[float] = None) -> Optional[float]:
        """Events per horizon, **measured** from what this drive actually received.

        Returns None when the drive has not run long enough to measure: an
        arrival rate is an observation about the environment, not a setting,
        and guessing it silently decides the magnitude of every perturbation.
        """
        if not self._seen or not self._history:
            return None
        elapsed = (self._history[-1][0] - self._history[0][0]) * self.dt
        if elapsed <= 0:
            return None
        H = horizon if horizon is not None else self.horizon
        return len(self._seen) * H / elapsed

    @property
    def open_perturbations(self) -> int:
        """Events nobody has closed — the agent's outstanding debt."""
        return sum(1 for p in self._open if p.open)

    @property
    def perturbation_load(self) -> float:
        """Net displacement the open envelopes are pressing with, right now."""
        return self._settled

    def _settle_perturbations(self, tick: int) -> None:
        """Write this pulse's net envelope displacement onto the level channel."""
        self._open = [p for p in self._open if not p.expired(tick)]
        total = sum(p.level(tick) for p in self._open)
        delta = total - self._settled
        self._settled = total
        if delta:
            self.value = max(0.0, min(1.0, self.value + delta))

    # ── Calibration (EPA v2.1) ───────────────────────────────────────────────

    def calibrate(self, *, mortality: float, horizon: Optional[float] = None,
                  shape: Optional["ShapeRatios"] = None, apply: bool = True,
                  iterations: int = 60) -> "Calibration":
        """Tune **this** drive so basal negligence kills it at `mortality`.

        Everything else is read off the drive as it stands: its margin, its
        set-point, the sign of its drift, its clock. Nothing is invented and no
        parallel world is simulated — phase 2 integrates a copy of this very
        drive with u = 0, which is the v2.1 §4 counterfactual.

        Args:
            mortality: fraction of the horizon at which the drive dies with
                nobody acting. Below 1.0 or A4 does not hold.
            horizon:   defaults to the drive's own `horizon`.
            apply:     write the result back onto this drive (default). False
                       returns the calibration without touching it.

        Two acceptance tests must hold together, and `Calibration.sound` says
        whether they did:

            R0 = kappa*w/(e*|lambda0|) > 1   the spring holds -> regulating is possible
            TTD_basal < horizon              fatigue eats it  -> negligence kills (A4)
        """
        from .calibration import calibrate_drive
        return calibrate_drive(self, mortality=mortality, horizon=horizon,
                               shape=shape, apply=apply, iterations=iterations)

    def calibrate_perturbation(self, *, exploratory_budget: float,
                               arrivals_per_horizon: Optional[float] = None,
                               horizon: Optional[float] = None,
                               apply: bool = True, **kw) -> tuple[float, float, float]:
        """Size this drive's impulse magnitudes from the room the agent needs.

        `exploratory_budget` is the fraction of the horizon the drive survives
        while nobody closes any event — the room an agent has to act and be
        wrong, since every action that measures g = 0 is spent out of it.

        The arrival rate is **measured** from the events this drive has
        received unless you pass one. Only the product of arrivals and
        magnitude sets the budget, so an unmeasured rate silently decides the
        magnitude. With `apply=True` the result is written to `impulse_iota`.

        Returns the three magnitudes (iota1, iota2, iota3), as fractions of the
        viability margin.
        """
        from .calibration import calibrate_drive_perturbation
        return calibrate_drive_perturbation(
            self, exploratory_budget=exploratory_budget,
            arrivals_per_horizon=arrivals_per_horizon, horizon=horizon,
            apply=apply, **kw)

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

    def calibrate(self, *, mortality: float | dict[str, float],
                  horizon: Optional[float] = None, apply: bool = True,
                  **kw) -> dict[str, "Calibration"]:
        """Calibrate every drive in the collection, in place.

        `mortality` is either one fraction for all of them or a per-name dict.
        Push and pull drives rarely want the same date: the one that decays
        usually has to die earlier than the one that replenishes.
        """
        out: dict[str, "Calibration"] = {}
        for name, drive in self._drives.items():
            m = mortality[name] if isinstance(mortality, dict) else mortality
            out[name] = drive.calibrate(mortality=m, horizon=horizon, apply=apply, **kw)
        return out

    @property
    def pressure(self) -> float:
        """v2.1 §2.3 — conjunctive system pressure.

        The viable set K is the intersection of every contract: dying by one
        variable is dying. So the system pressure is the max over drives —
        never the mean, which would average a dead drive with a healthy one
        into lukewarmth (the 0.465-with-metabolic-at-the-wall night).
        """
        vals = [d.pressure for d in self._drives.values()
                if d.pressure is not None]
        return max(vals) if vals else 0.0

    def project_basal(self, horizon_ticks: int) -> dict[str, Optional[tuple[float, str]]]:
        """v2.1 §4 — basal TTD: integrate the system forward with u = 0.

        Counterfactual: nobody acts and nothing perturbs. The collection is
        copied, sustained stimuli and event impulses are zeroed on ALL
        drives, and the system integrates with live coupling. Per drive,
        returns (time to crossing, wall) or None when it does not cross
        within the horizon.

        No window, no line fit: it is well-defined AT the wall, and it
        tells a drive that is dying from one the spring recovers. The
        allostatic load keeps integrating during the projection, so
        accumulated fatigue brings the projected death closer.
        """
        import copy
        sim = Drives()
        for name, d in self._drives.items():
            c = copy.copy(d)                     # scalars copied
            c._history = list(d._history)        # projection appends: don't touch the original log
            c._events = list(d._events)
            c._sustained = {}
            c._impulses = []
            c.observed = []                      # u = 0: sensors don't move the dynamics
            # the copy must stay silent: its bus would otherwise call
            # handlers bound to the live agent and leak projection events
            c._bus_handlers = {}
            c._bus_any = {}
            c._bus_subs = {}
            sim._drives[name] = c
        sim._coupling = self._coupling           # shared read-only matrix
        sim._coupling_tau = self._coupling_tau
        out: dict[str, Optional[tuple[float, str]]] = {
            n: None for n in sim._drives}
        t0 = max((d._history[-1][0] if d._history else 0)
                 for d in sim._drives.values())
        for k in range(1, int(horizon_ticks) + 1):
            sim.update_all(tick=t0 + k)              # live coupling
            for name, d in sim._drives.items():
                if out[name] is not None:
                    continue
                lo, hi = d.viability
                if d.value >= hi - 1e-9:
                    out[name] = (k * d.dt, "upper")
                elif d.value <= lo + 1e-9:
                    out[name] = (k * d.dt, "lower")
            if all(v is not None for v in out.values()):
                break
        return out

    def time_to_death(self, horizon_ticks: int) -> Optional[float]:
        """v2.1 §4 — basal system TTD: the first crossing of any drive.

        None = no drive crosses within the horizon (∞ for this window). A
        drive at the wall that is dying gives ~0; one the spring recovers
        gives None. No saturation special-case is needed: the wall is part
        of the counterfactual integration, not a flag.
        """
        crossings = [v[0] for v in self.project_basal(horizon_ticks).values()
                     if v is not None]
        return min(crossings) if crossings else None

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
                lambda_rate=0.001,
                satiation_rate=0.10,
                kappa=0.10,
                damping=0.10, spring_fatigue=0.05,
                spring_reach=Drive.design_spring_reach(0.10, 0.001, 0.20),
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
                lambda_rate=0.001,
                satiation_rate=0.15,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.001, 0.30),
                description="Integrity: error-avoidance, alignment, harm prevention",
            ),
            Drive(
                name="epistemic",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.0006,
                satiation_rate=0.20,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.0006, 0.30),
                description="Curiosity: uncertainty reduction, information seeking",
            ),
            Drive(
                name="coherence",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.0006,
                satiation_rate=0.20,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.0006, 0.30),
                description="Narrative integrity: contextual integration, consistency",
            ),
            Drive(
                name="competence",
                stratum=Stratum.BIOLOGICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.0006,
                satiation_rate=0.25,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.0006, 0.30),
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
                lambda_rate=0.0004,
                satiation_rate=0.10,
                damping=0.10, spring_fatigue=0.08,
                spring_reach=Drive.design_spring_reach(0.05, 0.0004, 0.30),
                description="Cybersecurity/Safe AI: prompt-injection resistance, state integrity",
            ),
            Drive(
                name="niche_construction",
                stratum=Stratum.TECHNICAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.0006,
                satiation_rate=0.15,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.0006, 0.30),
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
                lambda_rate=0.001,
                satiation_rate=0.25,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.001, 0.30),
                description="Bonding: trust, reciprocity, social connection",
            ),
            Drive(
                name="autonomy",
                stratum=Stratum.SOCIAL,
                category="push",
                basal_direction="decay",
                value=0.70,
                set_point=0.70,
                lambda_rate=0.0006,
                satiation_rate=0.15,
                damping=0.10, spring_fatigue=0.10,
                spring_reach=Drive.design_spring_reach(0.05, 0.0006, 0.30),
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
                lambda_rate=0.0004,
                satiation_rate=0.10,
                damping=0.10, spring_fatigue=0.08,
                spring_reach=Drive.design_spring_reach(0.05, 0.0004, 0.30),
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
