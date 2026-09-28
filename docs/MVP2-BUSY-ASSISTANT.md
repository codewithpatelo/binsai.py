# MVP 2 — The Busy Assistant Problem

Nombre elegido: **Busy Assistant Problem** (en la literatura actual: *persistent
agents*). Es el problema viable mínimo de la EPA — cumple las cuatro condiciones:

1. Mantener variables en rangos viables por tiempo indefinido, sin objetivo terminal.
2. Tensiones antagónicas entre empuje (servicio) y arrastre (recursos), que no se
   resuelven: se administran.
3. Información local y privilegiada, más barata y de menor latencia que la externa.
4. Dinámicas no lineales e incertidumbre.

## Por qué MVP 2 y no otra cosa

MVP 1 tenía **un solo drive** (δ_metabolic, S1). Con un solo drive de arrastre la
política óptima es no hacer nada — el equilibrio es un *nivel*. Recién con dos
drives antagónicos el equilibrio deja de ser un nivel y pasa a ser un **ritmo de
trabajo sostenible** — esa es la figura del paper.

## Componentes

- **Dos drives antagónicos**:
  - `servicio` — push, deriva basal `decay`: x es el nivel de satisfacción de
    la entrega ("estamos al día"), y sin entregar x cae hacia el déficit. Las
    acciones que entregan sacian (u > 0 sube x). Ver "Convención de signo".
  - `metabolico` — pull, deriva que recupera (la presión de cuidar recursos crece
    bajo negligencia basal)
- **Variables observadas con nivel y ritmo**:
  - servicio observa: entregas aprobadas, progreso
  - metabolico observa: presupuesto, tokens, memoria, disco
- **Contrato de viabilidad como archivo** (`viability-contract.json`) — los
  umbrales y los ritmos sostenibles se derivan del contrato, no se setean a ojo
  (esto cierra la procedencia de θ/ρ/w también)
- **Acciones con vector de efectos**, incluidas las de preservación (liberar
  memoria, compactar contexto, bajar de modelo) — son las que muestran que
  inhibir no es quedarse quieto
- **Demostración central — tres condiciones, una figura**: (1) solo
  `metabolico` → la política óptima es no hacer nada (los recursos se reponen
  solos, el agente converge a inacción); (2) solo `servicio` → el agente
  trabaja hasta agotarse (cada acción drena recursos sin freno de
  preservación, burn-out hacia viabilidad); (3) los dos → aparece el **ritmo
  sostenible** — ráfagas de entrega alternadas con preservación. La tesis del
  MVP2 en una imagen: ni la conservación sola ni el servicio solo son viables
  a largo plazo — la viabilidad persistente emerge de administrar ambas
  tensiones.

## Presión trazable (requisito transversal)

La presión total combina tres fuentes que deben verse separadas en la librería
(`drive.pressure_components()` ya lo expone):

- `level` — de la variable observada (dónde estás)
- `pace` — de la variable observada (a qué velocidad te degradás)
- `tension` — σ acumulada por la dinámica autónoma (hacia dónde tendés si nadie
  hace nada)

A igual estado medido, un drive con tensión acumulada empuja más que uno recién
saciado — la deriva es lo que hace que la señal de saciedad `g` importe: con
deriva, una acción tiene que *descargar tensión acumulada*, no solo mover un
nivel medible.

## Convención de signo (resuelta)

**x es el nivel de satisfacción de la necesidad, no la magnitud del déficit.**

- `servicio` (push): x alto = "la entrega está al día"; x bajo = "vamos
  atrasados". Deriva basal `decay`: sin entregar, el tiempo pasa, la ventana
  se consume y x cae hacia el déficit. Las acciones que entregan sacian:
  u > 0 sube x. La negligencia basal lo lleva al rojo — eso es lo que queremos.
- `metabolico` (pull): x alto = "recursos holgados"; x bajo = "recursos
  comprometidos". Deriva basal `recover`: la ventana repone (el presupuesto
  se refresca, la memoria se libera sola) y trabajar lo vacía (u < 0).

Con esta convención la asimetría queda explícita: los dos drives decaen hacia
zonas distintas por causas distintas — servicio decae *solo* (la necesidad
re-emerge), metabólico decae *por el trabajo* (el empuje de servicio lo drena
vía acciones/coupling). La figura del paper se sostiene sola.

**Implicación de implementación (ya ejecutada)**: bajo esta convención el
déficit es "x bajo respecto de x*", espejo de la convención original de la
librería (x = déficit, zonas deficit en el extremo alto). La armonización ya
se hizo — zonas default, satiate/deplete, presets (push=decay, pull=recover),
routing, sleep y fuzzificación migrados en el commit posterior a `d755aed`.
**Los experimentos corridos antes del flip usan la convención de déficit y no
son comparables punto a punto** — ver CHANGELOG.

## Hallazgo previo al MVP2 — el regulado gasta más, no menos

*(Resultado, no interpretación — medido en `tests/test_world.py`, 3 agentes,
300 ticks, λ_demand=0.5, dry_run.)*

Bajo la convención nueva (x = satisfacción, metabólico = pull/recover), la
ablación regulado/no-regulado dio:

| Condición | Acciones | session_tokens |
|---|---|---|
| No regulado | 130 × `respond_slow` (siempre lo mismo) | 65,290 |
| Regulado | 121 `respond_fast` + 178 `proact` + 8 `respond_slow` | **79,866 (+22%)** |

El regulado **gasta más**. Esto no es un bug: es la tesis del potenciador
funcionando. Con solo sensores, la holgura no pide nada; con deriva, la
holgura *empuja a usarla*. Un sistema regulado no es el que gasta menos — es
el que gasta cuando tiene margen y se cuida cuando no (`respond_slow` solo
aparece 8 veces: bajo déficit el regulado sí se retrae).

**La invariante vieja ("regulado gasta menos") era artefacto de la convención
anterior**, no una propiedad del mecanismo: con x = déficit, la deriva solo
podía empujar hacia la restricción.

**Pregunta abierta que responde el MVP2**: ¿el gasto extra produce entregas
útiles o es actividad sin retorno? Con el metabólico solo no se puede saber —
los 178 proacts no tienen una variable de servicio contra la cual medirlos.
Con los dos drives, la figura de las tres condiciones lo contesta.
