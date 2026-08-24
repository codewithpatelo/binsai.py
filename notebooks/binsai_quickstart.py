# %% [markdown]
# # Binsai.PY — Quickstart
# ## Bio-Inspired Neuro-Symbolic AI for self-regulating agents
#
# Four scenarios:
# 1. **Hunger / Fridge** — pure Python, no LLM. Single drive + custom action.
# 2. **Socialization ablation** — DeepSeek LLM. Plain vs homeostatic conversation.
# 3. **Hormonal routing (HPA)** — DeepSeek LLM + 2 coupled drives. Model routing.
# 4. **Antagonistic tensions** — multi-objective regulation without scalarizing.
#
# Scenario 1 & 4 run **offline** (no API key). Scenarios 2 & 3 need `DEEPSEEK_API_KEY`.

# %% [markdown]
# ## Install

# %%
!pip install binsai

# %% [markdown]
# *(Fallback if PyPI is unavailable: `!pip install git+https://github.com/codewithpatelo/binsai.py`)*

# %% [markdown]
# ---
# ## Scenario 1: Hunger / Fridge (no LLM)
#
# A single agent with a `hunger` drive. When hunger rises, it goes to the fridge and eats.
# This is the Γ operator in its simplest form — no LLM, just a drive and an action.

# %%
from binsai import BinsaiAgent, Drives, Drive, Stratum
from binsai.action_registry import ActionSet, ActionSpec
from binsai.action_registry import _handler_satiate
import random

# 1. Create a hunger drive — starts hungry (δ = 0.60)
hunger_drive = Drive(
    name="hunger", stratum=Stratum.BIOLOGICAL,
    value=0.60, set_point=0.30,
    kappa=0.02, lambda_rate=0.008,
    satiation_rate=0.30,
)

drives = Drives([hunger_drive])

# 2. Define custom actions: go_to_fridge satiates hunger, idle does nothing
actions = ActionSet([
    ActionSpec(
        name="go_to_fridge", requires_demand=False,
        delta_cost=0.0, ticks=1, max_tokens=0,
        beta=-8.0, bias=-1.0,
        handler=_handler_satiate("hunger", amount=0.8, action_name="go_to_fridge"),
    ),
    ActionSpec(
        name="idle", requires_demand=False,
        delta_cost=0.0, ticks=1, max_tokens=0,
        beta=0.0, bias=-0.3,
        handler=lambda a, d, t, dm, df: "idle",
    ),
])

# 3. Create agent with hunger drive and custom actions
agent = BinsaiAgent(
    name="Sim",
    drives=drives,
    action_set=actions,
    ablation_off=False,
    dry_run_llm=True,
    rng=random.Random(42),
)
agent.activate()

# 4. Run 40 ticks and observe
print("tick | hunger δ | zone       | action")
print("-" * 48)
for tick in range(40):
    agent.tick(tick)
    h = drives.get("hunger")
    zone = h.get_zone() if h else "?"
    delta = h.value if h else 0
    action = agent.last_action or "idle"
    marker = " ← eats!" if action == "go_to_fridge" else ""
    print(f"  {tick:2d} |   {delta:.3f}  | {zone:10s} | {action:13s}{marker}")

# %%
# Quick plot of the hunger trajectory
import matplotlib.pyplot as plt
deltas = []
for tick in range(80):
    agent.tick(tick)
    h = drives.get("hunger")
    deltas.append(h.value if h else 0.30)

plt.figure(figsize=(8, 2.5))
plt.plot(deltas, 'o-', markersize=2, color='#d29922')
plt.axhline(0.30, color='gray', linestyle='--', label='set-point')
plt.xlabel('tick'); plt.ylabel('hunger δ')
plt.title('Hunger drive — sawtooth: eat → drop → drift → eat')
plt.legend(); plt.grid(True, alpha=0.3)
plt.tight_layout(); plt.show()

# %% [markdown]
# ---
# ## Scenario 2: Socialization ablation (needs DeepSeek key)
#
# Two agents receive messages from a human. The **plain agent** responds and the conversation ends.
# The **homeostatic agent** has a `relatedness` drive: when it decays, the agent proactively
# re-initiates contact — even without being prompted.
#
# **Set your key first:**
# ```python
# import os
# os.environ["DEEPSEEK_API_KEY"] = "sk-..."
# ```

# %%
import os
# Uncomment and set your key:
# os.environ["DEEPSEEK_API_KEY"] = "sk-..."

from binsai import World, WorldConfig, AgentConfig
from binsai.action_registry import ActionSet, ActionSpec
from binsai.action_registry import _handler_llm, _handler_noop
from binsai.llm import get_backend

# 1. Create two agents with a relatedness drive + custom social actions
social_actions = ActionSet([
    ActionSpec(
        name="reply", requires_demand=True,
        delta_cost=0.002, ticks=1, max_tokens=256,
        beta=-0.5, bias=+1.6, handler=_handler_llm,
    ),
    ActionSpec(
        name="initiate_contact", requires_demand=False,
        delta_cost=0.003, ticks=1, max_tokens=256,
        beta=-10.0, bias=-2.5, handler=_handler_llm,
    ),
    ActionSpec(
        name="idle", requires_demand=False,
        delta_cost=0.0, ticks=1, max_tokens=0,
        beta=0.0, bias=-0.3, handler=_handler_noop,
    ),
])

# Regulated agent (relatedness decays → proact fires)
config = WorldConfig(
    seed=42,
    dry_run_llm=("DEEPSEEK_API_KEY" not in os.environ),
    agents=[
        AgentConfig(
            name="HomeoBot",
            drive_names=["relatedness"],
            drive_configs=[
                {"name": "relatedness", "lambda_rate": 0.010, "set_point": 0.30},
            ],
            temperature=1.0,
        ),
    ],
)
w = World(config)
# Inject the custom action set
for agent in w.agents:
    agent.action_set = social_actions

# 2. Simulate: human sends a message at tick 5, then stops. Watch relatedness decay → agent re-engages.
log = w.run(60)
df = log.to_dataframe()
# Show trajectory
import pandas as pd
df[df["agent"] == "HomeoBot"][["tick", "delta", "zone", "action", "session_tokens"]].head(20)

# %%
# Plot relatedness trajectory
import matplotlib.pyplot as plt
homeo = df[df["agent"] == "HomeoBot"]
plt.figure(figsize=(8, 2.5))
plt.plot(homeo["tick"], homeo["delta"], color='#58a6ff')
plt.axhline(0.30, color='gray', linestyle='--')
plt.xlabel('tick'); plt.ylabel('relatedness δ')
plt.title('Relatedness drive — decays when alone, spikes on contact')
plt.grid(True, alpha=0.3)
plt.tight_layout(); plt.show()

# Count proactive contacts
proact_ticks = homeo[homeo["action"] == "initiate_contact"]["tick"].tolist()
print(f"Agent initiated contact at ticks: {proact_ticks}")

# %% [markdown]
# ---
# ## Scenario 3: Hormonal routing (HPA) — 2 coupled drives
#
# A cheap model evaluates incoming tasks. When the metabolic drive is low (abundant resources)
# AND the task is hard, the agent routes to an expensive model. When metabolic is high,
# it defers or sleeps. Two drives are **coupled**: task_load feeds into metabolic.

# %%
from binsai import World, WorldConfig, AgentConfig, Drives, Drive, Stratum

# 1. Create two coupled drives
drives = Drives([
    Drive(name="metabolic", stratum=Stratum.MATERIAL, value=0.30, lambda_rate=0.005),
    Drive(name="task_load",  stratum=Stratum.TECHNICAL, value=0.30, lambda_rate=0.003),
])
# Coupling: task_load → metabolic (busy agent burns more resources)
drives.set_coupling({
    "task_load": {"metabolic": 0.08},
})

# 2. Custom routing actions
routing_actions = ActionSet([
    ActionSpec(
        name="respond_cheap", requires_demand=True,
        delta_cost=0.001, ticks=1, max_tokens=256,
        beta=-0.5, bias=+1.6, handler=_handler_llm,
    ),
    ActionSpec(
        name="respond_expensive", requires_demand=True,
        delta_cost=0.008, ticks=2, max_tokens=1500,
        beta=-8.0, bias=-2.0, handler=_handler_llm,
    ),
    ActionSpec(
        name="defer", requires_demand=True,
        delta_cost=0.0005, ticks=1, max_tokens=0,
        beta=+6.0, bias=-0.5,
        handler=lambda a, d, t, dm, df: ("defer" if not (
            a.pending_demands.append(dm) if dm else None
        ) else "defer"),
    ),
    ActionSpec(name="idle", requires_demand=False, handler=_handler_noop),
    ActionSpec(name="sleep", requires_demand=False, beta=+10.0, bias=-6.0,
               handler=lambda a, d, t, dm, df: "sleep"),
])

config = WorldConfig(
    seed=42,
    dry_run_llm=("DEEPSEEK_API_KEY" not in os.environ),
    lambda_demand=0.4,
    agents=[
        AgentConfig(
            name="Router",
            drive_names=["metabolic", "task_load"],
            drive_configs=[
                {"name": "metabolic", "lambda_rate": 0.004},
                {"name": "task_load",  "lambda_rate": 0.003},
            ],
            temperature=0.8,
        ),
    ],
)
w = World(config)
# Inject custom drives and actions
w.agents[0].drives = drives
w.agents[0].action_set = routing_actions

log = w.run(80)
df = log.to_dataframe()
router = df[df["agent"] == "Router"]

# Show routing decisions at key moments — what model was chosen and why
print("tick | metabolic δ | metabolic zone       | task_load δ | task_load zone       | action")
print("-" * 95)
for tick in range(0, 80, 8):
    row = router[router["tick"] == tick]
    if len(row) == 0: continue
    r = row.iloc[0]
    m = w.agents[0].drives.get("metabolic")
    tl = w.agents[0].drives.get("task_load")
    # Re-run to get drive values at this tick (they're consumed by the log but we can re-read)
    m_val = m.value if m else 0.30
    tl_val = tl.value if tl else 0.30
    print(f"  {tick:3d} |     {m_val:.3f}   | {m.get_zone():20s} |      {tl_val:.3f}  | {tl.get_zone():20s} | {r['action']}")

print()
print("Action distribution:", dict(router["action"].value_counts()))
print()
print("How it works: when metabolic is in equilibrium or superavit (abundant resources),")
print("the agent can afford respond_expensive (DeepSeek Pro). When metabolic is in deficit,")
print("it switches to respond_cheap (DeepSeek Flash) or defers. The task_load drive is")
print("coupled to metabolic — a busy agent burns more resources, creating natural feedback.")

# %% [markdown]
# ---
# ## Scenario 4: Antagonistic tensions — irreducible multi-objective regulation
#
# **The core insight from the latest paper**: homeostasis makes sense where you have
# genuinely conflicting objectives that *cannot* be reduced to a single scalar without
# choosing an arbitrary exchange rate ("cuanto vale una tarea en tokens de contexto?").
#
# Two drives pull in opposite directions:
# - **Process tasks** clears the backlog but fills the context window (costs tokens)
# - **Compress context** frees the window but drops pending work
#
# This manual simulation shows the raw Γ dynamics: each tick, the agent evaluates both
# drives and picks the action that keeps both within viable ranges — without scalarizing.

# %%
from binsai import Drive, Stratum
import math, random

rng = random.Random(7)

# Two genuinely antagonistic drives
ctx = Drive(name="context_fill", stratum=Stratum.TECHNICAL,
            value=0.30, set_point=0.30, kappa=0.02, lambda_rate=0.005)
bl  = Drive(name="task_backlog", stratum=Stratum.TECHNICAL,
            value=0.30, set_point=0.30, kappa=0.02, lambda_rate=0.004)

ctx_traj, bl_traj, actions = [], [], []
for tick in range(300):
    # Both drives decay each tick
    ctx.update(tick); bl.update(tick)

    # Simple homeostatic rule: act on whichever is farther from set-point
    ctx_dev = abs(ctx.value - ctx.set_point)
    bl_dev  = abs(bl.value - bl.set_point)

    if ctx_dev > bl_dev and ctx.value > ctx.set_point:
        # Context is too full → compress it (frees context, drops backlog)
        ctx.satiate(0.5)
        bl.deplete(0.02)
        actions.append("compress_ctx")
    elif bl_dev > ctx_dev and bl.value > bl.set_point:
        # Backlog is too high → process tasks (clears backlog, fills context)
        bl.satiate(0.4)
        ctx.deplete(0.05)
        actions.append("process_task")
    else:
        actions.append("idle")

    ctx_traj.append(ctx.value)
    bl_traj.append(bl.value)

# Plot: two drives oscillating in opposite phase, both staying viable
import matplotlib.pyplot as plt
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), sharex=True)

ax1.plot(ctx_traj, color='#58a6ff', linewidth=1.2, label='context_fill δ')
ax1.axhline(0.30, color='gray', linestyle='--', linewidth=0.8)
ax1.fill_between(range(300), 0.22, 0.40, color='#3fb950', alpha=0.08, label='viable band')
ax1.set_ylabel('context_fill δ'); ax1.legend(loc='upper right'); ax1.grid(True, alpha=0.3)

ax2.plot(bl_traj, color='#d29922', linewidth=1.2, label='task_backlog δ')
ax2.axhline(0.30, color='gray', linestyle='--', linewidth=0.8)
ax2.fill_between(range(300), 0.22, 0.40, color='#3fb950', alpha=0.08, label='viable band')
ax2.set_xlabel('tick'); ax2.set_ylabel('task_backlog δ')
ax2.legend(loc='upper right'); ax2.grid(True, alpha=0.3)

fig.suptitle('Antagonistic drives — oscillate in opposite phase, both stay viable', fontsize=11)
fig.tight_layout(); plt.show()

# Show that the two drives are anti-correlated — genuine tension
import numpy as np
corr = np.corrcoef(ctx_traj[50:], bl_traj[50:])[0, 1]
from collections import Counter
counts = Counter(actions)
print(f"Correlation (ctx vs backlog): {corr:.3f} — negative = genuine tension")
print(f"Action distribution: {dict(counts)}")
print()
print("Sample of decision-making (every 50 ticks):")
print("tick | context_fill δ | context zone         | task_backlog δ | backlog zone         | action")
print("-" * 95)
for tick in range(0, 300, 50):
    print(f"  {tick:3d} |        {ctx_traj[tick]:.3f}  | {ctx.get_zone():20s} |         {bl_traj[tick]:.3f}  | {bl.get_zone():20s} | {actions[tick]}")
print()
print("Key insight: no single scalar 'utility' can capture both drives — any")
print("weighted sum picks an arbitrary exchange rate ('how many context tokens")
print("is one pending task worth?'). Homeostasis maintains both in viable range")
print("without ever scalarizing. The Γ operator is designed for multi-objective")
print("regulation where the goal is maintenance itself, not optimization.")

# %% [markdown]
# ## Export
# Save the simulation log as JSONL for further analysis.

# %%
log.save_jsonl("binsai_demo.jsonl")
log.save_csv("binsai_demo.csv")
print("Exported binsai_demo.jsonl and binsai_demo.csv")
print(f"Total records: {len(log.to_records())}")
