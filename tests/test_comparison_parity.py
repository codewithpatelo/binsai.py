"""Comparison parity: all spring variants in an ablation must start from the
same state — otherwise the figure compares two things at once.

Context: fig_ablation_springs rendered the magnet as if it began from a
different satisfaction level. Root cause was silent history truncation
(default history_limit=500 < run length), which clipped the start of the
trajectory — not a different initial condition, but indistinguishable from
one in the rendered figure. These tests pin both sides: identical initial
state across variants, and full-history retention when asked.
"""
import pytest

from binsai import Drive

# The ablation config from tools_fig_spring_suite / docs/ABLATION-SPRING.md
CFG = dict(
    value=0.70, set_point=0.70, kappa=0.04, lambda_rate=0.002,
    basal_direction="decay", spring_threshold=0.12, spring_release=1.0,
    viability=(0.10, 0.98),
)
VARIANTS = [
    ("linear",    "linear",    None),
    ("pulsatile", "pulsatile", float("inf")),
    ("magnet",    "pulsatile", 0.18),
]


def _make(name, spring, reach):
    kw = {"spring": spring}
    if reach is not None:
        kw["spring_reach"] = reach
    return Drive(name=name, **kw, **CFG)


def test_variants_share_identical_initial_state():
    drives = [_make(n, s, w) for n, s, w in VARIANTS]
    ref = drives[0]
    for d in drives[1:]:
        assert d.value == ref.value
        assert d.set_point == ref.set_point
        assert d.lambda_rate == ref.lambda_rate
        assert d.viability == ref.viability
        assert [(z.name, z.center, z.width) for z in d.zones] == \
               [(z.name, z.center, z.width) for z in ref.zones]
        assert d._tension == ref._tension == 0.0
        assert d.history == ref.history == []


# ── EPA v2 ablation arms (docs/ABLATION-EPA-V2.md) ────────────────────────
# Same shared CFG; w derived by the w-rule for d*=0.35.
_V2_W = Drive.design_spring_reach(0.05, 0.001, 0.35)
V2_CFG = dict(
    value=0.70, set_point=0.70, kappa=0.05, lambda_rate=0.001,
    basal_direction="decay", viability=(0.10, 0.98),
    damping=0.10, dt=1.0, allostatic_recovery=0.002,
    spring_threshold=0.12, spring_release=1.0,
)
V2_VARIANTS = [
    ("linear",      dict(spring="linear")),
    ("pulsatile",   dict(spring="pulsatile", spring_reach=float("inf"))),
    ("magnet_f0",   dict(spring="magnetic-2nd", spring_reach=_V2_W,
                         spring_fatigue=0.0)),
    ("magnet_f010", dict(spring="magnetic-2nd", spring_reach=_V2_W,
                         spring_fatigue=0.10)),
]


def _make_v2(name, extra):
    return Drive(name=name, **{**V2_CFG, **extra})


def test_v2_variants_share_identical_initial_state():
    """All EPA v2 ablation arms start from the same (x, v) state."""
    drives = [_make_v2(n, e) for n, e in V2_VARIANTS]
    ref = drives[0]
    for d in drives[1:]:
        assert (d.value, d.velocity) == (ref.value, ref.velocity)
        assert d.set_point == ref.set_point
        assert d.lambda_rate == ref.lambda_rate
        assert d.viability == ref.viability
        assert d.dt == ref.dt
        assert d.damping == ref.damping
        assert d.allostatic_load == ref.allostatic_load == 0.0
        assert [(z.name, z.center, z.width) for z in d.zones] == \
               [(z.name, z.center, z.width) for z in ref.zones]
        assert d.history == ref.history == []


def test_v2_variants_differ_only_in_dynamics():
    """The only varying fields are the spring mode and fatigue coefficient."""
    drives = [_make_v2(n, e) for n, e in V2_VARIANTS]
    for a, b in zip(drives, drives[1:]):
        for f in ("value", "velocity", "set_point", "kappa", "lambda_rate",
                  "damping", "dt", "allostatic_recovery", "viability",
                  "spring_threshold", "spring_release"):
            assert getattr(a, f) == getattr(b, f), f


def test_variants_differ_only_in_spring():
    drives = [_make(n, s, w) for n, s, w in VARIANTS]
    spring_fields = {"spring", "spring_reach"}
    for a, b in zip(drives, drives[1:]):
        for f in ("value", "set_point", "kappa", "lambda_rate",
                  "spring_threshold", "spring_release", "viability"):
            assert getattr(a, f) == getattr(b, f), f


def test_default_retains_full_history():
    """Default history_limit=0 keeps every tick — silent truncation
    distorted the ablation figure (looked like a different initial
    condition). Retaining everything is the default; limits are opt-in."""
    d = Drive(name="t", value=0.5)
    for t in range(1200):
        d.update(t)
    assert len(d.history) == 1200
    assert d.history[0][0] == 0
    assert d.history_dropped == 0


def test_explicit_limit_caps_and_reports():
    """A configured limit must cap AND register the discard — nothing in
    this library drops data silently."""
    import warnings
    d = Drive(name="t", value=0.5, history_limit=500)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for t in range(1200):
            d.update(t)
    assert len(d.history) == 500
    assert d.history_dropped == 700
    assert any("history_limit" in str(w.message) for w in caught)
