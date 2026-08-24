"""Stratified drives — Bunge-Romero ontological levels.

Semantics (HRRL convention — Keramati-Gutkin 2014; Driveplexity):
    δ ∈ [0, 1]  |  HIGH = deficit = urgency  |  LOW = abundance / oversated
    set_point (ε) is the homeostatic target (nominal zone center ≈ 0.30).

    deplete(amount)  → raises δ  (resource consumed: tokens spent, cost incurred)
    satiate(amount)  → lowers δ  (resource gained: task completed, consolidation)
    update()         → raises δ by λ per tick (basal metabolic cost of being active)

10 canonical drives across 6 Bunge-Romero strata.
Only δ_metabolic (S1) is active in MVP1; the rest are defined for MVP2+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


@dataclass
class ZoneSpec:
    """A named fuzzy zone with center and width (Gaussian σ)."""
    name:   str
    center: float
    width:  float = 0.12


class Stratum(Enum):
    """Bunge-Romero ontological levels."""
    MATERIAL       = "material"        # S1
    CHEMICAL       = "chemical"        # S2 (empty for AI)
    BIOLOGICAL     = "biological"      # S3
    TECHNICAL      = "technical"       # S4
    SOCIAL         = "social"          # S5
    TECHNOLOGICAL  = "technological"   # S6 (Romero extension)


@dataclass
class Drive:
    """A homeostatic drive with bilateral set-point regulation.

    Discrete-time dynamics (one tick), aligned with Γ master equation:
        x_{t+1} = x_t − κ(x_t − ε) + λ − α·ρ(action, env) + W·φ(x_{t-τ})

    update() applies the autonomous terms (elastic return + basal drift).
    satiate() / deplete() apply the action-feedback term −α·ρ.
    Coupling W·φ is reserved for MVP2+ (multiple drives).

    Attributes:
        name:           Drive identifier
        stratum:        Ontological level (Bunge-Romero)
        value:          Current δ ∈ [0, 1]  (high = deficit)
        set_point:      Homeostatic target ε
        kappa:          Elastic return rate (Γ-κ); larger = stiffer thermostat
        lambda_rate:    Basal drift per tick λ (added to δ each tick)
        satiation_rate: Multiplier applied in satiate()
        subdrives:      Child drives for recursive decomposition (e.g. metabolic → tokens, latency, cost)
        description:    Human-readable explanation
    """
    name:           str
    stratum:        Stratum
    value:          float = 0.30
    set_point:      float = 0.30
    kappa:          float = 0.05
    lambda_rate:    float = 0.005
    satiation_rate: float = 0.10
    subdrives:      list["Drive"] = field(default_factory=list)
    description:    str   = ""
    drift:          str   = "constant"  # "constant" | "linear" | "exponential" | "circadian" | callable
    drift_period:   int   = 120        # circadian period in ticks
    drift_k:        float = 1.0        # exponential drift coefficient
    satiation:      str   = "linear"   # "linear" | "saturating" | "sigmoid" | callable
    zones:          Optional[list[ZoneSpec]] = None  # None = default 5 zones

    # Internal: not part of public API
    _history: list[tuple[int, float]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.value     = float(self.value)
        self.set_point = float(self.set_point)
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Drive value must be in [0,1], got {self.value}")
        if not 0.0 <= self.set_point <= 1.0:
            raise ValueError(f"Set point must be in [0,1], got {self.set_point}")
        # Resolve drift to callable if it's a named policy
        if isinstance(self.drift, str):
            self._drift_fn = self._resolve_drift(self.drift)
        else:
            self._drift_fn = self.drift
        # Resolve satiation to callable if it's a named policy
        if isinstance(self.satiation, str):
            self._satiation_fn = self._resolve_satiation(self.satiation)
        else:
            self._satiation_fn = self.satiation
        # Default zones if none provided — 7 interpretable bands
        # Low δ = superavit (abundance), high δ = deficit (scarcity)
        if self.zones is None:
            self.zones = [
                ZoneSpec("critical_superavit",   0.05, 0.08),
                ZoneSpec("high_superavit",       0.13, 0.08),
                ZoneSpec("moderate_superavit",   0.22, 0.08),
                ZoneSpec("equilibrium",          0.30, 0.08),
                ZoneSpec("moderate_deficit",     0.40, 0.08),
                ZoneSpec("high_deficit",         0.55, 0.10),
                ZoneSpec("critical_deficit",     0.80, 0.12),
            ]
        self._last_zone = None  # Force first update() to emit zone.enter

    @staticmethod
    def _resolve_drift(name: str):
        import math
        if name == "constant":
            return lambda v, s, t, lam, k: lam
        elif name == "linear":
            return lambda v, s, t, lam, k: lam * (1.0 + max(0.0, (v - s) / max(0.01, s)))
        elif name == "exponential":
            return lambda v, s, t, lam, k: lam * math.exp(k * max(0.0, v - s))
        elif name == "circadian":
            # oscillatory: peaks during "day", trough during "night"
            period = 120  # default, overridden by drift_period
            return lambda v, s, t, lam, k: lam * (1.0 + math.sin(2 * math.pi * t / period)) / 2.0
        else:
            raise ValueError(f"Unknown drift policy: {name!r}. Use 'constant', 'linear', 'exponential', 'circadian', or a callable.")

    @property
    def deviation(self) -> float:
        """Signed deviation from set-point (positive = above ε = more deficit)."""
        return self.value - self.set_point

    @property
    def urgency(self) -> float:
        """Absolute urgency: 0 at set-point, 1 at maximum deviation."""
        return abs(self.deviation)

    def update(self, tick: int = 0, coupling: float = 0.0) -> list[tuple[str, str]] | None:
        """Apply autonomous terms: elastic return to ε + drift + coupling.

            x_{t+1} = x_t − κ·(x_t − ε) + drift(value, set_point, tick) + W·φ(x_{t-τ})

        Returns a list of zone transition events if the dominant zone changed,
        otherwise None. Each event is (event_type, zone_name) e.g.
        ("zone.enter", "critical"), ("zone.exit", "nominal").
        The caller (agent) is responsible for emitting these as events.
        """
        old_zone = self._last_zone
        elastic = -self.kappa * (self.value - self.set_point)
        drift_amount = self._drift_fn(self.value, self.set_point, tick, self.lambda_rate, self.drift_k)
        self.value = max(0.0, min(1.0, self.value + elastic + drift_amount + coupling))
        self._history.append((tick, self.value))
        if len(self._history) > 500:
            self._history = self._history[-500:]
        new_zone = self.get_zone()
        self._last_zone = new_zone
        if old_zone is None:
            # First update — emit initial zone entry
            return [("zone.enter", new_zone)]
        if old_zone != new_zone:
            return [("zone.exit", old_zone), ("zone.enter", new_zone)]
        return None

    @staticmethod
    def _resolve_satiation(name: str):
        import math
        if name == "linear":
            return lambda v, a, r: a * r
        elif name == "saturating":
            # diminishing returns: large amounts give less per-unit benefit
            return lambda v, a, r: r * (1.0 - math.exp(-a))
        elif name == "sigmoid":
            # steepest near set-point, gentle at extremes
            return lambda v, a, r: r * a / (1.0 + abs(v - 0.30) * 5.0)
        else:
            raise ValueError(f"Unknown satiation policy: {name!r}. Use 'linear', 'saturating', 'sigmoid', or a callable.")

    def satiate(self, amount: float) -> None:
        """Lower δ using the configured satiation function g.

        Linear (default): value -= amount * satiation_rate
        Saturating: diminishing returns for large amounts
        Sigmoid: strongest effect near set-point
        """
        reduction = self._satiation_fn(self.value, amount, self.satiation_rate)
        self.value = max(0.0, self.value - reduction)

    def deplete(self, amount: float) -> None:
        """Raise δ by amount (resource consumed: tokens spent, error incurred)."""
        self.value = min(1.0, self.value + amount)

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
            "stratum":     self.stratum.value,
        }
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

        All drives use the new high=deficit semantics.
        Non-metabolic drives use conservative defaults; their λ is small
        since MVP2+ will tune them properly.
        """
        all_drives: list[Drive] = [
            # S1 Material — active MVP1
            Drive(
                name="metabolic",
                stratum=Stratum.MATERIAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.005,
                satiation_rate=0.10,
                description="Resource economy: tokens, energy, latency, API cost",
            ),
            # S3 Biological — MVP2+
            Drive(
                name="safety",
                stratum=Stratum.BIOLOGICAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.003,
                satiation_rate=0.15,
                description="Integrity: error-avoidance, alignment, harm prevention",
            ),
            Drive(
                name="epistemic",
                stratum=Stratum.BIOLOGICAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.002,
                satiation_rate=0.20,
                description="Curiosity: uncertainty reduction, information seeking",
            ),
            Drive(
                name="coherence",
                stratum=Stratum.BIOLOGICAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.002,
                satiation_rate=0.20,
                description="Narrative integrity: contextual integration, consistency",
            ),
            Drive(
                name="competence",
                stratum=Stratum.BIOLOGICAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.002,
                satiation_rate=0.25,
                description="Self-efficacy: mastery, skill development",
            ),
            # S4 Technical — MVP2+
            Drive(
                name="artifact_integrity",
                stratum=Stratum.TECHNICAL,
                value=0.20,
                set_point=0.20,
                lambda_rate=0.001,
                satiation_rate=0.10,
                description="Cybersecurity/Safe AI: prompt-injection resistance, state integrity",
            ),
            Drive(
                name="niche_construction",
                stratum=Stratum.TECHNICAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.002,
                satiation_rate=0.15,
                description="Creative capacity: modifying environment vs pure adaptation",
            ),
            # S5 Social — MVP3+
            Drive(
                name="relatedness",
                stratum=Stratum.SOCIAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.003,
                satiation_rate=0.25,
                description="Bonding: trust, reciprocity, social connection",
            ),
            Drive(
                name="autonomy",
                stratum=Stratum.SOCIAL,
                value=0.30,
                set_point=0.30,
                lambda_rate=0.002,
                satiation_rate=0.15,
                description="Self-determination: agency with mutual respect",
            ),
            # S6 Technological — MVP3+
            Drive(
                name="meaning",
                stratum=Stratum.TECHNOLOGICAL,
                value=0.30,
                set_point=0.30,
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
        """Apply one tick of basal decay to all drives. Returns zone transitions per drive."""
        transitions: dict[str, list[tuple[str, str]]] = {}
        for name, drive in self._drives.items():
            coupling_term = self._compute_coupling(name, tick)
            evts = drive.update(tick=tick, coupling=coupling_term)
            if evts:
                transitions[name] = evts
        return transitions

    def _compute_coupling(self, target_name: str, tick: int) -> float:
        """Compute Σ_j W_{j→target} · φ(x_j(t−τ)) for the coupling term."""
        total = 0.0
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
                x_delayed = src_drive.value
            # φ = sigmoid-squared (from AAH-A2 / Driveplexity)
            phi = (x_delayed / (1.0 + abs(x_delayed))) ** 2
            total += w * phi
        return total

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
