"""Binsai — Bio-Inspired Neuro-Symbolic AI.

Give agents motivations, not just capabilities.
"""

__version__ = "0.0.1.dev0"
__author__  = "Patricio Gerpe"
__email__   = "pj.patriciojulian@gmail.com"

from .agent  import BinsaiAgent, Position
from .drives import Drives, Drive, Stratum
from .fuzzy  import compute_action_distribution, zone_memberships
from .lifecycle import FIPAState, LifecycleManager
from .actions import ActionKind, RegulatoryBudgets
from .acl import ACLMessage, Performative, Mailbox
from .sleep import ConsolidationWorker, WakeGuard, SleepConfig
from .world.world import World, WorldConfig, AgentConfig, AgentFrame, WorldFrame

__all__ = [
    # Core
    "BinsaiAgent",
    "Position",
    # Drives
    "Drives",
    "Drive",
    "Stratum",
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
