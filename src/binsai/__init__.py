"""Binsai — Bio-Inspired Neuro-Symbolic AI.

Give agents motivations, not just capabilities.
"""

__version__ = "0.3.0"
__author__  = "Patricio Gerpe"
__email__   = "pj.patriciojulian@gmail.com"

from .agent  import BinsaiAgent, Position
from .drives import Drives, Drive, Stratum, ZoneSpec
from .fuzzy  import compute_action_distribution, zone_memberships
from .lifecycle import FIPAState, LifecycleManager
from .actions import ActionKind, RegulatoryBudgets, ExpectedEffect
from .acl import ACLMessage, Performative, Mailbox
from .events import (
    EventEmitter, PULSE, ZONE_CHANGED, PRESSURE_UPDATED, SENSOR_INVALID,
    VIABILITY_BREACHED, SATIATED, COUPLED,
    PERTURBED, DRIVE_SATURATED, EXPECTED_EFFECT, G_MEASURED,
    ACTIVATION_DRAW, ACTIVATION_FAILED, ACTION_REJECTED,
    GUARD_SIGNAL_UNCAL, GUARD_REJECTED,
    CONTRACT_VERIFIED, CONTRACT_REINJECTED,
)
from .guards import Guard, GuardVerdict
from .contract import ViabilityContract
from .observed import ObservedVariable, VariableKind, RateEstimator, load_contract
from .sleep import ConsolidationWorker, WakeGuard, SleepConfig
from .action_registry import ActionSpec, ActionSet
from .llm import DeepSeekBackend, DryRunBackend, get_backend, LLMTelemetry, ModelConfig
from .report import SimulationLog
from .viz import timeline_svg, timeline_html, trajectory_artifact, TrajectoryArtifact
from .viability_space import (
    ViabilityRecording, record_viability_run, render_viability_space,
)
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
    "ExpectedEffect",
    # Guards & contract (EPA v2.1)
    "Guard",
    "GuardVerdict",
    "ViabilityContract",
    # Communication
    "ACLMessage",
    "Performative",
    "Mailbox",
    # Events (canonical EPA)
    "EventEmitter",
    "PULSE",
    "ZONE_CHANGED",
    "PRESSURE_UPDATED",
    "SENSOR_INVALID",
    "VIABILITY_BREACHED",
    "SATIATED",
    "COUPLED",
    # EPA v2.1 events
    "PERTURBED",
    "DRIVE_SATURATED",
    "EXPECTED_EFFECT",
    "G_MEASURED",
    "ACTIVATION_DRAW",
    "ACTIVATION_FAILED",
    "ACTION_REJECTED",
    "GUARD_SIGNAL_UNCAL",
    "GUARD_REJECTED",
    "CONTRACT_VERIFIED",
    "CONTRACT_REINJECTED",
    # Observed variables
    "ObservedVariable",
    "VariableKind",
    "RateEstimator",
    "load_contract",
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
    # Visualization
    "timeline_svg",
    "timeline_html",
    "trajectory_artifact",
    "TrajectoryArtifact",
    "ViabilityRecording",
    "record_viability_run",
    "render_viability_space",
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
