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
        assert "hunger" in svg  # both use the same name; count strips via band rects
        # two set-point labels present (one per strip)
        assert svg.count('font-size="12"') >= 2

    def test_restorative_arrow_renders(self):
        d = make_trajectory(beta=-0.005)
        svg = timeline_svg(d)
        assert "binsai-arr" in svg

    def test_ghost_projection_renders(self):
        d = make_trajectory()
        svg = timeline_svg(d, ghost_ticks=30)
        assert "stroke-dasharray=\"2 5\"" in svg  # ghost polyline

    def test_events_rug_uses_drive_events(self):
        d = make_trajectory()
        d.record_event(5, "sat")
        d.record_event(9, "pert")
        svg = timeline_svg(d)
        assert svg.count('fill="#23479A"') >= 2  # trajectory circle + sat marker

    def test_events_override(self):
        d = make_trajectory()
        d.record_event(5, "sat")
        svg = timeline_svg(d, events={d.name: [(3, "alarm")]})
        assert 'fill="#7A2E22"' in svg  # alarm diamond present

    def test_record_event_public_api(self):
        d = make_trajectory()
        d.record_event(2, "shock")
        assert d.events == [(2, "shock")]
        # read-only copy
        d.events.clear()
        assert d.events == [(2, "shock")]

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


def test_history_property_is_public_and_readonly():
    d = make_trajectory()
    h = d.history
    assert isinstance(h, list)
    assert len(h) == 60
    # modifying the returned list must not mutate the drive
    h.clear()
    assert len(d.history) == 60
