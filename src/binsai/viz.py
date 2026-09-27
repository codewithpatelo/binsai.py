"""Dependency-free drive-trajectory timeline — a self-contained visual artifact.

Turns one or more :class:`~binsai.drives.Drive` trajectories into a "drive
timeline" artifact: stacked strips with algedonic zone bands, the set-point
(dashed), the basal-drift arrow at the tip of the line (up = recover,
down = decay), the elastic spring κ as a vertical tick on the set-point,
viability limits (thick red dashes) with translucent "death zones" beyond
them, an optional event rug, and an optional ghost projection of the
autonomous dynamics under inaction (basal drift + elastic return — it
converges to the resting level x* + λ/κ).

No matplotlib, no browser, no third-party dependency: everything is a
string, so artifacts can be embedded in notebooks, dashboards, agent
harnesses (Claude Code/Cowork-style artifacts, MCP tools) or saved to disk.

Example::

    from binsai.viz import trajectory_artifact, timeline_svg, timeline_html

    art = trajectory_artifact(drive)               # one drive
    art.save("drive.html")                         # standalone page
    svg = art.svg()                                # raw SVG string
    html = timeline_html([ctx, backlog])           # multi-drive page
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence, Union

from .drives import Drive

# ── Themes ──────────────────────────────────────────────────────────────────

_THEMES = {
    "dark": {
        "bg":       "#0E1117",
        "panel":    "#0E1117",
        "ink":      "#E6EDF3",
        "soft":     "#7D8590",
        "pen":      "#4ECDC4",   # trajectory stroke
        "grid":     "#21262D",
        "ok":       "#3FB950",
        "warn":     "#D29922",
        "bad":      "#F0A03C",
        "dead":     "#F85149",
        "kappa":    "#BC8CFF",
        "death":    "#000000",
    },
    "light": {
        "bg":       "#F2F6F3",
        "panel":    "#FFFFFF",
        "ink":      "#18242C",
        "soft":     "#51626B",
        "pen":      "#23479A",
        "grid":     "#CCD9D1",
        "ok":       "#5E9E72",
        "warn":     "#D9A92E",
        "bad":      "#C24F38",
        "dead":     "#7A2E22",
        "kappa":    "#6E49CB",
        "death":    "#1B1B1B",
    },
}

_MARGIN = {"l": 46, "r": 96, "t": 26, "b": 58}

_KINDS = {
    "sat":     "tri-up",
    "pert":    "tri-down",
    "alarm":   "diamond",
    "shock":   "bar",
    "release": "diamond-k",   # spring tension discharge — kappa purple
}


def _zone_color(name: str, th: dict) -> str:
    n = name.lower()
    if "equilibrium" in n:
        return th["ok"]
    if "moderate" in n:
        return th["warn"]
    if "high" in n:
        return th["bad"]
    if "critical" in n:
        return th["dead"]
    return th["warn"]


def _zone_bands(zones) -> list[tuple[float, float, str]]:
    """Hard-edged algedonic bands: (lo, hi, zone_name) covering [0,1].

    Band edges sit at the midpoints between consecutive zone centers — so
    the number of bands and their thresholds follow ``drive.zones`` directly
    (parametrizable per drive, default seven).
    """
    if not zones:
        return [(0.0, 1.0, "equilibrium")]
    zs = sorted(zones, key=lambda z: z.center)
    edges = [0.0]
    for a, b in zip(zs, zs[1:]):
        edges.append((a.center + b.center) / 2.0)
    edges.append(1.0)
    return [(edges[i], edges[i + 1], zs[i].name) for i in range(len(zs))]


def _as_list(drives: Union[Drive, Iterable[Drive]]) -> list[Drive]:
    if isinstance(drives, Drive):
        return [drives]
    return list(drives)


def _clip01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _ghost(drive: Drive, n: int) -> list[float]:
    """Project n ticks of autonomous dynamics under inaction.

    Mirrors Drive.update() — basal drift + the configured spring policy —
    minus action/coupling, on a scratch tension register so the real drive
    state is untouched. Under "linear" it converges to x* + λ/κ; under
    "pulsatile" it shows the sawtooth struggle (and the escape when the
    drift outruns the spring's reach).
    """
    x = drive.value
    sig = drive._tension
    t0 = drive.history[-1][0] if drive.history else 0
    out = [x]
    for i in range(1, n + 1):
        d = x - drive.set_point
        if callable(drive.spring):
            release = drive.spring(d)
        elif drive.spring == "linear":
            release = -drive.kappa * d
        else:
            sig += drive._spring_charge(d)
            release = -drive.spring_release * sig if abs(sig) >= drive.spring_threshold else 0.0
            if release:
                sig += release
        drift = drive._drift_fn(x, drive.set_point, t0 + i,
                                drive.lambda_rate, drive.drift_k)
        x = _clip01(x + release + drift)
        out.append(x)
    return out


def _event_mark(kind: str, cx: float, cy: float, th: dict) -> str:
    shape = _KINDS.get(kind, "bar")
    pen, bad, dead, soft = th["pen"], th["bad"], th["dead"], th["soft"]
    if shape == "tri-up":
        return f'<path d="M{cx:.1f} {cy - 7:.1f} l4 7 h-8z" fill="{pen}"/>'
    if shape == "tri-down":
        return f'<path d="M{cx - 4:.1f} {cy - 1:.1f} h8 l-4 7z" fill="{bad}"/>'
    if shape == "diamond":
        return f'<path d="M{cx:.1f} {cy - 6:.1f} l4 3 l-4 3 l-4-3z" fill="{dead}"/>'
    if shape == "diamond-k":
        return f'<path d="M{cx:.1f} {cy - 6:.1f} l4 3 l-4 3 l-4-3z" fill="{th["kappa"]}"/>'
    return f'<rect x="{cx - 1:.1f}" y="{cy - 6:.1f}" width="2" height="7" fill="{soft}"/>'


def _header_text(drive: Drive, lang: str) -> str:
    arrow = "↑" if drive.lambda_rate > 0 else ("↓" if drive.lambda_rate < 0 else "·")
    word = {"es": ("recupera", "decae"),
            "en": ("recovering", "decaying")}[lang]
    basal = word[0] if drive.lambda_rate > 0 else (word[1] if drive.lambda_rate < 0 else "—")
    label = {"es": "deriva basal", "en": "basal drift"}[lang]
    return f"{drive.name} — {label}: {arrow} {basal} · κ {drive.kappa:.2f}"


def _render_strip(
    drive: Drive,
    idx: int,
    x0: float,
    y0: float,
    pw: float,
    ph: float,
    tmax: int,
    events: Sequence[tuple[int, str]],
    ghost_ticks: int,
    th: dict,
    band_opacity: float,
    lang: str,
) -> str:
    g = []

    # ── viability limits + death zones (behind everything) ──
    lo_v, hi_v = drive.viability
    if lo_v > 0.0:  # death zone below lo_v
        y = y0 + (1.0 - lo_v) * ph
        g.append(
            f'<rect x="{x0:.1f}" y="{y:.1f}" width="{pw:.1f}" '
            f'height="{(y0 + ph - y):.1f}" fill="{th["death"]}" fill-opacity="0.55"/>'
        )
    if hi_v < 1.0:  # death zone above hi_v
        y = y0 + (1.0 - hi_v) * ph
        g.append(
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{pw:.1f}" '
            f'height="{(y - y0):.1f}" fill="{th["death"]}" fill-opacity="0.55"/>'
        )

    # ── algedonic zone bands ──
    for lo, hi, name in _zone_bands(drive.zones):
        y_top = y0 + (1.0 - hi) * ph
        h = (hi - lo) * ph
        g.append(
            f'<rect x="{x0:.1f}" y="{y_top:.1f}" width="{pw:.1f}" height="{h:.1f}" '
            f'fill="{_zone_color(name, th)}" fill-opacity="{band_opacity}"/>'
        )

    # ── viability limit lines (thick red dashes) ──
    for lim in (lo_v, hi_v):
        if 0.0 < lim < 1.0:
            y = y0 + (1.0 - lim) * ph
            g.append(
                f'<line x1="{x0:.1f}" x2="{x0 + pw:.1f}" y1="{y:.1f}" y2="{y:.1f}" '
                f'stroke="{th["dead"]}" stroke-width="2.4" stroke-dasharray="9 6"/>'
            )

    # ── grid + y labels ──
    for v in (0.0, 0.5, 1.0):
        y = y0 + (1.0 - v) * ph
        g.append(
            f'<line x1="{x0:.1f}" x2="{x0 + pw:.1f}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="{th["grid"]}" stroke-width="0.6"/>'
        )
        g.append(
            f'<text x="{x0 - 6:.1f}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="{th["soft"]}">{v:.1f}</text>'
        )

    # ── header: drive name, basal direction, resting level, κ ──
    g.append(
        f'<text x="{x0:.1f}" y="{y0 + 11:.1f}" font-size="11" font-weight="600" '
        f'fill="{th["pen"]}">{_header_text(drive, lang)}</text>'
    )

    # ── set-point (dashed) + κ vertical tick ──
    sp_y = y0 + (1.0 - drive.set_point) * ph
    g.append(
        f'<line x1="{x0:.1f}" x2="{x0 + pw:.1f}" y1="{sp_y:.1f}" y2="{sp_y:.1f}" '
        f'stroke="{th["ink"]}" stroke-width="1.1" stroke-dasharray="7 5"/>'
    )
    # κ: the elastic spring, drawn as a vertical tick on the set-point line
    k_h = max(5.0, drive.kappa * ph * 0.9)
    kx = x0 + pw - 10
    g.append(
        f'<line x1="{kx:.1f}" x2="{kx:.1f}" y1="{sp_y - k_h:.1f}" y2="{sp_y + k_h:.1f}" '
        f'stroke="{th["kappa"]}" stroke-width="2.6"/>'
    )

    # ── trajectory ──
    hist = drive.history
    if len(hist) >= 2:
        pts = []
        for tick, value in hist:
            xx = x0 + (tick / tmax) * pw if tmax else x0
            yy = y0 + (1.0 - value) * ph
            pts.append(f"{xx:.1f},{yy:.1f}")
        g.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{th["pen"]}" '
            f'stroke-width="2" stroke-linejoin="round"/>'
        )
        last_tick, last_val = hist[-1]
        tx = x0 + (last_tick / tmax) * pw if tmax else x0
        ty = y0 + (1.0 - last_val) * ph
        g.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="4" fill="{th["pen"]}"/>')
        # basal drift arrow at the tip — up if recovering (λ>0), down if decaying
        if abs(drive.lambda_rate) > 1e-9:
            length = 26 if drive.lambda_rate > 0 else -26
            g.append(
                f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{tx:.1f}" y2="{ty - length:.1f}" '
                f'stroke="{th["ink"]}" stroke-width="2.2" marker-end="url(#binsai-arr)"/>'
            )

    # ── ghost projection (what inaction would do next) ──
    if ghost_ticks > 0 and hist:
        last_tick, _ = hist[-1]
        proj = _ghost(drive, ghost_ticks)
        gp = []
        for i, v in enumerate(proj):
            xx = x0 + ((last_tick + i) / tmax) * pw
            yy = y0 + (1.0 - v) * ph
            gp.append(f"{xx:.1f},{yy:.1f}")
        g.append(
            f'<polyline points="{" ".join(gp)}" fill="none" stroke="{th["pen"]}" '
            f'stroke-width="2" stroke-dasharray="2 5" opacity="0.55"/>'
        )
        glabel = {"es": "sin acción", "en": "no action"}[lang]
        g.append(
            f'<text x="{xx + 5:.1f}" y="{yy + 3:.1f}" font-size="9" '
            f'fill="{th["soft"]}">{glabel}</text>'
        )

    # ── event rug ──
    rug_y = y0 + ph + 16
    for tick, kind in events:
        cx = x0 + (tick / tmax) * pw if tmax else x0
        g.append(_event_mark(kind, cx, rug_y, th))
    return "".join(g)


def timeline_svg(
    drives: Union[Drive, Iterable[Drive]],
    *,
    width: int = 900,
    strip_height: int = 140,
    title: Optional[str] = None,
    events: Optional[Mapping[str, Sequence[tuple[int, str]]]] = None,
    ghost_ticks: int = 0,
    theme: str = "dark",
    band_opacity: float = 0.22,
    lang: str = "es",
) -> str:
    """Render one or more drives as a self-contained SVG timeline string.

    Args:
        drives: a :class:`Drive` or an iterable of them (stacked vertically).
        width: SVG width in px.
        strip_height: height in px allocated to each drive.
        title: optional caption rendered above the strips.
        events: optional per-drive event lists, keyed by drive name; each entry
            is a ``(tick, kind)`` pair with kind in ``sat/pert/alarm/shock``.
            When omitted, each drive's own ``drive.events`` is used.
        ghost_ticks: how many ticks to project past the last recorded point
            under inaction (0 = off). Applies drift + elastic return, so the
            dashed extension converges to the resting level ``x* + λ/κ``.
        theme: ``"dark"`` (matches the reference figure) or ``"light"``.
        band_opacity: algedonic band fill opacity — transparent enough to
            read the trajectory through the bands.
        lang: ``"es"`` or ``"en"`` for strip headers.
    """
    th = _THEMES.get(theme)
    if th is None:
        raise ValueError(f"theme must be one of {sorted(_THEMES)}, got {theme!r}")

    ds = _as_list(drives)
    if not ds:
        raise ValueError("timeline_svg needs at least one Drive")

    all_ticks = [t for d in ds for t, _ in d.history]
    tmax = (max(all_ticks) if all_ticks else 1) + ghost_ticks
    n = len(ds)
    body_h = n * strip_height + (n - 1) * 18
    height = _MARGIN["t"] + body_h + _MARGIN["b"]
    if title:
        height += 24

    pw = width - _MARGIN["l"] - _MARGIN["r"]

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
                 f'width="{width}" role="img">')
    parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{th["bg"]}"/>'
    )
    parts.append(
        f'<marker id="binsai-arr" viewBox="0 0 10 10" refX="5" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10z" fill="{th["ink"]}"/></marker>'
    )

    y_cursor = _MARGIN["t"]
    if title:
        parts.append(
            f'<text x="{_MARGIN["l"]}" y="{y_cursor + 6}" font-size="14" font-weight="600" '
            f'fill="{th["ink"]}">{title}</text>'
        )
        y_cursor += 24

    for i, d in enumerate(ds):
        ev = (events or {}).get(d.name, d.events)
        parts.append(
            _render_strip(d, i, _MARGIN["l"], y_cursor, pw, strip_height,
                          tmax, ev, ghost_ticks, th, band_opacity, lang)
        )
        if i < n - 1:
            y_cursor += strip_height + 18

    # shared time axis, just below the last strip
    axis_y = _MARGIN["t"] + n * strip_height + (n - 1) * 18 + 12
    axis_y = min(axis_y, height - 14)
    parts.append(
        f'<line x1="{_MARGIN["l"]}" x2="{_MARGIN["l"] + pw}" y1="{axis_y:.1f}" '
        f'y2="{axis_y:.1f}" stroke="{th["ink"]}" stroke-width="1"/>'
    )
    xlab = {"es": "ticks", "en": "ticks"}[lang]
    for t in range(0, tmax + 1, max(1, tmax // 8)):
        xx = _MARGIN["l"] + (t / tmax) * pw
        parts.append(
            f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{axis_y - 3:.1f}" y2="{axis_y + 3:.1f}" '
            f'stroke="{th["ink"]}"/>'
        )
        parts.append(
            f'<text x="{xx:.1f}" y="{axis_y + 16:.1f}" text-anchor="middle" font-size="11" '
            f'fill="{th["soft"]}">{t}</text>'
        )
    parts.append(
        f'<text x="{_MARGIN["l"] + pw:.1f}" y="{axis_y + 30:.1f}" text-anchor="end" '
        f'font-size="10" fill="{th["soft"]}">{xlab}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def timeline_html(
    drives: Union[Drive, Iterable[Drive]],
    *,
    width: int = 900,
    strip_height: int = 140,
    title: Optional[str] = None,
    events: Optional[Mapping[str, Sequence[tuple[int, str]]]] = None,
    ghost_ticks: int = 0,
    theme: str = "dark",
    band_opacity: float = 0.22,
    lang: str = "es",
) -> str:
    """Return a standalone HTML page wrapping :func:`timeline_svg`."""
    svg = timeline_svg(
        drives, width=width, strip_height=strip_height, title=title,
        events=events, ghost_ticks=ghost_ticks, theme=theme,
        band_opacity=band_opacity, lang=lang,
    )
    th = _THEMES[theme if theme in _THEMES else "dark"]
    page_title = {"es": "Binsai · línea de tiempo de drives",
                  "en": "Binsai · drive timeline"}[lang]
    return (
        "<!doctype html><html lang=\"" + lang + "\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{page_title}</title>"
        f"<style>body{{margin:0;background:{th['bg']};color:{th['ink']};"
        "font-family:system-ui,sans-serif;padding:24px}svg{display:block;"
        f"max-width:100%;height:auto;border:1px solid {th['grid']};"
        "border-radius:14px;padding:8px}</style></head><body>"
        + svg +
        "</body></html>"
    )


class TrajectoryArtifact:
    """A self-contained drive-trajectory artifact for agent harnesses.

    Wraps :func:`timeline_svg`/:func:`timeline_html` into an object that can
    be rendered, saved, or embedded by tools that display artifacts
    (notebooks, Claude-style artifact panes, MCP responses).

    Example::

        art = trajectory_artifact(drive, title="metabolic — night shift")
        art.save("metabolic.html")          # shareable page
        art.svg()                            # inline SVG for embedding
        str(art)                             # full HTML page
    """

    def __init__(self, drives: Union[Drive, Iterable[Drive]], **kwargs) -> None:
        self.drives = _as_list(drives)
        self.kwargs = kwargs

    def svg(self, **overrides) -> str:
        kw = {**self.kwargs, **overrides}
        return timeline_svg(self.drives, **kw)

    def html(self, **overrides) -> str:
        kw = {**self.kwargs, **overrides}
        return timeline_html(self.drives, **kw)

    def save(self, path: str, **overrides) -> str:
        """Write the artifact (HTML page or raw SVG by extension)."""
        content = self.svg(**overrides) if path.endswith(".svg") else self.html(**overrides)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def _repr_html_(self) -> str:
        """IPython/Jupyter rich display hook."""
        return self.svg()

    def __str__(self) -> str:
        return self.html()

    def __repr__(self) -> str:
        names = ", ".join(d.name for d in self.drives)
        return f"TrajectoryArtifact([{names}])"


def trajectory_artifact(
    drives: Union[Drive, Iterable[Drive]],
    **kwargs,
) -> TrajectoryArtifact:
    """Build a :class:`TrajectoryArtifact` from one or more drives."""
    return TrajectoryArtifact(drives, **kwargs)
