# Contrato de viabilidad — agent-operations-night-shift

La semántica del acuerdo, en prosa. Cada límite del JSON tiene acá la frase que
explica qué significa cruzarlo. Si un número no aparece explicado acá, el umbral
está mal puesto y hay que revisarlo.

## gasto_api — budget, 150 USD por ventana de 11.5 h

El agente trabaja la noche con un presupuesto de API de 150 USD. Cruzar el techo
antes de que cierre la ventana es una violación del contrato: el proveedor corta
o el humano paga de más. El ritmo sostenible se recalcula en cada pulso
(`restante / tiempo_restante`), así que el ámbar de ritmo significa "al ritmo
actual ya no llego a corregir a tiempo" — la corrección (bajar de modelo,
acortar contexto) tarda ~0.5 h medido, no elegido.

## ram_libre — floor, 2 GB de piso

Si la RAM libre toca 2 GB el sistema operativo empieza a swappear y el trabajo
en curso se degrada hasta ser inútil. El límite de viabilidad está por debajo
del umbral del contrato: el piso de 2 GB es lo acordado con el humano; la muerte
operativa (OOM kill) está cerca de 0. Limpiar cachés o matar procesos tarda
~15 min medido.

## entregas — target, 2 entregables aprobados en 8 h

El compromiso es terminar la ventana con 2 entregables aprobados. La violación
no es cruzar un límite sino llegar al cierre sin haber llegado. La presión de
nivel es la fracción restante; la presión de ritmo compara el ritmo observado
contra el requerido (`restante / tiempo_restante`).

## cola_pendientes — band, entre 0 y 20 tareas

La cola tiene que quedar dentro del rango: vacía está bien (no hay déficit de
trabajo), pero más de 20 pendientes es superávit de demanda — el agente aceptó
más de lo que puede procesar. Sin ventana de ritmo: solo presión de nivel.

## Reglas del contrato

1. **Límite de viabilidad ≠ umbral del contrato.** Cruzar el contrato es
   incumplir lo acordado; cruzar la viabilidad es muerte operativa. Habilitan
   acciones distintas (negociar vs. abortar).
2. **Nunca se asume verde.** Un sensor vencido o ausente marca la variable como
   inválida y emite `SensorInvalid`; no aporta presión pero tampoco tranquiliza.
3. **`T_recuperación` se mide, no se elige.** Cada tiempo de corrección de esta
   tabla salió de medir cuánto tarda la acción real en surtir efecto.
