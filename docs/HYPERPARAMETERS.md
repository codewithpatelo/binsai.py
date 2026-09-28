# Censo de hiperparámetros — EPA v2

De `docs/paov2.tex` §Censo. Cada parámetro tiene procedencia: contrato,
derivado, medible, operativo, o libre por necesidad.

| Macro | Subparámetros | Procedencia |
|---|---|---|
| Punto de equilibrio | `x*` (`set_point`), `L⁻`, `L⁺` (`viability`) | contrato de viabilidad |
| Deriva basal | `λ⁰` (`lambda_rate`), dirección `σ` (`basal_direction`), forma `φ` (`drift_shape`, `drift_gamma`, `drift_s`) | contrato; la dirección por el tipo de necesidad |
| Resorte magnético | `κ` (`kappa`), `w` (`spring_reach`), `f` (`spring_fatigue`), `c` (`damping`) | `w` derivado por la regla `w = d*/ln(κ_ef·d*/λ⁰)`; `κ` por el régimen buscado; `f` por el tiempo de muerte por negligencia; `c` por defecto nulo |
| Estado alostático | `Λ`, `ρ_Λ` (`allostatic_recovery`) | `Λ` es estado, no parámetro; `ρ_Λ` por el dominio (cuánto descanso repara) |
| Estímulos | `α_is` (`sustain`), `Δ_i` (`impulse`), `g_i` | medibles por acción |
| Acoplamiento | `W` (`Drives.couple`) | medible |
| Zonas algedónicas | `θ_z`, histéresis (`alpha_in`, `alpha_out`), ancho `ω_z` | contrato; la histéresis por la granularidad de acción |
| Presión autónoma | `η` (`eta`), `v_ref` | operativo — cuánto pesa la velocidad en la presión |
| Pulso | `Δt` (`dt`) | operativo |
| Activación | `h` (`activation_h_pressure`, `h_demand`, `h_backlog`), refractario (`activation_refractory`) | tasa por unidad de tiempo — `1/h` = espera media a actuar; pregunta de dominio, no probabilidad por tick (docs/ACTIVATION.md) |

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
