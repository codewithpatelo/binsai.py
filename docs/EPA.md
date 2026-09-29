# Binsai — documentación de la EPA y de las variables observadas

**Estado:** borrador de trabajo, actualizado con las definiciones vigentes de la línea. Alcance: qué es Binsai, qué es la Ecuación Proacción (EPA), y cómo se parametrizan necesidades, zonas algedónicas y variables observadas (nivel y ritmo).

## 1. Qué es Binsai

Binsai es a la EPA lo que scikit-learn es a los modelos estadísticos, y a los agentes autorregulados lo que NetLogo es a los modelos basados en agentes: una librería para investigar, no un framework de producción.

Su propósito es que instanciar un agente con necesidades como estado interno y variables operativas observadas sea directo y reproducible, siguiendo el patrón orientado a agentes y dirigido por eventos: necesidades y agentes emiten y reciben señales.

Tres clases centrales:

- `Drive` (necesidad): parametrizable, con estado propio; emite y recibe eventos.
- `Agent`: parametrizable, se le instancian drives; tiene AID, ciclo de vida y mensajería tipada.
- `World`: el entorno que engloba a los agentes, lleva el reloj y transporta mensajes y eventos.

## 2. La Ecuación Proacción (EPA)

### 2.1 Qué modela

La EPA es una ecuación de estados. Modela la viabilidad de un sistema: mantener variables operativas dentro de rangos viables de manera indefinida, en un contexto de información local privilegiada, dinámicas no lineales, incertidumbre y tensiones antagónicas que no se resuelven sino que se administran.

No es una ecuación de optimización ni de maximización. No hay objetivo terminal que se maximice: hay rangos que se sostienen.

### 2.2 La ecuación

Para cada necesidad i, en cada pulso (EPA v2 — estado de segundo orden `(x_i, v_i)`, ver `docs/paov2.tex`):

$$
v_i(t+\Delta t) = v_i(t) + a_i(t)\,\Delta t,
\qquad
x_i(t+\Delta t) = x_i(t) + v_i(t+\Delta t)\,\Delta t
$$

$$
a_i(t) =
\lambda_i(x_i,t)
- S_i(x_i,t)
- c_i\,v_i(t)
+ u_i(t)
+ \sum_{j\ne i} W_{ij}\bigl(x_j(t)-x_j^*\bigr)
$$

con el resorte magnético fatigable $S_i = \kappa_i^{\mathrm{ef}}\, d_i\, e^{-|d_i|/w_i}$, $\kappa_i^{\mathrm{ef}} = \kappa_i\, e^{-f_i\Lambda_i}$ y $\dot\Lambda_i = |d_i| - \rho_i^{\Lambda}\Lambda_i$, donde $d_i = x_i - x_i^*$.

| Término | Nombre | Qué hace |
|---|---|---|
| `x_i` | nivel de la necesidad | el estado que se regula — convención: **nivel de satisfacción** (x alto = satisfecho/holgado; x bajo = déficit). Un drive push decae hacia el déficit por negligencia basal; uno pull se repone hacia la holgura y lo drena el trabajo |
| `v_i` | velocidad | la segunda componente del estado — inercia del nivel |
| `x_i*` | punto de equilibrio (set-point) | el punto teórico de armonía |
| `λ_i` | deriva basal | qué le pasa a la necesidad si no ocurre nada |
| `S_i` | resorte magnético | atracción al set-point con alcance finito `d*` y agarre que se fatiga (`w`, `f`) |
| `c_i` | amortiguación | disipa la velocidad — evita oscilación perpetua |
| `u_i` | estímulos y acciones | canal de aceleración: `sustain()` sostenido, `impulse()` salto instantáneo de `x` |
| `W_ij` | acoplamiento | cuánto el desvío de otra necesidad mueve a esta |

El pulso (tick, heartbeat) actualiza la EPA siempre, haya o no estímulos, haya o no perturbaciones. La unidad de tiempo del pulso es parametrizable.

### 2.3 Hiperparámetros

**Punto de equilibrio (`set_point`).** El punto teórico donde hay equilibrio perfecto. Ahí el desvío es cero y, con él, la probabilidad de activación o inhibición.

**Deriva basal (`lambda`).** El movimiento de actualización de la necesidad, que ocurre en cada pulso con independencia de lo que pase afuera. Es el mecanismo por el cual un sistema viable se activa o se inhibe cuando corresponde. A la situación en que el agente no actúa ni recibe estímulos y la dinámica queda librada solo a la deriva y el resorte se la llama **negligencia basal** — bajo negligencia basal sostenida, una necesidad push con deriva suficiente debería escalar hasta la viabilidad, no estancarse (ver §2.3 resorte y `docs/SPRING.md`).

- Subhiperparámetro `basal_direction`: `decay` (la necesidad decae) o `recover` (se recupera).
- Subhiperparámetro `basal_fn`: la forma de esa deriva. Por defecto, decaimiento lineal.

**Resorte (`kappa` + `spring`).** Atrae el nivel hacia el set-point sin llegar al equilibrio perfecto. Sin resorte el sistema puede sentarse exactamente en el set-point y quedar inerte.

- `spring="magnetic-2nd"` (default, EPA v2): fuerza continua `S = κ_ef·d·e^(−|d|/w)` con **alcance finito** `d*` — más allá el agarre decae y la negligencia sostenida o un shock grande pueden escalar hasta la viabilidad. La **fatiga** `f` hace que el desvío sostenido acumule carga alostática `Λ` y degrade `κ_ef` con el tiempo: sin `f` el sistema desatendido oscila para siempre. `w` se deriva por la regla `w = d*/ln(κ_ef·d*/λ⁰)` (`design_spring_reach`) con `d*` estrictamente dentro del margen viable. Subhiperparámetros: `damping` (c), `spring_fatigue` (f), `allostatic_relax` (ρ_Λ).
- `spring="pulsatile"` (legacy): el desplazamiento carga tensión `σ` a razón `κ·d·e^(−|d|/w)` por pulso; cuando `|σ| ≥ θ` el resorte libera un pulso `ρ·σ`. Subhiperparámetros: `spring_threshold` (θ) y `spring_release` (ρ).
- `spring="linear"` (legacy): amortiguador continuo `r = κ·(x−x*)` (comportamiento ≤0.2.x). Acota la desviación en `λ/κ` — útil como baseline de ablación.

Ver `docs/SPRING.md` para el análisis completo y los regímenes dinámicos.

**Acoplamiento (`W`).** Matriz N×N. El acoplamiento entre necesidades de un sistema viable se da por W.

### 2.4 Categorías de necesidad

Toda necesidad es de una de dos categorías, y es un parámetro de la clase:

- **Empuje (`push`)**: mueve hacia la activación. Cuanto más se espera, más presión se acumula.
- **Arrastre (`pull`)**: mueve hacia la inhibición. Cuanto más se actúa, más tira para frenar.

El matiz importante: una necesidad de arrastre puede activar al agente. Inhibir no significa necesariamente que el agente quede quieto; significa atenuar el consumo de aquello que la necesidad protege. Y muchas veces la forma de atenuar ese consumo es hacer algo: una tarea de preservación.

Ejemplos, en un agente que ejecuta trabajo:

| Situación | Qué inhibe | Qué activa la necesidad de arrastre |
|---|---|---|
| RAM cerca del piso | el trabajo que consume memoria | matar procesos sin uso, cerrar el navegador, pausar la implementación hasta que se libere |
| Disco cerca del piso | abrir trabajo nuevo | borrar cachés de compilación, eliminar worktrees de tareas ya cerradas |
| Gasto por encima del ritmo sostenible | el uso del modelo caro | bajar a un modelo más económico, acortar el contexto |
| Contexto saturado | seguir acumulando historia | compactar o resumir la conversación, hacer un traspaso a una sesión nueva |

Todas esas acciones cuestan algo de la propia necesidad de arrastre (arrancar un proceso de limpieza consume tiempo y tokens), pero devuelven mucho más de lo que gastan. Esa asimetría es lo que las vuelve racionales.

La regla que las distingue de abandonar: una acción de inhibición deja al sistema en mejores condiciones de seguir sirviendo su propósito. Si no lo hace, no es inhibición: es abandono disfrazado de prudencia.

Un sistema viable de mínima necesita una de cada tipo. Si todas las necesidades son de arrastre, la política óptima es no hacer nada, porque la inacción siempre las mejora. Con una de cada tipo, el equilibrio sano deja de ser un nivel y pasa a ser un ritmo de trabajo sostenible.

## 3. Zonas algedónicas

Cada necesidad tiene zonas algedónicas: niveles difusos del valor de la necesidad, con umbrales parametrizables.

Canónicamente son siete, simétricas respecto del punto de equilibrio:

| Zona | Color | Significado |
|---|---|---|
| Superávit crítico | rojo | no actuar implica consecuencias irreversibles |
| Superávit fuerte | ámbar | zona de alerta |
| Superávit moderado | amarillo | zona de alerta temprana |
| Equilibrio | verde | zona sin perturbaciones |
| Déficit moderado | amarillo | zona de alerta temprana |
| Déficit fuerte | ámbar | zona de alerta |
| Déficit crítico | rojo | no actuar implica consecuencias irreversibles |

Bajo la convención de satisfacción (x = nivel de satisfacción), las zonas de
**déficit viven por debajo de x*** (x bajo = necesidad insatisfecha) y las de
superávit por encima. Así la negligencia basal de un drive push (λ < 0)
desciende por moderado → fuerte → crítico → viabilidad, que es donde la
dinámica autónoma importa.

> **Corte de comparabilidad**: antes de 0.3.0 la convención era inversa
> (x = magnitud del déficit). Los experimentos anteriores a ese corte — la
> ablación de resortes incluida — se leyeron en la convención vieja y no son
> comparables punto a punto con corridas nuevas. Ver `CHANGELOG.md`.

Más allá del rojo está el límite de viabilidad: cruzarlo es la muerte operativa. Es conjuntivo sobre todas las necesidades: basta una afuera para que el sistema deje de ser viable.

Parámetros de las zonas:

- `thresholds`: los cortes de cada zona, en unidades normalizadas respecto del punto de equilibrio y del límite de viabilidad. Pueden ser asimétricos entre déficit y superávit.
- `fuzzy_width`: cada umbral es una banda de ancho `2w`, no una línea. La pertenencia `μ_z(x) ∈ [0,1]` permite priorizar alarmas por intensidad.
- `hysteresis`: umbrales distintos de entrada y salida (`α_in`, `α_out`), para que una necesidad que oscila cerca de un corte no produzca parpadeo de eventos.

Cada cambio de zona emite un evento (`ZoneChanged`) con la zona anterior, la nueva, el lado (déficit o superávit) y la pertenencia.

## 4. Variables observadas: nivel y ritmo

Esta es la parte que faltaba estandarizar.

### 4.1 Qué es una variable observada

Una necesidad no mira su propio nivel en el vacío: observa N variables operativas del sistema (o, recursivamente, otras necesidades). Cada variable observada aporta dos señales, y las dos son necesarias:

- **Nivel**: dónde está la variable ahora, respecto de su límite.
- **Ritmo (pacing)**: a qué velocidad se mueve, respecto del ritmo que el contrato tolera.

El nivel responde "¿estoy cerca del problema?". El ritmo responde "¿voy camino al problema?". Una variable puede estar en un nivel cómodo y en un ritmo insostenible: ese es justamente el caso que el nivel solo no detecta, y es donde la alerta temprana tiene valor.

### 4.2 Tipos de variable según su contrato

El tipo determina cómo se calculan nivel y ritmo. Es un parámetro obligatorio.

| Tipo | Qué es | Ejemplos | Violación |
|---|---|---|---|
| `budget` | un presupuesto que se consume dentro de una ventana y se repone al cerrarla | gasto de API, cupo de tokens | consumirlo antes de que termine la ventana |
| `floor` | una reserva que no debe bajar de un piso | RAM libre, disco libre | tocar el piso |
| `target` | algo que hay que alcanzar dentro de la ventana | entregas aprobadas, progreso de implementación | terminar la ventana sin alcanzarlo |
| `band` | tiene que quedar dentro de un rango, con déficit y superávit | temperatura, tamaño de cola, PRs por noche | salir por cualquiera de los dos lados |

Todo lo que no encaja en uno de estos cuatro tipos no es una variable observada de viabilidad. Las señales internas del regulador (probabilidad de activación, contadores de actividad, banderas de contexto) van a un canal de actividad, nunca a los sensores de una necesidad.

### 4.3 Presión de nivel

Se normaliza la distancia entre el valor actual y el límite, tomando el set-point como origen:

```
z_nivel = (x − x*) / (L − x*)        con L el límite del lado correspondiente
p_nivel = |z| / (1 − |z|)            forma de barrera: crece sin techo al acercarse a L
```

El signo de `z` determina el lado (déficit o superávit) y, con eso, la zona algedónica.

La forma de barrera es el default porque cerca del límite la presión tiene que crecer mucho más rápido que linealmente. `pressure_fn` es parametrizable si se quiere otra forma (lineal, cuadrática, logística).

### 4.4 Ritmo sostenible: se deriva, no se elige

Esta es la regla que evita los umbrales inventados: el ritmo tolerable sale del contrato y de la ventana, no de un número elegido a mano.

```
budget:  r_sostenible = presupuesto_restante / tiempo_restante_de_ventana
floor:   r_sostenible = (valor_actual − piso) / tiempo_restante_de_ventana
target:  r_requerido  = (objetivo − alcanzado) / tiempo_restante_de_ventana
band:    se calcula por cada lado, con la fórmula del lado que corresponda
```

Ejemplos:

- Gasto con techo de 150 en una ventana de 11,5 h: el ritmo sostenible al inicio es ~13 USD/h. Si a las 3 h van gastados 60, el sostenible pasa a `90 / 8,5 ≈ 10,6 USD/h`: el sostenible se recalcula en cada pulso, no es fijo.
- RAM con piso de 2 GB y 11,8 GB libres a 6 h del cierre: el ritmo tolerable es `9,8 / 6 ≈ 1,6 GB/h` de consumo.
- Entregas: 2 comprometidas, 0 alcanzadas, 8 h restantes: el requerido es `0,25 por hora`.

### 4.5 Presión de ritmo

Dos formas equivalentes; se elige por `pacing_mode`:

Por razón (`ratio`), simple y legible:

```
budget / floor:  p_ritmo = clip(|r_observado| / r_sostenible − 1)
target:          p_ritmo = clip(1 − r_observado / r_requerido)
```

Por tiempo hasta la violación (`time_to_violation`), la más informativa cuando se conoce cuánto tarda una corrección:

```
τ = margen / max(ε, ritmo_neto_hacia_el_límite)       horas hasta violar
p_ritmo = clip(1 − τ / (T_recuperación + T_reacción))
```

`T_recuperación` no se elige: se mide. Cuánto tarda compactar en liberar contexto, cuánto tarda una limpieza en liberar disco, cuánto tarda la reposición de la ventana. Con eso, el ámbar deja de ser un número arbitrario y pasa a significar algo verificable: "al ritmo actual ya no llego a corregir a tiempo".

### 4.6 Estimación del ritmo

Parámetro `rate_estimator`, con estos requisitos:

- Ventana móvil configurable (default: 1 hora) o EWMA.
- Series acumuladas deben ser monótonas. Si una serie acumulada baja (por ejemplo, porque se reinició el proceso que la contaba), el estimador no debe interpretarlo como ritmo negativo: es un reinicio de la fuente, y la serie de la ventana tiene que ser la suma de todas las fuentes.
- Robustez ante huecos: si faltan muestras, se calcula sobre las disponibles y se reporta la cobertura.
- Ritmo firmado: el signo indica si la variable se acerca o se aleja de su límite.

### 4.7 Validez del sensor

Un sensor puede estar ausente, vencido o devolver un valor imposible. En ese caso:

- La variable no aporta presión y se marca como inválida.
- Se emite `SensorInvalid` con el motivo (sin serie, serie vencida, valor fuera de rango físico).
- Nunca se asume verde. Una variable que no se puede medir no es una variable en equilibrio.

Parámetros: `max_staleness` (cuánto puede tardar una muestra antes de considerarse vencida) y `valid_range`.

### 4.8 Agregación

```
p_variable  = max(p_nivel, p_ritmo)                  # manda la peor de las dos
p_necesidad = agg({p_variable} para cada observada)  # default: max
```

El default es `max` porque los recursos no son fungibles: tener disco de sobra no compensa quedarse sin RAM. `aggregation` es parametrizable (`max`, `softmax`, `weighted`) para experimentar, pero cualquier agregación que permita compensar entre variables no fungibles va a subestimar el riesgo.

La variable que determina el máximo se expone como `driving_variable`: es la que está empujando la presión de la necesidad en ese momento, y sin ese dato no se puede auditar de dónde viene una alarma.

### 4.9 Esquema de una variable observada

```python
ObservedVariable(
    name              = "gasto_api",
    kind              = "budget",          # budget | floor | target | band
    unit              = "USD",
    limit             = 150.0,             # techo, piso u objetivo según kind
    set_point         = None,              # opcional; para band, el centro
    window            = "night",           # la ventana en que aplica el presupuesto
    pressure_fn       = "barrier",
    pacing_mode       = "time_to_violation",
    recovery_time_h   = 0.5,               # MEDIDO, no elegido
    reaction_time_h   = 0.1,
    rate_estimator    = {"type": "window", "hours": 1},
    monotonic         = True,              # series acumuladas
    max_staleness_min = 15,
    valid_range       = (0, None),
    source            = "dashboard.billed_attributed",
)
```

### 4.10 El contrato de viabilidad, como archivo

Los valores de las variables observadas no viven en el código: viven en dos archivos versionados.

- `viability-contract.json`: los valores. Por variable: tipo, límite, unidad, ventana, tiempos de recuperación y reacción, y la procedencia de cada número (`medición`, `contrato`, `supuesto`).
- `viability-contract.md`: la semántica del acuerdo, en prosa. Qué significa cada límite y qué pasa al cruzarlo.

Dos reglas:

1. Si un número no tiene una frase en el markdown que explique su consecuencia, ese umbral está mal puesto y hay que revisarlo.
2. Distinguir límite de viabilidad (cruzarlo es muerte operativa) de umbral del contrato (cruzarlo es incumplir lo acordado con el humano). Habilitan acciones distintas.

## 5. Eventos y suscripción

Binsai es orientado a eventos: drives y agentes emiten y reciben señales.

### 5.1 Eventos canónicos

| Evento | Emisor | Cuándo |
|---|---|---|
| `Pulse` | agente | cada tick; actualiza la EPA de todos sus drives |
| `ZoneChanged` | drive o variable observada | al cambiar de banda algedónica, con histéresis |
| `PressureUpdated` | drive | en cada pulso, con `driving_variable` |
| `SensorInvalid` | variable observada | sensor ausente, vencido o fuera de rango |
| `ViabilityBreached` | agente | un drive cruzó su límite de viabilidad |
| `Satiated` | drive | una acción redujo su desvío (señal de calidad `g`) |
| `Coupled` | drive | el desvío de otro drive lo movió, vía W |

El cambio de banda algedónica es un evento de primera clase, y lo emiten tanto los drives como las variables observadas. El payload lleva: emisor, banda anterior, banda nueva, lado (déficit o superávit), pertenencia `μ` y el valor que lo disparó.

### 5.2 Suscripción

Drives y agentes pueden suscribirse y desuscribirse a los eventos de otros drives y agentes. La notación sigue las performativas de FIPA ACL, para no inventar vocabulario:

```python
drive.subscribe(source, event_type, handler)   # FIPA: subscribe
drive.unsubscribe(subscription_id)             # FIPA: cancel
```

- La suscripción se puede filtrar por tipo de evento, por banda de destino o por lado.
- Toda suscripción devuelve un `subscription_id` y se puede cancelar.
- Un drive que se suscribe a otro es una forma explícita de acoplamiento, complementaria a `W`: `W` acopla por estado en cada pulso; la suscripción acopla por evento, solo cuando algo cruza una banda.

## 6. El agente: ciclo de vida, identidad y mensajes

### 6.1 Ciclo de vida

Los estados siguen la especificación de gestión de agentes de FIPA, que define el ciclo de vida de un agente en una plataforma. [VERIFICAR la numeración exacta de la especificación antes de citarla.]

| Estado | Qué significa | ¿La EPA se actualiza? | ¿Puede activarse o inhibirse? |
|---|---|---|---|
| `INITIATED` | creado, todavía no corre | no | no |
| `WAITING` | disponible, sin tarea en curso | sí | sí: es el estado en que la EPA decide |
| `ACTIVE` | ejecutando una tarea | sí | no: hay compromiso con la tarea en curso |
| `SUSPENDED` | dormido, en consolidación | sí, con la deriva basal | no, salvo por evento crítico |
| `TERMINATED` | fin de la simulación o del agente | no | no |

El estado que pedía llamarse `WORKING` es `ACTIVE` en la nomenclatura de FIPA, y el que estaba llamado `ACTIVE` pasa a ser `WAITING`: en FIPA, un agente en `Waiting` está vivo y a la espera de un evento que lo mueva, que es exactamente el estado en el que la EPA tiene que poder activarlo.

La regla de compromiso: mientras el agente está en `ACTIVE`, la EPA se sigue actualizando y las bandas se siguen emitiendo, pero no se dispara activación ni inhibición por presión. Eso evita el dithering: cambiar de conducta a mitad de una tarea porque otro drive subió un poco.

Excepción: una banda roja o un cruce de límite de viabilidad sí interrumpe un `ACTIVE`. Es la diferencia entre "hay algo más urgente" y "esto va a matar al sistema". Parametrizable con `interrupt_on_zone` (default: `red`).

Transiciones:

```
INITIATED --invoke--> WAITING
WAITING   --execute--> ACTIVE        (por decisión de la EPA o por mensaje)
ACTIVE    --done|abort--> WAITING
WAITING   --suspend--> SUSPENDED     (consolidación, descanso)
SUSPENDED --resume--> WAITING
cualquiera --quit--> TERMINATED
```

FIPA define además `TRANSIT`, para agentes móviles que migran de plataforma. Binsai no lo usa por ahora; queda el nombre reservado por si más adelante hay agentes que se mueven entre mundos.

### 6.2 Identidad y mensajes

Cada agente tiene un AID (agent identifier), al estilo FIPA: un nombre único dentro de la plataforma y sus direcciones de transporte.

Los mensajes entre agentes son tipados y usan las performativas de FIPA ACL, para que el vocabulario sea estándar y no propio:

| Performativa | Uso en Binsai |
|---|---|
| `inform` | comunicar un hecho o un cambio de estado |
| `request` | pedir la ejecución de una acción |
| `agree` / `refuse` | aceptar o rechazar un pedido |
| `failure` | informar que una acción pedida falló |
| `query-if` | preguntar por el estado de algo |
| `subscribe` / `cancel` | suscribirse y desuscribirse a eventos |
| `propose` / `accept-proposal` / `reject-proposal` | negociación entre agentes |

```python
agent.send(Message(
    performative = "request",
    receiver     = other_aid,
    content      = FreeDiskSpace(target_gb=5),
    conversation_id = "...",
))
```

El contenido es tipado: cada tipo de mensaje declara su esquema, para que el receptor no tenga que interpretar texto libre.

### 6.3 La clase World

`World` es el entorno que engloba a los agentes: el equivalente de la plataforma de agentes de FIPA.

Responsabilidades:

- Registro de agentes por AID, con su estado de ciclo de vida. Es el rol que en FIPA cumple el AMS (Agent Management System).
- Transporte de mensajes entre agentes y entrega de eventos a los suscriptos.
- El reloj: emite el `Pulse` que actualiza la EPA de todos los agentes, con la unidad de tiempo configurada.
- Las variables del entorno: lo que los agentes observan y no controlan, y su dinámica propia.
- La traza: el registro completo de pulsos, cambios de banda, mensajes y transiciones de estado, que es lo que después se analiza.

Opcionalmente, un directorio de servicios al estilo del DF (Directory Facilitator) de FIPA, para que un agente encuentre a otros por lo que ofrecen y no por su nombre.

## 7. Qué queda por definir

- La señal de calidad `g`: cómo se mide que una acción efectivamente satisfizo la necesidad que la originó. Hoy es el problema abierto de la línea.
- El catálogo de acciones como skills: cada acción con precondiciones, procedimiento, vector de efectos esperados sobre cada necesidad, costo estimado y verificación. Falta el esquema.
- Triaje de la ventana por complejidad: el ritmo requerido de `target` hoy usa un prior único; debería derivarse de la duración esperada según la complejidad de cada tarea.
- Alostasis: anticipar el desvío en lugar de corregirlo después exige un modelo del mundo, no solo del propio estado. Es dirección de trabajo, no resultado.
