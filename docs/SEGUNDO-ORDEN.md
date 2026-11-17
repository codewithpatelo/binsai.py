# ¿Este problema necesita regulación de segundo orden?

## Para qué sirve este documento

Para decidir, **antes de diseñar un experimento**, si tiene sentido comparar un agente regulado
por sus necesidades (segundo orden) contra el mismo agente regulado por sus sensores (primer
orden).

La razón: si el problema no tiene nada que el segundo orden pueda aprovechar, los dos agentes
empatan. Ese empate no dice nada sobre la EPA; dice que se eligió mal el problema. Este
documento evita gastar en ese experimento.

## Las dos cosas que se comparan

| | Qué es | Qué sabe |
|---|---|---|
| **Primer orden** | Un sensor mira una variable del mundo y avisa cuando cruza una zona | Lo de este instante: valor, zona y pendiente de **una** variable |
| **Segundo orden** | Una necesidad escucha a **varios** sensores y junta lo que avisan a lo largo del tiempo | Lo que ningún sensor dice solo: qué pasó junto, cuántas veces, hace cuánto, y qué significa para seguir vivo |

## La regla

Un problema necesita regulación de segundo orden si cumple **las dos partes**:

- **Parte A:** es un problema de regulación (las cuatro condiciones).
- **Parte B:** juntar señales aporta algo que una señal sola no aporta (al menos una de las seis
  preguntas se responde que sí).

Si cumple A y no cumple B, alcanza con primer orden.

## Parte A: ¿es un problema de regulación?

Tienen que cumplirse las cuatro (paper Blue Sky, AAMAS 2027). Si no, alcanza con optimizar.

1. **Sin meta final.** Hay variables que mantener en un rango viable por tiempo indefinido, y
   mantenerlas es el objetivo.
2. **Tensiones que no se resuelven.** Lo que empuja a trabajar y lo que tira a preservarse gastan
   los mismos recursos.
3. **Información local y privada.** Lo que hace falta saber para actuar se consigue más barato y
   más rápido adentro del agente que afuera.
4. **Respuesta no lineal e incierta.** Las variables no responden de forma proporcional ni segura
   a la acción ni a la negligencia.

## Parte B: ¿juntar señales aporta algo?

Seis preguntas. Cada una dice por qué, si la respuesta es sí, un sensor solo no alcanza.

**B1. ¿Lo que hay que cuidar lo miden varios sensores a la vez?**
Si sí, ningún sensor solo dice cómo está: hay que agregarlos (N sensores, una necesidad).
*Ejemplo:* el costo de operar se reparte en dólares de API, tokens, memoria y tiempo.

**B2. ¿Lo que importa no lo mide ningún sensor?**
Si sí, hay que inferirlo combinando los que hay.
*Ejemplo:* ningún sensor mide «la casa está ocupada»; se deduce de movimiento, agua y puertas.

**B3. ¿La misma lectura puede tener causas distintas que piden respuestas distintas?**
Si sí, un sensor solo no permite elegir la respuesta: hay que mirar qué más pasó.
*Ejemplo:* la precisión cae por deriva (sirve refrescar) o por un cambio en la entrada (no sirve).

**B4. ¿Lo que pasó antes predice algo que la lectura de ahora no predice?**
Si sí, hace falta memoria de los eventos: cuántos, cada cuánto, hace cuánto.
*Ejemplo:* tres caídas en una hora, cada vez más seguidas, anuncian otra cosa que una caída sola.

**B5. ¿Los sensores dan falsas alarmas?**
Si sí, combinar varios da una señal más confiable que cualquiera sola.
*Ejemplo:* un sensor que vibra en el borde de una zona.

**B6. ¿Saber si la última acción sirvió cambia cuál conviene ahora?**
Si sí, hay que llevar la cuenta del efecto de las propias acciones.
*Ejemplo:* tres refrescos seguidos sin efecto medido piden probar otra cosa.

## Cómo comprobar la Parte B sin gastar en un LLM

B2, B3, B4 y B6 se pueden medir con una **prueba de información**:

1. Simular jornadas con una política al azar.
2. En cada momento de decisión, intentar predecir lo que importa (¿esta acción va a servir?, ¿la
   variable va a empeorar pronto?) de tres maneras:
   - (a) sólo con las lecturas de primer orden de ese instante;
   - (b) agregando lecturas de segundo orden (conteos, duraciones, conjunciones);
   - (c) agregando el estado real del entorno, el que ningún sensor ve.
3. Comparar qué tan bien predice cada una, en semillas que no se usaron para ajustar.

| Resultado | Qué significa | Qué hacer |
|---|---|---|
| (c) no predice mejor que (a) | No hay nada escondido que saber. La Parte B no se cumple | No correr el experimento: va a dar empate |
| (c) predice mejor, y (b) también | Hay información y el segundo orden la captura | Correr el experimento con LLM |
| (c) predice mejor, y (b) no | Hay información, pero las lecturas de segundo orden elegidas no la capturan | Rediseñar esas lecturas |

Límite: la prueba mide si hay información, no si a un LLM le sirve recibirla ya procesada. Eso se
mide aparte, con pocas semillas.

## Caso resuelto: el reservorio de rc-gamma (17/11/2026)

**Parte A: sí.** Cumple las cuatro.

**Parte B: no.** Hay una sola causa de caída (la deriva de los memristores), una sola acción que
sirve (refrescar), y todo el estado se resume en la precisión de ahora.

| Qué se predice | (a) Primer orden | (b) Más segundo orden | (c) Más estado oculto |
|---|---|---|---|
| Cuánto sube la precisión con este refresco (R²) | 0,427 | 0,405 | 0,429 |
| Si la precisión cae a una zona peor en 30 min (AUC) | 0,852 | 0,846 | 0,851 |

(c) no predice mejor que (a): primera fila de la tabla de resultados. Con DeepSeek se confirmó:
darle al agente la lectura de segundo orden no cambió su aptitud (+1,3 ± 2,4 a carga nominal y
−3,0 ± 1,9 con calor, 8 semillas).

Por eso en ese entorno la EPA v2 y el primer orden empatan, y es lo que esta regla anticipa.
Datos: 80 jornadas, 1.598 refrescos, 3.600 instantes (`informacion.py` en rc-gamma).

## Fuentes

- Las tres clases de lectura de segundo orden (estado, conteo, duración): Laput, Zhang y
  Harrison, *Synthetic Sensors*, CHI 2017.
- Que más dimensiones por muestra permiten separar causas no calibradas (la «ventaja de segundo
  orden»): Booksh y Kowalski, *Theory of Analytical Chemistry*, 1994.
