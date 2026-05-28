"""Sleep cycle: consolidation during SUSPENDED + causal AND-wake.

ConsolidationWorker:
    Each tick while SUSPENDED, processes items from the agent's demand queue
    and applies δ recovery. Batch-accelerated so queue empties naturally.

WakeGuard:
    Tests the two AND conditions for waking:
        (a) δ ≤ wake_threshold  — metabolic recovery
        (b) queue_consolidated  — pending_demands is empty

    Both must be True simultaneously. If only one is met the agent stays asleep.
    When both True, emits "sleep.cycle.completed" and returns True.

SleepConfig:
    User-tunable parameters for the sleep/consolidation cycle.

Design note (from CONTEXT.md §8):
    Sleep is causal, not a timeout. An agent under sustained high demand may
    never clear its queue and therefore never wake — this is intentional behavior
    that should be visible in the UI as "blocked in sleep, queue growing".
    A forced-wake timeout is NOT implemented; it would compromise the demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import BinsaiAgent
    from .drives import Drive


@dataclass
class SleepConfig:
    """User-tunable sleep/consolidation parameters."""
    wake_threshold:    float = 0.20   # δ must be ≤ this to wake
    recovery_per_item: float = 0.03   # δ reduction per consolidated item
    batch_size:        int   = 3      # items processed per sleep tick
    summarize_every:   int   = 3      # run LLM summarizer every N sleep ticks


_SUMMARY_EVERY_N_TICKS: int = 3   # fallback: run LLM summarizer every N sleep ticks


class ConsolidationWorker:
    """Processes the demand queue during sleep, batch-accelerated.

    Each processed item lowers δ by `recovery_per_item` (consolidation reward).
    A passive recovery applies every tick regardless of queue state — sleep is
    restorative even with an empty queue.
    Periodically runs an LLM summarizer over working_memory + pending_demands
    and replaces them with a single compact summary, simulating context-window
    compression.
    """

    def __init__(
        self,
        config: SleepConfig | None = None,
        recovery_per_item: float = 0.03,
        passive_recovery:  float = 0.008,
    ) -> None:
        self.config = config or SleepConfig()
        self.recovery_per_item = recovery_per_item
        self.passive_recovery  = passive_recovery
        self._ticks_asleep:    int = 0

    def tick(self, agent: "BinsaiAgent", drive: "Drive", t: int) -> bool:
        """Process pending demand items during SUSPENDED.

        Always applies passive recovery. Returns True if any queue item was processed.
        Periodically runs LLM context compression.
        """
        self._ticks_asleep += 1

        # Passive metabolic recovery every sleep tick (basal is paused during sleep)
        drive.satiate(self.passive_recovery / drive.satiation_rate)

        # LLM summarization every N sleep ticks
        if self._ticks_asleep % self.config.summarize_every == 0:
            self._run_summary(agent, drive, t)

        # Batch-consolidate up to batch_size items per sleep tick
        n_processed = 0
        while agent.pending_demands and n_processed < self.config.batch_size:
            item = agent.pending_demands.popleft()
            drive.satiate(self.recovery_per_item / drive.satiation_rate)
            agent.emit("consolidation.item.processed", {
                "agent": agent.name,
                "tick":  t,
                "item":  getattr(item, "id", str(item)),
                "delta_after": round(drive.value, 4),
            })
            n_processed += 1
        return n_processed > 0

    def _run_summary(self, agent: "BinsaiAgent", drive: "Drive", t: int) -> None:
        """LLM-based working memory + demand queue compression.

        Uses tier 'weak' (flash, no thinking). Replaces all current working memory
        items with a single summary dict. Emits 'consolidation.summary' event.
        The δ recovery is proportional to how many items were compressed.
        """
        wm = list(agent._working_memory)
        pending_topics = [
            getattr(d, "topic", "?") for d in list(agent.pending_demands)
        ]
        n_wm      = len(wm)
        n_pending = len(pending_topics)

        if n_wm + n_pending == 0:
            return

        try:
            from .actions import call_llm, ModelConfig
            system = (
                "You are a memory consolidation module for an AI agent during sleep. "
                "Produce a compact summary of recent work and pending tasks. "
                "Be brief: 2-3 sentences max. "
                'Respond with JSON: {"summary": "<text>", "key_topics": ["<topic>", ...]}'
            )
            wm_str = "; ".join(
                f"{item.get('action', '?')}({item.get('demand', '?')})" for item in wm[-5:]
            )
            pending_str = ", ".join(pending_topics[:5]) or "none"
            user = (
                f"Recent actions: {wm_str or 'none'}\n"
                f"Pending topics: {pending_str}"
            )
            cfg = ModelConfig(model="deepseek-v4-flash", thinking=False)
            raw, _ = call_llm(system, user, cfg=cfg, max_tokens=256)

            from .actions import _extract_json
            data    = _extract_json(raw)
            summary = data.get("summary", raw[:80]) if data else raw[:80]

            # Replace working memory with single summary item
            agent._working_memory = [{
                "type":        "consolidation_summary",
                "summary":     summary,
                "n_compressed": n_wm,
                "t":           t,
            }]

            # Extra recovery proportional to items compressed
            bonus = 0.005 * (n_wm + n_pending)
            drive.satiate(bonus / drive.satiation_rate)

            agent.last_consolidation_summary = summary
            agent.emit("consolidation.summary", {
                "agent":        agent.name,
                "tick":         t,
                "n_compressed": n_wm,
                "n_pending":    n_pending,
                "summary":      summary[:80],
                "delta_after":  round(drive.value, 4),
            })
        except Exception as exc:
            agent.emit("consolidation.summary.error", {
                "agent": agent.name,
                "tick":  t,
                "error": str(exc)[:60],
            })


class WakeGuard:
    """Tests AND-condition for waking from sleep.

    Condition A: drive.value ≤ wake_threshold  — metabolic recovery
    Condition B: agent.pending_demands is empty (queue fully consolidated)

    Both must be True in the same tick. Emits events on each condition state.
    Consolidation is batch-accelerated so queue empties naturally as drive recovers.
    """

    def __init__(self, wake_threshold: float = 0.20) -> None:
        self.wake_threshold = wake_threshold

    def check(self, agent: "BinsaiAgent", drive: "Drive", t: int) -> bool:
        """Return True if both wake conditions are met (agent may transition to ACTIVE)."""
        recovered    = drive.value <= self.wake_threshold
        consolidated = len(agent.pending_demands) == 0

        agent.emit("sleep.wake_check", {
            "agent":       agent.name,
            "tick":        t,
            "recovered":   recovered,
            "consolidated": consolidated,
            "delta":       round(drive.value, 4),
            "queue_len":   len(agent.pending_demands),
        })

        if recovered and consolidated:
            agent.emit("sleep.cycle.completed", {
                "agent": agent.name,
                "tick":  t,
                "delta": round(drive.value, 4),
            })
            drive.satiate(0.5)  # wake bonus: consolidation reward ~−0.05 δ
            return True

        return False


def maybe_wake(agent: "BinsaiAgent", drive: "Drive", t: int) -> bool:
    """Convenience: consolidate one item then check wake conditions."""
    worker = ConsolidationWorker()
    guard  = WakeGuard()
    worker.tick(agent, drive, t)
    return guard.check(agent, drive, t)
