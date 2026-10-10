"""Guards — v2.1 §7: safety predicates over signals, calibration-aware.

A guard blocks an action when its predicate over named signals holds. The
night of 2026-10-09 was killed by the inverse rule: `destructiveActionGuard`
blocked a diagnosed fix with `signals_contradict` because the service drive
was red (real signal) while pacing was green — and pacing was green because
`rate` was `null`: the source was uncalibrated, and the guard read absence
as agreement.

v2.1 rules implemented here:

1. **Absent signal is not disagreement.** If any signal of the guard's
   predicate is uncalibrated (None), the guard does NOT block and records
   `guard_skipped_uncalibrated` with the signal names.
2. **A guard cannot park a diagnosed fix.** Corrective actions may require
   logging, may require confirmation — they cannot stay blocked while the
   window dies. A rejected corrective raises pressure instead of consuming
   the activation, and the reason enters the next cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Sequence

__all__ = ["Guard", "GuardVerdict", "evaluate_guards"]

# truthy reasons a guard fires
SIGNALS_CONTRADICT = "signals_contradict"


@dataclass
class GuardVerdict:
    """Outcome of evaluating one guard.

    blocked:     True when the predicate held over calibrated signals.
    skipped:     True when the guard could not judge (uncalibrated signal)
                 — v2.1 §7.1: it does NOT block in that case.
    uncalibrated: names of the absent signals.
    reason:      predicate's own reason string when blocked.
    """
    blocked:       bool = False
    skipped:       bool = False
    uncalibrated:  list[str] = field(default_factory=list)
    reason:        str = ""


class Guard:
    """A named safety predicate over signals, with risk classification.

    Args:
        name:       e.g. "destructive_action_guard"
        predicate:  f(signals: dict[str, float|None]) -> str | None.
                    Returns a reason string to BLOCK, None to pass.
        risk:       which actions it applies to — "destructive", "corrective"
                    or "all" (v2.1 §7.2 distinguishes the two classes).
    """

    def __init__(self, name: str, predicate: Callable[[Mapping[str, Optional[float]]], Optional[str]],
                 risk: str = "destructive") -> None:
        self.name = name
        self.predicate = predicate
        self.risk = risk

    def evaluate(self, signals: Mapping[str, Optional[float]]) -> GuardVerdict:
        """Evaluate the predicate. Uncalibrated signals → skipped, never blocked."""
        uncalibrated = [k for k, v in signals.items() if v is None]
        if uncalibrated:
            # v2.1 §7.1 — absent signal is not disagreement: it is absent.
            return GuardVerdict(skipped=True, uncalibrated=uncalibrated)
        reason = self.predicate(signals)
        if reason:
            return GuardVerdict(blocked=True, reason=reason)
        return GuardVerdict()


def evaluate_guards(guards: Sequence[Guard], risk: str,
                    signals: Mapping[str, Optional[float]],
                    emit) -> Optional[GuardVerdict]:
    """Run all guards of `risk` over `signals`; `emit(event, payload)` traces.

    Returns the first BLOCKING verdict, or None if the action passes (a
    skipped guard passes by definition — v2.1 §7.1). Skips and blocks are
    traced as first-class events either way (v2.1 §8).
    """
    for g in guards:
        if g.risk != "all" and g.risk != risk:
            continue
        verdict = g.evaluate(signals)
        if verdict.skipped:
            emit("GuardSkippedUncalibrated", {
                "guard":        g.name,
                "risk":         risk,
                "uncalibrated": verdict.uncalibrated,
            })
            continue
        if verdict.blocked:
            emit("GuardRejected", {
                "guard":   g.name,
                "risk":    risk,
                "reason":  verdict.reason,
                "signals": {k: (None if v is None else round(v, 4))
                            for k, v in signals.items()},
            })
            return verdict
    return None