"""
Vista previa del diseño de la animación (matplotlib, no Manim).
Sirve para validar la geometría y el relato antes de renderizar en Manim.
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
from itertools import product

D = json.load(open("epa_v2_sim.json"))
T = np.array(D["t"])
X = np.array(D["x"])          # (3, n)
NAMES = D["names"]
LIM = D["limit"]
ZON = D["zones"]              # 0.33 / 0.55 / 0.80
SHOCK_T = D["shock_t"]
DEAD = D.get("dead_at")

BG = "#0e1117"
INK = "#e8e6e0"
DIM = "#98a1b2"
COL = ["#5fb0a6", "#d08a54", "#8f7fb8"]
ZC = [("#4c8f73", .10), ("#9c8a3e", .07), ("#b57a33", .06), ("#b34b3c", .05)]

plt.rcParams.update({"figure.facecolor": BG, "savefig.facecolor": BG,
                     "text.color": INK, "axes.labelcolor": DIM,
                     "xtick.color": DIM, "ytick.color": DIM, "font.size": 9})


def cube_faces(r):
    """Las seis caras de un cubo de semilado r, para dibujar las capas de zona."""
    faces = []
    for axis, sign in product(range(3), (-1, 1)):
        pts = []
        for a, b in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            p = [0, 0, 0]
            p[axis] = sign * r
            others = [i for i in range(3) if i != axis]
            p[others[0]] = a * r
            p[others[1]] = b * r
            pts.append(p)
        faces.append(np.array(pts))
    return faces


fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
ax3 = fig.add_axes([0.02, 0.04, 0.60, 0.92], projection="3d")
ax3.set_facecolor(BG)
panels = [fig.add_axes([0.68, 0.70 - i * 0.30, 0.29, 0.22]) for i in range(3)]

# capas de zona, de la más externa a la más interna
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
for r, (c, a) in zip([LIM, ZON[2] * LIM, ZON[1] * LIM, ZON[0] * LIM], ZC[::-1]):
    pc = Poly3DCollection(cube_faces(r), facecolor=c, alpha=a,
                          edgecolor=c if r == LIM else "none", linewidths=0.8)
    ax3.add_collection3d(pc)

ax3.set_xlim(-LIM, LIM); ax3.set_ylim(-LIM, LIM); ax3.set_zlim(-LIM, LIM)
ax3.set_xlabel(NAMES[0], color=COL[0]); ax3.set_ylabel(NAMES[1], color=COL[1])
ax3.set_zlabel(NAMES[2], color=COL[2])
ax3.grid(False)
for pane in (ax3.xaxis, ax3.yaxis, ax3.zaxis):
    pane.set_pane_color((0, 0, 0, 0))
    pane.line.set_color(DIM)
ax3.scatter([0], [0], [0], s=22, color="#c9bb92", marker="+")

trail, = ax3.plot([], [], [], lw=2.0, color=COL[0], alpha=.95)
head = ax3.scatter([], [], [], s=60, color=INK, depthshade=False)
title = fig.text(0.03, 0.965, "", fontsize=13, color=INK)
sub = fig.text(0.03, 0.935, "", fontsize=10, color=DIM)

lines = []
for i, p in enumerate(panels):
    p.set_facecolor("#151a23")
    p.axhspan(-LIM, -ZON[2] * LIM, color=ZC[3][0], alpha=.28)
    p.axhspan(ZON[2] * LIM, LIM, color=ZC[3][0], alpha=.28)
    p.axhspan(-ZON[2] * LIM, -ZON[1] * LIM, color=ZC[2][0], alpha=.28)
    p.axhspan(ZON[1] * LIM, ZON[2] * LIM, color=ZC[2][0], alpha=.28)
    p.axhspan(-ZON[1] * LIM, -ZON[0] * LIM, color=ZC[1][0], alpha=.28)
    p.axhspan(ZON[0] * LIM, ZON[1] * LIM, color=ZC[1][0], alpha=.28)
    p.axhspan(-ZON[0] * LIM, ZON[0] * LIM, color=ZC[0][0], alpha=.30)
    p.axhline(0, color="#c9bb92", lw=.9)
    p.axhline(D["d_star"][i], color=INK, lw=.7, ls=":")
    p.axhline(-D["d_star"][i], color=INK, lw=.7, ls=":")
    p.set_xlim(0, T[-1]); p.set_ylim(-1.1, 1.1)
    p.set_title(NAMES[i], color=COL[i], fontsize=10, loc="left", pad=3)
    ln, = p.plot([], [], lw=1.6, color=COL[i])
    lines.append(ln)
    for s in p.spines.values():
        s.set_color("#262e3b")

STEP = 2
FRAMES = len(T) // STEP


def update(f):
    k = min(len(T) - 1, f * STEP)
    trail.set_data(X[0, :k], X[1, :k])
    trail.set_3d_properties(X[2, :k])
    head._offsets3d = ([X[0, k]], [X[1, k]], [X[2, k]])
    for i, ln in enumerate(lines):
        ln.set_data(T[:k], X[i, :k])
    ax3.view_init(elev=20 + 6 * np.sin(f / 60), azim=-60 + f * 0.45)
    t = T[k]
    if t < SHOCK_T:
        title.set_text("1 · Regulación")
        sub.set_text("las necesidades oscilan cerca del punto de equilibrio: el resorte alcanza")
        trail.set_color(COL[0])
    elif DEAD and t < DEAD:
        title.set_text("2 · El golpe cruza el punto de no retorno")
        sub.set_text("más allá de d* el agarre del resorte ya no compensa la deriva basal")
        trail.set_color("#b57a33")
    else:
        title.set_text("3 · Muerte operativa")
        sub.set_text(f"{NAMES[D['dead_drive']]} toca el límite de viabilidad a las {DEAD} h")
        trail.set_color("#b34b3c")
    return trail, head, *lines


anim = FuncAnimation(fig, update, frames=FRAMES, interval=40, blit=False)
anim.save("preview_epa_v2.mp4", writer=FFMpegWriter(fps=25, bitrate=2600))
print("listo: preview_epa_v2.mp4", FRAMES, "cuadros")
