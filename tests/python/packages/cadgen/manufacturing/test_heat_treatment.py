"""Heat treatment (`"process": "heat_treatment"`): the study it reads, hardening through the Jominy curve, the hand check.

Benchmarks, each through the whole analysis on a part build123d writes into a temporary directory:

- a thin bar of 1045 quenched in still water hardens through, while a thick one of the same steel and quench is hard
  at its surface and soft at its core;
- the thick bar's core is harder quenched in still water than in a slow oil;
- a plain round's centre cools at 700 °C, and from 800 to 500 °C, within 10 % of the exact series solution Grossmann's
  H rests on, and every joule the part gave up went to the bath;
- a surface under the study's target hardness is an error that says what it measured and how to fix it.

The heat-treatment reference stays in step with the tables. Parse tests run everywhere; checks need the fea extra.
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import box_step, check, class_directory, needs_fea, read_study, value_error
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
BASE = {"process": "heat_treatment", "steel": "1045", "quenchant": "still_water"}


def round_step(directory: Path, diameter: float, length: float) -> Path:
    """A plain round along x, centred on the origin."""
    from build123d import Align, Cylinder, Rotation, export_step

    step = directory / f"round{diameter:g}.step"
    export_step(Rotation(0, 90, 0) * Cylinder(diameter / 2, length, align=(Align.CENTER,) * 3), str(step))
    return step


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        return read_study({**BASE, **changes})

    def test_the_grade_and_quenchant_set_the_quench_and_the_study_overrides_them(self):
        study = self.parse()
        inputs = study.inputs
        self.assertEqual((inputs.grade.key, inputs.quenchant.key, inputs.austenitize_C, inputs.coefficient),
                         ("1045", "still_water", 845.0, 5000.0))
        self.assertEqual((study.mesh_order, study.material, inputs.requires_anchor, inputs.face_refs), (1, None, False, ()))
        own = self.parse(steel="AISI 4140", quenchant="water", austenitize_C=860, h_W_m2K=3000, target_hrc=50).inputs
        self.assertEqual((own.grade.key, own.quenchant.key, own.austenitize_C, own.coefficient, own.target_hrc),
                         ("4140", "still_water", 860.0, 3000.0, 50.0))

    def test_the_errors_name_the_field(self):
        cases = [
            ({"steel": None}, "study.steel: the steel grade"),
            ({"steel": "unobtainium"}, "steel: 'unobtainium' is not a steel grade"),
            ({"quenchant": None}, "study.quenchant: what it is quenched in"),
            ({"quenchant": "oil"}, "quenchant: \"oil\" is two quenchants here"),
            ({"quenchant": "honey"}, "quenchant: \"honey\" is not a quenchant"),
            ({"austenitize_C": 700}, "austenitize_C: 700 °C is not above the eutectoid"),
            ({"austenitize_C": "hot"}, "austenitize_C: expected a number"),
            ({"h_W_m2K": 0}, "h_W_m2K: must be > 0"),
            ({"target_hrc": 90}, "target_hrc: 90 is off the Rockwell C scale"),
            ({"material": "steel"}, "study.material: a heat treatment names its steel with 'steel'"),
            ({"parts": {"a": {"material": "steel"}}}, "study.parts: a heat treatment quenches one part"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "view.checks[0].kind: \"stress\" is not a check"),
            ({"mesh": {"order": 2}}, "study.mesh.order: heat_treatment studies take order 1"),
            ({"temper_C": 200}, "unknown keys ['temper_C']"),
        ]

        for changes, fragment in cases:
            document = {key: value for key, value in {**BASE, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))


class Hardenability(unittest.TestCase):
    def test_a_jominy_curve_starts_at_its_carbons_hardness_and_never_rises(self):
        from cadgen._internal.manufacturing.processes.hardening import GRADES, jominy_distance, jominy_rate

        for grade in GRADES.values():
            with self.subTest(grade=grade.key):
                values = [hrc for _, hrc in grade.jominy]
                self.assertEqual(values, sorted(values, reverse=True))
                self.assertGreaterEqual(min(values), 20.0)
        self.assertAlmostEqual(GRADES["4140"].hardest, 60 * math.sqrt(0.405) + 20, places=1)
        for distance in (2.0, 9.0, 30.0, 70.0):
            self.assertAlmostEqual(jominy_distance(jominy_rate(distance)), distance, places=6)


@needs_fea
class ThinAndThick(unittest.TestCase):
    """1045 is shallow hardening: a 10 mm bar hardens through in still water, a 30 mm one only at its skin."""

    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        thin = box_step(directory, "thin", (10.0, 10.0, 40.0))
        thick = box_step(directory, "thick", (30.0, 30.0, 60.0))
        cls.thin = check(thin, {**BASE, "mesh": {"size_mm": 2.0}})
        cls.water = check(thick, {**BASE, "mesh": {"size_mm": 3.5}, "target_hrc": 55})
        cls.oil = check(thick, {**BASE, "quenchant": "slow_oil", "mesh": {"size_mm": 3.5}})

    def test_a_thin_bar_hardens_through_and_a_thick_one_keeps_a_soft_core(self):
        thin, thick = self.thin.summary, self.water.summary
        self.assertGreater(thin["core_hrc"], 50.0)
        self.assertLess(thick["core_hrc"], 35.0)
        self.assertGreater(thick["surface_hrc"][1], 55.0)
        self.assertGreater(thin["core_hrc"] - thick["core_hrc"], 15.0)
        self.assertGreater(thin["cooling_rate_core_C_s"], 3 * thick["cooling_rate_core_C_s"])

    def test_a_faster_quench_hardens_the_core_more(self):
        self.assertGreater(self.water.summary["core_hrc"], self.oil.summary["core_hrc"] + 2.0)
        self.assertGreater(self.water.summary["cooling_rate_core_C_s"], self.oil.summary["cooling_rate_core_C_s"])

    def test_a_surface_under_the_target_fails_with_what_it_measured_and_the_fix(self):
        soft = next(f for f in self.water.findings if f["type"] == "soft_spot")
        self.assertEqual(soft["severity"], "error")
        self.assertEqual(set(soft["measured"]), {"quantity", "value", "limit", "units", "pass_when"})
        self.assertEqual((soft["measured"]["limit"], soft["measured"]["pass_when"]), (55.0, "above"))
        self.assertLess(soft["measured"]["value"], 55.0)
        self.assertIn(soft["fix"]["action"], {"change_material", "change_quenchant", "thin"})
        self.assertTrue(soft["fix"]["params"] and isinstance(soft["fix"]["where"][-1], list))   # its faces, then the point
        self.assertEqual(self.water.verdict["status"], "fix")
        self.assertTrue(self.oil.verdict["headline"].startswith("Ready to quench · core "), self.oil.verdict)
        # Every finding says what it is, and every error or warning that has a fix carries one.
        for found in self.water.findings:
            with self.subTest(finding=found["type"]):
                self.assertIn(found["severity"], {"error", "warning", "info"})
                if found["type"] in {"soft_spot", "crack_risk", "section_change"} and found["severity"] != "info":
                    self.assertIn("fix", found)


@needs_fea
class HandCheck(unittest.TestCase):
    def test_a_rounds_centre_cools_as_the_series_solution_says_and_its_heat_goes_to_the_bath(self):
        directory = class_directory(type(self))
        result = check(round_step(directory, 20.0, 60.0), {**BASE, "mesh": {"size_mm": 2.0}})
        hand = result.summary["hand_check"]
        self.assertEqual((hand["shape"], hand["dims_mm"]), ("round", [20.0, 60.0]))
        self.assertAlmostEqual(hand["simulated_rate_700_C_s"] / hand["centre_rate_700_C_s"], 1.0, delta=0.10)
        self.assertAlmostEqual(hand["simulated_t85_s"] / hand["centre_t85_s"], 1.0, delta=0.10)
        hand_check = next(f for f in result.findings if f["type"] == "hand_check")
        self.assertEqual(hand_check["severity"], "info")
        self.assertLess(result.summary["energy_balance"], 1e-9)
        # Grossmann's ideal critical diameter of 1045 is about an inch; a still-water quench hardens less.
        self.assertTrue(15.0 < hand["ideal_critical_diameter_mm"] < 35.0, hand)
        self.assertLess(hand["critical_diameter_mm"], hand["ideal_critical_diameter_mm"])


class SkillDocs(unittest.TestCase):
    """The heat-treatment reference lists what the tables hold."""

    def _rows(self, path: Path, heading: str) -> list[list[str]]:
        text = path.read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]

    def test_the_reference_lists_every_steel_and_quenchant(self):
        from cadgen._internal.manufacturing.processes.hardening import GRADES, QUENCHANTS

        page = SKILL / "references" / "heat-treatment.md"
        steels = [re.fullmatch(r"`([a-z0-9]+)`", cells[0]) for cells in self._rows(page, "## The steels")]
        self.assertEqual([found.group(1) for found in steels if found], list(GRADES))
        quenchants = [re.fullmatch(r"`([a-z_0-9]+)`", cells[0]) for cells in self._rows(page, "## The quenchants")]
        self.assertEqual([found.group(1) for found in quenchants if found], list(QUENCHANTS))


if __name__ == "__main__":
    unittest.main()
