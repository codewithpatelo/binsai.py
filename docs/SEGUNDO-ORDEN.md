# Problema regulatorio de segundo orden

## Definición

Una señal de **primer orden** es un dato crudo: lo que mide un sensor, tal cual. El costo de una
acción, una paga, una lectura de precisión.

El **segundo orden** es el significado que se construye sobre esos datos: en qué zona está, si
cruzó, cuántas veces, hace cuánto, qué coincidió con qué. Eso no lo emite ningún sensor; lo
produce la necesidad que los escucha.

Un problema regulatorio es de segundo orden cuando la acción correcta no se puede decidir
mirando un dato crudo solo: hay que agrupar varios datos distintos y leerlos juntos.

## Condiciones

Las cuatro de todo problema regulatorio (paper Blue Sky, AAMAS 2027):

1. **Sin meta final.** Hay variables que mantener en un rango viable por tiempo indefinido.
2. **Tensiones que no se resuelven.** Trabajar y preservarse gastan los mismos recursos.
3. **Información local y privada.** Lo que hace falta saber para actuar está adentro del agente.
4. **Respuesta no lineal e incierta** a la acción y a la negligencia.

Y tres más, que lo hacen de segundo orden:

5. **Agregación (N:1).** Cada cosa que el agente tiene que mantener viable depende de varios
   datos crudos **distintos**, no de uno. Medir el mismo dato de varias maneras (un gasto, su
   suma y su promedio) no es N:1: es un dato.
   *Ejemplo: el costo de operar son dólares de API, tokens, memoria y tiempo.*

6. **Contexto.** Lo que define qué hacer está en cómo se combinan esos datos en el tiempo:
   cuáles coinciden (conjunción), cuántas veces (frecuencia), hace cuánto (duración) y hacia dónde
   van (tendencia).
   *Ejemplo: una caída de precisión aislada y tres caídas en una hora, cada vez más seguidas, son
   el mismo dato crudo y piden respuestas distintas.*

7. **Ambigüedad.** Un mismo dato crudo admite más de una lectura, cada lectura pide
   otra acción, y sólo el contexto permite elegir.
   *Ejemplo: la precisión cae. Si coincide con calor, es deriva y sirve refrescar. Si coincide con
   un cambio en la entrada, refrescar no sirve.*

Con las cuatro primeras alcanza una regulación de primer orden. Con las siete hace falta una de
segundo orden: una necesidad que agrupa las señales, les da contexto y resuelve la ambigüedad.

## Cómo se verifica en un entorno concreto

Con una prueba de información, sin LLM:

1. Simular jornadas con una política al azar.
2. En cada momento de decisión, predecir si la acción va a servir y si la variable va a empeorar,
   de tres maneras: (a) con los datos crudos de ese instante; (b) sumando su contexto
   (conjunción, frecuencia, duración, tendencia); (c) sumando el estado real del entorno, el que
   ningún sensor ve.
3. Comparar, en semillas que no se usaron para ajustar.

Si (b) predice mejor que (a), el entorno cumple las condiciones 6 y 7. Si ni (c) predice mejor
que (a), no las cumple: toda la información que existe ya está en el dato crudo.

## Caso: el reservorio de rc-gamma (17/11/2026)

Cumple las condiciones 1 a 4. No cumple 5, 6 ni 7: la precisión tiene una sola causa de caída (la
deriva de los memristores) y una sola acción que la corrige (refrescar).

| Qué se predice | (a) Primer orden | (b) Con contexto | (c) Con estado real |
|---|---|---|---|
| Cuánto sube la precisión con este refresco (R²) | 0,427 | 0,405 | 0,429 |
| Si la precisión cae a una zona peor en 30 min (AUC) | 0,852 | 0,846 | 0,851 |

80 jornadas, 1.598 refrescos, 3.600 instantes (`informacion.py` en rc-gamma). En ese entorno el
agente regulado por la EPA v2 y el regulado por sus sensores rinden igual (aptitud 86,0 y 85,0 a
carga nominal, 83,5 y 81,8 con calor, 30 semillas, sin diferencia significativa).

## Fuentes

- Estado, conteo y duración como lecturas de segundo orden: Laput, Zhang y Harrison, *Synthetic
  Sensors*, CHI 2017.
- Separar causas no calibradas con más dimensiones por muestra: Booksh y Kowalski, *Theory of
  Analytical Chemistry*, 1994.
