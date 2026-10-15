"""Machining (`"process": "machining"`): the study it reads, Kienzle's force, the stability lobes, the cut on a part.

Hand checks, each a contract:

- Kienzle: a turning cut's force is k_c1.1 b h^(1 - m_c), and a milling cutter's thickest chip is f_z where it is
  engaged at 90°; the mean chip of a slot is 2 f_z / π;
- the stability lobes of one mode (k, ζ, ω_n) bottom out at Tlusty's b_lim = -1 / (2 K min Re G) = 2 k ζ (1 + ζ) / K,
  and its first stable pocket stands far above that, where the tooth passes at the mode's frequency;
- through the whole analysis on parts build123d writes into a temporary directory: a thin wall deflects far more than
  a block under the same cut, and fails with what it measured and the fix; a bar turned from the chuck deflects as a
  cantilever, P L³ / 3 E I, and rings at the Euler-Bernoulli frequency.

The machining reference lists every material. Parse tests run everywhere; checks need the fea extra.
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import (
    check, class_directory, glb_attribute_names, needs_fea, read_study, sidecar, value_error,
)
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
MILL = {"process": "machining", "material": "6061-t6", "operation": "milling", "tool": {"diameter_mm": 10, "flutes": 3},
        "spindle_rpm": 8000, "feed_per_tooth_mm": 0.05, "depth_mm": 3, "width_mm": 0.5,
        "cut_faces": ["#o1.f4"], "fixtures": [{"faces": ["#o1.f5"]}]}
TURN = {"process": "machining", "material": "1018", "operation": "turning", "spindle_rpm": 1200,
        "feed_per_tooth_mm": 0.1, "depth_mm": 1, "cut_faces": ["#o1.f1"], "fixtures": [{"faces": ["#o1.f3"]}]}


class StudyFile(unittest.TestCase):
    def parse(self, base=MILL, **changes):
        return read_study({**base, **changes})

    def test_a_milling_cut_reads_its_cutter_and_a_turning_cut_its_one_edge(self):
        study = self.parse()
        inputs = study.inputs
        self.assertEqual((inputs.operation, inputs.diameter_mm, inputs.flutes, inputs.teeth, inputs.milling),
                         ("milling", 10.0, 3, 3, "down"))
        self.assertEqual((inputs.tolerance_mm, inputs.tolerance_given, inputs.damping), (0.05, False, 0.02))
        self.assertEqual(inputs.face_refs, ("#o1.f4", "#o1.f5"))
        # The study's material is the workpiece's, its cutting force with it, and what the solver reads.
        self.assertEqual((study.material.name, study.material.kc11, study.material.mc), ("Aluminum 6061-T6", 800.0, 0.25))
        self.assertEqual((study.material.E, study.material.yield_strength), (68_900.0, 276.0))
        turned = self.parse(TURN).inputs
        self.assertEqual((turned.operation, turned.teeth, turned.material.key), ("turning", 1, "steel-1018"))
        own = self.parse(material={"name": "6061", "kc11_MPa": 750}, milling="climb", tolerance_mm=0.01,
                         damping_ratio=0.03).inputs
        self.assertEqual((own.material.kc11, own.material.group, own.milling, own.tolerance_mm, own.damping),
                         (750.0, "the study's own", "down", 0.01, 0.03))
        self.assertTrue(self.parse(material="Delrin").inputs.material.estimated)

    def test_the_errors_name_the_field(self):
        cases = [
            (MILL, {"spindle_rpm": 30000}, "spindle_rpm: 30000 rpm is past the spindle's 24000 rpm (max_spindle_rpm, "
                                           "24000 unless given)"),
            (MILL, {"max_spindle_rpm": 0}, "max_spindle_rpm: must be > 0"),
            (MILL, {"operation": None}, "study.operation: how it is cut, one of milling, turning"),
            (MILL, {"operation": "drilling"}, 'study.operation: how it is cut, one of milling, turning; got "drilling"'),
            (MILL, {"material": "unobtainium"}, "material: 'unobtainium' is not a material machining knows"),
            (MILL, {"material": {"name": "my alloy", "E_MPa": 70000}}, "material.nu: a material of its own needs"),
            (MILL, {"material": {"name": "6061", "colour": "red"}}, "material: unknown keys ['colour']"),
            (MILL, {"material": {"name": "6061", "mc": 1.5}}, "material.mc: Kienzle's exponent"),
            (MILL, {"tool": None}, "study.tool: the milling cutter"),
            (MILL, {"tool": {"diameter_mm": 10}}, "tool.flutes: how many cutting edges"),
            (MILL, {"tool": {"diameter_mm": -1, "flutes": 2}}, "tool.diameter_mm: must be > 0"),
            (MILL, {"tool": {"diameter_mm": 10, "flutes": 2, "helix": 30}}, "tool: unknown keys ['helix']"),
            (MILL, {"spindle_rpm": None}, "study.spindle_rpm: the spindle speed"),
            (MILL, {"feed_per_tooth_mm": 0}, "feed_per_tooth_mm: must be > 0"),
            (MILL, {"depth_mm": "deep"}, "depth_mm: expected a number"),
            (MILL, {"width_mm": None}, "study.width_mm: the radial depth of cut"),
            (MILL, {"width_mm": 12}, "width_mm: 12 mm is wider than the 10 mm cutter"),
            (MILL, {"milling": "sideways"}, "milling: down (climb) or up (conventional)"),
            (MILL, {"cut_faces": []}, "cut_faces: 'faces' must be a non-empty list"),
            (MILL, {"cut_faces": ["#o1.f5"]}, "cut_faces: #o1.f5 is also a fixture"),
            (MILL, {"fixtures": None}, "study: 'fixtures' must list at least one"),
            (MILL, {"tolerance_mm": 0}, "tolerance_mm: must be > 0"),
            (MILL, {"damping_ratio": 1.5}, "damping_ratio: a share of critical damping"),
            (MILL, {"parts": {"a": {"material": "6061"}}}, "study.parts: a machining study cuts one part"),
            (MILL, {"view": {"checks": [{"kind": "stress"}]}}, 'view.checks[0].kind: "stress" is not a check'),
            (MILL, {"surface_speed": 100}, "unknown keys ['surface_speed']"),
            (TURN, {"tool": {"diameter_mm": 10, "flutes": 1}}, "tool: a turning study takes no tool"),
            (TURN, {"width_mm": 1}, "width_mm: a turning cut has none"),
        ]
        for base, changes, fragment in cases:
            document = {key: value for key, value in {**base, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))


class Kienzle(unittest.TestCase):
    def test_a_turning_cuts_force_is_kc11_b_h_to_the_one_minus_mc(self):
        from cadgen._internal.manufacturing.processes.cutting import lookup_work_material, turning_forces

        steel = lookup_work_material("1018")
        forces = turning_forces(steel, depth_mm=2.0, feed_mm=0.2)
        by_hand = 1350.0 * 2.0 * 0.2 ** (1 - 0.21)          # 757 N: k_c1.1 b h^(1 - m_c)
        self.assertAlmostEqual(forces["tangential_N"], by_hand, places=9)
        self.assertAlmostEqual(forces["kc_MPa"], 1350.0 * 0.2 ** -0.21, places=9)
        self.assertAlmostEqual(forces["normal_N"], 0.3 * by_hand, places=9)

    def test_a_milling_teeth_chips_are_fz_sin_phi_and_a_slots_mean_chip_is_2_fz_over_pi(self):
        from cadgen._internal.manufacturing.processes.cutting import lookup_work_material, mean_chip_mm, milling_forces

        aluminium = lookup_work_material("6061")
        self.assertAlmostEqual(mean_chip_mm(0.1, 10.0, 10.0), 0.2 / math.pi, places=12)
        self.assertAlmostEqual(mean_chip_mm(0.1, 10.0, 5.0), 0.1 / (math.pi / 2), places=12)
        slot = milling_forces(aluminium, diameter_mm=10, flutes=1, depth_mm=4, width_mm=10, feed_mm=0.1, milling="down")
        # The thickest chip, f_z at 90°: one tooth's tangential force there.
        self.assertAlmostEqual(slot["tangential_N"], 800.0 * 4 * 0.1 ** 0.75, places=9)
        # Into the face it is that force, plus the radial force's share past 90°, and never the resultant's more.
        self.assertGreaterEqual(slot["normal_N"], slot["tangential_N"] * (1 - 1e-6))
        self.assertLessEqual(slot["normal_N"], slot["tangential_N"] * math.hypot(1, 0.3))


class Lobes(unittest.TestCase):
    """One mode, 1 kN/mm, 2 % damping, at 1 kHz, cut with K = 600 N/mm² by two teeth."""

    K, k, zeta, f_n, teeth = 600.0, 1000.0, 0.02, 1000.0, 2

    def lobes(self, rpm):
        import numpy as np

        from cadgen._internal.manufacturing.processes.cutting import stability

        w_n = 2 * math.pi * self.f_n
        omega = np.linspace(0.5 * w_n, 3 * w_n, 200_000)
        r = omega / w_n
        frf = 1.0 / (self.k * (1 - r ** 2 + 2j * self.zeta * r))
        return stability(omega, frf, self.K, self.teeth, rpm)

    def test_the_lowest_limit_is_tlustys_and_the_first_pocket_stands_far_above_it(self):
        import numpy as np

        tlusty = 2 * self.k * self.zeta * (1 + self.zeta) / self.K     # -1 / (2 K min Re G), min Re G = -1/(4kζ(1+ζ))
        rpm = np.geomspace(2_000, 60_000, 20_000)
        lobes = self.lobes(rpm)
        self.assertAlmostEqual(lobes.absolute_mm / tlusty, 1.0, delta=1e-4)
        # Every lobe bottoms out at it: the envelope's lowest, read on a grid of speeds, is it within 1 %.
        self.assertAlmostEqual(float(lobes.envelope_mm.min()) / tlusty, 1.0, delta=0.01)
        # The first pocket: the tooth passing at about the mode's frequency, 60 f_n / z rpm.
        pocket = 60 * self.f_n / self.teeth
        near = np.abs(rpm / pocket - 1) < 0.08
        self.assertGreater(float(lobes.envelope_mm[near].max()), 5 * tlusty)

    def test_a_chatter_fix_cuts_shallower_at_its_speed_and_offers_a_pocket_only_within_the_spindles_reach(self):
        import numpy as np

        from cadgen._internal.manufacturing.processes.machining import CHATTER_CLOSE, _chatter_fix

        # 9000 rpm, between lobes; the pockets, where the tooth passes at the mode's frequency over a whole number, are
        # at 15 000 and 30 000 rpm.
        rpm = np.unique(np.concatenate([np.geomspace(3_000, 60_000, 8_000), [9_000.0]]))
        lobes = self.lobes(rpm)
        limit = float(lobes.envelope_mm[np.searchsorted(lobes.rpm, 9_000.0)])

        def fix(**study):
            cut = read_study({**MILL, "spindle_rpm": 9000, "depth_mm": round(3 * limit, 4), **study}).inputs
            return cut, _chatter_fix(lobes, cut, limit, [0, 0, 0])

        cut, first = fix()
        self.assertEqual(cut.max_spindle_rpm, 24_000.0)                  # a common VMC spindle when the study says none
        # The fix is the depth that is stable at its own speed; a pocket the spindle reaches is the alternative.
        self.assertEqual(first["action"], "reduce_depth")
        self.assertLessEqual(first["params"]["depth_mm"], CHATTER_CLOSE * limit)
        [speed] = first["alternatives"]
        self.assertEqual(speed["action"], "change_speed")
        self.assertTrue(14_000 < speed["params"]["spindle_rpm"] <= 24_000, speed)
        # A spindle that reaches no pocket gets the depth alone, never a speed it cannot turn.
        _, slow = fix(max_spindle_rpm=10_000)
        self.assertEqual((slow["action"], slow.get("alternatives")), ("reduce_depth", None))


def wall_and_block(directory: Path) -> tuple[Path, Path]:
    """A 2 mm wall 15 mm tall on a 20 x 12 x 6 mm base, and a solid block of the same outline."""
    from build123d import Align, Box, Pos, export_step

    low = (Align.MIN, Align.MIN, Align.MIN)
    wall, block = directory / "wall.step", directory / "block.step"
    export_step(Box(20, 12, 6, align=low) + Pos(0, 5, 6) * Box(20, 2, 15, align=low), str(wall))
    export_step(Box(20, 12, 21, align=low), str(block))
    return wall, block


def cut_and_held(step: Path) -> tuple[str, str]:
    """The +y face the cutter is on (the wall's, above the base) and the bottom the vise holds."""
    from cadgen import fea

    faces = fea.faces(step).faces
    side = next(f.ref for f in faces if f.normal and f.normal[1] > 0.99 and f.center_mm[2] > 6)
    bottom = next(f.ref for f in faces if f.normal and f.normal[2] < -0.99)
    return side, bottom


@needs_fea
class WallAndBlock(unittest.TestCase):
    """The same cut on a thin wall and on a block of its outline."""

    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.results = {}
        for step in wall_and_block(directory):
            side, bottom = cut_and_held(step)
            study = {**MILL, "cut_faces": [side], "fixtures": [{"faces": [bottom]}], "tolerance_mm": 0.02,
                     "mesh": {"size_mm": 2.5}}
            cls.results[step.stem] = check(step, study)

    def test_a_thick_block_deflects_far_less_than_a_thin_wall_under_the_same_cut(self):
        wall, block = self.results["wall"].summary, self.results["block"].summary
        self.assertEqual(wall["force_normal_N"], block["force_normal_N"])
        self.assertGreater(abs(wall["deflection_at_cut_mm"]), 20 * abs(block["deflection_at_cut_mm"]))
        self.assertAlmostEqual(wall["section_at_cut_mm"], 2.0, delta=0.2)
        # Every check says so when it passes, with what it measured: the verdict counts those.
        block = self.results["block"]
        passed = {f["type"] for f in block.findings if f["severity"] == "info" and f.get("measured")}
        self.assertEqual(passed, {"deflection_within_tolerance", "clamp_stress_ok", "chatter_stable"})
        self.assertEqual((block.verdict["status"], block.verdict["passed"]), ("ready", 3))
        self.assertTrue(block.verdict["headline"].startswith("Ready to cut · "), block.verdict)

    def test_the_thin_wall_fails_with_what_it_measured_and_the_fix(self):
        result = self.results["wall"]
        self.assertEqual(result.verdict["status"], "fix")
        over = next(f for f in result.findings if f["type"] == "deflection_over_tolerance")
        self.assertEqual(over["severity"], "error")
        self.assertGreater(over["measured"]["value"], over["measured"]["limit"])
        self.assertEqual((over["measured"]["units"], over["measured"]["pass_when"], over["fix"]["action"]),
                         ("mm", "below", "reduce_depth"))
        self.assertLess(over["fix"]["params"]["depth_mm"], MILL["depth_mm"])
        thin = next(f for f in result.findings if f["type"] == "thin_wall_too_flexible")
        self.assertEqual(thin["fix"]["action"], "thicken")
        self.assertGreater(thin["fix"]["params"]["thickness_mm"], 2.0)
        for found in (f for f in result.findings if f["severity"] != "info"):
            with self.subTest(finding=found["type"]):
                self.assertLessEqual({"action", "summary", "where", "params"}, set(found["fix"]))
                self.assertTrue(found["measured"]["quantity"])

    def test_it_writes_the_lobes_the_mode_it_rings_in_and_its_limits(self):
        result = self.results["wall"]
        written = sidecar(result)
        lobes = written["curves"]["stability_lobes"]
        self.assertEqual((lobes["x_unit"], lobes["y_unit"]), ("rpm", "mm"))
        self.assertIn(MILL["spindle_rpm"], lobes["x"])
        self.assertEqual(len(lobes["x"]), len(lobes["y"]))
        self.assertTrue(written["limits"] and written["analysis"] == "machining")
        self.assertIn("_MODE_SHAPE", glb_attribute_names(result.glb))
        chatter = result.summary["chatter"]
        self.assertLessEqual(chatter["absolute_limit_mm"], chatter["limit_mm"])


@needs_fea
class TurnedBar(unittest.TestCase):
    """A 12 mm steel bar 60 mm out of the chuck, turned at its free end."""

    d, L = 12.0, 60.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Cylinder, Rotation, export_step

        from cadgen import fea

        directory = class_directory(cls)
        step = directory / "bar.step"
        export_step(Rotation(0, 90, 0) * Cylinder(cls.d / 2, cls.L, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(step))
        faces = fea.faces(step).faces
        chuck = next(f.ref for f in faces if f.normal and f.normal[0] < -0.99)
        od = next(f.ref for f in faces if f.surface != "plane")
        cls.result = check(step, {**TURN, "cut_faces": [od], "fixtures": [{"faces": [chuck]}], "mesh": {"size_mm": 2.0}})

    def test_it_deflects_as_a_cantilever_and_rings_at_euler_bernoullis_frequency(self):
        summary = self.result.summary
        E, I, rho = 205_000.0, math.pi * self.d ** 4 / 64, 7.87e-9
        reach = summary["cut_at_mm"][0]
        self.assertGreater(reach, self.L - 1e-6)                        # put at the free end, where it gives most
        cantilever = abs(summary["force_normal_N"]) * self.L ** 3 / (3 * E * I)
        self.assertAlmostEqual(abs(summary["deflection_at_cut_mm"]) / cantilever, 1.0, delta=0.1)
        first = 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * I / (rho * math.pi * self.d ** 2 / 4 * self.L ** 4))
        self.assertAlmostEqual(summary["modes"][0]["frequency_Hz"] / first, 1.0, delta=0.05)
        hand = next(f for f in self.result.findings if f["type"] == "hand_check")
        ratio = float(re.search(r"\(([0-9.]+) times\)", hand["summary"]).group(1))
        self.assertAlmostEqual(ratio, 1.0, delta=0.1)


class SkillDocs(unittest.TestCase):
    def test_the_machining_reference_lists_every_material(self):
        from cadgen._internal.manufacturing.processes.cutting import WORK_MATERIALS

        reference = (SKILL / "references" / "machining.md").read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", reference.split("## The materials", 1)[1], maxsplit=1)[0]
        listed = re.findall(r"^\| `([a-z0-9-]+)` \|", section, re.M)
        self.assertEqual(listed, list(WORK_MATERIALS))


if __name__ == "__main__":
    unittest.main()
