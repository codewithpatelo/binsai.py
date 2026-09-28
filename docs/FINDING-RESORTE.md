# Hallazgo: el término elástico de la EPA contradecía su propósito

Resumen para la línea de investigación (Binsai / Ecuación Proacción).
Detalle técnico completo en `docs/SPRING.md`.

---

## Contexto

La EPA (Ecuación Proacción) actualiza cada necesidad en cada pulso:

```
x(t+1) = x(t) + λ − κ(x − x*) + u + ΣW·φ
```

El término `−κ(x−x*)` se diseñó como "resorte elástico": atracción al set-point
que permite oscilación e impide el equilibrio perfecto.

## El problema detectado

**No era un resorte: era un amortiguador.**

Matemáticamente es relajación lineal de primer orden — una contracción
geométrica de razón `(1−κ)` que converge al punto fijo `x* + λ/κ` desde
cualquier estado inicial.

Consecuencias verificadas (λ=0.003, κ=0.05, x*=0.30 → reposo = 0.36):

- **La presión no puede acumularse autónomamente.** Bajo *negligencia basal*
  (sin acción ni estímulos), toda necesidad converge a un offset acotado por
  `λ/κ`. El hambre ignorada se estanca en déficit leve — para siempre.
- **Las zonas rojas eran ornamentales.** ZoneChanged, ViabilityBreached,
  interrupt_on_zone: nada podía dispararse por dinámica autónoma. Toda presión
  real debía venir de `u`, y κ además erosionaba `u` cada tick.
- **Disipaba tensión en vez de almacenarla.** Un resorte físico acumula
  energía potencial y oscila (segundo orden, inercia). El término implementado
  funcionaba como un threshold duro de desviación.
- **"No hacer nada" era seguro.** Contradice la premisa del modelo: una
  necesidad push abandonada debería escalar hacia la viabilidad, no
  estacionarse en zona segura.

## Iteración 1: resorte pulsátil (insuficiente)

Primera reformulación — oscilador de relajación: el desplazamiento carga
tensión `σ` (κ·d por tick) que libera un pulso al cruzar el umbral θ.
Producía las ondas buscadas pero **seguía acotado**: el techo es
`x* + λ/(κρ)` — la misma ley λ/κ con forma de onda. Mesa viva, pero segura.

## Iteración 2 (solución): resorte-imán — alcance finito

Un imán pierde agarre con la distancia; la homeostasis tiene *reach* limitado:

```
σ(t+1) = σ(t) + κ·(x−x*)·e^(−|x−x*|/w)    # grip máximo en |d|=w, decae después
x(t+1) = x(t) + λ + u + ΣW·φ − r(t)
r(t)   = ρ·σ   si |σ| ≥ θ,  0 si no       # liberación pulsátil
```

Surgen dos regímenes:

- **λ < κρw/e** (agarre vence a la deriva): atrapado oscilando bajo
  viabilidad — pero un shock `u` puede empujarlo fuera del alcance → cascada
  hasta la muerte. Homeostasis que aguanta hasta ser sobrepasada.
- **λ > κρw/e**: la deriva gana siempre → negligencia basal garantiza muerte.

`w=∞` degenera al pulsátil acotado: un solo mecanismo unifica todo.

## Por qué esto sí cumple el propósito

- σ **almacena** tensión (no la disipa) — literalmente un resorte cargándose
- La deriva predomina: λ actúa cada tick; el resorte muerde solo en pulsos
- Oscilación real: el período se acorta con la desviación (lucha acelerada)
- Nunca llega al set-point perfecto (liberaciones finitas)
- La negligencia basal **mata**: simulación verificada — cruza moderate →
  high → critical → viability breach (~105 ticks, λ=0.008, κ=0.04, w=0.25)
- Simétrico y parametrizable (κ, θ, ρ, w)

**Fundamento formal**: oscilador de relajación / integrate-and-fire —
mecanismo estándar, no aporte propio. Es la misma estructura que el gate del
paper de debate (la equidad emergía del reset tras el disparo): el resorte y
el gate pasan a ser el mismo mecanismo en dos lugares de la ecuación. La
pulsatilidad hormonal (insulina, GnRH) queda como analogía ilustrativa.

## La presión como suma trazable (implicación para la línea)

La deriva no duplica al sensor — un sistema que solo responde a estímulos es
reactivo. La presión total combina tres fuentes separadas:

- `level` — de la variable observada (dónde estás)
- `pace` — de la variable observada (a qué velocidad te degradás)
- `tension` — σ acumulada por la dinámica autónoma (hacia dónde tendés bajo
  negligencia basal)

A igual estado medido, un drive con tensión acumulada empuja más que uno
recién saciado. Y la deriva es lo que hace que la señal de saciedad `g`
importe: con deriva, actuar tiene que *descargar tensión acumulada*, no solo
mover una medición — el problema de saciedad y la dinámica autónoma son dos
caras de lo mismo.

## Implementación

binsai 0.3.0: `spring="pulsatile"` default (`spring_threshold`, `spring_release`,
`spring_reach`), `spring="linear"` como legacy para procesos saturantes y
baseline de ablación. Evento canónico `TensionReleased`; el artefacto de
trayectoria marca cada liberación y proyecta con la política configurada.

## Preguntas abiertas para la investigación

- ¿Defaults distintos por categoría? (push = alcance finito, pull = mesa
  oscilante)
- Resorte fatigable/alostásico: κ_eff decae bajo carga sostenida (McEwen) —
  escape por tiempo en vez de distancia
- Asimetría paramétrica (κ_in/κ_out, w_in/w_out) para necesidades con
  regulación desigual por lado
- Relación entre el régimen atrapado y la homeostasis "exitosa": ¿la mesa
  oscilante estable es el modelo correcto de regulación efectiva?

---

## Lectura interpretativa — acción como condición de permanencia

*(Sección interpretativa, no resultado experimental. Va marcada así a
propósito: es una lectura del hallazgo, no el hallazgo mismo.)*

Si la inacción lleva a la muerte operativa, un sistema que persiste
necesariamente actúa. La acción deja de ser una función añadida y pasa a ser
**condición de permanencia**. Y como el momento y la intensidad de la acción
dependen del estado interno, la política es función de ese estado: eso es lo
que el marco llama **albedrío delimitado** — el agente elige dentro de los
límites que su propia viabilidad impone.

Dos precisiones para que la lectura no sea teleológica ni exagerada:

- **No es que el sistema "quiera" persistir**: es que los que no actúan no
  persisten. Es un filtro, no un propósito. La selección opera sobre
  comportamiento, no sobre intención.
- **La negligencia muestra que actuar es NECESARIO para persistir, no que
  toda acción sea agencia.** Un termostato también actúa para no morir. Lo
  que agrega este marco es la deliberación: varias necesidades antagónicas,
  no fungibles y sin escala común. Cuando el conflicto no se reduce a un
  solo número, hay que decidir — y ahí aparece algo que sí merece el nombre
  de agencia delimitada.

Antecedentes a citar, para no presentarlo como nuevo:

- **Ashby**, ultraestabilidad (Design for a Brain, 1952): el sistema viable
  es el que mantiene variables esenciales dentro de límites — actuar es
  parte de esa definición, no un extra.
- **Varela**, autopoiesis y enacción: el sentido emerge de la precariedad
  del ser vivo — una entidad que no puede morir no tiene nada en juego.

Lo que podría ser aporte propio de esta línea no es la intuición — que es
vieja y buena — sino mostrarla como **consecuencia de un mecanismo
computable**: con esta ecuación y estos parámetros, la negligencia basal
mata, y eso es verificable en un artefacto, no declamado en un párrafo.
