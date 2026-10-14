# Los seis axiomas de la EPA

Esto es el canon. Cualquier cosa en binsai que lo contradiga es un bug en
binsai, no una variante. Cada axioma dice qué prohíbe, porque un axioma que no
prohíbe nada no restringe ninguna implementación.

---

## A1 — Autonomía

La política del agente depende de su estado interno. No es una función del
estímulo: el mismo estímulo con otro estado de los drives produce otra
conducta, y el mismo estado sin estímulo puede producir conducta.

**Prohíbe.** Que una condición del mundo se compile en una acción —
`if (zona == roja) ejecutar(accion)`. El catálogo describe acciones; elegir es
del agente.

---

## A2 — Impulso

La probabilidad de activación (o de inhibición) es **proporcional al desvío del
drive respecto de su set-point**: el error homeostático, y nada más. Se modela
como tasa de riesgo, `p_pulso = 1 − e^(−h·Δt)`, para que no dependa del tamaño
del pulso.

Sin acoplamiento, cada drive puede activar al agente por su cuenta. Con
acoplamiento, la agregación es ponderada por la matriz de acoplamiento.

**Prohíbe.** Que la tasa mire la presión de las variables observadas, el nivel
de un sensor, o cualquier señal que no sea el desvío del drive. Una variable
saturada —un techo ya cruzado, un piso ya tocado— no puede fijar la tasa de
activación en su máximo mientras el drive está en su punto de equilibrio. El
mundo entra al drive por sus eventos de perturbación; nunca por la tasa.

---

## A3 — Corrección

La calidad de una acción es la reducción de **la perturbación que la generó**,
medida sobre la variable observada **en la dimensión perturbada**, por su vuelta
a la zona estable. Ese grado es `g`, y es el release de la envolvente.

La reducción del error homeostático del drive **no** es `g`. Se observa en la
fase `Observe` del bucle cognitivo, como señal de aprendizaje.

**Prohíbe.** Que un evento se libere sin una acción de calidad medida. El mundo
aflojando no libera: si la variable vuelve sola, la condición desapareció pero
el agente no se lleva crédito, y `g` queda en cero. Prohíbe también medir `g`
en el mismo pulso de la acción: el mundo necesita su tiempo de respuesta, que
la variable declara.

---

## A4 — Negligencia basal

La dinámica basal sola —deriva más resorte más fatiga, con `u = 0`— mata dentro
del horizonte. No hay reposo permanente: con fatiga, el equilibrio *es* el
límite de viabilidad. Calibrar es elegir la fecha de esa muerte.

**Prohíbe.** Que un agente que no hace nada sobreviva su ventana. Un drive cuya
negligencia basal no mata no genera presión y vuelve decorativa toda la
ecuación. Prohíbe también que cruzar un límite de viabilidad sea un tope: se
cruza, y ahí se muere.

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
un agente exactamente en su set-point no tiene impulso para nada.

**Prohíbe.** Calibrar hacia el reposo. El objetivo no es llevar el desvío a
cero sino mantenerlo dentro de la zona viable, con el desvío suficiente para
que haya conducta.

---

## Qué toca el valor de un drive

Tres cosas, y ninguna más:

1. **Dinámica basal** — deriva basal y resorte magnético con su fatiga.
2. **Perturbaciones** — envolventes ADS, derivadas de los eventos que emiten
   las variables observadas al cruzar un umbral algedónico.
3. **Correcciones** — acciones del agente que satisfacen A3, cuya consecuencia
   observada devuelve la variable que emitió la perturbación a su zona estable.

Las variables observadas **no escriben el valor del drive** y **no entran en su
tasa de activación**. Entran sólo por sus eventos. Un drive cuyo valor sea una
función directa de un sensor —`setPoint + nivel`, por ejemplo— no es un drive:
es el sensor con otro nombre, y no tiene dinámica que calibrar.

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

**Prohíbe.** Que el drive o la variable observada hagan esa aritmética. La
variable mira `nivel_rojo` y compara; de dónde salió ese número no es asunto
suyo. Un `gasto/techo` calculado dentro de la variable mezcla dos
responsabilidades y vuelve imposible declarar un contrato dinámico sin tocar el
código.

**Consecuencia de llegar al rojo.** Si una variable alcanza su `nivel_rojo`, la
intensidad de la perturbación que emite tiene que llevar a la muerte — o el
contrato declara `nivel_muerte` y ahí no hay ambigüedad. Un rojo del que se
vuelve solo no era rojo.
