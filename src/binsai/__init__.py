"""Binsai — Bio-Inspired Neuro-Symbolic AI.

Give agents motivations, not just capabilities.
"""

__version__ = "0.1.3"
__author__  = "Patricio Gerpe"
__email__   = "pj.patriciojulian@gmail.com"

from .agent  import BinsaiAgent, Position
from .drives import Drives, Drive, Stratum, ZoneSpec
from .fuzzy  import compute_action_distribution, zone_memberships
from .lifecycle import FIPAState, LifecycleManager
from .actions import ActionKind, RegulatoryBudgets
from .acl import ACLMessage, Performative, Mailbox
from .sleep import ConsolidationWorker, WakeGuard, SleepConfig
from .action_registry import ActionSpec, ActionSet
from .llm import DeepSeekBackend, DryRunBackend, get_backend, LLMTelemetry, ModelConfig
from .report import SimulationLog
from .world.world import World, WorldConfig, AgentConfig, AgentFrame, WorldFrame

__all__ = [
    # Core
    "BinsaiAgent",
    "Position",
    # Drives
    "Drives",
    "Drive",
    "Stratum",
    "ZoneSpec",
    # Lifecycle
    "FIPAState",
    "LifecycleManager",
    # Actions & budgets
    "ActionKind",
    "RegulatoryBudgets",
    # Communication
    "ACLMessage",
    "Performative",
    "Mailbox",
    # Sleep
    "ConsolidationWorker",
    "WakeGuard",
    "SleepConfig",
    # LLM
    "DeepSeekBackend",
    "DryRunBackend",
    "get_backend",
    "LLMTelemetry",
    "ModelConfig",
    # Actions
    "ActionSpec",
    "ActionSet",
    # Telemetry
    "SimulationLog",
    # World / simulation
    "World",
    "WorldConfig",
    "AgentConfig",
    "AgentFrame",
    "WorldFrame",
    # Fuzzy
    "compute_action_distribution",
    "zone_memberships",
]
