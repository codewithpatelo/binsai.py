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
                          release sólo con g medido por A3. El agente puede
                          medir pero no mover el mundo: un evento se cierra
                          sólo si la variable grabada vuelve sola.
    CONTRAFACTICO         lo mismo, pero el manager elige la acción correcta
                          siempre: cada ciclo resuelve su micro-objetivo con
                          g = 1. Es la cota superior de lo que el agente puede
                          hacer, y la única pregunta que importa: ¿alcanza?

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

from .drives import Drive, PerturbationEnvelope
from .fuzzy import homeostatic_error
from .observed import ObservedVariable


def _sev_zona(zona: Optional[str]) -> int:
    """Severidad canónica de la zona de una necesidad: verde 0 … rojo 3."""
    z = zona or "verde"
    if "amarillo" in z:
        return 1
    if "ambar" in z:
        return 2
    if "rojo" in z:
        return 3
    return 0


class Escenario(Enum):
    SOLO_PERTURBACIONES = "solo_perturbaciones"
    SOLO_BASAL          = "solo_basal"
    TODO                = "todo"
    CON_AGENTE          = "con_agente"
    CONTRAFACTICO       = "contrafactico"


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
    curas: int = 0
    ultima_cura: int = -10**9


@dataclass
class Resultado:
    escenario: Escenario
    muerte: Optional[float]                 # tiempo del mundo, None = llega al final
    quien: Optional[str]
    series: dict                            # necesidad -> [(tick, valor)]
    eventos: dict                           # necesidad -> [Perturbation]
    necesidades: list = field(default_factory=list)
    pulsos: int = 0
    dt: float = 1.0
    ciclos: list = field(default_factory=list)
    descartados: list = field(default_factory=list)   # sorteos sin micro-objetivo
    pulsos_con_accion: int = 0              # medido, no declarado

    @property
    def releases(self) -> int:
        return sum(1 for ps in self.eventos.values() for p in ps if p.closed_at is not None)

    @property
    def n_eventos(self) -> int:
        return sum(len(ps) for ps in self.eventos.values())

    def dibujar(self, **kw) -> str:
        """El artefacto canónico de esta corrida, con todo lo que hay que ver.

        Los ciclos cognitivos como intervalos, los wakes descartados, la muerte
        griseando lo posterior, y el eje fijado a la ventana entera para que una
        necesidad que murió a mitad de camino no parezca haber llegado.
        """
        from .viz import timeline_svg
        ciclos: dict = {}
        for c in self.ciclos:
            ciclos.setdefault(c.necesidad, []).append(
                (c.abre, c.cierra or c.abre + 1, c.desenlace))
        kw.setdefault("tmax", self.pulsos)
        return timeline_svg(self.necesidades, cycles=ciclos,
                            discarded=self.descartados,
                            death=None if self.muerte is None else int(round(self.muerte/self.dt)),
                            **kw)

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
    verde: float = 0.33
    ttd_theta: float = 0.2                  # θ: fracción del TTD admitida como espera
    ttd_refractario: float = 0.1            # fracción del TTD para el refractario

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
               u: float = 0.0, accion: Optional[Callable] = None,
               basal_en_bucle: bool = True,
               wake_determinista: bool = False) -> Resultado:
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
        # con basal_en_bucle=False la deriva basal se apaga mientras hay un
        # ciclo cognitivo abierto: mismas perturbaciones, mismas correcciones.
        basal0 = {d.name: (d.kappa, d.lambda_rate, d.spring_fatigue) for d in necesidades}

        r = random.Random(semilla)
        res = Resultado(escenario=escenario, muerte=None, quien=None, series={}, eventos={},
                        pulsos=self.pulsos, dt=self.dt)
        ciclo: Optional[Ciclo] = None
        refr = -1e9
        con_agente = escenario in (Escenario.CON_AGENTE, Escenario.CONTRAFACTICO)
        infalible = escenario is Escenario.CONTRAFACTICO

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
                # Piso de presión, acotado por la tasa máxima.
                h = min(self.tasa_maxima, self.tasa_base * math.exp(self.ganancia * p))
                if wake_determinista:
                    # sin sorteo: si hay una perturbación activa, despierta.
                    con_pert = [d for d in vivos
                                if any(pp.open for pp in d.perturbation_history)]
                    if con_pert:
                        quien = max(con_pert, key=homeostatic_error)
                        suyas = [(k, o) for k, o in obs.items()
                                 if self.dueño[k] == quien.name]
                        var = (max(suyas, key=lambda kv: kv[1].pressure(t) or 0.0)[0]
                               if suyas else "")
                        ciclo = Ciclo(abre=i, variable=var, necesidad=quien.name,
                                      p0=round(homeostatic_error(quien), 4))
                    h = 0.0
                # La rama de TTD del contrato NO está acá. Medida sobre esta
                # ventana satura el portón: domina el 100 % de los pulsos con
                # tasas de 64 a 18.000 por hora, porque el TTD se proyecta con
                # u = 0 desde un estado ya fuera de verde y da ≈ 0 toda la
                # noche. Con eso las activaciones las espacia el refractario,
                # no A2, y la figura se ve bien por el motivo equivocado.
                if r.random() < 1 - math.exp(-h * self.dt):
                    # El micro-objetivo es la NECESIDAD con mayor error
                    # homeostático volviendo a verde. No exige que haya una
                    # perturbación abierta: la necesidad puede estar lejos de su
                    # punto de equilibrio por deriva basal, y eso también hay
                    # que atenderlo. La variable observada es dónde actúa, y es
                    # la de mayor presión del carril.
                    quien = max(vivos, key=homeostatic_error)
                    suyas = [(k, o) for k, o in obs.items() if self.dueño[k] == quien.name]
                    var = (max(suyas, key=lambda kv: kv[1].pressure(t) or 0.0)[0]
                           if suyas else "")
                    ciclo = Ciclo(abre=i, variable=var, necesidad=quien.name,
                                  p0=round(homeostatic_error(quien), 4))

            # ── el ciclo cognitivo: una iteración por tiempo de respuesta ────
            # El ciclo NO termina cuando la variable observada vuelve: termina
            # cuando la necesidad que lo activó está en su zona verde. Restaurar
            # la variable es la prioridad, no el criterio de cierre — devolver
            # el sensor y dejar a la necesidad en ámbar es declarar resuelto un
            # micro-objetivo que no se resolvió.
            if ciclo is not None:
                ciclo.iteraciones += 1
                # Una necesidad puede no tener ninguna variable observada: el
                # micro-objetivo sigue siendo ella volviendo a verde.
                o = obs.get(ciclo.variable)
                ahora = (o.pressure(t) or 0.0) if o is not None else 0.0
                nec = por_nombre[ciclo.necesidad]
                # A3: la corrección se aplica cuando hay calidad medida; nunca
                # en el pulso en que abre el ciclo.
                if ciclo.iteraciones >= 2 or i > ciclo.abre:
                    vuelve = ahora < self.verde
                    if infalible:
                        # El manager que actúa bien siempre NO espera a que la
                        # grabación devuelva la variable: su acción GENERA el
                        # zone pass hacia verde. La corrección vale lo que
                        # valdría el ataque de ese mismo cruce, ι(severidad) por
                        # el margen, y entra con la forma del release. Repite
                        # turno a turno hasta que la necesidad esté en verde.
                        # El tamaño de la corrección es el de la banda en que
                        # está la necesidad: ι(severidad de su zona) · margen.
                        # Así vale igual si la sacó una perturbación o la deriva.
                        # Un zone pass A VERDE es, por definición, el que deja a
                        # la necesidad en verde: su magnitud es la distancia que
                        # falta, no el ancho de una banda. Si la deriva se la
                        # come, el agente vuelve a actuar el turno siguiente;
                        # el bucle no se apaga hasta que llegue.
                        # Cuándo cae una acción efectiva se sortea, con la
                        # misma curva declarada que el portón: la tasa crece con
                        # el error homeostático. Un período fijo —un turno, un
                        # release— es tan arbitrario como uno por pulso.
                        pa = homeostatic_error(nec)
                        ha = min(self.tasa_maxima,
                                 self.tasa_base * math.exp(self.ganancia * pa))
                        sev = _sev_zona(nec.get_zone())
                        falta = nec.distancia_a_banda_siguiente()
                        if r.random() >= 1 - math.exp(-ha * self.dt):
                            falta = 0.0
                        if sev >= 1 and falta:
                            ciclo.ultima_cura = i
                            nec.open_correction(i, sev, ciclo.variable,
                                                hemisphere=(o.hemisphere if o is not None
                                                            else "deficit"),
                                                de=nec.get_zone() or "",
                                                a=nec.zona_de(nec.value + falta),
                                                magnitude=falta)
                            ciclo.curas += 1
                        nec.correct(i, 1.0, source=ciclo.variable)
                        ciclo.g = 1.0
                    else:
                        # Sin el supuesto de acción correcta, la acción sólo
                        # puede cobrar el cruce que la grabación contiene.
                        # cobra el cruce hacia el equilibrio en cualquier
                        # variable del carril: el agente atiende la necesidad
                        for k in [kk for kk in obs if self.dueño[kk] == nec.name]:
                            if nec.cobrar_correccion(i, k) is not None:
                                ciclo.curas += 1
                        if vuelve:
                            nec.correct(i, 1.0, source=ciclo.variable)
                            ciclo.g = 1.0
                    # Lo ÚNICO que apaga el bucle cognitivo son correcciones
                    # que lleven la necesidad a su zona verde. No hay breaker
                    # por iteraciones: un bucle que se apaga con la necesidad
                    # en ámbar deja el micro-objetivo sin resolver y habilita
                    # otra activación sobre el mismo problema.
                    if nec.get_zone() == "verde":
                        ciclo.cierra = i
                        ciclo.desenlace = "resuelto"
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

            if not basal_en_bucle:
                # La basal se pausa mientras transcurre el ADSR de una
                # perturbación o mientras hay un bucle cognitivo sobre esta
                # necesidad. Basal es lo que le pasa a la necesidad cuando no
                # está pasando ninguna de las dos cosas.
                for d in necesidades:
                    d.basal_suspendida = (
                        any(pp.en_adsr(i) for pp in d.perturbation_history)
                        or (ciclo is not None and ciclo.necesidad == d.name))
            for d in necesidades:
                d.update(tick=i)
                lo, hi = d.viability
                if res.muerte is None and not (lo < d.value < hi):
                    res.muerte, res.quien = t, d.name
            if res.muerte is not None:
                break                        # A4.1 — viabilidad conjuntiva

        if ciclo is not None:
            ciclo.cierra, ciclo.desenlace = self.pulsos, "abierto"
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
