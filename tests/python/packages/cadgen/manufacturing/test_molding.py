"""Injection molding (`"process": "molding"`): the study it reads, the plate formula, sink, warp and the checklist.

Benchmarks, each through the whole analysis on a part build123d writes into a temporary directory:

- the plate formula: a 2 mm ABS plate against a mould face held at the mould temperature (h far above a steel
  mould's) is ejectable everywhere within 8 % of t = s² / (π² α) ln((4/π) ΔT_melt / ΔT_eject), the formula for the
  plate's middle, at four elements across the wall; its whole-plate warp is a few microns;
- a 6 mm boss on a 2 mm plate stays hot more than four times as long as the plate: a sink or void, failing the check
  with what it measured and the fix (core it out to the nominal wall), and a section over ABS's wall range;
- a plate with a thick bar along one side bows toward the bar (its ends swing toward it, the bar's side concave),
  several times more than the uniform plate warps anywhere.

The molding reference stays in step with the resin table. Parse tests run everywhere; checks need the fea extra.
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import check_keeping, class_directory, needs_fea, read_study, value_error
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
BASE = {"process": "molding", "resin": "abs"}


def plate_step(directory: Path, name: str, *, bar: bool = False, boss: bool = False) -> Path:
    """A 2 mm plate in the +x +y +z octant: 12 x 12 alone; 16 x 16 with a 6 mm cube boss on its middle; or 30 x 8 with
    a 3 x 3 mm bar along its top's y = 5..8 edge."""
    from build123d import Align, Box, Pos, export_step

    low = (Align.MIN, Align.MIN, Align.MIN)
    if boss:
        shape = Box(16, 16, 2, align=low) + Pos(8, 8, 2) * Box(6, 6, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
    elif bar:
        shape = Box(30, 8, 2, align=low) + Pos(0, 5, 2) * Box(30, 3, 3, align=low)
    else:
        shape = Box(12, 12, 2, align=low)
    step = directory / f"{name}.step"
    export_step(shape, str(step))
    return step


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        return read_study({**BASE, **changes})

    def test_the_resin_sets_the_temperatures_and_the_study_overrides_them(self):
        study = self.parse()
        inputs = study.inputs
        self.assertEqual((inputs.resin.key, inputs.melt_C, inputs.mold_C, inputs.eject_C, inputs.h),
                         ("abs", 225.5, 54.5, 86.0, 2500.0))
        self.assertEqual((study.mesh_order, study.material, inputs.requires_anchor, inputs.warp_tolerance_mm),
                         (1, None, False, None))
        own = self.parse(resin="Nylon 66", melt_temperature_C=290, mold_temperature_C=80, ejection_temperature_C=170,
                         h_W_m2K=1500, warp_tolerance_mm=0.2).inputs
        self.assertEqual((own.resin.key, own.melt_C, own.mold_C, own.eject_C, own.h, own.warp_tolerance_mm),
                         ("pa66", 290.0, 80.0, 170.0, 1500.0, 0.2))
        self.assertEqual(self.parse(resin="PC/ABS").inputs.resin.key, "pc-abs")

    def test_the_errors_name_the_field(self):
        cases = [
            ({"resin": None}, "study.resin: the resin it is moulded in"),
            ({"resin": "unobtainium"}, "resin: 'unobtainium' is not a resin"),
            ({"mold_temperature_C": 90}, "mold_temperature_C: the mould at 90 °C is not below the ejection temperature"),
            ({"ejection_temperature_C": 40}, "ejection_temperature_C: the mould at 54.5 °C is not below"),
            ({"melt_temperature_C": 80}, "melt_temperature_C: the melt at 80 °C is not above the ejection temperature"),
            ({"resin": "pa66", "melt_temperature_C": 230}, "melt_temperature_C: 230 °C is not above where Nylon 66"),
            ({"h_W_m2K": 0}, "h_W_m2K: must be > 0"),
            ({"warp_tolerance_mm": "tight"}, "warp_tolerance_mm: expected a number"),
            ({"material": "abs"}, "study.material: a molding study names its plastic with 'resin'"),
            ({"parts": {"a": {"material": "abs"}}}, "study.parts: a molding study solves one part"),
            ({"mesh": {"order": 2}}, "study.mesh.order: molding studies take order 1"),
            ({"gate": "#o1.f1"}, "unknown keys ['gate']"),
        ]

        for changes, fragment in cases:
            document = {key: value for key, value in {**BASE, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))

    def test_the_plate_formula_is_the_handbooks_and_a_finite_contact_slows_it(self):
        from cadgen._internal.manufacturing.processes.resins import RESINS, diffusivity, linear_shrinkage, plate_cooling

        # A 2 mm wall, α = 0.1 mm²/s, melt 240 °C, mould 60 °C, ejection 90 °C: about 8 s to its middle.
        scale = 4.0 / (math.pi ** 2 * 0.1)
        self.assertAlmostEqual(plate_cooling(2, 0.1, 240, 60, 90, mean=False), scale * math.log(4 / math.pi * 6), places=9)
        self.assertAlmostEqual(plate_cooling(2, 0.1, 240, 60, 90, mean=True), scale * math.log(8 / math.pi ** 2 * 6), places=9)
        self.assertAlmostEqual(plate_cooling(2, 0.1, 240, 60, 90, mean=False, h=1e9, k=0.17),
                               plate_cooling(2, 0.1, 240, 60, 90, mean=False), places=4)
        self.assertGreater(plate_cooling(2, 0.1, 240, 60, 90, mean=False, h=2500, k=0.17),
                           1.1 * plate_cooling(2, 0.1, 240, 60, 90, mean=False))
        abs_ = RESINS["abs"]
        self.assertAlmostEqual(diffusivity(abs_), 0.17 / (1050 * 1400) * 1e6, places=12)
        # The thinnest wall shrinks at the range's low end; a section that stays hot four times as long, 3/4 of the way.
        self.assertEqual(linear_shrinkage(abs_, 0.5), 0.4)
        self.assertAlmostEqual(linear_shrinkage(abs_, 4.0), 0.4 + 0.75 * 0.3, places=12)


@needs_fea
class PlateFormula(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        study = {**BASE, "h_W_m2K": 1e6, "mesh": {"size_mm": 0.5}}
        cls.result, cls.solved = check_keeping(plate_step(directory, "plate"), study)

    def test_the_plate_is_ejectable_when_the_formula_for_its_middle_says(self):
        summary = self.result.summary
        hand = summary["hand_check"]
        self.assertAlmostEqual(hand["wall_mm"], 2.0, delta=0.05)
        self.assertAlmostEqual(summary["cooling_time_s"] / hand["centre_s"], 1.0, delta=0.08)
        # The handbook's mean (8/π²) comes first, the middle's (4/π) after it, a quarter later for these temperatures.
        self.assertLess(hand["mean_s"], 0.8 * hand["centre_s"])
        self.assertTrue(summary["ejectable"])
        self.assertLess(summary["energy_balance"], 1e-6)

    def test_the_checklist_passes_and_says_so(self):
        found = {f["type"]: f for f in self.result.findings}
        for kind in ("mesh_across_wall", "hand_check", "no_sink", "thinnest_wall", "thickest_wall", "melt_window",
                     "mold_window"):
            with self.subTest(kind=kind):
                self.assertEqual(found[kind]["severity"], "info")
                self.assertIn("limit", found[kind]["measured"])
        self.assertEqual(found["no_sink"]["measured"]["pass_when"], "below")
        verdict = self.result.verdict
        self.assertEqual((verdict["status"], verdict["errors"], verdict["warnings"], verdict["passed"]), ("ready", 0, 0, 7))
        self.assertTrue(verdict["headline"].startswith("Ready to mold · ejects in"), verdict["headline"])

    def test_a_uniform_plate_warps_by_microns(self):
        self.assertLess(self.result.summary["max_warp_mm"], 0.002)
        self.assertLess(self.result.summary["hold_reaction_share"], 1e-6)


@needs_fea
class Boss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.result, _ = check_keeping(plate_step(directory, "boss", boss=True), {**BASE, "mesh": {"size_mm": 0.67}})

    def test_a_thick_boss_on_a_thin_plate_is_a_sink_and_it_says_what_to_change(self):
        sinks = [f for f in self.result.findings if f["type"] in ("sink_void", "sink_risk")]
        self.assertEqual(len(sinks), 1, [f["type"] for f in self.result.findings])
        sink = sinks[0]
        self.assertEqual(sink["severity"], "error")
        x, y, z = sink["items"][0]["at"]
        self.assertTrue(5 <= x <= 11 and 5 <= y <= 11 and z >= 1, (x, y, z))
        self.assertEqual(sink["measured"]["pass_when"], "below")
        self.assertGreater(sink["measured"]["value"], sink["measured"]["limit"])
        self.assertEqual(sink["fix"]["action"], "thin")
        self.assertAlmostEqual(sink["fix"]["params"]["thickness_mm"], 2.0, delta=0.1)
        self.assertEqual(self.result.verdict["status"], "fix")
        for found in self.result.findings:
            if found["severity"] != "info":
                with self.subTest(kind=found["type"]):
                    self.assertLessEqual({"action", "summary", "where", "params"}, set(found["fix"]))

    def test_the_boss_is_over_the_walls_abs_takes(self):
        thick = next(f for f in self.result.findings if f["type"] == "thick_wall")
        self.assertAlmostEqual(thick["measured"]["value"], 6.0, delta=0.5)
        self.assertEqual(thick["fix"]["params"], {"thickness_mm": 3.56})


@needs_fea
class Warp(unittest.TestCase):
    def test_a_plate_with_one_thick_side_bows_toward_it(self):
        import numpy as np

        directory = class_directory(type(self))
        result, solved = check_keeping(plate_step(directory, "bar", bar=True),
                                       {**BASE, "mesh": {"size_mm": 0.67}, "warp_tolerance_mm": 0.001})
        nodes, u = solved.dof_locations, solved.fields["warp"]
        bottom = np.isclose(nodes[:, 2], 0.0) & (nodes[:, 1] < 4.0)

        def station(x: float) -> np.ndarray:
            near = bottom & (np.abs(nodes[:, 0] - x) < 1.0)
            self.assertTrue(near.any())
            return u[near].mean(axis=0)

        # The bar (on top, at the high-y edge) stays hot longest and shrinks most: the plate bows toward it, its ends
        # swinging toward +y against its middle (frame-free: a rigid move or turn of the whole cancels).
        swing = 0.5 * (station(0.5)[1] + station(29.5)[1]) - station(15.0)[1]
        self.assertGreater(swing, 0.005)
        over = next(f for f in result.findings if f["type"] == "warp_over_tolerance")
        self.assertEqual((over["severity"], over["measured"]["limit"], over["fix"]["action"]), ("error", 0.001, "thin"))
        # The warp's shrinkage scaling is cadgen's own model: the finding, the command's lines and the limits say so.
        self.assertIn("(an estimate)", over["summary"])
        self.assertIn("not a published law", over["description"])
        self.assertTrue(any("not a published law" in limit for limit in result.limits), result.limits)
        self.assertTrue(any("warp about" in line and "(an estimate)" in line for line in result.human_lines()))


class SkillDocs(unittest.TestCase):
    """The molding reference lists every resin."""

    def _rows(self, path: Path, heading: str) -> list[list[str]]:
        text = path.read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]

    def test_the_molding_reference_lists_every_resin(self):
        from cadgen._internal.manufacturing.processes.resins import RESINS

        resins = [re.fullmatch(r"`([a-z0-9-]+)`", cells[0]) for cells in self._rows(SKILL / "references" / "molding.md", "## The resins")]
        self.assertEqual([found.group(1) for found in resins if found], list(RESINS))


if __name__ == "__main__":
    unittest.main()
