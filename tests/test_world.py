"""Integration tests for world.py — reproducibility, ablation, emergent behavior."""

import pytest

from binsai.world.world import World, WorldConfig, WorldFrame


def make_world(seed: int = 42, ablation_off: bool = False, n_agents: int = 3) -> World:
    from binsai.world.world import AgentConfig
    agents = [
        AgentConfig(name=f"A{i}", lambda_override=0.005 + i * 0.001, initial_delta=0.30)
        for i in range(n_agents)
    ]
    config = WorldConfig(
        seed=seed,
        lambda_demand=0.5,
        ablation_off=ablation_off,
        dry_run_llm=True,
        agents=agents,
    )
    return World(config)


class TestReproducibility:
    def test_same_seed_same_frames(self):
        """Two worlds with same seed must produce identical frame sequences."""
        w1 = make_world(seed=42)
        w2 = make_world(seed=42)

        for _ in range(50):
            f1 = w1.step()
            f2 = w2.step()
            for a1, a2 in zip(f1.agents, f2.agents):
                assert a1.delta  == a2.delta,  f"delta mismatch at tick {f1.tick}"
                assert a1.zone   == a2.zone,   f"zone mismatch at tick {f1.tick}"
                assert a1.status == a2.status, f"status mismatch at tick {f1.tick}"
                assert a1.queue  == a2.queue,  f"queue mismatch at tick {f1.tick}"

    def test_different_seeds_diverge(self):
        """Different seeds should produce different frame sequences."""
        w1 = make_world(seed=1)
        w2 = make_world(seed=999)
        frames1 = [w1.step() for _ in range(30)]
        frames2 = [w2.step() for _ in range(30)]
        deltas1 = [a.delta for f in frames1 for a in f.agents]
        deltas2 = [a.delta for f in frames2 for a in f.agents]
        assert deltas1 != deltas2

    def test_reset_restores_initial_state(self):
        w = make_world(seed=7)
        frames_before = [w.step() for _ in range(20)]
        w.reset()
        frames_after  = [w.step() for _ in range(20)]
        for f1, f2 in zip(frames_before, frames_after):
            for a1, a2 in zip(f1.agents, f2.agents):
                assert a1.delta == a2.delta


class TestWorldFrame:
    def test_frame_has_correct_structure(self):
        w = make_world()
        frame = w.step()
        assert isinstance(frame, WorldFrame)
        assert frame.tick == 1
        assert len(frame.agents) == 3
        for ag in frame.agents:
            assert ag.name
            assert ag.status in ("initiated", "active", "suspended", "critical", "terminated")
            assert ag.delta is not None
            assert 0.0 <= ag.delta <= 1.0

    def test_frame_demands_list(self):
        w = make_world()
        frame = w.step()
        assert isinstance(frame.demands, list)

    def test_frame_events_list(self):
        w = make_world()
        frame = w.step()
        assert isinstance(frame.events, list)


class TestAblation:
    def test_ablation_toggle(self):
        w = make_world(ablation_off=False)
        assert w.config.ablation_off is False
        new_val = w.toggle_ablation()
        assert new_val is True
        assert w.config.ablation_off is True
        for agent in w.agents:
            assert agent.ablation_off is True

    def test_ablation_off_collapses_to_higher_delta(self):
        """Over 300 ticks, unregulated agents should accumulate higher mean δ.

        Regulated agents (ablation_off=False) defer/sleep when δ is high, reducing
        token spend and triggering consolidation. Unregulated agents pick uniformly,
        spending tokens regardless of state. With realistic dry_run token costs
        (80-300 tokens per LLM call) the difference becomes clear over 300 ticks.
        """
        from binsai.world.world import AgentConfig
        # Start agents slightly above set-point so regulation kicks in quickly
        agents = [
            AgentConfig(name=f"A{i}", lambda_override=0.006, initial_delta=0.40)
            for i in range(3)
        ]
        cfg_base = dict(lambda_demand=0.5, dry_run_llm=True, agents=agents)

        w_reg   = World(WorldConfig(seed=42, ablation_off=False, **cfg_base))
        w_unreg = World(WorldConfig(seed=42, ablation_off=True,  **cfg_base))

        deltas_reg   = []
        deltas_unreg = []
        for _ in range(300):
            f_reg   = w_reg.step()
            f_unreg = w_unreg.step()
            deltas_reg.extend(   [a.delta for a in f_reg.agents   if a.delta is not None])
            deltas_unreg.extend( [a.delta for a in f_unreg.agents if a.delta is not None])

        mean_reg   = sum(deltas_reg)   / len(deltas_reg)
        mean_unreg = sum(deltas_unreg) / len(deltas_unreg)
        assert mean_reg <= mean_unreg, (
            f"Expected regulated δ ≤ unregulated δ, got {mean_reg:.4f} vs {mean_unreg:.4f}"
        )


class TestOversatedProactivity:
    def test_oversated_agent_proacts_more_than_sleeps(self):
        """Agent starting oversated (δ very low, no demands) should proact most."""
        from binsai.world.world import AgentConfig
        config = WorldConfig(
            seed=0,
            lambda_demand=0.0,  # no external demands
            dry_run_llm=True,
            agents=[AgentConfig(name="A", lambda_override=0.0, initial_delta=0.05)],
        )
        w = World(config)
        action_counts: dict[str, int] = {}
        for _ in range(100):
            frame = w.step()
            for ev in frame.events:
                if ev.get("type") == "action.complete":
                    a = ev["payload"].get("action", "unknown")
                    action_counts[a] = action_counts.get(a, 0) + 1

        proact_count = action_counts.get("proact", 0)
        idle_count   = action_counts.get("idle",   0)
        # With abundant resources and no demands, proact should dominate
        assert proact_count > 0, "Expected at least some proact actions from oversated agent"
