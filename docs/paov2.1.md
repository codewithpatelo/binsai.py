# Ecuación Proacción v2.1 — especificación de cambios

**Estado:** delta sobre EPA v2. Todo lo que no está acá sigue igual que en v2.
**Origen:** la noche del 2026-10-09 en multiply-overnight. Cada cambio abajo
está anclado a una observación de esa corrida, no a una intuición.
**Destinatario:** implementación en Binsai.

## 0. El problema que v2.1 corrige

v2 define la perturbación como un canal de estímulo `u` sobre la aceleración.
La implementación la colapsó en la deriva basal `λ`. El resultado es un
sistema que nunca es perturbado: solo cambia de pendiente.

Evidencia de la noche del 2026-10-09, 166 muestras por drive, una por minuto:

- Cero discontinuidades en 166 muestras. El drive metabólico describe una U
  suave (0.462 → 0.291 → 1.000); el de servicio una rampa limpia
  (0.000 → −0.921). No hay un solo impulso en la trayectoria.
- `rate` (la fuente de presión de ritmo) fue `null` en 166 de 166 muestras,
  en los dos drives.
- Las tres fuentes de presión (`level`, `rate`, `autonomous`) tuvieron
  `status: "uncalibrated"` en 166 de 166 muestras. `dominant: "unknown"` las
  166 veces.
- La presión agregada fue 0.465 con el drive metabólico clavado en 1.000 (el
  límite de viabilidad) y el de servicio en −0.825. Con
  `h = min(12, 0.25·e^(3.1·p))` eso da una espera esperada de 57 minutos, 72
  minutos de ciclo contando el refractario de 15. El sistema despertaba una
  vez por hora con un drive muerto.
- `level` del drive metabólico alcanzó 1.934, por encima de la escala del
  límite de viabilidad.
- El drive metabólico estuvo 28 minutos clavado en 1.000 (saturado: un drive
  saturado no transporta información).
- La condición inicial del drive metabólico fue 0.462 en la primera muestra
  de la noche, con set-point 0.15 y límite 1.
- El manager predijo por escrito el efecto de su acción ("lifting service
  from −0.785 toward 0") y nadie midió si ocurrió.
- El sistema ya detecta cruces de zona (`amber_exposure`,
  `first_red_excess_at`) pero los calcula para el reporte, no para la
  dinámica.

Los siete cambios de abajo salen de esa lista.

## 1. La perturbación es un impulso de evento, no una inclinación de la deriva

### 1.1 Qué cambia

Las variables observadas emiten eventos al cruzar una frontera de zona. Cada
evento inyecta un impulso sobre la aceleración del drive suscripto, con
magnitud y signo. La deriva basal `λ` deja de ser el vehículo de la
perturbación.

La ecuación de v2 no cambia:

```
a(t) = λ·φ(x) − S(x) − c·v + u(t) + Σ_j W_ij·x_j
v(t+Δt) = v(t) + a(t)·Δt
x(t+Δt) = x(t) + v(t+Δt)·Δt
```

Lo que cambia es qué entra por `u`. En v2.1, `u(t)` es la suma de los
impulsos activos en ese tick:

```
u(t) = Σ_k ι_k · ψ(t − t_k)
```

donde `ι_k` es la magnitud con signo del impulso k, `t_k` su instante de
emisión, y `ψ` un núcleo de decaimiento con ancho `τ_u`:

```
ψ(s) = e^(−s/τ_u)   para s ≥ 0,   0 en otro caso
```

`τ_u` por defecto: 2 ticks. Un impulso es un golpe, no un escalón.

**Por qué sobre la aceleración y no sobre el nivel.** Si el impulso entra en
`x`, el sistema salta y vuelve con la dinámica de siempre. Si entra en `a`,
la velocidad `v` carga la memoria del golpe: el drive sigue alejándose
después de que el impulso terminó, y el resorte magnético tiene que ganarle
a una velocidad adquirida. Eso es precisamente para lo que hacía falta el
segundo orden en v2, y es lo que se pierde al meter la perturbación en `λ`.

### 1.2 Magnitud y signo

El signo lo da la dirección del cruce respecto del set-point, no la zona de
destino:

- cruce que aleja del set-point → `ι > 0` (perturba)
- cruce que acerca al set-point → `ι < 0` (sacia)

La magnitud la da la severidad del cruce:

| cruce | `ι` base |
|---|---|
| verde → amarillo | `ι₁` (leve) |
| amarillo → ámbar | `ι₂` (media) |
| ámbar → rojo | `ι₃` (fuerte) |

Con `ι₁ < ι₂ < ι₃`. Valores iniciales sugeridos, a calibrar: `ι₁ = 0.02`,
`ι₂ = 0.06`, `ι₃ = 0.18` por tick de aceleración. El cruce en sentido de
mejora usa la misma tabla con signo negativo y un factor de asimetría
`ζ ≤ 1` (mejorar sacia menos de lo que empeorar perturba; `ζ = 0.6` inicial).

### 1.3 Vale igual para nivel y para ritmo

Hay dos familias de variables observadas y las dos emiten:

- **Nivel.** El valor de la variable cruza una zona. RAM libre pasa de verde
  a amarillo → impulso leve al drive metabólico.
- **Ritmo.** La tasa sostenible —presupuesto restante dividido por ventana
  restante, recalculada en cada pulso— cruza una zona. Que la tasa necesaria
  para cumplir se vuelva inalcanzable es una perturbación al drive de
  servicio, no un ajuste de su basal.

Las dos familias usan la misma tabla de magnitudes y el mismo mecanismo de
evento.

### 1.4 La deriva basal sigue existiendo

Que nivel y ritmo además modulen `λ` no está mal y se mantiene: es el fondo
lento, la tendencia de la noche. Lo que no puede ser es el único canal. El
fondo lento explica por qué un drive deriva; los eventos explican por qué se
mueve la aguja.

### 1.5 Interfaz en Binsai

```
interface PerturbationEvent {
  t: number                    // ms epoch
  variable: string             // 'ram_free_gb' | 'spend_usd' | 'sustainable_rate' | ...
  kind: 'level' | 'pace'
  from: Zone                   // 'green' | 'yellow' | 'amber' | 'red'
  to: Zone
  direction: 'away' | 'toward' // respecto del set-point
  impulse: number              // ι con signo, ya aplicado ζ si corresponde
  driveId: string              // drive suscripto
}
```

La variable observada publica; el drive se suscribe. El drive no consulta a
la variable. Una variable puede alimentar a más de un drive; un drive puede
escuchar a más de una variable.

## 2. La presión: normalizar y agregar de forma conjuntiva

### 2.1 Normalización

Toda fuente de presión devuelve un valor en `[0, 1]`. La noche del 09 tuvo
`level = 1.934`, que rompe cualquier agregación posterior y rompe el mapeo
presión → tasa de activación.

```
presión_nivel_i   = min(1, |d_i| / |L_i − x*_i|)
presión_ritmo_i   = min(1, max(0, 1 − tasa_sostenible_i / tasa_requerida_i))
presión_autónoma_i = min(1, η · |v_i| / v_ref)
```

donde `d_i = x_i − x*_i`, `L_i` es el límite de viabilidad del lado en que
está el desvío, y `v_ref` es la velocidad de referencia del drive.

### 2.2 Fuente ausente ≠ fuente en cero

Una fuente sin calibrar no vale 0. Vale desconocida, y eso es información
distinta.

```
presión_i = max sobre las fuentes CALIBRADAS de i
```

Si una fuente está sin calibrar, queda fuera del máximo y se registra el
hecho. Nunca entra como 0.

El bug de la noche del 09: la componente de tiempo valía `0.000` por estar
sin calibrar, y al promediarse con las otras dos bajaba la presión alrededor
de un tercio. Con `memoryError = 0.125`, `tokenError = 1.000`,
`timeError = 0.000`, la media da 0.375 — y la presión observada fue 0.393.

### 2.3 Agregación entre drives: conjuntiva, no promedio

El conjunto viable `K` es la intersección de los contratos de todos los
drives. Morirse por una variable es morirse. Por lo tanto:

```
presión_sistema = max_i presión_i
```

o, si se quiere suavidad, una t-norma estricta. Nunca el promedio. Promediar
un drive muerto con uno sano da tibieza, y la tibieza de la noche del 09 fue
0.465 con el metabólico en el límite.

### 2.4 Saturación

Un drive clavado en el límite no transporta información. Cuando
`|d_i| ≥ |L_i − x*_i|`:

- `presión_i = 1` y se mantiene;
- se emite un evento `drive_saturated` con el instante de entrada;
- el tiempo acumulado en saturación pasa a ser una variable observada por
  derecho propio, porque la duración sí transporta información cuando el
  nivel ya no.

La noche del 09 tuvo 28 minutos de saturación metabólica indistinguibles
entre sí.

### 2.5 Condición inicial

El estado inicial de cada drive al abrir la ventana se declara en el
contrato de viabilidad, no se hereda. Una ventana que abre con el metabólico
en 0.462 sobre un límite de 1 arranca con la mitad del margen gastado antes
de hacer nada. Por defecto `x_i(t₀) = x*_i`, y cualquier otro valor tiene que
estar escrito y justificado en el contrato.

## 3. La señal de calidad `g` se mide

v2 ya define `g = Δ_obs / Δ_exp`. No estaba implementada.

### 3.1 La acción declara su efecto esperado

Toda acción del agente lleva, antes de ejecutarse, una predicción
cuantitativa:

```
interface ExpectedEffect {
  driveId: string
  deltaExpected: number   // Δ_exp, con signo
  byWhen: number          // ms epoch: cuándo debería ser observable
}
```

El manager de la noche del 09 ya escribía esto en prosa, en el campo
`changedAfter`: "lifting service from −0.785 toward 0", "unpinning
tokenError from 1.00". El cambio es volverlo un número con un plazo.

### 3.2 El bucle lo verifica

En `byWhen` el bucle de observación computa `Δ_obs` sobre el drive nombrado
y registra:

```
g = Δ_obs / Δ_exp     (acotado a [−1, 2] para que un sobredisparo no explote)
```

### 3.3 Qué hace `g` con la dinámica

Esta es la parte sustantiva:

- `g ≥ g_ok` (por defecto 0.5): la acción funcionó. Se aplica la saciación
  (`ι < 0`) sobre el efecto medido, nunca sobre la acción tomada.
- `|g| < g_nulo` (por defecto 0.15): la acción no movió la aguja. No se
  aplica saciación, la activación no se consume, y se emite un impulso de
  perturbación de magnitud `ι₂` al drive involucrado. Intentar y no lograr es
  peor que no intentar: cuesta presupuesto y no mueve el desvío.
- `g < 0`: la acción empeoró el desvío. Impulso `ι₃` y la acción queda en el
  libro de intentos con resultado `harmful`, lo que la inhabilita para la
  misma falla en la misma ventana.

### 3.4 La regla que esto hace cumplir

La saciación se aplica sobre efecto medido, nunca sobre acción tomada. Un
drive que se calma porque el agente intentó algo es un drive que se miente.
Es el Satiation Signal Problem en su forma más pura, y `g` es la defensa.

En la noche del 09 esto no falló —los drives se deterioraron monótonos, sin
saciación falsa— pero es la regla que impide que falle cuando la presión se
arregle y el agente empiece a actuar de verdad.

## 4. Proyección fantasma: tiempo a muerte

### 4.1 Cálculo

Sobre una ventana móvil de los últimos `N` ticks (por defecto 30), para cada
drive:

```
pendiente_i = (x_i(t) − x_i(t − N·Δt)) / (N·Δt)
margen_i    = L_i − x_i(t)                      // con el signo del lado en que está
TTD_i       = margen_i / pendiente_i            // si pendiente apunta al límite, si no: ∞
```

`TTD` = projected time to death by basal negligence. Es por drive, y el del
sistema es el mínimo:

```
TTD_sistema = min_i TTD_i
```

### 4.2 Por qué importa

Con los datos reales de la noche del 09, a las 00:40 hora local:

- servicio: valor −0.921, pendiente −0.00674/min → TTD = 11.7 minutos
- metabólico: ya en el límite

Y el contexto que recibía el manager en ese momento decía `timeError = 0.000`.

`TTD` no necesita nada nuevo: la pendiente sale de las muestras que el
controller ya escribe. Es el número más informativo que se puede poner en el
prompt de un agente que tiene que entender urgencia, y ya está disponible.

### 4.3 Dónde se usa

- En el prompt dinámico del agente, por drive y del sistema.
- Como insumo de la tasa de activación (§5).
- Como material de alostasis: `TTD` es la cantidad que dice cuánto anticipar,
  no cuánto reaccionar. La carga alostática `Λ` de v2 describe el costo
  acumulado de haber regulado; `TTD` describe el horizonte que queda. Son las
  dos caras.

## 5. La tasa de activación se deriva de la proyección

### 5.1 El problema con la forma actual

`h = min(h_max, h₀·e^(γ·p)` tiene tres números elegidos a mano (`h₀`, `γ`,
`h_max`) y ninguno está anclado a nada. En la implementación de la noche del
09, además, el tope era inalcanzable: hacía falta `p = 1.249` para tocarlo, y
el refractario de 15 minutos topea las activaciones efectivas en 4/h sin
importar lo que diga `h`.

### 5.2 El anclaje

La espera esperada tiene que ser una fracción del horizonte que queda:

```
E[espera] = 1/h  ≤  θ · TTD_sistema
```

con `θ` la fracción admisible (por defecto `θ = 0.2`: despertar al menos
cinco veces antes de morir). De ahí:

```
h_requerida = 1 / (θ · TTD_sistema)
h = min(h_max, max(h₀·e^(γ·p), h_requerida))
```

Con `TTD = 11.7 min` y `θ = 0.2`, `h_requerida = 25.6/h`, o sea 2.3 minutos
de espera esperada. El contraste con los 57 minutos reales es la medida
exacta del fallo.

`θ` y `h_max` siguen siendo hiperparámetros, pero son dos y tienen
interpretación directa, en lugar de tres sin interpretación. `h₀` y `γ` se
conservan como piso de exploración cuando `TTD = ∞` (ningún drive
acercándose a su límite).

### 5.3 El refractario tiene que escalar

Un refractario fijo de 15 minutos, con espera esperada de 2.3 minutos, es el
techo real. El refractario pasa a ser:

```
refractario = min(refractario_max, max(refractario_min, β · TTD_sistema))
```

con `β = 0.1`, `refractario_min = 1 min`, `refractario_max = 15 min`. Con
`TTD = ∞` queda en el máximo; con `TTD = 11.7 min` queda en ~1.2 min.

### 5.4 Lo que no cambia

- La activación sigue siendo estocástica: `p_tick = 1 − e^(−h·Δt)`,
  invariante al tamaño del tick.
- No hay activación garantizada en rojo. El rojo sube `h`, no fuerza el
  disparo.
- No se vuelve a sortear mientras el agente está activo.
- `h` nunca es una tabla por zona.

## 6. La historia de perturbaciones entra al prompt dinámico

El campo `perturbation` del log de la noche del 09 contenía una copia literal
del campo `action`. Existe y está mal usado.

En v2.1 el prompt dinámico del agente, al activarse, recibe:

- Perturbaciones desde la última activación: lista de `PerturbationEvent`,
  cada una con instante, variable, cruce de zona, magnitud y signo.
- Perturbaciones acumuladas de la ventana: la misma lista agregada por
  variable, para que se vea el patrón y no solo el instante.
- Estado de cada drive: `x`, `v`, `d`, presión por fuente con su estado de
  calibración, zona, tiempo en saturación si aplica.
- `TTD` por drive y del sistema.
- `g` de las acciones del ciclo anterior, con `Δ_exp` y `Δ_obs` lado a lado.
- Libro de intentos de la ventana: qué se probó para cada falla, con qué
  resultado medido.
- El contrato de viabilidad, verbatim.

El punto 7 no es decorativo: ver §7.3.

## 7. Guardas

### 7.1 Señal ausente no es desacuerdo

Una guarda que bloquea ante contradicción entre señales no puede dispararse
si una de las señales está sin calibrar. Una señal ausente no contradice:
falta.

Esto es lo que mató la noche del 09. `destructiveActionGuard` bloqueó
`reload_controller` con `signals_contradict` porque el drive de servicio
estaba en rojo (−0.825, señal real) y el pacing estaba en verde/amarillo — y
el pacing estaba ahí porque `rate` era `null` y la fuente estaba sin
calibrar. El arreglo correcto, ya escrito en disco por el agente, quedó sin
cargar.

Regla: si alguna señal del predicado de la guarda está sin calibrar, la
guarda no bloquea y registra `guard_skipped_uncalibrated` con el nombre de
la señal.

### 7.2 Una guarda no puede dejar un arreglo diagnosticado sin aplicar

Las guardas distinguen acciones destructivas de acciones correctivas. Una
acción correctiva que el agente justificó con causa raíz puede requerir
registro, puede requerir confirmación, no puede quedar bloqueada mientras la
ventana se muere. Si una guarda rechaza una correctiva, el rechazo sube la
presión en lugar de consumir la activación, y el motivo entra al prompt del
ciclo siguiente.

### 7.3 El contrato sobrevive a la compactación

El contrato de viabilidad no entra nunca a una compactación con pérdida. Se
verifica su integridad en cada activación y se reinyecta después de cada
compactación.

Esto no es paranoia: hay medición publicada de que una política presente en
contexto sin compactar da 0% de violaciones, y tras un solo paso de
compactación 30%, y tras cuatro 78%; y que si la restricción sobrevivió al
resumen la violación es 0%, mientras que si se cae es 38%. Las restricciones
blandas decaen unas 8 veces más que las duras. El costo de la mitigación es
del orden de decenas de tokens.

Implementación mínima: hash de las claves del contrato al abrir la ventana;
en cada activación, verificar presencia verbatim del bloque; si falta,
reinyectar antes de seguir y registrarlo.

### 7.4 El tope de iteraciones no es un freno

Un tope de iteraciones por activación es un mecanismo de parada más. Si al
agotarse las iteraciones el desvío no bajó (`g` nulo o negativo en todas),
la activación no se cierra como consumida: se registra como activación
fallida, la presión sube, y el refractario no se aplica.

En la noche del 09, el agente llegó a 3/3 iteraciones con el arreglo correcto
bloqueado y se fue a dormir con los dos drives en rojo. La forma de la falla
fue tope de iteraciones + correctiva bloqueada = estacionar el arreglo.

## 8. Trazas de cambio de estado

No es una propiedad de la ecuación, pero sin esto v2.1 no es diagnosticable y
por eso va en la especificación.

Cada módulo emite un evento de primera clase, con instante y motivo, en cada
cambio de estado. Como mínimo:

- transición de ciclo de vida de cada agente (`INITIATED` / `WAITING` /
  `ACTIVE` / `SUSPENDED` / `TERMINATED`);
- cada disparo de guarda, con las señales que lo dispararon y su estado de
  calibración;
- cada tope de tiempo alcanzado, con el módulo y el valor del tope;
- cada vez que un camino de excepción reutiliza un artefacto previo;
- cada acción rechazada, con el motivo;
- cada sorteo de activación: presión por drive y por fuente, `TTD`, `h`,
  `p_tick`, el sorteo y el resultado;
- cada `ExpectedEffect` emitido y cada `g` medido.

La cadena causal de la noche del 09 tiene siete pasos y ninguno fue un evento
en el log: se reconstruyó porque el agente la narró en prosa dentro de un
campo de texto libre. Si esa activación hubiera devuelto JSON malformado
—como la primera de las tres— la noche sería un misterio. Eso no es
observabilidad.

## 9. Qué no cambia respecto de v2

- Dinámica de segundo orden: `a → v → x`.
- Resorte magnético con alcance finito: `S = κ_ef · d · e^(−|d|/w)`.
- Fatiga / carga alostática: `κ_ef = κ · e^(−f·Λ)`, `dΛ/dt = |d| − ρ_Λ·Λ`.
- Regla de diseño del alcance: `w = d*/ln(κ_ef·d*/λ⁰)`, con `d*` dentro del
  rango viable; agarre máximo `G = κw/e`.
- Punto de no retorno: `d* = −w·W₋₁(−λ⁰/(κ_ef·w))`.
- Deriva basal con forma `φ`, y drives de empuje y de arrastre como
  consecuencia del signo de `λ` y del signo del efecto de la acción —no como
  hiperparámetros.
- Acoplamiento `W` entre drives.
- Cuatro zonas algedónicas, cada una de las no-verdes apareciendo dos veces
  sobre el eje (déficit y superávit), con histéresis y pertenencia difusa `μ`.
- Conjunto viable `K` como intersección de los contratos.
- Activación estocástica con `p_tick = 1 − e^(−h·Δt)`.

## 10. Fuera de alcance: v2.2

Pronóstico de serie temporal para anticipar perturbaciones catastróficas. La
idea es buena —ajustar la proyección en función de la historia de la ventana
y obtener un projected time to death by catastrophic perturbance— pero
necesita que exista una historia de impulsos sobre la cual pronosticar. Hoy
no existe: la noche del 09 tuvo cero eventos de perturbación en la dinámica.
Pronosticar sobre lo que hay sería pronosticar la deriva basal, que ya se
proyecta linealmente en §4.

Entra cuando §1 esté corriendo y haya varias ventanas con eventos reales.

## 11. Censo de hiperparámetros: delta

Nuevos:

| símbolo | significado | valor inicial |
|---|---|---|
| `ι₁`, `ι₂`, `ι₃` | magnitud del impulso por severidad de cruce | 0.02 / 0.06 / 0.18 |
| `ζ` | asimetría mejora vs empeoramiento | 0.6 |
| `τ_u` | ancho del núcleo de decaimiento del impulso | 2 ticks |
| `g_ok` | umbral de efecto logrado | 0.5 |
| `g_nulo` | umbral de efecto nulo | 0.15 |
| `θ` | fracción del `TTD` admisible como espera esperada | 0.2 |
| `β` | fracción del `TTD` para el refractario | 0.1 |
| `N` | ventana móvil para la pendiente del `TTD` | 30 ticks |

Eliminados o degradados:

- `h₀` y `γ`: pasan de definir la tasa a ser solo el piso cuando `TTD = ∞`.
- Refractario fijo: reemplazado por `β · TTD`.
- Cualquier tabla zona → tasa: eliminada.
- Cualquier presión que entre como 0 por estar sin calibrar: eliminada.

Todos los valores iniciales son provisionales y van en el contrato de
viabilidad, no en el código.

## 12. Pruebas de aceptación

1. **La perturbación se ve.** Forzar un cruce verde→amarillo en una variable
   observada y verificar que la trayectoria del drive presenta una
   discontinuidad en la aceleración, y que `v` sigue alejándose del set-point
   después de que el impulso decayó. Una noche sin discontinuidades en 166
   muestras falla esta prueba.
2. **Fuente ausente no vale cero.** Poner una fuente de presión en
   `uncalibrated` y verificar que queda fuera del máximo y que se registra,
   en lugar de entrar como 0.
3. **Agregación conjuntiva.** Con un drive en el límite de viabilidad y otro
   en el set-point, la presión del sistema es 1, no 0.5.
4. **Normalización.** Ninguna fuente de presión devuelve un valor fuera de
   `[0, 1]` en ninguna muestra de una ventana completa.
5. **`g` nulo no sacia y no consume.** Ejecutar una acción con `Δ_exp`
   declarado que no produce efecto; verificar que no se aplica saciación,
   que la activación no se cuenta como consumida, que se emite impulso `ι₂` y
   que la presión sube.
6. **`TTD` en el prompt.** Dado un drive con pendiente hacia su límite, el
   prompt de la activación siguiente contiene el `TTD` del drive y del
   sistema, y el `TTD` coincide con el cálculo de §4 sobre las muestras del
   log.
7. **La tasa respeta el horizonte.** Con `TTD = 12 min` y `θ = 0.2`, la
   espera esperada es ≤ 2.4 minutos.
8. **La guarda no bloquea con una señal ausente.** Reproducir el caso de la
   noche del 09: drive de servicio en rojo, fuente de ritmo sin calibrar,
   acción correctiva propuesta. La acción se ejecuta y se registra
   `guard_skipped_uncalibrated`.
9. **El contrato sobrevive.** Forzar una compactación y verificar que el
   bloque del contrato está verbatim en la activación siguiente, y que la
   verificación de integridad queda registrada.
10. **Condición inicial del contrato.** Abrir una ventana y verificar que el
    estado inicial de cada drive es el declarado en el contrato, y que
    cualquier valor distinto del set-point está justificado por escrito.
11. **Saturación registrada.** Llevar un drive al límite y verificar que se
    emite `drive_saturated` y que el tiempo acumulado en saturación aparece
    como variable observada.
12. **Trazas.** Reconstruir la cadena causal de una falla usando solo los
    eventos del log, sin leer ningún campo de texto libre de un agente.