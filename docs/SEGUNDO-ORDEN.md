# Cuándo un problema pide regulación de segundo orden

Sirve para diseñar experimentos: antes de comparar un agente regulado por sus necesidades contra
el mismo agente regulado por sus sensores, hay que saber si el problema tiene algo que el segundo
orden pueda leer. Si no lo tiene, el empate es el resultado esperado y no dice nada de la EPA.

## Vocabulario

- **Primer orden.** Un sensor lee una variable observada del mundo y emite un evento cuando cruza
  una zona del contrato, en nivel o en ritmo. Es una foto: valor, zona y pendiente de ahora.
- **Segundo orden.** Una necesidad escucha a varios sensores de primer orden, agrega sus eventos
  en el tiempo y les da significado respecto de la viabilidad del agente.

## Paso 1: que sea un problema de regulación

Las cuatro condiciones de un problema de autorregulación (paper Blue Sky, AAMAS 2027):

1. Hay variables que mantener en un rango viable por tiempo indefinido, y mantenerlas es el
   objetivo, no un paso hacia una recompensa final.
2. Hay tensiones que no se resuelven de una vez: lo que empuja a trabajar y lo que tira a
   preservarse gastan los mismos recursos finitos. Por eso hace falta al menos una necesidad de
   empuje y una de arrastre.
3. La información para actuar es más barata y más rápida adentro del agente, local y privada, que
   afuera.
4. Las variables responden a la acción y a la negligencia de forma no lineal y con incertidumbre.

Si no se cumplen, no hace falta regular: alcanza con optimizar.

## Paso 2: que la regulación tenga que ser de segundo orden

Además de las cuatro, tiene que cumplirse al menos una de estas. Si no se cumple ninguna, una
regulación de primer orden alcanza.

| | Condición | Qué quiere decir | Ejemplo |
|---|---|---|---|
| S1 | **Agregación N:1** | Lo que hay que mantener viable no lo mide un solo sensor: varias variables observadas hablan de la misma necesidad | El costo de operar se reparte en dólares de API, tokens, memoria y tiempo; ninguno solo dice si el agente puede seguir |
| S2 | **Variable inobservable** | La condición que importa no la lee ningún sensor y hay que inferirla de varios | «La casa está ocupada» no la mide nadie: se infiere de movimiento, agua y puertas |
| S3 | **Ambigüedad de causa** | La misma lectura de primer orden tiene más de una causa posible, y cada causa pide otra respuesta | La precisión cae por deriva (sirve refrescar) o por un cambio en la entrada (refrescar no sirve) |
| S4 | **La historia informa** | Duración, conteo, secuencia o frecuencia de los eventos predicen algo que la lectura de ahora no predice | Tres caídas en una hora con intervalos que se acortan anuncian otra cosa que una caída aislada |
| S5 | **Ruido** | Las detecciones de primer orden dan falsos positivos, y combinarlas da una señal más estable que cualquiera sola | Un sensor que vibra en un borde de zona |
| S6 | **Efecto de las propias acciones** | Saber si la última acción sirvió cambia cuál conviene ahora | Tres refrescos seguidos sin efecto medido |

Lo que agrega el segundo orden, cuando alguna se cumple, es contexto que no está en ningún sensor
por separado: **estado** (una conjunción de detecciones), **conteo** y **duración** (las tres
clases de Laput, Zhang y Harrison, CHI 2017), **tendencia**, y **significado**: qué quiere decir
esa combinación para la viabilidad del agente. En química analítica el mismo salto tiene nombre,
la «ventaja de segundo orden»: con una matriz de datos por muestra se puede cuantificar aunque
haya un interferente que no estaba en la calibración; con un vector se lo detecta, pero no se
puede analizar (Booksh y Kowalski, 1994).

Tiene costo: los errores de conteo se acumulan, una señal derivada amplifica el ruido de las que
combina, y más variables por necesidad son más contrato que calibrar.

## Paso 3: comprobarlo antes de gastar en un experimento

Las condiciones S2, S3, S4 y S6 se pueden medir sin LLM, con una **prueba de información**:

1. Simular jornadas con una política al azar.
2. En cada momento de decisión, predecir lo que importa (¿esta acción va a servir?, ¿la variable
   va a empeorar pronto?) con tres juegos de lecturas: las de primer orden de ese instante; esas
   más las de segundo orden; y esas más el estado oculto real del entorno, que ningún sensor ve.
3. Validar en semillas que el predictor no vio.

Lectura del resultado:

- **El estado oculto no predice más que el primer orden.** No hay nada escondido que saber. El
  problema no cumple S2, S3, S4 ni S6, y ningún sensado, de ningún orden, puede agregar
  información. Un empate entre primer y segundo orden es lo esperable.
- **El estado oculto predice más, y el segundo orden recupera parte.** Hay con qué: vale el
  experimento con LLM.
- **El estado oculto predice más y el segundo orden no.** Hay información, pero las lecturas de
  segundo orden elegidas no la capturan: falta diseñarlas.

La prueba mide información, no si a un LLM le sirve recibirla ya integrada. Eso se mide aparte.

## Caso: el reservorio de rc-gamma (17/11/2026)

Cumple las cuatro condiciones de regulación. No cumple las de segundo orden: una sola causa de
caída (la deriva de los memristores), una sola acción que sirve (refrescar) y un estado que se
resume en la precisión de ahora.

| Qué se predice | Primer orden | Más segundo orden | Más estado oculto |
|---|---|---|---|
| Cuánto sube la precisión con este refresco (R²) | 0,427 | 0,405 | 0,429 |
| Si la precisión cae a una zona peor en 30 min (AUC) | 0,852 | 0,846 | 0,851 |

80 jornadas, 1.598 refrescos, 3.600 instantes (`informacion.py` en rc-gamma). Con DeepSeek, darle
al agente la lectura de segundo orden ya integrada tampoco cambió la aptitud (8 semillas: +1,3 ±
2,4 a carga nominal y −3,0 ± 1,9 con calor). En ese entorno la EPA v2 queda primera en aptitud
sin diferencia significativa contra el primer orden, y es lo que estas condiciones anticipan.
