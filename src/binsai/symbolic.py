"""Symbolic pre-commit check for proactive actions.

Implements a minimal declarative rule-checker that gates proactive proposals
before they are sent to the human.

Rule set (MVP1 — S1 metabolic only):
    R1. Metabolic drive must be in oversated or sated zone (agent has spare capacity).
    R2. Pending demand queue must be small (< MAX_QUEUE_FOR_PROACT) — agent is not
        overwhelmed and can afford to self-initiate.
    R3. Priority must be coherent with drive margin:
        - "high" priority only when drive is oversated (full headroom).
        - "medium" or "low" always allowed when R1/R2 pass.

These rules encode the "reason before commit" principle: the agent checks its own
state symbolically before proposing anything to the human.

Future work (MVP4+): replace with DeLP / defeasible argumentation via OpenClaw.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import BinsaiAgent

MAX_QUEUE_FOR_PROACT: int = 3


def check_proact_proposal(
    agent:    "BinsaiAgent",
    proposal: str,
    priority: str = "low",
) -> tuple[bool, str]:
    """Check if the agent may send a proactive PROPOSE to the human.

    Returns:
        (ok, reason) — if ok=False, the proposal should be aborted and the
        reason logged as 'proact.rejected'.
    """
    drive = agent.drives.get("metabolic")
    if drive is None:
        return False, "no metabolic drive — cannot evaluate resource margin"

    zone = drive.get_zone()

    # R1: drive must be in oversated or sated zone
    if zone not in ("oversated", "sated"):
        return False, f"R1 failed: drive zone '{zone}' — insufficient resource margin for proact"

    # R2: queue must be small (agent not overwhelmed)
    queue_len = len(agent.pending_demands)
    if queue_len >= MAX_QUEUE_FOR_PROACT:
        return False, f"R2 failed: queue={queue_len} >= {MAX_QUEUE_FOR_PROACT} — agent is overwhelmed"

    # R3: priority coherence
    if priority == "high" and zone != "oversated":
        return False, f"R3 failed: high-priority proact requires oversated zone, got '{zone}'"

    return True, "all rules passed"
