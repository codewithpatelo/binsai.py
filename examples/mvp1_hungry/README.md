<p align="center">
  <a href="#english">English</a> · <a href="#español">Español</a>
</p>

---

<a id="english"></a>

## MVP1: Hungry Agents

A deterministic simulation of 3 agents (Alpha, Beta, Gamma) whose behavior is regulated by a single metabolic drive `δ_metabolic` (Bunge S1).

### What it demonstrates

- **One active drive**: `metabolic` — regulates when the agent acts fast, slow, defers, or sleeps
- **FIPA lifecycle**: `INITIATED → ACTIVE → SUSPENDED → ACTIVE` with causal transitions
- **Sleep/consolidation**: Agent suspends when deficit exceeds threshold; wakes when recovered AND queue is empty
- **Dummy human**: Random demands of varying metabolic cost
- **Ablation comparison**: Gamma starts unregulated to show the difference

### What it does NOT demonstrate

- The other 9 canonical drives do not affect behavior
- No pixel-art office or Phaser 3 visualization (MVP1 is headless/CLI)
- No episodic/semantic memory (only bounded working memory)
- No real LLM calls by default (`dry_run_llm=True`)

### Run

```bash
# Deterministic headless simulation (default)
binsai run mvp1 --seed 42 --speed 1.0 --no-browser

# With real LLM (requires DEEPSEEK_API_KEY)
export DEEPSEEK_API_KEY="your_key"
binsai run mvp1 --seed 42 --no-llm  # remove --no-llm to enable LLM
```

Or programmatically:

```python
from binsai import World, WorldConfig

config = WorldConfig(seed=42, dry_run_llm=True)
world = World(config)

for tick in range(100):
    frame = world.step()
    for a in frame.agents:
        print(f"tick={tick}  {a.name}: δ={a.delta:.2f}, zone={a.zone}, action={a.action}")
```

### Architecture

```
┌─────────────────────────────────────────────┐
│              World (deterministic)           │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ Alpha   │    │ Beta    │    │ Gamma   │  │
│  │ δM:0.3  │    │ δM:0.5  │    │ δM:0.4  │  │
│  │ status:A│    │ status:A│    │ status:S│  │
│  └─────────┘    └─────────┘    └─────────┘  │
│         ↑                                    │
│    [Dummy Human]                             │
│    random demands (quick/normal/heavy)       │
└─────────────────────────────────────────────┘
```

### How the loop works

1. **Passive decay**: Each tick, `δ_metabolic` drifts up (basal λ)
2. **External demand**: Dummy human emits a random demand
3. **Fuzzy appraisal**: The agent evaluates which action to take based on drive zone
4. **Execution**: If acting → LLM call (or dry-run) → depletion proportional to tokens
5. **Sleep**: If deficit is critical → `suspend()` → passive recovery + consolidation
6. **Wake**: When recovered AND queue empty → `resume()` → `ACTIVE`

---

<a id="español"></a>

## MVP1: Agentes Hambrientos

Simulación determinista de 3 agentes (Alpha, Beta, Gamma) cuyo comportamiento se regula mediante un único drive metabólico `δ_metabolic` (Bunge S1).

### Qué demuestra

- **Un drive activo**: `metabolic` — regula cuándo el agente actúa rápido, lento, difiere o duerme
- **Ciclo FIPA**: `INITIATED → ACTIVE → SUSPENDED → ACTIVE` con transiciones causales
- **Sueño/consolidación**: El agente se suspende cuando el déficit excede el umbral; despierta cuando se recupera Y la cola está vacía
- **Dummy human**: Demandas aleatorias de distinto costo metabólico
- **Comparación por ablación**: Gamma arranca sin regulación para mostrar la diferencia

### Qué NO demuestra

- Los otros 9 drives canónicos no afectan el comportamiento
- No hay visualización pixel-art ni oficina con Phaser 3 (MVP1 es headless/CLI)
- No hay memoria episódica/semántica (solo memoria de trabajo limitada)
- No hay llamadas reales a LLM por defecto (`dry_run_llm=True`)

### Ejecutar

```bash
# Simulación determinista headless (default)
binsai run mvp1 --seed 42 --speed 1.0 --no-browser

# Con LLM real (requiere DEEPSEEK_API_KEY)
export DEEPSEEK_API_KEY="tu_key"
binsai run mvp1 --seed 42  # sin --no-llm para habilitar LLM
```

O programáticamente:

```python
from binsai import World, WorldConfig

config = WorldConfig(seed=42, dry_run_llm=True)
world = World(config)

for tick in range(100):
    frame = world.step()
    for a in frame.agents:
        print(f"tick={tick}  {a.name}: δ={a.delta:.2f}, zona={a.zone}, acción={a.action}")
```

### Arquitectura

```
┌─────────────────────────────────────────────┐
│              World (determinista)            │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ Alpha   │    │ Beta    │    │ Gamma   │  │
│  │ δM:0.3  │    │ δM:0.5  │    │ δM:0.4  │  │
│  │ estado:A│    │ estado:A│    │ estado:S│  │
│  └─────────┘    └─────────┘    └─────────┘  │
│         ↑                                    │
│    [Dummy Human]                             │
│    demandas aleatorias (rápida/normal/pesada) │
└─────────────────────────────────────────────┘
```

### Cómo funciona el loop

1. **Decaimiento pasivo**: Cada tick, `δ_metabolic` crece (λ basal)
2. **Demanda externa**: Dummy human emite una demanda aleatoria
3. **Appraisal difuso**: El agente evalúa qué acción tomar según la zona del drive
4. **Ejecución**: Si actúa → llamada a LLM (o dry-run) → depleción proporcional a tokens
5. **Sueño**: Si el déficit es crítico → `suspend()` → recuperación pasiva + consolidación
6. **Despertar**: Cuando se recupera Y la cola está vacía → `resume()` → `ACTIVE`

---

## References / Referencias

- Bunge, M. (1979). *Ontology II: A World of Systems*
- Bunge, M. & Romero, G. (2014). *Entropy and the ontology of natural processes*
- Pro-Action Γ (in preparation): Multi-subsystem regulatory operator for LLM agents
- Driveplexity (JAIIO 2025, under review): Endogenous activation in multi-agent LLM debate
