import time
import uuid
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Implementación temporal de AgentCard hasta resolver python-a2a
@dataclass
class AgentCard:
    """Tarjeta de agente compatible con A2A (implementación temporal)."""
    name: str
    description: str
    version: str
    url: str
    capabilities: List[str]
    skills: List[str]

# Intentar importar desde python-a2a, usar implementación temporal si falla
try:
    from python_a2a import A2AServer, TaskState, TaskStatus
    # Si AgentCard no está disponible, usar nuestra implementación
    try:
        from python_a2a import AgentCard as A2AAgentCard
        AgentCard = A2AAgentCard
    except ImportError:
        pass  # Usar nuestra implementación temporal
except ImportError:
    # Si python-a2a no está disponible, crear stubs
    class A2AServer:
        pass
    
    class TaskState:
        pass
    
    class TaskStatus:
        pass
from .entities import (
    LangpifyAgentState,
    LangpifyEvent,
    LangpifyGoal,
    LangpifyLanguage,
    LangpifyRole,
    LangpifyStatus,
    LangpifyAgentType,
    LangpifyAuthorizations,
    LangpifySafety,
    AISettings,
    LangpifyPlanning,
    LangpifyLLM,
    LangpifyNeed,
    LangpifyAgentResponse,
)



class LangpifyBaseAgent():
    """
    LangpifyBaseAgent define una interfaz base para agentes conversacionales inspirada en estándares de interoperabilidad emergentes.

    ✅ Usa un enfoque declarativo (role, goals, state) que permite configurar comportamientos de agentes sin lógica rígida.
    ✅ Se alinea con la pionera filosofía FIPA: agentes definidos por roles, metas y estados comunicativos, pero sin la rígidez de ACL.
    ✅ Al mismo tiempo se adapta a protocolos modernos como MCP y A2A.
       que promueven estructuras comunes para agentes LLM colaborativos.

    ➕ Beneficio clave: promueve modularidad, estandarización, reutilización y diseño orientado a interoperabilidad entre agentes LLM
       sin acoplamiento a una plataforma específica.

    ## Implementación A2A

    El método `register()` implementa el protocolo A2A (Agent-to-Agent), permitiendo que cualquier agente
    basado en esta clase pueda exponerse como un servicio web compatible con el estándar A2A. Esto facilita:

    1. Interoperabilidad: El agente puede comunicarse con otros agentes que implementen el protocolo A2A,
       independientemente del lenguaje o framework en que estén implementados.

    2. Descubrimiento: A través de la tarjeta de agente (agent_card), otros sistemas pueden descubrir
       las capacidades del agente automáticamente.

    3. Comunicación estandarizada: El protocolo define un formato común para el intercambio de mensajes
       entre agentes, facilitando la integración en ecosistemas multi-agente.

    4. Exposición como API: El agente se expone a través de una API REST que sigue el estándar A2A,
       permitiendo su integración en aplicaciones web y móviles.

    Para más información sobre el protocolo A2A, consultar:
    https://python-a2a.readthedocs.io/en/latest/quickstart.html#creating-a-simple-a2a-agent
    """

    def __init__(
        self,
        aid: Optional[str] = None,
        name: str = None,
        type: Optional[LangpifyAgentType] = None,
        role: Optional[LangpifyRole] = None,
        goals: Optional[List[LangpifyGoal]] = None,
        authorizations: Optional[LangpifyAuthorizations] = None,
        safety: Optional[LangpifySafety] = None,
        status: LangpifyStatus = LangpifyStatus.INITIATED,
        settings: Optional[AISettings] = None,
        language: Optional[LangpifyLanguage] = None,
        planning: Optional[LangpifyPlanning] = None,
        response_model: Optional[type[BaseModel]] = None,
        state_schema: Optional[type[BaseModel]] = None,
        tools: Optional[List[Callable]] = None,
        skills: Optional[List[Callable]] = None,
        sub_workflows: Optional[list[StateGraph]] = None,
        needs: Optional[List[LangpifyNeed]] = None,
    ):
        """IDENTITY"""
        self.aid: Optional[str] = aid if aid is not None else f"agent_{uuid.uuid4()}"
        self.name: str = name
        self.role: Optional[LangpifyRole] = role or {"name": "", "content": ""}
        self.type: Optional[LangpifyAgentType] = type

        # Tarjeta de agente compatible con A2A
        self.agent_card = AgentCard(
            name=self.role.get("name", f"Agente-{self.aid}"),
            description=self.role.get("content", ""),
            version="0.1.0",
            url="",
            capabilities=[],
            skills=skills or [],
        )
        # Para más info -> https://google.github.io/A2A/specification/agent-card/

        """ LIFECYCLE """
        self.status: LangpifyStatus = status
        # Inspirado en ciclo de vida de FIPA y ACP
        # Para más info -> http://fipa.org/specs/fipa00023/SC00023K.html (5.1)
        # https://www.researchgate.net/figure/Agent-life-cycle-as-defined-by-FIPA_fig1_332959107

        """ GOVERNANCE """
        self.authorizations: LangpifyAuthorizations = authorizations or {
            "access_token": "*",
            "organizations": ["*"],
            "applications": ["*"],
            "projects": ["*"],
            "roles": ["*"],
        }
        self.safety: LangpifySafety = safety or {"guardrails": {"prompt": "*"}}
        self.settings: Optional[AISettings] = settings

        """ LANGUAGE MENTAL PROCESSES """
        self.language: Optional[LangpifyLanguage] = language
        # Language model configuration for communication

        """ PLANNING MENTAL PROCESSES """
        self.planning: Optional[LangpifyPlanning] = planning
        self.response_model: Optional[type[BaseModel]] = response_model
        self.state_schema: Optional[type[BaseModel]] = state_schema
        self.tools: Optional[List[Callable]] = tools
        self.sub_workflows: Optional[list[StateGraph]] = sub_workflows
        # Planning includes workflow, execution protocol, and goals

        """ MEMORY MENTAL PROCESSES 
        Reserved for Memory Engines (short-term, long-term)
        
        Short-Term -> Session Context | Example: Langgraph's MemorySaver
        Long-Term -> Episodic, Semantic, Procedural | Example: Langgraph's Store with PostgreSQL + Milvus
        
        In productive environments we would work with SQL, Mongodb and/or Vectorial/Graph Databases accordingly
        """

        """ REASONING MENTAL PROCESSES 
        Reserved for CoT and Inference Engines like Prolog
        
        In Langpify we include Decision-Support Algorithms like TOPSIS and other Multi-Criteria Methods.
        """

        """ PERCEPTION MENTAL PROCESSES 
        Reserved for Event Communication 
        
        Event-based Sensors and Actuators | Fuzzy Thresholds for Reactions
        """

        # El agente puede "percibir" eventos del entorno a través de sensores (funcionan como event listeners)
        self._local_sensors: Dict[str, List[Callable[[LangpifyEvent], None]]] = {}
        # Sensores locales escuchan eventos de un tipo en particular

        self._global_sensors: List[Callable[[LangpifyEvent], None]] = []
        # Sensores globales escuchan eventos de cualquier tipo

        # IDs de otros agentes a los que este agente escucha
        self._subscribed_agents: Set[str] = set()

        # Goals for goal-oriented behavior
        self.goals: Optional[List[LangpifyGoal]] = goals or []

        # MOTIVATIONAL MENTAL PROCESSES - Homeostatic need system
        self.needs: Dict[str, LangpifyNeed] = {}
        if needs:
            current_time = time.time()
            for need in needs:
                need.last_updated = current_time
                self.needs[need.name] = need

        # Este sistema de comunicación será, por el momento, únicamente entre agentes de la misma aplicación
        # Para comunicación entre agentes de otro sistema usamos A2A, registrando este agente usando el método register
        # Se prevee usar el modelo "TransportLayer", inspirado en FIPA Y MCP para comunicación protocolar (WS, JSONRPC, colas, etc...)

        # 2. Atención y Memoria
        #if self.settings.framework.value == "langgraph":
            # Si es langgraph, usamos MemorySaver de langgraph
      #      self.memory = MemorySaver()
       # else:
            # Si no es langgraph,
       #     self.memory = None  # Se deberá implementar en las clases concretas

        # 3. Motivación
        self.goals = goals or []  # Metas (Variable inyectada en prompt dinamico)
        # En futuro podemos trabajar con objetivos optimizables o IA basada en necesidades (función homeostática, función de saciedad y decaimiento, etc...)

        # A partir de prompt engineering podríamos modelar inteligencia emocional.
        # Por ahora, no es un objetivo prioritario.

        # PROCESOS MENTALES SUPERIORES
        # 1. Lenguaje
        self.language: LangpifyLanguage = {}
        # Aca colocamos la instancia del modelo de LLM utilizado. Ejem o4.

        # 2. Planificación
        self.workflow = None
        # El flujo de trabajo se correspode a un grafo. Si es langgraph, la implementación concreta es el grafo compilado.

        # Posibles procesos adicionales: Aprendizaje

    ## Métodos del Agente ##
    def adapt(self, key: str, value: Optional[str]):
        """
        Adapta el estado interno del agente ante un evento externo.

        Permite el cambio del estado del agente según un valor provisto. La adaptación
        se entiende como un cambio del estado interno del agente en respuesta a
        un evento externo.

        Args:
            key: Clave del estado a modificar
            value: Valor a asignar (puede ser None para eliminar un estado)
        """
        # Guardar el valor anterior para potencialmente incluirlo en el evento
        previous_value = self.state.get(key) if hasattr(self.state, "get") else None

        # Actualizar el estado
        self.state[key] = value

        # Emitir un evento de cambio de estado
        self.emit(
            "state_changed",
            {"key": key, "value": value, "previous_value": previous_value},
        )

    # Entendemos a adaptación a un cambio del estado interno del agente ante un evento externo.
    # Por su parte, un evento es toda variedad de estados (sea internos o externos)

    def sense(self, key: str) -> Optional[str]:
        return self.state.get(key, None)

    ## Métodos del Sistema de Eventos ##
    def emit(self, event_type: str, data: Dict[str, Any] = None) -> None:
        """
        Emit an event to all subscribed listeners.

        Args:
            event_type: The type of event being emitted
            data: Optional data payload for the event
        """
        if data is None:
            data = {}

        event: LangpifyEvent = {
            "type": event_type,
            "source": self.aid,
            "timestamp": time.time(),
            "data": data,
        }

        # Si el agente está suspendido y el evento no es de cambio de estado, no procesamos eventos
        # Esto permite que los eventos status_changed siempre se procesen para poder reactivar el agente
        if self.status == LangpifyStatus.SUSPENDED and event_type != "status_changed":
            # Opcionalmente podemos registrar que se ignoró un evento debido a la suspensión
            return

        # Notificar a los listeners de este tipo de evento específico
        if event_type in self._local_sensors:
            for listener in self._local_sensors[event_type]:
                listener(event)

        # Notificar a los listeners globales que reciben todos los eventos
        for listener in self._global_sensors:
            listener(event)

    def on(
        self, event_type: str, callback: Callable[[LangpifyEvent], None]
    ) -> None:  
        """
        Register a listener for a specific event type.

        Args:
            event_type: The type of event to listen for
            callback: Function to call when the event occurs
        """
        if event_type not in self._local_sensors:
            self._local_sensors[event_type] = []

        self._local_sensors[event_type].append(callback)

    def off(self, event_type: str, callback: Callable[[LangpifyEvent], None]) -> None:
        """
        Remove a listener for a specific event type.

        Args:
            event_type: The type of event
            callback: The callback function to remove
        """
        if (
            event_type in self._local_sensors
            and callback in self._local_sensors[event_type]
        ):
            self._local_sensors[event_type].remove(callback)

    def on_any(self, callback: Callable[[LangpifyEvent], None]) -> None:
        """
        Register a listener for all event types.

        Args:
            callback: Function to call when any event occurs
        """
        self._global_sensors.append(callback)

    def off_any(self, callback: Callable[[LangpifyEvent], None]) -> None:
        """
        Remove a listener for all event types.

        Args:
            callback: The callback function to remove
        """
        if callback in self._global_sensors:
            self._global_sensors.remove(callback)

    def subscribe_to(self, agent: "LangpifyBaseAgent") -> None:
        """
        Subscribe to events from another agent.

        Args:
            agent: The agent to subscribe to
        """
        # Agregar este agente como suscriptor a los eventos del otro agente
        self._subscribed_agents.add(agent.aid)

        # Registrar un handler en el otro agente para reenviar eventos a este agente
        agent.on_any(self._handle_external_event)

    def unsubscribe_from(self, agent: "LangpifyBaseAgent") -> None:
        """
        Unsubscribe from events from another agent.

        Args:
            agent: The agent to unsubscribe from
        """
        if agent.aid in self._subscribed_agents:
            self._subscribed_agents.remove(agent.aid)
            agent.off_any(self._handle_external_event)

    def _handle_external_event(self, event: LangpifyEvent) -> None:
        """
        Handle events from other agents this agent is subscribed to.

        Args:
            event: The event from the other agent
        """
        # Si el agente está suspendido y el evento no es de cambio de estado, no procesamos eventos
        # Esto permite que los eventos status_changed siempre se procesen para poder reactivar el agente
        if (
            self.status == LangpifyStatus.SUSPENDED
            and event["type"] != "status_changed"
        ):
            # Opcionalmente podemos registrar que se ignoró un evento externo debido a la suspensión
            return

        # Procesar el evento - por defecto solo reenviarlo a los listeners de este agente
        if event["source"] in self._subscribed_agents:
            # Reenviar a listeners de tipo de evento específico
            if event["type"] in self._local_sensors:
                for listener in self._local_sensors[event["type"]]:
                    listener(event)

            # Reenviar a listeners globales
            for listener in self._global_sensors:
                listener(event)

    ## Need System Methods ##
    def update_needs(self) -> Dict[str, float]:
        """
        Update all needs based on elapsed time since last update.
        
        This method applies decay functions to all needs and should be called
        periodically (e.g., before processing new messages).
        
        Returns:
            Dictionary mapping need names to their updated values
        """
        current_time = time.time()
        updated_values = {}
        
        for need_name, need in self.needs.items():
            elapsed = current_time - need.last_updated
            if elapsed > 0:
                need.decay(elapsed)
                need.last_updated = current_time
            updated_values[need_name] = need.value
        
        # Emitir evento sobre actualización de necesidades
        if self.needs:
            self.emit("needs_updated", {"needs": updated_values})
        
        return updated_values
    
    def process_need_satisfaction(self, event_type: str, satiation_amount: Optional[float] = None) -> Dict[str, float]:
        """
        Process satisfaction of needs based on an event type.
        
        Checks if any needs are satisfied by the given event type and applies
        satiation functions accordingly.
        
        Args:
            event_type: Type of event that occurred
            satiation_amount: Optional custom satiation amount for all matching needs
            
        Returns:
            Dictionary mapping satisfied need names to their updated values
        """
        satisfied_needs = {}
        current_time = time.time()
        
        for need_name, need in self.needs.items():
            if need.satiation_event_type == event_type:
                old_value = need.value
                new_value = need.satiate(satiation_amount)
                need.last_updated = current_time
                satisfied_needs[need_name] = new_value
                
                # Emitir evento sobre satisfacción de necesidad
                self.emit("need_satisfied", {
                    "need_name": need_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "event_type": event_type
                })
        
        return satisfied_needs
    
    def get_needs_context(self) -> str:
        """
        Generate a context string describing all current needs.
        
        This string can be included in LLM prompts to make the agent aware
        of its internal motivational state.
        
        Returns:
            Formatted string describing all needs and their states
        """
        if not self.needs:
            return "No active needs."
        
        # Actualizar necesidades antes de generar contexto
        self.update_needs()
        
        context_lines = ["Current Internal Needs:"]
        for need_name, need in self.needs.items():
            context_lines.append(f"  - {need.to_context_string()}")
            if need.description:
                context_lines.append(f"    ({need.description})")
        
        return "\n".join(context_lines)
    
    def get_need_by_name(self, name: str) -> Optional[LangpifyNeed]:
        """
        Get a specific need by name.
        
        Args:
            name: Name of the need to retrieve
            
        Returns:
            The need if found, None otherwise
        """
        return self.needs.get(name)

    @abstractmethod
    def communicate(self, prompt: str) -> str:
        """
        Check if the database connection is established.

        Returns:
            bool: True if connected, False otherwise.
        """
        pass

    # Este método esta orientado para comunicación sincronica, a diferencia de nuestro sistema de eventos orientado a asincronismo y streaming
    # Ver patrones de comunicación de ACP

    def register(self) -> A2AServer:
        """
        Crea y retorna una instancia de A2AServer basada en este agente.

        Este método implementa la integración con el protocolo A2A (Agent-to-Agent),
        permitiendo que el agente sea accesible a través de una API REST compatible
        con el estándar A2A.

        Returns:
            A2AServer: Una instancia de servidor A2A configurada con este agente.
        """

        # Clase A2A que envuelve al agente actual
        class LangpifyA2AServer(A2AServer):
            def __init__(self, langpify_agent: LangpifyBaseAgent):
                super().__init__()
                self.langpify_agent = langpify_agent

                # Configurar la tarjeta de agente con los datos del agente Langpify
                self.agent_card = self.langpify_agent.agent_card

            def handle_task(self, task):
                # Extraer el mensaje del task
                message_data = task.message or {}
                content = message_data.get("content", {})
                text = content.get("text", "") if isinstance(content, dict) else ""

                if not text:
                    task.status = TaskStatus(
                        state=TaskState.INPUT_REQUIRED,
                        message={
                            "role": "agent",
                            "content": {
                                "type": "text",
                                "text": "Por favor, envía un mensaje de texto.",
                            },
                        },
                    )
                    return task

                # Usar el método communicate del agente para procesar el mensaje
                response = self.langpify_agent.communicate(text)

                # Crear respuesta
                task.artifacts = [{"parts": [{"type": "text", "text": response}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)

                return task

        # Crear la instancia del servidor A2A
        a2a_server = LangpifyA2AServer(self)

        # No iniciamos el servidor aquí, solo devolvemos la instancia
        # para que el llamador pueda decidir cuándo iniciarlo
        return a2a_server
        # Para más info leer -> https://python-a2a.readthedocs.io/en/latest/quickstart.html#creating-a-simple-a2a-agent

    def suspend(self) -> None:
        """
        Suspende temporalmente el agente, cambiando su estado a SUSPENDED.

        Este método permite pausar la actividad del agente sin eliminarlo.
        Un agente suspendido puede ser reactivado posteriormente.

        De acuerdo con las especificaciones FIPA, un agente suspendido:
        - No procesa nuevos mensajes o tareas
        - Mantiene su estado interno
        - Puede ser reactivado para continuar su funcionamiento

        Returns:
            None
        """
        # Guardar el estado anterior para incluirlo en el evento
        previous_status = self.status

        # Cambiar el estado del agente a suspendido
        self.status = LangpifyStatus.SUSPENDED

        # Emitir un evento de cambio de estado
        self.emit(
            "status_changed",
            {"previous_status": previous_status, "current_status": self.status},
        )

    def resume(self) -> None:
        """
        Reactiva un agente suspendido, cambiando su estado a ACTIVE.

        Este método permite reanudar la actividad de un agente previamente suspendido.
        Solo tiene efecto si el agente estaba en estado SUSPENDED o INITIATED.

        De acuerdo con las especificaciones FIPA, un agente activo:
        - Procesa mensajes y tareas normalmente
        - Participa completamente en el sistema multi-agente
        - Puede interactuar con otros agentes y servicios

        Returns:
            None
        """
        # Solo activamos si el agente está suspendido o recién iniciado
        if self.status not in [LangpifyStatus.SUSPENDED, LangpifyStatus.INITIATED]:
            return

        # Guardar el estado anterior para incluirlo en el evento
        previous_status = self.status

        # Cambiar el estado del agente a activo
        self.status = LangpifyStatus.ACTIVE

        # Emitir un evento de cambio de estado
        self.emit(
            "status_changed",
            {"previous_status": previous_status, "current_status": self.status},
        )
