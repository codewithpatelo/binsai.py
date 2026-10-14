"""Contrafáctico de una ventana: qué habría pasado con la EPA bien implementada.

Esto no sabe nada de ninguna noche en particular. Toma lo que una ventana dejó
registrado —el contrato, las series de las variables observadas, y opcionalmente
cuándo se activó el agente— y lo corre contra el runtime canónico. Lo único que
cambia respecto de lo que corrió es el runtime.

    from binsai.replay import Ventana, Escenario

    v = Ventana(
        horizonte=11.5, dt=1/60,
        necesidades=[met, ser],                 # Drive, ya calibrados
        series={"ram_libre": [...], "gasto": [...]},
        variables={"ram_libre": var_ram, "gasto": var_gasto},
        dueño={"ram_libre": "metabolico", "gasto": "metabolico"},
    )
    v.correr(Escenario.SOLO_PERTURBACIONES)

Los cuatro escenarios responden preguntas distintas y hay que correrlos todos:

    SOLO_PERTURBACIONES   κ = λ = f = 0 — ¿alcanza el mundo solo para matar?
    SOLO_BASAL            sin variables observadas — ¿se cumple A4?
    TODO                  las dos, sin agente — la referencia contra la que se
                          mide cualquier cosa que el agente haga
    CON_AGENTE            activaciones por A2, ciclos cognitivos acotados,
                          release sólo con g medido por A3

Qué NO puede hacer un replay, y conviene tenerlo claro antes de leer el
resultado: las variables observadas son una grabación. El agente puede
despertar, elegir su micro-objetivo y medir, pero no puede mover el mundo. Un
evento sólo se cierra si la variable grabada vuelve a su zona durante el ciclo,
y atribuírselo al agente es correcto únicamente si el agente real causó esa
vuelta. Para preguntar "¿existe un régimen que salve la ventana?" está
`barrer_accion`, que agrega el canal que una grabación no contiene.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Sequence

from .drives import Drive
from .fuzzy import homeostatic_error
from .observed import ObservedVariable


class Escenario(Enum):
    SOLO_PERTURBACIONES = "solo_perturbaciones"
    SOLO_BASAL          = "solo_basal"
    TODO                = "todo"
    CON_AGENTE          = "con_agente"


@dataclass
class Ciclo:
    """Una activación: un ciclo cognitivo acotado (ARCHITECTURE §2.3).

    No es un punto en el tiempo. Empieza cuando el agente despierta, la
    perturbación que lo despertó define su micro-objetivo, y termina cuando ese
    micro-objetivo se resuelve, cuando ninguna acción segura puede ayudar, o
    cuando pega contra el breaker de iteraciones.
    """
    abre: int
    variable: str
    necesidad: str
    p0: float
    cierra: Optional[int] = None
    g: float = 0.0
    desenlace: str = "abierto"
    iteraciones: int = 0


@dataclass
class Resultado:
    escenario: Escenario
    muerte: Optional[float]                 # tiempo del mundo, None = llega al final
    quien: Optional[str]
    series: dict                            # necesidad -> [(tick, valor)]
    eventos: dict                           # necesidad -> [Perturbation]
    ciclos: list = field(default_factory=list)
    descartados: list = field(default_factory=list)   # sorteos sin micro-objetivo
    pulsos_con_accion: int = 0              # medido, no declarado

    @property
    def releases(self) -> int:
        return sum(1 for ps in self.eventos.values() for p in ps if p.closed_at is not None)

    @property
    def n_eventos(self) -> int:
        return sum(len(ps) for ps in self.eventos.values())

    def resumen(self) -> str:
        v = "llega al final" if self.muerte is None else f"muere {self.muerte:.2f} ({self.quien})"
        return (f"{self.escenario.value:21} {v:28} {self.n_eventos:4} eventos · "
                f"{self.releases} releases · {len(self.ciclos)} ciclos · "
                f"u en {self.pulsos_con_accion} pulsos")


@dataclass
class Ventana:
    """Lo que una ventana dejó registrado, listo para correr contra el canon."""
    horizonte: float                         # en tiempo del mundo
    dt: float                                # cuánto vale un pulso
    necesidades: Sequence[Drive]
    variables: dict                          # nombre -> ObservedVariable
    series: dict                             # nombre -> [valor | None] por pulso
    dueño: dict                              # nombre de variable -> nombre de necesidad
    # ley de despertar del contrato
    tasa_base: float = 0.25
    ganancia: float = 3.1
    tasa_maxima: float = 12.0
    refractario: float = 0.25                # tiempo del mundo
    turno: float = 5/60                      # duración de una iteración del ciclo
    breaker: int = 12                        # tope de iteraciones
    verde: float = 0.33                      # umbral de "volvió a su zona"

    def __post_init__(self) -> None:
        n = {len(s) for s in self.series.values()}
        if len(n) != 1:
            raise ValueError(f"las series tienen largos distintos: {sorted(n)}")
        self.pulsos = n.pop()
        faltan = set(self.series) - set(self.variables)
        if faltan:
            raise ValueError(f"series sin variable observada: {sorted(faltan)}")
        sin_dueño = set(self.variables) - set(self.dueño)
        if sin_dueño:
            raise ValueError(f"variables sin necesidad: {sorted(sin_dueño)}")

    # ── la corrida ──────────────────────────────────────────────────────────

    def correr(self, escenario: Escenario, *, semilla: int = 11,
               u: float = 0.0, accion: Optional[Callable] = None) -> Resultado:
        """`u` es la acción sostenida mientras hay un ciclo abierto, en múltiplos
        de |λ|: es el canal que una grabación no contiene. Con u = 0 el agente
        sólo puede cerrar eventos."""
        import copy
        necesidades = [copy.deepcopy(d) for d in self.necesidades]
        por_nombre = {d.name: d for d in necesidades}
        obs = {k: copy.deepcopy(v) for k, v in self.variables.items()}

        if escenario is Escenario.SOLO_BASAL:
            obs = {}
        if escenario is Escenario.SOLO_PERTURBACIONES:
            for d in necesidades:
                d.kappa = d.lambda_rate = d.spring_fatigue = 0.0
        for d in necesidades:
            d.observed = [o for k, o in obs.items() if self.dueño[k] == d.name]
            d.dt, d.horizon = self.dt, self.horizonte

        r = random.Random(semilla)
        res = Resultado(escenario=escenario, muerte=None, quien=None, series={}, eventos={})
        ciclo: Optional[Ciclo] = None
        refr = -1e9
        con_agente = escenario is Escenario.CON_AGENTE

        for i in range(1, self.pulsos + 1):
            t = i * self.dt
            for k, o in obs.items():
                v = self.series[k][i-1]
                if v is not None:
                    o.observe(t, float(v))

            # ── reactivación (A2 + §1.2): no se sortea con un ciclo abierto ──
            if con_agente and ciclo is None and (t - refr) >= self.refractario:
                vivos = [d for d in necesidades if res.muerte is None]
                p = max((homeostatic_error(d) for d in vivos), default=0.0)
                h = min(self.tasa_maxima, self.tasa_base * math.exp(self.ganancia * p))
                if r.random() < 1 - math.exp(-h * self.dt):
                    quien = max(vivos, key=homeostatic_error)
                    cand = [(k, o) for k, o in obs.items()
                            if self.dueño[k] == quien.name
                            and (o.pressure(t) or 0.0) >= self.verde
                            and any(pp.open and pp.source == k
                                    for pp in quien.perturbation_history)]
                    if cand:
                        var = max(cand, key=lambda kv: kv[1].pressure(t) or 0.0)[0]
                        ciclo = Ciclo(abre=i, variable=var, necesidad=quien.name,
                                      p0=round(obs[var].pressure(t) or 0.0, 4))
                    else:
                        # A2 §1.2: un wake sin micro-objetivo se descarta y se
                        # registra. Despertar sobre una variable en verde y
                        # declararla resuelta es una corrección fantasma.
                        res.descartados.append(i)

            # ── el ciclo cognitivo: una iteración por tiempo de respuesta ────
            if ciclo is not None and (i - ciclo.abre) % max(1, round(self.turno/self.dt)) == 0:
                ciclo.iteraciones += 1
                o = obs[ciclo.variable]
                ahora = o.pressure(t) or 0.0
                resuelto = ahora < self.verde
                if resuelto or ciclo.iteraciones >= self.breaker:
                    # A3 — g se mide sobre la variable perturbada, por su vuelta
                    # a la zona estable. No sobre el error de la necesidad.
                    g = 1.0 if resuelto else max(0.0, min(1.0, (ciclo.p0 - ahora)/max(ciclo.p0, 1e-9)))
                    por_nombre[ciclo.necesidad].correct(i, g, source=ciclo.variable)
                    ciclo.cierra, ciclo.g = i, round(g, 4)
                    ciclo.desenlace = "resuelto" if resuelto else "breaker"
                    res.ciclos.append(ciclo)
                    refr, ciclo = t, None

            if u and ciclo is not None:
                for d in necesidades:
                    signo = -1.0 if d.lambda_rate >= 0 else +1.0
                    d.sustain("accion", signo * abs(d.lambda_rate) * u)
                    res.pulsos_con_accion += 1
            elif u:
                for d in necesidades:
                    d.sustain("accion", 0.0)

            for d in necesidades:
                d.update(tick=i)
                lo, hi = d.viability
                if res.muerte is None and not (lo < d.value < hi):
                    res.muerte, res.quien = t, d.name
            if res.muerte is not None:
                break                        # A4.1 — viabilidad conjuntiva

        if ciclo is not None:
            ciclo.cierra, ciclo.desenlace = self.pulsos, "sin_accion_util"
            res.ciclos.append(ciclo)
        res.series = {d.name: list(d.history) for d in necesidades}
        res.eventos = {d.name: list(d.perturbation_history) for d in necesidades}
        res.necesidades = necesidades
        return res

    def descomponer(self, *, semilla: int = 11) -> dict:
        """Los tres escenarios sin agente, que es como se aísla qué está mal."""
        return {e: self.correr(e, semilla=semilla)
                for e in (Escenario.SOLO_PERTURBACIONES, Escenario.SOLO_BASAL,
                          Escenario.TODO)}

    def barrer_accion(self, us: Sequence[float], *, semillas: Sequence[int] = (11,),
                      ) -> list[dict]:
        """A5 — ¿existe un régimen donde el agente actúe y llegue al final?

        Un replay no contiene el canal de acción sostenida, así que para
        preguntar por la holgura hay que agregarlo y barrerlo. Si el tiempo de
        vida es monótono decreciente en `u`, no hay holgura: el agente sólo
        puede elegir morir antes.
        """
        salida = []
        for u in us:
            vidas, llegan = [], 0
            for s in semillas:
                r = self.correr(Escenario.CON_AGENTE, semilla=s, u=u)
                vidas.append(self.horizonte if r.muerte is None else r.muerte)
                llegan += r.muerte is None
            salida.append(dict(u=u, vida=sum(vidas)/len(vidas),
                               llegan=llegan, de=len(semillas)))
        return salida

    def hay_holgura(self, us: Sequence[float], **kw) -> bool:
        """True si alguna acción compra tiempo — A5 en una línea."""
        b = self.barrer_accion(us, **kw)
        sin = next((x["vida"] for x in b if x["u"] == 0), b[0]["vida"])
        return any(x["vida"] > sin for x in b)
