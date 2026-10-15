"""A steel part quenched from its austenitising temperature, on a linear-tet :class:`~cadgen._internal.fea.femspace.FemSpace`.

:func:`march` follows the temperature from the furnace (every node at the austenitising temperature) until the whole
part is under 500 °C and the spread between its hottest and coolest points has passed its peak. Every face loses heat
to the bath at one coefficient h (constant: the vapour blanket and the boiling are not modelled). Backward Euler on the
lumped (diagonal) capacity of linear tets, which keeps the march monotone, the step doubling while no node moves more
than :data:`CALM_C` in a step and halving when one moves more than :data:`REJECT_C`, one factor kept per step size:

    m (T¹ - T⁰) / Δt + K T¹ + h F (T¹ - T_bath) = 0.

Along the way it keeps, for every node, its cooling rate as it passes 700 °C (the step's own, a secant over at most
:data:`REJECT_C`) and when it passes 800 and 500 °C (for t8/5), and the moment the spread is largest, whose
temperatures :func:`thermal_stress` turns into the elastic stress and distortion of the free part (thermal strain
only). Units: mm, s, °C; heat in mJ and power in mW (the engine's). Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

__all__ = ["CALM_C", "Quench", "REJECT_C", "Stress", "march", "thermal_stress"]

#: A step that moved no node more than this doubles the next; one that moved a node more than REJECT_C is taken again
#: at half the step.
CALM_C, REJECT_C = 6.0, 25.0
#: The temperatures it keeps the crossing of, °C.
HARDENING_C, T8_C, T5_C = 700.0, 800.0, 500.0
#: The march ends once every node is under T5_C and the spread has fallen to this share of its peak.
SPREAD_PAST = 0.8
#: A march stops past this many steps, or past PATIENCE times the hand estimate's time to 500 °C, saying so.
MAX_STEPS, PATIENCE = 20_000, 50.0
#: The curves keep at most this many points.
CURVE_POINTS = 400


@dataclass
class Quench:
    """What a march kept."""

    #: (time s, temperatures) at the frames, t = 0 first; ``spread_frame`` is the moment of the largest spread.
    frames: list
    spread_frame: int
    spread_s: float
    spread_C: float
    spread_state: "np.ndarray"
    #: Each node's cooling rate at 700 °C (°C/s) and when it passed 800 and 500 °C (s); NaN where it never did.
    rate_700: "np.ndarray"
    t_800: "np.ndarray"
    t_500: "np.ndarray"
    end_s: float
    steps: int
    rejected: int
    smallest_step: float
    largest_step: float
    final: "np.ndarray"
    #: Heat (mJ): what the bath took, the part's own at the start and the end.
    heat_out: float
    energy_start: float
    energy_end: float
    #: The hottest and the coolest temperature against time.
    curve_t: list
    curve_hot: list
    curve_cold: list
    solver: str = ""
    #: Seconds of quench it stopped at past its wall-clock limit; None when it ran to its end.
    stopped_at: float | None = None
    #: Why it ended early, in words, or "".
    cut_short: str = ""


def march(space: "FemSpace", steel: "Material", *, h_W_m2K: float, bath_C: float, start_C: float, node_volumes,
          estimate_s: float, frames: int = 24, iterative: bool = False, log: Callable[[str], None] | None = None,
          limit_s: float | None = None) -> Quench:
    """The quench, from ``start_C`` everywhere until every node is under 500 °C and the spread is past its peak.

    ``steel`` gives the conductivity, density and specific heat; ``node_volumes`` each node's lumped volume (mm³);
    ``estimate_s`` the hand estimate of the slowest point's time to 500 °C, which spaces the frames and bounds the
    run (:data:`PATIENCE`)."""
    import numpy as np
    import scipy.sparse as sparse
    import scipy.sparse.linalg as spla

    from cadgen._internal.fea import operators
    from cadgen._internal.fea.thermal_ops import PER_M2
    from cadgen._internal.fea.timestep import Clock

    n = space.mesh.p.shape[1]
    capacity = np.asarray(node_volumes) * steel.density * steel.specific_heat * 1e6     # mJ/K per node
    K = operators.conduction(space, [steel]).tocsr()
    every = np.ones(len(space.boundary_quadratic), dtype=bool)
    F, load = operators.convection(space, space.facets_of_rows(every), h_W_m2K * PER_M2, bath_C)
    F, load = F.tocsr(), np.asarray(load)
    rows = np.asarray(F.sum(axis=1)).ravel()
    base = (K + F).tocsr()
    cache: dict = {}

    def solver(dt: float):
        if dt not in cache:
            A = (base + sparse.diags(capacity / dt)).tocsr()
            if iterative:
                import pyamg

                ml = pyamg.smoothed_aggregation_solver(A, symmetry="symmetric", strength="symmetric", smooth="energy",
                                                       max_coarse=500)
                cache[dt] = lambda b, x0, ml=ml: ml.solve(b, x0=x0, tol=1e-11, accel="cg", maxiter=400)
            else:
                lu = spla.splu(A.tocsc())
                cache[dt] = lambda b, x0, lu=lu: lu.solve(b)
        return cache[dt]

    T = np.full(n, float(start_C))
    energy_start = float(capacity @ T)
    rate = np.full(n, np.nan)
    t8, t5 = np.full(n, np.nan), np.full(n, np.nan)
    if start_C <= T8_C:
        t8[:] = 0.0
    spread_C, spread_s, spread_state = 0.0, 0.0, T.copy()
    kept: list = [(0.0, T.copy())]
    spacing = max(estimate_s, 1e-6) / max(frames - 1, 1)
    next_frame = spacing
    curve_t, curve_hot, curve_cold = [0.0], [float(T.max())], [float(T.min())]
    t, dt = 0.0, max(1e-3, 1e-4 * estimate_s)
    smallest_dt = dt * 1e-6
    steps = rejected = 0
    smallest, largest = math.inf, 0.0
    heat_out = 0.0
    clock = Clock(log, limit_s)
    stopped_at, cut_short = None, ""
    while True:
        spread_now = float(T.max() - T.min())
        if float(T.max()) < T5_C and spread_now <= SPREAD_PAST * spread_C:
            break
        if steps >= MAX_STEPS:
            cut_short = f"stopped after {MAX_STEPS} steps at t = {t:.4g} s"
            break
        if t > PATIENCE * estimate_s:
            cut_short = (f"still above 500 °C after {t:.4g} s, {PATIENCE:g} times the hand estimate; check the "
                         "quenchant and h_W_m2K")
            break
        T1 = solver(dt)(capacity / dt * T + load, T)
        moved = float(np.abs(T1 - T).max())
        if moved > REJECT_C and dt > smallest_dt:
            dt /= 2.0
            rejected += 1
            continue
        heat_out += float(rows @ T1 - load.sum()) * dt
        crossed = np.isnan(rate) & (T > HARDENING_C) & (T1 <= HARDENING_C)
        rate[crossed] = (T[crossed] - T1[crossed]) / dt
        for target, times in ((T8_C, t8), (T5_C, t5)):
            passing = np.isnan(times) & (T > target) & (T1 <= target)
            times[passing] = t + dt * (T[passing] - target) / (T[passing] - T1[passing])
        T = T1
        t += dt
        steps += 1
        smallest, largest = min(smallest, dt), max(largest, dt)
        spread_now = float(T.max() - T.min())
        if spread_now > spread_C:
            spread_C, spread_s, spread_state = spread_now, t, T.copy()
        curve_t.append(t)
        curve_hot.append(float(T.max()))
        curve_cold.append(float(T.min()))
        if t >= next_frame * (1 - 1e-9):
            kept.append((t, T.copy()))
            next_frame = t + spacing
            if len(kept) > 2 * frames:
                kept = kept[::2]
                spacing *= 2
        if moved < CALM_C:
            dt *= 2.0
        clock.tell(lambda: f"quenching: t = {t:.4g} s, hottest {curve_hot[-1]:.4g} °C, {steps} steps")
        if clock.over():
            stopped_at = t
            break
    if kept[-1][0] != t:
        kept.append((t, T.copy()))
    chosen = _evenly(kept, max(frames - 1, 2))
    if all(time != spread_s for time, _ in chosen):
        chosen = sorted(chosen + [(spread_s, spread_state)], key=lambda frame: frame[0])
    spread_frame = next(i for i, (time, _) in enumerate(chosen) if time == spread_s)
    if len(curve_t) > CURVE_POINTS:
        every_nth = math.ceil(len(curve_t) / CURVE_POINTS)
        picks = sorted({0, len(curve_t) - 1, *range(0, len(curve_t), every_nth)})
        curve_t, curve_hot, curve_cold = ([series[i] for i in picks] for series in (curve_t, curve_hot, curve_cold))
    how = ("multigrid-preconditioned CG" if iterative else "SuperLU") + \
        f", backward Euler, {steps} steps doubling and halving ({len(cache)} factorisations)"
    return Quench(
        frames=chosen, spread_frame=spread_frame, spread_s=spread_s, spread_C=spread_C, spread_state=spread_state,
        rate_700=rate, t_800=t8, t_500=t5, end_s=t, steps=steps, rejected=rejected,
        smallest_step=smallest if steps else 0.0, largest_step=largest, final=T, heat_out=heat_out,
        energy_start=energy_start, energy_end=float(capacity @ T), curve_t=curve_t, curve_hot=curve_hot,
        curve_cold=curve_cold, solver=how, stopped_at=stopped_at, cut_short=cut_short,
    )


def _evenly(kept: list, frames: int) -> list:
    """At most ``frames`` of the kept states, the nearest to evenly spaced times from the first to the last."""
    if len(kept) <= frames:
        return list(kept)
    end = kept[-1][0]
    picks = {min(range(len(kept)), key=lambda j: (abs(kept[j][0] - end * i / (frames - 1)), j)) for i in range(frames)}
    return [kept[j] for j in sorted(picks)]


# -- the stress of the largest spread -----------------------------------------------------------------


@dataclass
class Stress:
    """The free part's elastic stress and distortion under one temperature field (thermal strain only)."""

    #: (nodes,) von Mises and the largest principal stress (tension positive), MPa.
    von_mises: "np.ndarray"
    tension: "np.ndarray"
    #: (nodes, 3) mm: the shape change against the part shrunk uniformly to its mean temperature, rigid motion removed.
    displacement: "np.ndarray"
    #: The volume-mean temperature the strain is measured from, °C.
    mean_C: float
    #: |reactions| of the three held points against the thermal load: ~0 when the load balances, as it must.
    imbalance: float
    solver: str


def thermal_stress(space: "FemSpace", steel: "Material", temperature: "np.ndarray", node_volumes,
                   warnings: list[str]) -> Stress:
    """The elastic stress σ = C:(ε(u) - α (T - T̄) I) of the free part, T̄ its volume-mean temperature.

    A free part under a self-balanced thermal load needs only its rigid motion stopped: three nodes hold six
    displacements (a 3-2-1 support: one node in x, y and z, the farthest from it in the two directions across the
    line between them, a third, the farthest from that line, along the normal of their plane), which carry no
    reaction; the rigid motion they leave is then removed, so the displacement is the shape change alone."""
    import numpy as np

    from cadgen._internal.fea import operators

    volumes = np.asarray(node_volumes)
    mean = float(volumes @ temperature / volumes.sum())
    strain = steel.expansion * space.scalar.interpolate(temperature - mean).value
    K = operators.stiffness(space, [steel]).tocsr()
    f = operators.initial_strain_load(space, [steel], strain)
    points = space.dof_locations
    centre = points.mean(axis=0)
    a = int(np.argmin(np.linalg.norm(points - centre, axis=1)))
    b = int(np.argmax(np.linalg.norm(points - points[a], axis=1)))
    line = points[b] - points[a]
    line /= max(float(np.linalg.norm(line)), 1e-300)
    off = points - points[a]
    across = off - np.outer(off @ line, line)
    c = int(np.argmax(np.linalg.norm(across, axis=1)))
    normal = np.cross(line, points[c] - points[a])
    along = int(np.argmax(np.abs(line)))
    held = [(a, 0), (a, 1), (a, 2), *[(b, axis) for axis in range(3) if axis != along], (c, int(np.argmax(np.abs(normal))))]
    vector = {(node, axis): space.basis.nodal_dofs[axis][node] for node, axis in held}
    fixed = np.array(sorted(set(vector.values())), dtype=np.int64)
    free = np.setdiff1d(np.arange(space.basis.N), fixed)
    u = np.zeros(space.basis.N)
    u[free], how = operators.solve_spd(K, f, free, space.locations, space.component, warnings)
    reaction = K @ u - f
    imbalance = float(np.abs(reaction[fixed]).max()) / max(float(np.abs(f).max()), 1e-300)
    rigid = operators.rigid_body_modes(space.locations, space.component)
    u = u - rigid @ np.linalg.lstsq(rigid, u, rcond=None)[0]
    s = operators.stress(space, [steel], u, strain)
    von_mises = np.maximum(space.scalar.project(operators.von_mises(s)), 0.0)
    principal = np.linalg.eigvalsh(np.moveaxis(s, (0, 1), (-2, -1)))[..., -1]
    tension = space.scalar.project(principal)
    return Stress(von_mises=von_mises, tension=tension, displacement=space.nodal(u), mean_C=mean, imbalance=imbalance,
                  solver=how)
