# Changelog

## EPA v2.1 (unreleased)

### Delta sobre v2 — spec completa en `docs/paov2.1.md`

**Framing (rev 2026-10-10): EPA v2 nunca corrió.** El proceso de la noche
del 09 integró ley de Hooke con pared en ±1 (primer orden, resorte lineal,
clipping) — firma vieja de `integrateProaction`, el módulo v2 no cargaba.
v2.1 es el conjunto de correcciones que entran antes de que v2 corra por
primera vez: no hay evidencia contra v2, hay ausencia de la prueba. (La
aceptación §12.1 "v2 carga" vive en el harness TS, no en Binsai.)

- **§1 — La perturbación es un impulso de evento, no una inclinación de λ.**
  Las variables observadas publican `Perturbed` al cruzar una frontera de
  zona (familias level y pace); los drives suscriptos reciben el impulso
  `ι·ψ(t−t_k)` con `ψ(s)=e^(−s/τ_u)` sobre el canal de aceleración `u`.
  Magnitudes por severidad `ι₁/ι₂/ι₃` (0.02/0.06/0.18), asimetría `ζ=0.6`.
  `Drive.apply_impulse`, `Drive.impulses`.
- **§2 — Presión normalizada, fuentes que participan, agregación
  conjuntiva.** Toda fuente en `[0,1]`; la presión por drive es el máximo
  sobre sus fuentes CALIBRADAS — no la distancia sola (la noche del 09 las
  calculaba para el reporte y el agregador de despertar no las leía). Una
  fuente sin calibrar queda fuera del máximo y se registra — nunca vale 0.
  `Drives.pressure` = max (intersección de contratos). Saturación en el
  límite: presión 1, `DriveSaturated`, `saturation_time` acumulado.
- **§2.5 — Persistencia declarada por drive.** `persist_state` +
  `state_origin`: nada se hereda implícitamente y nada se reinicia
  implícitamente. Un drive persistido DEBE llegar con su estado heredado
  y decir de cuándo viene (error si no); el resto arranca en `x(t₀)=x*`.
- **§3 — `g` se mide.** `ExpectedEffect {driveId, Δ_exp, byWhen}` declarado
  ANTES de ejecutar; `g = Δ_obs/Δ_exp` acotado [−1,2] en `byWhen`.
  `g ≥ g_ok`: saciación sobre el efecto MEDIDO; `|g| < g_nulo`: impulso ι₂,
  activación NO consumida, `ActivationFailed`; `g < 0`: impulso ι₃,
  `harmful`, inhabilitada para la misma falla en la ventana.
  `agent.attempts` como libro de intentos.
- **§4 — TTD.** Proyección lineal sobre los últimos `N` ticks del log:
  `Drive.time_to_death()`, `Drives.time_to_death()` = min.
- **§5 — La tasa respeta el horizonte.** `E[espera] = 1/h ≤ θ·TTD` →
  `h = min(h_max, max(h_base, 1/(θ·TTD)))`; refractario
  `min(ref_max, max(ref_min, β·TTD))`. `h_max` default 60/h.
- **§7 — Guardas.** `binsai.guards`: señal ausente ≠ desacuerdo
  (`GuardSignalUncalibrated` — `guard.signal_uncalibrated` en la spec —,
  nunca bloquea); rechazo real con señales vivas sí bloquea y traza
  `GuardRejected`/`ActionRejected` (la noche del 09 fue un desacuerdo real:
  lo que falló fue §7.2, no §7.1). `ActionSpec.risk` correctiva/destructiva.
  **Contrato sobrevive a la compactación**: `binsai.contract.ViabilityContract`
  (bloque verbatim + hash + `agent.verify_contract_block` con
  `ContractVerified`/`ContractReinjected`).
- **§8 — Trazas que no mienten.** `ActivationDraw` registra presión por
  drive y fuente, **drive y fuente dominantes**, TTD, h, `Δt`, `p_tick`, el
  número sorteado y el resultado — cada campo se recomputa a mano desde el
  contrato (el log de la noche del 09 guardaba un delta de pacing bajo el
  nombre `probability`). `ExpectedEffect`/`GMeasured`/`ActivationFailed`
  completan la cadena causal reconstruible sin prosa.
- **§12 — Aceptación.** 23 tests en `tests/test_epa_v2_1.py`; la prueba
  "v2 carga" corresponde al harness TS (multiply-overnight).

### CORTE DE COMPARABILIDAD

El desvío ya no entra en la presión como `autonomous` (ahora es
velocidad-only) y la presión por drive es el máximo sobre fuentes
calibradas: las series de presión de v2 no son comparables punto a punto
con las de v2.1. El estado inicial de un drive solo se hereda si el
contrato lo declara (`persist_state`).

## EPA v2 (unreleased)

### CORTE DE COMPARABILIDAD — dinámica de segundo orden

**El estado de cada drive pasó de `x` a `(x, v)` y el resorte cambió de
pulsátil a magnético fatigable.** Formalización canónica: `docs/paov2.tex`.

- `spring="magnetic-2nd"` es el nuevo default:
  `v += a·Δt`, `x += v·Δt`, con `a = λ − S − c·v + u + ΣW·(x_j − x*_j)` y
  `S = κ_ef·d·e^(−|d|/w)`, `κ_ef = κ·e^(−f·Λ)`, `Λ' = |d| − ρ_Λ·Λ`.
- **Desaparecen θ y ρ** (`spring_threshold`, `spring_release`) — eran los
  dos parámetros sin procedencia. `spring="pulsatile"` y `spring="linear"`
  quedan como legacy para ablación controlada.
- Nuevos campos: `velocity`, `dt`, `damping` (c), `spring_fatigue` (f),
  `allostatic_recovery` (ρ_Λ), `eta`, `v_ref`, `drift_shape` (φ),
  `drift_gamma`, `drift_s`.
- Dos canales de estímulo: `sustain(name, α)` entra en la aceleración;
  `impulse(Δ, expected)` salta el nivel y devuelve `g = Δ_obs/Δ_exp`.
- `pressure_components()` ahora incluye `autonomous = |d|/|L−x*| +
  η·|v|/v_ref` — la velocidad ocupa el lugar que tenía σ (legacy arms
  siguen exponiendo `tension`).
- Validación en construcción: `no_return_point()` (Lambert W₋₁),
  `design_spring_reach(κ, λ⁰, d*)`, y warnings explícitos si d* cae fuera
  del margen viable o si la deriva domina (G ≤ λ⁰).

**Todo resultado con dinámica de primer orden (pulsátil o linear,
commits ≤ c37ec8f incluidos) NO es comparable punto a punto con EPA v2**:
el estado cambió de `x` a `(x,v)`, desaparecieron θ y ρ, y la presión
autónoma cambió de tensión a velocidad. La ablación v2 está en
`docs/ABLATION-EPA-V2.md` con predicciones escritas antes de la corrida y
paridad de condiciones iniciales verificada en tests.

### Activación por tasa de riesgo (docs/ACTIVATION.md)

- La decisión de actuar era `1 − p(idle)` por tick — una probabilidad por
  pulso es un hiperparámetro oculto ligado a Δt. Ahora es un proceso de
  Poisson: `p_tick = 1 − e^(−h·Δt)` (`fuzzy.activation_hazard`,
  `activation_probability`). `h` es por unidad de tiempo — `1/h` = espera
  media a actuar, pregunta de dominio.
- `h = h_pressure·p + h_demand·𝟙{demanda} + h_backlog·backlog` — se alimenta
  de `drive.pressure`. Params del agente: `activation_h_pressure`,
  `activation_h_demand`, `activation_h_backlog`, `activation_refractory`.
- **Período refractario** tras cada acción completada y **compromiso**
  mientras ejecuta (ACTIVE no re-sortea — ya estaba, queda declarado).
- Una vez que el gate dispara, el softmax elige *qué* acción con `idle`
  fuera del conjunto — el gate posee el si/no, el softmax el cuál.
- **Bug corregido**: `drive.pressure` solo reflejaba variables observadas —
  la fuente autónoma nunca entraba, y sin sensores quedaba `None`. Ahora
  `update()` pliega `max(nivel, ritmo, autónoma)` siempre.
- Cambio de comportamiento medible: la frecuencia de acciones por tick baja
  en régimen calmo (antes el softmax decidía aún sin presión). Misma forma
  de ruptura que el resto de v2 — las comparaciones de KPIs entre versiones
  deben notarlo.
- Direcciones documentadas (no implementadas): aprendizaje de `g` por
  promedio móvil con antecedente en Keramati & Gutkin, y mutación bajo
  estrés prolongado (ultraestabilidad de Ashby) — `docs/DIRECTIONS.md`.

## 0.3.0 (unreleased on PyPI)

### CORTE DE COMPARABILIDAD — convención de signo invertida

**`x` pasó de "magnitud del déficit" a "nivel de satisfacción".**

- x bajo = déficit, x alto = superávit/holgura (antes era al revés).
- `satiate()` ahora **sube** x; `deplete()` lo **baja**.
- Zonas default espejadas: `critical_deficit` en x≈0.20,
  `critical_superavit` en x≈0.95.
- Presets: `metabolic` es pull/`recover` (λ>0 — los recursos se reponen en
  reposo, el trabajo los drena); los push son `decay` (λ<0 — la satisfacción
  decae bajo negligencia basal).
- Routing, sleep, fuzzificación (D(x)=x*−x), prompts y notebooks migrados.
- Zonas custom siguen soportando cualquier convención — los defaults son la
  convención canónica, no la única posible.

**Todo experimento corrido antes del flip (commits ≤ d755aed) usa la
convención de déficit y NO es comparable punto a punto con resultados
posteriores.** La ablación de resortes (`docs/ABLATION-SPRING.md`) se corrió
pre-flip: sus trayectorias y tiempos de breach se leen en la convención vieja;
las conclusiones cualitativas (régimen atrapado, escape por shock, umbral de
w) son invariantes bajo el espejo x → 1−x.

### Added

- `spring="pulsatile"` (default): tensión σ carga con `κ·d·e^(−|d|/w)` y
  descarga `ρ·σ` al cruzar θ. Params: `spring_threshold`, `spring_release`,
  `spring_reach` (w). `spring="linear"` queda como damper legacy.
- Evento `TensionReleased`; `drive.tension` público;
  `drive.pressure_components()` → `{level, pace, tension}`.
- `basal_direction="recover"|"decay"` fija el signo de λ semánticamente.
- w documentado como regla de diseño derivable: `w = d*/ln(ρκd*/|λ|)`
  (ver `docs/SPRING.md`).

### Fixed

- `drift="circadian"` ignoraba `drift_period` (hardcodeaba 120).
