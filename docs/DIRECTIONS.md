# Direcciones de trabajo — lazo 2 y aprendizaje

Dos líneas discutidas y anotadas como dirección. **Ninguna está
implementada.** Las anotamos con su antecedente formal y sus límites, para
que el diseño parta de lo ya demostrado y no lo reinvente.

## 1. Aprendizaje de g — qué acciones sirven de verdad

**La idea.** El agente percibe la reducción del error homeostático como
consecuencia de su acción, y con eso aprende qué acciones sirven. Ya tenemos
la señal: `g = Δ_observado / Δ_esperado` se registra por acción.

**Antecedente formal.** El aprendizaje por refuerzo homeostático de Keramati
y Gutkin (homeostatic reinforcement learning) muestra que, bajo ciertas
condiciones, maximizar recompensa y minimizar el error homeostático son
equivalentes si la recompensa se define como la reducción del desvío. La
intuición ya es un teorema — se cita como antecedente, no se presenta como
aporte.

**Por dónde empezar — NO por RL.** La versión barata y primera:

- Cada acción tiene un efecto esperado `α` por necesidad (hoy declarado).
- Cada vez que se ejecuta se mide `g` y se actualiza ese estimado con un
  promedio móvil.
- La selección usa efectos *aprendidos* en vez de declarados.

No necesita asignación de crédito, ataca el problema de saciedad
directamente (una acción que se ejecuta y no satisface expone su `g ≈ 0`), y
produce un dato valioso por sí solo: **qué acciones dicen que sirven y no
sirven** — la discrepancia declarado-vs-medido es información.

**Advertencia innegociable.** `g` tiene que medirse FUERA del agente. Si el
sistema puede influir en cómo se mide su propia saciedad, aprende a verse
satisfecho — es el mismo problema que un juez de calidad que fuera el propio
ejecutor. La medición de `Δ_observado` es instrumento, no percepción del
agente.

## 2. Mutación bajo estrés prolongado — ultraestabilidad

**La idea.** Un sistema que pasa mucho tiempo en ámbar podría cambiar su
propia estructura — set-points, dinámicas, umbrales — como un organismo bajo
estrés evolutivo sostenido.

**No es especulativo — el homeostato de Ashby hace exactamente eso.** Cuando
las variables esenciales salen del rango viable, el homeostato cambia sus
propios parámetros al azar hasta encontrar una configuración viable. Eso es
la ultraestabilidad, y es el segundo lazo que este proyecto ya anuncia en su
motivación.

Otros antecedentes a citar:

- **Alostasis (Sterling)** — el set-point se mueve por anticipación, no solo
  por daño.
- **Carga alostática (McEwen), forma completa** — la exposición crónica
  *cambia la estructura*, no solo desgasta. Nuestro `Λ` hoy solo fatiga el
  agarre; la forma completa reparametriza.
- **Mutagénesis inducida por estrés en bacterias** — la tasa de mutación
  *sube* bajo estrés prolongado. El estrés es señal y gatillo.
- **Metaplasticidad** — la plasticidad misma es plástica.

**El límite, innegociable.** Puede mutar set-points, dinámicas, umbrales de
zona y políticas — que son *preferencias*. **Nunca** los límites de
viabilidad ni la vara de calidad, que son *contrato*. Si el estrés prolongado
pudiera mover los límites, el sistema resuelve el ámbar declarando que el
ámbar está bien — la forma más elegante de manipular la propia métrica.

**Gatillo.** Disparado por *permanencia en ámbar*, no por calendario — tiempo
acumulado en zona ámbar (o `Λ` por encima de un umbral) abre la ventana de
mutación. Conexión natural con la carga alostática que ya existe.

## Lo que NO se hace (todavía)

- Ninguna de las dos se implementa. La prioridad es que el lazo 1 esté
  bien medido y con procedencia completa antes de abrir el lazo 2.
- Si se implementa aprendizaje de `g`, va con: medición externa, estimado
  por promedio móvil, y comparación declarado-vs-aprendido reportable.
