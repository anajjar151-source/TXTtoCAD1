"""A bent sheet read from its B-rep, and the shape it springs back to.

A bent sheet is flats joined by bends: each bend is an inside and an outside cylinder of one axis, one thickness apart,
over the same arc, and each straight edge of a bend's arc is tangent to the flat it joins (:func:`read_sheet`). A part
with no such pair is not a bent sheet, and one whose bends or flats are not all one thickness is not one sheet: both are
refused in a sentence. The flats and bends make a tree (a graph, for a closed loop) rooted at the flat held still.

Every mesh node is placed in a bend (by its angle about the bend's axis, its radius and its place along it) or in the
flat its connected piece of the rest belongs to (:func:`node_regions`). The springback (:func:`spring_back`) keeps
each bend's mid-thickness length and opens its arc by the angle it springs back: the bend's points turn with it, by their
share of its arc, and every flat past it turns rigidly, so the flats far from the held one carry the sum of the
springback between. Bend ends that need a relief cut are found by probing the material just past them
(:func:`missing_reliefs`). Numeric and OCP imports are inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

__all__ = ["Bend", "Flat", "Sheet", "missing_reliefs", "node_regions", "read_sheet", "spring_back"]

#: Two cylinders share an axis when their directions agree this closely and their lines pass this close (x thickness).
_PARALLEL = 1e-6
_ON_LINE = 1e-3
#: Bends and flats are one thickness when they agree to this share of it.
_SAME_THICKNESS = 0.02
#: A part whose volume is more than this many times its surface area x thickness / 2 is mostly thicker than its bends.
_SHEET_VOLUME = 1.3


@dataclass
class Arc:
    """One bend surface: a cylinder's faces over one arc, in the bend's canonical axis direction."""

    ordinals: list[int]
    radius: float
    origin: Any            # (3,) a point on the axis
    axis: Any              # (3,) unit, canonical (its largest component positive)
    start: Any             # (3,) unit radial direction where the arc starts (turning +angle about axis reaches end)
    end: Any
    angle: float           # rad
    z0: float              # the arc's extent along the axis, from origin
    z1: float


@dataclass
class Bend:
    inner: Arc
    outer: Arc
    thickness: float
    #: Each side's (start, end) flat: an index into Sheet.flats.
    sides: list[int] = field(default_factory=list)
    #: 1-based, in the order the tree reaches it from the held flat.
    number: int = 0
    #: 0 when the tree reaches it from its start side, 1 from its end side; None for a bend that closes a loop.
    parent_side: int | None = 0

    @property
    def radius(self) -> float:
        return self.inner.radius

    @property
    def angle_deg(self) -> float:
        return math.degrees(self.inner.angle)

    @property
    def length(self) -> float:
        return self.inner.z1 - self.inner.z0

    @property
    def ordinals(self) -> list[int]:
        return [*self.inner.ordinals, *self.outer.ordinals]

    def middle(self):
        """The middle of its arc at mid-thickness, mid-length (mm)."""
        arc = self.inner
        half = _rotate(arc.start, arc.axis, arc.angle / 2.0)
        return arc.origin + (arc.radius + self.thickness / 2.0) * half + 0.5 * (arc.z0 + arc.z1) * arc.axis


@dataclass
class Flat:
    #: 1-based, in the order the tree reaches it (the held flat is 1).
    number: int
    ordinals: tuple[int, ...]
    area: float
    #: The faces' centre (mm), area-weighted.
    centre: Any = None


@dataclass
class Sheet:
    thickness: float
    bends: list[Bend]
    flats: list[Flat]
    #: The held flat: index into flats.
    fixed: int
    #: The tree from the held flat: (bend index, parent flat index, child flat index), in the order reached.
    tree: list[tuple[int, int, int]]


def _rotate(vector, axis, angle: float):
    """``vector`` turned by ``angle`` about the unit ``axis`` (Rodrigues)."""
    import numpy as np

    c, s = math.cos(angle), math.sin(angle)
    return vector * c + np.cross(axis, vector) * s + axis * float(np.dot(axis, vector)) * (1.0 - c)


def _canonical(axis):
    """The axis turned so its largest component is positive: coaxial faces read in one direction."""
    import numpy as np

    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    return -axis if axis[int(np.argmax(np.abs(axis)))] < 0 else axis


def _vec(point_or_dir):
    import numpy as np

    return np.array([point_or_dir.X(), point_or_dir.Y(), point_or_dir.Z()], dtype=float)


def _cylinder_arc(face, ordinal: int) -> Arc | None:
    """One cylindrical face as an arc in its canonical axis direction; ``None`` for a whole circle (a hole's wall)."""
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools

    surface = BRepAdaptor_Surface(face)
    cylinder = surface.Cylinder()
    position = cylinder.Position()
    loc, X, Y, Z = (_vec(position.Location()), _vec(position.XDirection()), _vec(position.YDirection()),
                    _vec(position.Direction()))
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    span = u1 - u0
    if span >= 2.0 * math.pi - 1e-6 or span <= 1e-9:
        return None

    def radial(u: float):
        return math.cos(u) * X + math.sin(u) * Y

    start, end, middle = radial(u0), radial(u1), radial(0.5 * (u0 + u1))
    axis = _canonical(Z)
    # The sense in which the arc turns from its start to its end, about the canonical axis.
    sense = float(np.dot(axis, np.cross(start, middle)))
    if sense < 0:
        start, end = end, start
    flip = float(np.dot(Z, axis))
    za, zb = sorted((v0 * flip, v1 * flip))
    return Arc([ordinal], float(cylinder.Radius()), loc, axis, start, end, span, za, zb)


def _same_line(a: Arc, b: Arc, scale: float) -> bool:
    import numpy as np

    if np.linalg.norm(np.cross(a.axis, b.axis)) > _PARALLEL:
        return False
    offset = b.origin - a.origin
    return float(np.linalg.norm(offset - np.dot(offset, a.axis) * a.axis)) < _ON_LINE * scale


def _rebase(arc: Arc, origin) -> Arc:
    """The arc's axial extent measured from ``origin`` on its axis."""
    import numpy as np

    shift = float(np.dot(arc.origin - origin, arc.axis))
    return Arc(arc.ordinals, arc.radius, origin, arc.axis, arc.start, arc.end, arc.angle, arc.z0 + shift, arc.z1 + shift)


def _merge(arcs: list[Arc], scale: float) -> list[Arc]:
    """Faces of one cylinder whose arcs continue one another (a bend split at a seam) and overlap along it, as one."""
    import numpy as np

    arcs = list(arcs)
    merged = True
    while merged:
        merged = False
        for i in range(len(arcs)):
            for j in range(len(arcs)):
                a, b = arcs[i], arcs[j]
                if i == j or abs(a.radius - b.radius) > 1e-6 * scale or not _same_line(a, b, scale):
                    continue
                b = _rebase(b, a.origin)
                if float(np.dot(a.end, b.start)) > 1 - 1e-9 and min(a.z1, b.z1) - max(a.z0, b.z0) > 1e-6 * scale:
                    arcs[i] = Arc(a.ordinals + b.ordinals, a.radius, a.origin, a.axis, a.start, b.end, a.angle + b.angle,
                                  min(a.z0, b.z0), max(a.z1, b.z1))
                    del arcs[j]
                    merged = True
                    break
            if merged:
                break
    return arcs


def _edges_faces(shape):
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

    found = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, found)
    return found


def _neighbours(arc: Arc, at, faces, edges_faces) -> set[int]:
    """The faces across ``arc``'s straight edges at radial direction ``at``: what the bend joins on that side."""
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    found: set[int] = set()
    for ordinal in arc.ordinals:
        face = faces.FindKey(ordinal)
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge_s(explorer.Current())
            explorer.Next()
            curve = BRepAdaptor_Curve(edge)
            if curve.GetType() != GeomAbs_Line:
                continue
            if np.linalg.norm(np.cross(_vec(curve.Line().Direction()), arc.axis)) > 1e-6:
                continue
            middle = _vec(curve.Value(0.5 * (curve.FirstParameter() + curve.LastParameter())))
            offset = middle - arc.origin
            radial = offset - np.dot(offset, arc.axis) * arc.axis
            if float(np.dot(radial / max(np.linalg.norm(radial), 1e-12), at)) < 1 - 1e-6:
                continue
            for other in edges_faces.FindFromKey(edge):
                index = faces.FindIndex(other)
                if index not in arc.ordinals:
                    found.add(index)
    return found


def _plane_offset(face, direction) -> float | None:
    """A planar face's plane as its offset along ``direction`` (its normal must be along it), else ``None``."""
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane

    surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane:
        return None
    plane = surface.Plane()
    normal = _vec(plane.Axis().Direction())
    if np.linalg.norm(np.cross(normal, direction)) > 1e-6:
        return None
    return float(np.dot(_vec(plane.Location()), direction))


class _Classes:
    """Union-find over face ordinals: the faces each flat is made of."""

    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, items) -> int | None:
        items = list(items)
        if not items:
            return None
        root = self.find(items[0])
        for item in items[1:]:
            other = self.find(item)
            if other != root:
                self.parent[other] = root
        return self.find(root)


def read_sheet(shape, *, part: str, volume_mm3: float, area_mm2: float, fixed_ordinal: int | None = None,
               fixed_ref: str = "") -> Sheet:
    """The part as a bent sheet: its bends, its flats, its thickness and its tree from the held flat (``fixed_ordinal``'s
    flat, else the largest). A ValueError in a sentence when it is not a bent sheet of one thickness."""
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    from cadgen._internal.entity_ordinals import entity_map
    from cadgen._internal.fea.assembly import gprops
    from cadgen._internal.fea.defeature import as_face

    faces = entity_map(shape, "face")
    scale = max(math.sqrt(max(area_mm2, 1e-12)), 1e-6)
    arcs = []
    for ordinal in range(1, faces.Extent() + 1):
        face = as_face(faces.FindKey(ordinal))
        if BRepAdaptor_Surface(face).GetType() == GeomAbs_Cylinder:
            arc = _cylinder_arc(face, ordinal)
            if arc is not None:
                arcs.append(arc)
    arcs = _merge(arcs, scale)

    # Pair each arc with the next larger coaxial one over the same arc and the same stretch of axis.
    pairs, used = [], set()
    for inner in sorted(arcs, key=lambda a: a.radius):
        if id(inner) in used:
            continue
        for outer in sorted(arcs, key=lambda a: a.radius):
            if outer is inner or id(outer) in used or outer.radius <= inner.radius + 1e-9 or not _same_line(inner, outer, scale):
                continue
            rebased = _rebase(outer, inner.origin)
            same_arc = float(np.dot(inner.start, rebased.start)) > 1 - 1e-6 and float(np.dot(inner.end, rebased.end)) > 1 - 1e-6
            overlap = min(inner.z1, rebased.z1) - max(inner.z0, rebased.z0)
            if same_arc and overlap > 0.5 * (inner.z1 - inner.z0):
                pairs.append((inner, rebased))
                used.update((id(inner), id(outer)))
                break
    if not pairs:
        raise ValueError(
            f"sheet_metal: {part} has no bends: a bent sheet's bends are an inside and an outside cylinder of one axis, "
            "one thickness apart, and this part has none, so it is not a bent sheet and this analysis does not apply")
    thicknesses = sorted(outer.radius - inner.radius for inner, outer in pairs)
    thickness = thicknesses[len(thicknesses) // 2]
    if thicknesses[-1] - thicknesses[0] > _SAME_THICKNESS * thickness:
        listed = ", ".join(f"{t:.3g}" for t in sorted(set(round(t, 4) for t in thicknesses)))
        raise ValueError(
            f"sheet_metal: {part} is not of constant thickness: its bends are {listed} mm thick, so it is not one "
            "sheet bent to shape and this analysis does not apply")
    if volume_mm3 > _SHEET_VOLUME * area_mm2 * thickness / 2.0:
        raise ValueError(
            f"sheet_metal: {part} is not of constant thickness: its {volume_mm3:.4g} mm³ is far more than a "
            f"{thickness:.3g} mm sheet over its {area_mm2:.4g} mm² of surface holds, so most of it is thicker than its bends; "
            "this analysis takes a sheet bent to shape")

    edges_faces = _edges_faces(shape)
    bends = [Bend(inner, outer, outer.radius - inner.radius) for inner, outer in pairs]
    bend_of_face = {o: b for b, bend in enumerate(bends) for o in bend.ordinals}
    classes = _Classes()
    for b, bend in enumerate(bends):
        for side, at in enumerate((bend.inner.start, bend.inner.end)):
            inside = _neighbours(bend.inner, at, faces, edges_faces)
            outside = _neighbours(bend.outer, at, faces, edges_faces)
            # The two faces of the flat it joins: planes along the radial direction, a thickness apart.
            planes_in = [o for o in inside if _plane_offset(as_face(faces.FindKey(o)), at) is not None]
            planes_out = [o for o in outside if _plane_offset(as_face(faces.FindKey(o)), at) is not None]
            for a in planes_in:
                for o in planes_out:
                    gap = abs(_plane_offset(as_face(faces.FindKey(o)), at) - _plane_offset(as_face(faces.FindKey(a)), at))
                    if abs(gap - bend.thickness) > _SAME_THICKNESS * bend.thickness:
                        raise ValueError(
                            f"sheet_metal: {part} is not of constant thickness: the flat beside its bend at "
                            f"{_xyz(bend.middle())} mm is {gap:.3g} mm thick and the bend {bend.thickness:.3g} mm, so it is "
                            "not one sheet bent to shape and this analysis does not apply")
            if planes_in or planes_out:
                bend.sides.append(classes.union(planes_in + planes_out))
                continue
            # No flat on this side: a bend straight into the next (the two share a flat of no length), or a bend
            # that ends at a cut (a flat of its own, of no length).
            other = sorted({bend_of_face[o] for o in inside | outside if o in bend_of_face and bend_of_face[o] != b})
            key = -(1 + min(b, other[0]) * len(bends) + max(b, other[0])) if other else -(10 ** 6 + 2 * b + side)
            bend.sides.append(classes.union([key]))

    # The flats: one per class of faces, its area the larger of its two sides (the faces facing one way).
    roots = sorted({classes.find(key) for bend in bends for key in bend.sides})
    members: dict[int, list[int]] = {root: [] for root in roots}
    for ordinal in list(classes.parent):
        root = classes.find(ordinal)
        if root in members and ordinal > 0:
            members[root].append(ordinal)
    bend_faces = {o for bend in bends for o in bend.ordinals}
    flats = []
    for root in roots:
        ordinals = tuple(sorted(o for o in members[root] if o not in bend_faces))
        area, centre = 0.0, np.zeros(3)
        for o in ordinals:
            props = gprops(faces.FindKey(o))
            centre += float(props.Mass()) * _vec(props.CentreOfMass())
            area += float(props.Mass())
        flats.append(Flat(0, ordinals, area / 2.0, centre / area if area > 0 else None))
    index_of = {root: i for i, root in enumerate(roots)}
    for bend in bends:
        bend.sides = [index_of[classes.find(key)] for key in bend.sides]

    if fixed_ordinal is not None:
        holding = [i for i, flat in enumerate(flats) if fixed_ordinal in flat.ordinals]
        if not holding:
            what = ("a bend's face" if fixed_ordinal in bend_faces else
                    "not a face of a flat (an edge of the sheet, or a face no bend reaches)")
            largest = max(range(len(flats)), key=lambda i: flats[i].area)
            raise ValueError(f"fixed_face: {fixed_ref} is {what}; name a face of the flat to hold, like "
                             f"#{part.lstrip('#')}.f{flats[largest].ordinals[0]} (the largest flat's)")
        fixed = holding[0]
    else:
        fixed = max(range(len(flats)), key=lambda i: (flats[i].area, -i))

    # The tree: breadth first from the held flat; a bend reached from both sides closes a loop.
    tree, seen, queue = [], {fixed}, [fixed]
    order_flats = [fixed]
    reached: set[int] = set()
    for flat in queue:
        for b, bend in enumerate(bends):
            if b in reached or flat not in bend.sides:
                continue
            side = bend.sides.index(flat)
            child = bend.sides[1 - side]
            reached.add(b)
            if child in seen:
                bend.parent_side = None
                continue
            bend.parent_side = side
            tree.append((b, flat, child))
            seen.add(child)
            queue.append(child)
            order_flats.append(child)
    order_flats += [i for i in range(len(flats)) if i not in seen]
    for number, i in enumerate(order_flats, 1):
        flats[i].number = number
    numbered = [b for b, _, _ in tree] + [b for b in range(len(bends)) if b not in {t[0] for t in tree}]
    for number, b in enumerate(numbered, 1):
        bends[b].number = number
    return Sheet(thickness, bends, flats, fixed, tree)


def _xyz(point) -> list[float]:
    return [round(float(c), 3) for c in point]


def _frame(bend: Bend, parent_side: int):
    """The bend seen from its parent's side: (origin, axis, u, v) with u the parent's radial direction and v the way
    the arc turns from it."""
    import numpy as np

    arc = bend.inner
    if parent_side == 0:
        axis, u = arc.axis, arc.start
    else:
        axis, u = -arc.axis, arc.end
    return arc.origin, axis, u, np.cross(axis, u)


def node_regions(sheet: Sheet, nodes, tets, boundary, boundary_ordinal):
    """Where each node is: (bend index or -1, flat index or -1, the share of its bend's arc from the bend's start side).

    A node is in a bend when its radius about the bend's axis is between the inside and the outside, its angle within
    the arc and its place along the axis within the bend's length. The rest are split into connected pieces along the
    tets' edges, and each piece is the flat whose faces most of its surface nodes lie on."""
    import numpy as np
    import scipy.sparse as sparse
    from scipy.sparse.csgraph import connected_components

    count = len(nodes)
    bend_of = np.full(count, -1, dtype=np.int64)
    share = np.zeros(count)
    tol = 1e-3 * sheet.thickness + 1e-9
    for b, bend in enumerate(sheet.bends):
        arc = bend.inner
        origin, axis, u, v = arc.origin, arc.axis, arc.start, np.cross(arc.axis, arc.start)
        rel = nodes - origin
        z = rel @ axis
        radial = rel - np.outer(z, axis)
        r = np.linalg.norm(radial, axis=1)
        phi = np.arctan2(radial @ v, radial @ u)
        slack = tol / max(arc.radius, tol)
        phi = np.where(phi < -slack, phi + 2.0 * math.pi, phi)
        inside = ((bend_of < 0) & (r >= arc.radius - tol) & (r <= bend.outer.radius + tol) & (phi <= arc.angle + slack)
                  & (z >= arc.z0 - tol) & (z <= arc.z1 + tol))
        bend_of[inside] = b
        share[inside] = np.clip(phi[inside] / arc.angle, 0.0, 1.0)

    flat_of = np.full(count, -1, dtype=np.int64)
    rest = bend_of < 0
    corners = np.asarray(tets)[:, :4].astype(np.int64)
    pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
    rows = np.concatenate([corners[:, a] for a, _ in pairs])
    cols = np.concatenate([corners[:, b] for _, b in pairs])
    keep = rest[rows] & rest[cols]
    graph = sparse.coo_matrix((np.ones(int(keep.sum())), (rows[keep], cols[keep])), shape=(count, count))
    _, piece = connected_components(graph, directed=False)
    face_flat = {o: i for i, flat in enumerate(sheet.flats) for o in flat.ordinals}
    votes: dict[tuple[int, int], int] = {}
    triangles = np.asarray(boundary)[:, :3].astype(np.int64)
    for triangle, ordinal in zip(triangles, np.asarray(boundary_ordinal)):
        flat = face_flat.get(int(ordinal))
        if flat is None:
            continue
        for node in triangle:
            if rest[node]:
                key = (int(piece[node]), flat)
                votes[key] = votes.get(key, 0) + 1
    best: dict[int, tuple[int, int]] = {}
    for (p, flat), n in votes.items():
        if p not in best or n > best[p][1]:
            best[p] = (flat, n)
    for p, (flat, _) in best.items():
        flat_of[rest & (piece == p)] = flat
    return bend_of, flat_of, share


def _child_transform(bend: Bend, parent_side: int, kept: float):
    """The rigid motion of the flat past ``bend`` when it springs back to ``kept`` of its angle, its parent held:
    (R, d) with x' = R x + d. The bend's mid-thickness keeps its length; the parent's tangent line stays put."""
    import numpy as np

    origin, axis, u, v = _frame(bend, parent_side)
    theta = bend.inner.angle
    rho = bend.inner.radius + bend.thickness / 2.0
    theta_f, rho_f = theta * kept, rho / kept

    def frame(angle):
        return (math.cos(angle) * u + math.sin(angle) * v, -math.sin(angle) * u + math.cos(angle) * v)

    uc, tc = frame(theta)
    ucf, tcf = frame(theta_f)
    before = np.column_stack([uc, tc, axis])
    after = np.column_stack([ucf, tcf, axis])
    R = after @ before.T
    q = origin + rho * uc
    centre_f = origin + (rho - rho_f) * u
    qf = centre_f + rho_f * ucf
    return R, qf - R @ q


def _bend_points(bend: Bend, parent_side: int, kept: float, points):
    """The bend's own points as it springs back, its parent held: each keeps its share of the arc and its offset from
    the mid-thickness, on the arc of the new radius."""
    import numpy as np

    origin, axis, u, v = _frame(bend, parent_side)
    theta = bend.inner.angle
    rho = bend.inner.radius + bend.thickness / 2.0
    theta_f, rho_f = theta * kept, rho / kept
    rel = points - origin
    z = rel @ axis
    radial = rel - np.outer(z, axis)
    r = np.linalg.norm(radial, axis=1)
    phi = np.arctan2(radial @ v, radial @ u)
    phi = np.where(phi < -0.5, phi + 2.0 * math.pi, phi)
    s = np.clip(phi / theta, 0.0, 1.0)
    angle = s * theta_f
    radius = rho_f + (r - rho)
    centre_f = origin + (rho - rho_f) * u
    return (centre_f + radius[:, None] * (np.outer(np.cos(angle), u) + np.outer(np.sin(angle), v))
            + np.outer(z, axis))


def spring_back(sheet: Sheet, kept: list[float], nodes, bend_of, flat_of):
    """The displacement of every node off the brake (mm, (M, 3)), the held flat still, and each flat's turn from its
    CAD angle (degrees). ``kept`` is each bend's share of its angle kept after release."""
    import numpy as np

    motion = {sheet.fixed: (np.eye(3), np.zeros(3))}
    for b, parent, child in sheet.tree:
        bend = sheet.bends[b]
        Rp, dp = motion[parent]
        Rc, dc = _child_transform(bend, bend.parent_side, kept[b])
        motion[child] = (Rp @ Rc, Rp @ dc + dp)
    moved = np.array(nodes, dtype=float, copy=True)
    for flat, (R, d) in motion.items():
        rows = flat_of == flat
        moved[rows] = nodes[rows] @ R.T + d
    for b, bend in enumerate(sheet.bends):
        rows = bend_of == b
        if not rows.any():
            continue
        side = bend.parent_side if bend.parent_side is not None else 0
        parent = bend.sides[side]
        R, d = motion.get(parent, (np.eye(3), np.zeros(3)))
        moved[rows] = _bend_points(bend, side, kept[b], nodes[rows]) @ R.T + d
    turned = []
    for i in range(len(sheet.flats)):
        R, _ = motion.get(i, (np.eye(3), np.zeros(3)))
        turned.append(math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(R)) - 1.0) / 2.0)))))
    return moved - nodes, turned


def missing_reliefs(shape, sheet: Sheet) -> list[tuple[int, list[float], int]]:
    """The bend ends with sheet beside them on a flat they join: (bend index, the point probed (mm), the flat index).

    A bend that ends inside a flat tears or bulges there unless a relief is cut. Just past each end of a bend, a quarter
    thickness along its axis and a quarter thickness into each flat it joins, at mid-thickness, is in the sheet when
    nothing was cut: that end needs a relief."""
    import numpy as np
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    found = []
    quarter = 0.25 * sheet.thickness
    for b, bend in enumerate(sheet.bends):
        arc = bend.inner
        rho = arc.radius + bend.thickness / 2.0
        for side, (radial, away) in enumerate(((arc.start, -np.cross(arc.axis, arc.start)),
                                               (arc.end, np.cross(arc.axis, arc.end)))):
            for z in (arc.z0 - quarter, arc.z1 + quarter):
                point = arc.origin + rho * radial + z * arc.axis + quarter * away
                classifier = BRepClass3d_SolidClassifier(shape, gp_Pnt(*map(float, point)), 1e-6)
                if classifier.State() == TopAbs_IN:
                    found.append((b, _xyz(point), bend.sides[side]))
    return found
