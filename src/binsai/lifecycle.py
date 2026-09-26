"""FIPA lifecycle with explicit causal transitions (EPA spec §6.1).

Every state change requires a non-empty cause string so that the event log
is always auditable — we know exactly why an agent changed state.

States (FIPA Agent Management):
    INITIATED  → created, not yet running            (EPA: not updated)
    WAITING    → alive, no task in course            (EPA updated; decides)
    ACTIVE     → executing a committed task          (EPA updated; no new
                 decisions — avoids dithering mid-task)
    SUSPENDED  → sleeping / consolidation            (EPA updated, basal only)
    TERMINATED → end of simulation
    TRANSIT    → reserved (FIPA mobile agents)       — not used yet

    CRITICAL   → Binsai extension: δ sustained in a red zone for
                 T_critical_dwell ticks. Alarm state — the agent freezes
                 until reset. (FIPA has no equivalent; documented extension.)

Transitions:
    INITIATED --invoke-->  WAITING
    WAITING   --execute--> ACTIVE      (EPA decision or incoming message)
    ACTIVE    --done|abort--> WAITING  (commitment rule; abort only on
                                        red zone / viability breach)
    WAITING   --suspend--> SUSPENDED   (consolidation, rest)
    SUSPENDED --resume-->  WAITING
    WAITING|ACTIVE --dwell--> CRITICAL (Binsai extension)
    CRITICAL  --reset-->   WAITING
    any       --quit-->    TERMINATED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FIPAState(Enum):
    INITIATED  = "initiated"
    WAITING    = "waiting"     # alive, idle, EPA decides (was ACTIVE pre-0.2)
    ACTIVE     = "active"      # executing a committed task (was implicit)
    SUSPENDED  = "suspended"
    CRITICAL   = "critical"    # Binsai extension (not in FIPA)
    TERMINATED = "terminated"
    TRANSIT    = "transit"     # reserved — mobile agents, not used yet


# Valid transitions: (from, to) pairs
_VALID_TRANSITIONS: set[tuple[FIPAState, FIPAState]] = {
    (FIPAState.INITIATED,  FIPAState.WAITING),     # invoke
    (FIPAState.WAITING,    FIPAState.ACTIVE),      # execute
    (FIPAState.ACTIVE,     FIPAState.WAITING),     # done | abort
    (FIPAState.WAITING,    FIPAState.SUSPENDED),   # suspend
    (FIPAState.SUSPENDED,  FIPAState.WAITING),     # resume
    (FIPAState.WAITING,    FIPAState.CRITICAL),    # dwell alarm (extension)
    (FIPAState.ACTIVE,     FIPAState.CRITICAL),    # dwell while working
    (FIPAState.CRITICAL,   FIPAState.WAITING),     # reset
    (FIPAState.CRITICAL,   FIPAState.SUSPENDED),   # forced consolidation from alarm
    (FIPAState.WAITING,    FIPAState.TERMINATED),  # quit
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
        T_critical_dwell:  Ticks in a red zone before → CRITICAL (default 60)
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
        """Call each tick when a drive is in a red zone while operational.

        Returns True and fires → CRITICAL if dwell threshold exceeded.
        """
        if self._state not in (FIPAState.WAITING, FIPAState.ACTIVE):
            self._critical_ticks = 0
            return False

        self._critical_ticks += 1
        if self._critical_ticks >= self.T_critical_dwell:
            self._critical_ticks = 0
            self.transition(
                FIPAState.CRITICAL,
                cause=f"critical_dwell: δ in red zone for {self.T_critical_dwell} ticks",
                tick=tick,
            )
            return True
        return False

    def reset_critical_counter(self) -> None:
        """Reset dwell counter when the agent leaves the red zone."""
        self._critical_ticks = 0

    # ── State predicates ────────────────────────────────────────────────────

    def is_waiting(self) -> bool:
        """WAITING — alive, no task in course; the EPA may decide."""
        return self._state == FIPAState.WAITING

    def is_active(self) -> bool:
        """ACTIVE — executing a committed task (no new decisions)."""
        return self._state == FIPAState.ACTIVE

    def is_operational(self) -> bool:
        """WAITING or ACTIVE — the agent participates in the world."""
        return self._state in (FIPAState.WAITING, FIPAState.ACTIVE)

    def is_suspended(self) -> bool:
        return self._state == FIPAState.SUSPENDED

    def is_critical(self) -> bool:
        return self._state == FIPAState.CRITICAL

    def is_terminated(self) -> bool:
        return self._state == FIPAState.TERMINATED

    def last_event(self) -> Optional[LifecycleEvent]:
        return self._history[-1] if self._history else None

    def __repr__(self) -> str:
        return f"LifecycleManager(state={self._state.value}, events={len(self._history)})"
