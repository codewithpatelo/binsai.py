"""Tests for binsai.viz — dependency-free SVG drive timelines."""

import pytest

from binsai.drives import Drive
from binsai.viz import timeline_svg, timeline_html


def make_trajectory(*, beta=0.005, value=0.30, set_point=0.30, kappa=0.05):
    d = Drive(name="hunger", value=value, set_point=set_point,
              kappa=kappa, lambda_rate=beta)
    for t in range(60):
        d.update(tick=t)
        if t % 17 == 5:
            d.satiate(0.5)
    return d


class TestTimelineSvg:
    def test_single_drive_returns_svg(self):
        d = make_trajectory()
        svg = timeline_svg(d)
        assert svg.startswith("<svg")
        assert svg.rstrip().endswith("</svg>")
        assert "hunger" in svg

    def test_multiple_drives_stacked(self):
        a = make_trajectory(beta=0.005)
        b = make_trajectory(beta=-0.005, set_point=0.35)
        svg = timeline_svg([a, b], title="dos drives")
        assert "dos drives" in svg
        assert "hunger" in svg  # both use the same name; count strips via headers
        # two strip headers present (one per drive)
        assert svg.count("deriva basal") == 2

    def test_restorative_arrow_renders(self):
        d = make_trajectory(beta=-0.005)
        svg = timeline_svg(d)
        assert "binsai-arr" in svg

    def test_ghost_projection_renders(self):
        d = make_trajectory()
        svg = timeline_svg(d, ghost_ticks=30)
        assert "stroke-dasharray=\"2 5\"" in svg  # ghost polyline

    def test_ghost_matches_spring_policy(self):
        from binsai.viz import _ghost
        # linear damper: converges to the cancellation point x*+λ/κ = 0.40
        lin = make_trajectory(beta=0.005)
        lin.spring = "linear"
        proj = _ghost(lin, 200)
        assert abs(proj[-1] - lin.resting_level) < 0.02
        # legacy pulsatile: sawtooth — the projection must oscillate
        pul = make_trajectory(beta=0.005)
        pul.spring = "pulsatile"
        gp = _ghost(pul, 120)
        diffs = [gp[i + 1] - gp[i] for i in range(len(gp) - 1)]
        assert any(d < -1e-6 for d in diffs) and any(d > 1e-6 for d in diffs)

    def test_events_rug_uses_drive_events(self):
        d = make_trajectory()
        d.record_event(5, "sat")
        d.record_event(9, "pert")
        svg = timeline_svg(d)
        assert svg.count('fill="#4ECDC4"') >= 2  # dark pen: trajectory circle + sat marker

    def test_events_override(self):
        d = make_trajectory()
        d.record_event(5, "sat")
        svg = timeline_svg(d, events={d.name: [(3, "alarm")]})
        assert 'fill="#F85149"' in svg  # alarm diamond present (dark dead color)

    def test_record_event_public_api(self):
        d = make_trajectory()
        d.record_event(2, "shock")
        assert (2, "shock") in d.events  # pulsatile releases may also be logged
        # read-only copy
        n = len(d.events)
        d.events.clear()
        assert len(d.events) == n

    def test_empty_history_does_not_crash(self):
        d = Drive(name="empty", value=0.30, set_point=0.30)
        svg = timeline_svg(d)
        assert svg.startswith("<svg")

    def test_raises_on_no_drives(self):
        with pytest.raises(ValueError):
            timeline_svg([])


class TestTimelineHtml:
    def test_html_wrapper(self):
        d = make_trajectory()
        html = timeline_html(d)
        assert html.startswith("<!doctype html>")
        assert "<svg" in html
        assert "hunger" in html


class TestTrajectoryArtifact:
    def test_artifact_wraps_svg_and_html(self):
        from binsai.viz import trajectory_artifact
        d = make_trajectory()
        art = trajectory_artifact(d)
        assert art.svg().startswith("<svg")
        assert art.html().startswith("<!doctype html>")
        assert "TrajectoryArtifact" in repr(art)

    def test_artifact_save(self, tmp_path):
        from binsai.viz import trajectory_artifact
        d = make_trajectory()
        art = trajectory_artifact(d)
        p = art.save(str(tmp_path / "d.html"))
        assert "svg" in open(p, encoding="utf-8").read()
        p2 = art.save(str(tmp_path / "d.svg"))
        assert open(p2, encoding="utf-8").read().startswith("<svg")

    def test_zone_bands_and_setpoint_dashed(self):
        d = make_trajectory()
        svg = timeline_svg(d)
        assert svg.count('fill-opacity="0.22"') == 7   # 7 algedonic bands
        assert 'stroke-dasharray="7 5"' in svg          # set-point dashed

    def test_viability_limits_and_death_zones(self):
        d = Drive(name="v", value=0.30, set_point=0.30, viability=(0.10, 0.90))
        for t in range(10):
            d.update(tick=t)
        svg = timeline_svg(d)
        assert svg.count('stroke-dasharray="9 6"') == 2  # lo + hi limit lines
        assert svg.count('fill-opacity="0.55"') == 2     # two death zones

    def test_full_range_viability_no_death_zone(self):
        d = make_trajectory()  # default viability (0,1)
        svg = timeline_svg(d)
        assert 'fill-opacity="0.55"' not in svg

    def test_kappa_tick_on_setpoint(self):
        d = make_trajectory()
        svg = timeline_svg(d)
        assert 'stroke="#BC8CFF"' in svg  # κ vertical tick (dark theme)

    def test_light_theme(self):
        d = make_trajectory()
        svg = timeline_svg(d, theme="light")
        assert 'fill="#F2F6F3"' in svg
        with pytest.raises(ValueError):
            timeline_svg(d, theme="neon")


def test_history_property_is_public_and_readonly():
    d = make_trajectory()
    h = d.history
    assert isinstance(h, list)
    assert len(h) == 60
    # modifying the returned list must not mutate the drive
    h.clear()
    assert len(d.history) == 60
