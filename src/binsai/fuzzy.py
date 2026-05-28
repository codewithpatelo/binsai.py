"""Action selection: AAH-A2 multinomial logistic + zone memberships for prompts.

The JAIIO paper (Driveplexity) formulates A2 for binary speak/pass:

    p(act) = σ(D(δ))   where D(ε)=0, D'(δ)>0 for δ > ε

For Binsai we have ≥6 candidate actions (respond_fast, respond_slow, defer,
proact, idle, sleep), so we generalize σ to its multi-class analogue —
multinomial logistic regression (softmax of per-action affine functions of D):

    p_k(δ) = exp(β_k · D(δ) + b_k) / Σ_j exp(β_j · D(δ) + b_j)

This is mathematically the multi-class extension of the binary sigmoid:
each action k has its own activation curve σ_k(D), normalized to a simplex.
- β_k > 0 → action activated by deficit (δ > ε)
- β_k < 0 → action activated by abundance (δ < ε)
- β_k = 0 → action is δ-insensitive baseline
- b_k    → bias (preference at set-point)

Properties (AAH-A2 compliant, multi-action):
- At δ = ε: D = 0, distribution is determined by biases alone (calm regime).
- As δ grows above ε: probability mass shifts monotonically toward β_k > 0 actions.
- As δ falls below ε: mass shifts toward β_k < 0 actions.
- For any pair (i,j): p_i/p_j = exp((β_i−β_j)·D + (b_i−b_j)) — monotonic in D.

zone_memberships() is retained for the State Injection prompt (LLM reads
its dominant zone label) but is no longer in the action selection path.
"""

from __future__ import annotations

import math
import random

ZONES = ("oversated", "sated", "nominal", "loaded", "critical")

ZONE_CENTERS: dict[str, float] = {
    "oversated": 0.05,
    "sated":     0.15,
    "nominal":   0.30,
    "loaded":    0.55,
    "critical":  0.80,
}

ZONE_WIDTH = 0.12  # Gaussian σ — controls overlap between adjacent zones

ACTIONS_WITH_DEMAND = ["respond_fast", "respond_slow", "defer", "idle", "sleep"]
ACTIONS_NO_DEMAND   = ["proact", "idle", "sleep"]

# ── AAH-A2 multinomial logistic parameters ─────────────────────────────────────
# Each action: (β, b) — β = drive-intensity sensitivity, b = baseline preference.
# Calibrated so that:
#   - δ ≈ ε: respond_fast dominates when demand present, idle when not
#   - δ << ε (oversated): proact and respond_slow surge
#   - δ >> ε (critical): defer and sleep surge, all LLM actions collapse
ACTION_PARAMS: dict[str, tuple[float, float]] = {
    # action          β        b
    "respond_fast": ( -0.5,   +1.6),   # mild abundance preference, default action
    "respond_slow": ( -8.0,   -0.3),   # strong abundance preference
    "defer":        ( +6.0,   -0.5),   # deficit-driven (activates a bit earlier)
    "proact":       (-12.0,   -1.5),   # extreme abundance preference (proactive)
    "idle":         (  0.0,   -0.3),   # slight baseline penalty — pushes toward action
    "sleep":        (+10.0,   -6.0),   # needs δ > 0.90 before meaningful probability
}


def drive_intensity(delta: float, set_point: float = 0.30) -> float:
    """D(δ) from AAH-A2. Signed deviation from set-point; D(ε)=0."""
    return delta - set_point


def gaussian_membership(delta: float, center: float, width: float = ZONE_WIDTH) -> float:
    """Gaussian membership for a drive level at a zone center."""
    return math.exp(-0.5 * ((delta - center) / width) ** 2)


def zone_memberships(delta: float) -> dict[str, float]:
    """Normalized Gaussian memberships over 5 zones. Values sum to 1.0.

    Retained for State Injection prompt building — the LLM is told its
    dominant zone as a natural-language label. Not used in action selection.
    """
    raw = {z: gaussian_membership(delta, ZONE_CENTERS[z]) for z in ZONES}
    total = sum(raw.values()) or 1.0
    return {z: v / total for z, v in raw.items()}


def _softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    """Numerically stable softmax."""
    scaled = [x / temperature for x in logits]
    max_v = max(scaled)
    exps = [math.exp(v - max_v) for v in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def compute_action_distribution(
    delta:        float,
    has_demand:   bool,
    set_point:    float = 0.30,
    ablation_off: bool  = False,
    temperature:  float = 1.0,
    demand_difficulty: float = 0.0,
    pending_labels: int = 0,
) -> dict[str, float]:
    """AAH-A2 multinomial logistic over candidate actions.

    Args:
        delta:             current drive value
        has_demand:        whether a pending demand exists (changes action set)
        set_point:         homeostatic target ε for D(δ)
        ablation_off:      if True, uniform distribution (regulation disabled)
        temperature:       softmax temperature (higher = more exploration)
        demand_difficulty: ∈[0,1]; predicted demand cost. Shifts logits as if
                           δ were higher by this much (anticipatory regulation).
        pending_labels:    number of planned task labels waiting in backlog.
                           Boosts proact probability when > 0 and no demand.
    """
    actions = ACTIONS_WITH_DEMAND if has_demand else ACTIONS_NO_DEMAND

    if ablation_off:
        # Sleep is a regulatory behavior — excluded when regulation is off.
        # Unregulated agent processes freely without resource management.
        ablation_actions = [a for a in actions if a != "sleep"]
        p = 1.0 / len(ablation_actions)
        return {a: p for a in ablation_actions}

    # Anticipatory: heavy demand shifts perceived intensity upward
    D = drive_intensity(delta, set_point) + 0.30 * demand_difficulty

    logits = [ACTION_PARAMS[a][0] * D + ACTION_PARAMS[a][1] for a in actions]

    # Proactive boost: if planned work exists but no current demand, prefer proact
    if not has_demand and pending_labels > 0 and "proact" in actions:
        idx = actions.index("proact")
        logits[idx] += 2.5  # strong boost to clear backlog

    probs = _softmax(logits, temperature=temperature)
    return dict(zip(actions, probs))


def sample_action(distribution: dict[str, float], rng: random.Random) -> str:
    """Sample one action from a probability distribution."""
    actions = list(distribution.keys())
    weights = [distribution[a] for a in actions]
    return rng.choices(actions, weights=weights, k=1)[0]
