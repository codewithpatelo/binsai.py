"""Viability-space artifact: recording runs real Drive dynamics and keeps
the schema the renderers consume. Render smoke tests need matplotlib."""
import math

import pytest

from binsai import Drive, ViabilityRecording, record_viability_run


def _drives(dt=0.01):
    out = []
    for name, lam, d, kap, w, f, c, x0 in [
        ("servicio",   0.010, "decay",   0.60, 0.106, 0.008, 0.10, 0.57),
        ("metabolica", 0.008, "recover", 0.55, 0.097, 0.006, 0.11, 0.415),
        ("social",     0.006, "decay",   0.50, 0.088, 0.004, 0.12, 0.545),
    ]:
        out.append(Drive(name=name, value=x0, set_point=0.5,
                         viability=(0.0, 1.0), lambda_rate=lam,
                         basal_direction=d, spring="magnetic-2nd",
                         kappa=kap, spring_reach=w, spring_fatigue=f,
                         allostatic_recovery=0.0, damping=c, dt=dt))
    return out


class TestRecording:
    def test_shape_and_u_space(self):
        rec = record_viability_run(_drives(), hours=1.0, dt=0.01)
        assert len(rec.names) == 3
        assert len(rec.x) == 3 and len(rec.t) == len(rec.x[0])
        assert all(-1.0 <= u <= 1.0 for row in rec.x for u in row)
        assert rec.limit == 1.0 and rec.set_points == [0.0] * 3
        assert rec.basal == [-1, 1, -1]

    def test_d_star_from_real_no_return_point(self):
        drives = _drives()
        rec = record_viability_run(drives, hours=0.2, dt=0.01)
        for i, d in enumerate(drives):
            expected = 2 * d.no_return_point()  # span = 1 → u* = 2·d*_x
            assert rec.d_star[i] == pytest.approx(expected, abs=1e-3)

    def test_impulse_jumps_x(self):
        rec = record_viability_run(_drives(), hours=1.0, dt=0.01,
                                   impulses={0.5: [-0.4, 0.0, 0.0]})
        assert rec.shock_t == 0.5
        k = rec.t.index(0.5)
        assert rec.x[0][k] - rec.x[0][k - 1] < -0.6   # −0.8 in u-space

    def test_death_recorded(self):
        rec = record_viability_run(_drives(), hours=30.0, dt=0.01,
                                   impulses={0.1: [-0.49, 0.0, 0.0]})
        assert rec.dead_at is not None and rec.dead_drive == 0
        assert rec.x[0][-1] <= -1.0 or rec.x[0][-1] >= 1.0

    def test_survival_has_no_dead_at(self):
        rec = record_viability_run(_drives(), hours=1.0, dt=0.01)
        assert rec.dead_at is None and rec.dead_drive is None

    def test_save_load_roundtrip(self, tmp_path):
        rec = record_viability_run(_drives(), hours=0.5, dt=0.01,
                                   impulses={0.2: [-0.1, 0.0, 0.0]})
        p = rec.save(tmp_path / "run.json")
        back = ViabilityRecording.load(p)
        assert back.to_dict() == rec.to_dict()

    def test_kappa_ef_recorded(self):
        rec = record_viability_run(_drives(), hours=0.5, dt=0.01)
        assert len(rec.kappa_ef) == 3
        assert all(k > 0 for row in rec.kappa_ef for k in row)


class TestRender:
    def test_rejects_non_3d(self):
        rec = record_viability_run(_drives()[:2], hours=0.2, dt=0.01)
        with pytest.raises(ValueError, match="3 drives"):
            from binsai import render_viability_space
            render_viability_space(rec, "out.gif")

    def test_renders_gif(self, tmp_path):
        pytest.importorskip("matplotlib")
        pytest.importorskip("PIL")
        from binsai import render_viability_space
        rec = record_viability_run(_drives(), hours=0.3, dt=0.01,
                                   impulses={0.15: [-0.3, 0.0, 0.0]})
        out = render_viability_space(rec, tmp_path / "v.gif", fps=10,
                                     dpi=50, stride=3)
        assert out.stat().st_size > 0
