from __future__ import annotations

# Prompt: An avionics mounting bracket, one solid in mm: a 120 x 80 x 8 base with a 36 mm back
# wall, two webs, a four-hole mounting pattern, a 10 mm locating bore, slots and a wall window,
# carrying semantic PMI as a model-based definition: datums A (bottom), B (back face) and C (left
# side), the base thickness and the bore's diameter with explicit tolerances, the bottom's flatness,
# and the bore's position to A|B|C, its true position located by basic dimensions from B and C;
# datum features B and C profiled to the datums before them, and every other face (the wall, the
# webs, the holes, slots and window) held by a general profile to A|B|C (Note 1); a general note
# and a flag note on the bore from the project's notes library; and two views: section A-A through
# the bore's axis, and an iso view showing everything.
#
# The geometry, every tolerance value below and every note's text (lib/notes.py) are ILLUSTRATIVE,
# chosen to exercise the PMI export, not taken from an aircraft drawing. This is not a qualified
# flight part. Do not manufacture to it.

import build123d as bd

from cadgen.engine import materials, pmi, step, xbf
from lib.notes import NOTES


def _body():
    body = bd.Pos(0, 0, 4) * bd.Box(120, 80, 8)
    body += bd.Pos(0, 36, 26) * bd.Box(120, 8, 36)
    # Two 6 mm webs support the back wall, outside the mounting pattern.
    web = bd.extrude(bd.Plane.YZ * bd.Polygon((12, 8), (32, 8), (32, 36), align=None), amount=6)
    for x in (-52, 46):
        body += bd.Pos(x, 0, 0) * web
    for x in (-36, 36):
        for y in (-23, 23):
            body -= bd.Pos(x, y, 4) * bd.Cylinder(3.3, 10)
    body -= bd.Pos(0, -18, 4) * bd.Cylinder(5, 10)
    # Rounded through-slots in the base and a window in the back wall lighten the part.
    for x in (-20, 20):
        slot = bd.Pos(x, 2, -1) * bd.Rot(0, 0, 90) * bd.SlotOverall(28, 14)
        body -= bd.extrude(slot, amount=10)
    window = bd.Plane.XZ * bd.Pos(0, 26) * bd.RectangleRounded(36, 16, 4)
    body -= bd.Pos(0, 41, 0) * bd.extrude(window, amount=10)
    for x in (-38, 38):
        body -= bd.Pos(x, 36, 28) * bd.Rot(90, 0, 0) * bd.Cylinder(3.2, 10)
    body.label = "avionics bracket"
    body.material = materials.aluminium_7075
    return body


def _plane(body, axis, at):
    """The largest planar face square to ``axis`` (0 X, 1 Y, 2 Z) at the coordinate ``at``."""
    return max((face for face in body.faces().filter_by(bd.GeomType.PLANE)
                if abs(tuple(face.center())[axis] - at) < 1e-6 and abs(tuple(face.normal_at())[axis]) > 0.999),
               key=lambda face: face.area)


@xbf(out="../XBF/aerospace_avionics_bracket.xbf")
@step(out="../XBF/aerospace_avionics_bracket.step")
def aerospace_avionics_bracket():
    body = _body()
    bottom, top = _plane(body, 2, 0), _plane(body, 2, 8)
    back, left = _plane(body, 1, 40), _plane(body, 0, -60)
    bore = next(face for face in body.faces().filter_by(bd.GeomType.CYLINDER) if abs(face.radius - 5) < 1e-6)
    return pmi.annotate(
        body,
        pmi.datum("A", bottom, presentation=pmi.place((45, -32, 0), (0, -16, -10))),
        pmi.datum("B", back, presentation=pmi.place((45, 40, 35), (15, 16, 0))),
        pmi.datum("C", left, presentation=pmi.place((-60, -25, 4), (-18, -10, 0))),
        # Illustrative: 8 +/-0.1.
        pmi.distance("base-thickness", bottom, top, tolerance=pmi.plus_minus(0.1),
                     presentation=pmi.place((60, -15, 4), (22, -8, 0))),
        # Illustrative: diameter 10 +0.05/0.
        pmi.diameter("locating-bore", bore, tolerance=pmi.plus_minus(0.05, 0),
                     presentation=pmi.place((5, -18, 8), (18, -22, 16))),
        # Illustrative: flatness 0.05.
        pmi.flatness("mounting-face-flatness", bottom, 0.05,
                     presentation=pmi.place((-42, -32, 0), (-8, -18, -12))),
        # Illustrative: position diameter 0.1 to A|B|C.
        pmi.position("locating-bore-position", bore, 0.1, datums=["A", "B", "C"],
                     presentation=pmi.place((-5, -18, 8), (-18, -22, 30))),
        # The bore's true position: basic (theoretically exact) distances from B and C, measured.
        pmi.basic("bore-from-B", back, bore, presentation=pmi.place((0, 11, 8), (8, 0, 0))),
        pmi.basic("bore-from-C", left, bore, presentation=pmi.place((-30, -18, 8), (0, -8, 0))),
        # The datum features a general profile leaves to their own controls. Illustrative: B within
        # 0.1 of true to A, C within 0.1 to A|B.
        pmi.profile("B-profile", back, 0.1, datums=["A"], presentation=pmi.place((-45, 40, 35), (-15, 16, 0))),
        pmi.profile("C-profile", left, 0.1, datums=["A", "B"], presentation=pmi.place((-60, 10, 4), (-18, 10, 0))),
        # Note 1. Illustrative: every face nothing above controls within 0.5 of true to A|B|C.
        pmi.general_profile("general", 0.5, datums=["A", "B", "C"]),
        # Note 2, a general note, and Note 3, a flag note on the bore and its diameter.
        pmi.note("edges", NOTES["edges"]),
        pmi.note("mask", NOTES["primer-mask"], faces=[bore], annotations=["locating-bore"],
                 presentation=pmi.place((0, -23, 8), (0, -16, 16))),
        # Section A-A across y through the bore's axis, keeping the far side (invert) so the front
        # camera, at -Y, looks at the cut; the bore's diameter drawn on it.
        pmi.view("A-A", camera="front",
                 shows=["base-thickness", "locating-bore", "locating-bore-position", "bore-from-C", "mask"],
                 section=pmi.section("y", -18, invert=True),
                 place={"locating-bore": pmi.place((5, -18, 4), (18, 0, 16))}),
        pmi.view("iso", camera="iso"),  # shows every annotation and note
        library=NOTES,
    )


if __name__ == "__main__":
    aerospace_avionics_bracket()
