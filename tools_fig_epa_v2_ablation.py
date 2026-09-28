# -*- coding: utf-8 -*-
"""EPA v2 ablation: three dynamics x two scenarios x fatigue on/off.

Arms (identical initial conditions — only the spring/dynamic differs):
    linear            — legacy first-order damper
    pulsatile w=inf   — legacy integrate-and-release, infinite reach
    magnetic-2nd f=0  — second-order magnetic spring, finite reach, no fatigue
    magnetic-2nd f>0  — same + allostatic fatigue (kappa_eff = kappa e^{-f Lambda})

Scenarios: A = pure basal neglect, B = neglect + impulsive shock at t=150.

    python tools_fig_epa_v2_ablation.py  ->  fig_ablation_epa_v2.html

Predictions were written BEFORE the run in docs/ABLATION-EPA-V2.md.
"""
import json
import math
import sys

sys.path.insert(0, "src")
from binsai import Drive
from binsai.viz import timeline_svg, _THEMES

TH = _THEMES["dark"]

LAM = 0.001
KAPPA = 0.05
D_STAR = 0.35
W = Drive.design_spring_reach(KAPPA, LAM, D_STAR)

CFG = dict(
    value=0.70, set_point=0.70, kappa=KAPPA, lambda_rate=LAM,
    basal_direction="decay", viability=(0.10, 0.98),
    damping=0.10, dt=1.0, spring_fatigue=0.0, allostatic_recovery=0.002,
    spring_threshold=0.12, spring_release=1.0,
)
TICKS_A, TICKS_B, SHOCK_T, SHOCK_X = 1200, 800, 150, -0.50

VARIANTS = [
    ("linear",         dict(spring="linear")),
    ("pulsatile_w_inf", dict(spring="pulsatile", spring_reach=float("inf"))),
    ("magnet_f0",      dict(spring="magnetic-2nd", spring_reach=W,
                            spring_fatigue=0.0)),
    ("magnet_f010",    dict(spring="magnetic-2nd", spring_reach=W,
                            spring_fatigue=0.10)),
]


def make_drive(name, extra):
    return Drive(name=name, history_limit=0, **{**CFG, **extra})


def run(drive, ticks, shock=None):
    series = {"x": [], "v": [], "lam_load": []}
    for t in range(ticks):
        if shock and t == shock[0]:
            drive.impulse(shock[1], expected=shock[1])
            drive.record_event(t, "shock")
        drive.update(t)
        series["x"].append((t, drive.value))
        series["v"].append((t, drive.velocity))
        series["lam_load"].append((t, drive.allostatic_load))
    return series


def breach_tick(drive):
    lo, hi = drive.viability
    for t, v in drive.history:
        if v <= lo or v >= hi:
            return t
    return None


def velocity_svg(series, tmax, title):
    """Small v(t) panel — the second-order signature."""
    width, ph = 940, 90
    ml, mr, mt, mb = 46, 30, 24, 26
    pw = width - ml - mr
    vmax = max(abs(v) for _, v in series) or 1e-3
    vmax *= 1.2
    def X(t): return ml + (t / tmax) * pw
    def Y(v): return mt + (1.0 - (v + vmax) / (2 * vmax)) * ph
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {mt+ph+mb}" '
         f'width="{width}" role="img">',
         f'<rect width="{width}" height="{mt+ph+mb}" fill="{TH["bg"]}"/>',
         f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" '
         f'fill="{TH["panel"]}" stroke="{TH["grid"]}" stroke-width="0.6"/>',
         f'<line x1="{ml}" x2="{ml+pw}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" '
         f'stroke="{TH["grid"]}" stroke-width="0.8"/>']
    pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in series)
    g.append(f'<polyline points="{pts}" fill="none" stroke="{TH["kappa"]}" '
             f'stroke-width="1.6" stroke-linejoin="round"/>')
    g.append(f'<text x="{ml}" y="{mt-8}" font-size="11" font-weight="600" '
             f'fill="{TH["kappa"]}">{title}</text>')
    g.append(f'<text x="{ml-6:.1f}" y="{Y(vmax)+4:.1f}" text-anchor="end" '
             f'font-size="10" fill="{TH["soft"]}">{vmax:.2f}</text>')
    g.append(f'<text x="{ml-6:.1f}" y="{Y(-vmax)+4:.1f}" text-anchor="end" '
             f'font-size="10" fill="{TH["soft"]}">-{vmax:.2f}</text>')
    g.append('</svg>')
    return "".join(g)


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


def main():
    data = {"config": {k: v for k, v in CFG.items()},
            "w": W, "d_star": D_STAR,
            "grip_G": KAPPA * W / math.e,
            "scenarios": {"A": {}, "B": {}}}
    print(f"w = {W:.4f}   G = kappa*w/e = {KAPPA*W/math.e:.4f}  vs lam = {LAM}")

    bodies = {}
    for scen, ticks, shock in (("A", TICKS_A, None),
                               ("B", TICKS_B, (SHOCK_T, SHOCK_X))):
        drives = []
        for label, extra in VARIANTS:
            d = make_drive(f"{scen}_{label}", extra)
            ser = run(d, ticks, shock=shock)
            drives.append(d)
            data["scenarios"][scen][label] = {
                "trajectory": d.history, "velocity": ser["v"],
                "allostatic": ser["lam_load"],
                "events": d.events, "breach": breach_tick(d),
            }
        breaches = {lbl: breach_tick(d) for lbl, d in
                    zip([v[0] for v in VARIANTS], drives)}
        print(f"scenario {scen}: breaches = {breaches}")

        svg = timeline_svg(
            drives, width=940, strip_height=130, ghost_ticks=0,
            title=(f"Escenario {scen} — " +
                   ("negligencia basal pura" if scen == "A" else
                    f"negligencia + impulso {SHOCK_X} en t={SHOCK_T}")),
        )
        # velocity panels for the two magnetic arms (signature of 2nd order)
        vpanels = ""
        for label, d in zip([v[0] for v in VARIANTS], drives):
            if label.startswith("magnet"):
                vpanels += velocity_svg(
                    data["scenarios"][scen][label]["velocity"], ticks,
                    f"v(t) — {label}")
        bodies[scen] = svg + vpanels

    cfg_txt = (
        f'x0={CFG["value"]}  v0=0  x*={CFG["set_point"]}  '
        f'lam={-LAM} (decay)  kappa={KAPPA}  c={CFG["damping"]}  '
        f'w={W:.3f} (d*={D_STAR})  f=0/0.10  rho_L={CFG["allostatic_recovery"]}  '
        f'dt={CFG["dt"]}  viability={CFG["viability"]}\n'
        f'G = kappa*w/e = {KAPPA*W/math.e:.4f} > lam={LAM} -> regimen estable '
        f'con escape dentro de viable\n'
        f'Brazos: linear (legacy damper) / pulsatile w=inf (legacy) / '
        f'magnetic-2nd f=0 / magnetic-2nd f=0.10 — mismas CI, solo cambia '
        f'la dinamica.'
    )
    body = (f'<div class="cfg">{cfg_txt}</div>'
            f'<h2>A — negligencia pura</h2>{bodies["A"]}'
            f'<h2>B — negligencia + shock</h2>{bodies["B"]}')
    html = page("Binsai — ablación EPA v2 (linear / pulsatile / magnetic-2nd)",
                body, data)
    with open("fig_ablation_epa_v2.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("fig_ablation_epa_v2.html")


if __name__ == "__main__":
    main()
