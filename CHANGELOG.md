# Changelog

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
