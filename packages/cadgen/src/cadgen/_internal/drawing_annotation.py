"""What a view says about the part: its dimensions and callouts resolved against
the geometry and planned round the view, and its hole table.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, NamedTuple

from cadgen._internal.drawing_assembly import _BALLOON_AIR, _BALLOON_LEAD, _BALLOON_R, _balloon_axis
from cadgen._internal.drawing_base import (
    _CALLOUT_CLEAR, _CALLOUT_GAP, _CALLOUT_LANDING, _DIM_ROW, _FLAG_SIDE, _LABEL_ROOM, _OPPOSITE, _SECTION_LETTERS,
    _SAME_PLACE, _SIDES,
    _dot, _exact, _fmt, _ink_width, _look, _looks_down, _near, _places, _shown, _spans, _text_width, _where,
)
from cadgen._internal.drawing_features import Slot
from cadgen._internal.drawing_gdt import _DATUM_REACH, _datum_toward, _side_of, frame_size, mark_width
from cadgen._internal.drawing_sheet import _CAPTION_HEIGHT

if TYPE_CHECKING:
    from cadgen.eng_drawing import Sheet, View


@dataclass
class _Dim:
    kind: str
    p1: tuple[float, float, float]
    p2: tuple[float, float, float] | None
    #: Sheet millimetres from the dimensioned points, or None for the next free row.
    offset: float | None
    text: str | None
    orientation: str | None
    radius: float = 0.0
    angle: float = 45.0
    tol: Any = None
    fit: str | None = None
    hole: dict | None = None
    #: The parts-list item a flag note points at, where it names one.
    item: Any = None
    #: Filled in at render time, on a copy: the hole a callout states, the side and
    #: row an unplaced dimension was given, and the call's index for messages.
    feature: Any = None
    side: str | None = None
    row: int = 0
    index: int = 0
    #: The holes or slots a callout states, each one: its ``4×`` covers four.
    covers: tuple = ()
    #: A basic dimension (exact, boxed: a GD&T frame bounds it) or a reference one
    #: (information only, in parentheses); and limits, the two the part lies between.
    basic: bool = False
    reference: bool = False
    limits: tuple[float, float] | None = None
    #: A feature control frame the callout or dimension carries, and the datum
    #: letter its feature is (a datum feature of size: a bore, a width).
    frame: Any = None
    datum: str | None = None
    #: A key characteristic: marked with the profile's boxed letters after the value.
    key: bool = False


def _tol_suffix(tol) -> str:
    if not tol:
        return ""
    plus, minus = tol
    if abs(plus - minus) < 1e-9:
        return f" ±{_exact(plus)}"
    places = _places(plus, minus)  # plus and minus to one precision, as given
    return f" +{plus:.{places}f}/-{minus:.{places}f}"


def hole_callout_text(spec: dict, *, tol=None, fit: str | None = None) -> str:
    """The text of a hole callout, in the ISO/ASME symbols a shop reads."""
    parts = []
    # One hole is not "1×": a count prints only when there is something to count.
    lead = f"{spec['count']}× " if (spec.get("count") or 1) > 1 else ""
    if spec.get("slot"):
        text = f"{lead}{_fmt(spec['width'])} × {_fmt(spec['length'])} SLOT"
        text += " THRU" if spec.get("thru") else (f" \u21a7{_fmt(spec['depth'])}" if spec.get("depth") else "")
        if spec.get("cbore"):
            width, length, depth = spec["cbore"]
            text += f"   \u2334 {_fmt(width)} × {_fmt(length)} \u21a7{_fmt(depth)}"
        return text + (f"   {spec['label']}" if spec.get("label") else "")
    size = spec["thread"] if spec.get("thread") else f"%%c{_fmt(spec['diameter'])}"
    size += _tol_suffix(tol) + (f" {fit}" if fit else "")
    if spec.get("thru"):
        size += " THRU"
    elif spec.get("depth") is not None:
        size += f" \u21a7{_fmt(spec['depth'])}"
    if spec.get("pcd"):
        # The bolt circle: equally spaced on a circle of this diameter.
        size += f" EQ SP ON %%c{_fmt(spec['pcd'])}"
    parts.append(lead + size)

    def same(a, b) -> bool:
        return a is not None and b is not None and all(abs(x - y) < 1e-3 for x, y in zip(a, b))

    def cbore(pair) -> str:
        return f"\u2334 %%c{_fmt(pair[0])} \u21a7{_fmt(pair[1])}"

    def csk(pair) -> str:
        return f"\u2335 %%c{_fmt(pair[0])} × {_fmt(pair[1])}°"

    # A through hole can be opened out at both ends: the same at each is stated
    # once, BOTH ENDS; something different at the far end is stated FAR SIDE.
    for near, far, text in ((spec.get("cbore"), spec.get("far_cbore"), cbore),
                            (spec.get("csk"), spec.get("far_csk"), csk)):
        if near:
            parts.append(text(near) + (" BOTH ENDS" if same(near, far) else ""))
    for near, far, text in ((spec.get("cbore"), spec.get("far_cbore"), cbore),
                            (spec.get("csk"), spec.get("far_csk"), csk)):
        if far and not same(near, far):
            parts.append("FAR SIDE " + text(far))
    if spec.get("label"):
        parts.append(str(spec["label"]))
    return "   ".join(parts)


def _shows(view: View, proj, feature, run: float, cut) -> bool:
    """Whether a view draws a hole or slot that runs ``run`` from its mouth: not one
    wholly in the half a section takes away, outside a detail's circle, or inside
    the stretch a broken view leaves out."""
    if view._detail is not None:
        if math.dist(proj.point(feature.mouth), proj.point(view._detail.centre)) > view._detail.radius + 1e-6:
            return False
    if view._break is not None and view._break.low < feature.mouth[view._break.axis] < view._break.high:
        return False
    if cut is None:
        return True
    look = _look(view)
    far = tuple(m + a * run for m, a in zip(feature.mouth, feature.axis))
    return min(_dot(tuple(e - c for e, c in zip(end, cut[2])), look) for end in (feature.mouth, far)) <= 1e-6


def _faces_viewer(feature, look) -> bool:
    """Whether a view sees a hole's or a slot's mouth: its axis runs into the
    material away from the viewer, or it is plain and through, which reads the
    same from either end. A counterbore or countersink on the far side is not
    something this view shows."""
    if _dot(feature.axis, look) < 0:
        return True
    sunk = feature.cbore if isinstance(feature, Slot) else feature.cbore or feature.csk
    return feature.thru and not sunk


def _looks_into(feature, look) -> bool:
    """Whether a view looks down a hole or slot from the side it opens on."""
    return _looks_down(feature.axis, look) and _faces_viewer(feature, look)


def _kinds(features) -> list[list]:
    """Holes and slots grouped by kind, in the order a drawing lists them: holes,
    largest first, then slots."""
    groups: dict[tuple, list] = {}
    for feature in features:
        groups.setdefault((isinstance(feature, Slot), feature.signature()), []).append(feature)
    return sorted(groups.values(), key=lambda g: (isinstance(g[0], Slot),
                                                  0.0 if isinstance(g[0], Slot) else -g[0].diameter,
                                                  g[0].signature()))


@dataclass
class _Features:
    """What a drawing reads off one part, once however many views show it."""

    holes: list
    slots: list
    circles: list

    def pcd(self, members) -> float | None:
        """The bolt circle's diameter when these holes are exactly one bolt circle."""
        mouths = {tuple(round(c, 6) for c in h.mouth) for h in members}
        for circle in self.circles:
            if {tuple(round(c, 6) for c in m) for m in circle.mouths} == mouths:
                return circle.diameter
        return None


def _hole_spec(hole, count: int, thread: str | None = None, label: str | None = None,
               pcd: float | None = None) -> dict:
    return {"diameter": hole.diameter, "depth": hole.depth, "thru": hole.thru, "cbore": hole.cbore,
            "csk": hole.csk, "far_cbore": hole.far_cbore, "far_csk": hole.far_csk, "count": count,
            "thread": thread, "label": label, "pcd": pcd}


def _slot_spec(slot, count: int, label: str | None = None) -> dict:
    return {"slot": True, "width": slot.width, "length": slot.length, "thru": slot.thru, "depth": slot.depth,
            "cbore": slot.cbore, "count": count, "label": label}


def _outer_radius(spec: dict) -> float:
    """Where a callout's leader ends: on the outermost circle the hole shows, so the
    arrow does not cross a counterbore to reach the bore inside it; on a slot,
    the arc of its end."""
    if spec.get("slot"):
        return (spec.get("cbore") or (spec["width"],))[0] / 2
    return max(spec["diameter"], (spec.get("cbore") or (0.0,))[0], (spec.get("csk") or (0.0,))[0]) / 2


def _radii_at(proj, target, *, closed_only: bool) -> list[float]:
    """The radii of the circles (and, unless ``closed_only``, arcs) a view draws
    centred on ``target``, in model millimetres. The hidden-line pass draws a
    turned groove's outline as a spline on one side and a circle on the other
    (where the torus's seam lies); a spline every point of which lies one
    distance from ``target`` is that arc."""
    from build123d import GeomType

    from cadgen._internal.drawing_views import _edge_polyline

    radii: set[float] = set()
    for edge in list(proj.visible) + list(proj.hidden):
        if edge.geom_type == GeomType.CIRCLE and not (closed_only and not edge.is_closed):
            if _near((edge.arc_center.X, edge.arc_center.Y), target):
                radii.add(round(edge.radius, 4))
        elif edge.geom_type == GeomType.BSPLINE and not closed_only:
            reach = [math.hypot(x - target[0], y - target[1]) for x, y in _edge_polyline(edge, 9)]
            if min(reach) > _SAME_PLACE and max(reach) - min(reach) <= _SAME_PLACE:
                radii.add(round(sum(reach) / len(reach), 4))
    return sorted(radii)


def _callout_value(dim: "_Dim") -> str:
    if dim.kind in ("hole", "slot"):
        return hole_callout_text(dim.hole, tol=dim.tol, fit=dim.fit)
    if dim.text:
        value = dim.text
    else:
        value = f"%%c{_fmt(2 * dim.radius)}" if dim.kind == "diameter" else f"R{_fmt(dim.radius)}"
    return f"({value})" if dim.reference else value


def _far_side(call: str, what: str, view) -> ValueError:
    """The refusal for a feature that opens away from the viewer, naming the view
    that looks into it where there is one by name."""
    there = (f"the {_OPPOSITE[view.name]} view, which looks into it" if view.name in _OPPOSITE
             else "a view that looks into it")
    return ValueError(f"{call}: that {what} opens on the far side of the part. Call it out in {there}.")


def _holes_hint(seen, look) -> str:
    mine = [h for h in seen if _faces_viewer(h, look)]
    if not mine:
        return ("This view looks down no hole; a hole is called out in the view that sees it as a circle "
                "and looks into its mouth.")
    listed = ", ".join(f"⌀{_fmt(h.diameter)} at {_where(h.mouth)}" for h in mine[:6])
    return f"The holes it looks down open at {listed}{' ...' if len(mine) > 6 else ''}; view.holes() calls out every one."


def _resolve_view(view: View, proj, bounds, part_features, warnings: list | None, cut=None) -> list["_Dim"]:
    """The view's annotation with every size the part decides filled in from the
    part, on copies: a hole callout's diameter, depth, counterbore, countersink and
    count, a diameter or radius callout's value, and ``holes()`` expanded into one
    callout per kind of hole, less the kinds a ``hole()`` or ``slot()`` on the view
    states. Anything the author typed is checked on the way."""
    look = _look(view)
    seen_cache: tuple | None = None

    def kept(feature, run: float) -> bool:
        return _shows(view, proj, feature, run, cut)

    def seen() -> tuple:
        nonlocal seen_cache
        if seen_cache is None:
            features = part_features(view.shape)
            seen_cache = (
                [h for h in features.holes if _looks_down(h.axis, look) and kept(h, h.length)],
                [sl for sl in features.slots if _looks_down(sl.axis, look) and kept(sl, sl.run)],
                features,
            )
        return seen_cache

    resolved: dict[int, list[_Dim]] = {}
    for index, dim in enumerate(view._dims):
        if dim.kind == "hole":
            holes, slots, features = seen()
            resolved[index] = [_resolve_hole(view, proj, dim, holes, look, features, slots)]
        elif dim.kind == "slot":
            _holes, slots, _features = seen()
            resolved[index] = [_resolve_slot(view, proj, bounds, dim, slots, look)]
        elif dim.kind in ("diameter", "radius"):
            resolved[index] = [_resolve_round(view, proj, dim)]
        elif dim.kind != "holes":
            resolved[index] = [replace(dim)]
    # A kind of hole a hole() call states is that call's, with its fit or frame;
    # holes() calls out the rest.
    stated = {id(f) for items in resolved.values() for item in items for f in (item.covers or (item.feature,))}
    for index, dim in enumerate(view._dims):
        if dim.kind == "holes":
            holes, slots, features = seen()
            resolved[index] = _expand_holes(view, proj, bounds, dim, holes, look, warnings, features, slots, stated)
    out: list[_Dim] = []
    for index in sorted(resolved):
        for item in resolved[index]:
            item.index = index
        out.extend(resolved[index])
    return out


def _resolve_hole(view: View, proj, dim: "_Dim", seen, look, features: _Features, slots) -> "_Dim":
    given, thread, label = dim.hole["given"], dim.hole["thread"], dim.hole["label"]
    call = f"{view.name}.hole({_where(dim.p1)})"
    target = proj.point(dim.p1)
    here = [h for h in seen if _near(proj.point(h.mouth), target)]
    if not here:
        if given["diameter"] is None and any(_near(proj.point(p), target) for sl in slots
                                             for p in (sl.mouth, *sl.ends)):
            raise ValueError(f"{call}: that is a slot, not a hole; call it out with "
                             f"{view.name}.slot({_where(dim.p1)}).")
        if given["diameter"] is None:
            raise ValueError(f"{call}: no hole runs along the {view.name} view's line of sight there. "
                             + _holes_hint(seen, look))
        # A bore the reader does not recognise as a hole can still be stated, but
        # only over a circle that is really there.
        radii = _radii_at(proj, target, closed_only=True)
        if not any(abs(2 * r - given["diameter"]) <= 0.01 for r in radii):
            shown = ", ".join("⌀" + _fmt(2 * r) for r in radii)
            raise ValueError(f"{call}: the {view.name} view shows no ⌀{_fmt(given['diameter'])} circle there"
                             f"{f' (it shows {shown})' if radii else ''}, so the callout would point at a hole "
                             "the part does not have.")
        spec = {"diameter": given["diameter"], "depth": given["depth"], "thru": bool(given["thru"]),
                "cbore": given["cbore"], "csk": given["csk"], "count": given["count"], "thread": thread,
                "label": label}
        return replace(dim, hole=spec, radius=_outer_radius(spec))
    # Two holes on one line (a clevis) both match; the one whose mouth this view
    # looks into, nearest the viewer, is the one it calls out.
    here.sort(key=lambda h: (not _faces_viewer(h, look), -_dot(h.mouth, look)))
    hole = here[0]
    if not _faces_viewer(hole, look):
        raise _far_side(call, "hole", view)
    same = [h for h in seen if h.signature() == hole.signature() and _faces_viewer(h, look)]
    problems = []
    if given["diameter"] is not None and thread is None and abs(given["diameter"] - hole.diameter) > 0.01:
        problems.append(f"diameter={_fmt(given['diameter'])}")
    if given["thru"] is not None and given["thru"] != hole.thru:
        problems.append(f"thru={given['thru']}")
    if given["depth"] is not None and (hole.thru or abs(given["depth"] - hole.depth) > 0.01):
        problems.append(f"depth={_fmt(given['depth'])}")
    if given["cbore"] is not None and (hole.cbore is None or any(
            abs(a - b) > 0.01 for a, b in zip(given["cbore"], hole.cbore))):
        problems.append(f"cbore=({_fmt(given['cbore'][0])}, {_fmt(given['cbore'][1])})")
    if given["csk"] is not None and (hole.csk is None or abs(given["csk"][0] - hole.csk[0]) > 0.01
                                     or abs(given["csk"][1] - hole.csk[1]) > 0.5):
        problems.append(f"csk=({_fmt(given['csk'][0])}, {_fmt(given['csk'][1])})")
    if given["count"] is not None and given["count"] != len(same):
        problems.append(f"count={given['count']}")
    if problems:
        raise ValueError(
            f"{call}: the part's hole reads {_shown(hole_callout_text(_hole_spec(hole, len(same))))}, but the "
            f"callout was given {', '.join(problems)}. Leave {'it' if len(problems) == 1 else 'them'} unset so "
            "the drawing states the part, or change the model."
        )
    spec = _hole_spec(hole, len(same), thread, label, features.pcd(same))
    return replace(dim, hole=spec, radius=_outer_radius(spec), feature=hole, covers=tuple(same))


def _slot_end(proj, bounds, slot) -> tuple:
    """The end of a slot a callout's leader goes to: the one nearer the view's
    left or right edge, the short way out."""
    x0, x1 = bounds[0], bounds[1]
    return min(slot.ends, key=lambda e: (round(min(proj.point(e)[0] - x0, x1 - proj.point(e)[0]), 6),
                                         -round(proj.point(e)[1], 6)))


def _resolve_slot(view: View, proj, bounds, dim: "_Dim", seen, look) -> "_Dim":
    given, label = dim.hole["given"], dim.hole["label"]
    call = f"{view.name}.slot({_where(dim.p1)})"
    target = proj.point(dim.p1)
    here = [sl for sl in seen if any(_near(proj.point(p), target) for p in (sl.mouth, *sl.ends))]
    if not here:
        mine = [sl for sl in seen if _faces_viewer(sl, look)]
        hint = (f"The slots it looks down are centred at {', '.join(_where(sl.mouth) for sl in mine[:6])}."
                if mine else "This view looks down no slot.")
        raise ValueError(f"{call}: no slot runs along the {view.name} view's line of sight there. {hint}")
    slot = here[0]
    if not _faces_viewer(slot, look):
        raise _far_side(call, "slot", view)
    same = [sl for sl in seen if sl.signature() == slot.signature() and _faces_viewer(sl, look)]
    problems = []
    for name, value in (("width", slot.width), ("length", slot.length)):
        if given[name] is not None and abs(given[name] - value) > 0.01:
            problems.append(f"{name}={_fmt(given[name])}")
    if given["thru"] is not None and given["thru"] != slot.thru:
        problems.append(f"thru={given['thru']}")
    if given["depth"] is not None and (slot.thru or abs(given["depth"] - slot.depth) > 0.01):
        problems.append(f"depth={_fmt(given['depth'])}")
    if given["count"] is not None and given["count"] != len(same):
        problems.append(f"count={given['count']}")
    if problems:
        raise ValueError(
            f"{call}: the part's slot reads {_shown(hole_callout_text(_slot_spec(slot, len(same))))}, but the "
            f"callout was given {', '.join(problems)}. Leave {'it' if len(problems) == 1 else 'them'} unset so "
            "the drawing states the part, or change the model."
        )
    spec = _slot_spec(slot, len(same), label)
    end = _slot_end(proj, bounds, slot)
    return replace(dim, p1=end, hole=spec, radius=_outer_radius(spec), feature=slot, covers=tuple(same))


def _expand_holes(view: View, proj, bounds, dim: "_Dim", seen, look, warnings: list | None,
                  features: _Features, slots, stated: set) -> list["_Dim"]:
    kinds = _kinds(f for f in (*seen, *slots) if _faces_viewer(f, look))
    if not kinds:
        if warnings is not None:
            warnings.append(f"{view.name}.holes(): the {view.name} view looks down no hole or slot, so it calls "
                            "nothing out.")
        return []
    x0, x1 = bounds[0], bounds[1]

    def short_way_out(point) -> tuple:
        p = proj.point(point)
        return (round(min(p[0] - x0, x1 - p[0]), 6), -round(p[1], 6))

    out = []
    for members in kinds:
        if any(id(member) in stated for member in members):
            continue
        if isinstance(members[0], Slot):
            slot = min(members, key=lambda sl: short_way_out(_slot_end(proj, bounds, sl)))
            spec = _slot_spec(slot, len(members))
            out.append(replace(dim, kind="slot", p1=_slot_end(proj, bounds, slot), hole=spec,
                                           radius=_outer_radius(spec), feature=slot, covers=tuple(members)))
        else:
            hole = min(members, key=lambda h: short_way_out(h.mouth))
            spec = _hole_spec(hole, len(members), pcd=features.pcd(members))
            out.append(replace(dim, kind="hole", p1=hole.mouth, hole=spec, radius=_outer_radius(spec),
                                           feature=hole, covers=tuple(members)))
    return out


def _resolve_round(view: View, proj, dim: "_Dim") -> "_Dim":
    closed = dim.kind == "diameter"
    what = "circle" if closed else "arc"
    target = proj.point(dim.p1)
    radii = _radii_at(proj, target, closed_only=closed)
    stated = "" if not dim.radius else f", size={_fmt(2 * dim.radius if closed else dim.radius)}"
    call = f"{view.name}.{dim.kind}({_where(dim.p1)}{stated})"
    shown = ", ".join(("⌀" + _fmt(2 * r)) if closed else ("R" + _fmt(r)) for r in radii)
    if dim.radius:
        if not any(abs(r - dim.radius) <= 0.01 for r in radii):
            raise ValueError(f"{call}: no {what} of that size is centred there in the {view.name} view"
                             f"{f'; it shows {shown}' if radii else ''}.")
        radius = dim.radius
    elif len(radii) == 1:
        radius = radii[0]
    elif not radii:
        raise ValueError(f"{call}: no {what} is centred there in the {view.name} view. A {dim.kind} is "
                         f"stated where the feature is seen as {'a circle' if closed else 'an arc'}, at its centre.")
    else:
        raise ValueError(f"{call}: {len(radii)} {what}s share that centre ({shown}); pass size= to say "
                         "which one this states.")
    return replace(dim, radius=radius)


def _rows_beyond(dim: "_Dim", horizontal: bool, th: float, mark: str) -> int:
    """The dimension rows a dimension's frame, datum symbol and key mark take
    beyond its own. Over a level dimension the frame takes the next row and the
    datum symbol the one after; beside an upright one's value they all run
    outward, across as many rows as they are wide."""
    if horizontal:
        return (dim.frame is not None) + (dim.datum is not None)
    width = ((mark_width(mark, th) + th * 0.5 if dim.key else 0.0)
             + (frame_size(dim.frame, th)[0] + th * 0.5 if dim.frame is not None else 0.0)
             + (_DATUM_REACH * th if dim.datum is not None else 0.0))
    return max(0, math.ceil((th * 1.5 + width + 2.0) / _DIM_ROW) - 1) if width else 0


def _plan_view(view: View, proj, bounds, items: list["_Dim"], sheet: Sheet) -> dict:
    """Which side and row each dimension takes, and the room the view's annotation
    needs on each side, before anything is drawn.

    A dimension left unplaced goes on the side of the view its points are on --
    a hole pitch along the top edge above the view, a height on the right half
    to the right -- so its extension lines do not cross the part to reach the
    far side. On each side the shortest dimension sits nearest the view and the
    longest outermost, so no extension line crosses another dimension's line;
    ``overall()`` is the longest and outermost of all. The room is what
    :func:`_arrange_three_views` spaces the views by.
    """
    bx0, bx1, by0, by1 = bounds
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    th = sheet.text_height
    sv = view.scale or sheet._scale()
    explicit = dict.fromkeys(_SIDES, 0)
    # A datum feature symbol stands on its face, in the first rows out of its side.
    for _letter, point, stem in view._datums:
        side = _side_of(_datum_toward(proj.point(point), bounds, stem))
        explicit[side] = max(explicit[side], math.ceil((_DATUM_REACH * th + 2.0) / _DIM_ROW) - 1)
    mark = sheet.profile.characteristic_mark if sheet.profile is not None else "KC"
    pending: dict[str, list] = {side: [] for side in _SIDES}
    for order, dim in enumerate(items):
        if dim.kind != "linear" or dim.orientation == "aligned":
            continue  # an aligned dimension stands off its own inclined edge, in no row
        a, b = proj.point(dim.p1), proj.point(dim.p2)
        horizontal = (dim.orientation or _spans(a, b)) == "h"
        if dim.offset is not None:
            dim.side = (("top" if dim.offset >= 0 else "bottom") if horizontal
                        else ("right" if dim.offset >= 0 else "left"))
            explicit[dim.side] = max(explicit[dim.side], int(abs(dim.offset) // _DIM_ROW))
            continue
        if horizontal:
            side, span = ("top" if (a[1] + b[1]) / 2 >= cy - 1e-9 else "bottom"), abs(b[0] - a[0])
        else:
            side, span = ("right" if (a[0] + b[0]) / 2 >= cx - 1e-9 else "left"), abs(b[1] - a[1])
        pending[side].append((round(span, 6), order, dim, horizontal))
    rows: dict[str, int] = {}
    for side in _SIDES:
        row = explicit[side]
        for _span, _order, dim, horizontal in sorted(pending[side], key=lambda t: (t[0], t[1])):
            row += 1
            dim.side, dim.row = side, row
            row += _rows_beyond(dim, horizontal, th, mark)
        rows[side] = row
    overall = {}
    if "width" in view._overall:
        overall["top"] = rows["top"] + 1
    if "height" in view._overall:
        overall["left"] = rows["left"] + 1
    rows_out = {side: overall.get(side, rows[side]) for side in _SIDES}
    room = {side: (rows_out[side] * _DIM_ROW + th * 1.5) if rows_out[side] else 0.0 for side in _SIDES}
    rowed = dict(room)
    for dim in items:
        if dim.kind in ("hole", "slot", "diameter", "radius"):
            # The side a callout prefers is its hole's own half of the view, the
            # short way out, past every dimension row on that side.
            side = "right" if proj.point(dim.p1)[0] > cx + 1e-6 else "left"
            width = _ink_width(_callout_value(dim), th)
            if dim.frame is not None:
                width = max(width, frame_size(dim.frame, th)[0])
            room[side] = max(room[side], rowed[side] + _CALLOUT_CLEAR + _CALLOUT_LANDING + _CALLOUT_GAP
                             + width + _CALLOUT_GAP)
        elif dim.kind == "flag" and dim.p1 is not None and dim.offset is None:
            # An unplaced flag goes out by the side nearest its point.
            side = _side_of(_datum_toward(proj.point(dim.p1), bounds, None))
            room[side] = max(room[side], rowed[side] + _FLAG_SIDE * th + 12.0)
        elif dim.kind in ("note", "frame", "flag") and dim.p1 is not None:
            p = proj.point(dim.p1)
            width = 4.0 + (_text_width(dim.text, th) if dim.kind == "note" else
                           frame_size(dim.frame, th)[0] if dim.kind == "frame" else _FLAG_SIDE * th)
            if dim.radius >= 0:
                room["right"] = max(room["right"], (p[0] - bx1) * sv + dim.radius + width)
            else:
                room["left"] = max(room["left"], (bx0 - p[0]) * sv - dim.radius + width)
            if dim.angle >= 0:
                room["top"] = max(room["top"], (p[1] - by1) * sv + dim.angle + th + 1.0)
            else:
                room["bottom"] = max(room["bottom"], (by0 - p[1]) * sv - dim.angle)
    if view._balloons:
        # A column of balloons each side of a tall view, a row above and below a wide one.
        for side in (("left", "right") if _balloon_axis(bounds) else ("bottom", "top")):
            room[side] += _BALLOON_LEAD + 2 * _BALLOON_R + _BALLOON_AIR
    room["bottom"] += _LABEL_ROOM  # the view's label hangs under everything below it
    return {"rows": rows, "overall": overall, "room": room}


#: A hole table's row height and its fixed columns; SIZE is as wide as its longest entry.
_TABLE_ROW = 6.0
_TABLE_COLUMNS = (("TAG", 12.0), ("X", 20.0), ("Y", 20.0))
#: The length of the X and Y arrows marking a hole table's origin.
_ORIGIN_ARM = 10.0


class _TableRow(NamedTuple):
    """One tabulated hole or slot: its tag, its X and Y from the table's origin
    (model mm, measured on the whole part), its size as a callout reads it, the
    feature, and the arc its tag stands beside: where the view draws that arc's
    centre (a hole's, or a slot's end furthest up and right) and its radius
    (model mm)."""

    tag: str
    x: float
    y: float
    size: str
    feature: Any
    beside: tuple[float, float]
    radius: float


@dataclass
class _HoleTable:
    """A view's hole table: its rows, the model point its X and Y run from, its
    size on the sheet, and its top-left corner once placed."""

    rows: list[_TableRow]
    origin: tuple[float, float, float]
    size: tuple[float, float]
    corner: tuple[float, float] | None = None


def _hole_table(view: View, proj, features, cut, items) -> _HoleTable:
    """The holes and slots a view tabulates, tagged and measured from its origin."""
    if any(dim.kind in ("hole", "slot", "holes") for dim in items):
        raise ValueError(f"the {view.name} view both tabulates its holes and calls them out; hole_table() lists "
                         "every hole the view looks down, so drop its holes(), hole() and slot() calls")
    look = _look(view)
    order = _kinds([*(h for h in features.holes if _looks_into(h, look) and _shows(view, proj, h, h.length, cut)),
                    *(sl for sl in features.slots if _looks_into(sl, look) and _shows(view, proj, sl, sl.run, cut))])
    if not order:
        raise ValueError(f"{view.name}.hole_table(): the {view.name} view looks down no hole or slot")
    origin = view._table.origin if view._table.origin is not None else _lower_left(view.shape, proj)
    zero = proj._raw_point(origin)
    if len(order) > len(_SECTION_LETTERS):
        raise ValueError(f"{view.name}.hole_table(): {len(order)} kinds of hole is more than the "
                         f"{len(_SECTION_LETTERS)} letters a table tags them with")

    def middle(feature) -> tuple[float, float, float]:
        """Where a hole's axis or a slot's middle meets the face it opens in."""
        if isinstance(feature, Slot):
            return tuple((a + b) / 2 for a, b in zip(*feature.ends))
        return feature.mouth

    def beside(feature) -> tuple[float, float]:
        """The centre of the arc a tag stands beside: up and right of it, the tag
        is clear of the outline and the centre lines."""
        if isinstance(feature, Slot):
            return max((proj.point(end) for end in feature.ends), key=lambda p: p[0] + p[1])
        return proj.point(feature.mouth)

    rows = []
    for letter, members in zip(_SECTION_LETTERS, order):
        is_slot = isinstance(members[0], Slot)
        spec = _slot_spec(members[0], 1) if is_slot else _hole_spec(members[0], 1)
        size = hole_callout_text(spec)
        radius = members[0].width / 2 if is_slot else _outer_radius(spec)
        measured = []
        for feature in members:
            at = proj._raw_point(middle(feature))
            measured.append((round(at[0] - zero[0], 6), round(at[1] - zero[1], 6), feature))
        for number, (x, y, feature) in enumerate(sorted(measured, key=lambda m: (round(m[0], 3), round(m[1], 3))),
                                                start=1):
            rows.append(_TableRow(f"{letter}{number}", x, y, size, feature, beside(feature), radius))
    width = sum(w for _n, w in _TABLE_COLUMNS) + max(28.0, max(_ink_width(r.size, 2.5) for r in rows) + 6.0)
    return _HoleTable(rows, origin, (width, (len(rows) + 1) * _TABLE_ROW))


def _lower_left(shape, proj) -> tuple[float, float, float]:
    """The corner of the part's box a view draws lowest and furthest left."""
    box = shape.bounding_box()
    corners = [(x, y, z) for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y) for z in (box.min.Z, box.max.Z)]
    return min(corners, key=lambda c: (round(proj._raw_point(c)[0], 6), round(proj._raw_point(c)[1], 6)))


def _draw_hole_tags(msp, table: _HoleTable, proj, to_sheet, sv: float, th: float, text) -> None:
    """Each tabulated hole's tag beside it, and the origin its X and Y run from."""
    from ezdxf.enums import TextEntityAlignment as A

    for row in table.rows:
        c, r = to_sheet(row.beside), row.radius * sv
        lean = r * 0.71 + 0.8
        text(row.tag, c[0] + lean, c[1] + lean, 2.5, A.BOTTOM_LEFT, "DIM")
    o = to_sheet(proj.point(table.origin))
    # The arrows often lie along the part's edges, so each letter stands off its
    # arrow's tip on the far side of the corner, clear of those edges.
    x_tip, y_tip = (o[0] + _ORIGIN_ARM, o[1]), (o[0], o[1] + _ORIGIN_ARM)
    for tip in (x_tip, y_tip):
        msp.add_leader([tip, o], dxfattribs={"layer": "DIM"},
                       override={"dimasz": th * 0.7, "dimldrblk": "_CLOSEDFILLED"})
    text("X", x_tip[0], x_tip[1] - 1.0, 2.5, A.TOP_CENTER, "DIM")
    text("Y", y_tip[0] - 1.0, y_tip[1], 2.5, A.MIDDLE_RIGHT, "DIM")
    text("0,0", o[0] - 1.0, o[1] - 1.0, 2.5, A.TOP_RIGHT, "DIM")


def _draw_hole_table(msp, table: _HoleTable, text) -> None:
    """The table itself, header on top: TAG, X, Y, SIZE."""
    from ezdxf.enums import TextEntityAlignment as A

    x0, y1 = table.corner
    w, h = table.size
    columns = list(_TABLE_COLUMNS) + [("SIZE", w - sum(cw for _n, cw in _TABLE_COLUMNS))]
    msp.add_lwpolyline([(x0, y1), (x0 + w, y1), (x0 + w, y1 - h), (x0, y1 - h)], close=True,
                       dxfattribs={"layer": "TITLE"})
    for r in range(1, len(table.rows) + 1):
        msp.add_line((x0, y1 - r * _TABLE_ROW), (x0 + w, y1 - r * _TABLE_ROW), dxfattribs={"layer": "TITLE"})
    x = x0
    for c, (name, width) in enumerate(columns):
        if c:
            msp.add_line((x, y1), (x, y1 - h), dxfattribs={"layer": "TITLE"})
        text(name, x + width / 2, y1 - _TABLE_ROW / 2, _CAPTION_HEIGHT, A.MIDDLE_CENTER, fit=width - 2)
        for r, row in enumerate(table.rows, start=1):
            value = (row.tag, _fmt(row.x), _fmt(row.y), row.size)[c]
            mid = y1 - (r + 0.5) * _TABLE_ROW
            if c == 3:
                text(value, x + 2.0, mid, 2.5, A.MIDDLE_LEFT, "NOTES")
            else:
                text(value, x + width / 2, mid, 2.5, A.MIDDLE_CENTER, fit=width - 2)
        x += width
