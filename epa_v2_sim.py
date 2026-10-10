"""
Simulación EPA v2 con tres necesidades acopladas — corrida real de Binsai.

Genera epa_v2_sim.json, que consumen la animación de Manim
(tools_manim_epa_v2.py), la vista previa (preview.py) y el artefacto
importable binsai.viability_space. Los datos salen de objetos
binsai.Drive reales vía binsai.record_viability_run: si cambian los
parámetros o la dinámica de la librería, la animación cambia.

Espacio de la escena (u): desviación normalizada respecto del equilibrio,
u ∈ [−1, 1], muerte operativa en |u| = 1.

Mapeo a Binsai (convención satisfacción x ∈ [0,1], x* = 0.5):

    u = 2·(x − x*)

    λ_b = λ_u/2   κ_b = κ_u   w_b = w_u/2   c_b = c_u   f_b = 2·f_u
    (f se duplica porque Λ acumula |d| = |u|/2)
"""
import sys

sys.path.insert(0, "src")
from binsai import Drive  # noqa: E402
from binsai.viability_space import record_viability_run  # noqa: E402

DT = 0.01          # horas por subpaso
HOURS = 30.0
SHOCK_T = 12.0     # el shock que cruza el punto de no retorno

#        nombre       λ_u     dir   κ     w_u    f_u    c     u0
DRIVES = [
    ("servicio",   0.020, "decay",   0.60, 0.212, 0.004, 0.10,  0.14),
    ("metabólica", 0.016, "recover", 0.55, 0.194, 0.003, 0.11, -0.17),
    ("social",     0.012, "decay",   0.50, 0.176, 0.002, 0.12,  0.09),
]
# acoplamiento: trabajar para el servicio vacía la metabólica, etc.
W = [[0.0, -0.05, -0.03],
     [-0.04, 0.0, 0.0],
     [-0.03, 0.0, 0.0]]

SHOCK = [-0.78, -0.34, -0.20]   # el golpe (unidades de escena; en x: /2)


def build_drives() -> list[Drive]:
    """Los tres drives reales. El set-point es 0.5 y el conjunto viable [0,1],
    así u = 2(x−x*) reproduce exactamente el espacio centrado de la escena."""
    drives = []
    for name, lam_u, direction, kap, w_u, f_u, c, u0 in DRIVES:
        drives.append(Drive(
            name=name,
            value=0.5 + u0 / 2,
            set_point=0.5,
            viability=(0.0, 1.0),
            lambda_rate=lam_u / 2,
            basal_direction=direction,
            spring="magnetic-2nd",
            kappa=kap,
            spring_reach=w_u / 2,
            spring_fatigue=2 * f_u,   # Λ acumula |d| = |u|/2 → f se duplica
            allostatic_recovery=0.0,
            damping=c,
            dt=DT,
        ))
    return drives


def run():
    rec = record_viability_run(
        build_drives(), hours=HOURS, dt=DT, sample_every=5,
        coupling=W,
        impulses={SHOCK_T: [s / 2 for s in SHOCK]},   # impulse es en x
        zones=[0.33, 0.55, 0.80],
    )
    return rec


if __name__ == "__main__":
    rec = run()
    rec.save("epa_v2_sim.json")
    print("muestras:", len(rec.t),
          "| muere:", rec.dead_at, "en",
          rec.names[rec.dead_drive or 0],
          "| d*:", rec.d_star)
