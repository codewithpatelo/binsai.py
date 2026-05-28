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
from typing import Optional


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

    # Internal: not part of public API
    _history: list[tuple[int, float]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.value     = float(self.value)
        self.set_point = float(self.set_point)
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Drive value must be in [0,1], got {self.value}")
        if not 0.0 <= self.set_point <= 1.0:
            raise ValueError(f"Set point must be in [0,1], got {self.set_point}")

    @property
    def deviation(self) -> float:
        """Signed deviation from set-point (positive = above ε = more deficit)."""
        return self.value - self.set_point

    @property
    def urgency(self) -> float:
        """Absolute urgency: 0 at set-point, 1 at maximum deviation."""
        return abs(self.deviation)

    def update(self, tick: int = 0) -> None:
        """Apply autonomous terms: elastic return to ε + basal drift λ.

            x_{t+1} = x_t − κ·(x_t − ε) + λ

        Without action feedback, the drive returns toward set-point at rate κ
        and drifts upward at λ (basal metabolic cost). Equilibrium under no
        action: x* = ε + λ/κ  (≈0.40 with default κ=0.05, λ=0.005).
        """
        elastic = -self.kappa * (self.value - self.set_point)
        self.value = max(0.0, min(1.0, self.value + elastic + self.lambda_rate))
        self._history.append((tick, self.value))
        if len(self._history) > 500:
            self._history = self._history[-500:]

    def satiate(self, amount: float) -> None:
        """Lower δ by amount * satiation_rate (resource gain / task completion)."""
        self.value = max(0.0, self.value - amount * self.satiation_rate)

    def deplete(self, amount: float) -> None:
        """Raise δ by amount (resource consumed: tokens spent, error incurred)."""
        self.value = min(1.0, self.value + amount)

    def get_zone(self) -> str:
        """Dominant zone name (highest Gaussian membership)."""
        from .fuzzy import zone_memberships as _zm
        memberships = _zm(self.value)
        return max(memberships, key=memberships.__getitem__)

    def zone_memberships(self) -> dict[str, float]:
        """Gaussian memberships over 5 zones. Values sum to 1.0."""
        from .fuzzy import zone_memberships as _zm
        return _zm(self.value)

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
        if drives:
            for d in drives:
                self._drives[d.name] = d

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

    def update_all(self, tick: int = 0) -> None:
        """Apply one tick of basal decay to all drives."""
        for drive in self._drives.values():
            drive.update(tick=tick)

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
