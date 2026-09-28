"""Action selection: AAH-A2 multinomial logistic + zone memberships for prompts.

The JAIIO paper (Driveplexity) formulates A2 for binary speak/pass:

    p(act) = σ(D(δ))   where D(ε)=0, D'(δ)>0 for δ > ε

For Binsai we have ≥6 candidate actions (respond_fast, respond_slow, defer,
proact, idle, sleep), so we generalize σ to its multi-class analogue —
multinomial logistic regression (softmax of per-action affine functions of D):

    p_k(δ) = exp(β_k · D(δ) + b_k) / Σ_j exp(β_j · D(δ) + b_j)

This is mathematically the multi-class extension of the binary sigmoid:
each action k has its own activation curve σ_k(D), normalized to a simplex.
Satisfaction convention (x = satisfaction level): D = x* − x, so D > 0 means
deficit (x below target) and D < 0 means slack.
- β_k > 0 → action activated by deficit (x < x*)
- β_k < 0 → action activated by slack (x > x*)
- β_k = 0 → action is x-insensitive baseline
- b_k    → bias (preference at set-point)

Properties (AAH-A2 compliant, multi-action):
- At x = x*: D = 0, distribution is determined by biases alone (calm regime).
- As x falls below x*: probability mass shifts monotonically toward β_k > 0 actions.
- As x rises above x*: mass shifts toward β_k < 0 actions.
- For any pair (i,j): p_i/p_j = exp((β_i−β_j)·D + (b_i−b_j)) — monotonic in D.

zone_memberships() is retained for the State Injection prompt (LLM reads
its dominant zone label) but is no longer in the action selection path.
"""

from __future__ import annotations

import math
import random

ZONES = ("critical_superavit", "high_superavit", "moderate_superavit",
         "equilibrium", "moderate_deficit", "high_deficit", "critical_deficit")

ZONE_CENTERS: dict[str, float] = {
    "critical_deficit":     0.20,
    "high_deficit":         0.45,
    "moderate_deficit":     0.60,
    "equilibrium":          0.70,
    "moderate_superavit":   0.78,
    "high_superavit":       0.87,
    "critical_superavit":   0.95,
}

ZONE_WIDTH = 0.08  # Gaussian σ — narrower for 7 zones

ACTIONS_WITH_DEMAND = ["respond_fast", "respond_slow", "defer", "idle", "sleep"]
ACTIONS_NO_DEMAND   = ["proact", "idle", "sleep"]

# ── AAH-A2 multinomial logistic parameters ─────────────────────────────────────
# Each action: (β, b) — β = drive-intensity sensitivity, b = baseline preference.
# Calibrated so that:
#   - x ≈ x*: respond_fast dominates when demand present, idle when not
#   - x >> x* (slack/oversated): proact and respond_slow surge
#   - x << x* (critical deficit): defer and sleep surge, all LLM actions collapse
ACTION_PARAMS: dict[str, tuple[float, float]] = {
    # action          β        b
    "respond_fast": ( -0.5,   +1.6),   # mild slack preference, default action
    "respond_slow": ( -8.0,   -0.3),   # strong slack preference
    "defer":        ( +6.0,   -0.5),   # deficit-driven (activates a bit earlier)
    "proact":       (-12.0,   -1.5),   # extreme slack preference (proactive)
    "idle":         (  0.0,   -0.3),   # slight baseline penalty — pushes toward action
    "sleep":        (+10.0,   -6.0),   # needs x < 0.10 before meaningful probability
}


def drive_intensity(delta: float, set_point: float = 0.70) -> float:
    """D(x) from AAH-A2 under the satisfaction convention: x* − x, so D > 0
    means deficit (x below target) and D < 0 means slack."""
    return set_point - delta


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
    set_point:    float = 0.70,
    ablation_off: bool  = False,
    temperature:  float = 1.0,
    demand_difficulty: float = 0.0,
    pending_labels: int = 0,
    action_set:   Any  = None,
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
        action_set:        Optional ActionSet; if None, uses module-level defaults.
    """
    if action_set is not None:
        params = action_set.to_action_params()
        specs_with = action_set.with_demand()
        specs_without = action_set.without_demand()
        actions = [s.name for s in (specs_with if has_demand else specs_without)]
    else:
        params = ACTION_PARAMS
        actions = ACTIONS_WITH_DEMAND if has_demand else ACTIONS_NO_DEMAND

    if ablation_off:
        ablation_actions = [a for a in actions if a != "sleep"]
        p = 1.0 / max(1, len(ablation_actions))
        return {a: p for a in ablation_actions}

    # Anticipatory: heavy demand shifts perceived intensity upward
    D = drive_intensity(delta, set_point) + 0.30 * demand_difficulty

    logits = [params[a][0] * D + params[a][1] for a in actions]

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


# ── Activation gate: hazard rate per unit time, not probability per tick ───────
# "p(act) = 20% per tick" is a hidden hyperparameter: at 1-min ticks, the odds of
# NOT acting in an hour are 0.8^60 ≈ 0; halving the tick changes the behaviour
# without touching the equation. Modelled instead as a Poisson process:
#
#     p_tick = 1 − e^(−h·Δt)        h in activations per unit time
#
# Behaviour is invariant to Δt, and h has domain provenance: mean waiting time
# to activation is 1/h, so calibration answers "in amber, how long should the
# agent take to act, on average?" — if 20 min, h = 3/hour.
#
# The gate owns the act / not-act decision; the softmax above owns *which*
# action. ACTIVE-state commitment and the post-action refractory period are
# enforced in BinsaiAgent, not here.

def activation_probability(hazard: float, dt: float = 1.0) -> float:
    """Per-tick activation probability from a per-time-unit hazard rate.

    p_tick = 1 − e^(−h·Δt). Returns 0 for h ≤ 0.
    """
    if hazard <= 0.0 or dt <= 0.0:
        return 0.0
    return -math.expm1(-hazard * dt)


def activation_hazard(pressure: float, *, has_demand: bool = False,
                      pending_labels: int = 0,
                      h_pressure: float = 1.5, h_demand: float = 4.0,
                      h_backlog: float = 0.3) -> float:
    """Activation rate h (activations per unit time).

    Driven by drive pressure p ∈ [0,1] — the same max(level, pace, autonomous)
    signal the EPA already computes — plus explicit boosts:
        has_demand:     h_demand   — pending work raises the rate sharply
                        (default 4/unit → mean wait ≈ 0.25 units ≈ fast reply)
        pending_labels: h_backlog each — planned work nudges proact
    pressure=0, no demand, no backlog → h=0 → agent idles.
    """
    h = h_pressure * min(1.0, max(0.0, pressure))
    if has_demand:
        h += h_demand
    return h + h_backlog * max(0, pending_labels)
