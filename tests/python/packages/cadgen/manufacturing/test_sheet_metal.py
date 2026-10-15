"""Sheet metal bending (`"process": "sheet_metal"`, a Tier 2 estimate): the study, Gardiner's springback, cracking.

Each solve reads a bent sheet build123d writes into a temporary directory (a profile of flats and arcs, extruded):

- a single 90° bend of 1.5 mm 5052-H32 at R = 2t, a tab out of a plate's edge, springs back Gardiner's 1.19° (the
  skill's hand check); the tab turns rigidly by exactly that while the held plate stays put, and its two ends, with no
  relief cut, are flagged;
- a U with both bends at R = t cracks in 6061-T6 (its minimum R/t at 1.5 mm is 1.44) and not in 5052-H32 (0.89), the
  failing bends carrying what they measured and the fix; it finds both bends at 90°, and held by one flange the other
  ends twice one bend's springback off;
- a block is refused in a sentence.

Each fresh STEP costs a document compile of several seconds, so two fixtures carry every solve.

The sheet metal reference stays in step with the table. Parse and formula tests run everywhere; checks need the fea
extra.
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import check, check_keeping, class_directory, needs_fea, read_study, value_error
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
BASE = {"process": "sheet_metal", "material": "5052-h32"}


def bent_solid(*, t: float, radius: float, legs: list[float], bends: list[float], width: float = 25.0):
    """A sheet ``t`` thick bent to inside radius ``radius``: straight ``legs`` (mm) joined by ``bends`` (degrees, + turns
    toward +z), its first leg along +x on z = 0..t, the profile extruded ``width`` along +y."""
    from build123d import Edge, Face, Solid, Vector, Wire

    x, z, heading = 0.0, t / 2, 0.0
    left, right = [], []

    def side(px, pz, h, d):
        return Vector(px - math.sin(h) * d, 0.0, pz + math.cos(h) * d)

    for i, leg in enumerate(legs):
        nx, nz = x + math.cos(heading) * leg, z + math.sin(heading) * leg
        left.append(Edge.make_line(side(x, z, heading, t / 2), side(nx, nz, heading, t / 2)))
        right.append(Edge.make_line(side(nx, nz, heading, -t / 2), side(x, z, heading, -t / 2)))
        x, z = nx, nz
        if i < len(bends):
            turn = math.radians(bends[i])
            s = 1.0 if turn > 0 else -1.0
            centre = side(x, z, heading, s * (radius + t / 2))

            def arc(r, forward):
                a0 = heading - s * math.pi / 2
                points = [centre + Vector(r * math.cos(a0 + turn * f), 0.0, r * math.sin(a0 + turn * f)) for f in (0, 0.5, 1)]
                return Edge.make_three_point_arc(*(points if forward else points[::-1]))

            inner, outer = (radius, radius + t) if s > 0 else (radius + t, radius)
            left.append(arc(inner, True))
            right.append(arc(outer, False))
            heading += turn
            a1 = heading - s * math.pi / 2
            x, z = centre.X + (radius + t / 2) * math.cos(a1), centre.Z + (radius + t / 2) * math.sin(a1)
    ends = [Edge.make_line(left[-1].end_point(), right[-1].start_point()),
            Edge.make_line(right[0].end_point(), left[0].start_point())]
    profile = Face(Wire([*left, ends[0], *reversed(right), ends[1]]))
    return Solid.extrude(profile, Vector(0, width, 0))


def bent_sheet(directory: Path, name: str, **shape) -> Path:
    """:func:`bent_solid` written to ``directory/name.step``."""
    from build123d import export_step

    step = directory / f"{name}.step"
    export_step(bent_solid(**shape), str(step))
    return step


def gardiner_by_hand(radius: float, t: float, yield_MPa: float, E_MPa: float, angle: float) -> float:
    """The springback, degrees, worked as the reference does it."""
    x = radius * yield_MPa / (E_MPa * t)
    final = radius / (4 * x ** 3 - 3 * x + 1)
    return angle * (1 - (2 * radius / t + 1) / (2 * final / t + 1))


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        return read_study({**BASE, **changes})

    def test_the_sheet_and_the_study_keys(self):
        study = self.parse()
        inputs = study.inputs
        self.assertEqual((inputs.sheet.key, inputs.thickness_mm, inputs.tolerance_deg, inputs.fixed_face, inputs.grain),
                         ("aluminum-5052-h32", None, 1.0, None, None))
        self.assertEqual((study.mesh_order, study.material, inputs.requires_anchor, inputs.face_refs), (1, None, False, ()))
        own = self.parse(material={"name": "6061-T6", "yield_MPa": 290}, thickness_mm=2, tolerance_deg=0.5,
                         fixed_face="#o1.f3", grain_direction=[0, 2, 0]).inputs
        self.assertEqual((own.sheet.key, own.sheet.yield_strength, own.sheet.E), ("aluminum-6061-t6", 290.0, 68_900.0))
        self.assertEqual((own.thickness_mm, own.tolerance_deg, own.face_refs, own.grain), (2.0, 0.5, ("#o1.f3",), (0.0, 1.0, 0.0)))

    def test_the_errors_name_the_field(self):
        cases = [
            ({"material": None}, "study.material: the sheet"),
            ({"material": "unobtainium"}, "material: 'unobtainium' is not a sheet"),
            ({"material": {"name": "my sheet", "E_MPa": 70000}}, "material: an object that names no sheet in the table needs"),
            ({"material": {"name": "5052", "temper": "H34"}}, "material: unknown keys ['temper']"),
            ({"material": {"name": "5052", "min_r_t": [[2, 1], [1, 2]]}}, "material.min_r_t: [thickness_mm, R/t] pairs"),
            ({"thickness_mm": 0}, "thickness_mm: must be > 0"),
            ({"tolerance_deg": "1°"}, "tolerance_deg: expected a number"),
            ({"fixed_face": 3}, "fixed_face: a face of the flat to hold still"),
            ({"grain_direction": [0, 0, 0]}, "grain_direction: the direction is zero"),
            ({"grain_direction": "x"}, "grain_direction: the sheet's rolling direction as [x, y, z]"),
            ({"parts": {"a": {"material": "steel"}}}, "study.parts: a sheet metal study reads one part"),
            ({"mesh": {"order": 2}}, "study.mesh.order: sheet_metal studies take order 1"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "view.checks[0].kind"),
            ({"bend_radius": 3}, "unknown keys ['bend_radius']"),
        ]
        for changes, fragment in cases:
            document = {key: value for key, value in {**BASE, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))


class Formulas(unittest.TestCase):
    def test_gardiners_springback_of_the_references_hand_check(self):
        from cadgen._internal.manufacturing.processes.brake import gardiner, lookup_sheet

        sheet = lookup_sheet("5052-H32")
        g = gardiner(3.0, 1.5, sheet)
        self.assertAlmostEqual(g["x"], 0.005491, places=6)
        self.assertAlmostEqual(g["final_radius_mm"], 3.0502, places=4)
        self.assertAlmostEqual(90 * (1 - g["kept"]), 1.190, places=3)
        self.assertAlmostEqual(90 / g["kept"] - 90, 1.206, places=3)
        self.assertTrue(gardiner(2000.0, 1.5, sheet)["elastic"])     # too gentle to yield: it springs back flat

    def test_the_minimum_bend_follows_temper_and_thickness(self):
        from cadgen._internal.manufacturing.processes.brake import k_factor, lookup_sheet

        t6, h32 = lookup_sheet("6061-t6"), lookup_sheet("5052-h32")
        self.assertAlmostEqual(t6.min_ratio(1.5), 1.445, places=3)    # between 1/32" (1t) and 1/16" (1.5t)
        self.assertAlmostEqual(h32.min_ratio(1.5), 0.889, places=3)   # between 1/32" (0t) and 1/16" (1t)
        self.assertEqual((t6.min_ratio(20.0), lookup_sheet("crs-1008").min_ratio(3.0)), (5.0, 0.0))
        self.assertEqual([round(k_factor(r), 3) for r in (0.2, 1.0, 2.0, 10.0)], [0.3, 0.325, 0.4, 0.5])


def tab_on_plate(directory: Path) -> Path:
    """A 10 mm wide tab of 1.5 mm sheet bent 90° up at R = 3 mm (2t) out of the middle of a 30 x 40 mm plate's edge
    (x = 30, the tab over y = 0..10), with no relief cut at its ends."""
    from build123d import Align, Box, Pos, export_step

    plate = Pos(0, -15, 0) * Box(30, 40, 1.5, align=(Align.MIN, Align.MIN, Align.MIN))
    step = directory / "plate.step"
    export_step((plate + bent_solid(t=1.5, radius=3.0, legs=[30, 20], bends=[90], width=10)).clean(), str(step))
    return step


@needs_fea
class SingleBend(unittest.TestCase):
    """One 90° bend at R = 2t, out of a plate's edge."""

    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.result, cls.solved = check_keeping(tab_on_plate(directory), BASE)

    def test_it_springs_back_gardiners_angle(self):
        from cadgen._internal.manufacturing.processes.brake import lookup_sheet

        sheet = lookup_sheet("5052-h32")
        [bend] = self.result.summary["bends"]
        self.assertEqual((bend["angle_deg"], bend["inner_radius_mm"], bend["r_over_t"]), (90.0, 3.0, 2.0))
        self.assertAlmostEqual(bend["springback_deg"], gardiner_by_hand(3.0, 1.5, sheet.yield_strength, sheet.E, 90), delta=1e-3)
        self.assertAlmostEqual(bend["springback_deg"], 1.19, delta=0.005)
        self.assertGreater(bend["springback_hardening_deg"], bend["springback_deg"])
        self.assertEqual(self.result.summary["thickness_measured_mm"], 1.5)

    def test_the_tab_turns_by_its_springback_and_the_plate_stays(self):
        import numpy as np

        nodes, moved = self.solved.dof_locations, self.solved.dof_locations + self.solved.fields["displacement"]
        plate, tab = nodes[:, 0] < 29.9, nodes[:, 2] > 5.0
        self.assertEqual(float(np.abs(moved[plate] - nodes[plate]).max()), 0.0)
        before = nodes[tab] - nodes[tab].mean(axis=0)
        after = moved[tab] - moved[tab].mean(axis=0)
        u, _, vt = np.linalg.svd(before.T @ after)
        turn = math.degrees(math.acos((np.trace(u @ vt) - 1) / 2))
        self.assertAlmostEqual(turn, self.result.summary["bends"][0]["springback_deg"], delta=1e-5)
        # Each bend's springback colours its bend and nothing else.
        springback = self.solved.fields["springback"]
        self.assertTrue((springback[plate] == 0).all() and springback.max() > 1.1)

    def test_a_bend_ending_inside_the_plate_needs_a_relief_at_both_ends(self):
        [relief] = [f for f in self.result.findings if f["type"] == "relief_missing"]
        self.assertEqual((relief["severity"], len(relief["items"]), relief["fix"]["action"]), ("warning", 2, "add_relief"))
        self.assertEqual(sorted(round(item["at"][1]) for item in relief["items"]), [0, 10])


@needs_fea
class TwoBends(unittest.TestCase):
    """A U of 1.5 mm sheet with both bends at R = t: past 6061-T6's minimum R/t, within 5052-H32's."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        directory = class_directory(cls)
        step = bent_sheet(directory, "u", t=1.5, radius=1.5, legs=[20, 30, 20], bends=[90, 90])
        cls.flange = next(face.ref for face in fea.faces(step).faces if face.normal and face.normal[2] < -0.99
                          and face.center_mm[2] < 0.1)
        cls.t6 = check(step, {**BASE, "material": "6061-t6"})
        cls.h32 = check(step, {**BASE, "fixed_face": cls.flange})

    def test_it_finds_both_bends_and_held_by_a_flange_the_other_is_off_by_both(self):
        summary = self.h32.summary
        self.assertEqual([(b["bend"], b["angle_deg"], b["r_over_t"]) for b in summary["bends"]], [(1, 90.0, 1.0), (2, 90.0, 1.0)])
        self.assertEqual([f["flat"] for f in summary["flats"]], [1, 2, 3])
        self.assertIn(self.flange, summary["flats"][0]["faces"])
        self.assertEqual(sorted(tuple(b["joins"]) for b in summary["bends"]), [(1, 2), (2, 3)])
        self.assertAlmostEqual(summary["max_angle_error_deg"], 2 * summary["bends"][0]["springback_deg"], delta=1e-5)

    def test_the_bends_crack_in_6061_t6_and_not_in_5052_h32(self):
        cracks = [f for f in self.t6.findings if f["type"] == "bend_may_crack"]
        self.assertEqual([f["severity"] for f in cracks], ["error", "error"])
        # A failing check carries what it measured against its limit, and the change that makes it pass.
        crack = cracks[0]
        self.assertEqual(crack["measured"]["pass_when"], "below")
        self.assertGreater(crack["measured"]["value"], crack["measured"]["limit"])
        self.assertEqual(crack["fix"]["action"], "increase_radius")
        self.assertAlmostEqual(crack["fix"]["params"]["inner_radius_mm"], 2.2)      # 1.445 x 1.5 mm, rounded up
        self.assertTrue(crack["fix"]["where"])
        self.assertEqual((self.t6.verdict["status"], self.t6.verdict["headline"]), ("fix", "2 to fix · bend may crack"))
        self.assertEqual([f["type"] for f in self.h32.findings if f["type"].startswith("bend_")], ["bend_formable"] * 2)
        self.assertEqual(self.h32.summary["cracking_bends"], [])
        # Every check it makes says so when it passes: two bends, two checks each, the far flat, the reliefs, the
        # thickness it was not given; work hardening takes 5052-H32's 0.5° past the 1° tolerance, a warning.
        passed = sorted(f["type"] for f in self.h32.findings if f["severity"] == "info" and f.get("measured"))
        self.assertEqual(passed, ["angle_error_within_tolerance", "bend_formable", "bend_formable", "reliefs",
                                  "springback_within_tolerance", "springback_within_tolerance"])
        self.assertEqual([f["type"] for f in self.h32.findings if f["severity"] == "warning"], ["springback_work_hardening"])
        self.assertEqual(self.h32.verdict, {"status": "ready", "headline": "Ready to bend · 2 bends · overbend up to 0.498°",
                                            "errors": 0, "warnings": 1, "passed": 6})


class NotSheet(unittest.TestCase):
    def test_a_block_is_refused_in_a_sentence(self):
        from build123d import Box

        from cadgen._internal.manufacturing.processes.bends import read_sheet

        block = Box(20, 20, 20)
        message = value_error(self, read_sheet, block.wrapped, part="#o1", volume_mm3=block.volume, area_mm2=block.area)
        self.assertRegex(message, r"^sheet_metal: #o1 has no bends: .* not a bent sheet")


class SkillDocs(unittest.TestCase):
    """The sheet metal reference lists what the table holds."""

    def _rows(self, path: Path, heading: str) -> list[list[str]]:
        text = path.read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]

    def test_the_reference_lists_every_sheet(self):
        from cadgen._internal.manufacturing.processes.brake import SHEETS

        found = [re.fullmatch(r"`([a-z0-9-]+)`", cells[0]) for cells in self._rows(SKILL / "references" / "sheet_metal.md", "## The sheets")]
        self.assertEqual([match.group(1) for match in found if match], list(SHEETS))


if __name__ == "__main__":
    unittest.main()
