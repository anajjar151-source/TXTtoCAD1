"""Casting (`"process": "casting"`): the study it reads, Chvorinov's rule, where shrinkage collects, the latent heat.

Benchmarks, each through the whole analysis on a part build123d writes into a temporary directory:

- Chvorinov's rule: two cubes of A356 in sand, one twice the other, meshed alike; doubling the modulus V/A
  quadruples the freezing time (t = B (V/A)², an insulating mould's own law) within 10 %, and each is within 15 % of
  the rule's B (V/A)²;
- a thin fin freezes, through its whole length, before the block it hangs from has started to freeze at its core,
  and the thinnest section reads the fin's 3 mm;
- a thick boss on a thin bar is an isolated hot spot when the feeder is at the bar's end, an error whose fix is a feeder
  on the boss's top, and none when the boss's own top is the feeder, insulated or held hot (the hold puts its heat in,
  and lets go): fed there the casting is ready; fed from the end it fails `--fail-on error` and the command exits 3,
  its lines ending on the checklist and the verdict;
- energy: every joule the metal gave up (its sensible heat and all of its latent heat) left through the mould.

The casting reference stays in step with the tables. Parse tests run everywhere; checks need the fea extra.
"""

from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.python.support.fea_fixtures import (
    box_step, check, check_keeping, class_directory, needs_fea, quiet, read_study, value_error,
)
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
BASE = {"process": "casting", "alloy": "a356", "mold": "sand"}


def bar_with_boss(directory: Path) -> Path:
    """An 80 x 10 x 6 mm bar along x with a 16 mm cube boss standing on it at x = 50."""
    from build123d import Align, Box, Pos, export_step

    bar = Box(80, 10, 6, align=(Align.MIN, Align.CENTER, Align.MIN))
    boss = Pos(50, 0, 0) * Box(16, 16, 16, align=(Align.CENTER, Align.CENTER, Align.MIN))
    step = directory / "bossbar.step"
    export_step(bar + boss, str(step))
    return step


def block_with_fin(directory: Path) -> Path:
    """A 20 mm cube in the +x +y +z octant with a 15 x 3 x 16 mm fin out of its x = 20 face."""
    from build123d import Align, Box, Pos, export_step

    low = (Align.MIN, Align.MIN, Align.MIN)
    fin = Pos(20, 8.5, 2) * Box(15, 3, 16, align=low)
    step = directory / "fin.step"
    export_step(Box(20, 20, 20, align=low) + fin, str(step))
    return step


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        return read_study({**BASE, **changes})

    def test_the_mould_sets_the_pour_and_its_temperature_and_the_study_overrides_them(self):
        study = self.parse()
        inputs = study.inputs
        self.assertEqual((inputs.alloy.key, inputs.mold.key, inputs.pour_C, inputs.mold_C), ("a356", "sand", 715.0, 25.0))
        self.assertEqual((study.mesh_order, study.material, inputs.requires_anchor), (1, None, False))
        own = self.parse(alloy="Sterling", mold="investment", pour_temperature_C=980, mold_temperature_C=500,
                         feeders=[{"faces": ["#o1.f3"]}, {"faces": ["#o1.f4"], "h_W_m2K": 40},
                                  {"faces": ["#o1.f5"], "held_C": 1000}]).inputs
        self.assertEqual((own.alloy.key, own.pour_C, own.mold_C), ("sterling-silver-925", 980.0, 500.0))
        self.assertEqual([(f.faces, f.h, f.held_C) for f in own.feeders],
                         [(("#o1.f3",), 0.0, None), (("#o1.f4",), 40.0, None), (("#o1.f5",), 0.0, 1000.0)])
        self.assertEqual(own.face_refs, ("#o1.f3", "#o1.f4", "#o1.f5"))

    def test_the_errors_name_the_field(self):
        cases = [
            ({"alloy": None}, "study.alloy: the casting alloy"),
            ({"alloy": "unobtainium"}, "alloy: 'unobtainium' is not a casting alloy"),
            ({"mold": None}, "study.mold: the mould it is cast in"),
            ({"mold": "3d print"}, "mold: \"3d print\" is not a casting mould"),
            ({"pour_temperature_C": 600}, "pour_temperature_C: 600 °C is not above the liquidus"),
            ({"mold_temperature_C": 560}, "mold_temperature_C: 560 °C is not below the solidus"),
            ({"mold": "investment"}, "mold_temperature_C: the investment preset's mould (600 °C)"),
            ({"h_W_m2K": -5}, "h_W_m2K: must be > 0"),
            ({"feeders": [{"faces": ["#o1.f1"], "riser": True}]}, "feeders[0]: unknown keys ['riser']"),
            ({"feeders": [{"faces": ["#o1.f1"], "h_W_m2K": 5, "held_C": 700}]}, "feeders[0]: give h_W_m2K or held_C"),
            ({"feeders": [{"faces": ["#o1.f1"], "held_C": 500}]}, "feeders[0].held_C: 500 °C is not above the solidus"),
            ({"feeders": [{"faces": ["#o1.f1"]}, {"faces": ["#o1.f1"]}]}, "feeders[1]: #o1.f1 is already a feeder"),
            ({"fill_time_s": 0}, "fill_time_s: must be > 0"),
            ({"duration_s": "long"}, "duration_s: expected a number"),
            ({"material": "steel"}, "study.material: a casting study names its metal with 'alloy'"),
            ({"parts": {"a": {"material": "steel"}}}, "study.parts: a casting study solves one part"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "view.checks[0].kind: \"stress\" is not a check"),
            ({"mesh": {"order": 2}}, "study.mesh.order: casting studies take order 1"),
            ({"gate": "#o1.f1"}, "unknown keys ['gate']"),
        ]
        for changes, fragment in cases:
            document = {key: value for key, value in {**BASE, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))

    def test_an_insulating_moulds_coefficient_falls_as_it_heats_and_passes_its_heat_over_any_step(self):
        import math

        from cadgen._internal.manufacturing.processes.foundry import lookup_mold, mould_h

        sand, die = lookup_mold("sand"), lookup_mold("die")
        self.assertEqual(mould_h(die.h, die.effusivity, 0.0, 10.0), 5000.0)
        # e / √(π t) integrated over [0, t] is 2 e √(t / π): one step from the pour passes what any split of it does.
        whole = mould_h(sand.h, sand.effusivity, 0.0, 100.0) * 100.0
        halves = mould_h(sand.h, sand.effusivity, 0.0, 50.0) * 50.0 + mould_h(sand.h, sand.effusivity, 50.0, 100.0) * 50.0
        self.assertAlmostEqual(whole, 2.0 * 1000.0 * math.sqrt(100.0 / math.pi), places=9)
        self.assertAlmostEqual(whole, halves, places=9)


def freeze_ratio(directory: Path, side: float) -> tuple[float, float]:
    """(the simulated freezing time, Chvorinov's) of an A356 cube in sand meshed at an eighth of its side."""
    step = box_step(directory, f"cube{side:g}", (side, side, side), "corner")
    result = check(step, {**BASE, "mesh": {"size_mm": side / 8}})
    return result.summary["solidification_time_s"], result.summary["hand_check"]["estimate_s"]


@needs_fea
class Chvorinov(unittest.TestCase):
    def test_doubling_the_modulus_quadruples_the_freezing_time(self):
        directory = class_directory(type(self))
        (small, small_hand), (large, large_hand) = freeze_ratio(directory, 15.0), freeze_ratio(directory, 30.0)
        self.assertAlmostEqual(large / small, 4.0, delta=0.4)
        for simulated, hand in ((small, small_hand), (large, large_hand)):
            with self.subTest(hand=hand):
                self.assertAlmostEqual(simulated / hand, 1.0, delta=0.15)


@needs_fea
class FinAndBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.result, cls.solved = check_keeping(block_with_fin(directory), {**BASE, "mesh": {"size_mm": 2.0}})

    def test_the_fin_is_solid_before_the_blocks_core_starts_to_freeze(self):
        import numpy as np

        nodes, freeze = self.solved.dof_locations, self.solved.fields["solidification_time"]
        fin = nodes[:, 0] > 25.0                                       # 5 mm and more out from the block
        core = np.linalg.norm(nodes - 10.0, axis=1) < 4.0
        self.assertTrue(fin.any() and core.any())
        self.assertLess(freeze[fin].max(), freeze[core].min())
        self.assertLess(self.result.summary["last_to_freeze_at_mm"][0], 20.0)     # in the block

    def test_the_thinnest_section_is_the_fins_and_it_says_when_it_froze(self):
        summary = self.result.summary
        self.assertAlmostEqual(summary["thinnest_section_mm"], 3.0, delta=0.3)
        thinnest = next(f for f in self.result.findings if f["type"] == "thinnest_section")
        self.assertEqual(thinnest["severity"], "info")
        self.assertIn("well after the mould fills", thinnest["summary"])
        self.assertGreater(thinnest["measured"]["value"], thinnest["measured"]["limit"])     # a pass, and what it measured
        self.assertTrue(summary["fill_time_estimated"])

    def test_a_fill_slower_than_the_fin_freezes_is_a_misrun(self):
        directory = class_directory(type(self))
        step = block_with_fin(directory)
        slow = check(step, {**BASE, "mesh": {"size_mm": 2.0}, "fill_time_s": 30})
        misrun = next(f for f in slow.findings if f["type"] == "misrun")
        self.assertEqual(misrun["severity"], "error")
        self.assertGreater(misrun["items"][0]["at"][0], 20.0)          # in the fin
        self.assertTrue(misrun["summary"].startswith("A 3 mm section"), misrun["summary"])
        self.assertEqual((misrun["measured"]["limit"], misrun["measured"]["pass_when"]), (30.0, "above"))
        # Thicken the fin to stay liquid three times the fill, by Chvorinov's rule scaled to it; or preheat, or gate.
        fix = misrun["fix"]
        self.assertEqual((fix["action"], fix["where"]), ("thicken", [misrun["items"][0]["ref"]]))
        self.assertGreater(fix["params"]["thickness_mm"], 3.0)
        self.assertEqual(fix["alternatives"][-1]["action"], "move_gate")


@needs_fea
class Feeding(unittest.TestCase):
    """A thick boss on a thin bar freezes after the bar around it: fed from the bar's end it is cut off, and the fix
    names its top to feed; fed on its own top it is not, and the casting is ready."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea
        from cadgen.cli.manufacturing_check import main

        directory = class_directory(cls)
        step = bar_with_boss(directory)
        faces = fea.faces(step).faces
        end = next(face.ref for face in faces if face.normal and face.normal[0] < -0.99)
        top = next(face.ref for face in faces if face.normal and face.normal[2] > 0.99 and face.center_mm[2] > 15)
        study = {**BASE, "mesh": {"size_mm": 2.0}}
        cls.top_faces = [top]
        # Fed from the end through the command an agent runs, its study beside the part as the skill names it, gated as
        # CI gates it: its exit code, its lines, and the sidecar beside the part it reads the fixes from.
        cls.study_file = directory / "bossbar.casting.json"
        cls.study_file.write_text(json.dumps({**study, "feeders": [{"faces": [end]}]}), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), quiet():
            cls.end_code = main([str(step), "--study", str(cls.study_file), "--fail-on", "error"])
        cls.end_lines = out.getvalue().splitlines()
        cls.from_end = json.loads((directory / "bossbar.casting.result.json").read_text(encoding="utf-8"))
        cls.from_top = check(step, {**study, "feeders": [{"faces": [top]}]})

    def test_the_boss_is_an_isolated_hot_spot_when_fed_from_the_bars_end(self):
        spots = [f for f in self.from_end["findings"] if f["type"] == "shrinkage_hot_spot"]
        self.assertEqual(len(spots), 1)
        self.assertEqual(spots[0]["severity"], "error")
        x, y, z = spots[0]["items"][0]["at"]
        self.assertTrue(42 <= x <= 58 and abs(y) <= 8 and 6 <= z <= 16, (x, y, z))
        spot = self.from_end["summary"]["hot_spots"][0]
        self.assertLess(spot["cut_off_at_s"], spot["freezes_at_s"])
        self.assertGreater(spot["volume_mm3"], 0.5 * 16 ** 3)          # the boss, at least half of it, still liquid

    def test_fed_from_the_end_it_fails_its_gate_and_the_fix_is_a_riser_on_the_boss_top(self):
        # It ran and wrote its result beside the study, never over it, and the error fails --fail-on error: exit 3, as a
        # failing CI check, never 1.
        self.assertEqual(self.end_code, 3)
        self.assertEqual(json.loads(self.study_file.read_text(encoding="utf-8"))["process"], "casting")
        verdict = self.from_end["verdict"]
        self.assertEqual((verdict["status"], verdict["errors"], verdict["headline"]), ("fix", 1, "1 to fix · shrinkage hot spot"))
        spot = next(f for f in self.from_end["findings"] if f["type"] == "shrinkage_hot_spot")
        self.assertEqual(spot["measured"]["pass_when"], "below")
        self.assertGreater(spot["measured"]["value"], spot["measured"]["limit"])
        fix = spot["fix"]
        self.assertEqual((fix["action"], fix["where"]), ("add_feeder", self.top_faces))
        params = fix["params"]
        self.assertAlmostEqual(params["riser_modulus_mm"], 1.2 * params["hot_spot_modulus_mm"], delta=0.01)
        self.assertEqual([other["action"] for other in fix["alternatives"]], ["thin", "add_chill"])
        # The command's lines end on the checklist, the failure first and naming the face to feed, then the verdict.
        checks = [line for line in self.end_lines if line[:4] in ("FAIL", "WARN", "PASS")]
        self.assertTrue(checks[0].startswith("FAIL  shrinkage_hot_spot  liquid cut off: "), checks)
        self.assertIn(f"fix: Feed it from {self.top_faces[0]}: a riser of modulus", checks[0])
        self.assertTrue(self.end_lines[-1].startswith("Verdict: 1 to fix · shrinkage hot spot · 1 failed, "), self.end_lines[-1])
        self.assertTrue(self.end_lines[-1].endswith("; fails --fail-on error"), self.end_lines[-1])

    def test_a_feeder_on_the_boss_feeds_it(self):
        self.assertEqual([f for f in self.from_top.findings if f["type"] == "shrinkage_hot_spot"], [])
        self.assertEqual(self.from_top.summary["hot_spots"], [])
        # Fed where the fix said, it is ready to cast, and says so check by check.
        self.assertEqual(self.from_top.verdict["status"], "ready")
        fed = next(f for f in self.from_top.findings if f["type"] == "no_hot_spot")
        self.assertLess(fed["measured"]["value"], fed["measured"]["limit"])
        lines = self.from_top.human_lines()
        self.assertTrue(any(line.startswith("PASS  no_hot_spot") for line in lines), lines)
        self.assertTrue(lines[-1].startswith("Verdict: Ready to cast · solid in "), lines[-1])

    def test_a_riser_held_hot_feeds_it_puts_its_heat_in_and_lets_go(self):
        directory = class_directory(type(self))
        study = {**BASE, "mesh": {"size_mm": 2.0}, "feeders": [{"faces": self.top_faces, "held_C": 720}]}
        held = check(bar_with_boss(directory), study)
        summary = held.summary
        self.assertTrue(summary["fully_solid"], held.findings)
        self.assertEqual(summary["hot_spots"], [])
        self.assertGreater(summary["heat_from_held_feeders_J"], 0.0)
        self.assertLess(summary["energy_balance"], 1e-6)
        # Its heat keeps the casting liquid longer than the same face insulated; held at most 1.44 times Chvorinov's
        # time, it lets go and freezes too, last, under the riser: inside the held face's 16 mm square, in the upper
        # half of the 16 mm boss.
        self.assertGreater(summary["solidification_time_s"], self.from_top.summary["solidification_time_s"])
        self.assertGreater(summary["solidification_time_s"], 1.44 * summary["hand_check"]["estimate_s"])
        x, y, z = summary["last_to_freeze_at_mm"]
        self.assertTrue(42 <= x <= 58 and abs(y) <= 8 and 8 <= z <= 16, summary["last_to_freeze_at_mm"])


@needs_fea
class LatentHeat(unittest.TestCase):
    def test_the_heat_to_the_mould_is_the_metals_sensible_heat_and_all_its_latent_heat(self):
        from cadgen._internal.manufacturing.processes import solidification
        from cadgen._internal.manufacturing.processes.foundry import lookup_alloy

        directory = class_directory(type(self))
        step = box_step(directory, "cube", (12.0, 12.0, 12.0), "corner")
        result, solved = check_keeping(step, {**BASE, "mesh": {"size_mm": 2.0}})
        run = solved.scalars["run"]
        m = solved.scalars["node_volumes"]
        enthalpy = solidification.Enthalpy.of(lookup_alloy("a356"))
        self.assertTrue(run.solid)
        sensible = float(m @ (enthalpy.rho_c * (715.0 - run.final)))
        latent = enthalpy.rho_L * float(m.sum())
        self.assertAlmostEqual(run.heat_out / (sensible + latent), 1.0, delta=1e-6)
        self.assertLess(result.summary["energy_balance"], 1e-6)
        self.assertAlmostEqual(result.summary["heat_to_mould_J"], result.summary["heat_released_J"], delta=1e-3)


class SkillDocs(unittest.TestCase):
    """The casting reference says what the tables say."""

    def _rows(self, path: Path, heading: str) -> list[list[str]]:
        text = path.read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]

    def test_the_casting_reference_lists_every_alloy_and_mould(self):
        from cadgen._internal.manufacturing.processes.foundry import ALLOYS, MOLDS

        alloys = [re.fullmatch(r"`([a-z0-9-]+)`", cells[0]) for cells in self._rows(SKILL / "references" / "casting.md", "## The alloys")]
        self.assertEqual([found.group(1) for found in alloys if found], list(ALLOYS))
        molds = [re.fullmatch(r"`([a-z_]+)`", cells[0]) for cells in self._rows(SKILL / "references" / "casting.md", "## The moulds")]
        self.assertEqual([found.group(1) for found in molds if found], list(MOLDS))


if __name__ == "__main__":
    unittest.main()
