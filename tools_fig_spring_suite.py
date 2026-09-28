# -*- coding: utf-8 -*-
"""Generates the spring-figure suite as self-contained HTML artifacts.

Each output embeds the run data as JSON (<script type="application/json">)
plus hand-rolled SVG in the same visual language as binsai.viz (algedonic
bands, viability dashes, death zones, set-point, basal arrow).

    python _fig_spring_suite.py   ->  fig_*.html in repo root

Convention: x = satisfaction (post-0.3.0). The ablation scenarios below are
the exact mirror (x -> 1-x) of the pre-flip runs in docs/ABLATION-SPRING.md:
push drive, basal_direction="decay" (lambda < 0), shock = deplete(-0.35).
"""
import json
import math
import sys

sys.path.insert(0, "src")
from binsai import Drive
from binsai.observed import ObservedVariable
from binsai.viz import timeline_svg, _THEMES

TH = _THEMES["dark"]

CFG = dict(
    set_point=0.70, kappa=0.04, lambda_rate=0.002, basal_direction="decay",
    spring_threshold=0.12, spring_release=1.0,
    viability=(0.10, 0.98),
)
TICKS_A, TICKS_B, SHOCK_T, SHOCK_U = 900, 700, 150, 0.35


def make_drive(name, spring, reach):
    return Drive(name=name, value=CFG["set_point"], spring=spring,
                 spring_reach=reach, history_limit=0, **CFG)
    # history_limit=0: keep the full trajectory — silent truncation made the
    # magnet look like it started from a different initial condition.


def run(drive, ticks, shock=None):
    """Advance the drive under basal negligence; shock = (tick, deplete_amount)."""
    sigma, zones = [], []
    for t in range(ticks):
        if shock and t == shock[0]:
            drive.deplete(shock[1])
            drive.record_event(t, "shock")
        drive.update(t)
        sigma.append((t, drive.tension))
        zones.append((t, drive.get_zone()))
    return sigma, zones


def breach_tick(drive):
    lo, hi = drive.viability
    for t, v in drive.history:
        if v <= lo or v >= hi:
            return t
    return None


def page(title, body, data):
    return (
        f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{title}</title><style>'
        f'body{{margin:0;background:{TH["bg"]};color:{TH["ink"]};'
        f'font-family:system-ui,sans-serif;padding:24px}}'
        f'h1{{font-size:17px}}h2{{font-size:13px;color:{TH["soft"]};'
        f'font-weight:500}}svg{{display:block;max-width:100%;height:auto;'
        f'border:1px solid {TH["grid"]};border-radius:14px;padding:8px;'
        f'margin-bottom:24px}}.cfg{{color:{TH["soft"]};font-size:12px;'
        f'font-family:ui-monospace,monospace;white-space:pre-wrap}}</style>'
        f'</head><body><h1>{title}</h1>{body}'
        f'<script type="application/json" id="run-data">'
        f'{json.dumps(data)}</script></body></html>'
    )


# ── (a) three springs × two scenarios, trapped regime ────────────────────────

def fig_ablation():
    variants = [
        ("linear",      "linear",    None),
        ("pulsatile_w_inf", "pulsatile", float("inf")),
        ("magnet_w0.18",    "pulsatile", 0.18),
    ]
    data = {"config": {**CFG, "ticks_A": TICKS_A, "ticks_B": TICKS_B,
                       "shock_t": SHOCK_T, "shock_u": SHOCK_U},
            "scenario_A": {}, "scenario_B": {}}

    strips = {}
    for label, spring, w in variants:
        d = make_drive(f"A_{label}", spring, w)
        _, zones = run(d, TICKS_A)
        strips[label] = (d, breach_tick(d))
        data["scenario_A"][label] = {
            "trajectory": d.history, "events": d.events,
            "breach": breach_tick(d), "zones": zones,
        }

    svgA = timeline_svg(
        [s for s, _ in strips.values()],
        width=940, strip_height=130, ghost_ticks=0,
        title="Escenario A — negligencia basal pura (régimen atrapado: λ < κρw/e)",
    )

    drives_b = {}
    for label, spring, w in variants:
        d = make_drive(f"B_{label}", spring, w)
        run(d, TICKS_B, shock=(SHOCK_T, SHOCK_U))
        drives_b[label] = d
        data["scenario_B"][label] = {
            "trajectory": d.history, "events": d.events,
            "breach": breach_tick(d), "shock": [SHOCK_T, SHOCK_U],
        }

    svgB = timeline_svg(
        list(drives_b.values()),
        width=940, strip_height=130, ghost_ticks=0,
        title=f"Escenario B — mismo régimen + shock −{SHOCK_U} en t={SHOCK_T}",
    )

    cfg_txt = (
        f'x*={CFG["set_point"]}  λ={-CFG["lambda_rate"]} (decay)  κ={CFG["kappa"]}  '
        f'θ={CFG["spring_threshold"]}  ρ={CFG["spring_release"]}  '
        f'w=0.18 (magnet) / ∞ (pulsatile) / — (linear)  '
        f'viability={CFG["viability"]}\n'
        f'grip κρw/e = {CFG["kappa"]*CFG["spring_release"]*0.18/math.e:.4f} '
        f'> |λ|={CFG["lambda_rate"]} → régimen atrapado'
    )
    body = f'<div class="cfg">{cfg_txt}</div><h2>A</h2>{svgA}<h2>B</h2>{svgB}'
    html = page("Binsai — ablación de resortes (régimen atrapado)", body, data)
    with open("fig_ablation_springs.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("fig_ablation_springs.html",
          "| A breaches:", {k: b for k, (_, b) in strips.items()},
          "| B breaches:", {k: breach_tick(d) for k, d in drives_b.items()})


# ── (b) tension σ as its own series under the trajectory ─────────────────────

def fig_tension():
    d = make_drive("servicio", "pulsatile", 0.18)
    sigma, _ = run(d, TICKS_B, shock=(SHOCK_T, SHOCK_U))

    width, ph1, ph2 = 940, 150, 110
    ml, mr, mt, gap, mb = 46, 96, 30, 14, 58
    pw = width - ml - mr
    tmax = TICKS_B
    height = mt + ph1 + gap + ph2 + mb

    def X(t):
        return ml + (t / tmax) * pw

    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
         f'width="{width}" role="img">',
         f'<rect width="{width}" height="{height}" fill="{TH["bg"]}"/>',
         f'<marker id="arr" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" '
         f'markerHeight="7" orient="auto-start-reverse">'
         f'<path d="M0 0 L10 5 L0 10z" fill="{TH["ink"]}"/></marker>']

    # ── panel 1: trajectory (same visual language) ──
    y0, y1 = mt, mt + ph1
    lo_v, hi_v = d.viability
    # death zone below lo_v (deficit side in satisfaction convention)
    if lo_v > 0:
        yy = y0 + (1.0 - lo_v) * ph1
        g.append(f'<rect x="{ml}" y="{yy:.1f}" width="{pw}" height="{y1-yy:.1f}" '
                 f'fill="{TH["death"]}" fill-opacity="0.55"/>')
    if hi_v < 1:
        yy = y0 + (1.0 - hi_v) * ph1
        g.append(f'<rect x="{ml}" y="{y0}" width="{pw}" height="{yy-y0:.1f}" '
                 f'fill="{TH["death"]}" fill-opacity="0.55"/>')
    from binsai.viz import _zone_bands, _zone_color
    for lo, hi, zn in _zone_bands(d.zones):
        yt = y0 + (1.0 - hi) * ph1
        g.append(f'<rect x="{ml}" y="{yt:.1f}" width="{pw}" '
                 f'height="{(hi-lo)*ph1:.1f}" fill="{_zone_color(zn, TH)}" '
                 f'fill-opacity="0.22"/>')
    for lim in (lo_v, hi_v):
        if 0 < lim < 1:
            yy = y0 + (1.0 - lim) * ph1
            g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{yy:.1f}" y2="{yy:.1f}" '
                     f'stroke="{TH["dead"]}" stroke-width="2.4" stroke-dasharray="9 6"/>')
    sp_y = y0 + (1.0 - d.set_point) * ph1
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{sp_y:.1f}" y2="{sp_y:.1f}" '
             f'stroke="{TH["ink"]}" stroke-width="1.1" stroke-dasharray="7 5"/>')
    # resting level marker
    rl = d.resting_level
    rl_y = y0 + (1.0 - rl) * ph1
    g.append(f'<line x1="{ml+pw-58}" x2="{ml+pw-26}" y1="{rl_y:.1f}" y2="{rl_y:.1f}" '
             f'stroke="{TH["kappa"]}" stroke-width="2" stroke-dasharray="3 3"/>')
    g.append(f'<text x="{ml+pw-58:.1f}" y="{rl_y-4:.1f}" font-size="9" '
             f'fill="{TH["kappa"]}">reposo {rl:.2f}</text>')
    pts = " ".join(f"{X(t):.1f},{y0 + (1.0 - v) * ph1:.1f}" for t, v in d.history)
    g.append(f'<polyline points="{pts}" fill="none" stroke="{TH["pen"]}" '
             f'stroke-width="2" stroke-linejoin="round"/>')
    # basal arrow (decay → down)
    lt, lv = d.history[-1]
    g.append(f'<line x1="{X(lt):.1f}" y1="{y0+(1.0-lv)*ph1:.1f}" x2="{X(lt):.1f}" '
             f'y2="{y0+(1.0-lv)*ph1+26:.1f}" stroke="{TH["ink"]}" '
             f'stroke-width="2.2" marker-end="url(#arr)"/>')
    g.append(f'<text x="{ml}" y="{y0+11}" font-size="11" font-weight="600" '
             f'fill="{TH["pen"]}">x(t) — satisfacción del servicio</text>')
    # shock + release rug under panel 1
    rug = y1 - 4
    for t, kind in d.events:
        cx = X(t)
        if kind == "shock":
            g.append(f'<path d="M{cx:.1f} {y0+8:.1f} l5 0 l-2.5 -7z" '
                     f'fill="{TH["bad"]}" transform="translate(0,0)"/>')
            g.append(f'<text x="{cx+7:.1f}" y="{y0+10:.1f}" font-size="9" '
                     f'fill="{TH["bad"]}">shock −{SHOCK_U}</text>')
    for t, s in sigma:
        pass  # rug drawn on panel 2

    # ── panel 2: sigma(t) ──
    sy0, sy1 = y1 + gap, y1 + gap + ph2
    smax = max(abs(s) for _, s in sigma) * 1.15 or 0.1
    smax = max(smax, CFG["spring_threshold"] * 1.3)
    def SY(v):
        return sy0 + (1.0 - (v / smax)) * ph2
    g.append(f'<rect x="{ml}" y="{sy0}" width="{pw}" height="{ph2}" '
             f'fill="{TH["panel"]}" stroke="{TH["grid"]}" stroke-width="0.6"/>')
    # theta band
    th_y = SY(-CFG["spring_threshold"])
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{SY(-CFG["spring_threshold"]):.1f}" '
             f'y2="{SY(-CFG["spring_threshold"]):.1f}" stroke="{TH["bad"]}" '
             f'stroke-width="1.4" stroke-dasharray="5 4"/>')
    g.append(f'<text x="{ml+pw-4:.1f}" y="{SY(-CFG["spring_threshold"])-4:.1f}" '
             f'text-anchor="end" font-size="9" fill="{TH["bad"]}">θ = '
             f'{CFG["spring_threshold"]}</text>')
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{SY(0):.1f}" y2="{SY(0):.1f}" '
             f'stroke="{TH["grid"]}" stroke-width="0.8"/>')
    spts = " ".join(f"{X(t):.1f},{SY(s):.1f}" for t, s in sigma)
    g.append(f'<polyline points="{spts}" fill="none" stroke="{TH["kappa"]}" '
             f'stroke-width="1.6" stroke-linejoin="round"/>')
    # release events: vertical diamonds on sigma axis
    for t, kind in d.events:
        if kind == "release":
            s_at = next((s for tt, s in sigma if tt == t), 0.0)
            cx, cy = X(t), SY(s_at)
            g.append(f'<path d="M{cx:.1f} {cy-5:.1f} l4 5 l-4 5 l-4-5z" '
                     f'fill="{TH["kappa"]}"/>')
            g.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{sy0+2:.1f}" '
                     f'y2="{sy1-2:.1f}" stroke="{TH["kappa"]}" '
                     f'stroke-width="0.7" stroke-dasharray="2 3" opacity="0.6"/>')
    g.append(f'<text x="{ml}" y="{sy0+11}" font-size="11" font-weight="600" '
             f'fill="{TH["kappa"]}">σ(t) — tensión acumulada del resorte '
             f'(◆ = TensionReleased)</text>')
    for v in (-smax, 0, smax):
        g.append(f'<text x="{ml-6:.1f}" y="{SY(v)+4:.1f}" text-anchor="end" '
                 f'font-size="10" fill="{TH["soft"]}">{v:.2f}</text>')

    # shared x axis
    ay = sy1 + 14
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{ay:.1f}" y2="{ay:.1f}" '
             f'stroke="{TH["ink"]}"/>')
    for t in range(0, tmax + 1, max(1, tmax // 8)):
        g.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{ay-3:.1f}" '
                 f'y2="{ay+3:.1f}" stroke="{TH["ink"]}"/>')
        g.append(f'<text x="{X(t):.1f}" y="{ay+16:.1f}" text-anchor="middle" '
                 f'font-size="11" fill="{TH["soft"]}">{t}</text>')
    g.append('</svg>')

    body = (f'<div class="cfg">magnet spring w=0.18 · shock −{SHOCK_U} en t={SHOCK_T} · '
            f'breach t={breach_tick(d)} · {sum(1 for _,k in d.events if k=="release")} releases</div>'
            + "".join(g))
    data = {"sigma": sigma, "trajectory": d.history, "events": d.events,
            "config": CFG, "breach": breach_tick(d)}
    with open("fig_tension_sigma.html", "w", encoding="utf-8") as fh:
        fh.write(page("Binsai — tensión σ bajo la trayectoria", body, data))
    print("fig_tension_sigma.html | releases:",
          sum(1 for _, k in d.events if k == "release"),
          "| breach:", breach_tick(d))


# ── (c) regime map λ × w ─────────────────────────────────────────────────────

def fig_regime_map():
    kappa, rho, m = CFG["kappa"], CFG["spring_release"], 0.60  # m = viable margin
    # m: distance from x* (0.70) to viability lo (0.10) — the side the drift pushes toward
    W_MAX, L_MAX = 0.45, 0.006
    width, height = 940, 560
    ml, mr, mt, mb = 60, 30, 40, 60
    pw, ph = width - ml - mr, height - mt - mb

    def X(w): return ml + (w / W_MAX) * pw
    def Y(l): return mt + (1.0 - l / L_MAX) * ph

    def frontier(w): return kappa * rho * w / math.e          # λ = κρw/e
    def deg(w):      return kappa * rho * m * math.exp(-m / w) if w > 0 else 0.0

    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
         f'width="{width}" role="img">',
         f'<rect width="{width}" height="{height}" fill="{TH["bg"]}"/>']

    ws = [i * W_MAX / 300 for i in range(1, 301)]

    # region shading (order: below deg = degenerate, between = trapped-with-escape,
    # above frontier = drift-dominant)
    above_frontier = [(w, frontier(w)) for w in ws]
    poly = " ".join(f"{X(w):.1f},{min(Y(l), mt):.1f}" for w, l in above_frontier) + \
           f" {X(W_MAX):.1f},{mt:.1f} {X(ws[0]):.1f},{mt:.1f}"
    g.append(f'<polygon points="{poly}" fill="{TH["dead"]}" fill-opacity="0.18"/>')
    mid = [(w, frontier(w), deg(w)) for w in ws]
    poly2 = " ".join(f"{X(w):.1f},{Y(min(l, L_MAX)):.1f}" for w, l, _ in mid)
    poly2 += " " + " ".join(f"{X(w):.1f},{Y(dl):.1f}" for w, _, dl in reversed(mid))
    g.append(f'<polygon points="{poly2}" fill="{TH["ok"]}" fill-opacity="0.14"/>')
    poly3 = " ".join(f"{X(w):.1f},{Y(dl):.1f}" for w, _, dl in mid)
    poly3 += f" {X(W_MAX):.1f},{Y(0):.1f} {X(ws[0]):.1f},{Y(0):.1f}"
    g.append(f'<polygon points="{poly3}" fill="{TH["warn"]}" fill-opacity="0.14"/>')

    # curves
    fpts = " ".join(f"{X(w):.1f},{Y(frontier(w)):.1f}" for w in ws)
    g.append(f'<polyline points="{fpts}" fill="none" stroke="{TH["dead"]}" '
             f'stroke-width="2.2"/>')
    dpts = " ".join(f"{X(w):.1f},{Y(min(deg(w), L_MAX)):.1f}" for w in ws)
    g.append(f'<polyline points="{dpts}" fill="none" stroke="{TH["warn"]}" '
             f'stroke-width="2.2" stroke-dasharray="7 5"/>')

    # axes
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{mt+ph}" y2="{mt+ph}" stroke="{TH["ink"]}"/>')
    g.append(f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt+ph}" stroke="{TH["ink"]}"/>')
    for wv in [0, 0.1, 0.2, 0.3, 0.4]:
        g.append(f'<text x="{X(wv):.1f}" y="{mt+ph+18:.1f}" text-anchor="middle" '
                 f'font-size="11" fill="{TH["soft"]}">{wv:.1f}</text>')
    for lv in [0, 0.002, 0.004, 0.006]:
        g.append(f'<text x="{ml-8:.1f}" y="{Y(lv)+4:.1f}" text-anchor="end" '
                 f'font-size="11" fill="{TH["soft"]}">{lv:.3f}</text>')
    g.append(f'<text x="{ml+pw:.1f}" y="{mt+ph+40:.1f}" text-anchor="end" '
             f'font-size="12" fill="{TH["ink"]}">w (alcance del resorte)</text>')
    g.append(f'<text x="{ml-40:.1f}" y="{mt-12:.1f}" font-size="12" '
             f'fill="{TH["ink"]}">λ (deriva basal)</text>')

    # region labels
    g.append(f'<text x="{X(0.32):.1f}" y="{Y(0.0055):.1f}" font-size="12" '
             f'fill="{TH["dead"]}">deriva domina — negligencia mata</text>')
    g.append(f'<text x="{X(0.20):.1f}" y="{Y(0.0033):.1f}" font-size="12" '
             f'fill="{TH["ok"]}">atrapado, escape dentro de viable</text>')
    g.append(f'<text x="{X(0.33):.1f}" y="{Y(0.0008):.1f}" font-size="12" '
             f'fill="{TH["warn"]}">escape cae en el límite — degenera a pulsátil</text>')
    g.append(f'<text x="{X(0.415):.1f}" y="{Y(frontier(0.415))-8:.1f}" font-size="10" '
             f'text-anchor="end" fill="{TH["dead"]}">λ = κρw/e</text>')
    g.append(f'<text x="{X(0.415):.1f}" y="{Y(deg(0.415))-8:.1f}" font-size="10" '
             f'text-anchor="end" fill="{TH["warn"]}">λ = κρ·m·e^(−m/w), m=0.60</text>')

    # the three points
    pts = [
        (0.18, 0.002, TH["ok"],   "A — atrapado c/ escape viable (usado en ablación B)"),
        (0.25, 0.004, TH["dead"], "B — λ > grip: muerte por negligencia (pasada 1)"),
        (0.25, 0.002, TH["warn"], "C — escape en el límite → degenerado (w=0.25)"),
    ]
    for wv, lv, col, lab in pts:
        g.append(f'<circle cx="{X(wv):.1f}" cy="{Y(lv):.1f}" r="6" fill="{col}" '
                 f'stroke="{TH["ink"]}" stroke-width="1"/>')
        g.append(f'<text x="{X(wv)+9:.1f}" y="{Y(lv)+4:.1f}" font-size="10.5" '
                 f'fill="{col}">{lab}</text>')
    g.append('</svg>')

    body = (f'<div class="cfg">κ={kappa}, ρ={rho}, margen viable m={m} '
            f'(x*={CFG["set_point"]} → límite {CFG["viability"][0]}). '
            f'Tres regiones: arriba de la frontera la deriva gana siempre; '
            f'entre las dos curvas el escape ocurre dentro del rango viable '
            f'(el régimen útil del imán); debajo, el alcance finito degenera — '
            f'w debe derivarse del contrato, no elegirse a ojo.</div>' + "".join(g))
    data = {"kappa": kappa, "rho": rho, "viable_margin": m,
            "frontier": "lambda = kappa*rho*w/e",
            "degeneracy": "lambda = kappa*rho*m*exp(-m/w)",
            "points": [{"w": w, "lambda": l, "label": lab} for w, l, _, lab in pts]}
    with open("fig_regime_map.html", "w", encoding="utf-8") as fh:
        fh.write(page("Binsai — mapa de regímenes λ×w", body, data))
    print("fig_regime_map.html")


# ── (d) pressure decomposition: level + pace + tension ───────────────────────

def fig_pressure_split():
    TICKS = 300
    d = Drive(name="metabolico", value=0.70, set_point=0.70, kappa=0.05,
              lambda_rate=0.004, basal_direction="recover",
              spring_threshold=0.10, spring_release=1.0, spring_reach=0.30,
              viability=(0.10, 0.98))
    budget = ObservedVariable(
        name="tokens", kind="budget", limit=40000.0, unit="tok",
        set_point=0.0, window=TICKS, window_start=0,
        pressure_fn="logistic", pacing_mode="ratio",
    )
    d.observed = [budget]

    consumed = 0.0
    rows = []   # (t, level, pace, tension, value)
    for t in range(TICKS):
        # work bursts: light t<100, heavy 100-200, idle 200+
        # drain 0.008/tick is deliberate: drive dips to moderate_deficit and
        # recovers — this figure shows WHERE pressure comes from, so the
        # scenario must not die (a breach would distract from the sources).
        rate = 40.0 if t < 100 else (220.0 if t < 200 else 30.0)
        consumed += rate
        budget.observe(t, consumed)
        if 100 <= t < 200:
            d.deplete(0.008)         # work drains the metabolic drive
        elif t == 220:
            d.deplete(0.05)          # small late shock
        d.update(t)
        pc = d.pressure_components()
        rows.append((t, pc["level"], pc["pace"], pc["tension"], d.value))

    width = 940
    ph_t, ph_p = 120, 150
    ml, mr, mt, gap, mb = 46, 96, 30, 14, 58
    pw = width - ml - mr
    tmax = TICKS
    height = mt + ph_t + gap + ph_p + mb

    def X(t): return ml + (t / tmax) * pw

    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
         f'width="{width}" role="img">',
         f'<rect width="{width}" height="{height}" fill="{TH["bg"]}"/>']

    # panel 1: trajectory (reuse strip renderer pieces inline, simplified)
    y0 = mt
    lo_v, hi_v = d.viability
    if lo_v > 0:
        yy = y0 + (1.0 - lo_v) * ph_t
        g.append(f'<rect x="{ml}" y="{yy:.1f}" width="{pw}" height="{y0+ph_t-yy:.1f}" '
                 f'fill="{TH["death"]}" fill-opacity="0.55"/>')
    from binsai.viz import _zone_bands, _zone_color
    for lo, hi, zn in _zone_bands(d.zones):
        yt = y0 + (1.0 - hi) * ph_t
        g.append(f'<rect x="{ml}" y="{yt:.1f}" width="{pw}" height="{(hi-lo)*ph_t:.1f}" '
                 f'fill="{_zone_color(zn, TH)}" fill-opacity="0.22"/>')
    for lim in (lo_v, hi_v):
        if 0 < lim < 1:
            yy = y0 + (1.0 - lim) * ph_t
            g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{yy:.1f}" y2="{yy:.1f}" '
                     f'stroke="{TH["dead"]}" stroke-width="2.4" stroke-dasharray="9 6"/>')
    sp_y = y0 + (1.0 - d.set_point) * ph_t
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{sp_y:.1f}" y2="{sp_y:.1f}" '
             f'stroke="{TH["ink"]}" stroke-width="1.1" stroke-dasharray="7 5"/>')
    pts = " ".join(f"{X(t):.1f},{y0+(1.0-v)*ph_t:.1f}" for t, _, _, _, v in [(r[0],0,0,0,r[4]) for r in rows] )
    g.append(f'<polyline points="{pts}" fill="none" stroke="{TH["pen"]}" '
             f'stroke-width="2" stroke-linejoin="round"/>')
    g.append(f'<text x="{ml}" y="{y0+11}" font-size="11" font-weight="600" '
             f'fill="{TH["pen"]}">metabolico — x(t)</text>')

    # panel 2: stacked areas level + pace + sigma/theta
    py0 = y0 + ph_t + gap
    pmax = 0.0
    for _, lv, pc_, ts, _ in rows:
        tot = (lv or 0.0) + (pc_ or 0.0) + abs(ts) / CFG["spring_threshold"]
        pmax = max(pmax, tot)
    pmax = max(pmax, 0.01) * 1.1

    def PY(v): return py0 + (1.0 - v / pmax) * ph_p

    def area(idx):
        # stack: layer0=level, +pace, +|sigma|/theta
        top, bot = [], []
        for t, lv, pc_, ts, _v in rows:
            l = lv or 0.0
            p = pc_ or 0.0
            s = abs(ts) / CFG["spring_threshold"]
            vals = [l, l + p, l + p + s]
            top.append((t, vals[idx]))
            bot.append((t, vals[idx - 1] if idx else 0.0))
        poly = " ".join(f"{X(t):.1f},{PY(v):.1f}" for t, v in top)
        poly += " " + " ".join(f"{X(t):.1f},{PY(v):.1f}" for t, v in reversed(bot))
        return poly

    g.append(f'<rect x="{ml}" y="{py0}" width="{pw}" height="{ph_p}" '
             f'fill="{TH["panel"]}" stroke="{TH["grid"]}" stroke-width="0.6"/>')
    cols = [TH["pen"], TH["warn"], TH["kappa"]]
    labs = ["level (tokens: nivel)", "pace (tokens: ritmo)", "σ/θ (tensión)"]
    for i in (2, 1, 0):   # draw top layer first
        g.append(f'<polygon points="{area(i)}" fill="{cols[i]}" fill-opacity="0.55"/>')
    for i, (c, lab) in enumerate(zip(cols, labs)):
        g.append(f'<rect x="{ml+8+i*230:.1f}" y="{py0+8:.1f}" width="10" height="10" '
                 f'fill="{c}" fill-opacity="0.7"/>')
        g.append(f'<text x="{ml+22+i*230:.1f}" y="{py0+17:.1f}" font-size="10.5" '
                 f'fill="{TH["ink"]}">{lab}</text>')
    g.append(f'<text x="{ml+pw-4:.1f}" y="{py0+ph_p-6:.1f}" text-anchor="end" '
             f'font-size="9" fill="{TH["soft"]}">σ normalizado por θ '
             f'(unidades distintas a presión)</text>')

    ay = py0 + ph_p + 14
    g.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{ay:.1f}" y2="{ay:.1f}" stroke="{TH["ink"]}"/>')
    for t in range(0, tmax + 1, 50):
        g.append(f'<text x="{X(t):.1f}" y="{ay+16:.1f}" text-anchor="middle" '
                 f'font-size="11" fill="{TH["soft"]}">{t}</text>')
    g.append('</svg>')

    body = ('<div class="cfg">metabolico (pull/recover λ=+0.004) observa '
            '"tokens" (budget 40k/300t, logistic). Fases: liviano t&lt;100, '
            'ráfaga t=100–200 (drena el drive vía deplete 0.008/t — baja a '
            'moderate_deficit y se recupera, sin cruzar viabilidad), reposo '
            't&gt;200. <b>Esta figura muestra de dónde viene la presión, no '
            'si el agente regula bien.</b> Las tres fuentes no se confunden: '
            'level y pace vienen del sensor, σ/θ de la dinámica autónoma.</div>'
            + "".join(g))
    data = {"rows": rows, "config": {"budget": 30000, "window": TICKS,
            "phases": {"light": [0, 100], "burst": [100, 200], "idle": [200, 300]}},
            "note": "tension plotted as |sigma|/theta"}
    with open("fig_pressure_split.html", "w", encoding="utf-8") as fh:
        fh.write(page("Binsai — descomposición de la presión", body, data))
    print("fig_pressure_split.html | max total:", round(pmax, 3))


if __name__ == "__main__":
    fig_ablation()
    fig_tension()
    fig_regime_map()
    fig_pressure_split()
