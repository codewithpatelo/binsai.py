"""Tests for Binsai core MVP 1."""

import pytest
from binsai import BinsaiAgent, Drives, Drive, Stratum, Position


def test_create_agent():
    agent = BinsaiAgent(name="TestAgent", dry_run_llm=True)
    assert agent.name == "TestAgent"
    assert len(agent.aid) == 8
    assert agent.status == "initiated"


def test_drives_stratified_subset():
    drives = Drives.from_names(["metabolic", "safety"])
    assert drives.get("metabolic") is not None
    assert drives.get("safety") is not None
    assert drives.get("epistemic") is None
    metabolic = drives.get("metabolic")
    assert metabolic is not None
    assert metabolic.stratum == Stratum.MATERIAL
    assert 0 <= metabolic.value <= 1


def test_drive_update():
    drive = Drive(name="test", stratum=Stratum.BIOLOGICAL, value=0.80, set_point=0.50,
                  kappa=0.1, lambda_rate=0.0, spring="linear")
    initial = drive.value
    drive.update(tick=0)
    # Elastic return toward set-point: x = x - kappa*(x - set_point) + lambda
    # 0.80 - 0.1*(0.80 - 0.50) + 0 = 0.80 - 0.03 = 0.77
    assert drive.value < initial


def test_drive_update_pulsatile():
    """Default spring: tension charges silently until θ, then discharges."""
    drive = Drive(name="test", stratum=Stratum.BIOLOGICAL, value=0.80, set_point=0.50,
                  kappa=0.1, lambda_rate=0.0, spring_threshold=0.05)
    drive.update(tick=0)
    # first pulse: σ += 0.1·0.3·e^(−0.3/0.3) ≈ 0.011 < θ=0.05 → no release yet
    assert drive.value == 0.80
    released = []
    drive.on("TensionReleased", lambda p: released.append(p))
    for t in range(1, 20):
        drive.update(tick=t)
    assert released          # tension crossed θ and pulsed
    assert drive.value < 0.80  # the discharge pulled the level down
    assert any(k == "release" for _, k in drive.events)  # rug marks


def test_pulsatile_drift_escapes_to_viability():
    """λ > spring grip (κρw/e): neglect escalates past the reach and kills."""
    breaches = []
    d = Drive(name="h", value=0.30, set_point=0.30, kappa=0.04,
              lambda_rate=0.008, spring_reach=0.25, spring_threshold=0.12,
              viability=(0.10, 0.90))
    d.on("ViabilityBreached", lambda p: breaches.append(p))
    for t in range(300):
        d.update(tick=t)
    assert breaches and d.value >= 0.90


def test_pulsatile_grip_holds_weak_drift():
    """λ < grip: the spring holds — bounded oscillation, never critical."""
    d = Drive(name="h", value=0.30, set_point=0.30, kappa=0.05,
              lambda_rate=0.001, spring_reach=0.30)
    for t in range(400):
        d.update(tick=t)
    assert d.value < 0.80
    vals = [v for _, v in d.history[-60:]]
    assert max(vals) - min(vals) > 0.02  # genuinely oscillating, not flat


def test_event_emission():
    agent = BinsaiAgent(name="TestAgent", drives=Drives.from_names(["metabolic"]), dry_run_llm=True)
    received = []
    agent.on("test_event", lambda p: received.append(p))
    agent.emit("test_event", {"data": 123})
    assert len(received) == 1
    assert received[0]["data"] == 123


def test_state_introspection():
    agent = BinsaiAgent(name="TestAgent", drives=Drives.from_names(["metabolic"]), dry_run_llm=True)
    state = agent.get_state()
    assert state["name"] == "TestAgent"
    assert state["delta"] is not None
    assert state["zone"] is not None
    assert "memberships" in state


def test_position():
    pos1 = Position(x=0, y=0)
    pos2 = Position(x=3, y=4)
    assert pos1.distance_to(pos2) == 5.0


def test_working_memory():
    agent = BinsaiAgent(name="TestAgent", dry_run_llm=True)
    for i in range(10):
        agent.remember({"item": i})
    recent = agent.recall_recent(7)
    assert len(recent) == 7
    assert recent[-1]["item"] == 9


def test_drive_zones():
    drive = Drive(name="test", stratum=Stratum.BIOLOGICAL, value=0.30)
    zone = drive.get_zone()
    assert zone in ("critical_superavit", "high_superavit", "moderate_superavit",
                     "equilibrium", "moderate_deficit", "high_deficit", "critical_deficit")


def test_drive_to_dict():
    drive = Drive(name="metabolic", stratum=Stratum.MATERIAL, value=0.30)
    d = drive.to_dict()
    assert "value" in d
    assert "set_point" in d
    assert "zone" in d
    assert "memberships" in d


def test_drives_all():
    drives = Drives.stratified()
    assert len(drives.all) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
