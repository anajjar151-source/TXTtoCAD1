"""A bent sheet bracket for the sheet metal estimate (`cadgen manufacturing check` with `"process": "sheet_metal"`).

A 1.5 mm sheet: a channel 40 mm across with two 20 mm flanges bent up at an inside radius of 1.5 mm (R = t), 50 mm
long, and a 15 mm tab bent down at R = 3 mm (2t) out of the middle of the base's back edge, with no relief cut. In
6061-T6 the flanges' bends are tighter than its minimum R/t and the tab's ends need reliefs; in 5052-H32 every bend
forms.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd
from cadgen import step

THICKNESS = 1.5
FLANGE_RADIUS = 1.5
TAB_RADIUS = 3.0
BASE = 40.0
FLANGE = 20.0
LENGTH = 50.0
TAB_WIDTH = 15.0
TAB_DROP = 12.0


def bent_profile(t: float, radius: float, legs: list[float], bends: list[float], heading_deg: float, width: float):
    """A sheet ``t`` thick: straight ``legs`` joined by ``bends`` (degrees, + turns left) at inside ``radius``, starting
    at the origin along ``heading_deg`` in the XZ plane, extruded ``width`` along +Y."""
    x, z, heading = 0.0, 0.0, math.radians(heading_deg)
    left, right = [], []

    def side(px, pz, h, d):
        return bd.Vector(px - math.sin(h) * d, 0.0, pz + math.cos(h) * d)

    for i, leg in enumerate(legs):
        nx, nz = x + math.cos(heading) * leg, z + math.sin(heading) * leg
        left.append(bd.Edge.make_line(side(x, z, heading, t / 2), side(nx, nz, heading, t / 2)))
        right.append(bd.Edge.make_line(side(nx, nz, heading, -t / 2), side(x, z, heading, -t / 2)))
        x, z = nx, nz
        if i < len(bends):
            turn = math.radians(bends[i])
            s = 1.0 if turn > 0 else -1.0
            centre = side(x, z, heading, s * (radius + t / 2))

            def arc(r, forward, a0=heading - s * math.pi / 2, turn=turn, centre=centre):
                points = [centre + bd.Vector(r * math.cos(a0 + turn * f), 0.0, r * math.sin(a0 + turn * f))
                          for f in (0, 0.5, 1)]
                return bd.Edge.make_three_point_arc(*(points if forward else points[::-1]))

            inner, outer = (radius, radius + t) if s > 0 else (radius + t, radius)
            left.append(arc(inner, True))
            right.append(arc(outer, False))
            heading += turn
            a1 = heading - s * math.pi / 2
            x, z = centre.X + (radius + t / 2) * math.cos(a1), centre.Z + (radius + t / 2) * math.sin(a1)
    ends = [bd.Edge.make_line(left[-1].end_point(), right[-1].start_point()),
            bd.Edge.make_line(right[0].end_point(), left[0].start_point())]
    profile = bd.Face(bd.Wire([*left, ends[0], *reversed(right), ends[1]]))
    return bd.Solid.extrude(profile, bd.Vector(0, width, 0))


@step(out="../STEP/sheet_metal_bracket.step")
def sheet_metal_bracket():
    # The channel: down the left flange, along the base, up the right flange; its base's mid-surface is z = -FLANGE - R - t/2.
    channel = bent_profile(THICKNESS, FLANGE_RADIUS, [FLANGE, BASE, FLANGE], [90, 90], -90, LENGTH)
    base_z = -FLANGE - FLANGE_RADIUS - THICKNESS / 2
    base_x0 = FLANGE_RADIUS + THICKNESS / 2
    # The tab: its first leg lies on the base, along +y from inside it out past the back edge, then turns down.
    tab = bent_profile(THICKNESS, TAB_RADIUS, [20.0, TAB_DROP], [-90], 0, TAB_WIDTH)
    tab = bd.Pos(base_x0 + BASE / 2 + TAB_WIDTH / 2, LENGTH - 20.0, base_z) * bd.Rot(0, 0, 90) * tab
    part = (channel + tab).clean()
    part.label = "sheet_metal_bracket"
    return part


if __name__ == "__main__":
    sheet_metal_bracket()
