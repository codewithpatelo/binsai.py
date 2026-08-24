"""Telemetry export and visualization for Binsai simulations.

SimulationLog: accumulates frames from World.run() and exports them.
Report functions: matplotlib-based plots (optional, requires binsai[analysis]).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SimulationLog:
    """Accumulated telemetry from a simulation run."""

    config:   dict[str, Any]           = field(default_factory=dict)
    frames:   list[dict[str, Any]]     = field(default_factory=list)
    metadata: dict[str, Any]           = field(default_factory=dict)

    def record(self, frame: Any) -> None:
        """Record one WorldFrame as a flat dict."""
        try:
            d = _frame_to_dict(frame)
        except Exception:
            import dataclasses
            d = dataclasses.asdict(frame)
        self.frames.append(d)

    def to_records(self) -> list[dict[str, Any]]:
        """Flat list of per-tick per-agent records (for DataFrame conversion)."""
        records = []
        for f in self.frames:
            tick = f.get("tick", 0)
            for a in f.get("agents", []):
                records.append({
                    "tick":              tick,
                    "agent":             a.get("name", "?"),
                    "status":            a.get("status", "?"),
                    "delta":             a.get("delta"),
                    "zone":              a.get("zone", "?"),
                    "action":            a.get("action", "?"),
                    "queue":             a.get("queue", 0),
                    "session_tokens":    a.get("session_tokens", 0),
                    "session_cost_usd":  a.get("session_cost_usd", 0.0),
                    "session_calls":     a.get("session_calls", 0),
                    "session_deferred":  a.get("session_deferred", 0),
                    "last_tokens":       a.get("last_tokens"),
                    "last_cost_usd":     a.get("last_cost_usd"),
                    "last_latency_ms":   a.get("last_latency_ms"),
                    "window_saturation": a.get("window_saturation"),
                    "context_used":      a.get("context_used_tokens", 0),
                    "context_budget":    a.get("context_budget_tokens", 0),
                    "ablation_off":      a.get("ablation_off", False),
                    "lambda_rate":       a.get("lambda_rate"),
                    "temperature":       a.get("temperature"),
                })
        return records

    def to_dataframe(self):
        """Return a pandas DataFrame. Requires pandas."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for to_dataframe(). Install with: pip install binsai[analysis]"
            )
        return pd.DataFrame(self.to_records())

    def save_jsonl(self, path: str) -> None:
        """Save all frames as newline-delimited JSON."""
        import json
        with open(path, "w", encoding="utf-8") as f:
            for frame in self.frames:
                f.write(json.dumps(frame, default=str) + "\n")

    def save_csv(self, path: str) -> None:
        """Save per-tick per-agent records as CSV."""
        self.to_dataframe().to_csv(path, index=False)


def _frame_to_dict(frame: Any) -> dict:
    """Convert a WorldFrame dataclass to a plain dict."""
    import dataclasses
    try:
        d = dataclasses.asdict(frame)
    except Exception:
        d = {"tick": getattr(frame, "tick", 0), "agents": [], "config": {}}
    return d


# ── Plotting (requires matplotlib — optional) ─────────────────────────────────

def plot_trajectories(log: SimulationLog, save_path: Optional[str] = None):
    """Plot δ trajectories for all agents over time."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError(
            "matplotlib is required for plotting. Install with: pip install binsai[analysis]"
        )

    df = log.to_dataframe()
    fig, ax = plt.subplots(figsize=(10, 4))
    for name, group in df.groupby("agent"):
        ax.plot(group["tick"], group["delta"], label=name, linewidth=1.2)
    ax.axhline(0.30, color="gray", linestyle="--", linewidth=0.8, label="set-point")
    ax.set_xlabel("tick")
    ax.set_ylabel("δ (metabolic drive)")
    ax.set_title("Drive trajectories")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_action_histogram(log: SimulationLog, save_path: Optional[str] = None):
    """Stacked bar chart of action counts per agent."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError(
            "matplotlib is required for plotting. Install with: pip install binsai[analysis]"
        )

    df = log.to_dataframe()
    actions = df["action"].value_counts().index.tolist()
    agents = df["agent"].unique()
    fig, ax = plt.subplots(figsize=(8, 4))
    width = 0.35
    x = range(len(actions))
    for i, agent in enumerate(agents):
        counts = [len(df[(df["agent"] == agent) & (df["action"] == a)]) for a in actions]
        ax.bar([xi + i * width for xi in x], counts, width, label=agent)
    ax.set_xticks([xi + width / 2 for xi in x])
    ax.set_xticklabels(actions, rotation=45, ha="right")
    ax.set_ylabel("count")
    ax.set_title("Action distribution per agent")
    ax.legend()
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig


def plot_kpi_comparison(log: SimulationLog, save_path: Optional[str] = None):
    """Bar chart comparing regulated vs unregulated cumulative tokens/cost."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError(
            "matplotlib is required for plotting. Install with: pip install binsai[analysis]"
        )

    df = log.to_dataframe()
    # Get last tick values per agent
    last = df.sort_values("tick").groupby("agent").last().reset_index()
    reg = last[~last["ablation_off"]]
    unreg = last[last["ablation_off"]]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5))
    ax1.bar(["regulated", "unregulated"],
            [reg["session_tokens"].sum(), unreg["session_tokens"].sum()],
            color=["#3fb950", "#f85149"])
    ax1.set_ylabel("total tokens")
    ax1.set_title("Cumulative tokens")
    ax2.bar(["regulated", "unregulated"],
            [reg["session_cost_usd"].sum(), unreg["session_cost_usd"].sum()],
            color=["#3fb950", "#f85149"])
    ax2.set_ylabel("total cost (USD)")
    ax2.set_title("Cumulative cost")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150)
    return fig
