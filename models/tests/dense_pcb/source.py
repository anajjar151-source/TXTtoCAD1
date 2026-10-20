"""A dense PCB beside a few ordinary parts (issue #626).

One component carries thousands of small features -- through-holes and round
pads -- so its exact surface is large while each feature tessellates to a
handful of triangles. Raise DENSE_PCB_GRID to make the board heavier.
"""
import os

from cadgen import build123d as bd
from cadgen import step

GRID = int(os.environ.get("DENSE_PCB_GRID", "85"))  # GRID x GRID holes and pads
PITCH = 1.27
BOARD_T = 1.6
SIZE = GRID * PITCH + 4


def board():
    plate = bd.Solid.make_box(SIZE, SIZE, BOARD_T)
    holes, pads = [], []
    for i in range(GRID):
        for j in range(GRID):
            x, y = 2 + PITCH * (i + 0.5), 2 + PITCH * (j + 0.5)
            holes.append(bd.Solid.make_cylinder(0.3, BOARD_T + 2).moved(bd.Location((x, y, -1))))
            pads.append(bd.Solid.make_cylinder(0.4, 0.05).moved(bd.Location((x + PITCH / 2, y, BOARD_T))))
    plate = plate.cut(bd.Compound(children=holes))
    pcb = bd.Compound(children=[plate, *pads])
    pcb.label = "dense_pcb"
    pcb.color = bd.Color(0.1, 0.45, 0.2)
    return pcb


@step(out="dense_pcb.step")
def assembly():
    parts = [board()]
    corners = [(0, -12), (SIZE - 10, -12), (0, SIZE + 2), (SIZE - 10, SIZE + 2)]
    for k, (x, y) in enumerate(corners):
        part = bd.Solid.make_box(10, 10, 6).moved(bd.Location((x, y, 0)))
        part.label = f"bracket_{k + 1}"
        part.color = bd.Color(0.6, 0.6, 0.65)
        parts.append(part)
    return bd.Compound(children=parts)


if __name__ == "__main__":
    assembly()
