# Activación por tasa de riesgo — no probabilidad por tick

## El bug de diseño

Antes de EPA v2 la activación era implícita: cada tick en WAITING el agente
sorteaba la distribución softmax completa, y `1 − p(idle)` era de facto la
probabilidad de actuar *por tick*.

El problema: una probabilidad por tick es un hiperparámetro oculto ligado al
tamaño del pulso. Si "20% por tick" con ticks de 1 minuto, la probabilidad de
no actuar en una hora es `0.8^60 ≈ 0` — la baja probabilidad se amortiza con
la cantidad de intentos. Cambiar el tick de 1 a 5 minutos cambia toda la
conducta sin tocar la ecuación.

## La corrección

La activación se modela como **tasa de riesgo por unidad de tiempo**
(proceso de Poisson):

```
p_tick = 1 − e^(−h·Δt)        h en activaciones por unidad de tiempo
```

`fuzzy.activation_probability(h, dt)` — invariante a Δt por construcción:
`P(no activar en T) = e^(−h·T)` para cualquier subdivisión del pulso.

Y da **procedencia gratis**: la espera media hasta actuar es `1/h`. En vez de
elegir una probabilidad abstracta se contesta una pregunta del dominio:
*en ámbar, ¿cuánto quiero que tarde en actuar, en promedio?* Si son 20
minutos, `h = 3`/hora.

## De dónde sale h

`fuzzy.activation_hazard(pressure, has_demand, pending_labels)`:

```
h = h_pressure·p + h_demand·𝟙{demanda} + h_backlog·(tareas pendientes)
```

- `p` es la presión del drive — la misma señal `max(nivel, ritmo, autónoma)`
  que la EPA ya computa. En equilibrio `p ≈ 0` → `h ≈ 0` → el agente descansa.
- Demanda pendiente suma `h_demand` (default 4/unidad → espera media ≈ 0.25
  unidades — respuesta casi inmediata).
- Backlog de tareas planificadas suma `h_backlog` c/u.

Parámetros del agente: `activation_h_pressure`, `activation_h_demand`,
`activation_h_backlog`, `activation_refractory`.

## División de responsabilidades

| Componente | Decide |
|---|---|
| Gate de riesgo (`1−e^(−hΔt)`) | **si** actuar este tick |
| Softmax AAH-A2 | **qué** acción (condicionada a actuar: `idle` sale del conjunto) |
| Estado ACTIVE | **compromiso** — la acción en curso no se re-sortea |
| Refractario | **dead-time** post-acción (`activation_refractory` unidades) — sin ráfagas |

El refractario se fija en `_on_action_complete` (tiempo `t·Δt + refractory`);
mientras `t·Δt < _refractory_until` el gate no puede disparar, ni siquiera con
demanda encolada.

## Pregunta de diseño evaluada: ¿hace falta la aleatoriedad?

Con muestreo probabilístico + histéresis + refractario + compromiso, ¿la
aleatoriedad aporta algo, o alcanza umbral determinista más refractario?

**Evaluación:** se conserva el sorteo, pero la pregunta queda abierta como
ablación barata. Argumentos a favor de mantenerla:

- El gate sigue necesitando *un* sorteo (la tasa es continua, el tick es
  discreto) — la aleatoriedad está en el modelo, no en un adorno.
- El softmax desempata acciones con logits cercanos sin introducir régimen
  periódico: un argmax + refractario produce lock-step (todos los agentes
  actúan en fase) y hace la conducta frágil a la discretización.
- El RNG está sembrado: la reproducibilidad no se pierde.

Contra: en esperanza, argmax+refractario+histéresis produce trayectorias casi
idénticas — la varianza solo agrega heterogeneidad entre agentes. Si se quiere
cerrar la pregunta: correr la ablación `hazard gate + argmax` vs `hazard gate +
softmax` sobre los mismos dos escenarios y comparar varianza de KPIs. Es un
brazo de ablación, no una decisión tomada.

## Verificación

`tests/test_activation_rate.py`:
- `P(no activar en 1h) = e^(−3)` exacta para Δt ∈ {1, 0.5, 0.25, 0.1, 1/60}.
- Espera media `1/p` consistente con `1/(1−e^(−h))`.
- Refractario bloquea re-activación con demanda encolada.
- Distribución condicionada a actuar (sin `idle`).

## Bug colateral encontrado y corregido

`drive.pressure` solo se poblaba desde variables observadas
(`_poll_observed`): sin sensores cableados quedaba `None` para siempre, y la
fuente autónoma `|d|/|L−x*| + η|v|/v_ref` **nunca** entraba en el escalar —
contradiciendo la spec `p = max(nivel, ritmo, autónoma)`. Ahora `update()`
pliega las tres fuentes siempre.
