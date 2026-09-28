# El resorte elástico — diagnóstico y reformulación pulsátil

Nota de diseño sobre el término del resorte en la ecuación proacción: por qué la
forma lineal original contradice lo que promete, y la reformulación adoptada
(resorte-imán pulsátil).

**Terminología**: *negligencia basal* = el agente no actúa ni recibe estímulos;
la dinámica queda librada únicamente a `λ` + resorte. Es el escenario de
referencia para evaluar si una necesidad acumula presión de verdad: bajo
negligencia basal sostenida, una necesidad push debería escalar hacia las zonas
de déficit y eventualmente amenazar la viabilidad — nunca estacionarse en una
zona segura.

---

## 1. El bug de fondo

La ecuación autónoma actual es:

```
x(t+1) = x(t) + λ − κ·(x(t) − x*)
```

Esto es una **contracción geométrica** (razón `1−κ`). Todo estado inicial converge
al mismo punto fijo:

```
x_rest = x* + λ/κ
```

Con `λ=0.003, κ=0.05, x*=0.30` → `x_rest = 0.36`. Proyección de 400 ticks desde
cualquier valor inicial:

| x inicial | t=50 | t=200 | Resultado |
|---|---|---|---|
| 0.05 (saciación profunda) | 0.336 | 0.360 | plateau |
| 0.445 | 0.366 | 0.360 | plateau |
| 0.80 | 0.394 | 0.360 | plateau |

Es simétrico: con `decay` desde déficit moderado converge a `x*−|λ|/κ = 0.24`.

**Consecuencia**: un drive abandonado nunca genera presión real. Con los defaults
se estanca en déficit leve eterno (0.36, entre equilibrium 0.30 y moderate 0.40).
`ZoneChanged` a critical, `ViabilityBreached`, `interrupt_on_zone` — ninguno puede
dispararse por dinámica autónoma. Toda presión debe venir de `u`, y encima el
resorte erosiona κ cada tick también a `u`.

## 2. Por qué no es un resorte

Un resorte físico es de segundo orden: tiene inercia, oscila, **almacena** tensión.
El término `−κ(x−x*)` es relajación lineal de primer orden: un **amortiguador**
que disipa desviación monótonamente. Además:

- Bajo flujo basal sostenido ni siquiera centra en `x*` — estaciona en `x*+λ/κ`
- Actúa como **threshold duro** sobre la desviación (`λ/κ`), no como resorte
- Disipa tensión en vez de almacenarla — el drive nunca puede "cargarse"

## 3. ¿Puede la deriva ganarle al resorte?

Con drift constante: **nunca dinámicamente**. λ es fijo; el resorte crece con la
desviación — siempre gana a desviación suficiente. Solo por ratio de parámetros:

| λ (κ=0.05) | x_rest | Zona |
|---|---|---|
| 0.003 | 0.36 | equilibrium |
| 0.010 | 0.50 | moderate |
| 0.020 | 0.70 | high |
| 0.030 | 0.90 | critical |
| ≥0.04 | >1.0 | viability breach → muerte |

"Ganar" así significa morir, no acumular presión sostenida. Con `drift` escalado
(`linear`/`exponential`) sí escapa dinámicamente — aparece una segunda raíz
inestable = tipping point — pero es fragil y opaco.

## 4. Reformulación propuesta: resorte pulsátil

El comportamiento buscado: *κ atrae el nivel al set-point sin llegar al punto
perfecto, acumulando tensión y liberando; la deriva predomina pero existe
oscilación (siluetas "S")*.

Eso es un **oscilador de relajación** (integra-y-libera):

```
σ(t+1) = σ(t) + κ·(x(t) − x*)            # el resorte CARGA tensión con el desplazamiento
x(t+1) = x(t) + λ + u + ΣW·φ − r(t)      # la deriva aplica siempre — predomina
r(t)   = ρ·σ(t+1)   si |σ(t+1)| ≥ θ      # LIBERA cuando la tensión cruza el umbral
         0          si no
σ ← σ − r(t)                             # ρ=1 → descarga total; ρ<1 → residual
```

Parámetros:

| Param | Significado |
|---|---|
| `κ` | tasa de carga de tensión — cuánto carga el resorte por tick de desplazamiento |
| `θ` | umbral de liberación — cuánta tensión aguanta antes de descargar |
| `ρ` | fracción de descarga (0<ρ≤1) — 1.0 snap completo, <1 liberación parcial |

### Propiedades

- **Deriva predomina**: λ aplica cada tick sin oposición; el resorte solo muerde
  en pulsos → la presión acumula en la dirección basal
- **Acumula y libera**: `σ` es un registro de tensión (energía potencial), no un
  dissipador
- **Nunca llega al set-point perfecto**: la liberación es pulso finito
- **Simétrico**: `σ<0` en superávit libera hacia arriba
- **Oscilación viva**: el período se acorta lejos de `x*` (carga más rápido) —
  el ritmo de lucha acelera con la desviación
- **Escalación posible**: λ fuerte o κρ débil → escape a viabilidad; balance →
  oscilación sostenida en zona alta (mesa viva, no plateau muerto)
- **Las bandas algedónicas se cruzan arriba y abajo**: `ZoneChanged`, histéresis
  e `interrupt_on_zone` se ejercitan de verdad

### Fundamento formal

El respaldo formal es el **oscilador de relajación / integrate-and-fire** — un
mecanismo estándar, no un aporte propio. Detalle de interés para la línea: es la
misma estructura que el gate del paper de debate, donde la equidad emergía del
reset tras el disparo. Con este cambio, el resorte y el gate son el mismo
mecanismo en dos lugares distintos de la ecuación.

La pulsatilidad hormonal (insulina, GnRH) va como **analogía ilustrativa**, no
como respaldo.

### Procedencia de los parámetros

Tres parámetros libres nuevos permiten producir casi cualquier forma de onda —
riesgo de ajuste cosmético. Lectura de dominio para que dejen de ser perillas:

| Param | Propiedad del dominio | Procedencia |
|---|---|---|
| `w` (spring_reach) | hasta qué desvío la regulación propia alcanza sin ayuda externa (a partir de cierto déficit, compactar o limpiar ya no alcanzan) | medible — *supuesto en defaults actuales* |
| `ρ` (spring_release) | cuánto descarga realmente una acción típica de ese tipo | medible — *supuesto* |
| `θ` (spring_threshold) | cuánta tensión hace falta para que valga la pena actuar; se relaciona con el costo mínimo de una acción | derivable del contrato de viabilidad — *supuesto* |

Los defaults actuales son **supuestos**: quedan marcados hasta derivarlos de un
contrato o medirlos en un escenario real (ver §6 ablación).

### Simulación (λ=0.003, κ=0.02, θ=0.10, ρ=1.0, x*=0.30)

Rampa de ~40 ticks de 0.30 → pico ~0.49 → pulso a ~0.38 → repite. Mesa
oscilante en déficit moderado con techo lentamente creciente. Render verificado
en el artefacto de trayectoria: siluetas "S" legibles, cada descarga marcable
en el event rug.

## 4b. El techo residual del pulsátil puro

El pulsátil con carga lineal (`σ += κ·d`) sigue acotado: por ciclo la deriva gana
`λ·θ/(κd)` y la liberación resta `ρθ` → neto positivo solo si `d < λ/(κρ)`.
El techo es ~`x* + λ/(κρ)` — la misma ley λ/κ con forma de onda. La mesa ahora
**oscila viva**, pero no hacer nada sigue siendo seguro. Verificado: con
`λ=0.003, κ=0.02, θ=0.10, ρ=1.0` el techo queda en ~0.49.

## 4c. Resorte-imán: alcance finito

Un imán pierde agarre con la distancia — la homeostasis tiene *reach* limitado.
La carga pasa a ser:

```
σ(t+1) = σ(t) + κ·(x−x*)·e^(−|x−x*|/w)
```

La fuerza de carga crece hasta `d=w` (máximo `κw/e`) y decae después. Surgen dos
regímenes:

- `λ < κρw/e`: atrapado oscilando bajo viabilidad — pero un shock `u` puede
  empujarlo más allá del alcance → cascada hasta la muerte
- `λ > κρw/e`: la deriva siempre gana → negligencia garantiza muerte

`w=∞` recupera el pulsátil de techo fijo — un mecanismo unifica todo.

Verificado (`λ=0.008, κ=0.04, w=0.25, θ=0.12, ρ=1.0`): cruza moderate t=12,
high t=31, critical t=77, viabilidad t~105 → muere. Render: `magnet_spring.png`.

## 4d. Regla de diseño de w — la primera procedencia real del parámetro

La ablación (`docs/ABLATION-SPRING.md`, segunda pasada) mostró que con
`w=0.25` el umbral de escape quedaba en `x≈0.93` — prácticamente sobre el
límite de viabilidad `0.90`, así que ningún shock sobrevivable podía sacar al
drive del alcance. **Eso no es un detalle de calibración: es el criterio que
le faltaba al parámetro.**

Regla de diseño: **w tiene que ser lo bastante corto como para que exista una
región de no retorno dentro del rango viable.** Si el umbral de escape cae
sobre o más allá del límite de viabilidad, el alcance finito no hace nada y
el mecanismo degenera al pulsátil acotado.

### Derivación — w como parámetro derivado

El escape ocurre cuando la carga de tensión por tick cae por debajo de lo que
la deriva agrega en el mismo intervalo: el umbral de escape `d*` (desviación
a partir de la cual no hay retorno) resuelve

```
κ · d* · e^(−d*/w) = λ/ρ
```

El lado izquierdo es la tasa de carga a desviación `d` (cuánta tensión gana
el resorte por tick); el derecho es la deriva efectiva por pulso de
liberación. Despejando `w` en función del `d*` deseado:

```
w = d* / ln(ρ·κ·d* / λ)        — válido si ρ·κ·d* > λ
```

La restricción `ρ·κ·d* > λ` dice que `d*` debe estar más allá del techo del
pulsátil acotado (`d_eq = λ/(ρκ)`) — si el punto de escape que elegís está
dentro de la mesa oscilante, la ecuación no tiene solución porque ahí el
agarre siempre gana.

### Receta

1. Elegí `d*` = dónde querés que arranque el no-retorno. Tiene que quedar
   **dentro** del margen viable, con holgura: `d* ≈ 0.5–0.8 · (v_hi − x*)`
   es una lectura razonable — más allá hay déficit recuperable, menos y el
   shock ya era casi mortal de por sí.
2. Verificá la restricción `ρ·κ·d* > λ` (si no, subí κ o revisá λ — el drive
   escaparía incluso sin alcance finito).
3. `w = d* / ln(ρ·κ·d*/λ)`.
4. Chequeo de consistencia: `w > e·λ/(κρ)` garantiza que el régimen atrapado
   existe (agarre máximo `κw/e` vence a la deriva — si no, la negligencia
   mata siempre y w pierde sentido discriminatorio).

Ejemplo (los parámetros de la ablación): `λ=0.002, κ=0.04, ρ=1.0, x*=0.30,
v_hi=0.90`. Margen viable `0.60`; elegimos `d*=0.42` (70% del margen).
Restricción: `0.04·0.42 = 0.0168 > 0.002` ✓. Entonces
`w = 0.42 / ln(8.4) = 0.42/2.13 ≈ 0.197` — consistente con el `w=0.18` que
produjo escape a `x≈0.65–0.70` en la ablación. Con `w=0.25` la fórmula
predice `d*≈0.63` → `x≈0.93` > viabilidad → degenerado, exactamente lo que
se observó.

Con esta regla `w` deja de ser una perilla libre: **se deriva de dónde el
diseñador declara que empieza el no-retorno**, que es una propiedad del
dominio (a partir de qué déficit la recuperación propia ya no alcanza).

## 5. Implementación (adoptada en 0.3.0)

- `Drive(spring="pulsatile")` como default nuevo; `spring="linear"` conserva el
  comportamiento viejo — útil para procesos que saturan de verdad (batería,
  stamina, contexto) y como baseline de ablación
- Nuevos params: `spring_threshold` (θ), `spring_release` (ρ), `spring_reach`
  (w, `inf` = techo fijo, finito = escape posible)
- Estado interno `self._tension` por drive
- Evento canónico nuevo `TensionReleased` (payload: tensión descargada, tick) —
  renderizable como marca en el event rug del artefacto
- El ghost del artefacto proyecta con la misma política
- `kappa` conserva su rol (tasa de carga); docs/EPA.md actualiza la ecuación

Decisión de versionado: cambio de dinámica → `0.3.0`.
