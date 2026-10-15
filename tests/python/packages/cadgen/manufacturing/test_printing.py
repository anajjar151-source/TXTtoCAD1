"""3D printing (`"process": "printing"`): the study it reads, the shared inherent-strain method, warp and release.

Benchmarks, each through the whole analysis on a part build123d writes into a temporary directory:

- the method's hand check: a thin cantilever plate given a uniform inherent strain gradient g curls by beam theory,
  its tip rising g L² / 2, and a free plate bows g L² / 8 with no stress;
- a tall thin wall of 316L lifts more off the plate, once cut off, than a squat block of the same length;
- letting go of the plate changes the distortion, and the frames build the part band by band, then let it go;
- every check says what it measured, passes included, and a failing one carries the fix that makes it pass.

The printing reference stays in step with the tables. Parse tests run everywhere; checks need the fea extra.
"""

from __future__ import annotations

import re
import shutil
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import (
    box_step, box_volume, check, class_directory, needs_fea, read_study, value_error,
)
from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills" / "manufacturing-sim"
BASE = {"process": "printing", "technology": "powder_bed_metal", "alloy": "316l"}
FIX_KEYS = {"action", "summary", "where", "params"}


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        return read_study({key: value for key, value in {**BASE, **changes}.items() if value is not None}).inputs

    def test_the_technology_and_material_set_the_strain_and_the_study_overrides_it(self):
        inputs = self.parse()
        self.assertEqual((inputs.technology.key, inputs.material.key, inputs.direction, inputs.bands, inputs.release),
                         ("powder_bed_metal", "316l", (0.0, 0.0, 1.0), 12, True))
        self.assertAlmostEqual(inputs.in_plane, -480 / 193_000)
        self.assertEqual((inputs.along, inputs.given, inputs.layer_mm, inputs.requires_anchor), (0.0, False, 0.04, False))
        self.assertAlmostEqual(self.parse(alloy="Ti64").in_plane, -0.0056)
        fdm = self.parse(technology="fdm", polymer="ABS", alloy=None, chamber_temperature_C=45)
        self.assertAlmostEqual(fdm.in_plane, -90e-6 * (105 - 45))
        own = self.parse(inherent_strain={"in_plane": -0.002, "build": -0.0005}, build_direction=[0, 2, 0], bands=6,
                         release_from_plate=False, tolerance_mm=0.1)
        self.assertEqual((own.in_plane, own.along, own.given, own.direction, own.bands, own.release, own.tolerance_mm),
                         (-0.002, -0.0005, True, (0.0, 1.0, 0.0), 6, False, 0.1))

    def test_the_errors_name_the_field(self):
        cases = [
            ({"technology": None}, "study.technology: how it is printed"),
            ({"technology": "inkjet"}, 'technology: "inkjet" is not a printing technology'),
            ({"alloy": None}, "study.alloy: what it is printed in"),
            ({"alloy": "unobtainium"}, "alloy: 'unobtainium' is not a metal powder bed fusion material"),
            ({"polymer": "abs"}, "study.polymer: powder_bed_metal prints an alloy; name it with 'alloy'"),
            ({"technology": "fdm", "alloy": None, "polymer": "316l"}, "polymer: '316l' is not a fused filament"),
            ({"material": "steel"}, "study.material: a printing study names its material by the technology"),
            ({"parts": {"a": {}}}, "study.parts: a printing study solves one part"),
            ({"build_direction": [0, 0, 0]}, "build_direction: [0, 0, 0] points nowhere"),
            ({"build_direction": "up"}, "build_direction: the build direction as [x, y, z]"),
            ({"bands": 1}, "bands: how many height bands to build it in, 2 to 40"),
            ({"release_from_plate": "yes"}, "release_from_plate: true or false"),
            ({"tolerance_mm": 0}, "tolerance_mm: must be > 0"),
            ({"chamber_temperature_C": 40}, "chamber_temperature_C: FDM's alone"),
            ({"technology": "fdm", "alloy": None, "polymer": "pla", "chamber_temperature_C": 70},
             "chamber_temperature_C: 70 °C is not below where PLA sets (60 °C)"),
            ({"inherent_strain": {"in_plane": -0.2}}, "inherent_strain.in_plane: -0.2 is a strain of 20%"),
            ({"inherent_strain": {"shrink": 1}}, "inherent_strain: unknown keys ['shrink']"),
            ({"view": {"checks": [{"kind": "stress"}]}}, 'view.checks[0].kind: "stress" is not a check'),
            ({"plate": "#o1.f1"}, "unknown keys ['plate']"),
        ]
        for changes, fragment in cases:
            document = {key: value for key, value in {**BASE, **changes}.items() if value is not None}
            with self.subTest(changes=changes):
                self.assertIn(fragment, value_error(self, read_study, document))


@needs_fea
class InherentStrainMethod(unittest.TestCase):
    """The shared method against beam theory: a strain varying linearly through a plate's thickness, κ = g."""

    @classmethod
    def setUpClass(cls):
        import numpy as np

        from cadgen._internal.manufacturing.processes import inherent_strain
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.materials import Material

        cls.L, cls.w, cls.t, cls.g = 40.0, 4.0, 2.0, 1e-3
        cls.space = FemSpace.build(box_volume((cls.L, cls.w, cls.t), (20, 2, 2)), 2)
        cls.material = Material("steel", 200_000.0, 0.3, 250.0, 7.85e-9)
        X = inherent_strain.quadrature_points(cls.space)
        cls.strain = np.zeros((3, 3, *X.shape[1:]))
        cls.strain[0, 0] = -cls.g * (X[2] - cls.t / 2)              # shrinks most at the top: curls up

    def test_a_thin_cantilever_plate_curls_as_beam_theory_says(self):
        import numpy as np

        from cadgen._internal.manufacturing.processes import inherent_strain

        space = self.space
        clamp = inherent_strain.vector_dofs(space, np.flatnonzero(space.dof_locations[:, 0] < 1e-9))
        solved = inherent_strain.solve_once(space, self.material, self.strain, clamp)
        tip = space.dof_locations[:, 0] > self.L - 1e-9
        rise = float(space.nodal(solved.u)[tip, 2].mean())
        self.assertAlmostEqual(rise / (self.g * self.L ** 2 / 2), 1.0, delta=0.01)
        self.assertLess(float(np.abs(solved.stress).max()), 1e-6)      # a compatible strain: nothing stressed

    def test_a_free_plate_bows_with_no_stress_and_a_build_of_one_band_is_one_solve(self):
        import numpy as np

        from cadgen._internal.manufacturing.processes import inherent_strain

        space = self.space
        held = inherent_strain.hold_free(space)
        self.assertEqual(len(held), 6)
        solved = inherent_strain.solve_once(space, self.material, self.strain, held)
        shape = space.nodal(solved.u)
        shape -= inherent_strain.rigid_part(space.dof_locations, shape)
        self.assertAlmostEqual(float(np.ptp(shape[:, 2])) / (self.g * self.L ** 2 / 8), 1.0, delta=0.01)
        build = inherent_strain.Build(space, self.material)
        build.hold(held)
        build.add(np.arange(space.mesh.t.shape[1]), self.strain)
        self.assertTrue(np.allclose(build.u, solved.u, atol=1e-9))


def wall_and_block(directory: Path) -> tuple[Path, Path]:
    """A 40 x 3 x 30 mm wall and a 40 x 30 x 6 mm block, standing on z = 0."""
    return (box_step(directory, "wall", (40.0, 3.0, 30.0), "corner"),
            box_step(directory, "block", (40.0, 30.0, 6.0), "corner"))


@needs_fea
class TallAndSquat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.directory = directory
        cls.wall_step, block = wall_and_block(directory)
        study = {**BASE, "mesh": {"size_mm": 2.5}, "bands": 8}
        cls.wall = check(cls.wall_step, study)
        cls.block = check(block, study)
        # Its own copy: a check writes <stem>.printing.glb, and the released wall's frames are read below.
        held = shutil.copy(cls.wall_step, directory / "held.step")
        cls.held = check(Path(held), {**study, "release_from_plate": False})

    def test_a_tall_thin_wall_curls_and_lifts_more_than_a_squat_block(self):
        wall, block = self.wall.summary, self.block.summary
        self.assertGreater(wall["warp_mm"], 1.3 * block["warp_mm"])
        self.assertGreater(block["warp_mm"], 0.0)
        self.assertEqual(wall["warp_at_mm"][2], 0.0)                    # on the bottom, at an end
        self.assertTrue(wall["warp_at_mm"][0] <= 3.0 or wall["warp_at_mm"][0] >= 37.0, wall["warp_at_mm"])

    def test_release_from_the_plate_changes_the_distortion_and_the_frames_build_it(self):
        from tests.python.support.fea_fixtures import glb_array, glb_extras

        wall, held = self.wall.summary, self.held.summary
        self.assertTrue(wall["released"])
        self.assertFalse(held["released"])
        self.assertIsNone(held["warp_mm"])
        self.assertNotAlmostEqual(wall["max_distortion_mm"], held["max_distortion_mm"], places=4)
        series = glb_extras(self.wall.glb)["series"]
        self.assertEqual([frame["label"] for frame in series["frames"]][-1], "Off the plate")
        self.assertEqual((len(series["frames"]), series["default"]), (9, 8))
        printed = [glb_array(self.wall.glb, frame["attributes"]["printed"]) for frame in series["frames"][:-1]]
        shares = [float(values.mean()) for values in printed]
        self.assertEqual(shares, sorted(shares))                        # it grows band by band
        self.assertLess(shares[0], 0.3)
        self.assertEqual(shares[-1], 1.0)

    def test_every_check_says_what_it_measured_and_the_hand_check_passes(self):
        for result in (self.wall, self.block, self.held):
            for found in result.findings:
                with self.subTest(kind=found["type"]):
                    if found["severity"] in ("error", "warning"):
                        self.assertLessEqual(FIX_KEYS, set(found["fix"]))
                        self.assertIn("measured", found)
        kinds = {found["type"]: found for found in self.block.findings}
        for kind in ("warp", "release_distortion", "residual_stress", "recoater_collision", "hand_check"):
            with self.subTest(check=kind):
                self.assertIn("measured", kinds[kind])
        self.assertEqual(kinds["hand_check"]["severity"], "info")
        self.assertLess(kinds["hand_check"]["measured"]["value"], 2.0)
        self.assertEqual(kinds["residual_stress"]["severity"], "warning")  # linear 316L passes its yield

    def test_a_failing_print_carries_what_it_measured_and_the_fix(self):
        tight = check(self.wall_step, {**BASE, "mesh": {"size_mm": 2.5}, "bands": 8, "tolerance_mm": 0.01})
        warp = next(found for found in tight.findings if found["type"] == "warp")
        self.assertEqual(warp["severity"], "error")
        self.assertEqual((warp["measured"]["limit"], warp["measured"]["pass_when"]), (0.01, "below"))
        self.assertGreater(warp["measured"]["value"], 0.01)
        self.assertEqual(warp["fix"]["action"], "change_orientation")
        self.assertEqual(warp["fix"]["params"], {"build_direction": [0.0, 1.0, 0.0]})   # the wall's 3 mm side up
        self.assertEqual(tight.verdict["status"], "fix")


@needs_fea
class Filament(unittest.TestCase):
    def test_an_fdm_part_that_warps_is_fixed_by_a_warmer_chamber(self):
        directory = class_directory(type(self))
        step = box_step(directory, "plate", (40.0, 20.0, 4.0), "corner")
        study = {"process": "printing", "technology": "fdm", "polymer": "abs", "mesh": {"size_mm": 2.5}, "bands": 6,
                 "tolerance_mm": 0.05, "bed_adhesion_MPa": 100.0}
        result = check(step, study)
        failing = [found for found in result.findings if found["severity"] == "error"]
        self.assertTrue(failing, result.findings)
        fix = failing[0]["fix"]
        self.assertEqual(fix["action"], "raise_chamber_temperature")
        warmer = fix["params"]["chamber_temperature_C"]
        self.assertTrue(25 < warmer < 105, warmer)
        again = check(step, {**study, "chamber_temperature_C": warmer})
        self.assertLess(again.summary["max_distortion_mm"], result.summary["max_distortion_mm"])
        adhesion = next(found for found in result.findings if found["type"] == "bed_adhesion")
        self.assertEqual((adhesion["severity"], adhesion["measured"]["limit"]), ("info", 100.0))


class SkillDocs(unittest.TestCase):
    """The printing reference lists what the tables hold."""

    def _rows(self, heading: str) -> list[list[str]]:
        text = (SKILL / "references" / "printing.md").read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
        return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]

    def test_the_reference_lists_every_material_and_technology(self):
        from cadgen._internal.manufacturing.processes.additive import MATERIALS, TECHNOLOGIES

        materials = [re.fullmatch(r"`([a-z0-9-]+)`", cells[0]) for cells in self._rows("## The materials")]
        self.assertEqual([found.group(1) for found in materials if found], list(MATERIALS))
        technologies = [re.fullmatch(r"`([a-z_]+)`", cells[0]) for cells in self._rows("## The technologies")]
        self.assertEqual([found.group(1) for found in technologies if found], list(TECHNOLOGIES))


if __name__ == "__main__":
    unittest.main()
