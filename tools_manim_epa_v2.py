"""
Animación de la EPA v2: tres necesidades en un espacio de viabilidad.

Uso:
    python epa_v2_sim.py                 # genera epa_v2_sim.json con datos reales
    manim -qh -o epa_v2_viability.mp4 tools_manim_epa_v2.py EPAViability

Qué muestra, y por qué cada cosa:
  · el cubo exterior punteado es el conjunto viable K: salir de ahí es muerte operativa
  · las capas concéntricas son las zonas algedónicas: verde en el centro, luego amarillo,
    ámbar y rojo hacia cada límite
  · el elipsoide translúcido es el ALCANCE del resorte: dentro de él el agarre alcanza para
    compensar la deriva; fuera, ya no. Su borde es el punto de no retorno d*
  · la línea que une el punto con el origen es el RESORTE: su grosor y su opacidad son el
    agarre instantáneo κ_ef·d·e^(−|d|/w). Cuando el sistema se aleja, la línea se apaga
  · las flechas en los ejes son la DIRECCIÓN BASAL de cada necesidad: hacia dónde va sola
  · los tres paneles laterales son las mismas trayectorias como series de tiempo
"""
import json
import numpy as np
from manim import *

# ───────────────────────────── datos ─────────────────────────────
D = json.load(open("epa_v2_sim.json"))
T = np.array(D["t"])
X = np.array(D["x"])                     # (3, n)
NAMES = D["names"]
LIMIT = D["limit"]
ZONES = D["zones"]                       # [0.33, 0.55, 0.80]
DSTAR = D["d_star"]
SHOCK_T = D["shock_t"]
DEAD_T = D.get("dead_at")
DEAD_I = D.get("dead_drive", 0)
BASAL = [-1, +1, -1]                     # dirección basal: decae / recupera / decae

# ──────────────────────────── paleta ─────────────────────────────
BG = "#0e1117"
INK = "#e8e6e0"
DIM = "#98a1b2"
GREEN, YELLOW, AMBER, RED = "#4c8f73", "#9c8a3e", "#b57a33", "#b34b3c"
ACCENT = "#c9bb92"
DRIVE_COLORS = ["#5fb0a6", "#d08a54", "#8f7fb8"]
SCALE = 2.6                              # unidades de escena por unidad de necesidad


def to_scene(p):
    return np.array([p[0], p[1], p[2]]) * SCALE


class EPAViability(ThreeDScene):
    def construct(self):
        self.camera.background_color = BG
        self.set_camera_orientation(phi=68 * DEGREES, theta=-55 * DEGREES, zoom=0.85)

        # ── ejes y punto de equilibrio ──────────────────────────
        axes = ThreeDAxes(
            x_range=[-LIMIT, LIMIT, 0.5], y_range=[-LIMIT, LIMIT, 0.5],
            z_range=[-LIMIT, LIMIT, 0.5],
            x_length=2 * LIMIT * SCALE, y_length=2 * LIMIT * SCALE,
            z_length=2 * LIMIT * SCALE,
            axis_config={"stroke_color": DIM, "stroke_width": 1.2,
                         "include_ticks": False},
        )
        origin = Dot3D(ORIGIN, radius=0.05, color=ACCENT)

        labels = VGroup()
        for i, (name, col) in enumerate(zip(NAMES, DRIVE_COLORS)):
            pos = np.zeros(3)
            pos[i] = LIMIT * SCALE * 1.12
            lab = Text(name, font_size=22, color=col).move_to(pos)
            labels.add(lab)

        # ── zonas algedónicas: capas concéntricas ───────────────
        shells = VGroup()
        for frac, col, op in [(ZONES[0], GREEN, 0.10), (ZONES[1], YELLOW, 0.07),
                              (ZONES[2], AMBER, 0.06), (1.0, RED, 0.05)]:
            cube = Cube(side_length=2 * frac * LIMIT * SCALE,
                        fill_color=col, fill_opacity=op,
                        stroke_color=col, stroke_width=0.6, stroke_opacity=0.35)
            shells.add(cube)

        # ── el conjunto viable K ────────────────────────────────
        viable = Cube(side_length=2 * LIMIT * SCALE, fill_opacity=0,
                      stroke_color=RED, stroke_width=2.0)
        k_label = Text("K · conjunto viable", font_size=20, color=RED)

        # ── alcance del resorte: hasta dónde el agarre alcanza ──
        reach = Sphere(radius=1, resolution=(24, 24),
                       fill_color=ACCENT, fill_opacity=0.05,
                       stroke_color=ACCENT, stroke_width=0.5, stroke_opacity=0.35)
        reach.stretch_to_fit_width(2 * DSTAR[0] * SCALE)
        reach.stretch_to_fit_depth(2 * DSTAR[1] * SCALE)
        reach.stretch_to_fit_height(2 * DSTAR[2] * SCALE)

        # ── flechas de dirección basal sobre cada eje ───────────
        basal = VGroup()
        for i, (sgn, col) in enumerate(zip(BASAL, DRIVE_COLORS)):
            start, end = np.zeros(3), np.zeros(3)
            start[i] = sgn * 0.40 * LIMIT * SCALE
            end[i] = sgn * 0.68 * LIMIT * SCALE
            basal.add(Arrow3D(start, end, color=col, thickness=0.012,
                              base_radius=0.05, height=0.18))

        self.add(axes, shells, viable, origin, reach, basal)
        self.add_fixed_orientation_mobjects(*labels)

        # ── paneles 2D, fijos en pantalla ───────────────────────
        panels, panel_dots, panel_curves = VGroup(), [], []
        for i, col in enumerate(DRIVE_COLORS):
            ax = Axes(x_range=[0, T[-1], 10], y_range=[-1.1, 1.1, 0.5],
                      x_length=3.2, y_length=1.25,
                      axis_config={"stroke_color": "#39404f", "stroke_width": 1.2,
                                   "include_ticks": False, "include_tip": False})
            ax.to_corner(UR).shift(DOWN * (1.35 + i * 1.75) + LEFT * 0.2)
            bands = VGroup()
            for lo, hi, c, o in [(-ZONES[0], ZONES[0], GREEN, .22),
                                 (ZONES[0], ZONES[1], YELLOW, .20),
                                 (-ZONES[1], -ZONES[0], YELLOW, .20),
                                 (ZONES[1], ZONES[2], AMBER, .22),
                                 (-ZONES[2], -ZONES[1], AMBER, .22),
                                 (ZONES[2], 1.1, RED, .24),
                                 (-1.1, -ZONES[2], RED, .24)]:
                p0, p1 = ax.c2p(0, lo), ax.c2p(T[-1], hi)
                bands.add(Rectangle(width=abs(p1[0] - p0[0]), height=abs(p1[1] - p0[1]),
                                    fill_color=c, fill_opacity=o, stroke_width=0)
                          .move_to((p0 + p1) / 2))
            name = Text(NAMES[i], font_size=16, color=col).next_to(ax, UP, buff=0.06).align_to(ax, LEFT)
            curve = VMobject(stroke_color=col, stroke_width=2.2)
            dot = Dot(ax.c2p(T[0], X[i][0]), radius=0.045, color=INK)
            panels.add(VGroup(bands, ax, name))
            panel_curves.append((ax, curve))
            panel_dots.append(dot)
            self.add_fixed_in_frame_mobjects(bands, ax, name, curve, dot)

        # ── textos del relato ───────────────────────────────────
        # OJO: add_fixed_in_frame_mobjects registra los SUBmobjects que
        # existen al agregar. become()/set_value() los reemplaza y los nuevos
        # quedan fuera del registro → se renderizan como objetos 3D. Por eso
        # el texto fijo se reemplaza entero (remove + re-add), nunca se muta.
        title_holder, clock_holder = [None], [None]

        def narrate(t1, t2):
            t_ = Text(t1, font_size=30, color=INK).to_corner(UL).shift(DOWN * 0.1)
            s_ = Text(t2, font_size=19, color=DIM).next_to(t_, DOWN, aligned_edge=LEFT, buff=0.12)
            if title_holder[0] is not None:
                self.remove_fixed_in_frame_mobjects(*title_holder[0])
                self.remove(*title_holder[0])
            self.add_fixed_in_frame_mobjects(t_, s_)
            title_holder[0] = (t_, s_)

        def set_clock(hh):
            c = Text(f"t = {hh} h", font_size=18, color=DIM).to_corner(DL)
            if clock_holder[0] is not None:
                self.remove_fixed_in_frame_mobjects(clock_holder[0])
                self.remove(clock_holder[0])
            self.add_fixed_in_frame_mobjects(c)
            clock_holder[0] = c

        set_clock(0)
        self.add_fixed_in_frame_mobjects(k_label)
        k_label.to_corner(DR).shift(UP * 0.1)

        # ── trayectoria y cabeza ────────────────────────────────
        path = VMobject(stroke_color=DRIVE_COLORS[0], stroke_width=3.5)
        path.set_points_as_corners([to_scene(X[:, 0]), to_scene(X[:, 0])])
        head = Dot3D(to_scene(X[:, 0]), radius=0.09, color=INK)
        spring = Line3D(ORIGIN, to_scene(X[:, 0]), thickness=0.012, color=ACCENT)
        self.add(path, spring, head)

        n = X.shape[1]
        prog = ValueTracker(0)

        def grip_of(x):
            """Agarre instantáneo, normalizado: se apaga al salir del alcance."""
            d = np.linalg.norm(x)
            dstar = float(np.mean(DSTAR))
            w = dstar / max(1e-6, np.log(max(1.0001, 3.0)))   # sólo para la forma visual
            return float(np.exp(-d / max(0.12, w)))

        def update_all(mob, dt):
            k = int(np.clip(prog.get_value(), 0, n - 1))
            pts = [to_scene(X[:, j]) for j in range(max(1, k))]
            if len(pts) > 1:
                path.set_points_as_corners(pts)
            p = to_scene(X[:, k])
            head.move_to(p)
            # el resorte: se apaga cuando el agarre se pierde
            g = grip_of(X[:, k])
            spring.become(Line3D(ORIGIN, p, thickness=0.004 + 0.016 * g, color=ACCENT))
            spring.set_opacity(0.15 + 0.75 * g)
            t = T[k]
            # color del rastro según el momento
            col = DRIVE_COLORS[0] if t < SHOCK_T else (AMBER if (DEAD_T and t < DEAD_T) else RED)
            path.set_stroke(col)
            if int(t) != update_all.last_clock:
                update_all.last_clock = int(t)
                set_clock(int(t))
            for i, ((ax, curve), dot) in enumerate(zip(panel_curves, panel_dots)):
                ppts = [ax.c2p(T[j], X[i][j]) for j in range(max(2, k))]
                curve.set_points_as_corners(ppts)
                dot.move_to(ax.c2p(T[k], X[i][k]))

        update_all.last_clock = -1
        path.add_updater(update_all)

        # ── momento 1: regulación ───────────────────────────────
        narrate("1 · Regulación",
                "dentro del alcance del resorte, las necesidades oscilan cerca del equilibrio")
        self.begin_ambient_camera_rotation(rate=0.045)
        k_shock = int(np.searchsorted(T, SHOCK_T))
        self.play(prog.animate.set_value(k_shock), run_time=9, rate_func=linear)

        # ── momento 2: el golpe cruza el punto de no retorno ────
        narrate("2 · El golpe cruza el punto de no retorno",
                "más allá de d* el agarre ya no compensa la deriva basal")
        self.play(Indicate(reach, color=RED, scale_factor=1.03), run_time=1.2)
        k_end = n - 1
        self.play(prog.animate.set_value(k_end), run_time=8, rate_func=linear)

        # ── momento 3: muerte operativa ─────────────────────────
        if DEAD_T:
            narrate("3 · Muerte operativa",
                    f"{NAMES[DEAD_I]} toca el límite de viabilidad a las {DEAD_T} h")
            self.play(Flash(head, color=RED, line_length=0.35, num_lines=18,
                            flash_radius=0.5), run_time=1.0)
            self.play(viable.animate.set_stroke(RED, width=4.5), run_time=0.8)
        self.wait(2.0)
        self.stop_ambient_camera_rotation()
