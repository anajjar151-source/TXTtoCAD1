"""A part's warp from an inherent strain: a shrinkage that differs from place to place, held at three points.

:func:`warp` takes one isotropic strain per linear tet (a moulding's differential shrinkage) and solves the linear
static problem it loads, K u = ∫ C:ε0 : ε(v), on quadratic tets made from the same linear ones (straight edges, a
midpoint on each), because linear tets are too stiff in bending to show a warp. The part is held as a fixture holds
it to measure it, 3-2-1, at three of its corners far apart (:func:`hold_points`): the first in all three directions,
the second in the two across the line to it, the third along the normal of their plane. That takes out the six rigid
motions and nothing more, so the hold puts no stress in and its reactions vanish (an inherent strain loads the part
with no net force or moment). The modulus cancels from u: only Poisson's ratio reaches it.

Units are the engine's: mm, MPa. Numeric imports live inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = ["Warp", "hold_points", "warp"]

#: The modulus the solve uses, MPa: any value gives the same displacement.
MODULUS = 1000.0


@dataclass
class Warp:
    #: (vertices, 3) mm: each linear vertex's displacement.
    displacement: "np.ndarray"
    #: The three held vertices and, for each, the directions held (0, 1, 2 for x, y, z).
    held: list[tuple[int, tuple[int, ...]]]
    #: The hold's reactions against the load, as a share: zero when the hold took out rigid motion only.
    reaction_share: float
    dofs: int
    how: str


def hold_points(points: "np.ndarray") -> list[tuple[int, tuple[int, ...]]]:
    """3-2-1 on three of ``points`` far apart: A, the farthest from the middle (x, y and z held); B, the farthest from A
    (held in the two directions other than the one along AB most); C, the farthest from the line AB (held along the
    direction the plane ABC's normal points most). The constraint removes every rigid motion: a rotation about AB is
    the only one A and B leave, and C's held direction is the one it moves along."""
    import numpy as np

    middle = points.mean(axis=0)
    a = int(np.argmax(np.linalg.norm(points - middle, axis=1)))
    b = int(np.argmax(np.linalg.norm(points - points[a], axis=1)))
    along = points[b] - points[a]
    unit = along / np.linalg.norm(along)
    offsets = points - points[a]
    across = offsets - np.outer(offsets @ unit, unit)
    c = int(np.argmax(np.linalg.norm(across, axis=1)))
    normal = np.cross(along, points[c] - points[a])
    axis_b = int(np.argmax(np.abs(along)))
    return [(a, (0, 1, 2)), (b, tuple(i for i in range(3) if i != axis_b)), (c, (int(np.argmax(np.abs(normal))),))]


def warp(space: "FemSpace", strain: "np.ndarray", nu: float, *, warnings: list[str] | None = None) -> Warp:
    """The displacement of the linear ``space``'s vertices under ``strain`` (one isotropic stress-free strain per
    tet, as a thermal α ΔT is), held 3-2-1 at :func:`hold_points` of its surface vertices."""
    import numpy as np
    from skfem import MeshTet2

    from cadgen._internal.fea import operators
    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

    if space.order != 1:
        raise ValueError("warp: the inherent strain is solved from linear tets (mesh.order 1)")
    quadratic = FemSpace.from_mesh(MeshTet2.from_mesh(space.mesh), order=2)
    vertices = space.vertices
    if not np.allclose(quadratic.dof_locations[:vertices], space.dof_locations, atol=1e-9):
        raise RuntimeError("warp: the quadratic tets renumbered the linear vertices")
    material = Material("warp", MODULUS, nu, None, 1e-9)
    points = quadratic.basis.X.shape[1]
    load = operators.initial_strain_load(quadratic, material, np.repeat(np.asarray(strain, float)[:, None], points, axis=1))
    K = operators.stiffness(quadratic, material)
    surface = np.unique(np.asarray(space.boundary_quadratic)[:, :3])
    held = [(int(surface[i]), axes) for i, axes in hold_points(space.dof_locations[surface])]
    fixed = np.array([quadratic.basis.nodal_dofs[axis][vertex] for vertex, axes in held for axis in axes], dtype=np.int64)
    free = np.setdiff1d(np.arange(quadratic.dofs), fixed)
    u = np.zeros(quadratic.dofs)
    u[free], how = operators.solve_spd(K, load, free, quadratic.locations, quadratic.component,
                                       warnings if warnings is not None else [])
    reaction = (K @ u - load)[fixed]
    share = float(np.linalg.norm(reaction) / max(float(np.linalg.norm(load)), 1e-300))
    return Warp(quadratic.nodal(u)[:vertices], held, share, int(quadratic.dofs), how)
