"""El contrafáctico de una ventana, independiente de qué ventana sea."""
import math
import pytest

from binsai.drives import Drive, ZoneSpec
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
                           pacing_mode="time_to_violation", monotonic=False, window=H,
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
    # la serie está en las unidades de la variable: USD, no presión
    pres = [0.0]*50 + [40.0]*(PULSOS-100) + [0.0]*50
    r = ventana(pres).correr(Escenario.TODO)
    assert r.n_eventos >= 1
    assert r.releases == 0, "ningún evento se cierra porque no hay agente"


def test_el_micro_objetivo_es_la_necesidad_no_la_variable_observada():
    """Un wake nunca se descarta: el micro-objetivo es la necesidad.

    Exigir una perturbación abierta para abrir un ciclo deja la deriva basal
    fuera del alcance del agente, que es justamente lo que A4 dice que mata.
    """
    r = ventana().correr(Escenario.CON_AGENTE, semilla=3)
    assert not r.descartados, "ningún wake se descarta"
    assert all(c.necesidad for c in r.ciclos), "todo ciclo atiende una necesidad"


def test_el_ciclo_cognitivo_es_un_intervalo_y_no_se_solapa():
    pres = [40.0 if 100 < i < 500 else 0.0 for i in range(PULSOS)]
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
                               pacing_mode="time_to_violation", window=H)
        Ventana(horizonte=H, dt=DT, necesidades=[met],
                variables={"a": var, "b": var},
                series={"a": [0.0]*10, "b": [0.0]*11}, dueño={"a": "m", "b": "m"})


# ── lo que el artefacto canónico tiene que mostrar ───────────────────────────

def _drive_corrido(pulsos=400):
    d = necesidad("m", +1.0)
    for t in range(1, pulsos):
        d.update(tick=t)
    return d


def test_una_activacion_se_dibuja_como_intervalo_no_como_punto():
    from binsai.viz import timeline_svg
    d = _drive_corrido()
    sin = timeline_svg([d], width=900, tmax=PULSOS)
    con = timeline_svg([d], width=900, tmax=PULSOS,
                       cycles={"m": [(60, 120, "resuelto"), (200, 300, "breaker")]})
    assert con.count('fill-opacity="0.16"') == 2, "cada ciclo es una banda"
    assert sin.count('fill-opacity="0.16"') == 0
    assert "#3FB950" in con and "#F85149" in con, "el desenlace se distingue"


def test_un_agente_muerto_no_se_activa_y_lo_posterior_va_en_gris():
    from binsai.viz import timeline_svg
    d = _drive_corrido()
    s = timeline_svg([d], width=900, tmax=PULSOS, death=250,
                     cycles={"m": [(100, 180, "breaker"), (300, 360, "breaker")]},
                     discarded=[50, 280])
    assert "muerte" in s
    assert s.count('fill-opacity="0.16"') == 1, "el ciclo posterior a la muerte no se dibuja"
    assert s.count('stroke-opacity="0.45"') == 1, "ni el wake descartado posterior"


def test_el_eje_es_la_ventana_entera_no_la_ultima_muestra():
    from binsai.viz import timeline_svg
    import re
    d = _drive_corrido(pulsos=200)                 # murió a mitad de camino
    libre = timeline_svg([d], width=900)
    fijo = timeline_svg([d], width=900, tmax=PULSOS)
    puntos = lambda s: re.search(r'<polyline points="([^"]*)"', s).group(1).split()
    assert float(puntos(libre)[-1].split(",")[0]) > float(puntos(fijo)[-1].split(",")[0]), \
        "sin tmax la serie ocupa todo el ancho y parece que llegó al final"


def test_la_figura_no_dibuja_marcas_que_nadie_pidio():
    """La marca del resorte no está: era una marca sin leyenda sobre la tira."""
    from binsai.viz import timeline_svg
    d = Drive(name="m", set_point=0.5, value=0.5, spring="magnetic-2nd",
              lambda_rate=0.001, basal_direction="recover", dt=1/60,
              horizon=H, viability=(0.5-1/3, 0.5+1/3))
    d.calibrate(mortality=0.6)
    d.update(tick=1)
    s = timeline_svg([d], width=900, strip_height=180)
    assert "#BC8CFF" not in s and "#6E49CB" not in s


# ── el canon 5D: lo que la noche del 13/10 dejó fijado ────────────────────────

def test_5d_la_basal_se_pausa_durante_el_adsr_o_el_bucle():
    """Basal es lo que le pasa a la necesidad cuando NO hay perturbación ni acción.

    Mientras transcurre el ADSR de un evento, o mientras el agente tiene un
    bucle cognitivo abierto sobre esa necesidad, la basal no corre: ni deriva,
    ni resorte, ni carga alostática, y la velocidad queda congelada donde
    estaba. Colgar la pausa del flag `open` en vez del ADSR congela la
    necesidad para siempre cuando nadie corrige.
    """
    d = Drive(name="m", set_point=0.5, value=0.5, spring="magnetic-2nd",
              lambda_rate=0.05, basal_direction="decay", dt=DT, horizon=H,
              viability=(0.5 - 1/3, 0.5 + 1/3))
    d.calibrate(mortality=0.6)
    p = d.open_perturbation(1, 3, -1.0)
    assert p.en_adsr(2), "el ataque transcurre"
    fin = int((p.envelope.rise + p.envelope.decay) * H / DT) + 5
    assert not p.en_adsr(1 + fin), "el sustain NO es el evento transcurriendo"
    assert p.open, "y sigue abierta: nadie la corrigió"

    # la pausa, sobre una necesidad sin eventos: el valor no se mueve solo
    q = Drive(name="q", set_point=0.5, value=0.5, spring="magnetic-2nd",
              lambda_rate=0.05, basal_direction="decay", dt=DT, horizon=H,
              viability=(0.5 - 1/3, 0.5 + 1/3))
    q.calibrate(mortality=0.6)
    q.basal_suspendida = True
    antes = q.value
    for t in range(1, 60):
        q.update(tick=t)
    assert q.value == pytest.approx(antes, abs=1e-12), "con la basal en pausa no deriva"
    q.basal_suspendida = False
    for t in range(60, 80):
        q.update(tick=t)
    assert q.value != pytest.approx(antes, abs=1e-9), "y al reanudar vuelve a correr"


def test_5d_una_correccion_es_un_zone_pass_de_una_banda():
    """La consecuencia exitosa de una acción es un zone pass, y es discreto."""
    d = Drive(name="m", set_point=0.5, value=0.5, spring="magnetic-2nd",
              lambda_rate=0.05, basal_direction="decay", dt=DT, horizon=H,
              viability=(0.5 - 1/3, 0.5 + 1/3),
              zones=[ZoneSpec("verde", 0.5, 0.04),
                     ZoneSpec("deficit_amarillo", 0.39, 0.04),
                     ZoneSpec("deficit_ambar", 0.28, 0.04),
                     ZoneSpec("deficit_rojo", 0.17, 0.04)])
    d.value = 0.20                                  # en rojo
    paso = d.distancia_a_banda_siguiente()
    assert paso > 0, "hacia el punto de equilibrio"
    destino = d.value + paso
    assert destino < 0.5, "no se teletransporta a verde de un saque"
    assert d.zona_de(destino - 1e-4) != "verde", "cruza una banda, no todas"
    assert destino > d.value and destino <= 0.28 + 1e-6, "llega al borde de la siguiente"


def test_5d_el_bucle_cognitivo_solo_cierra_con_la_necesidad_en_verde():
    """No hay breaker por iteraciones ni wakes descartados."""
    v = ventana()
    r = v.correr(Escenario.CONTRAFACTICO, semilla=11, basal_en_bucle=False)
    assert not r.descartados
    for c in r.ciclos:
        assert c.desenlace in ("resuelto", "abierto")
        assert c.desenlace != "breaker"


def test_5d_sin_agente_no_hay_una_sola_correccion():
    """A3: el mundo no cura. Una corrección la cobra una acción o no existe."""
    for esc in (Escenario.TODO, Escenario.SOLO_PERTURBACIONES):
        r = ventana().correr(esc)
        assert all(not d._curas for d in r.necesidades)
