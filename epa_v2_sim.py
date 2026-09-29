"""
Simulación EPA v2 con tres necesidades acopladas — corrida real de Binsai.

Genera epa_v2_sim.json, que consume tanto la animación de Manim como la vista
previa. Los datos salen de objetos binsai.Drive reales (spring="magnetic-2nd",
docs/paov2.tex): si cambian los parámetros o la dinámica de la librería, la
animación cambia.

Espacio de la escena (u): desviación normalizada respecto del equilibrio,
u ∈ [−1, 1], muerte operativa en |u| = 1.

Mapeo a Binsai (convención satisfacción x ∈ [0,1], x* = 0.5):

    u = 2·(x − x*)      a_b = a_u/2

    λ_b = λ_u/2   κ_b = κ_u   w_b = w_u/2   c_b = c_u   f_b = 2·f_u
    (f se duplica porque Λ acumula |d| = |u|/2)

Dinámica (por necesidad i, en unidades de escena):
    a = λ·σ  −  κ_ef·u·e^(−|u|/w)  −  c·v  +  Σ_j W_ij·u_j
    v ← v + a·Δt ;  u ← u + v·Δt
    κ_ef = κ·e^(−f·Λ) ;  Λ' = |u|
"""
import json
import math
import sys

sys.path.insert(0, "src")
from binsai import Drive  # noqa: E402

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

LIMIT = 1.0
SHOCK = [-0.78, -0.34, -0.20]   # el golpe: una carga que saca al sistema del alcance


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


def no_return_point(kappa, lam, w):
    """Raíz lejana de κ·d·e^(−d/w) = λ, por barrido (unidades de escena)."""
    d = w
    while d < 4.0:
        if kappa * d * math.exp(-d / w) < lam:
            return d
        d += 0.002
    return None


def run():
    n = len(DRIVES)
    drives = build_drives()
    out = {"t": [], "x": [[] for _ in range(n)], "v": [[] for _ in range(n)],
           "kappa_ef": [[] for _ in range(n)]}
    shocked = False
    steps = int(HOURS / DT)
    for s in range(steps + 1):
        t = s * DT
        if not shocked and t >= SHOCK_T:
            for i, d in enumerate(drives):
                d.impulse(SHOCK[i] / 2, expected=SHOCK[i] / 2)  # impulse es en x
            shocked = True
        if s % 5 == 0:                      # se guarda cada 0,05 h
            out["t"].append(round(t, 3))
            for i, d in enumerate(drives):
                u = 2 * (d.value - d.set_point)
                kef = d.kappa * math.exp(-d.spring_fatigue * d._allostatic)
                out["x"][i].append(round(u, 5))
                out["v"][i].append(round(2 * d.velocity, 5))
                out["kappa_ef"][i].append(round(kef, 5))
        # acoplamiento en unidades binsai: Σ_j W_ij·d_j
        couplings = [
            sum(W[i][j] * (drives[j].value - drives[j].set_point)
                for j in range(n) if j != i)
            for i in range(n)
        ]
        for i, d in enumerate(drives):
            d.update(tick=t, coupling=couplings[i])
        dead = [i for i, d in enumerate(drives)
                if d.value <= d.viability[0] or d.value >= d.viability[1]]
        if dead:
            out["dead_at"] = round(t, 2)
            out["dead_drive"] = dead[0]
            break
    out["names"] = [d[0] for d in DRIVES]
    out["set_points"] = [0.0 for _ in DRIVES]           # en unidades de escena
    out["limit"] = LIMIT
    out["shock_t"] = SHOCK_T
    out["d_star"] = [round(no_return_point(d[3], d[1], d[4]) or 0, 3)
                     for d in DRIVES]
    out["zones"] = [0.33, 0.55, 0.80]
    return out


if __name__ == "__main__":
    data = run()
    json.dump(data, open("epa_v2_sim.json", "w"))
    print("muestras:", len(data["t"]),
          "| muere:", data.get("dead_at"), "en",
          data["names"][data.get("dead_drive", 0)],
          "| d*:", data["d_star"])
