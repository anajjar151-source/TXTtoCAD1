"""Welding (`"process": "welding"`): the study it reads, the classical relations, and a T joint's angular distortion.

Benchmarks, each through the whole analysis on a part build123d writes into a temporary directory:

- Satoh and Terasaki's relations as Nakatani gives them: continuous where they change form (to their published figures), the angle peaking near
  Q / h² = 10.6 J/mm³; the tendon force 0.2 kN per J/mm in steel; a fillet's heat shared 2 h_F / (2 h_F + h_W);
- a single-sided fillet weld on a steel T joint closes the joint on its own side, within a quarter of the empirical
  angular distortion, and the part bows along it as beam theory says;
- the same weld on both sides turns each side's joint less (the web stays square);
- a failing case says what it measured against the tolerance and carries the fix.

The welding reference stays in step with the tables. Parse tests run everywhere; checks need the fea extra.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import check, class_directory, needs_fea, read_study, value_error
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
WELD = {"faces": ["#o1.f3", "#o1.f8"], "process": "gmaw", "heat_input_kJ_mm": 1.0}
BASE = {"process": "welding", "alloy": "s235", "welds": [WELD]}
FIX_KEYS = {"action", "summary", "where", "params"}


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        return read_study({**BASE, **changes}).inputs

    def test_the_heat_input_is_given_or_made_from_the_arc_and_the_weld_takes_its_faces(self):
        inputs = self.parse()
        weld = inputs.welds[0]
        self.assertEqual((inputs.metal.key, weld.faces, weld.process.key, weld.heat_J_mm, weld.passes, weld.line),
                         ("s235", ("#o1.f3", "#o1.f8"), "gmaw", 1000.0, 1, None))
        self.assertEqual((inputs.face_refs, inputs.requires_anchor, inputs.fatigue_critical), (("#o1.f3", "#o1.f8"), False, False))
        arc = self.parse(welds=[{"faces": ["#o1.f3", "#o1.f8"], "process": "MIG", "volts": 24, "amps": 200,
                                 "travel_speed_mm_s": 5, "passes": 2, "thickness_mm": [10, 8], "label": "root"}]).welds[0]
        self.assertAlmostEqual(arc.heat_J_mm, 0.8 * 24 * 200 / 5)      # EN 1011-1's k for MIG/MAG, 0.8
        self.assertEqual((arc.passes, arc.thickness, arc.label), (2, (10.0, 8.0), "root"))
        tig = self.parse(welds=[{"faces": ["#o1.f3", "#o1.f8"], "process": "tig", "volts": 12, "amps": 120,
                                 "travel_speed_mm_s": 2}]).welds[0]
        self.assertAlmostEqual(tig.heat_J_mm, 0.6 * 12 * 120 / 2)
        laser = self.parse(welds=[{"faces": ["#o1.f3"], "line_mm": [[0, 0, 10], [0, 100, 10]], "process": "laser",
                                   "power_W": 3000, "travel_speed_mm_s": 20, "efficiency": 0.5}]).welds[0]
        self.assertEqual((laser.heat_J_mm, laser.line), (75.0, ((0.0, 0.0, 10.0), (0.0, 100.0, 10.0))))

    def test_the_errors_name_the_field(self):
        cases = [
            ({"alloy": None}, "study.alloy: the base metal"),
            ({"alloy": "mithril"}, "alloy: 'mithril' is not a base metal"),
            ({"material": "steel"}, "study.material: a welding study names its base metal with 'alloy'"),
            ({"welds": []}, "study.welds: the welds"),
            ({"welds": [{**WELD, "rod": 1}]}, "welds[0]: unknown keys ['rod']"),
            ({"welds": [{**WELD, "faces": ["#o1.f3"]}]}, "welds[0]: one face makes no edge"),
            ({"welds": [{**WELD, "faces": ["#o1.f1", "#o1.f2", "#o1.f3"]}]}, "welds[0].faces: at most two faces"),
            ({"welds": [{**WELD, "process": "brazing"}]}, 'welds[0].process: "brazing" is not a welding process'),
            ({"welds": [{"faces": WELD["faces"], "process": "gmaw"}]}, "welds[0]: give the heat one way"),
            ({"welds": [{**WELD, "volts": 24}]}, "welds[0]: give the heat one way"),
            ({"welds": [{**WELD, "heat_input_kJ_mm": 80}]}, "welds[0].heat_input_kJ_mm: 80 kJ/mm is not a weld's"),
            ({"welds": [{"faces": WELD["faces"], "process": "gmaw", "power_W": 2000, "travel_speed_mm_s": 5}]},
             "welds[0]: a gmaw weld takes volts, amps and travel_speed_mm_s, not power_W"),
            ({"welds": [{"faces": WELD["faces"], "process": "gmaw", "volts": 24, "amps": 200,
                         "travel_speed_mm_s": 5, "efficiency": 1.5}]}, "welds[0].efficiency: the share of the energy"),
            ({"welds": [{**WELD, "passes": 0}]}, "welds[0].passes: how many passes"),
            ({"welds": [{**WELD, "thickness_mm": [10, 8, 6]}]}, "welds[0].thickness_mm: one thickness, or one per face"),
            ({"welds": [{**WELD, "line_mm": [[0, 0, 0], [0, 0, 0]]}]}, "welds[0].line_mm: its two ends are the same point"),
            ({"fatigue_critical": "yes"}, "fatigue_critical: true or false"),
            ({"tolerance_mm": -1}, "tolerance_mm: must be > 0"),
        ]
        for changes, fragment in cases:
            document = {key: value for key, value in {**BASE, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))


class Relations(unittest.TestCase):
    def test_satoh_and_terasaki_are_continuous_and_peak_where_the_heat_reaches_through(self):
        from cadgen._internal.manufacturing.processes.weldments import METALS, angular_200, heat_shares, tendon_force_N, transverse_200

        steel = METALS["s235"]
        h = 10.0

        def heat(x):                                                   # the Q giving Q / h² = x
            return x * h * h

        for x in (6.27, 20.0):
            with self.subTest(x=x):
                below, above = (transverse_200(steel, heat(x * f), h, fillet=True) for f in (1 - 1e-9, 1 + 1e-9))
                self.assertAlmostEqual(below / above, 1.0, delta=0.005)     # to the published coefficients' figures
        self.assertAlmostEqual(angular_200(steel, heat(6.27 - 1e-9), h) / angular_200(steel, heat(6.27 + 1e-9), h), 1.0,
                               delta=0.005)
        peak = max((angular_200(steel, heat(x / 10), h), x / 10) for x in range(10, 400))
        self.assertAlmostEqual(peak[1], 10.6, delta=0.15)
        self.assertAlmostEqual(tendon_force_N(steel, 1000.0), 200_000.0)
        self.assertGreater(tendon_force_N(METALS["6061-t6"], 1000.0), 0.0)
        for share, expected in zip(heat_shares([10.0, 10.0]), (2 / 3, 1 / 3)):
            self.assertAlmostEqual(share, expected)
        self.assertEqual(heat_shares([6.0]), [1.0])


def t_joint(directory: Path) -> Path:
    """A 100 x 200 x 10 mm flange with a 10 mm web 80 mm tall standing on its middle, along y."""
    from build123d import Align, Box, Pos, export_step

    flange = Box(100, 200, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    web = Pos(0, 0, 10) * Box(10, 200, 80, align=(Align.CENTER, Align.CENTER, Align.MIN))
    step = directory / "tjoint.step"
    export_step(flange + web, str(step))
    return step


def joint_faces(step: Path) -> dict[str, str]:
    from cadgen import fea

    found = {}
    for face in fea.faces(step).faces:
        x, _, z = face.center_mm
        if face.normal == (0.0, 0.0, 1.0) and abs(z - 10) < 1e-6:
            found["top_left" if x < 0 else "top_right"] = face.ref
        elif face.normal and abs(abs(face.normal[0]) - 1) < 1e-9 and abs(abs(x) - 5) < 1e-6:
            found["web_left" if x < 0 else "web_right"] = face.ref
    return found


@needs_fea
class TJoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.directory = directory
        cls.step = t_joint(directory)
        faces = joint_faces(cls.step)
        cls.left = {"faces": [faces["top_left"], faces["web_left"]], "process": "gmaw", "heat_input_kJ_mm": 1.0}
        right = {"faces": [faces["top_right"], faces["web_right"]], "process": "gmaw", "heat_input_kJ_mm": 1.0}
        cls.study = {"process": "welding", "alloy": "s235", "mesh": {"size_mm": 5.0}}
        cls.single = check(cls.step, {**cls.study, "welds": [cls.left]})
        cls.double = check(cls.step, {**cls.study, "welds": [cls.left, right]})

    def test_a_single_fillet_closes_its_joint_within_a_quarter_of_satoh_and_terasaki(self):
        weld = self.single.summary["welds"][0]
        self.assertEqual(weld["joint"], "fillet")
        self.assertEqual([plate["thickness_mm"] for plate in weld["plates"]], [10.0, 10.0])
        self.assertGreater(weld["angle_deg"], 0.0)                      # it closes on the weld's own side
        self.assertAlmostEqual(weld["angle_deg"] / weld["angle_empirical_deg"], 1.0, delta=0.25)
        self.assertGreater(weld["plates"][0]["angle_deg"], 0.0)         # the flange's wing lifts toward the web
        hand = next(found for found in self.single.findings if found["type"] == "hand_check")
        self.assertEqual((hand["severity"], hand["measured"]["limit"]), ("info", 2.0))

    def test_the_part_bows_along_the_weld_as_beam_theory_says(self):
        weld = self.single.summary["welds"][0]
        self.assertGreater(weld["bow_mm"], 0.0)
        self.assertAlmostEqual(weld["bow_mm"] / weld["bow_beam_mm"], 1.0, delta=0.5)
        bowing = next(found for found in self.single.findings if found["type"] == "bowing")
        self.assertEqual(bowing["severity"], "info")

    def test_welding_both_sides_turns_each_joint_less(self):
        single = self.single.summary["welds"][0]["angle_deg"]
        both = [weld["angle_deg"] for weld in self.double.summary["welds"]]
        self.assertTrue(all(0.0 < angle < 0.85 * single for angle in both), (single, both))
        webs = [weld["plates"][1]["angle_deg"] for weld in self.double.summary["welds"]]
        self.assertTrue(all(abs(web) < 0.1 * single for web in webs), webs)   # the web stays square

    def test_a_failing_weld_carries_what_it_measured_and_the_fix(self):
        tight = check(self.step, {**self.study, "welds": [self.left], "tolerance_mm": 0.05, "fatigue_critical": True})
        distortion = next(found for found in tight.findings if found["type"] == "distortion")
        self.assertEqual(distortion["severity"], "error")
        self.assertEqual((distortion["measured"]["limit"], distortion["measured"]["units"]), (0.05, "mm"))
        self.assertGreater(distortion["measured"]["value"], 0.05)
        self.assertLessEqual(FIX_KEYS, set(distortion["fix"]))
        self.assertEqual(distortion["fix"]["action"], "reduce_heat_input")
        self.assertLess(distortion["fix"]["params"]["heat_input_kJ_mm"], 1.0)
        self.assertEqual([alt["action"] for alt in distortion["fix"]["alternatives"]][:2], ["balance_welds", "preset"])
        for found in tight.findings:
            if found["severity"] in ("error", "warning"):
                with self.subTest(kind=found["type"]):
                    self.assertLessEqual(FIX_KEYS, set(found["fix"]))
                    self.assertIn("measured", found)
        self.assertEqual(tight.verdict["status"], "fix")
        self.assertEqual(self.single.verdict["errors"], 1)              # 0.49 mm past ISO 2768-2 K's 0.4 mm


class SkillDocs(unittest.TestCase):
    """The welding reference lists what the tables hold."""

    def _rows(self, heading: str) -> list[list[str]]:
        text = (SKILL / "references" / "welding.md").read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]

    def test_the_reference_lists_every_base_metal_and_process(self):
        from cadgen._internal.manufacturing.processes.weldments import METALS, PROCESSES

        metals = [re.fullmatch(r"`([a-z0-9-]+)`", cells[0]) for cells in self._rows("## The base metals")]
        self.assertEqual([found.group(1) for found in metals if found], list(METALS))
        processes = [re.fullmatch(r"`([a-z_]+)`", cells[0]) for cells in self._rows("## The processes")]
        self.assertEqual([found.group(1) for found in processes if found], list(PROCESSES))


if __name__ == "__main__":
    unittest.main()
