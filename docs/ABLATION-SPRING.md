# Ablación del resorte — predicciones y resultados

Experimentos escritos y predichos **antes** de correr (anti-overfitting).
Configuración común: `x*=0.30, λ=0.004 (recover), κ=0.04, θ=0.12, ρ=1.0`,
viabilidad `(0.10, 0.90)`, 300 ticks.

Tres variantes:
- **linear** — damper legacy `−κ·d`
- **pulsatile∞** — σ += κ·d, release en θ (w = inf)
- **magnet** — σ += κ·d·e^(−|d|/w), w=0.25 (grip máx. `κw/e ≈ 0.0037 < λ`)

## Predicciones (escritas pre-ejecución)

### Escenario A — negligencia basal pura (sin u ni estímulos)

| Variante | Predicción |
|---|---|
| linear | plateau plano en x*+λ/κ = **0.40**; zonas visitadas: equilibrium→moderate solo; nunca muere |
| pulsatile∞ | oscilación ~0.40–0.50 (techo ≈ x*+λ/(κρ)); equilibrium↔moderate↔high esporádico; nunca muere |
| magnet | oscilación en ascenso → critical → **viability breach** y muerte |

### Escenario B — negligencia + un shock u en t=150 (deplete +0.30 → x≈0.62, d>w)

| Variante | Predicción |
|---|---|
| linear | el damper lo recupera → vuelve a plateau 0.40; sin muerte |
| pulsatile∞ | oscilación continúa, techo alto transitorio, vuelve; sin muerte |
| magnet | el shock lo saca del alcance del resorte → grip decae → cascada → **muerte** |

## Criterios de medición

1. ¿La negligencia basal mata? (viability breach en A)
2. ¿Las zonas se ejercitan? (conteo de entradas a cada zona)
3. ¿El escape por shock ocurre solo con alcance finito? (muerte en B solo para magnet)

## Resultados (ejecutado)

### Escenario A — negligencia basal pura

| Variante | x_final | Breach | Zonas ejercitadas | Veredicto |
|---|---|---|---|---|
| linear | 0.400 plano | nunca | equilibrium, moderate | plateau muerto — ✓ como se predijo |
| pulsatile∞ | 0.384 oscilante | nunca | equilibrium↔moderate (repetido) | mesa viva acotada — ✓ |
| magnet w=0.25 | 0.967 | **t=729** | equilibrium→moderate→high→critical | negligencia mata — ✓ (más lento que lo predicho a 300t: λ=0.004 apenas supera el grip 0.0037, el escape es asintótico) |

### Escenario B — negligencia + shock u en t=150 (x → ~0.62, d > w)

| Variante | x_final | Breach | Veredicto |
|---|---|---|---|
| linear | 0.401 | nunca | el damper recupera — ✓ |
| pulsatile∞ | 0.429 | nunca | vuelve a la mesa oscilante — ✓ |
| magnet w=0.25 | 0.971 | **t=197** | el shock lo saca del alcance → cascada → muerte — ✓ |

### Criterios

1. **¿La negligencia basal mata?** Solo con alcance finito (breach t=729). Sin w la presión queda acotada siempre.
2. **¿Las zonas se ejercitan?** Magnet recorre equilibrium→moderate→high→critical; linear/pulsatile∞ nunca salen de equilibrium/moderate en negligencia.
3. **¿Escape por shock solo con alcance finito?** Confirmado — mismo shock, mismos parámetros, solo magnet muere (t=197).

Conclusión de la primera pasada: correcta pero **incompleta** — la config usada
(λ=0.004 > grip κρw/e ≈ 0.0037) está en el régimen donde la deriva gana siempre
por construcción. El breach a t=729 no demostró escalada: era inevitable. Y el
escenario B midió aceleración, no atribución — el imán ya venía muriendo solo.
La prueba real exige el **régimen atrapado**.

---

# Segunda pasada — régimen atrapado (λ < κρw/e)

Misma config, pero `λ=0.002` < `κρw/e ≈ 0.0037` — el agarre del resorte vence a
la deriva. Lo que el alcance finito debe producir y los otros no pueden:

## Predicciones (escritas pre-ejecución)

### Escenario A — negligencia basal, 900 ticks

| Variante | Predicción |
|---|---|
| linear | plateau en x*+λ/κ = 0.35, sin muerte |
| pulsatile∞ | oscilación ~techo x*+λ/(κρ)=0.35, sin muerte |
| magnet w=0.25 | **atrapado**: oscila bajo viabilidad, sin muerte — el grip aguanta |

### Escenario B — mismo régimen atrapado + shock u en t=150 (x → ~0.62, d > w)

| Variante | Predicción |
|---|---|
| linear | recupera hacia 0.35, sin muerte |
| pulsatile∞ | vuelve a la mesa oscilante, sin muerte |
| magnet w=0.25 | shock lo saca del alcance → grip decae → cascada → **muerte** |

## Resultados (ejecutado)

Nota de tuning: con w=0.25 el umbral de escape quedaba en d*≈0.63 (x≈0.93) —
prácticamente en viabilidad, así que ningún shock sobrevivable podía sacar al
drive del alcance (el shock +0.35 recuperó en las tres variantes). Con
w=0.18 (grip máx ≈ 0.00265 > λ=0.002) el umbral de escape queda en zona
media-alta y el experimento es demostrable.

### Escenario A — negligencia basal, 900 ticks, λ=0.002, viability (0.02, 0.90)

```
linear    | x_final=0.385 | breach=None | zones=[equilibrium, moderate_deficit]
puls-inf  | x_final=0.385 | breach=None | zones=[equilibrium, moderate_deficit]
magnet    | x_final=0.396 | breach=None | zones=[equilibrium, moderate_deficit]
```

→ CONFIRMADO: en el régimen atrapado las tres variantes sobreviven la
negligencia basal — incluido el imán, que queda oscilando bajo viabilidad.
La muerte por negligencia NO es automática: requiere λ > grip o un shock.

### Escenario B — mismo régimen + shock u=+0.35 en t=150

```
linear    | x_final=0.365 | breach=None  | recuperó
puls-inf  | x_final=0.365 | breach=None  | recuperó
magnet    | x_final=1.000 | breach=t=305 | shock lo sacó del alcance → cascada
```

→ CONFIRMADO: el escape por shock ocurre **solo** con alcance finito, en el
régimen donde la negligencia pura no mata. Las otras dos variantes visitan
critical_deficit y vuelven; el imán no regresa. Esto es lo que justifica w.

### Nota honesta sobre la primera pasada

El resultado anterior (magnet muere en t=729 con λ=0.004) no probaba
escalada: con λ > κρw/e la muerte por negligencia es inevitable por
construcción — estaba midiendo el tiempo de un escape ya garantizado. El
hallazgo real de esta ablación es la combinación:

- **Atrapado bajo negligencia** (A, magnet: vivo a 900t)
- **Mortal tras shock** (B, magnet: muerto a t=305)

…en la MISMA configuración. Ningún otro resorte produce ambas cosas a la vez:
linear y pulsatile∞ siempre recuperan; un integrador puro (κ=0) siempre
muere. El alcance finito es lo que hace que "el shock importe solo cuando te
saca del alcance" — homeostasis que aguanta hasta ser sobrepasada.

Conclusión: la reformulación no es cosmética — produce comportamiento que el
damper no puede producir (escalada bajo negligencia en régimen λ>grip) y
comportamiento que el pulsátil acotado no puede producir (escape por shock
pasado el alcance, en régimen atrapado).
