"""Dependency-free SVG visualisation for homeostatic / algedonic drives.

Turns one or more :class:`~binsai.drives.Drive` trajectories into a
"drive timeline": stacked strips with fuzzy algedonic zones, the set-point
(solid) and passive resting level (dashed), the trajectory, an arrow at the
tip showing the basal direction of inaction, an optional event rug, and an
optional ghost projection of what inaction would do next.

No matplotlib, no browser, no third-party dependency: the functions return
strings, so they work in notebooks, scripts and CI alike.

Example::

    from binsai.viz import timeline_svg, timeline_html
    svg = timeline_svg(drive)                      # one drive
    html = timeline_html([ctx, backlog])           # multi-drive, standalone page
    open("timeline.svg", "w").write(svg)
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence, Union

from .drives import Drive

# Algedonic palette (Okabe-Ito-compatible greens/ambers/reds).
_OK = "#5E9E72"
_WARN = "#D9A92E"
_BAD = "#C24F38"
_DEAD = "#7A2E22"
_INK = "#18242C"
_SOFT = "#51626B"
_PEN = "#23479A"
_GRID = "#CCD9D1"

_MARGIN = {"l": 44, "r": 84, "t": 22, "b": 58}

_KINDS = {
    "sat": ("tri-up", _PEN),
    "pert": ("tri-down", _BAD),
    "alarm": ("diamond", _DEAD),
    "shock": ("bar", _SOFT),
}


def _zone_color(name: str) -> str:
    n = name.lower()
    if "equilibrium" in n:
        return _OK
    if "moderate" in n:
        return _WARN
    if "high" in n:
        return _BAD
    if "critical" in n:
        return _DEAD
    return _WARN


def _zone_stops(zones) -> list[tuple[float, str]]:
    """Sorted (offset, color) stops for a soft vertical gradient.

    SVG gradient offsets run 0 (top, value 1) to 1 (bottom, value 0), so the
    offset of a zone centered at ``c`` is ``1 - c``. One stop per zone center
    lets the linear gradient cross-fade between neighbouring zones (soft edges,
    no hard band lines).
    """
    if not zones:
        return [(0.0, _OK), (1.0, _OK)]
    zs = sorted(zones, key=lambda z: z.center)
    stops = {0.0: _zone_color(zs[-1].name), 1.0: _zone_color(zs[0].name)}
    for z in zs:
        stops[round(1.0 - z.center, 6)] = _zone_color(z.name)
    return sorted(stops.items())


def _as_list(drives: Union[Drive, Iterable[Drive]]) -> list[Drive]:
    if isinstance(drives, Drive):
        return [drives]
    return list(drives)


def _clip01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _ghost(drive: Drive, n: int) -> list[float]:
    """Project the drive n ticks under inaction (elastic return + basal flux)."""
    x = drive.value
    out = [x]
    for _ in range(n):
        x = _clip01(x - drive.kappa * (x - drive.set_point) + drive.lambda_rate)
        out.append(x)
    return out


def _event_mark(kind: str, cx: float, cy: float) -> str:
    shape, color = _KINDS.get(kind, _KINDS["shock"])
    if shape == "tri-up":
        return f'<path d="M{cx:.1f} {cy - 7:.1f} l4 7 h-8z" fill="{color}"/>'
    if shape == "tri-down":
        return f'<path d="M{cx - 4:.1f} {cy - 1:.1f} h8 l-4 7z" fill="{color}"/>'
    if shape == "diamond":
        return f'<path d="M{cx:.1f} {cy - 6:.1f} l4 3 l-4 3 l-4-3z" fill="{color}"/>'
    return f'<rect x="{cx - 1:.1f}" y="{cy - 6:.1f}" width="2" height="7" fill="{color}"/>'


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
) -> str:
    g = []
    # fuzzy algedonic background
    stops = _zone_stops(drive.zones)
    grad = "".join(
        f'<stop offset="{o * 100:.3f}%" stop-color="{c}" stop-opacity="0.26"/>'
        for o, c in stops
    )
    g.append(
        f'<defs><linearGradient id="binsai-band-{idx}" x1="0" y1="0" x2="0" y2="1">'
        f"{grad}</linearGradient></defs>"
    )
    g.append(
        f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{pw:.1f}" height="{ph:.1f}" '
        f'fill="url(#binsai-band-{idx})"/>'
    )
    # horizontal grid + y labels
    for v in (0.0, 0.5, 1.0):
        y = y0 + (1.0 - v) * ph
        g.append(
            f'<line x1="{x0:.1f}" x2="{x0 + pw:.1f}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="{_GRID}" stroke-width="0.6"/>'
        )
        g.append(
            f'<text x="{x0 - 6:.1f}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="{_SOFT}">{v:.1f}</text>'
        )
    # drive label
    g.append(
        f'<text x="{x0:.1f}" y="{y0 + 12:.1f}" font-size="12" font-weight="600" '
        f'fill="{_INK}">δ·{drive.name}</text>'
    )
    # set-point (solid) and resting level (dashed)
    sp_y = y0 + (1.0 - drive.set_point) * ph
    g.append(
        f'<line x1="{x0:.1f}" x2="{x0 + pw:.1f}" y1="{sp_y:.1f}" y2="{sp_y:.1f}" '
        f'stroke="{_INK}" stroke-width="1.1"/>'
    )
    xr = drive.resting_level
    if 0.0 <= xr <= 1.0:
        r_y = y0 + (1.0 - xr) * ph
        g.append(
            f'<line x1="{x0:.1f}" x2="{x0 + pw:.1f}" y1="{r_y:.1f}" y2="{r_y:.1f}" '
            f'stroke="{_INK}" stroke-dasharray="5 5" stroke-width="1"/>'
        )
        g.append(
            f'<text x="{x0 + pw + 4:.1f}" y="{r_y + 4:.1f}" font-size="10" fill="{_INK}">reposo</text>'
        )
    # trajectory
    hist = drive.history
    if len(hist) >= 2:
        pts = []
        for tick, value in hist:
            xx = x0 + (tick / tmax) * pw if tmax else x0
            yy = y0 + (1.0 - value) * ph
            pts.append(f"{xx:.1f},{yy:.1f}")
        g.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{_PEN}" '
            f'stroke-width="2" stroke-linejoin="round"/>'
        )
        last_tick, last_val = hist[-1]
        tx = x0 + (last_tick / tmax) * pw if tmax else x0
        ty = y0 + (1.0 - last_val) * ph
        g.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="4" fill="{_PEN}"/>')
        # arrow at the tip: basal direction of inaction
        f = -drive.kappa * (last_val - drive.set_point) + drive.lambda_rate
        if abs(f) > 1e-4:
            length = max(-0.9 * ph, min(0.9 * ph, f * 22 * ph))
            g.append(
                f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{tx:.1f}" y2="{ty - length:.1f}" '
                f'stroke="{_INK}" stroke-width="2.2" marker-end="url(#binsai-arr)"/>'
            )
    # ghost projection (what inaction would do next)
    if ghost_ticks > 0 and hist:
        last_tick, _ = hist[-1]
        proj = _ghost(drive, ghost_ticks)
        gp = []
        for i, v in enumerate(proj):
            xx = x0 + ((last_tick + i) / tmax) * pw
            yy = y0 + (1.0 - v) * ph
            gp.append(f"{xx:.1f},{yy:.1f}")
        g.append(
            f'<polyline points="{" ".join(gp)}" fill="none" stroke="{_PEN}" '
            f'stroke-width="2" stroke-dasharray="2 5" opacity="0.55"/>'
        )
    # event rug
    rug_y = y0 + ph + 16
    for tick, kind in events:
        cx = x0 + (tick / tmax) * pw if tmax else x0
        g.append(_event_mark(kind, cx, rug_y))
    return "".join(g)


def timeline_svg(
    drives: Union[Drive, Iterable[Drive]],
    *,
    width: int = 860,
    strip_height: int = 130,
    title: Optional[str] = None,
    events: Optional[Mapping[str, Sequence[tuple[int, str]]]] = None,
    ghost_ticks: int = 0,
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
        ghost_ticks: how many ticks of "inaction" to project past the last
            recorded point (0 = off). Drawn as a dashed extension.
    """
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
        '<marker id="binsai-arr" viewBox="0 0 10 10" refX="5" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0 L10 5 L0 10z" fill="#18242C"/></marker>'
    )

    y_cursor = _MARGIN["t"]
    if title:
        parts.append(
            f'<text x="{_MARGIN["l"]}" y="{y_cursor + 6}" font-size="14" font-weight="600" '
            f'fill="{_INK}">{title}</text>'
        )
        y_cursor += 24

    for i, d in enumerate(ds):
        ev = (events or {}).get(d.name, d.events)
        parts.append(
            _render_strip(d, i, _MARGIN["l"], y_cursor, pw, strip_height, tmax, ev, ghost_ticks)
        )
        if i < n - 1:
            y_cursor += strip_height + 18

    # shared time axis, just below the last strip
    axis_y = _MARGIN["t"] + n * strip_height + (n - 1) * 18 + 12
    axis_y = min(axis_y, height - 14)
    parts.append(
        f'<line x1="{_MARGIN["l"]}" x2="{_MARGIN["l"] + pw}" y1="{axis_y:.1f}" '
        f'y2="{axis_y:.1f}" stroke="{_INK}" stroke-width="1"/>'
    )
    for t in range(0, tmax + 1, max(1, tmax // 8)):
        xx = _MARGIN["l"] + (t / tmax) * pw
        parts.append(
            f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{axis_y - 3:.1f}" y2="{axis_y + 3:.1f}" '
            f'stroke="{_INK}"/>'
        )
        parts.append(
            f'<text x="{xx:.1f}" y="{axis_y + 16:.1f}" text-anchor="middle" font-size="11" '
            f'fill="{_SOFT}">{t}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def timeline_html(
    drives: Union[Drive, Iterable[Drive]],
    *,
    width: int = 860,
    strip_height: int = 130,
    title: Optional[str] = None,
    events: Optional[Mapping[str, Sequence[tuple[int, str]]]] = None,
    ghost_ticks: int = 0,
) -> str:
    """Return a standalone HTML page wrapping :func:`timeline_svg` (for sharing)."""
    svg = timeline_svg(
        drives, width=width, strip_height=strip_height, title=title,
        events=events, ghost_ticks=ghost_ticks,
    )
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Binsai · línea de tiempo de drives</title>"
        "<style>body{margin:0;background:#E7EEEA;color:#18242C;"
        "font-family:system-ui,sans-serif;padding:24px}svg{display:block;"
        "max-width:100%;height:auto;background:#F2F6F3;border-radius:14px;"
        "border:1px solid #CCD9D1;padding:8px}</style></head><body>"
        + svg +
        "</body></html>"
    )
