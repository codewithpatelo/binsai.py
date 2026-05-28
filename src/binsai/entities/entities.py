from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict, Union
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph


class LangpifyEvent(TypedDict):
    type: str
    source: str  # Agent ID that emitted the event
    timestamp: float
    data: Dict[str, Any]  # Event payload


class LangpifyRole(TypedDict):
    name: str
    content: str


class LangpifyGoal(TypedDict):
    name: str
    content: str


class LangpifyAgentState(ABC):
    """
    Clase abstracta
    Represents the agent's state, which can be generalized to different frameworks:
    - For standard use: Basic key-value state with utterance and response
    - For langgraph: Can be used as a base for StateGraph nodes

    When using with langgraph, this can be used directly with StateGraph.
    See: https://deepwiki.com/langchain-ai/langgraphjs/2.1-stategraph
    """


class LangpifyConfig(TypedDict):
    framework: Literal["langchain", "langgraph", "llamaindex"]


class LangpifyAgentType(Enum):
    """Inspired in the Viable System Model from Management Cybernetics"""

    OPS_AGENT = "OpsAgent"
    COORDINATOR_AGENT = "CoordinatorAgent"
    CONTROL_AGENT = "ControlAgent"
    INTEL_AGENT = "IntelAgent"
    STRAT_AGENT = "StratAgent"


class Framework(str, Enum):
    """Supported AI Frameworks."""

    LANGCHAIN = "langchain"
    LANGGRAPH = "langgraph"
    LLAMAINDEX = "llamaindex"


class LangpifyStatus(str, Enum):
    """Agent lifecycle status inspired on FIPA and ACP specifications.

    References:
    - http://fipa.org/specs/fipa00023/SC00023K.html (5.1)
    - https://www.researchgate.net/figure/Agent-life-cycle-as-defined-by-FIPA_fig1_332959107
    - https://agentcommunicationprotocol.dev/core-concepts/agent-run-lifecycle
    """

    ACTIVE = "active"  # Agent is sensoring stimuli and computing needs  - Recommended visual feedback:  Glowing Green
    INITIATED = "initiated"  # Agent has been created but not fully activated - Recommended visual feedback:  Smooth Glowing Green
    SUSPENDED = "suspended"  # Agent is temporarily paused - Recommended visual feedback:  Static Grey
    WORKING = "working"  # Agent is actively performing tasks - Recommended visual feedback:  Flashing Green
    DELETED = "deleted"  # Agent has been terminated - Recommended visual feedback:  Static Black
    WAITING = "waiting"  # Agent is waiting for an event or resource - Recommended visual feedback:  Flashing Yellow
    ERROR = "error"  # Agent has encountered an error - Recommended visual feedback: Glowing Red


class LangpifyDynamicPrompt(BaseModel):
    role: Optional[str] = None
    goal: Optional[str] = None
    instructions: Optional[str] = None
    extras: Optional[str] = None
    examples: Optional[str] = None
    output: Optional[str] = None
    guardrails: Optional[str] = None


class LangpifyNeed(BaseModel):
    """Represents a need with homeostatic dynamics inspired by psychological motivation theory.
    
    A need has a current value that decays over time and can be satisfied through specific events.
    This creates emergent behavior where agents are driven by internal states.
    
    Attributes:
        name: Unique identifier for the need (e.g., 'life_purpose', 'social_connection')
        value: Current satisfaction level (0.0 = completely unsatisfied, 1.0 = fully satisfied)
        decay_rate: Rate at which the need decays per second (linear decay)
        satiation_rate: Rate at which the need is satisfied when satiation event occurs
        satiation_event_type: Type of event that satisfies this need
        min_value: Minimum value the need can reach (default 0.0)
        max_value: Maximum value the need can reach (default 1.0)
        last_updated: Timestamp of last update (seconds since epoch)
        description: Human-readable description of what this need represents
    """
    name: str
    value: float = 0.5  # Start at medium satisfaction
    decay_rate: float = 0.01  # Default: 1% decay per second
    satiation_rate: float = 0.3  # Default: 30% increase per satiation event
    satiation_event_type: str = "generic_satisfaction"
    min_value: float = 0.0
    max_value: float = 1.0
    last_updated: float = 0.0  # Will be set to current time on initialization
    description: Optional[str] = None
    
    def decay(self, elapsed_seconds: float) -> float:
        """Apply decay function to the need value.
        
        Uses linear decay: value -= decay_rate * elapsed_seconds
        
        Args:
            elapsed_seconds: Time elapsed since last update
            
        Returns:
            New value after decay
        """
        decayed_value = self.value - (self.decay_rate * elapsed_seconds)
        self.value = max(self.min_value, decayed_value)
        return self.value
    
    def satiate(self, satiation_amount: Optional[float] = None) -> float:
        """Apply satiation function to the need value.
        
        Uses exponential satiation with diminishing returns:
        The closer to max_value, the less effective satiation becomes.
        
        Args:
            satiation_amount: Optional custom satiation amount. If None, uses satiation_rate
            
        Returns:
            New value after satiation
        """
        if satiation_amount is None:
            satiation_amount = self.satiation_rate
        
        # Exponential satiation with diminishing returns
        # The formula: value + satiation_amount * (1 - value)^2
        # This means: the higher the current value, the less effective satiation is
        remaining_capacity = self.max_value - self.value
        effective_satiation = satiation_amount * (remaining_capacity / self.max_value) ** 0.5
        
        new_value = self.value + effective_satiation
        self.value = min(self.max_value, new_value)
        return self.value
    
    def get_urgency_level(self) -> str:
        """Get a human-readable urgency level based on current value.
        
        Returns:
            String describing urgency: 'critical', 'high', 'medium', 'low', 'satisfied'
        """
        if self.value < 0.2:
            return "critical"
        elif self.value < 0.4:
            return "high"
        elif self.value < 0.6:
            return "medium"
        elif self.value < 0.8:
            return "low"
        else:
            return "satisfied"
    
    def to_context_string(self) -> str:
        """Generate a context string for LLM prompts.
        
        Returns:
            Formatted string describing the need state
        """
        urgency = self.get_urgency_level()
        percentage = int(self.value * 100)
        return f"{self.name}: {percentage}% satisfied (urgency: {urgency})"


class LangpifyAgentResponse(BaseModel):
    """Structured response from an agent that includes introspection about needs.
    
    This model captures not just what the agent says, but also how it feels
    and how the interaction affects its internal needs.
    
    Attributes:
        response: The natural language response to the message
        emotional_introspection: How the agent felt about the message
        purpose_introspection: Numeric value (-1.0 to 1.0) indicating how the message
                              affected the agent's sense of life purpose
                              -1.0 = very detrimental to purpose
                               0.0 = neutral
                               1.0 = very fulfilling to purpose
        reasoning: Optional chain of thought explaining the introspections
    """
    response: str
    emotional_introspection: str
    purpose_introspection: float  # -1.0 to 1.0
    reasoning: Optional[str] = None


class AISettings(TypedDict):
    """Settings for the AI framework
    Langpify works as a meta-framework, allowing higher-level generalization
    in a framework-agnostic way.

    Note that in productive environments default values would be set by environment variables
    """

    _framework: Optional[Framework]
    # Another possible params are _embedding_model,_vector_db: and a global default settings for _llm


class LangpifyAuthorizations(TypedDict, total=False):
    """Basic schema for authorizations and AI governance
    with BYOK approach (Bring Your Own Key)"""

    access_token: Optional[str]
    organizations: Optional[List[str]]
    applications: Optional[List[str]]
    projects: Optional[List[str]]
    roles: Optional[List[str]]
    permissions: Optional[List[str]]
    risk_tier: Optional[str]
    compliance_docs_url: Optional[List[str]]
    allowed_tools: Optional[List[str]]
    allowed_models: Optional[List[str]]


class LangpifyGuardrails(TypedDict):
    prompt: str


class LangpifySafety(TypedDict):
    guardrails: LangpifyGuardrails


class LangpifyTemplateLLM(TypedDict, total=False):
    provider: str
    model: str
    temperature: Optional[float]
    max_tokens: Optional[int]


class LangpifyTemplateLLMGateway(TypedDict):
    primary_model: LangpifyTemplateLLM
    secondary_model: Optional[LangpifyTemplateLLM]


class LangpifyTemplateLanguage(TypedDict):
    default: str
    llm: LangpifyTemplateLLMGateway


class LangpifyLLM(TypedDict, total=False):
    """Represents a language model instance for an agent.

    This class defines the language model that an agent will use for communication,
    including the provider (e.g., OpenAI, Anthropic), model name, and optionally
    the actual model instance if already instantiated.
    """

    model_provider: str  # Provider of the language model (e.g., 'openai', 'anthropic', 'local')
    model_name: str  # Name of the specific model (e.g., 'gpt-4', 'claude-3')
    model: Optional[Any]  # The actual model instance, if already instantiated


class LangpifyLanguage(TypedDict):
    """Language configuration for an agent including LLM settings"""

    default: str
    llm: LangpifyLLM


class LangpifyTemplateWorkflow(TypedDict):
    type: str


class LangpifyTemplateGoal(TypedDict):
    name: str
    prompt: str
    prompt_extras: str


class LangpifyExecutionProtocol(TypedDict):
    prompt: str
    prompt_examples: str
    prompt_output: str


class LangpifyTemplatePlanning(TypedDict):
    workflow: LangpifyTemplateWorkflow
    excecution_protocol: LangpifyExecutionProtocol
    goal: LangpifyTemplateGoal


class LangpifyWorkflow(TypedDict):
    """This is just examplary
    LangpifyWorkflow is agnostic to any framework so its value type would depend on the framework set
    """

    graph: StateGraph


class LangpifyPlanning(TypedDict):
    workflow: LangpifyWorkflow
    excecution_protocol: LangpifyExecutionProtocol
    goal: LangpifyGoal
