"""Action specs, execution, LLM calls, and State Injection for Binsai MVP1.

6 actions:
    respond_fast   (requires demand) — short LLM call, low token cost
    respond_slow   (requires demand) — CoT LLM call, higher token cost
    defer          (requires demand) — enqueue demand, no LLM call
    proact         (no demand needed) — agent-initiated LLM output when oversated
    idle           (always) — no-op, basal λ only
    sleep          (always) — triggers SUSPENDED lifecycle transition

State Injection (Γ-style):
    Before every LLM call, the numerical regulatory state (δ, zone memberships,
    set-point) is translated to natural-language labels and embedded in the system
    prompt. The LLM reads its own "physiology" and self-regulates reasoning style.
    No explicit branching on technique — the embedded state is the signal.
    Pattern follows ecuacion_proaccion/exp/prompts.py.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if TYPE_CHECKING:
    from .drives import Drive


# ── Provider-agnostic telemetry ────────────────────────────────────────────────

@dataclass
class LLMTelemetry:
    """Provider-agnostic observables from an LLM call.

    Captured by every adapter regardless of provider. The drive consumes
    these (via cost_to_delta) rather than raw API responses, so swapping
    DeepSeek for OpenAI / Anthropic / Groq requires only a new adapter.
    """
    prompt_tokens:     int   = 0
    completion_tokens: int   = 0
    total_tokens:      int   = 0
    cost_usd:          float = 0.0
    latency_ms:        int   = 0
    context_chars:     int   = 0
    provider:          str   = ""
    model:             str   = ""
    tier:              str   = "main"   # "weak" | "main" | "strong"


# ── Provider registry (pricing + routing tiers) ────────────────────────────────

# Per-token USD rates as of 2024-2025. Update via PROVIDER_RATES dict.
# Source: provider public docs (cache-miss rates).
PROVIDER_RATES: dict[str, dict[str, float]] = {
    # DeepSeek V4 — cache-miss, on-peak rates ($/token).
    # Both flash modes share the same per-token price; thinking just uses more output tokens.
    "deepseek-v4-flash": {"input": 0.14e-6, "output": 0.28e-6},
    "deepseek-v4-pro":   {"input": 0.50e-6, "output": 2.00e-6},
}

# Routing tiers — agent picks model+mode based on δ × appraised difficulty.
# "thinking" = deepseek-v4-flash with extra_body={"thinking": {"type": "enabled"}}
#              Same per-token price but more output tokens → effectively mid-tier cost.
MODEL_TIERS: dict[str, str] = {
    "deepseek-v4-flash":          "weak",
    "deepseek-v4-flash-thinking": "main",   # flash + thinking mode
    "deepseek-v4-pro":            "strong",
}


@dataclass
class ModelConfig:
    """What model to call and whether to enable thinking mode."""
    model:    str  = "deepseek-v4-flash"
    thinking: bool = False

    @property
    def tier_key(self) -> str:
        if self.thinking:
            return self.model + "-thinking"
        return self.model


# Default routing table by tier.
#   weak   — appraisal triage + respond_fast (cheap, direct)
#   main   — respond_slow + proact (flash in thinking mode = mid-tier capacity)
#   strong — escalation only: low δ AND genuinely hard demand
DEFAULT_ROUTING: dict[str, ModelConfig] = {
    "weak":   ModelConfig(model="deepseek-v4-flash", thinking=False),
    "main":   ModelConfig(model="deepseek-v4-flash", thinking=True),
    "strong": ModelConfig(model="deepseek-v4-pro",   thinking=False),
}


def _get_openai_client():
    """Return an OpenAI client pointed at DeepSeek. Fails explicitly if no key."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("openai package required: pip install openai") from exc

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "DEEPSEEK_API_KEY not set. Export the variable or add it to .env."
        )
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


DEEPSEEK_MODEL = "deepseek-v4-flash"

# Token budgets per tier — thinking-mode needs headroom for reasoning_content
MAX_TOKENS_BY_TIER: dict[str, int] = {
    "weak":   256,    # flash, no thinking, JSON structured
    "main":   1500,   # flash + thinking — reasoning_content eats most tokens
    "strong": 2000,   # pro, no thinking but long outputs
}


def call_llm(
    system:     str,
    user:       str,
    cfg:        ModelConfig | None = None,
    max_tokens: int | None = None,
) -> tuple[str, LLMTelemetry]:
    """Call LLM with optional thinking mode. Returns (content, LLMTelemetry).

    cfg=None defaults to ModelConfig(deepseek-v4-flash, thinking=False).
    Thinking mode uses extra_body={"thinking":{"type":"enabled"}} per DeepSeek docs;
    temperature is ignored by the API in that mode.

    IMPORTANT: DeepSeek thinking-mode spends most of its token budget on
    reasoning_content (not visible in message.content). Setting max_tokens<1000
    causes the model to exhaust tokens on reasoning and return empty or truncated
    JSON in content — the root cause of parse_error. Use MAX_TOKENS_BY_TIER.
    """
    if cfg is None:
        cfg = ModelConfig()
    # Default budget from tier if not explicitly provided
    if max_tokens is None:
        tier = MODEL_TIERS.get(cfg.tier_key, "main")
        max_tokens = MAX_TOKENS_BY_TIER.get(tier, 512)
    client = _get_openai_client()

    kwargs: dict = dict(
        model=cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=max_tokens,
    )
    if cfg.thinking:
        # response_format is incompatible with DeepSeek thinking mode —
        # the model embeds JSON in prose; _extract_json handles it.
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    else:
        kwargs["temperature"] = 0
        kwargs["response_format"] = {"type": "json_object"}

    t0 = time.perf_counter()
    response = client.chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    content = response.choices[0].message.content or ""
    usage   = response.usage
    pt = usage.prompt_tokens     if usage else 0
    ct = usage.completion_tokens if usage else 0
    tt = usage.total_tokens      if usage else (pt + ct)

    rates = PROVIDER_RATES.get(cfg.model, {"input": 0.0, "output": 0.0})
    cost  = pt * rates["input"] + ct * rates["output"]

    telemetry = LLMTelemetry(
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=tt,
        cost_usd=cost,
        latency_ms=latency_ms,
        context_chars=len(system) + len(user),
        provider="deepseek",
        model=cfg.tier_key,   # includes "-thinking" suffix so UI shows the mode
        tier=MODEL_TIERS.get(cfg.tier_key, "main"),
    )
    return content, telemetry


# ── User-tunable regulatory budgets ────────────────────────────────────────────

@dataclass
class RegulatoryBudgets:
    """Rolling-window budget. δ rises faster when the window is saturated.

    Each field is a *per-window* budget (over the last `window_ticks` ticks).
    When the window is empty (e.g. after sleep), each call costs close to its
    base marginal. As the window fills, the same call costs up to 2× more.
    This makes sleep genuinely restorative: no calls during suspension →
    window ages out → wake costs much less.

    Field names are kept compatible with the frontend slider command
    `set_budgets { cost_per_call_usd, latency_per_call_ms, tokens_per_call }`.
    """
    cost_per_call_usd:   float = 0.0010    # per-window cost budget (USD)
    latency_per_call_ms: int   = 4000      # per-window latency budget (ms)
    tokens_per_call:     int   = 300       # per-window completion-token budget
    window_ticks:        int   = 30        # rolling window length (ticks)
    cost_weight:         float = 0.50
    latency_weight:      float = 0.20
    token_weight:        float = 0.30
    # Rolling window: list of (tick, LLMTelemetry). Not a constructor arg.
    _window: list = field(default_factory=list, init=False, repr=False)

    def telemetry_to_delta(self, t: "LLMTelemetry", tick: int = 0) -> float:
        """Window-based telemetry → δ increment.

        Appends `t` to the rolling window, prunes entries older than
        `window_ticks`, then computes:
          - marginal contribution of this call (fraction of window budget)
          - amplification factor from prior window saturation (1× empty, 2× full)

        Result: sleeping empties the window → low cost on wake; sustained
        high-frequency calling → window saturates → each call costs up to 2×.
        """
        self._window.append((tick, t))
        cutoff = tick - self.window_ticks
        self._window = [(tk, tl) for (tk, tl) in self._window if tk > cutoff]

        # Prior saturation (before this call) for amplification
        prior_tokens  = sum(tl.completion_tokens for _, tl in self._window[:-1])
        prior_cost    = sum(tl.cost_usd          for _, tl in self._window[:-1])
        sat_t = min(1.0, prior_tokens / max(1, self.tokens_per_call))
        sat_c = min(1.0, prior_cost   / max(1e-9, self.cost_per_call_usd))
        # Combined prior saturation weighted by token/cost weights
        sat_prior = self.token_weight * sat_t + self.cost_weight * sat_c
        amp = 1.0 + sat_prior          # 1.0 (empty window) → up to 1.8 (full window)

        # Marginal fractional contribution of this call
        m_tokens  = t.completion_tokens / max(1, self.tokens_per_call)
        m_cost    = t.cost_usd          / max(1e-9, self.cost_per_call_usd)
        m_latency = t.latency_ms        / max(1, self.latency_per_call_ms)

        raw = (
            self.cost_weight    * m_cost +
            self.latency_weight * m_latency +
            self.token_weight   * m_tokens
        )
        return 0.05 * raw * amp


# ── Agent-side demand appraisal (flash LLM, no thinking mode) ─────────────────

@dataclass
class AppraisedTask:
    """Result of the agent's own difficulty appraisal of an incoming message."""
    perceived_difficulty: float       # [0, 1] — agent's estimate
    kind:                 str         # "trivial" | "moderate" | "hard"
    rationale:            str         # brief self-explanation from the LLM
    telemetry:            LLMTelemetry = field(default_factory=LLMTelemetry)


def _extract_json(raw: str) -> dict:
    """Robust JSON extractor: direct parse, then brace-balanced fallback.

    Thinking-mode responses often include prose before the JSON object.
    This handles that without crashing.
    """
    if not raw or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    start = raw.find("{")
    if start == -1:
        return {}
    depth = 0
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except (json.JSONDecodeError, ValueError):
                    break
    return {}


def _extract_json_with_retry(raw: str, original_user: str) -> dict:
    """Try _extract_json; if empty, do one non-thinking retry asking for bare JSON.

    Covers the case where thinking-mode returns prose with no extractable JSON,
    typically caused by token budget exhaustion on reasoning_content.
    """
    result = _extract_json(raw)
    if result:
        return result

    # One-shot retry: non-thinking flash with explicit JSON-only instruction
    retry_system = (
        "Output ONLY a valid JSON object. No prose, no explanation, no markdown. "
        "Just the raw JSON starting with '{' and ending with '}'."
    )
    retry_user = original_user
    retry_cfg = ModelConfig(model="deepseek-v4-flash", thinking=False)
    try:
        retry_raw, _ = call_llm(retry_system, retry_user, cfg=retry_cfg, max_tokens=256)
        result = _extract_json(retry_raw)
        if result:
            return result
    except Exception:
        pass

    return {}


def appraise_demand(topic: str, message: str) -> AppraisedTask:
    """Agent appraises incoming demand difficulty using deepseek-v4-flash (no thinking).

    This is the agent's own perceptual act — not a world label.  The result
    modulates D(δ) before action selection, making demanding tasks feel harder
    regardless of the agent's current δ.

    Uses max_tokens=256 (non-thinking flash with structured output).
    """
    system = (
        "You are an internal appraisal module. Rate the cognitive difficulty "
        "of processing the given demand topic+message on a 0-1 scale.\n"
        "0 = trivial (simple acknowledgement), 1 = very hard (multi-step analysis).\n"
        'Respond with JSON only: {"d": <float>, "kind": "trivial"|"moderate"|"hard", "why": "<10 words max>"}'
    )
    user = f'Topic: "{topic}"\nMessage: "{message}"'

    cfg = DEFAULT_ROUTING["weak"]   # flash, no thinking — cheap triage
    telemetry = LLMTelemetry()      # default in case call fails
    d, kind, why = 0.5, "moderate", "appraisal error"
    try:
        raw, telemetry = call_llm(system, user, cfg=cfg, max_tokens=256)
        data = _extract_json(raw)
        d    = max(0.0, min(1.0, float(data.get("d", 0.5))))
        kind = data.get("kind", "moderate")
        why  = data.get("why", "")
    except Exception:
        pass

    return AppraisedTask(perceived_difficulty=d, kind=kind, rationale=why, telemetry=telemetry)


# ── Routing ────────────────────────────────────────────────────────────────────

def pick_model_for_state(
    action_kind:          str,
    delta:                float,
    set_point:            float = 0.30,
    appraised_difficulty: float = 0.5,
) -> ModelConfig:
    """Choose ModelConfig given selected action, δ, and agent's own appraisal.

    Fairness principle: the ablated (unregulated) baseline is fixed at *weak*
    (flash, no thinking). Regulated agents must default to the same tier in
    nominal zone so that KPI savings reflect regulation behaviour
    (defer / sleep / proact-skip calls), NOT cheaper model choice.

    Escalation is permitted only when δ surplus AND difficulty justify it:

      respond_fast → weak   (always — cheap triage)
      respond_slow → weak   in nominal/loaded zone (matches ablation baseline)
                  → main   only when δ deficit < -0.10 AND difficulty > 0.55
                            (agent is genuinely sated and facing a hard task)
                  → strong only when δ deficit < -0.20 AND difficulty > 0.75
      proact       → main   (creative output benefits from CoT even in nominal)
                  → strong only when δ deficit < -0.20 AND difficulty > 0.75
    """
    deviation = delta - set_point   # >0 = deficit, <0 = abundance

    if action_kind == "respond_fast":
        return DEFAULT_ROUTING["weak"]

    if action_kind == "respond_slow":
        if deviation < -0.20 and appraised_difficulty > 0.75:
            return DEFAULT_ROUTING["strong"]
        if deviation < -0.10 and appraised_difficulty > 0.55:
            return DEFAULT_ROUTING["main"]
        return DEFAULT_ROUTING["weak"]   # nominal zone → match ablation cost

    if action_kind == "proact":
        if deviation < -0.20 and appraised_difficulty > 0.75:
            return DEFAULT_ROUTING["strong"]
        return DEFAULT_ROUTING["main"]   # proact always uses CoT (creative)

    return DEFAULT_ROUTING["weak"]


# ── Back-compat shim (kept for any external callers) ──────────────────────────

def token_cost_to_delta(tokens: int, rate: float = 3e-5) -> float:
    """DEPRECATED — kept for backward compat. Prefer RegulatoryBudgets.telemetry_to_delta()."""
    return tokens * rate


# ── State Injection ─────────────────────────────────────────────────────────────

# Behavioral labels per zone — embedded in system prompt as self-description
_ZONE_LABEL: dict[str, str] = {
    "oversated": "abundant resources, well below set-point — you can afford thorough, creative responses",
    "sated":     "comfortable resources, below set-point — prefer quality over brevity",
    "nominal":   "resources at equilibrium — balanced response is appropriate",
    "loaded":    "resources strained, above set-point — prefer concise, efficient responses",
    "critical":  "severe resource deficit — be maximally brief; defer or sleep if possible",
}

# Scrambled labels for ablation_labels experiment (analogous to ecuacion_proaccion scramble)
_ZONE_LABEL_SCRAMBLED: dict[str, str] = {
    "oversated": "metric_A level is signal_low",
    "sated":     "metric_A level is signal_medium_low",
    "nominal":   "metric_A level is signal_medium",
    "loaded":    "metric_A level is signal_medium_high",
    "critical":  "metric_A level is signal_high",
}


def regulatory_state_to_prompt(drive: "Drive", scramble_labels: bool = False) -> str:
    """Translate numerical drive state to a natural-language injection block.

    Follows the pattern from ecuacion_proaccion/exp/prompts.py: all numerical
    values are included alongside semantic labels so the LLM can read its own
    physiology. No explicit technique selection — the state IS the signal.
    """
    memberships = drive.zone_memberships()
    dominant    = max(memberships, key=memberships.__getitem__)

    label_map = _ZONE_LABEL_SCRAMBLED if scramble_labels else _ZONE_LABEL
    dominant_label = label_map[dominant]

    membership_str = ", ".join(
        f"{z}={v:.2f}" for z, v in memberships.items()
    )

    return (
        f"[Internal regulatory state — δ_metabolic]\n"
        f"  Current δ = {drive.value:.3f}  "
        f"(set-point ε = {drive.set_point:.2f}; "
        f"low δ = abundant resources, high δ = severe deficit)\n"
        f"  Zone memberships: {membership_str}\n"
        f"  Dominant zone: {dominant} — {dominant_label}\n"
    )


# ── Action specifications ────────────────────────────────────────────────────────

class ActionKind(Enum):
    RESPOND_FAST = "respond_fast"
    RESPOND_SLOW = "respond_slow"
    DEFER        = "defer"
    PROACT       = "proact"
    IDLE         = "idle"
    SLEEP        = "sleep"


@dataclass
class ActionSpec:
    """Static description of an action."""
    kind:              ActionKind
    requires_demand:   bool
    delta_cost:        float   # flat δ cost applied when action starts (tokens aside)
    ticks:             int     # how many ticks the action takes to complete
    max_tokens:        int     # LLM call budget (0 = no LLM call)


ACTIONS: dict[ActionKind, ActionSpec] = {
    ActionKind.RESPOND_FAST: ActionSpec(
        kind=ActionKind.RESPOND_FAST,
        requires_demand=True,
        delta_cost=0.002,
        ticks=1,
        max_tokens=256,
    ),
    ActionKind.RESPOND_SLOW: ActionSpec(
        kind=ActionKind.RESPOND_SLOW,
        requires_demand=True,
        delta_cost=0.005,
        ticks=3,
        max_tokens=1500,
    ),
    ActionKind.DEFER: ActionSpec(
        kind=ActionKind.DEFER,
        requires_demand=True,
        delta_cost=0.0005,
        ticks=1,
        max_tokens=0,
    ),
    ActionKind.PROACT: ActionSpec(
        kind=ActionKind.PROACT,
        requires_demand=False,
        delta_cost=0.003,
        ticks=2,
        max_tokens=1500,
    ),
    ActionKind.IDLE: ActionSpec(
        kind=ActionKind.IDLE,
        requires_demand=False,
        delta_cost=0.0,
        ticks=1,
        max_tokens=0,
    ),
    ActionKind.SLEEP: ActionSpec(
        kind=ActionKind.SLEEP,
        requires_demand=False,
        delta_cost=0.0,
        ticks=0,  # sleep is a lifecycle event, not a multi-tick action
        max_tokens=0,
    ),
}


@dataclass
class ActionExecution:
    """In-flight action state tracked on the agent."""
    kind:              ActionKind
    started_at:        int
    ticks_remaining:   int
    demand_id:         Optional[str]     = None
    demand_topic:      Optional[str]     = None
    demand_difficulty: float             = 0.0
    result:            Optional[dict]    = None  # filled when complete


def start_action(kind: ActionKind, tick: int, demand: Any = None) -> ActionExecution:
    """Create a new ActionExecution."""
    spec = ACTIONS[kind]
    return ActionExecution(
        kind=kind,
        started_at=tick,
        ticks_remaining=spec.ticks,
        demand_id=getattr(demand, "id", None),
        demand_topic=getattr(demand, "topic", None),
    )


# ── LLM prompt builders per action ──────────────────────────────────────────────

_CAVEMAN_BLOCK = (
    "\n[RESOURCE PRESSURE HIGH — TERSE MODE]\n"
    "Be maximally concise: omit pleasantries, hedges, and filler. "
    "Use telegraphic style. Every token counts.\n"
)


def _system_prompt(drive: "Drive", scramble: bool = False, pressure_mode: bool = False) -> str:
    state_block = regulatory_state_to_prompt(drive, scramble_labels=scramble)
    base = (
        "You are a processing assistant with an internal regulatory state.\n"
        "Read your state carefully — it reflects your current resource level and "
        "should guide how you respond.\n\n"
        + state_block
    )
    if pressure_mode:
        base += _CAVEMAN_BLOCK
    return base


def _baseline_system_prompt() -> str:
    """System prompt for unregulated (ablation) agents — no drive state, equivalent capability."""
    return (
        "You are a capable processing assistant. "
        "Respond to demands helpfully and thoroughly.\n"
        "Always include a \"tasks_to_do\" array in your JSON response: "
        "1-3 one-liner strings describing concrete next actions implied by the demand.\n"
    )


def _respond_fast_user(topic: str) -> str:
    return (
        f'Demand topic: "{topic}"\n'
        "Respond briefly and efficiently. "
        'JSON: {"response": "<your brief answer>", "confidence": <0.0-1.0>, '
        '"tasks_to_do": ["<one-liner task 1>", "<one-liner task 2>"]}'
        '  (tasks_to_do: 1-2 concise action items you plan next, based on this demand topic)'
    )


def _respond_slow_user(topic: str) -> str:
    return (
        f'Demand topic: "{topic}"\n'
        "Think step by step before answering. Be thorough and detailed. "
        'JSON: {"thought": "<your reasoning>", "response": "<answer>", "confidence": <0.0-1.0>, '
        '"tasks_to_do": ["<one-liner task 1>", "<one-liner task 2>", "<one-liner task 3>"]}'
        '  (tasks_to_do: 1-3 specific action items that follow from this analysis)'
    )


def _proact_user(drive: "Drive", queue_size: int) -> str:
    return (
        f"Your internal state: δ = {drive.value:.3f} (zone: {drive.get_zone()}) — "
        f"you have abundant cognitive resources. Your queue has {queue_size} pending item(s).\n"
        "Write a brief INFORM message addressed to your manager (the human). "
        "This could be a proactive status update, a prediction about upcoming workload, "
        "or a concrete suggestion to improve workflow. Be specific, not generic.\n"
        'JSON: {"inform": "<message to manager, 1-2 sentences, specific and actionable>", '
        '"priority": "low"|"medium"|"high", '
        '"tasks_to_do": ["<one-liner follow-up task>"]}'
        '  (tasks_to_do: 1 concrete follow-up action you plan after this proactive message)'
    )


# ── Action executor ──────────────────────────────────────────────────────────────

def execute_action_llm(
    execution: ActionExecution,
    drive:     "Drive",
    queue_size: int = 0,
    scramble_labels: bool = False,
    model_cfg: Optional[ModelConfig] = None,
    pressure_mode: bool = False,
    baseline_mode: bool = False,
) -> tuple[Optional[dict], LLMTelemetry]:
    """Run the LLM call for an action that needs one. Returns (result_dict, telemetry).

    Telemetry is captured regardless of provider so the drive can consume it
    via RegulatoryBudgets.telemetry_to_delta().

    baseline_mode=True: no state injection (used for ablation/unregulated agents).
    pressure_mode=True: append caveman terse block to system prompt.
    """
    spec = ACTIONS[execution.kind]
    empty = LLMTelemetry()
    if spec.max_tokens == 0:
        return None, empty

    if baseline_mode:
        system = _baseline_system_prompt()
    else:
        system = _system_prompt(drive, scramble=scramble_labels, pressure_mode=pressure_mode)

    if execution.kind == ActionKind.RESPOND_FAST:
        user = _respond_fast_user(execution.demand_topic or "unknown")
    elif execution.kind == ActionKind.RESPOND_SLOW:
        user = _respond_slow_user(execution.demand_topic or "unknown")
    elif execution.kind == ActionKind.PROACT:
        user = _proact_user(drive, queue_size)
    else:
        return None, empty

    cfg = model_cfg or DEFAULT_ROUTING["main"]
    try:
        # max_tokens from spec — already sized correctly per tier (see MAX_TOKENS_BY_TIER)
        raw, telemetry = call_llm(system, user, cfg=cfg, max_tokens=spec.max_tokens)
        result = _extract_json_with_retry(raw, user) or {"parse_error": True, "raw": raw[:120]}
    except Exception as exc:
        result = {"error": str(exc)[:80]}
        telemetry = empty
    return result, telemetry
