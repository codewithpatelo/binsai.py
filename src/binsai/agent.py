"""BinsaiAgent — Core agent with regulatory drives, interoceptive tick loop, and FIPA lifecycle.

Architecture:
    Perception:  event bus (on/off/emit) + demand queue (pending_demands)
    Motor:       action emission — drives determine WHICH action via fuzzy softmax
    Drives:      stratified Bunge-Romero (10 canonical; metabolic active in MVP1)
    Memory:      bounded working memory (Miller's law: 7 items)
    Lifecycle:   FIPA states managed by LifecycleManager with causal transitions

Tick loop (interoceptive + exteroceptive):
    Each tick the agent:
      1. Applies basal λ decay to all drives
      2. If SUSPENDED: runs consolidation + checks AND-wake condition
      3. If ACTIVE: selects and begins (or continues) an action via fuzzy softmax
         over δ_metabolic. The decision integrates internal state (interoception)
         and whether a demand is waiting (exteroception).
      4. Emits a tick summary event for the world to log.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .acl import ACLMessage, Mailbox, Performative
from .drives import Drive, Drives
from .lifecycle import FIPAState, LifecycleManager
from .fuzzy import compute_action_distribution, sample_action
from .actions import (
    ActionExecution,
    ActionKind,
    ACTIONS,
    AppraisedTask,
    DEFAULT_ROUTING,
    LLMTelemetry,
    ModelConfig,
    RegulatoryBudgets,
    appraise_demand,
    execute_action_llm,
    pick_model_for_state,
    start_action,
)
from .sleep import ConsolidationWorker, WakeGuard
from .symbolic import check_proact_proposal


@dataclass
class Position:
    """2D spatial situatedness."""
    x: float = 0.0
    y: float = 0.0

    def distance_to(self, other: "Position") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


class BinsaiAgent:
    """Core Binsai agent — regulatory substrate over a tick-based interoceptive loop.

    Args:
        name:             Human-readable label (e.g. "Alpha")
        drives:           Stratified drives collection (defaults to full 10-drive set)
        position:         2D spatial position
        metadata:         Arbitrary key-value bag for framework integration
        lambda_override:  Override metabolic λ for heterogeneity demos
        ablation_off:     If True, action selection is uniform (regulation disabled)
        dry_run_llm:      If True, LLM calls return synthetic payloads (no API key needed)
        temperature:      Softmax temperature for action selection
        rng:              Seeded random.Random instance (injected by World for reproducibility)
    """

    def __init__(
        self,
        name:            str,
        drives:          Optional[Drives]   = None,
        position:        Optional[Position] = None,
        metadata:        Optional[dict]     = None,
        lambda_override: Optional[float]    = None,
        ablation_off:    bool               = False,
        dry_run_llm:     bool               = False,
        temperature:     float              = 1.0,
        rng:             Optional[Any]      = None,
    ) -> None:
        import random as _random

        self.aid      = str(uuid.uuid4())[:8]
        self.name     = name
        self.drives   = drives or Drives.stratified()
        self.position = position or Position()
        self.metadata = metadata or {}

        self.ablation_off = ablation_off
        self.dry_run_llm  = dry_run_llm
        self.temperature  = temperature
        self._rng         = rng or _random.Random()

        # User-tunable regulatory budgets (cost / latency / token targets)
        self.budgets = RegulatoryBudgets()
        # Last LLM telemetry and appraisal (for UI display)
        self.last_telemetry:    Optional[LLMTelemetry]  = None
        self.last_appraisal:    Optional[AppraisedTask]  = None
        # Last proactive INFORM to human (consumed once per world frame)
        self.last_proact_message: Optional[str] = None
        # Last token-minimization (caveman) pressure flag — UI indicator
        self.last_pressure_mode: bool = False
        # Last sleep-time consolidation summary (consumed once per world frame)
        self.last_consolidation_summary: Optional[str] = None

        # Session accumulators (for comparative KPI metrics)
        self.session_tokens:   int   = 0
        self.session_cost_usd: float = 0.0
        self.session_calls:    int   = 0
        self.session_deferred: int   = 0

        # Kanban task tracking — fed from LLM tasks_to_do output
        self.pending_task_labels: deque[str] = deque(maxlen=12)
        self.current_task_label:  Optional[str] = None
        self.done_task_labels:    deque[str] = deque(maxlen=6)

        # Context window budget (tokens) — used for window_saturation via prompt_tokens
        self.context_budget_tokens: int = 8000

        # Mailbox: FIPA-aware sensor (suspended → buffer, active → inbox)
        self.mailbox = Mailbox(owner_aid=self.aid)

        # Override λ for heterogeneity
        metabolic = self.drives.get("metabolic")
        if metabolic and lambda_override is not None:
            metabolic.lambda_rate = lambda_override

        # FIPA lifecycle
        self._lifecycle = LifecycleManager()

        # Event bus
        self._event_handlers:        dict[str, list[Callable]] = {}
        self._global_event_handlers: list[Callable]            = []
        self._subscribed_agents:     dict[str, "BinsaiAgent"]  = {}

        # Demand queue: demands waiting to be processed
        self.pending_demands: deque = deque()

        # Current in-flight action (None when idle or between actions)
        self.current_action: Optional[ActionExecution] = None

        # Last action taken this tick (for UI — includes single-tick actions)
        self.last_action: Optional[str] = None

        # Bounded working memory (Miller's law)
        self._working_memory: list[dict] = []
        self._max_wm_size = 7

        # Sleep helpers
        self._consolidation_worker = ConsolidationWorker()
        self._wake_guard           = WakeGuard()

        # Current tick (set at start of tick() so budget window calls can reference it)
        self._current_tick: int = 0

    # ── Properties ──────────────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._lifecycle.state.value

    # ── Lifecycle ────────────────────────────────────────────────────────────────

    def activate(self) -> None:
        """INITIATED → ACTIVE."""
        if self._lifecycle.state == FIPAState.INITIATED:
            self._lifecycle.transition(FIPAState.ACTIVE, cause="start", tick=0)
            self.emit("lifecycle", {"event": "activated", "agent": self.name})

    def can_participate(self) -> bool:
        return self._lifecycle.is_active()

    def _add_task_label(self, label: str) -> None:
        """Append a task label to pending, filtering meta/junk strings from LLM."""
        raw = label.strip()
        if not raw or len(raw) < 3:
            return
        low = raw.lower()
        junk = [
            "no recent work", "no pending tasks", "no tasks", "no task",
            "none", "n/a", "not applicable", "no action", "nothing to do",
            "no follow-up", "no follow up", "not needed", "no change",
            "no updates", "no update", "status quo", "nothing new",
        ]
        if any(j in low for j in junk):
            return
        self.pending_task_labels.append(raw)

    # ── Tick loop (interoceptive + exteroceptive) ────────────────────────────────

    def tick(self, t: int, world: Any = None) -> dict:  # noqa: ARG002  (world reserved for MVP2+ multi-process)
        """Execute one simulation tick. Returns a summary dict for WorldFrame.

        Steps:
          1. Basal λ decay on all drives
          2. Branch on ACTIVE vs SUSPENDED
          3. Emit tick summary
        """
        self._current_tick = t
        drive = self.drives.get("metabolic")

        # 1. Basal decay only during ACTIVE — sleep is restorative, no metabolic burn
        # Ablation agents have no drive regulation, so no decay (flat line)
        if not self._lifecycle.is_suspended() and not self.ablation_off:
            self.drives.update_all(tick=t)

        summary: dict = {
            "agent":    self.name,
            "aid":      self.aid,
            "tick":     t,
            "status":   self.status,
            "delta":    round(drive.value, 4) if drive else None,
            "zone":     drive.get_zone() if drive else None,
            "queue":    len(self.pending_demands),
            "action":   None,
        }

        if self._lifecycle.is_suspended():
            summary["action"] = "sleep"
            self._tick_suspended(drive, t)

        elif self._lifecycle.is_active():
            action_taken = self._tick_active(drive, t)
            self.last_action = action_taken
            summary["action"] = action_taken

            # Critical zone dwell check
            if drive and drive.get_zone() == "critical":
                transitioned = self._lifecycle.tick_critical_zone(t)
                if transitioned:
                    self.emit("lifecycle", {
                        "event": "critical",
                        "agent": self.name,
                        "tick":  t,
                        "cause": "dwell",
                    })
            else:
                self._lifecycle.reset_critical_counter()

        self.emit("tick.summary", summary)
        return summary

    def _tick_suspended(self, drive: Optional[Drive], t: int) -> None:
        """One tick of sleep: consolidate one demand item, check wake."""
        if drive is None:
            return

        self._consolidation_worker.tick(self, drive, t)
        should_wake = self._wake_guard.check(self, drive, t)

        if should_wake:
            # Flush buffered messages that arrived during suspension
            n_buffered = self.mailbox.flush_buffer_to_inbox()
            # Move buffered mailbox demands into pending_demands deque
            buffered_topics = []
            for msg in self.mailbox.drain_inbox():
                topic = getattr(msg, "topic", None) or getattr(msg, "content", "")
                if topic:
                    buffered_topics.append(topic)
                self._enqueue_from_message(msg)

            # Move the sleep maintenance task to done
            if self.current_task_label:
                self.done_task_labels.append(self.current_task_label)
                self.current_task_label = None

            # Convert buffered demand topics into pending task labels
            for topic in buffered_topics[:3]:
                self._add_task_label(f"Reply: {topic.replace('_', ' ')}")

            self._lifecycle.transition(
                FIPAState.ACTIVE,
                cause=f"wake: recovered+consolidated at t={t}",
                tick=t,
            )
            self.emit("lifecycle", {
                "event": "resumed",
                "agent": self.name,
                "tick":  t,
                "cause": f"wake: recovered+consolidated (flushed {n_buffered} buffered)",
            })

    def _tick_active(self, drive: Optional[Drive], t: int, world: Any = None) -> str:  # noqa: ARG002
        """One tick of active operation. Returns name of action taken."""
        # Drain active mailbox inbox → enqueue demands
        for msg in self.mailbox.drain_inbox():
            self._enqueue_from_message(msg)

        # Continue multi-tick action if in progress
        if self.current_action is not None:
            self.current_action.ticks_remaining -= 1
            if self.current_action.ticks_remaining <= 0:
                self._complete_action(self.current_action, drive, t)
                self.current_action = None
            return self.current_action.kind.value if self.current_action else "completing"

        # ── Ablation branch: parallel unregulated architecture ──
        # No appraisal, no fuzzy selection, no sleep, no proact, no state injection.
        # Always respond_slow with baseline prompt (tier main) for fair comparison.
        if self.ablation_off:
            return self._tick_ablation(t)

        # ── Regulated branch ──
        has_demand = len(self.pending_demands) > 0
        delta      = drive.value if drive else 0.30
        set_point  = drive.set_point if drive else 0.30

        # Agent appraises next demand difficulty (LLM flash call, no thinking).
        # Cost is small but real — the drive pays for thinking before acting.
        # Skip if no demand, or if same topic was recently appraised (episodic cache).
        next_demand = self.pending_demands[0] if has_demand else None
        if next_demand is not None:
            appraisal = self._appraise(
                topic=getattr(next_demand, "topic", ""),
                message=getattr(next_demand, "message", ""),
                drive=drive,
            )
            demand_difficulty = appraisal.perceived_difficulty
        else:
            demand_difficulty = 0.0

        distribution = compute_action_distribution(
            delta=delta,
            has_demand=has_demand,
            set_point=set_point,
            ablation_off=False,   # regulated path always uses full distribution
            temperature=self.temperature,
            demand_difficulty=demand_difficulty,
            pending_labels=len(self.pending_task_labels),
        )
        chosen_name = sample_action(distribution, self._rng)
        kind = ActionKind(chosen_name)

        return self._start_chosen_action(kind, drive, t, demand_difficulty=demand_difficulty)

    def _tick_ablation(self, t: int) -> str:
        """Unregulated tick: respond to every demand at weak tier, no regulation.

        Fixed to deepseek-v4-flash (no thinking) so the KPI comparison is fair:
        any cost/token savings from regulation are purely behavioural
        (fewer calls via defer/sleep/proact-skip), not model-selection artefacts.
        """
        if not self.pending_demands:
            return "idle"
        demand = self.pending_demands.popleft()
        execution = start_action(ActionKind.RESPOND_SLOW, t, demand=demand)
        # Weak tier = flash, no thinking — cheapest per-call baseline
        model_cfg = DEFAULT_ROUTING["weak"]
        # For baseline mode, drive is passed but not used for state injection
        drive_arg = self.drives.get("metabolic")
        if drive_arg is None:
            drive_arg = Drives.from_names(["metabolic"]).get("metabolic")
        result, telemetry = execute_action_llm(
            execution,
            drive_arg,
            len(self.pending_demands),
            model_cfg=model_cfg,
            baseline_mode=True,
        )
        execution.result = result
        self.last_telemetry = telemetry
        # Extract LLM-generated task plans (ablation path)
        if result:
            for lbl in (result.get("tasks_to_do") or [])[:3]:
                if isinstance(lbl, str) and lbl.strip():
                    self._add_task_label(lbl.strip())
        # Append to budgets window so context_used_tokens tracks like regulated agent
        # (no δ depletion — only the rolling prompt-token window matters for ctx display)
        if telemetry.total_tokens > 0:
            self.budgets._window.append((t, telemetry))
            cutoff = t - self.budgets.window_ticks
            self.budgets._window = [
                (tk, tl) for (tk, tl) in self.budgets._window if tk > cutoff
            ]
        # Accumulate session stats (no drive depletion — no regulatory feedback)
        if telemetry.total_tokens > 0:
            self.session_tokens   += telemetry.total_tokens
            self.session_cost_usd += telemetry.cost_usd
            self.session_calls    += 1
            self.emit("telemetry", {
                "agent":             self.name,
                "model":             telemetry.model,
                "tier":              telemetry.tier,
                "cost_usd":          round(telemetry.cost_usd, 6),
                "latency_ms":        telemetry.latency_ms,
                "prompt_tokens":     telemetry.prompt_tokens,
                "completion_tokens": telemetry.completion_tokens,
                "delta_increment":   0.0,
                "demand_difficulty": 0.0,
            })
        self._on_action_complete(execution, t)
        return ActionKind.RESPOND_SLOW.value

    def _start_chosen_action(self, kind: ActionKind, drive: Optional[Drive], t: int,
                              demand_difficulty: float = 0.0) -> str:
        """Dispatch chosen action kind."""
        if kind == ActionKind.SLEEP:
            # Set the sleep maintenance task as current (visible in Kanban DOING)
            self.current_task_label = "Compress & consolidate context"
            self._lifecycle.transition(
                FIPAState.SUSPENDED,
                cause=f"regulatory sleep at t={t} δ={drive.value:.3f}" if drive else f"sleep at t={t}",
                tick=t,
            )
            self.emit("lifecycle", {
                "event": "suspended",
                "agent": self.name,
                "tick":  t,
                "cause": "regulatory: sleep action selected",
            })
            return "sleep"

        if kind == ActionKind.IDLE:
            return "idle"

        # Actions that may need a demand
        spec = ACTIONS[kind]
        demand = None
        if spec.requires_demand:
            if not self.pending_demands:
                # Fallback: if demand evaporated between decision and execution, idle
                return "idle"
            demand = self.pending_demands.popleft()

        execution = start_action(kind, t, demand=demand)
        # Persist the predicted difficulty so multi-tick completion can use it
        execution.demand_difficulty = demand_difficulty
        # Pop next task label from queue; fall back to demand topic + action kind
        if self.pending_task_labels:
            self.current_task_label = self.pending_task_labels.popleft()
        else:
            fallback_topic = getattr(demand, 'topic', None) if demand else None
            self.current_task_label = fallback_topic or kind.value.replace('_', ' ')

        # Apply flat start cost (action-energy term, separate from token cost)
        if drive and spec.delta_cost > 0:
            drive.deplete(spec.delta_cost)

        # Single-tick actions: execute LLM immediately
        if spec.ticks <= 1:
            self._run_llm_and_apply_cost(execution, drive, demand_difficulty)
            self._on_action_complete(execution, t)
            return kind.value

        # Multi-tick: store in-progress
        execution.ticks_remaining -= 1  # first tick consumed now
        self.current_action = execution
        return kind.value

    def _appraise(self, topic: str, message: str, drive: Optional[Drive]) -> AppraisedTask:
        """Agent's own difficulty appraisal of an incoming demand.

        Uses deepseek-v4-flash (no thinking) — cheap triage, ~$0.000003.
        The δ cost of this call is applied via telemetry_to_delta, making
        appraisal itself part of the metabolic economy.
        Result is cached on self.last_appraisal for UI display.
        """
        # Lightweight episodic shortcut: if we just appraised the same topic, reuse.
        if (self.last_appraisal is not None and
                getattr(self.last_appraisal, "_topic", "") == topic):
            return self.last_appraisal

        appraisal = appraise_demand(topic, message)
        appraisal._topic = topic  # type: ignore[attr-defined]
        self.last_appraisal = appraisal

        # Pay the metabolic cost of appraisal
        if drive and appraisal.telemetry.total_tokens > 0:
            d_delta = self.budgets.telemetry_to_delta(appraisal.telemetry, self._current_tick)
            drive.deplete(d_delta)

        self.emit("appraisal", {
            "agent":      self.name,
            "topic":      topic,
            "difficulty": round(appraisal.perceived_difficulty, 3),
            "kind":       appraisal.kind,
            "why":        appraisal.rationale,
            "cost_usd":   round(appraisal.telemetry.cost_usd, 6),
        })
        return appraisal

    def _enqueue_from_message(self, msg: ACLMessage) -> None:
        """Convert an ACLMessage into a demand and enqueue it.

        Only REQUEST performatives generate work. Other performatives
        (INFORM, REFUSE) are logged but don't enqueue.
        """
        if msg.performative != Performative.REQUEST:
            self.emit("message.received", {
                "agent": self.name,
                "performative": msg.performative.value,
                "sender": msg.sender,
            })
            return

        # Reconstruct a thin Demand-compatible object from the envelope content
        # (world.py Demand is not imported here to avoid circular; we use a dict-proxy)
        class _Proxy:
            pass

        proxy = _Proxy()
        proxy.id         = msg.message_id[:8]      # type: ignore[attr-defined]
        proxy.topic      = msg.content.get("topic", "unknown")  # type: ignore[attr-defined]
        proxy.message    = msg.content.get("message", "")       # type: ignore[attr-defined]
        proxy.target_aid = self.aid                              # type: ignore[attr-defined]
        proxy.envelope   = msg                                   # type: ignore[attr-defined]

        self.pending_demands.append(proxy)
        self.emit("demand.received", {
            "agent":     self.name,
            "demand_id": proxy.id,
            "topic":     proxy.topic,
            "queue_len": len(self.pending_demands),
        })

    def compute_window_saturation(self, t: int) -> float:
        """Context window saturation: prompt_tokens in rolling window vs context_budget.

        Uses prompt_tokens (not completion) as the proxy for context window growth.
        Returns [0, 1] where 1 = context_budget_tokens exhausted.
        """
        if not self.budgets._window:
            return 0.0
        cutoff = t - self.budgets.window_ticks
        active = [(tk, tl) for tk, tl in self.budgets._window if tk > cutoff]
        window_prompt = sum(tl.prompt_tokens for _, tl in active)
        return min(1.0, window_prompt / max(1, self.context_budget_tokens))

    def _run_llm_and_apply_cost(self, execution: ActionExecution,
                                  drive: Optional[Drive],
                                  demand_difficulty: float) -> None:
        """Execute LLM call with model routing; convert telemetry → δ via budgets."""
        delta     = drive.value     if drive else 0.30
        set_point = drive.set_point if drive else 0.30
        model_cfg = pick_model_for_state(
            execution.kind.value, delta, set_point, demand_difficulty
        )

        # Caveman pressure mode: activate when zone is loaded/critical OR win_sat > 0.6
        zone     = drive.get_zone() if drive else "nominal"
        win_sat  = self.compute_window_saturation(self._current_tick)
        pressure = zone in ("loaded", "critical") or win_sat > 0.6
        self.last_pressure_mode = bool(pressure)

        result, telemetry = execute_action_llm(
            execution, drive, len(self.pending_demands),
            model_cfg=model_cfg,
            pressure_mode=pressure,
        )
        execution.result = result
        self.last_telemetry = telemetry
        # Extract LLM-generated task plans and extend the pending queue
        if result:
            for lbl in (result.get("tasks_to_do") or [])[:3]:
                if isinstance(lbl, str) and lbl.strip():
                    self._add_task_label(lbl.strip())

        # Real cost feedback into δ (replaces the flat token_cost_to_delta)
        if drive and telemetry.total_tokens > 0:
            d_delta = self.budgets.telemetry_to_delta(telemetry, self._current_tick)
            drive.deplete(d_delta)
            # Session accumulators
            self.session_tokens   += telemetry.total_tokens
            self.session_cost_usd += telemetry.cost_usd
            self.session_calls    += 1
            self.emit("telemetry", {
                "agent":             self.name,
                "model":             telemetry.model,
                "tier":              telemetry.tier,
                "cost_usd":          round(telemetry.cost_usd, 6),
                "latency_ms":        telemetry.latency_ms,
                "prompt_tokens":     telemetry.prompt_tokens,
                "completion_tokens": telemetry.completion_tokens,
                "delta_increment":   round(d_delta, 4),
                "demand_difficulty": round(demand_difficulty, 3),
            })

    def _complete_action(self, execution: ActionExecution, drive: Optional[Drive], t: int) -> None:
        """Finish a multi-tick action: run LLM, apply telemetry-based cost."""
        difficulty = getattr(execution, "demand_difficulty", 0.0)
        self._run_llm_and_apply_cost(execution, drive, difficulty)
        self._on_action_complete(execution, t)

    def _on_action_complete(self, execution: ActionExecution, t: int) -> None:
        """Emit completion event and store to working memory."""
        self.emit("action.complete", {
            "agent":    self.name,
            "tick":     t,
            "action":   execution.kind.value,
            "demand":   execution.demand_id,
            "result":   execution.result,
        })

        # Proact: symbolic pre-commit check before emitting to human
        if execution.kind == ActionKind.PROACT and execution.result:
            inform_text = execution.result.get("inform", "")
            priority    = execution.result.get("priority", "low")
            if inform_text:
                ok, reason = check_proact_proposal(self, inform_text, priority)
                if ok:
                    self.last_proact_message = inform_text
                    self.emit("proact.inform", {
                        "agent":    self.name,
                        "tick":     t,
                        "message":  inform_text,
                        "priority": priority,
                    })
                else:
                    self.emit("proact.rejected", {
                        "agent":   self.name,
                        "tick":    t,
                        "reason":  reason,
                        "message": inform_text[:60],
                    })

        # Move current task label to done
        if self.current_task_label:
            self.done_task_labels.append(self.current_task_label)
            self.current_task_label = None

        # Track deferred actions for session KPI
        if execution.kind == ActionKind.DEFER:
            self.session_deferred += 1

        self.remember({
            "type":   "action",
            "action": execution.kind.value,
            "demand": execution.demand_id,
        })

    # ── Event System ─────────────────────────────────────────────────────────────

    def on(self, event_type: str, handler: Callable[[Any], None]) -> None:
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Optional[Callable] = None) -> None:
        if event_type in self._event_handlers:
            if handler is None:
                self._event_handlers[event_type] = []
            else:
                self._event_handlers[event_type] = [
                    h for h in self._event_handlers[event_type] if h != handler
                ]

    def emit(self, event_type: str, payload: Any) -> None:
        """Emit event — no implicit drive coupling (explicit in tick loop)."""
        for handler in self._event_handlers.get(event_type, []):
            try:
                handler(payload)
            except Exception as e:
                print(f"[{self.name}] handler error for {event_type}: {e}")

        envelope = {
            "type":       event_type,
            "source":     self.aid,
            "agent_name": self.name,
            "payload":    payload,
        }
        for handler in self._global_event_handlers:
            try:
                handler(envelope)
            except Exception as e:
                print(f"[{self.name}] global handler error for {event_type}: {e}")

    def on_any(self, handler: Callable[[Any], None]) -> None:
        self._global_event_handlers.append(handler)

    def off_any(self, handler: Callable[[Any], None]) -> None:
        self._global_event_handlers = [h for h in self._global_event_handlers if h != handler]

    def subscribe_to(self, other: "BinsaiAgent") -> None:
        self._subscribed_agents[other.aid] = other
        other.on_any(self._handle_external_event)

    def unsubscribe_from(self, other: "BinsaiAgent") -> None:
        if other.aid in self._subscribed_agents:
            del self._subscribed_agents[other.aid]
            other.off_any(self._handle_external_event)

    def _handle_external_event(self, event: Any) -> None:
        source     = event.get("source")
        event_type = event.get("type")
        payload    = event.get("payload", {})
        if source not in self._subscribed_agents:
            return
        for handler in self._event_handlers.get(event_type, []):
            try:
                handler(payload)
            except Exception as e:
                print(f"[{self.name}] external handler error for {event_type}: {e}")

    # ── Sensors: message reception ───────────────────────────────────────────────

    def receive_message(self, msg: ACLMessage) -> Optional[ACLMessage]:
        """FIPA sensor: route incoming ACL message via lifecycle-aware mailbox.

        ACTIVE  → message goes to inbox, drained next tick.
        SUSPENDED → message goes to mailbox.buffered (default policy).
        Returns a refusal reply ACLMessage if the mailbox generates one (policy="refuse").
        """
        is_suspended = self._lifecycle.is_suspended()
        return self.mailbox.deliver(msg, is_suspended=is_suspended)

    def receive_demand(self, demand: Any) -> None:
        """Legacy entry point kept for world.py backward compatibility.

        If the demand has a FIPA envelope, routes through receive_message.
        Otherwise falls back to direct queue append (lifecycle-aware).
        """
        envelope = getattr(demand, "envelope", None)
        if envelope is not None:
            self.receive_message(envelope)
            return
        # Bare demand without envelope (legacy): apply lifecycle gate manually
        if self._lifecycle.is_suspended():
            # Create a minimal envelope and buffer it
            from .world.dummy_human import HUMAN_AID
            env = ACLMessage(
                performative=Performative.REQUEST,
                sender=HUMAN_AID,
                receiver=self.aid,
                content={
                    "topic":   getattr(demand, "topic", "unknown"),
                    "message": getattr(demand, "message", ""),
                },
            )
            demand.envelope = env
            self.mailbox.buffered.append(env)
            return
        self.pending_demands.append(demand)
        self.emit("demand.received", {
            "agent":     self.name,
            "demand_id": getattr(demand, "id", str(demand)),
            "topic":     getattr(demand, "topic", None),
            "queue_len": len(self.pending_demands),
        })

    # ── Working Memory ────────────────────────────────────────────────────────────

    def remember(self, item: dict) -> None:
        import time
        self._working_memory.append({**item, "ts": time.time()})
        if len(self._working_memory) > self._max_wm_size:
            self._working_memory = self._working_memory[-self._max_wm_size:]

    def recall_recent(self, n: int = 3) -> list[dict]:
        return self._working_memory[-n:]

    def consolidate(self) -> int:
        """Offline memory consolidation: trim to 3 most recent items."""
        if len(self._working_memory) <= 3:
            return 0
        removed = len(self._working_memory) - 3
        self._working_memory = self._working_memory[-3:]
        return removed

    # ── Introspection ─────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        drive = self.drives.get("metabolic")
        return {
            "aid":        self.aid,
            "name":       self.name,
            "status":     self.status,
            "delta":      round(drive.value, 4) if drive else None,
            "zone":       drive.get_zone() if drive else None,
            "memberships": drive.zone_memberships() if drive else {},
            "queue":      len(self.pending_demands),
            "action":     self.current_action.kind.value if self.current_action else None,
            "position":   {"x": self.position.x, "y": self.position.y},
        }

    def __repr__(self) -> str:
        return (
            f"BinsaiAgent({self.name}#{self.aid}, "
            f"status={self.status}, "
            f"δ={self.drives.get('metabolic').value:.3f if self.drives.get('metabolic') else '?'})"
        )
