"""A casting freezing in its mould, on a linear-tet :class:`~cadgen._internal.fea.femspace.FemSpace`.

:func:`march` follows the temperature from the pour to fully solid. The heat equation is written in the enthalpy
H(T) = ρ c T + ρ L f_l(T) per volume (f_l the liquid fraction, straight between solidus and liquidus), on the lumped
(diagonal) capacity of linear tets, which is positive and keeps the march monotone, with backward Euler:

    m (H(T¹) - H(T⁰)) / Δt + K T¹ + Σ h F (T¹ - T_mould) = 0

K the conduction (:func:`cadgen._internal.fea.operators.conduction`), F each mould face's film matrix
(:func:`cadgen._internal.fea.operators.convection`), h its mean coefficient over the step. Each step is solved by
Newton's method on the nodes' enthalpies (Nedjar's form): T(H) is single-valued and has no plateau to stall on, and
each update solves the symmetric (m/Δt dH/dT + K + Σ h F) δT = -R, applied as δH = dH/dT δT, shortened where it
would raise the residual. Settled, it is the equation exactly: every joule of latent heat is accounted for however
far a node moves in one step, a pure metal's one-degree freezing range included. The linear solves are conjugate
gradients preconditioned by a factor (or a multigrid hierarchy) of the same matrix taken a few steps earlier, rebuilt
when the step or the mould's coefficient has moved threefold or a solve slowed down.

Along the way it keeps each node's time to fully solid, and, as it passes the Niyama temperature (a tenth of the
freezing range above the solidus), its cooling rate and the Niyama value G / √(cooling rate). :func:`pockets` finds
the liquid regions that freeze after everything around them with no feeder reaching them; :func:`sections` measures
the section under each surface triangle (along its inward normal, walking the tets) and when it is solid through.

Units: mm, s, °C; heat in mJ and power in mW (the engine's); conductivity in W/(m K) (= mW/(mm K)). Numeric imports
live inside the functions.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.manufacturing.processes.foundry import CastingAlloy

__all__ = [
    "Cooling", "Enthalpy", "Film", "Held", "NIYAMA_SHARE", "Pocket", "Section", "boundary_facet_rows", "march",
    "mesh_graph", "node_volumes", "pockets", "sections",
]

#: Niyama's temperature: this share of the freezing range above the solidus, near the end of solidification.
NIYAMA_SHARE = 0.1
#: A step moves a node's temperature at most 1/STEP_SHARE_T of the pour-to-mould span, the liquid share of the
#: volume at most STEP_LIQUID percent, and a node's enthalpy at most STEP_NODE_H of the freezing range's (latent heat
#: and all): the freezing takes at least 100 / STEP_LIQUID steps, and the front crosses an element in two or more.
STEP_SHARE_T, STEP_LIQUID, STEP_NODE_H = 60.0, 2.0, 0.5
#: A step is taken again, shorter, when it moved more than this many times its target.
REJECT_ABOVE = 2.5
#: A step's Newton iterations: at most this many.
MAX_PASSES = 40
#: The preconditioner is rebuilt once the step or a mould coefficient has moved this many times from its own, or a
#: solve with it took more than SLOW_CG iterations (the freezing range's capacity moved on).
REBUILD_RATIO, SLOW_CG = 3.0, 25
#: A march stops past this many steps, saying so.
MAX_STEPS = 20_000
#: A study with no end stops (saying so) once it has run this many times the hand estimate of the freezing time.
PATIENCE = 50.0
#: The liquid-share curve keeps at most this many points.
CURVE_POINTS = 400


@dataclass(frozen=True)
class Enthalpy:
    """The alloy's enthalpy per volume, mJ/mm³, against temperature (°C; only differences matter)."""

    rho_c: float          # mJ/(mm³ K)
    rho_L: float          # mJ/mm³
    solidus: float
    liquidus: float

    @classmethod
    def of(cls, alloy: "CastingAlloy") -> "Enthalpy":
        solidus, liquidus = alloy.freezing
        return cls(alloy.density * alloy.specific_heat * 1e6, alloy.density * alloy.latent_heat * 1e6, solidus, liquidus)

    def liquid(self, T):
        import numpy as np

        return np.clip((np.asarray(T) - self.solidus) / (self.liquidus - self.solidus), 0.0, 1.0)

    def H(self, T):
        return self.rho_c * T + self.rho_L * self.liquid(T)

    def temperature(self, H):
        """T(H): the inverse of :meth:`H`, flat-free (a pure metal's plateau is its one-degree range)."""
        import numpy as np

        low, high = self.H_solid, self.H_solid + self.mushy_span
        span = self.liquidus - self.solidus
        return np.where(H <= low, H / self.rho_c, np.where(H >= high, (H - self.rho_L) / self.rho_c,
                                                           self.solidus + (H - low) * span / self.mushy_span))

    def capacity(self, H):
        """dH/dT at the enthalpy H: ρ c, or the freezing range's own slope while H is within it."""
        import numpy as np

        low, high = self.H_solid, self.H_solid + self.mushy_span
        return np.where((H > low) & (H < high), self.mushy_span / (self.liquidus - self.solidus), self.rho_c)

    @property
    def H_solid(self) -> float:
        return float(self.H(self.solidus))

    @property
    def mushy_span(self) -> float:
        """H(liquidus) - H(solidus): the latent heat and the sensible heat of the freezing range."""
        return float(self.H(self.liquidus) - self.H(self.solidus))


@dataclass
class Film:
    """Faces losing heat to the mould: their skfem facets, the mould's temperature and the mean h over a step."""

    facets: "np.ndarray"
    ambient: float
    #: (t0, t1) -> mean W/(m² K) over the step.
    h_of: Callable[[float, float], float]


@dataclass
class Held:
    """Faces held at a temperature (a riser kept hot) while the rest freezes, then left to the mould."""

    dofs: "np.ndarray"
    celsius: float
    #: Once the hold ends, these films take over on the same faces (the mould's own); none leaves them insulated.
    after: list = field(default_factory=list)
    #: The hold ends here, s, if the rest is not solid sooner (a face held above the liquidus keeps its neighbours
    #: liquid for as long as it is held).
    until_s: float = math.inf


@dataclass
class Cooling:
    """What a march kept."""

    #: (time s, temperatures) at the frames, t = 0 first.
    frames: list
    #: Each node's time to fully solid, s (the end of the march for a node that never froze).
    freeze_s: "np.ndarray"
    #: Each node's Niyama value, (°C s)^½/mm, and cooling rate, °C/s, as it passed the Niyama temperature (NaN where
    #: it never did).
    niyama: "np.ndarray"
    cooling_rate: "np.ndarray"
    end_s: float
    solid: bool
    steps: int
    rejected: int
    passes: int
    smallest_step: float
    largest_step: float
    #: Heat (mJ): what left through the mould, what the held faces put in, the metal's own at the start and the end.
    heat_out: float
    heat_in: float
    energy_start: float
    energy_end: float
    #: The liquid share of the volume against time, percent (thinned to CURVE_POINTS).
    curve_t: list
    curve_liquid: list
    final: "np.ndarray"
    #: Seconds of simulated time it stopped at past its wall-clock limit; None when it ran to its end.
    stopped_at: float | None = None
    #: Why it ended early, in words ("still not solid after ..."), or "".
    cut_short: str = ""
    solver: str = ""
    #: The volume's mean temperature, °C, and the share of it not yet past the stop temperature, percent, at each
    #: ``curve_t`` (a moulding's: its mean and the share still too hot to eject).
    curve_mean: list = field(default_factory=list)
    curve_above: list = field(default_factory=list)
    #: Each node's time to fall below the march's ``watch_C``, s (the end of the march where it never did); ``None``
    #: when no temperature was watched.
    watch_s: "np.ndarray | None" = None


def node_volumes(space: "FemSpace") -> "np.ndarray":
    """Each node's lumped volume, mm³: a quarter of every linear tet it is a corner of (positive, sums to the part's)."""
    import numpy as np

    points, tets = space.mesh.p, space.mesh.t
    corners = points[:, tets]                                  # (3, 4, E)
    edges = corners[:, 1:, :] - corners[:, :1, :]              # (3, 3, E)
    volume = np.abs(np.linalg.det(np.moveaxis(edges, -1, 0))) / 6.0
    out = np.zeros(points.shape[1])
    np.add.at(out, tets.ravel(), np.repeat(volume[None, :] / 4.0, 4, axis=0).ravel())
    return out


def mesh_graph(space: "FemSpace"):
    """The nodes' neighbours along the tets' edges, as CSR (indptr, indices)."""
    import numpy as np
    import scipy.sparse as sparse

    tets = space.mesh.t
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    rows = np.concatenate([tets[a] for a, b in pairs] + [tets[b] for a, b in pairs])
    cols = np.concatenate([tets[b] for a, b in pairs] + [tets[a] for a, b in pairs])
    n = space.mesh.p.shape[1]
    graph = sparse.coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n)).tocsr()
    return graph.indptr, graph.indices


def _gradient(space: "FemSpace"):
    """A function T -> |∇T| at the nodes, °C/mm: each tet's constant gradient, averaged over a node's tets by volume."""
    import numpy as np
    import scipy.sparse as sparse

    points, tets = space.mesh.p, space.mesh.t
    n, count = points.shape[1], tets.shape[1]
    corners = points[:, tets]
    jacobian = np.moveaxis(corners[:, 1:, :] - corners[:, :1, :], -1, 0)   # (E, 3, 3): columns are edges
    inverse = np.linalg.inv(jacobian)                                     # rows: ∇φ1..∇φ3
    grads = np.empty((count, 4, 3))
    grads[:, 1:, :] = inverse
    grads[:, 0, :] = -inverse.sum(axis=1)
    volume = np.abs(np.linalg.det(jacobian)) / 6.0
    weight = np.zeros(n)
    np.add.at(weight, tets.ravel(), np.repeat(volume[None, :], 4, axis=0).ravel())
    averaging = sparse.coo_matrix((np.repeat(volume[None, :], 4, axis=0).ravel() / weight[tets.ravel()],
                                   (tets.ravel(), np.tile(np.arange(count), 4))), shape=(n, count)).tocsr()
    operators = []
    for c in range(3):
        per_tet = sparse.coo_matrix((grads[:, :, c].T.ravel(), (np.tile(np.arange(count), 4), tets.ravel())),
                                    shape=(count, n)).tocsr()
        operators.append((averaging @ per_tet).tocsr())

    def magnitude(T):
        return np.sqrt(sum((op @ T) ** 2 for op in operators))

    return magnitude


class _Solver:
    """(diag(d) + K + Σ h F) x = b on the free nodes, by conjugate gradients preconditioned with a factor (or, with
    ``iterative``, a multigrid hierarchy) of the same matrix as it was when last built, rebuilt once the step or a
    mould coefficient has moved :data:`REBUILD_RATIO` times or a solve was slow (a new solver for new free nodes)."""

    def __init__(self, K, films: list, free, iterative: bool):
        self.K = K[free][:, free].tocsr()
        self.films = [matrix[free][:, free].tocsr() for matrix in films]
        self.iterative = iterative
        self.reference: tuple | None = None
        self.prec = None
        self.builds = 0
        self.iterations = 0
        self.last = 0

    def _stale(self, dt: float, hs: list[float]) -> bool:
        if self.reference is None or self.last > SLOW_CG:
            return True
        old_dt, old_hs = self.reference
        r = REBUILD_RATIO
        if not 1 / r <= dt / old_dt <= r:
            return True
        return any(not (h == old == 0 or (old > 0 and 1 / r <= h / old <= r)) for h, old in zip(hs, old_hs))

    def product(self, hs: list[float], x):
        """(K + Σ h F) x on the free nodes."""
        y = self.K @ x
        for h, F in zip(hs, self.films):
            if h:
                y = y + h * (F @ x)
        return y

    def solve(self, diagonal, dt: float, hs: list[float], b, x0):
        import scipy.sparse as sparse
        import scipy.sparse.linalg as spla

        A = self.K + sparse.diags(diagonal)
        for h, F in zip(hs, self.films):
            if h:
                A = A + h * F
        A = A.tocsr()
        if self._stale(dt, hs):
            if self.iterative:
                import pyamg

                ml = pyamg.smoothed_aggregation_solver(A, symmetry="symmetric", strength="symmetric", smooth="energy",
                                                       max_coarse=500)
                self.prec = ml.aspreconditioner(cycle="V")
            else:
                lu = spla.splu(A.tocsc())
                self.prec = spla.LinearOperator(A.shape, matvec=lu.solve)
            self.reference = (dt, list(hs))
            self.builds += 1
        count = [0]

        def counted(_):
            count[0] += 1

        x, info = spla.cg(A, b, x0=x0, M=self.prec, rtol=1e-11, atol=0.0, maxiter=500, callback=counted)
        self.iterations += count[0]
        self.last = count[0]
        if info:  # the preconditioner drifted too far from the matrix: build it afresh and solve again
            self.reference = None
            return self.solve(diagonal, dt, hs, b, x)
        return x


def march(
    space: "FemSpace",
    alloy: "CastingAlloy",
    *,
    pour_C: float,
    films: list[Film],
    held: Held | None,
    first_step_s: float,
    hand_s: float,
    end_s: float | None,
    span_C: float,
    frames: int = 24,
    iterative: bool = False,
    log: Callable[[str], None] | None = None,
    limit_s: float | None = None,
    stop_C: float | None = None,
    goal: str = "fully solid",
    watch_C: float | None = None,
) -> Cooling:
    """The casting from the pour (every node at ``pour_C``, held nodes at their temperature) to fully solid, or to
    ``end_s`` when given (cooling on after it is solid).

    ``stop_C`` moves the goal from the solidus to that temperature: the march runs until every node is below it, and
    ``freeze_s`` is when each passed it (a moulding's ejection temperature, below or within its crystallisation
    range). ``goal`` names it in the words of a run cut short. ``watch_C``: each node's time to fall below it is kept
    too (a semi-crystalline moulding's crystallisation onset).

    The step starts at ``first_step_s`` and adapts to the targets above (:data:`STEP_SHARE_T`, :data:`STEP_LIQUID`,
    :data:`STEP_NODE_H`; ``span_C`` is pour to mould); a step that moved more than :data:`REJECT_ABOVE` times them, or
    whose iterations did not settle, is taken again shorter. With no ``end_s`` it stops when every node is solid, or
    past :data:`PATIENCE` times ``hand_s`` (saying so). ``held`` faces are held until every other node is solid or
    ``held.until_s``, then handed to their ``after`` films. Frames are kept about every ``hand_s / (frames - 1)``, the spacing doubling as
    they fill. ``log`` gets a progress line at most every ``timestep.PROGRESS_S``; past ``limit_s`` seconds of wall
    time it stops after the step it is on.
    """
    import numpy as np

    from cadgen._internal.fea import operators
    from cadgen._internal.fea.thermal_ops import PER_M2
    from cadgen._internal.fea.timestep import Clock

    enthalpy = Enthalpy.of(alloy)
    n = space.mesh.p.shape[1]
    m = node_volumes(space)
    K = operators.conduction(space, [alloy]).tocsr()
    gradient = _gradient(space)

    def assembled(entries: list[Film]):
        out = []
        for film in entries:
            matrix, load = operators.convection(space, film.facets, PER_M2, film.ambient)   # at h = 1 W/(m² K)
            out.append((film, matrix.tocsr(), np.asarray(load), np.asarray(matrix.sum(axis=1)).ravel()))
        return out

    active = assembled(films)
    later = assembled(held.after) if held is not None else []
    hold = held is not None and len(held.dofs) > 0
    fixed = np.asarray(held.dofs, dtype=np.int64) if hold else np.zeros(0, dtype=np.int64)
    is_fixed = np.zeros(n, dtype=bool)
    is_fixed[fixed] = True

    def build(entries, fixed_mask):
        free = np.flatnonzero(~fixed_mask)
        return free, _Solver(K, [matrix for _, matrix, _, _ in entries], free, iterative)

    entries = active
    free, solver = build(entries, is_fixed)

    T = np.full(n, float(pour_C))
    if hold:
        T[fixed] = held.celsius
    H = enthalpy.H(T)
    H_solid = enthalpy.H_solid
    H_stop = H_solid if stop_C is None else float(enthalpy.H(stop_C))
    T_niyama = enthalpy.solidus + NIYAMA_SHARE * (enthalpy.liquidus - enthalpy.solidus)
    volume = float(m.sum())
    freeze = np.full(n, np.nan)
    watch = np.full(n, np.nan)
    niyama = np.full(n, np.nan)
    rate = np.full(n, np.nan)
    G = gradient(T)
    energy_start = float(m @ H)
    heat_out = heat_in = 0.0
    dT_target = max(span_C / STEP_SHARE_T, 0.5)
    dH_target = STEP_NODE_H * enthalpy.mushy_span
    # A step has settled once its Newton update moves no node's enthalpy by more than this (mJ/mm³).
    tolerance = 1e-9 * (enthalpy.rho_c * max(span_C, 1.0) + enthalpy.rho_L)

    kept: list = [(0.0, T.copy())]
    spacing = max(hand_s, first_step_s) / max(frames - 1, 1)
    next_frame = spacing
    liquid_now = 100.0 * float(m @ enthalpy.liquid(T)) / volume
    curve_t, curve_liquid = [0.0], [liquid_now]
    curve_mean, curve_above = [float(m @ T) / volume], [100.0 * float(m[H > H_stop].sum()) / volume]
    t, dt = 0.0, float(first_step_s)
    steps = rejected = passes = 0
    smallest, largest = math.inf, 0.0
    clock = Clock(log, limit_s)
    stopped_at, cut_short = None, ""

    def solid_everywhere() -> bool:
        return bool((H[~is_fixed] <= H_stop).all())

    def step(Tn, t0: float, dt: float):
        """T at t0 + dt from Tn, and whether its iterations settled."""
        nonlocal passes
        hs = [film.h_of(t0, t0 + dt) for film, _, _, _ in entries]
        load = np.zeros(n)
        for h, (_, _, film_load, _) in zip(hs, entries):
            load += h * film_load
        b = load
        if hold:
            x_fixed = np.zeros(n)
            x_fixed[fixed] = held.celsius
            coupling = K @ x_fixed
            for h, (_, matrix, _, _) in zip(hs, entries):
                if h:
                    coupling += h * (matrix @ x_fixed)
            b = load - coupling
        mf, Hn, bf = m[free] / dt, enthalpy.H(Tn[free]), b[free]

        def residual(enthalpies):
            return mf * (enthalpies - Hn) + solver.product(hs, enthalpy.temperature(enthalpies)) - bf

        # Newton on the nodes' enthalpies (the module's docstring); an update that would raise the residual is shortened.
        Hx = Hn.copy()
        R = residual(Hx)
        norm = float(np.abs(R).max())
        settled = False
        for _ in range(MAX_PASSES):
            passes += 1
            capacity = enthalpy.capacity(Hx)
            dT = solver.solve(mf * capacity, dt, hs, -R, np.zeros_like(Hx))
            if float(np.abs(capacity * dT).max()) < tolerance:
                Hx = Hx + capacity * dT
                settled = True
                break
            alpha = 1.0
            while True:
                trial = Hx + alpha * capacity * dT
                R_trial = residual(trial)
                if float(np.abs(R_trial).max()) <= norm or alpha <= 1.0 / 16:
                    break
                alpha *= 0.5
            Hx, R = trial, R_trial
            norm = float(np.abs(R).max())
        x = enthalpy.temperature(Hx)
        out = Tn.copy()
        out[free] = x
        return out, hs, load, settled

    while True:
        if end_s is not None:
            if t >= end_s * (1 - 1e-12):
                break
            dt = min(dt, end_s - t)
        elif not hold and solid_everywhere():
            break
        if end_s is None and t > PATIENCE * hand_s:
            advice = ("give the study a duration_s, or check the alloy, the mould temperature and h" if stop_C is None
                      else "check the temperatures and h")
            cut_short = f"still not {goal} after {t:.4g} s, {PATIENCE:g} times the hand estimate; {advice}"
            break
        if steps >= MAX_STEPS:
            cut_short = f"stopped after {MAX_STEPS} steps at t = {t:.4g} s"
            break
        T1, hs, load, settled = step(T, t, dt)
        H1 = enthalpy.H(T1)
        liquid_next = 100.0 * float(m @ enthalpy.liquid(T1)) / volume
        moved = max(float(np.abs(T1 - T).max()) / dT_target, abs(liquid_next - liquid_now) / STEP_LIQUID,
                    float(np.abs(H1 - H).max()) / dH_target)
        if (not settled or moved > REJECT_ABOVE) and dt > first_step_s * 1e-4:
            rejected += 1
            dt *= 0.5 if not settled else max(0.25, 0.7 / moved)
            continue
        # Accepted: the heat that crossed the boundary in the step, at the step's end (backward Euler).
        for h, (film, _, film_load, rows) in zip(hs, entries):
            heat_out += h * float(rows @ T1 - film_load.sum()) * dt
        if hold:
            residual = K @ T1 + sum(h * (matrix @ T1) for h, (_, matrix, _, _) in zip(hs, entries) if h) - load
            heat_in += float(residual[fixed].sum()) * dt
        G1 = gradient(T1)
        # Each node's time to fully solid (its enthalpy through the solidus's), and the Niyama temperature's crossing.
        crossed = np.isnan(freeze) & (H1 <= H_stop) & (H > H_stop)
        if crossed.any():
            share = (H[crossed] - H_stop) / (H[crossed] - H1[crossed])
            freeze[crossed] = t + share * dt
        if watch_C is not None:
            falling = np.isnan(watch) & (T1 <= watch_C) & (T > watch_C)
            if falling.any():
                watch[falling] = t + (T[falling] - watch_C) / (T[falling] - T1[falling]) * dt
        passing = np.isnan(niyama) & (T1 <= T_niyama) & (T > T_niyama)
        if passing.any():
            share = (T[passing] - T_niyama) / (T[passing] - T1[passing])
            cooling = (T[passing] - T1[passing]) / dt
            g = G[passing] + share * (G1[passing] - G[passing])
            rate[passing] = cooling
            niyama[passing] = g / np.sqrt(np.maximum(cooling, 1e-12))
        T, H, G, liquid_now = T1, H1, G1, liquid_next
        t += dt
        steps += 1
        smallest, largest = min(smallest, dt), max(largest, dt)
        curve_t.append(t)
        curve_liquid.append(liquid_now)
        curve_mean.append(float(m @ T) / volume)
        curve_above.append(100.0 * float(m[H > H_stop].sum()) / volume)
        if t >= next_frame * (1 - 1e-9):
            kept.append((t, T.copy()))
            next_frame = t + spacing
            if len(kept) > 2 * frames:
                kept = kept[::2]
                spacing *= 2
        dt *= min(1.5, max(0.5, 0.8 / moved)) if moved > 0 else 1.5
        if hold and (solid_everywhere() or t >= held.until_s):
            # The rest is solid, or the riser's time is up: the mould takes the held faces too.
            hold = False
            is_fixed[:] = False
            entries = active + later
            free, solver_next = build(entries, is_fixed)
            solver_next.builds, solver_next.iterations = solver.builds, solver.iterations
            solver = solver_next
        if stop_C is None:
            clock.tell(lambda: f"freezing: t = {t:.4g} s, {curve_liquid[-1]:.3g} % still liquid, {steps} steps")
        else:
            clock.tell(lambda: f"cooling: t = {t:.4g} s, {curve_above[-1]:.3g} % still above {stop_C:g} °C, {steps} steps")
        if clock.over():
            stopped_at = t
            break
    if kept[-1][0] != t:
        kept.append((t, T.copy()))
    chosen = _evenly(kept, frames)
    solid = bool((H <= H_stop).all())
    freeze = np.where(np.isnan(freeze), t, freeze)
    watched = None if watch_C is None else np.where(np.isnan(watch), np.where(T <= watch_C, 0.0, t), watch)
    if len(curve_t) > CURVE_POINTS:
        every = math.ceil(len(curve_t) / CURVE_POINTS)
        picks = sorted({0, len(curve_t) - 1, *range(0, len(curve_t), every)})
        curve_t, curve_liquid = [curve_t[i] for i in picks], [curve_liquid[i] for i in picks]
        curve_mean, curve_above = [curve_mean[i] for i in picks], [curve_above[i] for i in picks]
    how = ("multigrid-preconditioned CG" if iterative else "CG preconditioned by a SuperLU factor") + \
        f", backward Euler on the enthalpy, {steps} adaptive steps ({solver.builds} factorisations, " \
        f"{solver.iterations} CG iterations)"
    return Cooling(
        frames=chosen, freeze_s=freeze, niyama=niyama, cooling_rate=rate, end_s=t, solid=solid, steps=steps,
        rejected=rejected, passes=passes, smallest_step=smallest if steps else 0.0, largest_step=largest,
        heat_out=heat_out, heat_in=heat_in, energy_start=energy_start, energy_end=float(m @ H), curve_t=curve_t,
        curve_liquid=curve_liquid, final=T, stopped_at=stopped_at, cut_short=cut_short, solver=how,
        curve_mean=curve_mean, curve_above=curve_above, watch_s=watched,
    )


def _evenly(kept: list, frames: int) -> list:
    """At most ``frames`` of the kept states, the nearest to evenly spaced times from the first to the last."""
    if len(kept) <= frames:
        return list(kept)
    end = kept[-1][0]
    chosen = []
    for i in range(frames):
        target = end * i / (frames - 1)
        best = min(range(len(kept)), key=lambda j: (abs(kept[j][0] - target), j))
        if not chosen or chosen[-1] != best:
            chosen.append(best)
    return [kept[j] for j in sorted(set(chosen))]


# -- where shrinkage collects ------------------------------------------------------------------------


@dataclass(frozen=True)
class Pocket:
    """A liquid region cut off from every feeder while it still had to freeze: shrinkage collects there."""

    #: The node that freezes last in it, and when.
    peak: int
    freeze_s: float
    #: When it was cut off from the last feeder (0 when nothing ever fed it).
    cut_s: float
    #: Its liquid volume when cut off (or, fed by nothing, the volume that freezes in its last tenth of the time), mm³.
    volume_mm3: float
    #: Nothing ever fed it: the study names no feeder.
    unfed: bool = False


def pockets(freeze_s, graph, volumes, feeder, *, min_life_s: float, min_volume_mm3: float) -> list[Pocket]:
    """The isolated hot spots, latest to freeze first.

    The liquid at time τ is the nodes that freeze after τ; a region of it is fed while it holds a feeder node (a
    feeder is taken to outlast the casting, as a riser sized for it does). Nodes are added from the last to freeze
    back (union-find), so the regions are built up in reverse; a region that has no feeder when it joins one that
    has, or when a feeder node joins it, was cut off from feeding at that moment, and is a hot spot when it then
    stayed liquid at least ``min_life_s`` and held at least ``min_volume_mm3``. Two unfed regions that join are two hot
    spots once the pair is cut off. With no feeder at all, the region that freezes last is one, fed by nothing.
    """
    import numpy as np

    indptr, indices = graph
    n = len(freeze_s)
    key = np.where(feeder, np.inf, freeze_s)
    order = np.argsort(-key, kind="stable")
    parent = np.full(n, -1, dtype=np.int64)
    volume = np.zeros(n)
    peak = np.arange(n)
    fed = np.asarray(feeder, dtype=bool).copy()
    pending: dict[int, list[Pocket]] = {}
    found: list[Pocket] = []

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    def significant(root: int, cut: float) -> Pocket | None:
        life = freeze_s[peak[root]] - cut
        if life >= min_life_s and volume[root] >= min_volume_mm3 and not fed[root]:
            return Pocket(int(peak[root]), float(freeze_s[peak[root]]), float(cut), float(volume[root]))
        return None

    for i in order:
        i = int(i)
        parent[i] = i
        volume[i] = volumes[i]
        roots = {find(int(j)) for j in indices[indptr[i]:indptr[i + 1]] if parent[j] >= 0}
        roots.discard(i)
        if not roots:
            continue
        cut = float(key[i])
        eldest = max(roots, key=lambda r: (freeze_s[peak[r]] if not fed[r] else np.inf, -r))
        any_fed = bool(feeder[i]) or any(fed[r] for r in roots)
        merged_pending: list[Pocket] = []
        for r in roots:
            if fed[r]:
                continue
            if any_fed:
                # Cut off from feeding at `cut`: it and every hot spot inside it.
                pocket = significant(r, cut)
                found.extend(([pocket] if pocket else []) + pending.pop(r, []))
            elif r != eldest:
                pocket = significant(r, cut)
                merged_pending.extend(([pocket] if pocket else []) + pending.pop(r, []))
        for r in roots:
            parent[r] = eldest
        parent[i] = eldest
        volume[eldest] = volume[i] + sum(volume[r] for r in roots)
        if not any_fed and merged_pending:
            pending.setdefault(eldest, []).extend(merged_pending)
        fed[eldest] = any_fed
        if not fed[eldest] and freeze_s[i] > freeze_s[peak[eldest]]:
            peak[eldest] = i
    # A region nothing ever fed (no feeder named): the last tenth of its freezing is where its shrinkage collects.
    for root in sorted({find(i) for i in range(n)}):
        if fed[root]:
            continue
        members = np.array([i for i in range(n) if find(i) == root])
        last = float(freeze_s[peak[root]])
        tail = members[freeze_s[members] >= 0.9 * last]
        found.append(Pocket(int(peak[root]), last, 0.0, float(volumes[tail].sum()), unfed=True))
        found.extend(pending.pop(root, []))
    return sorted(found, key=lambda pocket: -pocket.freeze_s)


# -- sections ------------------------------------------------------------------------------------------


@dataclass
class Section:
    """The section under each surface triangle: its thickness along the inward normal, and when it is solid through."""

    #: (B,) mm, and the time (s) the last node the ray crosses freezes.
    thickness: "np.ndarray"
    freeze_s: "np.ndarray"
    #: (B, 3): the middle of each section, mm.
    middle: "np.ndarray"
    #: (B,) whether the walk found the far side (a ray that ran out of steps is not measured).
    measured: "np.ndarray"


def sections(space: "FemSpace", freeze_s: "np.ndarray", max_steps: int = 2000) -> Section:
    """Walks every surface triangle's inward normal through the tets to the far surface, all rays at once.

    Each ray starts at its triangle's centroid in the tet behind it and leaves each tet through the face its line
    meets first ahead of it; a face with no tet beyond is the far surface. The section's freezing time is the latest of
    every node of the tets crossed (the middle freezes last).
    """
    import numpy as np

    mesh = space.mesh
    points = mesh.p.T
    facets = mesh.facets.T                                   # (F, 3)
    f2t = mesh.f2t                                           # (2, F), -1 beyond the surface
    t2f = mesh.t2f                                           # (4, E)
    tets = mesh.t
    a, b, c = points[facets[:, 0]], points[facets[:, 1]], points[facets[:, 2]]
    normal = np.cross(b - a, c - a)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    offset = np.einsum("ij,ij->i", normal, a)
    boundary = mesh.boundary_facets()
    start_tet = f2t[0, boundary]
    centroid = (a[boundary] + b[boundary] + c[boundary]) / 3.0
    inward = normal[boundary].copy()
    tet_middle = points[tets[:, start_tet].T].mean(axis=1)
    flip = np.einsum("ij,ij->i", tet_middle - centroid, inward) < 0
    inward[flip] *= -1
    rays = len(boundary)
    tet = start_tet.copy()
    s = np.zeros(rays)
    latest = freeze_s[tets[:, tet]].max(axis=0)
    done = np.zeros(rays, dtype=bool)
    thickness = np.full(rays, np.nan)
    entered = boundary.copy()
    for _ in range(max_steps):
        live = np.flatnonzero(~done)
        if not len(live):
            break
        faces = t2f[:, tet[live]].T                          # (R, 4)
        along = np.einsum("rkj,rj->rk", normal[faces], inward[live])
        reach = offset[faces] - np.einsum("rkj,rj->rk", normal[faces], centroid[live])
        with np.errstate(divide="ignore", invalid="ignore"):
            hit = reach / along
        scale = np.maximum(s[live], 1e-6)[:, None]
        hit[(faces == entered[live][:, None]) | ~np.isfinite(hit) | (hit <= s[live][:, None] + 1e-9 * scale)] = np.inf
        pick = hit.argmin(axis=1)
        exit_face = faces[np.arange(len(live)), pick]
        exit_s = hit[np.arange(len(live)), pick]
        stuck = ~np.isfinite(exit_s)
        beyond = np.where(f2t[0, exit_face] == tet[live], f2t[1, exit_face], f2t[0, exit_face])
        out = (beyond < 0) & ~stuck
        thickness[live[out]] = exit_s[out]
        done[live[out | stuck]] = True
        going = live[~out & ~stuck]
        keep = ~out & ~stuck
        tet[going] = beyond[keep]
        s[going] = exit_s[keep]
        entered[going] = exit_face[keep]
        latest[going] = np.maximum(latest[going], freeze_s[tets[:, tet[going]]].max(axis=0))
    measured = np.isfinite(thickness)
    middle = centroid + inward * np.where(measured, thickness / 2.0, 0.0)[:, None]
    return Section(thickness=np.where(measured, thickness, 0.0), freeze_s=latest, middle=middle, measured=measured)


def boundary_facet_rows(space: "FemSpace") -> "np.ndarray":
    """The row of ``space.boundary_quadratic`` (the mesher's surface triangles) of each of skfem's boundary facets, in
    ``mesh.boundary_facets()`` order: how a section's ray names its face."""
    import numpy as np

    triangles = np.sort(np.asarray(space.boundary_quadratic)[:, :3].astype(np.int64), axis=1)
    facets = np.sort(space.mesh.facets[:, space.mesh.boundary_facets()].T.astype(np.int64), axis=1)
    n = space.mesh.p.shape[1]
    keys = (triangles[:, 0] * n + triangles[:, 1]) * n + triangles[:, 2]
    wanted = (facets[:, 0] * n + facets[:, 1]) * n + facets[:, 2]
    order = np.argsort(keys)
    where = order[np.clip(np.searchsorted(keys[order], wanted), 0, len(keys) - 1)]
    return np.where(keys[where] == wanted, where, -1)
