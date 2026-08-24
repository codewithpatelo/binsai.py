"""Action registry — pluggable action specs with handler dispatch.

ActionSpec defines what an action IS (cost, ticks, softmax coefficients).
ActionSet is an ordered collection; .mvp1() reproduces today's 6 actions.
Handlers are callables (agent, drive, tick, demand, demand_difficulty) -> action_name_str.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ActionKind(Enum):
    """Convenience aliases for the 6 built-in actions."""
    RESPOND_FAST = "respond_fast"
    RESPOND_SLOW = "respond_slow"
    DEFER        = "defer"
    PROACT       = "proact"
    IDLE         = "idle"
    SLEEP        = "sleep"


@dataclass
class ActionSpec:
    """A single action in the agent's repertoire.

    Attributes:
        name:             Unique action identifier (e.g. "respond_fast", "go_to_fridge")
        requires_demand:  Whether this action needs a pending demand
        delta_cost:       Flat δ cost applied when the action starts
        ticks:            How many ticks the action takes (1 = instant)
        beta:             Softmax coefficient for drive intensity sensitivity
        bias:             Softmax baseline preference at set-point
        handler:          Callable (agent, drive, tick, demand, difficulty) -> action_name_str
        max_tokens:       LLM call budget (0 = no LLM call)
    """
    name:             str
    requires_demand:  bool
    delta_cost:       float   = 0.0
    ticks:            int     = 1
    beta:             float   = 0.0
    bias:             float   = 0.0
    handler:          Optional[Callable] = None
    max_tokens:       int     = 0


# ── Built-in handlers ────────────────────────────────────────────────────────

def _handler_noop(agent: Any, drive: Any, tick: int, demand: Any, difficulty: float) -> str:
    """Idle: do nothing."""
    return "idle"

def _handler_sleep(agent: Any, drive: Any, tick: int, demand: Any, difficulty: float) -> str:
    """Sleep: transition to SUSPENDED lifecycle state."""
    from .lifecycle import FIPAState
    agent.current_task_label = "Compress & consolidate context"
    agent._lifecycle.transition(
        FIPAState.SUSPENDED,
        cause=f"regulatory sleep at t={tick} delta={drive.value:.3f}" if drive else f"sleep at t={tick}",
        tick=tick,
    )
    agent.emit("lifecycle", {
        "event": "suspended",
        "agent": agent.name,
        "tick": tick,
        "cause": "regulatory: sleep action selected",
    })
    return "sleep"

def _handler_defer(agent: Any, drive: Any, tick: int, demand: Any, difficulty: float) -> str:
    """Defer: requeue the demand for later."""
    if demand:
        agent.pending_demands.append(demand)
    agent.session_deferred += 1
    return "defer"

def _handler_llm(agent: Any, drive: Any, tick: int, demand: Any, difficulty: float) -> str:
    """LLM-based action (respond_fast, respond_slow, proact)."""
    # The actual LLM call is orchestrated by agent._run_llm_and_apply_cost()
    # which is called by the action execution path in agent.py.
    # This handler just returns the action name; the caller handles the rest.
    return "llm"  # caller maps this to the actual action kind

def _handler_satiate(drive_name: str, amount: float = 0.5, action_name: str = "eat",
                     only_when_deficit: bool = True) -> Callable:
    """Factory: create a satiation handler for a specific drive.
    
    Args:
        drive_name: Name of the drive to satiate
        amount: Amount to satiate
        action_name: Display name for the action (e.g. 'go_to_fridge')
        only_when_deficit: If True, only satiates when drive is above set-point
                           (prevents eating when already oversated)
    """
    def handler(agent: Any, drive: Any, tick: int, demand: Any, difficulty: float) -> str:
        target = agent.drives.get(drive_name)
        if target:
            if only_when_deficit and target.value <= target.set_point:
                return "idle"  # already full, don't eat
            target.satiate(amount)
        return action_name
    return handler


# ── ActionSet ─────────────────────────────────────────────────────────────────

class ActionSet:
    """An ordered collection of ActionSpecs — the agent's action repertoire."""

    def __init__(self, specs: Optional[list[ActionSpec]] = None) -> None:
        self._specs: dict[str, ActionSpec] = {}
        if specs:
            for s in specs:
                self._specs[s.name] = s

    def add(self, spec: ActionSpec) -> None:
        """Add or replace an action."""
        self._specs[spec.name] = spec

    def get(self, name: str) -> Optional[ActionSpec]:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return list(self._specs.keys())

    def with_demand(self) -> list[ActionSpec]:
        """Actions available when a demand is pending (excludes proact, includes sleep)."""
        return [s for s in self._specs.values() if s.name != "proact"]

    def without_demand(self) -> list[ActionSpec]:
        """Actions available when no demand is pending."""
        return [s for s in self._specs.values() if not s.requires_demand]

    @classmethod
    def mvp1(cls) -> "ActionSet":
        """The 6 built-in actions of MVP1 — byte-for-byte compatible with today."""
        return cls([
            ActionSpec(
                name="respond_fast", requires_demand=True,
                delta_cost=0.002, ticks=1, max_tokens=256,
                beta=-0.5, bias=+1.6, handler=_handler_llm,
            ),
            ActionSpec(
                name="respond_slow", requires_demand=True,
                delta_cost=0.005, ticks=3, max_tokens=1500,
                beta=-8.0, bias=-0.3, handler=_handler_llm,
            ),
            ActionSpec(
                name="defer", requires_demand=True,
                delta_cost=0.0005, ticks=1, max_tokens=0,
                beta=+6.0, bias=-0.5, handler=_handler_defer,
            ),
            ActionSpec(
                name="proact", requires_demand=False,
                delta_cost=0.003, ticks=2, max_tokens=1500,
                beta=-12.0, bias=-1.5, handler=_handler_llm,
            ),
            ActionSpec(
                name="idle", requires_demand=False,
                delta_cost=0.0, ticks=1, max_tokens=0,
                beta=0.0, bias=-0.3, handler=_handler_noop,
            ),
            ActionSpec(
                name="sleep", requires_demand=False,
                delta_cost=0.0, ticks=0, max_tokens=0,
                beta=+10.0, bias=-6.0, handler=_handler_sleep,
            ),
        ])

    def to_action_params(self) -> dict[str, tuple[float, float]]:
        """Export {name: (beta, bias)} for fuzzy.compute_action_distribution."""
        return {s.name: (s.beta, s.bias) for s in self._specs.values()}
