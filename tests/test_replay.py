"""El contrafáctico de una ventana, independiente de qué ventana sea."""
import math
import pytest

from binsai.drives import Drive
from binsai.observed import ObservedVariable
from binsai.replay import Ventana, Escenario

H, DT = 11.5, 1/60.0
PULSOS = int(round(H/DT))


def necesidad(nombre, direccion, sp=0.5, margen=1/3):
    d = Drive(name=nombre, set_point=sp, value=sp, spring="magnetic-2nd",
              lambda_rate=math.copysign(0.001, direccion),
              basal_direction="recover" if direccion > 0 else "decay",
              dt=DT, horizon=H, viability=(sp-margen, sp+margen))
    d.calibrate(mortality=0.6)
    return d


def ventana(series=None, **kw):
    met, ser = necesidad("metabolico", +1.0), necesidad("servicio", -1.0)
    var = ObservedVariable("gasto", "band", (0.0, 1.0), set_point=0.0,
                           pacing_mode="none", monotonic=False, window=H,
                           levels={"amarillo": 10, "ambar": 25, "rojo": 50},
                           hemisphere="deficit")
    s = series if series is not None else [0.0]*PULSOS
    return Ventana(horizonte=H, dt=DT, necesidades=[met, ser],
                   variables={"gasto": var}, series={"gasto": s},
                   dueño={"gasto": "metabolico"}, **kw)


def test_a4_solo_la_dinamica_basal_mata():
    r = ventana().correr(Escenario.SOLO_BASAL)
    assert r.muerte is not None and r.muerte < H
    assert r.n_eventos == 0
    assert r.pulsos_con_accion == 0, "nadie actuó, y está medido en ejecución"


def test_sin_dinamica_basal_el_mundo_queda_solo():
    """Aísla la pregunta: ¿alcanza el mundo sin ayuda de la deriva?"""
    r = ventana().correr(Escenario.SOLO_PERTURBACIONES)
    assert r.muerte is None, "sin perturbaciones y sin deriva no pasa nada"
    assert all(abs(v - 0.5) < 1e-9 for _, v in r.series["metabolico"])


def test_a3_sin_agente_no_hay_un_solo_release():
    pres = [0.0]*50 + [0.9]*(PULSOS-100) + [0.0]*50
    r = ventana(pres).correr(Escenario.TODO)
    assert r.n_eventos >= 1
    assert r.releases == 0, "ningún evento se cierra porque no hay agente"


def test_a2_un_wake_sin_micro_objetivo_se_descarta_y_se_cuenta():
    r = ventana().correr(Escenario.CON_AGENTE, semilla=3)
    assert r.releases == 0
    assert all(c.variable for c in r.ciclos), "todo ciclo tiene micro-objetivo"


def test_el_ciclo_cognitivo_es_un_intervalo_y_no_se_solapa():
    pres = [0.9 if 100 < i < 500 else 0.0 for i in range(PULSOS)]
    r = ventana(pres).correr(Escenario.CON_AGENTE, semilla=7)
    for a, b in zip(r.ciclos, r.ciclos[1:]):
        assert a.cierra is not None and a.cierra <= b.abre, "dos ciclos a la vez"
    for c in r.ciclos:
        assert c.cierra > c.abre, "una activación dura su ciclo, no es un punto"


def test_a4_1_la_corrida_termina_en_la_primera_muerte():
    r = ventana().correr(Escenario.SOLO_BASAL)
    fin = max(t for t, _ in r.series["metabolico"])
    assert fin * DT == pytest.approx(r.muerte, rel=1e-6)


def test_a5_la_holgura_se_mide_y_puede_no_existir():
    v = ventana()
    barrido = v.barrer_accion([0.0, 1.0, 2.0], semillas=(11,))
    assert [b["u"] for b in barrido] == [0.0, 1.0, 2.0]
    assert all(b["de"] == 1 for b in barrido)
    # con el agente sin eventos que cerrar, actuar no compra nada: eso es
    # holgura cero, y la función lo dice en vez de inventar un régimen
    assert isinstance(v.hay_holgura([0.0, 1.0]), bool)


def test_las_series_tienen_que_medir_lo_mismo():
    with pytest.raises(ValueError, match="largos distintos"):
        met = necesidad("m", +1.0)
        var = ObservedVariable("a", "band", (0.0, 1.0), set_point=0.0,
                               pacing_mode="none", window=H)
        Ventana(horizonte=H, dt=DT, necesidades=[met],
                variables={"a": var, "b": var},
                series={"a": [0.0]*10, "b": [0.0]*11}, dueño={"a": "m", "b": "m"})
