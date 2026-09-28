# Ablación EPA v2 — tres dinámicas × dos escenarios × con/sin fatiga

Referencia canónica: `docs/paov2.tex`. Estado `(x, v)`; aceleración

```
a = λ(x,t) − S(x,t) − c·v + u + Σ_j W_ij·(x_j − x*_j)
S = κ_ef·d·e^(−|d|/w),   κ_ef = κ·e^(−f·Λ),   Λ' = |d| − ρ_Λ·Λ
```

## Configuración (paridad de condición inicial)

Todos los brazos comparten — **solo difiere el resorte** (y `f` en el eje de
fatiga):

| Parámetro | Valor |
|---|---|
| `x₀`, `v₀` | 0.70, 0.0 |
| `x*` | 0.70 |
| viabilidad | (0.10, 0.98) |
| `λ⁰` (decay, signo por `basal_direction`) | 0.001 |
| `κ` | 0.05 |
| `c` (amortiguación, brazos 2º orden) | 0.10 |
| `θ`, `ρ` (legacy pulsátil) | 0.12, 1.0 |
| `w` | derivado por la regla `w = d*/ln(κd*/λ⁰)` con `d* = 0.35` → **w ≈ 0.135** |
| `f` (fatiga) | 0.0 (sin fatiga) / 0.10 (con fatiga) |
| `ρ_Λ` | 0.002 |
| `Δt` | 1.0 |
| shock (escenario B) | impulso `Δx = −0.50` en t = 150 |

El shock (−0.50) supera `d* = 0.35` desde el reposo: aterriza en x ≈ 0.20,
`|d| = 0.50 > d*` — fuera del alcance magnético pero dentro de viabilidad.

**Nota de régimen** (brazo magnético): `G = κw/e ≈ 0.05·0.135/2.718 ≈ 0.0025
> λ⁰ = 0.001` → régimen estable con escape dentro del rango viable.

## Predicciones — escritas antes de correr

### Escenario A — negligencia pura

| Brazo | Predicción |
|---|---|
| **linear** (legacy, `x += −κd + λ`) | Estacionario en `x* + λ/κ = 0.72`? No: decay → `x* − |λ|/κ = 0.68`. Plateau, sin oscilación, **nunca muere**. |
| **pulsatile w=∞** (legacy) | Mesa oscilante en diente de sierra: σ carga hasta θ, descarga ρσ. Acotado, **nunca muere**. |
| **magnetic-2nd, f=0** | Ondas suaves en la dirección basal (no dientes de sierra), amortiguadas hacia el equilibrio cercano `x* − d_eq`. **Sobrevive**: sin fatiga el agarre no se desgasta. |
| **magnetic-2nd, f=0.10** | Oscila igual al inicio, pero Λ acumula por exposición a `|d|`; cuando `κ_ef·w/e < λ⁰` la deriva gana → **muerte por negligencia** (sin shock, sin acción). |

### Escenario B — negligencia + shock −0.50 en t=150

| Brazo | Predicción |
|---|---|
| **linear** | Retorno monótono al mismo plateau 0.68 — el damper no tiene alcance, recupera cualquier desvío. **Sobrevive.** |
| **pulsatile w=∞** | σ carga durante la recuperación, mesa reanuda. **Sobrevive** (alcance infinito = sin escape). |
| **magnetic-2nd, f=0** | El shock deja `|d| = 0.50 > d*`: agarre insuficiente contra λ → deriva gana, cascada a la pared. **Muere.** |
| **magnetic-2nd, f=0.10** | Muere **antes** que en A: el shock suma exposición, Λ ya cargada acelera la fatiga. |

### Lo que la ablación prueba

1. **Las tres muertes son distinguibles**: linear/pulsatile-∞ no mueren nunca
   (ninguna negligencia los mata — el amortiguador descartado); el magnético
   muere por negligencia solo con fatiga, y por shock solo si cruza d*.
2. **f y w no son redundantes**: `w` da escape por distancia (shock), `f` da
   muerte por tiempo (negligencia sostenida). f=0 sin shock sobrevive;
   f>0 sin shock muere.
3. La firma de tiempo de cada dinámica es distinta: plateau (linear), diente
   de sierra (pulsátil), onda amortiguada + escape tardío (magnético).

## Resultados

Corrida con `w = 0.1223` (regla: `d* = 0.35`, `κd*/λ⁰ = 17.5 > e`).
`G = κw/e = 0.0022 > λ⁰ = 0.001` → régimen estable confirmado.

| Brazo | A: negligencia pura | B: + shock −0.50 @ t=150 |
|---|---|---|
| linear (legacy) | sobrevive — plateau | sobrevive — retorna al plateau |
| pulsatile w=∞ (legacy) | sobrevive — mesa de dientes de sierra | sobrevive — mesa reanuda |
| magnetic-2nd f=0 | **sobrevive** — ondas amortiguadas | **muere t=168** (18 ticks post-shock: cruzó d*) |
| magnetic-2nd f=0.10 | **muere t=358** — fatiga alostática | **muere t=163** — más rápido que f=0 |

Todas las predicciones se cumplieron. Las tres muertes quedan
diferenciadas:

- **Muerte por negligencia** solo existe con fatiga (`f>0`): Λ acumula
  exposición a `|d|` y degrada `κ_ef` hasta que la deriva gana el régimen.
  Sin `f`, el magnético f=0 oscila acotado para siempre — como pronosticó
  la formalización.
- **Muerte por shock** solo existe con alcance finito (`w` finito): el
  impulso −0.50 lleva `|d|` a 0.50 > d*=0.35 → escape irreversible incluso
  con `f=0`. El pulsátil `w=∞` nunca escapa — no existe `d*`.
- **El legado no mata**: linear y pulsatile-∞ sobreviven a ambos escenarios.
  La muerte por negligencia — el fenómeno que motiva actuar — requiere el
  resorte fatigable o el alcance finito.

Figura: `fig_ablation_epa_v2.html` (autocontenida, datos embebidos; paneles
de `v(t)` bajo los brazos magnéticos muestran la onda amortiguada que
reemplaza al diente de sierra).
