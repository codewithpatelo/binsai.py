# Antecedentes

Trabajos cercanos a la EPA. Cada entrada dice qué hace el trabajo, en qué se parece y en
qué difiere. Se citan como antecedentes; no se presentan como aporte propio.

## Interoceptive Attention as Dynamic Homeostatic Prioritization in a Foraging Agent

Grimbly, Kuske, Boonstra, Bassett, van Hoof, Hodson, Rosman, Smith, Solms y Shock.
arXiv:2608.04232 (2026). https://arxiv.org/abs/2608.04232

**Qué hace.** Un agente de inferencia activa en una grilla (AffectWorld) con cuatro canales
interoceptivos: hambre, sed y sofocación, y uno de control que no informa nada. Cada
necesidad tiene un nivel discreto de 0 a 5. Hambre y sed decaen una unidad por paso y
llegar a cero mata; la comida y el agua las reponen. El agente tiene un presupuesto fijo de
precisión de lectura para repartir entre los canales y lo vuelca en la necesidad que cree
más comprometida.

**Qué reporta.** Repartir la precisión hacia la necesidad más comprometida duplica la
supervivencia en la fase de aprendizaje frente a repartirla parejo (0,414 contra 0,199, 11
escenarios). Apuntarla a la necesidad menos comprometida da peor que el reparto parejo.

**En qué se parece.** Necesidades con decaimiento propio bajo inacción y muerte al cruzar
el límite (A4, A4.1). La conducta depende del estado interno (A1). Lo que prioriza es la
necesidad más comprometida, no un promedio (A2.1).

**En qué difiere.** El decaimiento es lineal y sin resorte ni fatiga. No hay bandas
algedónicas ni eventos: la necesidad es un nivel que el agente lee con ruido. No hay
variables observadas del mundo que perturben a la necesidad, ni envolvente, ni `g`: la
reposición es automática al pisar el recurso. El selector está puesto a mano y supone que
la creencia sobre el cuerpo está bien calibrada.

## Interoceptive machine framework: Toward interoception-inspired regulatory architectures in artificial intelligence

Candia-Rivera. arXiv:2604.24527 (2026). https://arxiv.org/abs/2604.24527

**Qué hace.** Propone una arquitectura con tres módulos (homeostático, alostático y
enactivo) que alimentan una capa de arbitraje de la política. Define una variable
interoceptiva por su función: codifica el estado del sistema respecto de sus límites de
viabilidad, influye en la elección de acciones y participa de lazos de regulación. La
separa de la «telemetría pasiva», que no influye en el control.

**Qué reporta.** Nada medido: el propio trabajo dice que la propuesta es conceptual y de
arquitectura. Propone ablaciones pero no las corre.

**En qué se parece.** La distinción entre variable interoceptiva y telemetría es la misma
que la EPA hace entre necesidad y variable observada. Los límites de viabilidad pesan más
que el éxito en la tarea.

**En qué difiere.** Deja abierto, y lo dice, cómo una lectura de un sensor se convierte en
un cambio de la variable interna y con qué dinámica esa variable decae o se recupera. Eso
es lo que en la EPA especifican la dinámica basal, la envolvente de la perturbación y la
corrección. La regulación entra como un costo restado a la recompensa y como temperatura
de la política, no como una tasa de activación.
