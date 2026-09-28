# Changelog

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
