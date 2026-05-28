# MVP 1: Hungry Agents Office 🏢🧠⚡

**Agentes en una oficina pixelart reciben demandas de un dummy human mientras su drive metabólico (S1 Bunge) regula cuándo, cómo y si actúan.**

## ¿Qué demuestra?

Este demo ilustra el **núcleo regulador endógeno** de Binsai con una visualización viral tipo OfficeClaw/MiroShark:

- **🏢 Entorno MAS**: Oficina con escritorios, plantas, iluminación
- **🎨 Pixel art**: Agentes 8-bit animados, barras flotantes de drives, speech bubbles
- **🧠 Drive metabólico único**: `δ_metabolic` (S1 Bunge) — tokens, energía, latencia
- **👤 Dummy human**: Emite prompts aleatorios (quick / normal / heavy) con distinto costo metabólico
- **😴 FIPA lifecycle**: Estados `initiated → active → suspended` con sleep/consolidación
- **📊 Fuzzy sigmoid**: Todas las decisiones usan umbrales difusos (no if/else duros)
- **📊 Visualización en tiempo real**: Los drives decaen y afectan el comportamiento visible

## Arquitectura

```
┌─────────────────────────────────────────────┐
│         OfficeEnvironment (MAS)              │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │  Desk   │    │  Desk   │    │  Desk   │  │
│  │ Ana (11)│    │Bruno (8)│    │Olivia(12)│  │
│  │ δM:0.3  │    │ δM:0.5  │    │ δM:0.4  │  │
│  │ status:A│    │ status:A│    │ status:S│  │
│  └─────────┘    └─────────┘    └─────────┘  │
│         ↑                                    │
│    [Dummy Human]                             │
│    "Resumí la situación" (normal)             │
│         ↓                                    │
│    ¿act_fast? ¿act_slow? ¿defer? ¿sleep?     │
└─────────────────────────────────────────────┘

S = suspended (sleep/consolidación)
A = active
```

## Ciclo de vida (FIPA-like)

```
initiated ──activate()──→ active ──suspend()──→ suspended
                                              │
                                              │ consolidate()
                                              │ (trim working memory)
                                              │
                                              └──resume()──→ active
```

En **suspended**: el agente no recibe prompts, no consume tokens, y recupera `δ_metabolic` pasivamente mientras consolida memoria.

## Dummy Human: perturbación externa

Un agente "dummy human" emite prompts cada heartbeat con probabilidad configurable:

| Tipo | Prompt ejemplo | Costo metabólico |
|------|---------------|------------------|
| **quick** | "Dame un sí o no." | 0.02 |
| **normal** | "Resumí la situación en una frase." | 0.05 |
| **heavy** | "Desarrollá un argumento completo a favor o en contra." | 0.10 |

El dummy human **elige agente al azar** (no conoce drives internos).

## Decisiones fuzzy del agente

Dado un prompt con costo `c`, el agente selecciona acción por sigmoides:

- **`act_fast`**: Usa modelo rápido/cheap (responde con pocos tokens)
- **`act_slow`**: Usa modelo lento/costoso (responde con más tokens)
- **`defer`**: No responde ahora (preserva `δ_metabolic`)
- **`sleep`**: Se suspende para consolidar memoria y recuperar recursos

La probabilidad de cada acción depende de `δ_metabolic` y del costo del prompt — no hay umbrales duros.

## Presión regulatoria (Driveplexity A2)

Per el paper Driveplexity:

```
D(δ) = (δ · σ(k·δ))²
```

donde `δ = set_point - value`. Cuando `value < set_point` (déficit), la presión crece cuadráticamente. Cuando `value > set_point` (superávit), la presición cae a cero suavemente via sigmoide.

## Ejecución

### Browser (Phaser 3)
```bash
$env:PYTHONPATH = "src"; python -m binsai.simulation.runner --mode web --port 8080
```
Abrir: `http://127.0.0.1:8080`

### CLI (validación científica)
```bash
$env:PYTHONPATH = "src"; python -m binsai.simulation.runner --mode cli --steps 1200
```

## Controles (GUI)

| Tecla | Acción |
|-------|--------|
| `ESPACIO` | Pausar/continuar |
| `Q` | Salir |

## Módulo de Simulación

```python
from binsai.simulation import SimulationEngine, ScenarioConfig, AgentSpec

cfg = ScenarioConfig(
    mode="web",
    topic="Can AI be functionally conscious?",
    heartbeat_interval=40,
    agent_specs=[
        AgentSpec("Ana", "developer", 11),
        AgentSpec("Bruno", "analyst", 8),
        AgentSpec("Olivia", "researcher", 12),
        AgentSpec("Nico", "designer", 14),
    ],
)
engine = SimulationEngine(cfg)
engine.run()
```

## Comunicación con LLM (DeepSeek)

- El agente recibe prompt del dummy human
- Decide acción fuzzy basada en `δ_metabolic`
- Llama al LLM (fast o slow según decisión)
- Evento `token_consumed` depleta `δ_metabolic`
- Trazabilidad completa en panel: tokens, costo, presión, cambio de drive

```bash
$env:DEEPSEEK_API_KEY = "tu_key"
$env:PYTHONPATH = "src"; python -m binsai.simulation.runner --mode web
```

## Cómo funciona el loop

1. **Decay pasivo**: Cada step, `δ_metabolic` decae (-0.02) — simula costo de estar "despierto"
2. **Prompt externo**: Dummy human emite demanda cada heartbeat
3. **Selección de target**: Uniformemente al azar entre agentes activos
4. **Decisión fuzzy**: `σ(δ_metabolic)` determina probabilidad de cada acción
5. **Ejecución**: Si actúa → LLM call → depleción proporcional a tokens
6. **Sleep**: Si `δ_metabolic` es crítico → `suspend()` → no recibe prompts, no decae, recupera +0.10/heartbeat
7. **Consolidación**: Durante sleep, trim de working memory (Miller 7→3 items) con costo -0.01
8. **Resume**: `σ(δ_metabolic - set_point + 0.10)` determina probabilidad de despertar

## Herencia de AopifyJS (2019)

Del [roadmap de AopifyJS](https://github.com/codewithpatelo/aopifyjs):
> "Homeoestatic Motives system"
> "Agent Entities"
> "Emotional Valence system"

Binsai MVP 1 implementa exactamente esto, 6 años después:
- ✅ Sistema de motivos homeostáticos (Bunge S1: `δ_metabolic`)
- ✅ Agent Entities con visualización pixelart
- ✅ FIPA lifecycle (initiated/active/suspended)
- ✅ Regulación fuzzy por sigmoides (no if/else duros)
- ✅ **Nuevo**: Dummy human como fuente de perturbación externa
- ✅ **Nuevo**: Sleep/consolidación con recuperación pasiva

## Inspiraciones Visuales

- **OfficeClaw / Athenas IT**: Oficinas pixel art con múltiples agentes
- **MiroShark**: Visualizaciones de agentes virales
- **NetLogo**: Simulación MAS clásica, modernizada con pixel art

## Referencias

- Bunge, M. (1979). *Ontology II: A World of Systems*
- Bunge, M. & Romero, G. (2014). *Entropy and the ontology of\natural processes*
- Pro-Action Γ (in preparation): Multi-subsystem regulatory operator
- Driveplexity (JAIIO 2025, under review): Endogenous activation in multi-agent LLM debate
- Miller, G.A. (1956). *The magical number seven, plus or minus two*
