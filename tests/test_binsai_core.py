"""Tests for Binsai core MVP 1.

Validates:
- BinsaiAgent creation
- Drives system (metabolic, safety)
- Event emission affecting drives
- State introspection
"""

import pytest
from binsai import BinsaiAgent, Drives, Drive, Stratum, Position


def test_create_agent():
    """Test basic agent creation."""
    agent = BinsaiAgent(name="TestAgent")
    assert agent.name == "TestAgent"
    assert len(agent.aid) == 8  # UUID short
    assert agent.status == "idle"


def test_drives_stratified_subset():
    """Test creating subset of drives."""
    drives = Drives.from_names(["metabolic", "safety"])
    
    assert drives.get("metabolic") is not None
    assert drives.get("safety") is not None
    assert drives.get("epistemic") is None
    
    metabolic = drives.get("metabolic")
    assert metabolic.stratum == Stratum.MATERIAL
    assert 0 <= metabolic.value <= 1


def test_drive_decay():
    """Test that drives decay over time."""
    drive = Drive(
        name="test",
        stratum=Stratum.BIOLOGICAL,
        value=0.8,
        set_point=0.5,
        decay_rate=0.1,
    )
    
    initial = drive.value
    import time
    time.sleep(0.1)  # Small delay
    drive.update()
    
    # Should have decayed toward set_point (0.5)
    assert drive.value < initial


def test_event_affects_drives():
    """Test that events modify drive values."""
    agent = BinsaiAgent(
        name="TestAgent",
        drives=Drives.from_names(["metabolic", "safety"])
    )
    
    metabolic = agent.get_drive("metabolic")
    initial = metabolic.value
    
    # Emit token consumption
    agent.emit("token_consumed", {"cost": 0.1})
    
    # Should have depleted
    assert metabolic.value < initial


def test_state_introspection():
    """Test agent state export."""
    agent = BinsaiAgent(
        name="TestAgent",
        drives=Drives.from_names(["metabolic", "safety"])
    )
    
    state = agent.get_state()
    assert state.name == "TestAgent"
    assert "metabolic" in state.drives
    assert "safety" in state.drives
    
    # Check drive format
    metabolic_state = state.drives["metabolic"]
    assert "value" in metabolic_state
    assert "set_point" in metabolic_state
    assert "zone" in metabolic_state


def test_prompt_context():
    """Test drive prompt context generation."""
    agent = BinsaiAgent(
        name="TestAgent",
        drives=Drives.from_names(["metabolic", "safety"])
    )
    
    context = agent.get_drive_prompt_context()
    assert "Internal regulatory state" in context
    assert "metabolic" in context
    assert "zone:" in context


def test_position():
    """Test spatial situatedness."""
    pos1 = Position(x=0, y=0)
    pos2 = Position(x=3, y=4)
    
    assert pos1.distance_to(pos2) == 5.0


def test_working_memory():
    """Test bounded working memory."""
    agent = BinsaiAgent(name="TestAgent")
    
    # Fill beyond capacity
    for i in range(10):
        agent.remember({"item": i})
    
    # Should only keep last 7 (Miller's law)
    recent = agent.recall_recent(7)
    assert len(recent) == 7
    assert recent[-1]["item"] == 9  # Most recent


def test_event_handlers():
    """Test event system."""
    agent = BinsaiAgent(name="TestAgent")
    
    received = []
    
    def handler(payload):
        received.append(payload)
    
    agent.on("test_event", handler)
    agent.emit("test_event", {"data": 123})
    
    assert len(received) == 1
    assert received[0]["data"] == 123


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
