# Hallazgo — los defaults que descartan mienten con naturalidad

*(Meta-hallazgo sobre el proceso, no sobre el resorte. Tercer caso de la
misma forma de falla en esta línea.)*

## La forma de falla

Tres incidentes, un mismo patrón:

1. **El techo que no se aplicaba**: un cap de gasto que no actuaba cuando no
   podía leer el consumo — el sistema seguía reportando "dentro de
   presupuesto" con datos incompletos.
2. **El contador que sumaba snapshots**: un acumulador que trataba lecturas
   del estado total como gasto nuevo — cifras infladas, plausibles, falsas.
3. **El buffer que recortaba historia** (`Drive._history` → últimos 500
   ticks): la figura de ablación renderizó solo el tramo final y el magnet
   pareció arrancar de una condición inicial distinta — una comparación
   contaminada sin que nada fallara.

Lo que los une: **no fallan, mienten con naturalidad.** Ninguno rompe, lanza
excepción ni deja la pantalla en rojo. Cada uno devuelve un valor plausible
que contamina la evidencia que lo usa.

Y los tres se detectaron del mismo modo: **mirando un gráfico, no corriendo
tests.** El test suite estaba verde en los tres casos — porque el mecanismo
funcionaba; lo que estaba mal era lo que el mecanismo *afirmaba* sobre los
datos.

## El principio

En un sistema de medición — y esta librería ES un sistema de medición del
comportamiento de agentes — **todo valor por defecto que descarta, redondea o
acota datos tiene que ser explícito y quedar registrado cuando actúa.**

Consecuencias adoptadas en el código:

- `Drive.history_limit`: default `0` = retener todo (antes 500, silencioso).
  Cuando un límite explícito actúa, `drive.history_dropped` cuenta los ticks
  descartados y se emite un `warnings.warn` la primera vez.
- `Drives` coupling con `coupling_tau`: si τ excede la historia retenida del
  drive fuente, el delay ya no cae en silencio al valor actual — advierte
  una vez por drive.
- `ObservedVariable._samples` (deque `maxlen=10000`): cuenta evicciones en
  `samples_dropped` y advierte la primera — las estimaciones de ritmo en
  ventanas largas quedan señaladas como windowed, no full-run.
- `ACLMessageBus.sent` (cap de 200 mensajes): cuenta descartes en
  `sent_dropped` y advierte la primera vez.

Excepción declarada: los `maxlen` de `agent.py` (working memory, etiquetas de
tareas) son **límites cognitivos intencionales del modelo**, no estructuras de
medición — un buffer de memoria de trabajo acotado modela algo real. La regla
aplica a instrumentos de medición y evidencia, no a límites que son parte del
fenómeno simulado (una memoria de trabajo acotada *es* el modelo; una historia
de trayectoria truncada no es el modelo, es evidencia incompleta).

## Por qué importa para la línea

La tesis del proyecto es que un agente regula variables operativas. Si la
*evidencia* de esa regulación se genera con instrumentos que descartan en
silencio, cualquier conclusión — incluido el hallazgo del resorte — descansa
sobre arena. La regla del buffer es la regla del termómetro: un instrumento
que redondea, acota o descarta sin registrar está decorando, no midiendo.

Regla operativa para revisión: ante cualquier contenedor con límite,
preguntar **"¿qué pasa cuando se llena, y quién se entera?"**
