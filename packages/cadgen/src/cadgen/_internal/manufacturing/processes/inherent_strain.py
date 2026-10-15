"""Inherent strain: the distortion and residual stress a process leaves, from the strain it locks into the material.

A weld cooling beside cold metal, a printed layer shrinking on the layers below it: each leaves the material near it a
strain it would take up if it were free, its *inherent strain* ε* (Ueda's term), here a tensor per element. Held by
the rest of the part it cannot, so the part distorts and is stressed: a linear elastic static solve with ε* as a
stress-free strain, σ = C:(ε(u) - ε*), on the engine's element space (quadratic or linear tets, small strain, one
isotropic material). This module is that solve, shared by the processes that use it:

- :func:`solve_once`: every element's ε* at once (a weld's zones, all welds together);
- :class:`Build`: elements born in groups (a print's height bands), each group stress-free on the part already built
  and deformed, carrying its own ε*, the groups before it keeping theirs; the elements' strain counts from their birth.
  :meth:`Build.release` lets go of the holds (the build plate, supports) and the part springs back.

Holds are vector DOFs held at zero: a plate's every node, or :func:`hold_free`'s six (3-2-1), which stop the part's
rigid motion without stressing it. :func:`rigid_part` is the rigid motion that best fits a displacement, so what is
reported is the distortion, not where the part went. Units are the engine's (mm, N, MPa). Stdlib only at import.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

__all__ = [
    "Build", "Once", "at_points", "default_tolerance_mm", "element_centroids", "element_volumes", "hold_free",
    "lowest_nodes", "nodal_von_mises", "quadrature_points", "rigid_part", "solve_once", "stress_of", "tensor_field", "vector_dofs",
]

#: ISO 2768-2 class K (medium) general flatness and straightness tolerance, mm, by the length of the feature: up to
#: 10, 30, 100, 300, 1000 and 3000 mm. The tolerance a distortion is judged against when the study gives none.
ISO_2768_K = ((10.0, 0.05), (30.0, 0.1), (100.0, 0.2), (300.0, 0.4), (1000.0, 0.6), (3000.0, 0.8))


def default_tolerance_mm(length_mm: float) -> float:
    """ISO 2768-2 class K's general flatness tolerance for a feature ``length_mm`` long (0.8 mm past 3 m)."""
    for upto, tolerance in ISO_2768_K:
        if length_mm <= upto:
            return tolerance
    return ISO_2768_K[-1][1]


# -- strains as arrays ---------------------------------------------------------------------------------


def tensor_field(count: int, parts: Sequence[tuple[Any, Any]]) -> "np.ndarray":
    """Σ s d⊗d over ``parts`` as (3, 3, count): each part a direction ``d`` ((3,) or (count, 3), unit) and a strain
    ``s`` (a number or (count,)) along it. An in-plane strain is two such parts; an isotropic one, three."""
    import numpy as np

    out = np.zeros((3, 3, count))
    for direction, strain in parts:
        d = np.broadcast_to(np.asarray(direction, dtype=float), (count, 3))
        s = np.broadcast_to(np.asarray(strain, dtype=float), (count,))
        out += np.einsum("e,ei,ej->ije", s, d, d)
    return out


def at_points(space: "FemSpace", strain: "np.ndarray", basis=None) -> "np.ndarray":
    """A strain at the basis's quadrature points, (3, 3, E, Q): one per element ((3, 3, E)) repeated at each of its
    points, or already per point ((3, 3, E, Q)) as given."""
    import numpy as np

    strain = np.asarray(strain, dtype=float)
    if strain.ndim == 4:
        return strain
    points = (basis or space.basis).dx.shape[1]
    return np.repeat(strain[..., None], points, axis=-1)


def quadrature_points(space: "FemSpace") -> "np.ndarray":
    """(3, E, Q): where each element's quadrature points are, mm (a strain that varies inside an element is evaluated
    there, so its moments are exact)."""
    return space.basis.mapping.F(space.basis.X)


def element_centroids(space: "FemSpace") -> "np.ndarray":
    """(E, 3): each element's corner average, mm."""
    return space.mesh.p[:, space.mesh.t].mean(axis=1).T


def element_volumes(space: "FemSpace") -> "np.ndarray":
    """(E,): each element's volume, mm³ (the quadrature weights summed)."""
    return space.basis.dx.sum(axis=1)


def _lame(material: "Material") -> tuple[float, float]:
    from skfem.models.elasticity import lame_parameters

    return lame_parameters(material.E, material.nu)


def stress_of(material: "Material", strain: "np.ndarray") -> "np.ndarray":
    """σ = 2 μ ε + λ tr(ε) I for any (3, 3, ...) strain, MPa."""
    import numpy as np

    lam, mu = _lame(material)
    out = 2.0 * mu * np.asarray(strain, dtype=float)
    trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
    for i in range(3):
        out[i, i] = out[i, i] + lam * trace
    return out


def nodal_von_mises(space: "FemSpace", sigma: "np.ndarray") -> "np.ndarray":
    """Von Mises of a (3, 3, E, Q) stress, projected onto the nodes (never below zero), MPa."""
    import numpy as np

    from cadgen._internal.fea import operators

    return np.maximum(space.scalar.project(operators.von_mises(sigma)), 0.0)


# -- DOF bookkeeping -----------------------------------------------------------------------------------


def vector_dofs(space: "FemSpace", nodes) -> "np.ndarray":
    """Every vector DOF (all three components) of the scalar ``nodes`` (vertices first, then edge midpoints)."""
    import numpy as np

    nodes = np.unique(np.asarray(nodes, dtype=np.int64))
    corners = nodes[nodes < space.vertices]
    middles = nodes[nodes >= space.vertices] - space.vertices
    out = [space.basis.nodal_dofs[c][corners] for c in range(3)]
    if space.order == 2 and len(middles):
        out += [space.basis.edge_dofs[c][middles] for c in range(3)]
    return np.unique(np.concatenate(out)) if out else np.zeros(0, dtype=np.int64)


def _dof(space: "FemSpace", node: int, component: int) -> int:
    if node < space.vertices:
        return int(space.basis.nodal_dofs[component][node])
    return int(space.basis.edge_dofs[component][node - space.vertices])


def hold_free(space: "FemSpace", nodes=None) -> "np.ndarray":
    """Six vector DOFs (3-2-1) among the corner ``nodes`` (default every vertex) that stop the part's rigid motion and
    stress nothing: one node held in x, y and z; the node farthest from it held across the line between them; the node
    farthest from that line held across the plane of the three."""
    import numpy as np

    points = space.dof_locations
    nodes = np.arange(space.vertices) if nodes is None else np.asarray(nodes, dtype=np.int64)
    nodes = nodes[nodes < space.vertices]
    if len(nodes) < 3:
        raise ValueError("a free part needs three corners to hold it still")
    centre = points[nodes].mean(axis=0)
    a = int(nodes[np.argmax(np.linalg.norm(points[nodes] - centre, axis=1))])
    b = int(nodes[np.argmax(np.linalg.norm(points[nodes] - points[a], axis=1))])
    line = points[b] - points[a]
    line /= max(float(np.linalg.norm(line)), 1e-300)
    off = points[nodes] - points[a]
    across = off - np.outer(off @ line, line)
    c = int(nodes[np.argmax(np.linalg.norm(across, axis=1))])
    normal = np.cross(line, points[c] - points[a])
    if not np.linalg.norm(normal) > 1e-9 * max(float(np.linalg.norm(points[c] - points[a])), 1e-300):
        raise ValueError("a free part's corners all lie on one line: it cannot be held still")
    normal /= np.linalg.norm(normal)
    # b moves along the line only: hold the two axes the line is least along. c moves in the plane only.
    b_axes = np.argsort(np.abs(line))[:2]
    c_axis = int(np.argmax(np.abs(normal)))
    held = [_dof(space, a, k) for k in range(3)] + [_dof(space, b, int(k)) for k in b_axes] + [_dof(space, c, c_axis)]
    return np.asarray(sorted(set(held)), dtype=np.int64)


def lowest_nodes(space: "FemSpace", nodes, direction, tolerance: float) -> "np.ndarray":
    """The ``nodes`` within ``tolerance`` of the lowest of them along ``direction``."""
    import numpy as np

    nodes = np.asarray(nodes, dtype=np.int64)
    height = space.dof_locations[nodes] @ np.asarray(direction, dtype=float)
    return nodes[height <= height.min() + tolerance]


def rigid_part(points: "np.ndarray", u: "np.ndarray") -> "np.ndarray":
    """The rigid motion t + ω × (x - x̄) that best fits ``u`` at ``points`` (least squares), evaluated at ``points``:
    subtract it to keep only the distortion."""
    import numpy as np

    x = np.asarray(points, dtype=float) - np.asarray(points, dtype=float).mean(axis=0)
    n = len(x)
    A = np.zeros((3 * n, 6))
    for k in range(3):
        A[k::3, k] = 1.0
    # ω × x = (ω_y z - ω_z y, ω_z x - ω_x z, ω_x y - ω_y x)
    A[0::3, 4], A[0::3, 5] = x[:, 2], -x[:, 1]
    A[1::3, 3], A[1::3, 5] = -x[:, 2], x[:, 0]
    A[2::3, 3], A[2::3, 4] = x[:, 1], -x[:, 0]
    coefficients, *_ = np.linalg.lstsq(A, np.asarray(u, dtype=float).ravel(), rcond=None)
    return (A @ coefficients).reshape(n, 3)


# -- the solves ----------------------------------------------------------------------------------------


def _subset(space: "FemSpace", elements: "np.ndarray"):
    """The vector basis on ``elements`` alone (the full space's DOF numbering and quadrature)."""
    from skfem import Basis

    return Basis(space.mesh, space.basis.elem, elements=elements, quadrature=space.basis.quadrature, dofs=space.basis.dofs)


def _stiffness(basis, material: "Material"):
    from skfem import asm
    from skfem.models.elasticity import linear_elasticity

    return asm(linear_elasticity(*_lame(material)), basis).tocsr()


def _load(basis, material: "Material", strain_q: "np.ndarray") -> "np.ndarray":
    """f = ∫ C:ε* : ε(v) over the basis's elements: the load a stress-free strain puts on the part."""
    from skfem import LinearForm, asm
    from skfem.helpers import ddot, sym_grad

    @LinearForm
    def form(v, w):
        return ddot(w["sigma0"], sym_grad(v))

    return asm(form, basis, sigma0=stress_of(material, strain_q))


def _internal(space: "FemSpace", sigma_q: "np.ndarray") -> "np.ndarray":
    """g = ∫ σ : ε(v): the force the part's own stress puts on each DOF; zero where nothing holds it."""
    from skfem import LinearForm, asm
    from skfem.helpers import ddot, sym_grad

    @LinearForm
    def form(v, w):
        return ddot(w["sigma"], sym_grad(v))

    return asm(form, space.basis, sigma=sigma_q)


def _strain(space: "FemSpace", u: "np.ndarray") -> "np.ndarray":
    import numpy as np

    grad = space.basis.interpolate(u).grad
    return 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))


def _solve(K, f: "np.ndarray", free: "np.ndarray", space: "FemSpace", warnings: list[str], method: str | None):
    import numpy as np

    from cadgen._internal.fea import operators

    u = np.zeros(space.basis.N)
    if len(free):
        u[free], how = operators.solve_spd(K, f, free, space.locations, space.component, warnings, method=method)
    else:
        how = "nothing free"
    return u, how


@dataclass
class Once:
    """One solve of every element's inherent strain together."""

    #: (N,) displacement on the vector DOFs, mm.
    u: "np.ndarray"
    #: (3, 3, E, Q) residual stress, MPa.
    stress: "np.ndarray"
    how: str
    warnings: list[str] = field(default_factory=list)


def solve_once(space: "FemSpace", material: "Material", strain: "np.ndarray", held: "np.ndarray", *,
               method: str | None = None) -> Once:
    """Every element's inherent strain ``strain`` ((3, 3, E), or (3, 3, E, Q) per point) at once, the vector DOFs
    ``held`` at zero."""
    import numpy as np

    warnings: list[str] = []
    strain_q = at_points(space, strain)
    K = _stiffness(space.basis, material)
    f = _load(space.basis, material, strain_q)
    free = np.setdiff1d(np.arange(space.basis.N), held)
    u, how = _solve(K, f, free, space, warnings, method)
    return Once(u=u, stress=stress_of(material, _strain(space, u) - strain_q), how=how, warnings=warnings)


class Build:
    """A part built in groups of elements, each born stress-free on what is already built and deformed.

    :meth:`add` births a group with its inherent strain and solves its step: the part built so far (its stiffness),
    held at the DOFs held so far, takes the new group's load. An element's strain counts from its birth, so its stress
    is C:(Σ ε(Δu) since its birth - ε*); its nodes shared with the part below move with it from the start. The
    displacement is the sum of the steps', which on a node born later is its motion since it was put down.
    """

    def __init__(self, space: "FemSpace", material: "Material", *, method: str | None = None,
                 log: Callable[[str], None] | None = None):
        import numpy as np

        self.space, self.material, self.method, self.log = space, material, method, log
        E = space.mesh.t.shape[1]
        points = space.basis.dx.shape[1]
        self.born = np.zeros(E, dtype=bool)
        self.inherent = np.zeros((3, 3, E, points))
        self.strain = np.zeros((3, 3, E, points))       # each element's strain since its birth
        self.u = np.zeros(space.basis.N)
        self.K = None
        self.held = np.zeros(0, dtype=np.int64)
        self.active_nodes = np.zeros(space.scalar_count, dtype=bool)
        self.warnings: list[str] = []
        self.how = ""

    def hold(self, dofs) -> None:
        """Hold these vector DOFs at zero from now on (a plate, a support)."""
        import numpy as np

        self.held = np.union1d(self.held, np.asarray(dofs, dtype=np.int64))

    def add(self, elements, strain: "np.ndarray") -> "np.ndarray":
        """Birth ``elements`` with their inherent strain ``strain`` ((3, 3, n) per element, or (3, 3, n, Q) per point)
        and solve the step. Returns the step's displacement Δu on the vector DOFs."""
        import numpy as np

        space = self.space
        elements = np.asarray(elements, dtype=np.int64)
        if len(elements) == 0:
            return np.zeros(space.basis.N)
        if self.born[elements].any():
            raise ValueError("an element is born only once")
        self.born[elements] = True
        basis = _subset(space, elements)
        strain = at_points(space, strain, basis)
        self.inherent[:, :, elements] = strain
        self.active_nodes[np.unique(space.scalar.element_dofs[:, elements])] = True
        K_new = _stiffness(basis, self.material)
        self.K = K_new if self.K is None else (self.K + K_new).tocsr()
        f = _load(basis, self.material, strain)
        active = vector_dofs(space, np.flatnonzero(self.active_nodes))
        free = np.setdiff1d(active, self.held)
        du, self.how = _solve(self.K, f, free, space, self.warnings, self.method)
        self.u += du
        step = _strain(space, du)
        self.strain[:, :, self.born] += step[:, :, self.born]
        return du

    def stress(self) -> "np.ndarray":
        """(3, 3, E, Q): C:(strain since birth - ε*) on the born elements, zero on the rest, MPa."""
        import numpy as np

        sigma = stress_of(self.material, self.strain - self.inherent)
        sigma[:, :, ~self.born] = 0.0
        return sigma

    def reactions(self) -> "np.ndarray":
        """(N,) the force the holds put on the part, N: its own stress's internal force, nonzero only where held."""
        return _internal(self.space, self.stress())

    def release(self, keep: "np.ndarray") -> "np.ndarray":
        """Let go of every hold but ``keep`` (a free part's 3-2-1): the part, its stress self-balanced, springs back.
        Returns the release's displacement; ``u`` and the strains take it in."""
        import numpy as np

        space = self.space
        g = self.reactions()
        active = vector_dofs(space, np.flatnonzero(self.active_nodes))
        free = np.setdiff1d(active, keep)
        du, self.how = _solve(self.K, -g, free, space, self.warnings, self.method)
        self.u += du
        step = _strain(space, du)
        self.strain[:, :, self.born] += step[:, :, self.born]
        self.held = np.asarray(keep, dtype=np.int64)
        return du
