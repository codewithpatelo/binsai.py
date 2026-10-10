"""Viability-space artifact — record real Drive runs, render the 3D space.

Two layers:

- :func:`record_viability_run` runs real :class:`~binsai.drives.Drive`
  objects (``spring="magnetic-2nd"`` dynamics included) and returns a
  :class:`ViabilityRecording` — the trajectory of the joint system in the
  normalized deviation space ``u ∈ [−1, 1]`` where each axis is one drive
  and ``|u| = 1`` is the viability wall. Stdlib only.
- :func:`render_viability_space` turns a recording into an MP4/GIF
  animation with matplotlib (optional, ``pip install binsai[analysis]``):
  the viable cube K, concentric algedonic zone layers, the spring-reach
  ellipsoid bounded at d*, a spring line whose width/opacity are the
  instantaneous grip κ_eff·|u|·e^(−|u|/w)/λ, basal-direction arrows, and
  one synchronized 1D panel per drive.

Nothing here is scripted: narration (regulation → shock beyond d* →
operational death) is derived from the recording's ``shock_t``/``dead_at``
metadata, so a run without shocks or without death renders what it is.

Example::

    from binsai import Drive, record_viability_run, render_viability_space

    rec = record_viability_run([d1, d2, d3], hours=30, dt=0.01,
                               impulses={12.0: [-0.39, -0.17, -0.10]})
    rec.save("run.json")
    render_viability_space(rec, "viability.mp4")
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from .drives import Drive

__all__ = ["ViabilityRecording", "record_viability_run", "render_viability_space"]

DEFAULT_ZONES = (0.33, 0.55, 0.80)


@dataclass
class ViabilityRecording:
    """A recorded joint trajectory in normalized viability space.

    ``x``/``v``/``kappa_ef`` are ``(n_drives, n_samples)`` lists in
    scene units: ``u = 2·(x − x*)/span`` with ``span = L⁺ − L⁻``, so the
    set-point is the origin and the viability wall is ``|u| = 1``.
    """

    t: list[float]
    x: list[list[float]]
    v: list[list[float]]
    kappa_ef: list[list[float]]
    names: list[str]
    d_star: list[Optional[float]]      # per drive, scene units (None = unbounded)
    zones: list[float]
    basal: list[int]                   # +1 recover / −1 decay / 0 no drift
    w: list[Optional[float]]           # spring reach per drive, scene units
    lambda_u: list[float]              # |basal drift| per drive, scene units
    limit: float = 1.0
    set_points: list[float] = field(default_factory=list)
    shock_t: Optional[float] = None    # first impulse time, if any
    impulses: list[dict] = field(default_factory=list)  # [{"t":…,"dx":[…]}] x-units
    dead_at: Optional[float] = None
    dead_drive: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "t": self.t, "x": self.x, "v": self.v, "kappa_ef": self.kappa_ef,
            "names": self.names, "d_star": self.d_star, "zones": self.zones,
            "basal": self.basal, "w": self.w, "lambda_u": self.lambda_u,
            "limit": self.limit, "set_points": self.set_points,
            "shock_t": self.shock_t, "impulses": self.impulses,
            "dead_at": self.dead_at, "dead_drive": self.dead_drive,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "ViabilityRecording":
        return cls(
            t=list(d["t"]), x=[list(r) for r in d["x"]],
            v=[list(r) for r in d["v"]],
            kappa_ef=[list(r) for r in d.get("kappa_ef", [])],
            names=list(d["names"]), d_star=list(d["d_star"]),
            zones=list(d["zones"]), basal=list(d.get("basal", [])),
            w=list(d.get("w", [])), lambda_u=list(d.get("lambda_u", [])),
            limit=d.get("limit", 1.0),
            set_points=list(d.get("set_points", [])),
            shock_t=d.get("shock_t"), impulses=list(d.get("impulses", [])),
            dead_at=d.get("dead_at"), dead_drive=d.get("dead_drive"),
        )

    def save(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ViabilityRecording":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def record_viability_run(
    drives: Sequence[Drive],
    hours: float,
    dt: float = 0.01,
    sample_every: int = 5,
    coupling: Optional[Sequence[Sequence[float]]] = None,
    impulses: Optional[Mapping[float, Sequence[float]]] = None,
    zones: Sequence[float] = DEFAULT_ZONES,
) -> ViabilityRecording:
    """Run real Drive objects and record the joint trajectory.

    Parameters
    ----------
    drives     : the drives to integrate (must already carry their dt or
                 share ``dt`` semantics — see ``Drive.dt``)
    hours      : horizon in the drives' time units
    dt         : integration step (must match ``Drive.dt``)
    sample_every : record every N-th step
    coupling   : optional W matrix in x-units — the term Σ_j W_ij·d_j is
                 passed to ``Drive.update(coupling=...)``
    impulses   : optional {time: [Δx_i]} shocks applied via ``Drive.impulse``
    zones      : algedonic layer boundaries in scene units (fractions of
                 the viable half-range)
    """
    n = len(drives)
    if n == 0:
        raise ValueError("record_viability_run needs at least one drive")
    spans = [d.viability[1] - d.viability[0] for d in drives]
    shocks = sorted((impulses or {}).items())
    fired = [False] * len(shocks)

    t_out: list[float] = []
    x_out: list[list[float]] = [[] for _ in range(n)]
    v_out: list[list[float]] = [[] for _ in range(n)]
    kef_out: list[list[float]] = [[] for _ in range(n)]
    dead_at = dead_drive = None

    steps = int(hours / dt)
    for s in range(steps + 1):
        t = s * dt
        for k, (t_shock, delta) in enumerate(shocks):
            if not fired[k] and t >= t_shock:
                for i, d in enumerate(drives):
                    d.impulse(delta[i], expected=delta[i])
                fired[k] = True
        if s % sample_every == 0:
            t_out.append(round(t, 3))
            for i, d in enumerate(drives):
                x_out[i].append(round(2 * (d.value - d.set_point) / spans[i], 5))
                v_out[i].append(round(2 * d.velocity / spans[i], 5))
                kef_out[i].append(round(d.kappa_eff, 5))
        couplings = [
            sum(coupling[i][j] * (drives[j].value - drives[j].set_point)
                for j in range(n) if j != i)
            if coupling else 0.0
            for i in range(n)
        ]
        for i, d in enumerate(drives):
            d.update(tick=t, coupling=couplings[i])
        breached = [i for i, d in enumerate(drives)
                    if d.value <= d.viability[0] or d.value >= d.viability[1]]
        if breached:
            dead_at, dead_drive = round(t, 2), breached[0]
            if s % sample_every != 0:   # final sample: the head touches the wall
                t_out.append(round(t, 3))
                for i, d in enumerate(drives):
                    x_out[i].append(round(2 * (d.value - d.set_point) / spans[i], 5))
                    v_out[i].append(round(2 * d.velocity / spans[i], 5))
                    kef_out[i].append(round(d.kappa_eff, 5))
            break

    to_u = [2.0 / sp for sp in spans]
    return ViabilityRecording(
        t=t_out, x=x_out, v=v_out, kappa_ef=kef_out,
        names=[d.name for d in drives],
        d_star=[round(ds * to_u[i], 4) if (ds := d.no_return_point()) else None
                for i, d in enumerate(drives)],
        zones=list(zones),
        basal=[0 if d.lambda_rate == 0 else (1 if d.lambda_rate > 0 else -1)
               for d in drives],
        w=[(2 * d.spring_reach / spans[i])
           if d.spring_reach not in (None, float("inf")) else None
           for i, d in enumerate(drives)],
        lambda_u=[abs(d.lambda_rate) * to_u[i] for i, d in enumerate(drives)],
        set_points=[0.0] * n,
        shock_t=shocks[0][0] if shocks else None,
        impulses=[{"t": st, "dx": list(dx)} for st, dx in shocks],
        dead_at=dead_at, dead_drive=dead_drive,
    )


# ──────────────────────────── rendering ─────────────────────────────

_BG = "#0e1117"
_INK = "#e8e6e0"
_DIM = "#98a1b2"
_ACCENT = "#c9bb92"
_COLS = ["#5fb0a6", "#d08a54", "#8f7fb8"]
_ZONE_STYLE = [(0.33, "#4c8f73", 0.10), (0.55, "#9c8a3e", 0.07),
               (0.80, "#b57a33", 0.06), (1.0, "#b34b3c", 0.05)]
_RED = "#b34b3c"


def _grip(rec: ViabilityRecording, k: int) -> float:
    """Instantaneous normalized grip: min over drives of spring force vs
    basal drift, g_i = κ_eff·|u|·e^(−|u|/w) / λ. Below 1 the spring can no
    longer compensate — this is what 'leaving reach' means physically."""
    g = 1.0
    for i in range(len(rec.names)):
        w_i = rec.w[i] if i < len(rec.w) else None
        lam = rec.lambda_u[i] if i < len(rec.lambda_u) else 0.0
        if lam == 0.0 or i >= len(rec.kappa_ef):
            continue                       # no drift: always recoverable
        if w_i is None:
            g_i = rec.kappa_ef[i][k] * abs(rec.x[i][k]) / lam
        else:
            g_i = (rec.kappa_ef[i][k] * abs(rec.x[i][k])
                   * math.exp(-abs(rec.x[i][k]) / w_i) / lam)
        g = min(g, g_i)
    return max(0.0, min(1.0, g))


def render_viability_space(
    recording: Union[ViabilityRecording, str, Path],
    output: Union[str, Path],
    fps: int = 25,
    dpi: int = 100,
    stride: int = 2,
) -> Path:
    """Render a recording to MP4 (ffmpeg) or GIF (Pillow) with matplotlib.

    Requires ``pip install binsai[analysis]``. ``output`` extension picks
    the writer: ``.mp4`` → FFMpegWriter, ``.gif`` → PillowWriter.
    """
    rec = (ViabilityRecording.load(recording)
           if isinstance(recording, (str, Path)) else recording)
    if len(rec.names) != 3:
        raise ValueError(
            f"viability space is 3D: expected 3 drives, got {len(rec.names)}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from itertools import product
        from matplotlib.animation import FuncAnimation, FFMpegWriter
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "render_viability_space needs matplotlib — "
            "pip install binsai[analysis]"
        ) from exc

    T = np.array(rec.t)
    X = np.array(rec.x)
    LIM = rec.limit
    Z = rec.zones + [1.0]
    shock_t = rec.shock_t
    dead_t = rec.dead_at

    def cube_faces(r):
        faces = []
        for axis, sign in product(range(3), (-1, 1)):
            pts = []
            for a, b in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
                p = [0.0, 0.0, 0.0]
                p[axis] = sign * r
                others = [i for i in range(3) if i != axis]
                p[others[0]], p[others[1]] = a * r, b * r
                pts.append(p)
            faces.append(np.array(pts))
        return faces

    plt.rcParams.update({"figure.facecolor": _BG, "savefig.facecolor": _BG,
                         "text.color": _INK, "axes.labelcolor": _DIM,
                         "xtick.color": _DIM, "ytick.color": _DIM,
                         "font.size": 9})
    fig = plt.figure(figsize=(12.8, 7.2), dpi=dpi)
    ax3 = fig.add_axes([0.02, 0.04, 0.60, 0.92], projection="3d")
    ax3.set_facecolor(_BG)
    panels = [fig.add_axes([0.68, 0.70 - i * 0.30, 0.29, 0.22])
              for i in range(3)]

    # concentric algedonic layers + viable cube K
    zone_cols = {0.33: "#4c8f73", 0.55: "#9c8a3e", 0.80: "#b57a33", 1.0: _RED}
    for r in sorted(Z, reverse=True):
        c = zone_cols.get(r, _RED)
        pc = Poly3DCollection(
            cube_faces(r * LIM), facecolor=c, alpha=0.10 if r <= 1.0 else 0.05,
            edgecolor=c if r == LIM else "none", linewidths=0.8)
        ax3.add_collection3d(pc)

    # spring-reach ellipsoid, semiaxes = d* per drive
    have_reach = all(d is not None for d in rec.d_star)
    if have_reach:
        u_, v_ = np.mgrid[0:2 * np.pi:25j, 0:np.pi:13j]
        ex = rec.d_star[0] * np.cos(u_) * np.sin(v_)
        ey = rec.d_star[1] * np.sin(u_) * np.sin(v_)
        ez = rec.d_star[2] * np.cos(v_)
        ax3.plot_wireframe(ex, ey, ez, color=_ACCENT, alpha=0.28,
                           linewidth=0.5, rstride=1, cstride=1)

    # basal-direction arrows on each axis
    for i, sgn in enumerate(rec.basal):
        if sgn == 0:
            continue
        org = [0.0, 0.0, 0.0]
        org[i] = sgn * 0.45 * LIM
        vec = [0.0, 0.0, 0.0]
        vec[i] = sgn * 0.30 * LIM
        ax3.quiver(org[0], org[1], org[2], vec[0], vec[1], vec[2],
                   color=_COLS[i], arrow_length_ratio=0.35, linewidth=1.6)

    ax3.set_xlim(-LIM, LIM); ax3.set_ylim(-LIM, LIM); ax3.set_zlim(-LIM, LIM)
    for i in range(3):
        getattr(ax3, f"set_{'xyz'[i]}label")(rec.names[i], color=_COLS[i])
    ax3.grid(False)
    for pane in (ax3.xaxis, ax3.yaxis, ax3.zaxis):
        pane.set_pane_color((0, 0, 0, 0))
        pane.line.set_color(_DIM)
    ax3.scatter([0], [0], [0], s=22, color=_ACCENT, marker="+")

    trail, = ax3.plot([], [], [], lw=2.0, color=_COLS[0], alpha=0.95)
    spring, = ax3.plot([], [], [], lw=2.5, color=_ACCENT, alpha=0.8)
    head = ax3.scatter([], [], [], s=60, color=_INK, depthshade=False)
    title = fig.text(0.03, 0.965, "", fontsize=13, color=_INK)
    sub = fig.text(0.03, 0.935, "", fontsize=10, color=_DIM)

    lines = []
    for i, p in enumerate(panels):
        p.set_facecolor("#151a23")
        for lo, hi, ci in [(rec.zones[0], rec.zones[1], 1),
                           (rec.zones[1], rec.zones[2], 2),
                           (rec.zones[2], 1.1, 3)]:
            p.axhspan(-hi, -lo, color=_ZONE_STYLE[ci][1], alpha=0.26)
            p.axhspan(lo, hi, color=_ZONE_STYLE[ci][1], alpha=0.26)
        p.axhspan(-rec.zones[0], rec.zones[0], color=_ZONE_STYLE[0][1],
                  alpha=0.30)
        p.axhline(0, color=_ACCENT, lw=0.9)
        if rec.d_star[i] is not None:
            p.axhline(rec.d_star[i], color=_INK, lw=0.7, ls=":")
            p.axhline(-rec.d_star[i], color=_INK, lw=0.7, ls=":")
        p.set_xlim(0, T[-1]); p.set_ylim(-1.1, 1.1)
        p.set_title(rec.names[i], color=_COLS[i], fontsize=10, loc="left",
                    pad=3)
        ln, = p.plot([], [], lw=1.6, color=_COLS[i])
        lines.append(ln)
        for s in p.spines.values():
            s.set_color("#262e3b")

    n_frames = len(T) // max(1, stride)

    def update(f):
        k = min(len(T) - 1, f * stride)
        trail.set_data(X[0, :k], X[1, :k])
        trail.set_3d_properties(X[2, :k])
        head._offsets3d = ([X[0, k]], [X[1, k]], [X[2, k]])
        g = _grip(rec, k)
        spring.set_data([0, X[0, k]], [0, X[1, k]])
        spring.set_3d_properties([0, X[2, k]])
        spring.set_linewidth(0.6 + 3.2 * g)
        spring.set_alpha(0.10 + 0.75 * g)
        for i, ln in enumerate(lines):
            ln.set_data(T[:k], X[i, :k])
        ax3.view_init(elev=20 + 6 * np.sin(f / 60), azim=-60 + f * 0.45)
        t = T[k]
        if shock_t is None or t < shock_t:
            title.set_text("1 · Regulación")
            sub.set_text("las necesidades oscilan cerca del equilibrio: "
                         "el resorte alcanza")
            trail.set_color(_COLS[0])
        elif dead_t is None or t < dead_t:
            title.set_text("2 · El golpe cruza el punto de no retorno")
            sub.set_text("más allá de d* el agarre del resorte ya no "
                         "compensa la deriva basal")
            trail.set_color("#b57a33")
        else:
            title.set_text("3 · Muerte operativa")
            dd = rec.names[rec.dead_drive or 0]
            sub.set_text(f"{dd} toca el límite de viabilidad a las {dead_t} h")
            trail.set_color(_RED)
        return trail, spring, head, *lines

    anim = FuncAnimation(fig, update, frames=n_frames, interval=40,
                         blit=False)
    out = Path(output)
    if out.suffix.lower() == ".gif":
        try:
            from matplotlib.animation import PillowWriter
        except ImportError as exc:  # pragma: no cover
            raise ImportError("GIF output needs pillow — pip install pillow"
                              ) from exc
        anim.save(str(out), writer=PillowWriter(fps=fps), dpi=dpi)
    else:
        anim.save(str(out), writer=FFMpegWriter(fps=fps, bitrate=2600),
                  dpi=dpi)
    plt.close(fig)
    return out
