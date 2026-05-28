"""FIPA-inspired lifecycle with explicit causal transitions.

Every state change requires a non-empty cause string so that the event log
is always auditable — we know exactly why an agent changed state.

States:
    INITIATED  → agent created, not yet running
    ACTIVE     → normal operation
    SUSPENDED  → sleeping (consolidation mode)
    CRITICAL   → δ sustained above critical threshold for T_critical_dwell ticks
    TERMINATED → end of simulation (MVP1: never reached automatically)

Transitions:
    INITIATED → ACTIVE    (activate, cause: "start")
    ACTIVE    → SUSPENDED (cause: regulatory — sleep action chosen)
    ACTIVE    → CRITICAL  (cause: regulatory — dwell timer expired)
    SUSPENDED → ACTIVE    (cause: wake — δ recovered AND queue consolidated)
    CRITICAL  → ACTIVE    (cause: ablation reset or manual intervention)
    any       → TERMINATED (cause: explicit shutdown)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FIPAState(Enum):
    INITIATED  = "initiated"
    ACTIVE     = "active"
    SUSPENDED  = "suspended"
    CRITICAL   = "critical"
    TERMINATED = "terminated"


# Valid transitions: (from, to) pairs
_VALID_TRANSITIONS: set[tuple[FIPAState, FIPAState]] = {
    (FIPAState.INITIATED,  FIPAState.ACTIVE),
    (FIPAState.ACTIVE,     FIPAState.SUSPENDED),
    (FIPAState.ACTIVE,     FIPAState.CRITICAL),
    (FIPAState.SUSPENDED,  FIPAState.ACTIVE),
    (FIPAState.CRITICAL,   FIPAState.ACTIVE),
    (FIPAState.ACTIVE,     FIPAState.TERMINATED),
    (FIPAState.SUSPENDED,  FIPAState.TERMINATED),
    (FIPAState.CRITICAL,   FIPAState.TERMINATED),
}


@dataclass(frozen=True)
class LifecycleEvent:
    """Immutable record of one state transition."""
    tick:  int
    from_: FIPAState
    to:    FIPAState
    cause: str


class LifecycleManager:
    """Manages FIPA state transitions with causal logging.

    Args:
        initial:           Starting state (default INITIATED)
        T_critical_dwell:  Ticks in zone critical before ACTIVE → CRITICAL (default 60)
    """

    def __init__(
        self,
        initial:          FIPAState = FIPAState.INITIATED,
        T_critical_dwell: int       = 60,
    ) -> None:
        self._state            = initial
        self._history:  list[LifecycleEvent] = []
        self.T_critical_dwell  = T_critical_dwell
        self._critical_ticks   = 0  # consecutive ticks in critical zone

    @property
    def state(self) -> FIPAState:
        return self._state

    @property
    def history(self) -> list[LifecycleEvent]:
        return list(self._history)

    def transition(self, to: FIPAState, cause: str, tick: int = 0) -> None:
        """Apply a state transition.

        Raises:
            ValueError: if cause is empty or the transition is not valid.
        """
        if not cause.strip():
            raise ValueError(
                f"Lifecycle transition {self._state} → {to} requires a non-empty cause."
            )
        if (self._state, to) not in _VALID_TRANSITIONS:
            raise ValueError(
                f"Invalid lifecycle transition: {self._state.value} → {to.value}"
            )
        event = LifecycleEvent(tick=tick, from_=self._state, to=to, cause=cause)
        self._history.append(event)
        self._state = to

    def tick_critical_zone(self, tick: int) -> bool:
        """Call each tick when drive is in critical zone while ACTIVE.

        Returns True and fires ACTIVE → CRITICAL if dwell threshold exceeded.
        """
        if self._state != FIPAState.ACTIVE:
            self._critical_ticks = 0
            return False

        self._critical_ticks += 1
        if self._critical_ticks >= self.T_critical_dwell:
            self._critical_ticks = 0
            self.transition(
                FIPAState.CRITICAL,
                cause=f"critical_dwell: δ in critical zone for {self.T_critical_dwell} ticks",
                tick=tick,
            )
            return True
        return False

    def reset_critical_counter(self) -> None:
        """Reset dwell counter when agent leaves critical zone."""
        self._critical_ticks = 0

    def is_active(self) -> bool:
        return self._state == FIPAState.ACTIVE

    def is_suspended(self) -> bool:
        return self._state == FIPAState.SUSPENDED

    def last_event(self) -> Optional[LifecycleEvent]:
        return self._history[-1] if self._history else None

    def __repr__(self) -> str:
        return f"LifecycleManager(state={self._state.value}, events={len(self._history)})"
