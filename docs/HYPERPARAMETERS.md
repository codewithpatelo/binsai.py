# Censo de hiperparámetros — EPA v2.1

De `docs/paov2.1.md` §11 (delta sobre v2) + `docs/paov2.tex` §Censo. Cada
parámetro tiene procedencia: contrato, derivado, medible, operativo, o
libre por necesidad.

## Delta v2.1 — nuevos

| Símbolo | Campo | Significado | Valor inicial |
|---|---|---|---|
| `ι₁`, `ι₂`, `ι₃` | `impulse_iota` | magnitud del impulso por severidad de cruce (verde→amarillo, amarillo→ámbar, ámbar→rojo) | 0.02 / 0.06 / 0.18 |
| `ζ` | `impulse_zeta` | asimetría mejora vs empeoramiento | 0.6 |
| `τ_u` | `impulse_tau` | ancho del núcleo de decaimiento `ψ(s)=e^(−s/τ_u)`, en ticks | 2 |
| `g_ok` | `agent.g_ok` | umbral de efecto logrado (`g ≥ g_ok` → saciación sobre lo medido) | 0.5 |
| `g_nulo` | `agent.g_nulo` | umbral de efecto nulo (`|g| < g_nulo` → ι₂, activación no consumida) | 0.15 |
| `θ` | `activation_theta` | fracción del TTD admisible como espera esperada: `1/h ≤ θ·TTD` | 0.2 |
| `β` | `activation_beta` | fracción del TTD para el refractario: `ref = β·TTD` (clampado) | 0.1 |
| `h_max` | `activation_h_max` | techo de la tasa. Debe quedar por encima de `1/(θ·TTD_mín)` para que el anclaje θ actúe — la noche del 09 tenía `h_max=12/h` y no podía despertar antes de 5 min | 60 |

El horizonte del TTD es la **ventana restante** (`agent.window_ticks`), una
cantidad operativa, no un hiperparámetro: si ninguna pared se cruza antes
de que la ventana cierre, `TTD = ∞` para esta ventana (§4).

## Delta v2.1 — eliminados o degradados

- **Refractario fijo** — ahora `min(ref_max, max(ref_min, β·TTD))`; con
  `TTD=∞` queda en el máximo (`activation_refractory`).
- **`h₀`, `γ`** (forma exponencial del harness de la noche del 09) — no
  existen en Binsai; la composición lineal `h_pressure·p + h_demand·𝟙 +
  h_backlog·backlog` pasa a ser el **piso de exploración**: cuando
  `TTD=∞`, el anclaje `h_requerida` no actúa y manda la composición base.
- **Tabla zona → tasa**: eliminada. El rojo sube `h` vía presión/TTD, no
  fuerza el disparo.
- **Fuente sin calibrar como 0**: eliminada. Queda fuera del máximo y se
  registra (`pressure_components()["uncalibrated"]`).

Todos los valores iniciales son provisionales y van en el contrato de
viabilidad, no en el código (paov2.1 §11).

---

## Censo v2

| Macro | Subparámetros | Procedencia |
|---|---|---|
| Punto de equilibrio | `x*` (`set_point`), `L⁻`, `L⁺` (`viability`) | contrato de viabilidad |
| Deriva basal | `λ⁰` (`lambda_rate`), dirección `σ` (`basal_direction`), forma `φ` (`drift_shape`, `drift_gamma`, `drift_s`) | contrato; la dirección por el tipo de necesidad |
| Resorte magnético | `κ` (`kappa`), `w` (`spring_reach`), `f` (`spring_fatigue`), `c` (`damping`) | `w` derivado por la regla `w = d*/ln(κ_ef·d*/λ⁰)`; `κ` por el régimen buscado; `f` por el tiempo de muerte por negligencia; `c` por defecto nulo |
| Estado alostático | `Λ`, `ρ_Λ` (`allostatic_recovery`) | `Λ` es estado, no parámetro; `ρ_Λ` por el dominio (cuánto descanso repara) |
| Estímulos | `α_is` (`sustain`), `Δ_i` (`impulse`), `g_i` | medibles por acción |
| Acoplamiento | `W` (`Drives.couple`) | medible |
| Zonas algedónicas | `θ_z`, histéresis (`alpha_in`, `alpha_out`), ancho `ω_z` | contrato; la histéresis por la granularidad de acción |
| Presión | `level = min(1, \|d\|/\|L−x*\|)`, `pace` (variables observadas), `autonomous = min(1, η·\|v\|/v_ref)` | todas las fuentes en `[0,1]`; `η`/`v_ref` operativos; agregación conjuntiva entre drives (`Drives.pressure = max`) |
| Pulso | `Δt` (`dt`) | operativo |
| Activación | `h` (`activation_h_pressure`, `h_demand`, `h_backlog`), anclaje `θ·TTD` (`activation_theta`, horizonte = ventana restante), refractario `β·TTD` (`activation_beta`, `activation_refractory_min`/`activation_refractory`) | tasa por unidad de tiempo — `1/h` = espera media a actuar; anclada al horizonte que queda, no elegida a mano (docs/paov2.1.md §5, docs/ACTIVATION.md) |

## Libres por necesidad: `λ⁰`, `κ`, `f`

Las tres responden a una pregunta del dominio:

- **`λ⁰`** — cuánto se degrada la necesidad por unidad de tiempo sin
  estímulo. Es la deriva basal: el hecho de que desatender tiene costo.
- **`κ`** — qué régimen de regulación se busca. Con `w` derivado, `κ` fija
  el agarre máximo `G = κw/e` y por tanto si existe régimen estable
  (`G > λ⁰`) o si la negligencia mata siempre (`G < λ⁰`).
- **`f`** — en cuánto tiempo la negligencia debe resultar fatal. Sin
  fatiga (`f=0`), un sistema dentro del régimen estable oscila acotado
  para siempre cerca del equilibrio; `f>0` hace que la exposición sostenida
  desgaste el agarre hasta el escape.

## Derivados (no son perillas)

- **`w`** (`spring_reach`) — se deriva del contrato con la regla de diseño
  `w = d*/ln(κ_ef·d*/λ⁰)` (`Drive.design_spring_reach`), eligiendo el punto
  de no retorno `d*` dentro del margen viable. No se elige a ojo: la
  validación en construcción advierte si `d*` cae fuera de `(L⁻, L⁺)`.
- **`d*`** — punto de no retorno: `d* = −w·W₋₁(−λ⁰/(κ_ef·w))`
  (`Drive.no_return_point()`). Frontera entre "el resorte alcanza" y
  "la deriva gana".

## Removidos en EPA v2

- **`θ` (`spring_threshold`), `ρ` (`spring_release`)** — eran los dos
  parámetros sin procedencia del resorte pulsátil. En segundo orden no hay
  liberación: la velocidad acumula el rol de σ. Siguen existiendo solo en
  `spring="pulsatile"` (legacy, para ablación).
