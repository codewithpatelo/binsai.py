# Los axiomas de la EPA

Esto es el canon. Cualquier cosa en binsai que lo contradiga es un bug en
binsai, no una variante. Cada axioma dice qué prohíbe, porque un axioma que no
prohíbe nada no restringe ninguna implementación.

**Vocabulario.** Una **necesidad** es lo que el código llama `Drive`. Su
**punto de equilibrio** es `set_point`. Su **desvío** es la distancia del valor
de la necesidad a su punto de equilibrio. El **error homeostático** es ese
desvío normalizado por el margen hasta el límite de viabilidad.

---

## A1 — Autonomía

La política del agente depende de su estado interno. No es una función del
estímulo: el mismo estímulo con otro estado de las necesidades produce otra
conducta, y el mismo estado sin estímulo puede producir conducta.

**Prohíbe.** Que una condición del mundo se compile en una acción —
`if (zona == roja) ejecutar(accion)`. El catálogo describe acciones; elegir es
del agente.

---

## A2 — Impulso

La probabilidad de activación (o de inhibición) es **proporcional al desvío de
la necesidad respecto de su punto de equilibrio**: el error homeostático, y nada
más. Se modela como tasa de riesgo, `p_pulso = 1 − e^(−h·Δt)`, para que no
dependa del tamaño del pulso.

**Prohíbe.** Que la tasa mire la presión de las variables observadas, el nivel
de un sensor, o cualquier señal que no sea el desvío de la necesidad. Una
variable saturada —un techo ya cruzado, un piso ya tocado— no puede fijar la
tasa de activación en su máximo mientras la necesidad está en su punto de
equilibrio. El mundo entra a la necesidad por sus eventos de perturbación;
nunca por la tasa.

### A2.1 — Agregación por acoplamiento

Sin acoplamiento, cada necesidad puede activar al agente por su cuenta: la
señal del sistema es el máximo de los desvíos, y una necesidad no se diluye
porque las demás estén tranquilas.

Con acoplamiento, la agregación es ponderada por la matriz `W`: el desvío de
una necesidad acoplada entra al impulso de la otra con el peso que `W` declara,
y con el retardo que declare.

**Prohíbe.** Promediar las necesidades. Un promedio con una necesidad muerta y
otra en equilibrio da media presión y el agente descansa junto al cadáver. Si
una fuente no está calibrada se excluye de la agregación y se reporta; no entra
como cero.

### A2.2 — Histéresis

Un cruce de banda tiene umbrales distintos de entrada y de salida (`α_in`,
`α_out`). Entrar a una banda peor es inmediato —el dolor no se demora—; salir
exige que la pertenencia caiga por debajo del umbral de salida.

La histéresis es sobre la **banda**, no sobre el tiempo: no es un temporizador,
es un deadband. Su ancho es una fracción de la banda, así que no tiene unidades
propias y la misma calibración sirve a cualquier escala.

**Prohíbe.** Que una necesidad o una variable que oscila alrededor de un corte
emita un evento por muestra. Un sensor que vibra en un borde no está
perturbando al agente: está haciendo ruido, y un agente que tiene que cerrar
cada vibración no tiene presupuesto para regular.

---

## A3 — Corrección

La calidad de una acción es la reducción de **la perturbación que la generó**,
medida sobre la variable observada **en la dimensión perturbada**, por su vuelta
a la zona estable. Ese grado es `g`, y es el release de la envolvente.

La reducción del error homeostático de la necesidad **no** es `g`. Se observa en
la fase `Observe` del bucle cognitivo, como señal de aprendizaje.

**Prohíbe.** Que un evento se libere sin una acción de calidad medida. El mundo
aflojando no libera: si la variable vuelve sola, la condición desapareció pero
el agente no se lleva crédito, y `g` queda en cero. Prohíbe también medir `g`
en el mismo pulso de la acción: el mundo necesita su tiempo de respuesta, que
la variable declara. Y prohíbe que una acción cierre eventos que no atendió:
el evento lo abrió el cruce de una variable concreta, y lo cierra que esa
variable vuelva.

---

## A4 — Negligencia basal

La dinámica basal sola —deriva más resorte más fatiga, con `u = 0`— mata dentro
del horizonte. No hay reposo permanente: con fatiga, el equilibrio *es* el
límite de viabilidad. Calibrar es elegir la fecha de esa muerte.

**Prohíbe.** Que un agente que no hace nada sobreviva su ventana. Una necesidad
cuya negligencia basal no mata no genera presión y vuelve decorativa toda la
ecuación. Prohíbe también que cruzar un límite de viabilidad sea un tope: se
cruza, y ahí se muere.

### A4.1 — Viabilidad conjuntiva

La primera necesidad que cruza su límite mata al agente. No hay una necesidad
que siga viva después de que otra cruzó.

---

## A5 — Holgura agéntica

Tiene que existir un régimen de operación donde el agente actúe, se equivoque
una fracción de las veces, y aun así llegue al final de la ventana. La holgura
es el ancho de ese régimen.

**Prohíbe.** Que el tiempo de vida sea monótono decreciente en la acción. Si
toda acción acorta la noche, el agente sólo puede elegir morir antes y la
ecuación no gobierna nada. Exige por lo tanto un canal por el que una acción de
calidad pague —no sólo cerrar eventos, cuyo total está acotado, sino descontar
de la deriva, que no lo está.

---

## A6 — Equilibrio perfecto

En el punto de equilibrio el desvío es cero y, con él, la probabilidad de
activación o inhibición. **El equilibrio perfecto es por lo tanto indeseado**:
un agente exactamente en su punto de equilibrio no tiene impulso para nada.

**Prohíbe.** Calibrar hacia el reposo. El objetivo no es llevar el desvío a cero
sino mantenerlo dentro de la zona viable, con el desvío suficiente para que haya
conducta.

---

## A7 — Holgura basal · BORRADOR, no cerrado

Una necesidad en **superávit** tiene recursos por encima de su punto de
equilibrio que la ventana no va a devolver. Dejarlos sin usar es una pérdida, y
la pérdida tiene que generar impulso igual que la falta.

**Prohíbe (lo que sí está claro).** Que el impulso sea asimétrico: si la tasa
sale de `|desvío|`, el superávit activa igual que el déficit, y una
implementación que sólo mire el hemisferio de déficit rompe A2. Prohíbe también
tratar «no consumir» como seguro por defecto: con la ventana corriendo, no
consumir un recurso perecedero es una decisión, no la ausencia de una.

**Lo que no tengo cerrado, y lo marco en vez de inventarlo.**

1. **La condición de perecibilidad.** La pérdida existe sólo si el superávit no
   sobrevive la ventana. El presupuesto de una noche no se acumula; horas de
   máquina ociosas no se guardan. Pero un recurso que sí se acumula no genera
   esta presión, y entonces A7 no es universal sino que depende de una propiedad
   que el contrato tendría que declarar por variable: *¿esto se pierde al cerrar
   la ventana?*

2. **Qué es el superávit fuera del metabolismo.** En metabólico es obvio: RAM
   libre, disco libre, presupuesto sin gastar. En servicio, un superávit es ir
   adelantado del ritmo comprometido — y ahí no está claro que la presión sea a
   «usar más», porque el contrato declara un techo (`maxPrsPerNight`). Puede que
   en una necesidad de empuje el superávit pida consumir y en una de arrastre
   pida frenar, que es lo que `docs/EPA.md` ya dice sobre inhibición. Si es así,
   A7 no es un axioma nuevo sino A2 leído en el hemisferio de superávit, más una
   regla sobre **qué** hacer ahí, que es del agente y no de la ecuación.

3. **La formulación que más me cierra, y no la doy por buena.** Con necesidades
   antagónicas, el superávit de una es el presupuesto para reducir el déficit de
   la otra: el metabólico con recursos de sobra es la capacidad de trabajar que
   el servicio necesita. Formulado así, A7 no agrega un impulso nuevo sino que
   dice **hacia dónde** apunta el impulso que A2 ya genera, y conecta
   directamente con A5: esa conversión *es* la holgura agéntica. Lo que falta
   para cerrarlo es si vale sin antagonismo — con una sola necesidad, ¿hacia
   dónde apunta el superávit?

Hasta que esas tres estén resueltas, A7 queda como borrador y nada en binsai
depende de él.

---

## Qué toca el valor de una necesidad

Tres cosas, y ninguna más:

1. **Dinámica basal** — deriva basal y resorte magnético con su fatiga.
2. **Perturbaciones** — envolventes ADS, derivadas de los eventos que emiten
   las variables observadas al cruzar un umbral algedónico.
3. **Correcciones** — acciones del agente que satisfacen A3, cuya consecuencia
   observada devuelve la variable que emitió la perturbación a su zona estable.

Las variables observadas **no escriben el valor de la necesidad** y **no entran
en su tasa de activación**. Entran sólo por sus eventos. Una necesidad cuyo
valor sea una función directa de un sensor —`punto_de_equilibrio + nivel`, por
ejemplo— no es una necesidad: es el sensor con otro nombre, y no tiene dinámica
que calibrar.

---

## Qué reporta una variable observada

Dos dimensiones: **nivel** y **ritmo**. En cada una emite un evento cuando cruza
un umbral algedónico declarado en el contrato.

Los umbrales son **niveles en las unidades de la variable**, no fracciones ni
cocientes:

```yaml
usd_gastado:
  nivel_verde:    5
  nivel_amarillo: 10
  nivel_ambar:    25
  nivel_rojo:     50
  nivel_muerte:   null        # opcional: valor exacto que no se puede pasar
```

La aritmética que produce esos niveles es del autor del contrato. Si el
presupuesto depende de cuántos tickets se comprometieron, el contrato los
calcula:

```yaml
usd_gastado:
  nivel_rojo:  "50 * n_tickets_comprometidos"
  nivel_ambar: "25 * n_tickets_comprometidos"
```

**Prohíbe.** Que la necesidad o la variable observada hagan esa aritmética. La
variable mira `nivel_rojo` y compara; de dónde salió ese número no es asunto
suyo. Un `gasto/techo` calculado dentro de la variable mezcla dos
responsabilidades y vuelve imposible declarar un contrato dinámico sin tocar el
código.

**Consecuencia de llegar al rojo.** Si una variable alcanza su `nivel_rojo`, la
intensidad de la perturbación que emite tiene que llevar a la muerte — o el
contrato declara `nivel_muerte` y ahí no hay ambigüedad. Un rojo del que se
vuelve solo no era rojo.

---

## El ciclo cognitivo y la corrección

Lo que sigue salió de reconstruir la noche del 13/10 escenario por escenario
hasta que la EPA se sostuvo sin empujarla. No es una recomendación: es lo que
quedó cuando se sacó todo lo que estaba puesto a mano.

### C1 — Qué cura una necesidad

Una sola cosa: **correcciones**. Y una corrección es un **zone pass de la
variable observada hacia el punto de equilibrio**, causado por una acción.

Su magnitud es la misma escala que la del ataque equivalente —`ι(severidad del
cruce) · distancia de viabilidad`— con el signo invertido, y entra con la forma
del release.

**Prohíbe.** Que la corrección sea un factor que escala el evento abierto. `g`
no cura: `g` cierra. Lo que mueve el valor de la necesidad es un desplazamiento
propio, simétrico al golpe. Prohíbe también que una corrección exista sin una
acción que la haya causado: un cruce hacia el equilibrio que nadie provocó es el
mundo curándose solo, y eso ya lo prohíbe A3.

### C2 — Un zone pass es discreto

La **consecuencia exitosa** de una acción —la que cumple A3— es un zone pass, y
un zone pass cruza **una banda**: rojo→ámbar, ámbar→amarillo, amarillo→verde.
Para llegar a verde desde rojo hacen falta tres acciones exitosas, cada una con
su release.

**Prohíbe.** Que una acción lleve la necesidad de donde esté hasta verde de un
saque. Eso no es un zone pass, es teletransporte.

### C3 — Qué apaga el bucle cognitivo

Correcciones que lleven la **necesidad** a su zona verde. Nada más.

**Prohíbe.** Un breaker por iteraciones. Un cierre porque la variable observada
volvió mientras la necesidad sigue en ámbar —restaurar la variable es la
prioridad, no el criterio de cierre—. Y descartar un wake por no encontrar una
perturbación abierta: el micro-objetivo es la necesidad, que puede estar lejos
de su punto de equilibrio por pura deriva, y eso también hay que atenderlo.

### C4 — La dinámica basal se pausa

La basal es lo que le pasa a la necesidad cuando **no** hay perturbación ni
acción. Mientras transcurre el ADSR de un evento, o mientras hay un bucle
cognitivo abierto sobre esa necesidad, la basal no corre: ni deriva, ni resorte,
ni carga alostática, y la velocidad queda congelada donde estaba, así que al
reanudar sigue de ahí y no desde cero.

**Prohíbe.** Colgar la pausa de que el evento siga *abierto*. El sustain no es
el evento transcurriendo: es el desplazamiento que quedó, y puede quedar para
siempre si nadie corrige. Una perturbación sin cerrar congelaría la necesidad
hasta el final de la ventana, y la noche sobreviviría por estar en pausa.

### C5 — La curva del portón

`h = tasa_base · e^(ganancia · p)`, con la ganancia despejada de una condición
sobre las bandas, no elegida: **en el borde ámbar→rojo despertar tiene que ser
casi seguro**. Con `p = amberMax`, `P(despertar en un pulso) ≈ 0,99`.

Para las bandas del contrato del 13/10 (`greenMax 0,33`, `yellowMax 0,55`,
`amberMax 0,80`) y `tasa_base = 0,25/h`, eso da **ganancia 8,76** y la curva:

| p | tasa | P(despertar en 1 min) |
|---|---|---|
| 0,00 | 0,2/h | 0,4 % |
| 0,33 | 4,5/h | 7,2 % |
| 0,55 | 30,9/h | 40,3 % |
| 0,80 | 276,3/h | 99,0 % |
| 1,00 | 1593,2/h | 100 % |

Así A2 sigue siendo probabilístico —la urgencia ordena y prioriza, que es lo que
un disparo determinista pierde— y a la vez es casi determinista donde importa.

**Prohíbe.** Un tope de tasa que vuelva la condición inalcanzable. Y una rama de
TTD que infle la tasa en todos lados: medida sobre una ventana real domina el
100 % de los pulsos, el agente quiere despertar siempre, y lo que termina
espaciando las activaciones es el refractario. La figura se ve bien por el
motivo equivocado.
