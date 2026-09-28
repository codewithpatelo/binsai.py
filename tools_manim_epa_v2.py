# -*- coding: utf-8 -*-
"""EPA v2 viability-space animation — Manim scene driven by a REAL Binsai run.

Three needs (one per axis): servicio (push/decay), metabolica (pull/recover),
social (push/decay). The translucent box is the viability set K — leaving the
box is operational death. Nested shells show the algedonic zones around the
equilibrium (green core → amber → red at the walls). The scene narrates three
moments:

    1. oscillation inside the green zone (damped second-order waves);
    2. an impulsive shock pushing 'servicio' beyond the magnetic reach
       |d| > d* — the spring can no longer hold it;
    3. the cascade to the wall: basal drift wins and x hits L⁻ = death.

The 1D trajectories are drawn at the side, synchronized with the 3D point.

Data provenance: `run_simulation()` below is a real Drive simulation
(spring="magnetic-2nd", docs/paov2.tex); the run is also dumped to
epa_v2_sim.json next to this script — nothing in the animation is invented.

Render (from repo root):

    manim -ql --format gif tools_manim_epa_v2.py EPAv2Scene \
        -o epa_v2_viability.gif
    # output lands in media/videos/tools_manim_epa_v2/480p15/EPAv2Scene.gif
"""
import json
import sys

import numpy as np

sys.path.insert(0, "src")
from binsai import Drive

from manim import (
    DOWN, GREEN, LEFT, ORANGE, RED, TEAL, UP, WHITE, YELLOW,
    Dot3D, FadeIn, FadeOut, Line, Prism, Rectangle, Text, ThreeDAxes,
    ThreeDScene, ValueTracker, VGroup, VMobject,
)

# ── Real Binsai run ──────────────────────────────────────────────────────────

SHOCK_T = 240          # impulse tick — moment 2
TICKS = 620            # total run — the cascade must reach the wall
DT = 1.0


def run_simulation() -> dict:
    """Three needs, pure neglect + one impulsive shock on 'servicio'.

    Servicio: f=0 — survives neglect forever inside the stable regime, but
    the shock lands it beyond d* (no-return) → escapes to the wall.
    Metabolica and social: same regime, no shock — they stay inside.
    """
    w_svc = Drive.design_spring_reach(0.05, 0.001, 0.35)   # d* = 0.35
    w_soc = Drive.design_spring_reach(0.05, 0.0006, 0.30)
    # displaced starts → damped waves into the green zone (moment 1 visible)
    drives = {
        "servicio": Drive(name="servicio", value=0.60, set_point=0.70,
                          kappa=0.05, lambda_rate=0.001,
                          basal_direction="decay", spring="magnetic-2nd",
                          spring_reach=w_svc, damping=0.06,
                          spring_fatigue=0.0, viability=(0.10, 0.98)),
        "metabolica": Drive(name="metabolica", value=0.78, set_point=0.70,
                            kappa=0.10, lambda_rate=0.001,
                            basal_direction="recover", spring="magnetic-2nd",
                            spring_reach=Drive.design_spring_reach(
                                0.10, 0.001, 0.20),
                            damping=0.10, spring_fatigue=0.0,
                            viability=(0.10, 0.98)),
        "social": Drive(name="social", value=0.64, set_point=0.70,
                        kappa=0.05, lambda_rate=0.0006,
                        basal_direction="decay", spring="magnetic-2nd",
                        spring_reach=w_soc, damping=0.08,
                        spring_fatigue=0.0, viability=(0.10, 0.98)),
    }
    traj = {k: [] for k in drives}
    breach = None
    for t in range(TICKS):
        if t == SHOCK_T:
            drives["servicio"].impulse(-0.50, expected=-0.50)
        for k, d in drives.items():
            d.update(t)
            traj[k].append(d.value)
        if breach is None and drives["servicio"].value <= 0.10:
            breach = t
    out = {"ticks": TICKS, "shock_t": SHOCK_T, "breach_t": breach,
           "w_servicio": w_svc, "d_star": 0.35, "traj": traj}
    with open("epa_v2_sim.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print(f"[sim] servicio breach @ {breach} | w={w_svc:.3f} d*=0.35")
    return out


SIM = run_simulation()

NAMES = ["servicio", "metabolica", "social"]
COLORS = {"servicio": YELLOW, "metabolica": TEAL, "social": ORANGE}
LO, HI = 0.10, 0.98
SP = 0.70


class EPAv2Scene(ThreeDScene):
    def construct(self):
        np.random.seed(0)
        traj = np.array([SIM["traj"][k] for k in NAMES])          # (3, T)
        T = SIM["ticks"]

        # ── 3D viability space ──────────────────────────────────────────
        axes = ThreeDAxes(
            x_range=[0, 1, 0.25], y_range=[0, 1, 0.25], z_range=[0, 1, 0.25],
            x_length=5.4, y_length=5.4, z_length=5.4,
        )
        axes.shift(LEFT * 1.6)
        self.set_camera_orientation(phi=68 * np.pi / 180,
                                    theta=-52 * np.pi / 180)

        def p3(x, y, z):
            return axes.c2p(x, y, z)

        # viability box K — translucent
        side = HI - LO
        mid = (LO + HI) / 2
        k_box = Prism(dimensions=[side * 5.4, side * 5.4, side * 5.4])
        k_box.move_to(p3(mid, mid, mid))
        k_box.set_fill(WHITE, opacity=0.06)
        k_box.set_stroke(WHITE, width=1.2, opacity=0.55)

        # algedonic shells around the equilibrium — intensity toward walls
        shells = VGroup()
        for half, color, op in ((0.10, GREEN, 0.14), (0.30, YELLOW, 0.08),
                                (0.44, RED, 0.05)):
            sh = Prism(dimensions=[half * 2 * 5.4] * 3)
            sh.move_to(p3(SP, SP, SP))
            sh.set_fill(color, opacity=op)
            sh.set_stroke(color, width=0.8, opacity=0.4)
            shells.add(sh)

        self.add(axes, k_box, shells)

        axis_labels = VGroup(*[
            Text(n, font_size=20).move_to(p)
            for n, p in (("servicio", axes.c2p(1.12, 0, 0)),
                         ("metabolica", axes.c2p(0, 1.14, 0)),
                         ("social", axes.c2p(0, 0, 1.14)))
        ])
        # fixed ORIENTATION (billboard) at their 3D anchor — they rotate with
        # the scene instead of floating pinned to the camera
        self.add_fixed_orientation_mobjects(*axis_labels)

        # equilibrium marker (x*, x*, x*)
        eq = Dot3D(point=p3(SP, SP, SP), color=GREEN, radius=0.055)
        self.add(eq)

        # ── trajectory + moving dot, driven by a tick tracker ───────────
        tick = ValueTracker(0.0)
        pts3 = [p3(*traj[:, i]) for i in range(T)]

        dot = Dot3D(point=pts3[0], color=WHITE, radius=0.14)
        dot.add_updater(
            lambda m: m.move_to(pts3[min(int(tick.get_value()), T - 1)]))
        path = VMobject(stroke_color=WHITE, stroke_width=4)
        path.add_updater(lambda m: m.set_points_as_corners(
            pts3[: max(2, int(tick.get_value()))]))
        self.add(path, dot)

        # ── 1D side panels (fixed in frame) ──────────────────────────────
        panel = VGroup()
        traces = {}
        dots1d = {}
        for i, name in enumerate(NAMES):
            y0 = 2.4 - i * 1.35
            rect = Rectangle(width=3.6, height=1.05, stroke_color=WHITE,
                             stroke_width=0.7, fill_opacity=0.03)
            rect.move_to([3.7, y0, 0])
            lab = Text(name, font_size=15, color=COLORS[name])
            lab.next_to(rect, UP, buff=0.04).align_to(rect, LEFT)
            # viability lines inside panel
            def ymap(v):
                return y0 + (v - LO) / (HI - LO) * 1.05 - 0.525
            lo_ln = Line(rect.get_left(), rect.get_right())
            lo_ln.set_y(ymap(LO)); lo_ln.set_stroke(RED, width=0.8, opacity=0.7)
            sp_ln = Line(rect.get_left(), rect.get_right())
            sp_ln.set_y(ymap(SP)); sp_ln.set_stroke(GREEN, width=0.6,
                                                   opacity=0.45)
            line = VMobject(stroke_color=COLORS[name], stroke_width=1.8)
            xs = np.linspace(rect.get_left()[0], rect.get_right()[0], T)

            def mk_updater(ln, xs_, ys_, i_):
                def upd(m):
                    k = max(2, int(tick.get_value()))
                    pts = np.column_stack(
                        [xs_[:k], ys_[:k], np.zeros(k)])
                    m.set_points_as_corners(pts)
                return upd
            ys = np.array([ymap(v) for v in traj[i]])
            line.add_updater(mk_updater(line, xs, ys, i))
            d1 = Dot3D(point=[xs[0], ys[0], 0], color=COLORS[name],
                       radius=0.05)

            def dot_upd(m, xs_=xs, ys_=ys):
                k = min(int(tick.get_value()), T - 1)
                m.move_to([xs_[k], ys_[k], 0])
            d1.add_updater(dot_upd)
            traces[name] = line
            dots1d[name] = d1
            panel.add(rect, lab, lo_ln, sp_ln)
        self.add_fixed_in_frame_mobjects(panel, *traces.values(),
                                         *dots1d.values())

        # ── narrated moments ────────────────────────────────────────────
        def caption(txt, color=WHITE):
            c = Text(txt, font_size=21, color=color)
            c.to_edge(DOWN).shift(UP * 0.25)
            return c

        cap1 = caption("1 · el sistema oscila dentro de la zona verde — "
                       "resorte magnético, segundo orden", GREEN)
        cap2 = caption("2 · shock −0.50 en servicio: |d| > d* — "
                       "fuera del alcance del resorte", ORANGE)
        cap3 = caption("3 · cascada a la pared: la deriva basal gana — "
                       "salir de K es la muerte operativa", RED)

        self.add_fixed_in_frame_mobjects(cap1)
        self.begin_ambient_camera_rotation(rate=0.10)

        SEG1 = SHOCK_T
        self.play(tick.animate.set_value(SEG1),
                  run_time=7, rate_func=lambda s: s)
        self.play(FadeOut(cap1), FadeIn(cap2))
        self.add_fixed_in_frame_mobjects(cap2)
        # flash the shock
        self.play(dot.animate.scale(3.2), run_time=0.35)
        self.play(dot.animate.scale(1 / 3.2), run_time=0.35)
        self.play(tick.animate.set_value(SIM["breach_t"]),
                  run_time=9, rate_func=lambda s: s)
        self.play(FadeOut(cap2), FadeIn(cap3))
        self.add_fixed_in_frame_mobjects(cap3)
        self.play(tick.animate.set_value(T - 1),
                  run_time=5, rate_func=lambda s: s)
        # dead — hold, then fade for the loop
        dot.clear_updaters()
        dot.set_color(RED)
        self.wait(1.2)
        self.play(FadeOut(path), FadeOut(dot), FadeOut(cap3), run_time=0.8)


if __name__ == "__main__":
    pass  # render with: manim -ql --format gif tools_manim_epa_v2.py EPAv2Scene
