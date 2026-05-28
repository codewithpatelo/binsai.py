"""World — orchestrator for the MVP1 "Inbox bajo presión" simulation.

World.step() advances one tick:
    1. Clock ticks
    2. DummyHuman generates demands (as ACL REQUEST envelopes) → routed to agent mailboxes
    3. Each agent executes agent.tick(t, world)
    4. WorldFrame assembled and returned

WorldFrame is JSON-serializable and sent verbatim to the frontend via WebSocket.
Demand difficulty is NOT in the WorldFrame — the agent appraises it itself (appraisal
is returned in the AgentFrame as perceived_difficulty).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from ..agent import BinsaiAgent, Position
from ..drives import Drives
from ..clock import StepClock
from .dummy_human import DummyHuman, Demand


@dataclass
class AgentConfig:
    """Per-agent physical parameters for heterogeneity."""
    name:            str
    lambda_override: float | None = None
    initial_delta:   float        = 0.30
    temperature:     float        = 1.0
    ablation_off:    bool         = False   # per-agent regulation toggle


@dataclass
class WorldConfig:
    """Complete simulation configuration — deterministic from seed alone."""
    seed:           int                  = 42
    lambda_demand:  float                = 0.5
    ablation_off:   bool                 = False   # global override (all agents)
    dry_run_llm:    bool                 = False   # real LLM calls by default
    speed:          float                = 2.0
    agents: list[AgentConfig] = field(default_factory=lambda: [
        AgentConfig(name="Alpha", lambda_override=0.004, initial_delta=0.28, temperature=0.8),
        AgentConfig(name="Beta",  lambda_override=0.006, initial_delta=0.30, temperature=1.0),
        AgentConfig(name="Gamma", lambda_override=0.008, initial_delta=0.32, temperature=1.2,
                    ablation_off=True),   # Gamma starts unregulated for ablation comparison
    ])


@dataclass
class AgentFrame:
    """Snapshot of one agent at one tick."""
    aid:                  str
    name:                 str
    status:               str
    delta:                float | None
    zone:                 str | None
    memberships:          dict[str, float]
    queue:                int
    buffered:             int             # messages buffered during SUSPENDED
    action:               str | None
    position:             dict[str, float]
    # LLM telemetry from last call (None until first call completes)
    last_model:           str | None
    last_tier:            str | None
    last_cost_usd:        float | None
    last_latency_ms:      int | None
    last_tokens:          int | None
    # Agent's own appraisal of next pending demand (not world-labelled)
    perceived_difficulty: float | None
    appraisal_kind:       str | None
    # Backlog: topic strings for next up to 3 pending demands
    backlog:              list[str]
    # Proactive INFORM sent to human this tick (None if no proact completed)
    proact_message:       str | None
    # Rolling window saturation [0,1] — 0 = empty (post-sleep), 1 = budget exhausted
    window_saturation:    float | None
    # Per-agent regulation state (ablation)
    ablation_off:         bool
    # Session accumulators (for comparative KPI)
    session_tokens:       int
    session_cost_usd:     float
    session_calls:        int
    session_deferred:     int
    # Token-minimization (caveman) pressure flag — UI badge
    pressure_mode:        bool
    # Last sleep consolidation summary (consumed once per frame)
    consolidation_summary: str | None
    # Effective context-window prompt-token usage (for explicit display)
    context_used_tokens:  int
    context_budget_tokens: int
    # Kanban task tracking — fed from LLM tasks_to_do output
    pending_task_labels:  list[str]
    current_task_label:   str | None
    done_task_labels:     list[str]


@dataclass
class WorldFrame:
    """Complete snapshot of one tick — sent to frontend as JSON."""
    tick:    int
    agents:  list[AgentFrame]
    demands: list[dict]   # ACL envelope summary (no difficulty — that's agent-side)
    events:  list[dict]
    config:  dict


class World:
    """Deterministic simulation world."""

    def __init__(self, config: WorldConfig | None = None) -> None:
        self.config = config or WorldConfig()
        self._rng   = random.Random(self.config.seed)
        self._clock = StepClock(seed=self.config.seed)
        self._events_this_tick: list[dict] = []

        self.agents = self._build_agents()
        self.dummy_human = DummyHuman(
            targets=self.agents,
            lambda_demand=self.config.lambda_demand,
            rng=random.Random(self.config.seed + 1),
        )

        for agent in self.agents:
            agent.activate()

    def _build_agents(self) -> list[BinsaiAgent]:
        agents = []
        for i, cfg in enumerate(self.config.agents):
            drives   = Drives.from_names(["metabolic"])
            metabolic = drives.get("metabolic")
            if metabolic:
                metabolic.value = cfg.initial_delta

            # Per-agent ablation: agent's own flag OR global override
            agent_ablation = cfg.ablation_off or self.config.ablation_off
            agent = BinsaiAgent(
                name=cfg.name,
                drives=drives,
                position=Position(x=float(i * 200 + 100), y=300.0),
                lambda_override=cfg.lambda_override,
                ablation_off=agent_ablation,
                temperature=cfg.temperature,
                rng=random.Random(self.config.seed + 100 + i),
            )
            agent.on_any(self._capture_event)
            agents.append(agent)
        return agents

    def _capture_event(self, envelope: dict) -> None:
        self._events_this_tick.append(envelope)

    def step(self) -> WorldFrame:
        """Advance one tick. Returns serializable WorldFrame."""
        self._events_this_tick = []
        t = self._clock.tick()

        # Generate demands as ACL REQUEST envelopes — route via agent.receive_demand()
        # which is lifecycle-aware: suspended agents buffer, active agents enqueue.
        demands_this_tick: list[Demand] = self.dummy_human.tick(t)
        demand_dicts: list[dict] = []

        for demand in demands_this_tick:
            target = next(
                (a for a in self.agents if a.aid == demand.target_aid), None
            )
            if target:
                demand.mark_received(t)
                target.receive_demand(demand)   # routes via mailbox + lifecycle gate

            # WorldFrame includes only what the world knows — no difficulty label
            demand_dicts.append({
                "id":          demand.id,
                "target_aid":  demand.target_aid,
                "target_name": demand.target_name,
                "topic":       demand.topic,
                "message":     demand.message,
                "performative": demand.envelope.performative.value if demand.envelope else "request",
                "t_emitted":   demand.t_emitted,
            })

        for agent in self.agents:
            agent.tick(t, world=self)

        agent_frames = []
        for a in self.agents:
            telem   = a.last_telemetry
            apprais = a.last_appraisal
            backlog = [
                getattr(d, "topic", "?")
                for d in list(a.pending_demands)[:3]
            ]
            # Proact message (consume once per frame — reset so it only fires once)
            proact_msg = a.last_proact_message
            a.last_proact_message = None

            # Window saturation via prompt_tokens (context window proxy)
            win_sat = round(a.compute_window_saturation(t), 3)
            # Effective prompt tokens in rolling window (for ctx display)
            cutoff = t - a.budgets.window_ticks
            ctx_used = sum(
                tl.prompt_tokens
                for tk, tl in a.budgets._window
                if tk > cutoff
            )
            # Consume consolidation summary once per frame
            cons_summary = a.last_consolidation_summary
            a.last_consolidation_summary = None

            agent_frames.append(AgentFrame(
                aid=a.aid,
                name=a.name,
                status=a.status,
                delta=round(a.drives.get("metabolic").value, 4) if a.drives.get("metabolic") else None,
                zone=a.drives.get("metabolic").get_zone() if a.drives.get("metabolic") else None,
                memberships={
                    k: round(v, 4)
                    for k, v in (a.drives.get("metabolic").zone_memberships() if a.drives.get("metabolic") else {}).items()
                },
                queue=len(a.pending_demands),
                buffered=len(a.mailbox.buffered),
                action=(
                    "sleep" if a.status == "suspended"
                    else (a.current_action.kind.value if a.current_action else "idle")
                ),
                position={"x": a.position.x, "y": a.position.y},
                last_model=telem.model if telem else None,
                last_tier=telem.tier if telem else None,
                last_cost_usd=round(telem.cost_usd, 6) if telem else None,
                last_latency_ms=telem.latency_ms if telem else None,
                last_tokens=telem.total_tokens if telem else None,
                perceived_difficulty=round(apprais.perceived_difficulty, 3) if apprais else None,
                appraisal_kind=apprais.kind if apprais else None,
                backlog=backlog,
                proact_message=proact_msg,
                window_saturation=win_sat,
                ablation_off=a.ablation_off,
                session_tokens=a.session_tokens,
                session_cost_usd=round(a.session_cost_usd, 6),
                session_calls=a.session_calls,
                session_deferred=a.session_deferred,
                pressure_mode=a.last_pressure_mode,
                consolidation_summary=cons_summary,
                context_used_tokens=ctx_used,
                context_budget_tokens=a.context_budget_tokens,
                pending_task_labels=list(a.pending_task_labels),
                current_task_label=a.current_task_label,
                done_task_labels=list(a.done_task_labels),
            ))

        # KPI comparison: regulated vs unregulated session totals
        reg   = [a for a in self.agents if not a.ablation_off]
        unreg = [a for a in self.agents if a.ablation_off]
        reg_tok   = sum(a.session_tokens   for a in reg)
        unreg_tok = sum(a.session_tokens   for a in unreg)
        reg_cost  = sum(a.session_cost_usd for a in reg)
        unreg_cost= sum(a.session_cost_usd for a in unreg)

        return WorldFrame(
            tick=t,
            agents=agent_frames,
            demands=demand_dicts,
            events=list(self._events_this_tick),
            config={
                "lambda_demand":        self.config.lambda_demand,
                "ablation_off":         self.config.ablation_off,
                "speed":                self.config.speed,
                "kpi_reg_tokens":       reg_tok,
                "kpi_unreg_tokens":     unreg_tok,
                "kpi_reg_cost_usd":     round(reg_cost, 6),
                "kpi_unreg_cost_usd":   round(unreg_cost, 6),
            },
        )

    def toggle_ablation(self) -> bool:
        """Toggle global ablation (all agents)."""
        self.config.ablation_off = not self.config.ablation_off
        for agent, cfg in zip(self.agents, self.config.agents):
            agent.ablation_off = self.config.ablation_off or cfg.ablation_off
        return self.config.ablation_off

    def toggle_ablation_agent(self, aid: str) -> bool:
        """Toggle per-agent ablation. Returns new ablation_off value for that agent."""
        for agent, cfg in zip(self.agents, self.config.agents):
            if agent.aid == aid:
                cfg.ablation_off = not cfg.ablation_off
                agent.ablation_off = cfg.ablation_off or self.config.ablation_off
                return agent.ablation_off
        raise ValueError(f"Agent {aid!r} not found")

    def set_lambda_demand(self, value: float) -> None:
        self.config.lambda_demand      = value
        self.dummy_human.lambda_demand = value

    def reset(self) -> None:
        self.__init__(self.config)
