"""Observed variables — level + pacing pressure over operational variables (EPA §4).

A need (Drive) does not look at its own level in a vacuum: it observes N
operational variables of the system. Each observed variable contributes two
signals, and both are necessary:

    level — where the variable is now, relative to its limit
    pace  — how fast it is moving, relative to the rate the contract tolerates

Kinds (the contract type determines how level and pace are computed):
    budget  — a budget consumed within a window, refilled when it closes
              (API spend, token quota). Violation: exhaust before window ends.
    floor   — a reserve that must not drop below a floor (free RAM, free disk).
              Violation: touch the floor.
    target  — something that must be reached within the window (deliverables).
              Violation: window ends without reaching it.
    band    — must stay inside a range, deficit and superavit both possible
              (temperature, queue size). Violation: exit on either side.

Sustainable pace is derived, not chosen:
    budget:  r_sust = remaining_budget / window_time_remaining
    floor:   r_sust = (value − floor) / window_time_remaining
    target:  r_req  = (goal − achieved) / window_time_remaining
    band:    computed per side with the matching formula

Aggregation (non-fungible resources → max by default):
    p_variable = max(p_level, p_pace)
    p_need     = max over all observed variables   (see Drive.observed)
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from .events import EventEmitter, ZONE_CHANGED, SENSOR_INVALID


class VariableKind(Enum):
    BUDGET = "budget"
    FLOOR  = "floor"
    TARGET = "target"
    BAND   = "band"


_EPS = 1e-9


# ── Rate estimation ───────────────────────────────────────────────────────────

@dataclass
class RateEstimator:
    """Estimates the signed rate of an observed variable.

    type:
        "window" — linear rate over a moving span of `span` time units
        "ewma"   — exponentially weighted moving average of per-sample rates
    """
    type:  str   = "window"      # "window" | "ewma"
    span:  float = 1.0           # window span (same time units as observations)
    alpha: float = 0.3           # EWMA smoothing factor

    def estimate(self, samples: list[tuple[float, float]], monotonic: bool) -> tuple[float, float]:
        """Return (rate, coverage).

        rate:     units of value per unit of time, signed. Positive means the
                  variable is increasing.
        coverage: fraction of the estimator window actually covered by samples
                  (0..1). 1.0 for EWMA once it has ≥2 samples.
        """
        if len(samples) < 2:
            return 0.0, 0.0
        if self.type == "ewma":
            rate = 0.0
            n = 0
            prev_t, prev_v = samples[0]
            for t, v in samples[1:]:
                dt = t - prev_t
                if dt > 0:
                    dv = v - prev_v
                    if monotonic and dv < 0:
                        dv = v  # source reset: count only the new accumulated value
                    r_inst = dv / dt
                    rate = self.alpha * r_inst + (1 - self.alpha) * rate
                    n += 1
                prev_t, prev_v = t, v
            return rate, 1.0 if n else 0.0
        # window estimator
        t_now  = samples[-1][0]
        cutoff = t_now - self.span
        win = [s for s in samples if s[0] >= cutoff]
        if len(win) < 2:
            return 0.0, 0.0
        dt = win[-1][0] - win[0][0]
        if dt <= 0:
            return 0.0, 0.0
        total = 0.0
        for (t0, v0), (t1, v1) in zip(win, win[1:]):
            dv = v1 - v0
            if monotonic and dv < 0:
                dv = v1  # source reset: the drop is a restart, not negative rate
            total += dv
        coverage = min(1.0, dt / self.span)
        return total / dt, coverage


# ── Pressure functions ────────────────────────────────────────────────────────

def _pressure_fn(name_or_fn) -> Callable[[float], float]:
    """Resolve a pressure function. Input: |z| ∈ [0,1). Output: pressure ≥ 0."""
    if callable(name_or_fn):
        return name_or_fn
    if name_or_fn == "barrier":
        return lambda z: min(abs(z), 0.999999) / (1.0 - min(abs(z), 0.999999))
    if name_or_fn == "linear":
        return lambda z: abs(z)
    if name_or_fn == "quadratic":
        return lambda z: z * z
    if name_or_fn == "logistic":
        return lambda z: 1.0 / (1.0 + math.exp(-10.0 * (abs(z) - 0.5)))
    raise ValueError(
        f"Unknown pressure_fn {name_or_fn!r}. "
        "Use 'barrier', 'linear', 'quadratic', 'logistic', or a callable."
    )


# ── ObservedVariable ──────────────────────────────────────────────────────────

class ObservedVariable(EventEmitter):
    """One operational variable observed by a need, with level + pace pressure.

    Args follow the EPA §4.9 schema. Time is unitless — use any consistent unit
    (ticks, seconds, hours) as long as window/rates/staleness share it.
    """

    def __init__(
        self,
        name:             str,
        kind:             str | VariableKind,
        limit:            float | tuple[float, float],
        unit:             str             = "",
        set_point:        Optional[float] = None,
        window:           Optional[float] = None,   # window duration (same units as t)
        window_start:     float           = 0.0,    # when the current window opened
        pressure_fn:      str | Callable  = "barrier",
        pacing_mode:      str             = "ratio",  # "ratio" | "time_to_violation" | "none"
        recovery_time:    float           = 0.0,    # MEASURED, not chosen
        reaction_time:    float           = 0.0,
        rate_estimator:   Optional[dict]  = None,   # {"type": "window"|"ewma", ...}
        monotonic:        bool            = True,   # accumulated series
        max_staleness:    Optional[float] = None,
        valid_range:      tuple[Optional[float], Optional[float]] = (None, None),
        source:           str             = "",
        zone_thresholds:  tuple[float, float, float] = (0.15, 0.40, 0.70),
    ) -> None:
        self._init_bus()
        self.name = name
        self.kind = kind if isinstance(kind, VariableKind) else VariableKind(kind)
        self.unit = unit
        self.limit = limit
        self.set_point = set_point
        self.window = window
        self.window_start = window_start
        self._p_fn = _pressure_fn(pressure_fn)
        self.pacing_mode = pacing_mode
        self.recovery_time = recovery_time
        self.reaction_time = reaction_time
        est = rate_estimator or {"type": "window", "span": 1.0}
        self.rate_estimator = RateEstimator(
            type=est.get("type", "window"),
            span=est.get("span", est.get("hours", 1.0)),
            alpha=est.get("alpha", 0.3),
        )
        self.monotonic = monotonic
        self.max_staleness = max_staleness
        self.valid_range = valid_range
        self.source = source
        self.zone_thresholds = zone_thresholds

        self._samples: deque[tuple[float, float]] = deque(maxlen=10000)
        self.samples_dropped: int = 0          # count of evicted oldest samples
        self._drop_warned: bool = False        # warn once, then count silently
        self._last_zone: Optional[str] = None
        self._invalid_reason: Optional[str] = "no samples"
        # last computed state (for introspection)
        self.last_level_pressure: Optional[float] = None
        self.last_pace_pressure:  Optional[float] = None
        self.last_rate:           Optional[float] = None
        self.last_coverage:       float           = 0.0

    # ── Observation intake ─────────────────────────────────────────────────

    def observe(self, t: float, value: float) -> Optional[float]:
        """Feed a sample at time t. Returns the variable's pressure (None if invalid).

        Emits SensorInvalid on invalid input and ZoneChanged when the algedonic
        band of the pressure changes.
        """
        reason = self._validate(t, value)
        if reason is not None:
            self._set_invalid(reason, t)
            return None
        self._invalid_reason = None
        if self._samples.maxlen and len(self._samples) == self._samples.maxlen:
            self.samples_dropped += 1
            if not self._drop_warned:
                import warnings
                warnings.warn(
                    f"ObservedVariable '{self.name}' evicted its oldest sample "
                    f"(maxlen={self._samples.maxlen}) — long-window rate "
                    f"estimates are now windowed, not full-run.",
                    stacklevel=2,
                )
                self._drop_warned = True
        self._samples.append((float(t), float(value)))

        p_level = self.level_pressure()
        p_pace  = self.pace_pressure(t)
        self.last_level_pressure = p_level
        self.last_pace_pressure  = p_pace
        p = max(p for p in (p_level, p_pace) if p is not None) \
            if any(p is not None for p in (p_level, p_pace)) else 0.0
        self._check_zone(p, t, value)
        return p

    def _validate(self, t: float, value: float) -> Optional[str]:
        """Return an invalidity reason, or None if the sample is acceptable."""
        lo, hi = self.valid_range
        if lo is not None and value < lo:
            return f"value {value} below physical range ({lo})"
        if hi is not None and value > hi:
            return f"value {value} above physical range ({hi})"
        if self.max_staleness is not None and self._samples:
            t_last = self._samples[-1][0]
            if t - t_last > self.max_staleness:
                return f"stale: gap {t - t_last:.3f} > max_staleness {self.max_staleness}"
        return None

    def _set_invalid(self, reason: str, t: float) -> None:
        if reason == self._invalid_reason:
            return  # already flagged — don't spam SensorInvalid every pulse
        self._invalid_reason = reason
        self.emit(SENSOR_INVALID, {
            "variable": self.name,
            "reason":   reason,
            "t":        t,
            "source":   self.source,
        })

    def pressure(self, t: float) -> Optional[float]:
        """Recompute pressure from existing samples at time t (read-only poll).

        Used by the owning Drive each pulse. Re-checks staleness: a variable
        whose sensor stops reporting goes invalid and contributes no pressure —
        never assumed green.
        """
        if not self._samples:
            self._set_invalid("no samples", t)
            return None
        if self.max_staleness is not None:
            t_last = self._samples[-1][0]
            if t - t_last > self.max_staleness:
                self._set_invalid(
                    f"stale: {t - t_last:.3f} since last sample > {self.max_staleness}", t
                )
                return None
        self._invalid_reason = None
        p_level = self.level_pressure()
        p_pace  = self.pace_pressure(t)
        self.last_level_pressure = p_level
        self.last_pace_pressure  = p_pace
        vals = [p for p in (p_level, p_pace) if p is not None]
        p = max(vals) if vals else 0.0
        self._check_zone(p, t, self._samples[-1][1])
        return p

    @property
    def invalid_reason(self) -> Optional[str]:
        return self._invalid_reason

    @property
    def is_valid(self) -> bool:
        return self._invalid_reason is None

    # ── Normalized deviation z ─────────────────────────────────────────────

    def _limits(self) -> tuple[float, float]:
        """(lo, hi) bounds for the variable's contract."""
        if isinstance(self.limit, tuple):
            return self.limit
        if self.kind == VariableKind.FLOOR:
            return (self.limit, self.set_point if self.set_point is not None else self.limit + 1.0)
        # budget/target: lower bound is the origin (set_point or 0), upper is limit
        lo = self.set_point if self.set_point is not None else 0.0
        return (lo, self.limit)

    def _signed_deviation(self, x: float) -> float:
        """z ∈ ℝ: +1 at the deficit-side limit, −1 at the superavit-side limit.

        deficit  = moving toward violation (budget spent, floor reached,
                   target missed, band exited below set-point)
        superavit = moving away from violation on the comfortable side
        """
        lo, hi = self._limits()
        sp = self.set_point
        if self.kind == VariableKind.BAND:
            sp = sp if sp is not None else (lo + hi) / 2.0
            side_limit = hi if x >= sp else lo
            denom = (side_limit - sp) or _EPS
            return (x - sp) / denom
        if self.kind == VariableKind.FLOOR:
            sp = sp if sp is not None else hi
            denom = (sp - lo) or _EPS
            return (sp - x) / denom          # x → lo ⇒ z → +1
        if self.kind == VariableKind.TARGET:
            sp0 = self.set_point if self.set_point is not None else 0.0
            denom = (hi - sp0) or _EPS
            return (x - hi) / denom          # x → goal ⇒ z → 0; x=0 ⇒ z=−1
        # BUDGET: x = consumed, origin sp (default 0), limit = cap
        sp = sp if sp is not None else lo
        denom = (hi - sp) or _EPS
        return (x - sp) / denom

    @property
    def side(self) -> str:
        """Algedonic side of the last observation: 'deficit' | 'superavit' | 'equilibrium'."""
        if not self._samples:
            return "equilibrium"
        z = self._signed_deviation(self._samples[-1][1])
        if self.kind == VariableKind.TARGET:
            return "deficit" if z < -0.05 else "equilibrium"   # behind goal = deficit
        if z > 0.05:
            return "deficit"
        if z < -0.05:
            return "superavit"
        return "equilibrium"

    # ── Level pressure ─────────────────────────────────────────────────────

    def level_pressure(self) -> Optional[float]:
        """Barrier pressure of the current level toward the limit (spec §4.3).

            z = (x − x*) / (L − x*);   p = |z| / (1 − |z|)

        For `target`, level pressure is the linear remaining fraction — the
        violation is temporal (missing the deadline), so pacing carries it.
        """
        if not self._samples or self._invalid_reason:
            return None
        x = self._samples[-1][1]
        if self.kind == VariableKind.TARGET:
            _, hi = self._limits()
            x0 = self.set_point if self.set_point is not None else 0.0
            remaining = (hi - x) / ((hi - x0) or _EPS)
            return max(0.0, min(1.0, remaining))
        z = self._signed_deviation(x)
        if self.kind in (VariableKind.BUDGET, VariableKind.FLOOR):
            z = max(z, 0.0) if z > 0 else z   # keep sign for band-style readability
        return self._p_fn(min(abs(z), 0.999999))

    # ── Pace pressure ──────────────────────────────────────────────────────

    def window_time_remaining(self, t: float) -> Optional[float]:
        """Time left in the current contract window, or None if no window set."""
        if self.window is None:
            return None
        return max(0.0, (self.window_start + self.window) - t)

    def sustainable_rate(self, t: float) -> Optional[float]:
        """Tolerable/required rate derived from the contract (spec §4.4)."""
        if not self._samples:
            return None
        t_rem = self.window_time_remaining(t)
        if t_rem is None or t_rem <= 0:
            return None
        x = self._samples[-1][1]
        lo, hi = self._limits()
        if self.kind == VariableKind.BUDGET:
            return max(0.0, hi - x) / t_rem
        if self.kind == VariableKind.FLOOR:
            return max(0.0, x - lo) / t_rem
        if self.kind == VariableKind.TARGET:
            return max(0.0, hi - x) / t_rem          # required rate
        # BAND: margin to the nearer limit, per side
        sp = self.set_point if self.set_point is not None else (lo + hi) / 2.0
        if x >= sp:
            return max(0.0, hi - x) / t_rem
        return max(0.0, x - lo) / t_rem

    def pace_pressure(self, t: float) -> Optional[float]:
        """Pacing pressure (spec §4.5). None when pacing cannot be computed."""
        if self.pacing_mode == "none" or not self._samples or self._invalid_reason:
            return None
        r_obs, coverage = self.rate_estimator.estimate(list(self._samples), self.monotonic)
        self.last_rate     = r_obs
        self.last_coverage = coverage
        r_sust = self.sustainable_rate(t)
        if r_sust is None or r_sust <= 0:
            return None
        x = self._samples[-1][1]

        if self.pacing_mode == "ratio":
            if self.kind == VariableKind.TARGET:
                return max(0.0, 1.0 - r_obs / r_sust)
            # budget/floor/band: moving toward the limit too fast
            toward = self._rate_toward_limit(r_obs, x)
            return max(0.0, abs(toward) / r_sust - 1.0)

        if self.pacing_mode == "time_to_violation":
            tau = self._time_to_violation(t, x, r_obs, r_sust)
            if tau is None:
                return None
            t_correct = self.recovery_time + self.reaction_time
            if t_correct <= 0:
                return 0.0
            return max(0.0, min(1.0, 1.0 - tau / t_correct))

        raise ValueError(f"Unknown pacing_mode {self.pacing_mode!r}")

    def _rate_toward_limit(self, r_obs: float, x: float) -> float:
        """Signed rate component moving the variable toward violation."""
        if self.kind == VariableKind.BUDGET:
            return r_obs                    # spending ↑ is toward cap
        if self.kind == VariableKind.FLOOR:
            return -r_obs                   # free ↓ is toward floor
        if self.kind == VariableKind.BAND:
            sp = self.set_point if self.set_point is not None else sum(self._limits()) / 2.0
            return r_obs if x >= sp else -r_obs
        return r_obs                        # TARGET handled by ratio branch

    def _time_to_violation(self, t: float, x: float, r_obs: float,
                           r_sust: float) -> Optional[float]:
        """τ — time until violation at the current net rate (spec §4.5)."""
        t_rem = self.window_time_remaining(t)
        if self.kind == VariableKind.TARGET:
            # slack = window remaining − time needed to finish at current rate
            _, hi = self._limits()
            remaining_work = max(0.0, hi - x)
            t_needed = remaining_work / max(_EPS, r_obs) if r_obs > 0 else math.inf
            if t_rem is None:
                return None
            return t_rem - t_needed
        # margin to the limit / net rate toward it
        lo, hi = self._limits()
        if self.kind == VariableKind.BUDGET:
            margin = hi - x
        elif self.kind == VariableKind.FLOOR:
            margin = x - lo
        else:  # BAND
            margin = (hi - x) if x >= (self.set_point or (lo + hi) / 2) else (x - lo)
        net = self._rate_toward_limit(r_obs, x)
        if net <= 0:
            return math.inf                 # moving away from the limit
        return margin / max(_EPS, net)

    # ── Zone mapping ───────────────────────────────────────────────────────

    def pressure_zone(self, p: float) -> str:
        """Map pressure magnitude to a canonical algedonic zone name."""
        side = self.side
        if side == "equilibrium" and p < self.zone_thresholds[0]:
            return "equilibrium"
        suffix = "deficit" if side == "deficit" else "superavit"
        lo, mid, hi = self.zone_thresholds
        if p >= hi:
            return f"critical_{suffix}"
        if p >= mid:
            return f"high_{suffix}"
        if p >= lo:
            return f"moderate_{suffix}"
        return "equilibrium"

    def _check_zone(self, p: float, t: float, value: float) -> None:
        zone = self.pressure_zone(p)
        if zone != self._last_zone:
            self.emit(ZONE_CHANGED, {
                "variable":   self.name,
                "prev_zone":  self._last_zone,
                "zone":       zone,
                "side":       self.side,
                "pressure":   round(p, 4),
                "value":      value,
                "t":          t,
            })
            self._last_zone = zone

    @property
    def zone(self) -> Optional[str]:
        return self._last_zone

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":           self.name,
            "kind":           self.kind.value,
            "unit":           self.unit,
            "zone":           self._last_zone,
            "side":           self.side,
            "valid":          self.is_valid,
            "invalid_reason": self._invalid_reason,
            "level_pressure": self.last_level_pressure,
            "pace_pressure":  self.last_pace_pressure,
            "rate":           self.last_rate,
            "coverage":       self.last_coverage,
            "n_samples":      len(self._samples),
            "source":         self.source,
        }


# ── Viability contract loader (spec §4.10) ────────────────────────────────────

def load_contract(path: str | Path) -> list[ObservedVariable]:
    """Load a viability-contract.json into ObservedVariable instances.

    Expected schema per variable:
        {
          "name": "gasto_api", "kind": "budget", "unit": "USD",
          "limit": 150.0, "window": 11.5, "pressure_fn": "barrier",
          "pacing_mode": "time_to_violation",
          "recovery_time": 0.5, "reaction_time": 0.1,
          "rate_estimator": {"type": "window", "span": 1.0},
          "monotonic": true, "max_staleness": 0.25,
          "valid_range": [0, null], "source": "dashboard.billed",
          "provenance": "measurement" | "contract" | "assumption"
        }
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    specs = data.get("variables", data if isinstance(data, list) else [])
    out: list[ObservedVariable] = []
    for s in specs:
        rng = s.get("valid_range", (None, None))
        out.append(ObservedVariable(
            name=s["name"],
            kind=s["kind"],
            limit=tuple(s["limit"]) if isinstance(s["limit"], list) else s["limit"],
            unit=s.get("unit", ""),
            set_point=s.get("set_point"),
            window=s.get("window"),
            window_start=s.get("window_start", 0.0),
            pressure_fn=s.get("pressure_fn", "barrier"),
            pacing_mode=s.get("pacing_mode", "ratio"),
            recovery_time=s.get("recovery_time", s.get("recovery_time_h", 0.0)),
            reaction_time=s.get("reaction_time", s.get("reaction_time_h", 0.0)),
            rate_estimator=s.get("rate_estimator"),
            monotonic=s.get("monotonic", True),
            max_staleness=s.get("max_staleness", s.get("max_staleness_min")),
            valid_range=(rng[0], rng[1]) if rng else (None, None),
            source=s.get("source", ""),
        ))
    return out
