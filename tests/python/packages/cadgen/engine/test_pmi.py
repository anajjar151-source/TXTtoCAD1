"""Semantic PMI (``cadgen.engine.pmi``): a plate's datums, dimensions and geometric tolerances
written into its xbf as XCAF's GD&T objects and read back the same from the file as from the
build; its AP242 STEP read by OCCT and by a reader of no OCCT (``export/ap242.py``),
which agree on values, units, datum frames and the faces each annotation is on; a dimension
given limits, written as AP242's lower and upper limit and its nominal still measured; a surface
profile on several faces of any kind, written as one AP242 surface profile tolerance; a general
profile on every face nothing else controls, computed each build and written on exactly those
faces, or as nothing where it covers none; general and flag notes, numbered after the general
profile, and a project's notes library, kept in the xbf as XCAF notes (the same bytes from the same
code) and never in a STEP, which neither refuses nor checks them; named views of a part (their
camera, a preset's the snapshot's own, section, shown ids and placements) kept in the xbf as XCAF
views and served as ``pmi_views``, never in a STEP; each part's coverage (the faces no requirement
is on, and the requirements that cannot both hold) served as ``pmi_coverage`` and warned of by the
build, never failing it; a warm rebuild,
an edit of the geometry and of a tolerance, a ref the model no longer satisfies (missing,
ambiguous, invalid) kept in the document and refused by a STEP, and one that names another kind
of face than on the last build warned of, the document the code's alone; what is not supported
refused by name; a STEP another system wrote read, converted and exported as it is, what this does
not model listed; and the committed fixture (``pmi_golden``) the same as a fresh build's. A
deliberate change to what a build writes makes the fixture again:
`CADGEN_RENDER_GOLDENS=write scripts/test/test-python.sh tests/python/packages/cadgen/engine/test_pmi.py`."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from cadgen.engine import build as engine_build
from cadgen.engine import document, export, pmi
from cadgen.engine.export import ap242

FIXTURE = Path(__file__).resolve().parent / "pmi_golden"
WRITE = os.environ.get("CADGEN_RENDER_GOLDENS") == "write"


# The fixture's model: the plate of ``models/examples/src/pmi_plate.py`` and its first requirements (the
# example goes on to a model-based definition: datum-feature profiles, a general profile, notes and
# views). Tolerance values ILLUSTRATIVE.
PLATE = '''
import build123d as bd
from cadgen.engine import materials, pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, {thickness}) - bd.Cylinder({radius}, {thickness})
    body.label = "plate"
    body.material = materials.aluminium_6061
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    top = body.faces().sort_by(bd.Axis.Z)[-1]
    front = body.faces().sort_by(bd.Axis.Y)[0]
    left = body.faces().sort_by(bd.Axis.X)[0]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom, presentation=pmi.place((40, -20, -5), (0, -15, -10))),
        pmi.datum("B", front, presentation=pmi.place((40, -30, 0), (0, -15, 0))),
        pmi.datum("C", left, presentation=pmi.place((-50, 20, 0), (-15, 0, 0))),
        pmi.distance("thickness", bottom, top, tolerance=pmi.plus_minus({thickness_tolerance}),
                     presentation=pmi.place((50, 30, 0), (15, 0, 0))),
        pmi.diameter("hole-diameter", hole, tolerance=pmi.plus_minus(0.1, 0),
                     presentation=pmi.place((5, 0, 5), (15, 15, 0))),
        pmi.flatness("top-flatness", top, 0.05, presentation=pmi.place((-30, 20, 5), (0, 15, 0))),
        pmi.position("hole-position", hole, 0.1, datums=["A", "B", "C"],
                     presentation=pmi.place((-5, 0, 5), (-15, 15, 0))),
        pmi.basic("hole-from-B", front, hole, presentation=pmi.place((0, -15, 5), (6, 0, 0))),
        pmi.basic("hole-from-C", left, hole, presentation=pmi.place((-25, 0, 5), (0, 6, 0))),
    )
'''


def plate(thickness: float = 10, radius: float = 5, thickness_tolerance: float = 0.2) -> str:
    return PLATE.format(thickness=thickness, radius=radius, thickness_tolerance=thickness_tolerance)


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-pmi-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def build(self, source: str, name: str = "pmi_plate", *, ok: bool | None = True,
              log: list[str] | None = None) -> dict:
        """The model built from ``source``, its report ``ok`` as said (None: either), its log's lines
        kept in ``log``."""
        script = self.folder / f"{name}.py"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, [name], cwd=self.folder, log=(log if log is not None else []).append)[0]
        if ok is not None:
            self.assertEqual(report["ok"], ok, report)
        return report

    @property
    def xbf(self) -> Path:
        return self.folder / "XBF" / "pmi_plate.xbf"

    @property
    def step(self) -> Path:
        return self.folder / "pmi_plate.step"


def _by_id(entries: list[dict]) -> dict[str, dict]:
    return {entry["id"]: entry for entry in entries}


def _but_coverage(report: dict) -> dict:
    """A build report's ``pmi`` with its ``coverage`` left out, which ``CoverageTest`` holds."""
    return {key: value for key, value in report["pmi"].items() if key != "coverage"}


def _said(found: object) -> object:
    """An AP242 reader's report (``ap242.report``) with the file's name and its record numbers left
    out (a ``record``, a feature's ``face``): a writer numbering its records otherwise says the same."""
    if isinstance(found, dict):
        return {key: _said(value) for key, value in found.items() if key not in ("file", "record", "face")}
    if isinstance(found, list):
        return [_said(value) for value in found]
    return found


def _face(loaded: document.Loaded, entry: dict, at: int = 0) -> tuple[str, dict]:
    """The surface of the face an entry's ``at``-th ref names, from the document's own geometry."""
    from cadgen.engine.refs import resolve_structure

    [hit] = resolve_structure(loaded.structure(), entry["refs"][at]["ref"])
    prototype = loaded.prototypes[hit.node.payload["prototype"]]
    return pmi._surface(pmi._faces(prototype.shape).FindKey(hit.ordinal))


class PlateTest(_Folder):
    def test_the_document_holds_each_annotation_on_its_face(self) -> None:
        report = self.build(plate())
        self.assertEqual(_but_coverage(report), {"annotations": 9, "problems": []})
        loaded = document.Loaded(self.xbf)
        found = _by_id(loaded.structure()["pmi"])
        self.assertEqual(list(found), ["A", "B", "C", "thickness", "hole-diameter", "hole-from-B", "hole-from-C",
                                       "top-flatness", "hole-position"])
        self.assertTrue(all(entry["status"] == "ok" for entry in found.values()))
        # Datums: A the bottom (z = -5), B the front (y = -30), C the left (x = -50).
        for letter, axis, at in (("A", 2, -5.0), ("B", 1, -30.0), ("C", 0, -50.0)):
            kind, surface = _face(loaded, found[letter])
            self.assertEqual(kind, "plane")
            self.assertAlmostEqual(abs(surface["normal"][axis]), 1.0)
            self.assertAlmostEqual(surface["origin"][axis], at)
            self.assertEqual(found[letter]["datum"], {"letter": letter})
        # The thickness: measured, 10 mm, between the bottom and the top, +/-0.2 as given.
        thickness = found["thickness"]
        self.assertEqual(thickness["dimension"], {
            "type": "distance", "basic": False, "nominal": {"value": 10.0, "unit": "mm", "source": "geometry"},
            "tolerance": {"type": "plus_minus", "upper": 0.2, "lower": -0.2}})
        self.assertEqual([ref["role"] for ref in thickness["refs"]], ["from", "to"])
        self.assertAlmostEqual(_face(loaded, thickness, 0)[1]["origin"][2], -5.0)
        self.assertAlmostEqual(_face(loaded, thickness, 1)[1]["origin"][2], 5.0)
        self.assertEqual(thickness["refs"][0]["ref"], found["A"]["refs"][0]["ref"])
        # The hole: a cylinder of radius 5, its diameter 10 +0.1/0.
        diameter = found["hole-diameter"]
        self.assertEqual(_face(loaded, diameter), ("cylinder", {"radius": 5.0}))
        self.assertEqual(diameter["dimension"]["nominal"]["value"], 10.0)
        self.assertEqual(diameter["dimension"]["tolerance"], {"type": "plus_minus", "upper": 0.1, "lower": 0.0})
        # Flatness on the top; position of the hole to A|B|C, a diametral zone.
        self.assertEqual(found["top-flatness"]["geometric_tolerance"], {
            "characteristic": "flatness", "value": 0.05, "unit": "mm", "zone": None, "modifier": None, "datums": [],
            "general": False})
        self.assertEqual(found["top-flatness"]["refs"][0]["ref"], thickness["refs"][1]["ref"])
        self.assertEqual(found["hole-position"]["geometric_tolerance"], {
            "characteristic": "position", "value": 0.1, "unit": "mm", "zone": "diameter", "modifier": None,
            "datums": ["A", "B", "C"], "general": False})
        self.assertEqual(found["hole-position"]["refs"][0]["ref"], diameter["refs"][0]["ref"])
        # Presentation is kept, apart from the semantics.
        self.assertEqual(found["hole-position"]["presentation"], {"anchor": [-5.0, 0.0, 5.0], "offset": [-15.0, 15.0, 0.0]})

    def test_the_file_reads_back_what_the_build_served(self) -> None:
        self.build(plate())
        held = engine_build.held(self.folder / "pmi_plate.py", "pmi_plate")
        self.assertIsNotNone(held)
        self.assertEqual(held.structure["pmi"], document.Loaded(self.xbf).structure()["pmi"])

    def test_the_step_carries_the_same_pmi_to_occt_and_to_a_reader_of_no_occt(self) -> None:
        self.build(plate())
        ours = _by_id(pmi.read(self.xbf))
        # OCCT's XCAF reader: the same kinds, values and faces (ids are the engine's, not the file's).
        theirs = pmi.read(self.step)
        self.assertEqual(len(theirs), len(ours))

        def meaning(entry: dict) -> tuple:
            dimension = entry.get("dimension")
            if dimension is not None:  # its nominal's value: read from a file, its source is the file
                dimension = {**dimension, "nominal": dimension["nominal"]["value"]}
            return (entry["kind"], json.dumps(dimension, sort_keys=True), json.dumps(entry.get("datum")),
                    json.dumps(entry.get("geometric_tolerance"), sort_keys=True), [ref["ref"] for ref in entry["refs"]])

        self.assertEqual(sorted(map(meaning, theirs)), sorted(map(meaning, ours.values())))
        # A nominal the file holds, not one measured here.
        self.assertEqual({entry["dimension"]["nominal"]["source"] for entry in theirs if entry["kind"] == "dimension"},
                         {"file"})
        # The reader of no OCCT: AP242's entities, their values, units and faces, and nothing malformed.
        found = ap242.report(self.step)
        self.assertEqual(found["schema"].split(" ")[0], "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF")
        self.assertEqual(found["problems"], [])
        names = {letter: ours[letter]["refs"][0]["ref"].split("/", 1)[1] for letter in "ABC"}
        datums = {datum["identification"]: datum for datum in found["datums"]}
        self.assertEqual(sorted(datums), ["A", "B", "C"])
        for letter in "ABC":
            [feature] = datums[letter]["features"]
            self.assertEqual(feature["name"], names[letter])
            self.assertEqual(feature["surface"]["type"], "plane")
        dimensions = {entry["entity"]: entry for entry in found["dimensions"]}
        size = dimensions["DIMENSIONAL_SIZE"]
        self.assertEqual((size["name"], size["nominal"]["value"], size["nominal"]["unit"]), ("diameter", 10.0, "mm"))
        self.assertEqual((size["tolerance"]["lower"], size["tolerance"]["upper"], size["tolerance"]["unit"]), (0.0, 0.1, "mm"))
        self.assertEqual(size["features"][0]["surface"]["radius"], 5.0)
        [location] = [d for d in found["dimensions"] if d["entity"] == "DIMENSIONAL_LOCATION" and not d["notes"]]
        self.assertEqual((location["nominal"]["value"], location["tolerance"]["lower"], location["tolerance"]["upper"]),
                         (10.0, -0.2, 0.2))
        self.assertEqual([feature["surface"]["origin"][2] for feature in location["features"]], [-5.0, 5.0])
        tolerances = {entry["entity"]: entry for entry in found["tolerances"]}
        flatness = tolerances["FLATNESS_TOLERANCE"]
        self.assertEqual((flatness["magnitude"]["value"], flatness["magnitude"]["unit"], flatness["datums"]),
                         (0.05, "mm", []))
        position = tolerances["POSITION_TOLERANCE"]
        self.assertEqual((position["magnitude"]["value"], position["datums"], position["zone"]),
                         (0.1, ["A", "B", "C"], "cylindrical or circular"))
        self.assertNotIn("zone_definitions", position)
        self.assertEqual(position["features"][0]["name"], ours["hole-position"]["refs"][0]["ref"].split("/", 1)[1])

    def test_the_saved_document_exports_the_pmi_the_build_wrote(self) -> None:
        """Reopened from its xbf, the document writes a STEP whose PMI is the build's, to a reader of
        no OCCT. (Not its bytes: geometry read back from BinXCAF writes some zeros signed.)"""
        self.build(plate())
        again = self.folder / "again.step"
        export.translate(self.xbf, "step", again)
        self.assertEqual(_said(ap242.report(again)), _said(ap242.report(self.step)))

    def test_a_warm_rebuild_writes_the_same_document(self) -> None:
        self.build(plate())
        first = self.xbf.read_bytes()
        self.xbf.unlink()
        self.build(plate())
        self.assertEqual(self.xbf.read_bytes(), first)

    def test_an_edit_of_the_geometry_is_measured_again(self) -> None:
        self.build(plate())
        self.build(plate(thickness=12, radius=6))
        found = _by_id(pmi.read(self.xbf))
        self.assertEqual(found["thickness"]["dimension"]["nominal"]["value"], 12.0)
        self.assertEqual(found["hole-diameter"]["dimension"]["nominal"]["value"], 12.0)
        # The tolerances are the code's, unchanged by the geometry.
        self.assertEqual(found["thickness"]["dimension"]["tolerance"]["upper"], 0.2)
        self.assertTrue(all(entry["status"] == "ok" for entry in found.values()))
        report = ap242.report(self.step)
        self.assertEqual(sorted((entry["entity"], entry["nominal"]["value"], bool(entry["notes"]))
                                for entry in report["dimensions"]),
                         [("DIMENSIONAL_LOCATION", 12.0, False), ("DIMENSIONAL_LOCATION", 30.0, True),
                          ("DIMENSIONAL_LOCATION", 50.0, True), ("DIMENSIONAL_SIZE", 12.0, False)])

    def test_an_edit_of_a_tolerance_alone_is_written(self) -> None:
        self.build(plate())
        self.build(plate(thickness_tolerance=0.3))
        found = _by_id(pmi.read(self.xbf))
        self.assertEqual(found["thickness"]["dimension"]["tolerance"], {"type": "plus_minus", "upper": 0.3, "lower": -0.3})
        location = next(e for e in ap242.report(self.step)["dimensions"]
                        if e["entity"] == "DIMENSIONAL_LOCATION" and not e["notes"])
        self.assertEqual((location["tolerance"]["lower"], location["tolerance"]["upper"]), (-0.3, 0.3))

    def test_annotations_removed_from_the_code_leave_the_document(self) -> None:
        self.build(plate())
        self.build('''
import build123d as bd
from cadgen.engine import step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
    body.label = "plate"
    return body
''')
        self.assertNotIn("pmi", document.Loaded(self.xbf).structure())
        self.assertEqual(ap242.report(self.step)["datums"], [])


# A plate whose hole is named by its element name, as a viewer's Quick Edit writes it.
NAMED = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    {cut}
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom),
        pmi.diameter("hole-diameter", "{ref}", tolerance=pmi.plus_minus(0.1, 0)),
    )
'''


class BasicTest(_Folder):
    def test_basic_dimensions_locate_the_hole_from_its_datums_with_no_tolerance(self) -> None:
        self.build(plate())
        loaded = document.Loaded(self.xbf)
        found = _by_id(loaded.structure()["pmi"])
        for id, plane_axis, at, nominal in (("hole-from-B", 1, -30.0, 30.0), ("hole-from-C", 0, -50.0, 50.0)):
            entry = found[id]
            self.assertEqual(entry["status"], "ok", entry)
            self.assertEqual(entry["dimension"], {"type": "distance", "basic": True, "tolerance": None,
                                                  "nominal": {"value": nominal, "unit": "mm", "source": "geometry"}})
            self.assertEqual([ref["role"] for ref in entry["refs"]], ["from", "to"])
            kind, surface = _face(loaded, entry, 0)
            self.assertEqual(kind, "plane")
            self.assertAlmostEqual(surface["origin"][plane_axis], at)
            self.assertEqual(_face(loaded, entry, 1), ("cylinder", {"radius": 5.0}))
            # The datum the frame names, and the hole the position is on: the same faces.
            self.assertEqual(entry["refs"][0]["ref"], found["B" if id.endswith("B") else "C"]["refs"][0]["ref"])
            self.assertEqual(entry["refs"][1]["ref"], found["hole-position"]["refs"][0]["ref"])
        self.assertFalse(found["thickness"]["dimension"]["basic"])

    def test_the_step_marks_them_theoretical_to_occt_and_to_a_reader_of_no_occt(self) -> None:
        self.build(plate())
        report = ap242.report(self.step)
        self.assertEqual(report["problems"], [])
        basic = sorted((d["nominal"]["value"], d["nominal"]["unit"], d["tolerance"], d["notes"],
                        [f["surface"]["type"] for f in d["features"]])
                       for d in report["dimensions"] if d["notes"])
        self.assertEqual(basic, [
            (30.0, "mm", None, [["dimensional note", "theoretical"]], ["plane", "cylinder"]),
            (50.0, "mm", None, [["dimensional note", "theoretical"]], ["plane", "cylinder"])])
        theirs = sorted((e["dimension"]["nominal"]["value"], e["dimension"]["basic"])
                        for e in pmi.read(self.step) if e["kind"] == "dimension")
        self.assertEqual(theirs, [(10.0, False), (10.0, False), (30.0, True), (50.0, True)])

    def test_a_moved_hole_is_measured_again(self) -> None:
        self.build(plate())
        self.build(plate().replace("bd.Cylinder(5, 10)", "bd.Pos(10, 5, 0) * bd.Cylinder(5, 10)"))
        found = _by_id(pmi.read(self.xbf))
        self.assertEqual(found["hole-from-B"]["dimension"]["nominal"]["value"], 35.0)
        self.assertEqual(found["hole-from-C"]["dimension"]["nominal"]["value"], 60.0)

    def test_between_two_hole_axes_and_refused_where_the_axis_crosses_the_plane(self) -> None:
        report = self.build('''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Pos(-20, 0, 0) * bd.Cylinder(4, 10) - bd.Pos(20, 0, 0) * bd.Cylinder(4, 10)
    body.label = "plate"
    top = body.faces().sort_by(bd.Axis.Z)[-1]
    left, right = sorted(body.faces().filter_by(bd.GeomType.CYLINDER), key=lambda face: face.center().X)
    return pmi.annotate(body, pmi.basic("pitch", left, right), pmi.basic("crossing", top, left))
''', ok=False)
        [problem] = report["pmi"]["problems"]
        self.assertEqual((problem["id"], problem["status"]), ("crossing", "invalid"))
        self.assertIn("not parallel", problem["problem"])
        found = _by_id(pmi.read(self.xbf))
        self.assertEqual(found["pitch"]["dimension"]["nominal"]["value"], 40.0)
        self.assertTrue(found["pitch"]["dimension"]["basic"])
        self.assertEqual(found["crossing"]["status"], "invalid")
        self.assertTrue(found["crossing"]["dimension"]["basic"], "an unlinked basic dimension stays basic")

    def test_a_basic_dimension_takes_no_tolerance(self) -> None:
        import build123d as bd

        box = bd.Box(10, 10, 10)
        faces = box.faces().sort_by(bd.Axis.Z)
        with self.assertRaisesRegex(pmi.PMIError, "a basic dimension is theoretically exact"):
            pmi.dimension("b", "distance", faces[0], faces[-1], basic=True, tolerance=pmi.plus_minus(0.1))
        with self.assertRaisesRegex(pmi.PMIUnsupported, "basic"):
            pmi.dimension("d", "diameter", faces[0], basic=True)


# A plate whose hole and thickness are given limits: values ILLUSTRATIVE.
LIMITS = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    top = body.faces().sort_by(bd.Axis.Z)[-1]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return pmi.annotate(
        body,
        pmi.diameter("hole", hole, tolerance=pmi.limits(10.0, 10.05)),
        pmi.distance("thickness", bottom, top, tolerance=pmi.limits(9.9, 10.1)),
    )
'''


class LimitsTest(_Folder):
    def test_a_diameter_given_limits_keeps_them_and_measures_its_nominal(self) -> None:
        self.build(LIMITS)
        served = _by_id(engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure["pmi"])
        self.assertEqual(_by_id(pmi.read(self.xbf)), served)
        entry = served["hole"]
        self.assertEqual(entry["status"], "ok", entry)
        self.assertEqual(entry["dimension"]["tolerance"], {"type": "limits", "lower": 10.0, "upper": 10.05})
        self.assertAlmostEqual(entry["dimension"]["nominal"]["value"], 10.0)
        self.assertEqual(entry["dimension"]["nominal"]["source"], "geometry")
        self.assertEqual(served["thickness"]["dimension"]["tolerance"], {"type": "limits", "lower": 9.9, "upper": 10.1})
        self.assertAlmostEqual(served["thickness"]["dimension"]["nominal"]["value"], 10.0)

    def test_limits_are_refused_when_not_upper_above_lower(self) -> None:
        with self.assertRaisesRegex(pmi.PMIError, "upper limit .* is above its lower, not 10.05 and 10.05"):
            pmi.limits(10.05, 10.05)

    def test_limits_are_sizes_above_zero(self) -> None:
        with self.assertRaisesRegex(pmi.PMIError, "lower limit is a size above 0, not 0.0"):
            pmi.limits(0, 0.05)

    def test_a_basic_dimension_refuses_limits(self) -> None:
        import build123d as bd

        faces = bd.Box(10, 10, 10).faces().sort_by(bd.Axis.Z)
        with self.assertRaisesRegex(pmi.PMIError, "a basic dimension is theoretically exact"):
            pmi.dimension("b", "distance", faces[0], faces[-1], basic=True, tolerance=pmi.limits(9.9, 10.1))

    def test_the_step_carries_the_limits_and_the_check_matches_them(self) -> None:
        self.build(LIMITS)
        result = ap242.verify(pmi.read(self.xbf), self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (2, 2, []))
        text = self.step.read_text(encoding="utf-8")
        for value, role in (("10.", "lower limit"), ("10.05", "upper limit"), ("9.9", "lower limit"),
                            ("10.1", "upper limit")):
            self.assertRegex(text, rf"POSITIVE_LENGTH_MEASURE\({re.escape(value)}\),#\d+\)\s*REPRESENTATION_ITEM\s*"
                                   rf"\('{role}'\)")
        self.assertNotIn("PLUS_MINUS_TOLERANCE", text)
        size = next(row for row in ap242.report(self.step)["dimensions"] if row["entity"] == "DIMENSIONAL_SIZE")
        self.assertEqual([(bound["value"], bound["unit"]) for bound in size["limits"]], [(10.0, "mm"), (10.05, "mm")])
        self.assertIsNone(size["tolerance"])

    def test_a_vendor_dimension_with_limits_reads_as_limits(self) -> None:
        import build123d as bd

        body = bd.Box(20, 20, 10) - bd.Cylinder(4, 10)
        hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
        foreign = _Foreign(body)
        # Its hole named, as the check finds a face in a file: by the name its ADVANCED_FACE carries.
        document._name(foreign.sub(hole), "f:vendor.hole.1")
        foreign.dimension("Size_Diameter", [hole], 8.0, SetLowerBound=(7.9,), SetUpperBound=(8.1,))
        vendor = foreign.step(self.folder / "vendor.step")
        [entry] = pmi.read(vendor)
        self.assertEqual((entry["kind"], entry["status"]), ("dimension", "ok"), entry)
        self.assertEqual(entry["dimension"]["tolerance"], {"type": "limits", "lower": 7.9, "upper": 8.1})
        # The file states limits, not a nominal: none is served (XCAF's midpoint is no fact of the file).
        self.assertIsNone(entry["dimension"]["nominal"])
        # And the check matches it by its limits, in millimetres, as one of the code's.
        result = ap242.verify([entry], vendor)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (1, 1, []))

    def test_a_vendor_dimension_with_limits_and_more_is_unsupported_with_why(self) -> None:
        """XCAF holds limits or deviations, never both; limits with a fit or a qualifier say more
        than limits, so they are listed unsupported, naming both, never read as limits alone."""
        import build123d as bd
        from OCP import XCAFDimTolObjects as X

        body = bd.Box(20, 20, 10) - bd.Cylinder(4, 10)
        hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
        foreign = _Foreign(body)
        foreign.dimension("Size_Diameter", [hole], 8.0, SetLowerBound=(7.9,), SetUpperBound=(8.1,),
                          SetClassOfTolerance=(True, X.XCAFDimTolObjects_DimensionFormVariance_H,
                                               X.XCAFDimTolObjects_DimensionGrade_IT7))
        foreign.dimension("Size_Diameter", [hole], 8.0, SetLowerBound=(7.9,), SetUpperBound=(8.1,),
                          SetQualifier=(X.XCAFDimTolObjects_DimensionQualifier_Avg,))
        fitted, qualified = pmi.read(foreign.xbf(self.folder / "foreign.xbf"))
        for entry, other in ((fitted, "class of tolerance"), (qualified, "qualifier")):
            self.assertEqual((entry["kind"], entry["xcaf_type"]),
                             ("unsupported", "XCAFDimTolObjects_DimensionType_Size_Diameter"), entry)
            self.assertIn("limits", entry["reason"])
            self.assertIn(other, entry["reason"])
            self.assertEqual(entry["values"]["tolerance"], {"type": "limits", "lower": 7.9, "upper": 8.1})
            self.assertIsNone(entry["values"]["nominal"])


# A plate whose sides and hole are given one surface profile to datum A, and whose spherical dimple is
# given another of no datum: values ILLUSTRATIVE. No dimension, so OCCT's writer would put every
# magnitude in a bare metre (``UnitsTest``).
PROFILE = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10) - bd.Pos(30, 0, 5) * bd.Sphere(4)
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    front = body.faces().sort_by(bd.Axis.Y)[0]
    left = body.faces().sort_by(bd.Axis.X)[0]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    dimple = body.faces().filter_by(bd.GeomType.SPHERE)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom),
        pmi.profile("sides", [front, left, hole], 0.5, datums=["A"]),
        pmi.profile("dimple", dimple, 0.2),
    )
'''


class ProfileTest(_Folder):
    def test_a_profile_stands_on_several_faces_of_any_kind(self) -> None:
        report = self.build(PROFILE)
        self.assertEqual(_but_coverage(report), {"annotations": 3, "problems": []})
        loaded = document.Loaded(self.xbf)
        found = _by_id(loaded.structure()["pmi"])
        self.assertEqual(found, _by_id(engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure["pmi"]))
        sides = found["sides"]
        self.assertEqual((sides["kind"], sides["status"]), ("geometric_tolerance", "ok"), sides)
        self.assertEqual(sides["geometric_tolerance"], {
            "characteristic": "surface_profile", "value": 0.5, "unit": "mm", "zone": None, "modifier": None,
            "datums": ["A"], "general": False})
        self.assertEqual([(ref["role"], ref["status"]) for ref in sides["refs"]], [("feature", "ok")] * 3)
        self.assertEqual([_face(loaded, sides, at)[0] for at in range(3)], ["plane", "plane", "cylinder"])
        # One face, of a kind no other annotation stands on.
        dimple = found["dimple"]
        self.assertEqual((dimple["status"], _face(loaded, dimple)[0]), ("ok", "sphere"))
        self.assertEqual((dimple["geometric_tolerance"]["value"], dimple["geometric_tolerance"]["datums"]), (0.2, []))

    def test_a_profile_is_written_as_one_surface_profile_tolerance_and_checked(self) -> None:
        self.build(PROFILE)
        ours = _by_id(pmi.read(self.xbf))
        result = ap242.verify(list(ours.values()), self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (3, 3, []))
        found = ap242.report(self.step)
        self.assertEqual(found["problems"], [])
        sides, dimple = sorted(found["tolerances"], key=lambda row: -len(row["features"]))
        # The sides': one tolerance to datum A on the three faces, its magnitude in millimetres (the
        # writer's bare metre put right); the dimple's, of no datum, on its sphere.
        self.assertEqual((sides["entity"], sides["magnitude"]["value"], sides["magnitude"]["unit"], sides["datums"]),
                         ("SURFACE_PROFILE_TOLERANCE", 0.5, "mm", ["A"]))
        self.assertEqual(sorted(feature["name"] for feature in sides["features"]),
                         sorted(ref["ref"].split("/", 1)[1] for ref in ours["sides"]["refs"]))
        self.assertEqual(sorted(feature["surface"]["type"] for feature in sides["features"]), ["cylinder", "plane", "plane"])
        self.assertEqual((dimple["entity"], dimple["magnitude"]["value"], dimple["magnitude"]["unit"], dimple["datums"]),
                         ("SURFACE_PROFILE_TOLERANCE", 0.2, "mm", []))
        self.assertEqual([feature["surface"]["type"] for feature in dimple["features"]], ["spherical_surface"])
        text = self.step.read_text(encoding="utf-8")
        self.assertRegex(text, r"GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE\s*\(\s*\(\s*#\d+\s*\)\s*\)\s*"
                               r"SURFACE_PROFILE_TOLERANCE\s*\(\s*\)")
        self.assertNotIn("SI_UNIT($,.METRE.)", text.replace(" ", ""))
        # OCCT's reader: the same characteristic, value and faces.
        theirs = {entry["geometric_tolerance"]["value"]: entry for entry in pmi.read(self.step)
                  if entry["kind"] == "geometric_tolerance"}
        self.assertEqual(sorted(theirs), [0.2, 0.5])
        self.assertEqual(theirs[0.5]["geometric_tolerance"]["characteristic"], "surface_profile")
        self.assertEqual(sorted(ref["ref"] for ref in theirs[0.5]["refs"]), sorted(ref["ref"] for ref in ours["sides"]["refs"]))

    def test_a_profile_refuses_no_faces_a_zone_and_four_datums(self) -> None:
        import build123d as bd

        box = bd.Box(10, 10, 10)
        top = box.faces().sort_by(bd.Axis.Z)[-1]
        with self.assertRaisesRegex(pmi.PMIError, "a surface profile is on one face or more, not none"):
            pmi.profile("p", [], 0.5)
        with self.assertRaisesRegex(pmi.PMIError, "a surface profile's zone is a width about the profile: no "
                                                  "diametral zone"):
            pmi.geometric("p", "surface_profile", top, 0.5, diameter_zone=True)
        with self.assertRaisesRegex(pmi.PMIError, "three datums at most, not 4"):
            pmi.profile("p", top, 0.5, datums=["A", "B", "C", "D"])
        # A list of faces is a profile's alone.
        with self.assertRaisesRegex(pmi.PMIError, "a ref is a face of the part"):
            pmi.flatness("f", [top], 0.05)
        # One face named twice (here as a Face and by its element name) is no second face.
        ordinal = pmi._faces(box.wrapped).FindIndex(top.wrapped)
        names = [None] * 6
        names[ordinal - 1] = "f:box.top.1"
        pmi.annotate(box, pmi.profile("p", [top, "f:box.top.1"], 0.5))
        [item] = pmi._resolved_part(box.__dict__[pmi.PMI], box.wrapped, names, {"box"})
        self.assertEqual((item.status, [ref.status for ref in item.refs]), ("invalid", ["ok", "invalid"]))
        self.assertEqual(item.problem, f"f:box.top.1 names face {ordinal}, as face {ordinal} does: a surface profile "
                                       "is on each face once")

    def test_a_vendor_profile_reads_as_supported(self) -> None:
        """An OCCT-written surface profile on two faces reads back as one, on both; one with a
        diametral zone says more than a profile this holds, so it is listed unsupported."""
        import build123d as bd
        from OCP import XCAFDimTolObjects as X

        body = bd.Box(20, 20, 10)
        sides = body.faces().sort_by(bd.Axis.X)
        foreign = _Foreign(body)
        foreign.tolerance("ProfileOfSurface", [sides[0], sides[-1]], 0.3)
        [entry] = pmi.read(foreign.step(self.folder / "vendor.step"))
        self.assertEqual((entry["kind"], entry["status"], entry["xcaf_type"]), ("geometric_tolerance", "ok", None), entry)
        self.assertEqual(entry["geometric_tolerance"], {
            "characteristic": "surface_profile", "value": 0.3, "unit": "mm", "zone": None, "modifier": None,
            "datums": [], "general": False})
        self.assertEqual([(ref["role"], ref["status"]) for ref in entry["refs"]], [("feature", "ok")] * 2)
        self.assertEqual(len({ref["ref"] for ref in entry["refs"]}), 2)
        zoned = _Foreign(body)
        zoned.tolerance("ProfileOfSurface", [sides[0]], 0.3,
                        SetTypeOfValue=(X.XCAFDimTolObjects_GeomToleranceTypeValue_Diameter,))
        [entry] = pmi.read(zoned.xbf(self.folder / "zoned.xbf"))
        self.assertEqual((entry["kind"], entry["xcaf_type"]),
                         ("unsupported", "XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface"), entry)
        self.assertIn("diametral zone", entry["reason"])


# A plate given a general profile to A|B (ASME's "unless otherwise noted, all surfaces"): the hole has
# a size and a position, located from B and C by basic dimensions; the top has a flatness alone.
# Values ILLUSTRATIVE.
GENERAL = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    top = body.faces().sort_by(bd.Axis.Z)[-1]
    front = body.faces().sort_by(bd.Axis.Y)[0]
    left = body.faces().sort_by(bd.Axis.X)[0]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom),
        pmi.datum("B", front),
        pmi.datum("C", left),
        pmi.diameter("hole-diameter", hole, tolerance=pmi.plus_minus(0.1, 0)),
        pmi.position("hole-position", hole, 0.1, datums=["A", "B", "C"]),
        pmi.basic("hole-from-B", front, hole),
        pmi.basic("hole-from-C", left, hole),
        pmi.flatness("top-flatness", top, 0.05),
        pmi.general_profile("general", 0.5, datums=["A", "B"]),
    )
'''
# A block each face of which has a size of its own, and a general profile: values ILLUSTRATIVE.
CONTROLLED = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    body.label = "plate"
    x, y, z = (body.faces().sort_by(axis) for axis in (bd.Axis.X, bd.Axis.Y, bd.Axis.Z))
    return pmi.annotate(
        body,
        pmi.datum("A", z[0]),
        pmi.distance("length", x[0], x[-1], tolerance=pmi.plus_minus(0.2)),
        pmi.distance("width", y[0], y[-1], tolerance=pmi.limits(59.8, 60.2)),
        pmi.distance("thickness", z[0], z[-1], tolerance=pmi.plus_minus(0.1)),
        pmi.general_profile("general", 0.5, datums=["A"]),
    )
'''
# A plate whose ``cut`` is a round hole and then a square pocket, its thickness toleranced and the
# rest left to a general profile ({general}): values ILLUSTRATIVE.
GENERAL_CUT = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - {cut}
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    top = body.faces().sort_by(bd.Axis.Z)[-1]
    return pmi.annotate(body, pmi.datum("A", bottom),
                        pmi.distance("thickness", bottom, top, tolerance=pmi.plus_minus(0.2)), {general})
'''


def _ordinal(loaded: document.Loaded, ref: str) -> int:
    """The ordinal of the face a canonical ref names, in the document's own geometry."""
    from cadgen.engine.refs import resolve_structure

    [hit] = resolve_structure(loaded.structure(), ref)
    return hit.ordinal


class GeneralProfileTest(_Folder):
    def test_it_covers_every_face_nothing_else_controls(self) -> None:
        report = self.build(GENERAL)
        self.assertEqual(_but_coverage(report), {"annotations": 9, "problems": []})
        loaded = document.Loaded(self.xbf)
        served = loaded.structure()["pmi"]
        self.assertEqual(served, engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure["pmi"])
        found = _by_id(served)
        general = found["general"]
        self.assertEqual((general["kind"], general["status"], general["problem"]), ("geometric_tolerance", "ok", None))
        self.assertEqual(general["geometric_tolerance"], {
            "characteristic": "surface_profile", "value": 0.5, "unit": "mm", "zone": None, "modifier": None,
            "datums": ["A", "B"], "general": True})
        # The hole has a size and a location of its own. The basic dimensions locate it, not their
        # datum ends; the top's flatness is form alone, and a datum is no requirement.
        hole = found["hole-position"]["refs"][0]["ref"]
        self.assertEqual(pmi.otherwise_controlled(served), {hole})
        # The datum features it names are controlled on their own: no face is profiled to itself.
        named = [found[letter]["refs"][0]["ref"] for letter in "AB"]
        left = {_ordinal(loaded, ref) for ref in [hole, *named]}
        count = pmi._faces(loaded.prototypes[0].shape).Extent()
        # Every other face, in the part's order, each a computed ref the code never wrote.
        self.assertEqual([_ordinal(loaded, ref["ref"]) for ref in general["refs"]],
                         [at for at in range(1, count + 1) if at not in left])
        self.assertEqual(len(general["refs"]), 4)
        self.assertTrue(all(ref == {"role": "feature", "written": None, "status": "ok", "ref": ref["ref"],
                                    "candidates": None, "problem": None} for ref in general["refs"]), general["refs"])
        covered = {ref["ref"] for ref in general["refs"]}
        # C, which the frame does not name and only a basic dimension starts from, stays covered.
        self.assertLessEqual({found["top-flatness"]["refs"][0]["ref"], found["C"]["refs"][0]["ref"]}, covered)

    def test_the_step_holds_it_on_exactly_those_faces(self) -> None:
        self.build(GENERAL)
        ours = pmi.read(self.xbf)
        result = ap242.verify(ours, self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (9, 9, []))
        general = _by_id(ours)["general"]
        [profile] = [row for row in ap242.report(self.step)["tolerances"] if row["entity"] == "SURFACE_PROFILE_TOLERANCE"]
        self.assertEqual(sorted(feature["name"] for feature in profile["features"]),
                         sorted(ref["ref"].split("/", 1)[1] for ref in general["refs"]))
        self.assertEqual((profile["magnitude"]["value"], profile["magnitude"]["unit"], profile["datums"]),
                         (0.5, "mm", ["A", "B"]))
        # OCCT's reader: a surface profile on those faces, as any CAM reader gets it.
        [theirs] = [entry for entry in pmi.read(self.step)
                    if (entry.get("geometric_tolerance") or {}).get("characteristic") == "surface_profile"]
        self.assertEqual(sorted(ref["ref"] for ref in theirs["refs"]), sorted(ref["ref"] for ref in general["refs"]))

    def test_it_covers_no_face_when_every_face_has_its_own(self) -> None:
        report = self.build(CONTROLLED)
        self.assertEqual(report["pmi"], {"annotations": 5, "problems": []})
        served = pmi.read(self.xbf)
        self.assertEqual(served, engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure["pmi"])
        general = _by_id(served)["general"]
        self.assertEqual((general["status"], general["problem"], general["refs"]), ("ok", None, []))
        self.assertEqual((general["geometric_tolerance"]["datums"], general["geometric_tolerance"]["general"]),
                         (["A"], True))
        # Linked to nothing, it is written as nothing, and the check expects nothing for it.
        self.assertNotIn("SURFACE_PROFILE_TOLERANCE", self.step.read_text(encoding="utf-8"))
        result = ap242.verify(served, self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (5, 5, []))

    def test_a_second_general_profile_is_refused(self) -> None:
        import build123d as bd

        with self.assertRaisesRegex(pmi.PMIError, "one general profile, not 'general' and 'outer'"):
            pmi.annotate(bd.Box(10, 10, 10), pmi.general_profile("general", 0.5), pmi.general_profile("outer", 0.2))

    def test_one_naming_a_datum_the_part_lacks_covers_nothing_and_is_refused_by_a_step(self) -> None:
        report = self.build(GENERAL_CUT.format(cut=ROUND,
                                               general='pmi.general_profile("general", 0.5, datums=["B"])'), ok=False)
        [problem] = report["pmi"]["problems"]
        self.assertEqual((problem["id"], problem["status"]), ("general", "invalid"))
        self.assertIn("a STEP would drop PMI", report["error"])
        self.assertIn("general", report["error"])
        self.assertEqual(_by_id(pmi.read(self.xbf))["general"]["refs"], [])

    def test_its_faces_follow_an_edit_with_the_same_bytes_whatever_was_built_before(self) -> None:
        def built(cut: str) -> list[str]:
            """The kinds of the faces the general profile covers, built with ``cut``."""
            self.build(GENERAL_CUT.format(cut=cut, general='pmi.general_profile("general", 0.5, datums=["A"])'))
            loaded = document.Loaded(self.xbf)
            general = _by_id(loaded.structure()["pmi"])["general"]
            return sorted(_face(loaded, general, at)[0] for at in range(len(general["refs"])))

        # The four sides and the hole; then the four sides and the pocket's four, nothing controlling them.
        self.assertEqual(built(ROUND), ["cylinder"] + ["plane"] * 4)
        self.assertEqual(built(SQUARE), ["plane"] * 8)
        after = self.xbf.read_bytes()
        self.xbf.unlink()
        engine_build._WRITTEN.clear()
        self.assertEqual(built(SQUARE), ["plane"] * 8)
        self.assertEqual(self.xbf.read_bytes(), after)


# A plate given a general note and a flag note on its hole, after its general profile ({general}): the
# flag note's text is the project's notes library's, a dict its own module would hold (here inline).
# Tolerance values and note texts ILLUSTRATIVE.
NOTES = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf

LIBRARY = {{"primer-mask": "Mask these features before coating with primer"}}


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    {cut}
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom),
        pmi.diameter("hole-dia", {hole}, tolerance=pmi.plus_minus(0.1, 0)),
        {general}
        pmi.note("deburr", "Break all sharp edges 0.2 max"),
        pmi.note("mask", LIBRARY["primer-mask"], faces=[{mask}], annotations=["hole-dia"]),
        library=LIBRARY,
    )
'''
HOLE = "body.faces().filter_by(bd.GeomType.CYLINDER)[0]"
MASK = "Mask these features before coating with primer"


def notes(*, general: bool = True, cut: str = "body = body - bd.Cylinder(5, 10)", hole: str = HOLE,
          mask: str | None = None) -> str:
    """The plate with notes; ``mask``: the flag note's face where it is not the hole's ref."""
    return NOTES.format(general='pmi.general_profile("general", 0.5, datums=["A"]),' if general else "", cut=cut,
                        hole=hole, mask=hole if mask is None else mask)


def _numbers(entries: list[dict]) -> list[tuple[str, int, bool]]:
    """Each note's id, number and whether it is a general note, in the order served."""
    return [(entry["id"], entry["note"]["number"], entry["note"]["general"]) for entry in entries
            if entry["kind"] == "note"]


class NoteTest(_Folder):
    def served(self) -> dict:
        """The structure the last build served."""
        return engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure

    def test_notes_are_numbered_after_the_general_profile(self) -> None:
        report = self.build(notes())
        self.assertEqual(_but_coverage(report), {"annotations": 5, "problems": []})
        served = pmi.read(self.xbf)
        self.assertEqual(served, self.served()["pmi"])
        # The part's general profile is Note 1; the notes follow in the order the code gives them.
        self.assertEqual(_numbers(served), [("deburr", 2, True), ("mask", 3, False)])
        deburr = _by_id(served)["deburr"]
        self.assertEqual((deburr["status"], deburr["problem"], deburr["refs"]), ("ok", None, []))
        self.assertEqual(deburr["note"], {"number": 2, "text": "Break all sharp edges 0.2 max", "general": True,
                                          "annotations": []})
        # With no general profile, the first note is Note 1.
        self.build(notes(general=False))
        self.assertEqual(_numbers(pmi.read(self.xbf)), [("deburr", 1, True), ("mask", 2, False)])

    def test_a_flag_note_names_its_faces_and_annotations(self) -> None:
        self.build(notes())
        loaded = document.Loaded(self.xbf)
        found = _by_id(loaded.structure()["pmi"])
        mask = found["mask"]
        self.assertEqual(set(mask), {"id", "kind", "label", "status", "problem", "warnings", "part", "refs",
                                     "presentation", "xcaf_type", "note"})
        self.assertEqual((mask["kind"], mask["label"], mask["status"], mask["problem"], mask["warnings"], mask["part"],
                          mask["presentation"], mask["xcaf_type"]),
                         ("note", None, "ok", None, [], 0, None, "XCAFDoc_NoteComment"))
        self.assertEqual(mask["note"], {"number": 3, "text": MASK, "general": False, "annotations": ["hole-dia"]})
        # On the hole's face, a ref as any other annotation's.
        hole = found["hole-dia"]["refs"][0]
        self.assertEqual(mask["refs"], [{"role": "feature", "written": hole["written"], "status": "ok", "ref": hole["ref"],
                                         "candidates": None, "problem": None}])
        self.assertEqual(_face(loaded, mask), ("cylinder", {"radius": 5.0}))

    def test_a_flag_note_whose_face_is_gone_keeps_its_number_and_says_missing(self) -> None:
        self.build(notes())
        loaded = document.Loaded(self.xbf)
        faces = pmi._faces(loaded.prototypes[0].shape)
        [ordinal] = [at for at in range(1, faces.Extent() + 1) if pmi._surface(faces.FindKey(at))[0] == "cylinder"]
        name = loaded.prototypes[0].face_names[ordinal]
        self.build(notes(hole=repr(name)))
        before = _by_id(pmi.read(self.xbf))["mask"]
        self.assertEqual((before["status"], before["note"]["number"]), ("ok", 3))
        # The hole removed: the note's face is gone. The build says so; the note keeps its number,
        # its text and its links as written, missing; the STEP is refused for the diameter alone.
        report = self.build(notes(hole=repr(name), cut="pass"), ok=False)
        self.assertEqual({(problem["id"], problem["status"]) for problem in report["pmi"]["problems"]},
                         {("hole-dia", "missing"), ("mask", "missing")})
        self.assertIn("hole-dia", report["error"])
        self.assertNotIn("mask", report["error"])
        served = pmi.read(self.xbf)
        mask = _by_id(served)["mask"]
        self.assertEqual((mask["status"], mask["note"]), ("missing", before["note"]))
        self.assertIn(f"no face {name}", mask["problem"])
        self.assertEqual([(ref["ref"], ref["written"], ref["status"]) for ref in mask["refs"]], [(name, name, "missing")])

    def test_an_unknown_annotation_id_and_empty_text_are_refused(self) -> None:
        import build123d as bd

        box = bd.Box(10, 10, 10)
        top = box.faces().sort_by(bd.Axis.Z)[-1]
        with self.assertRaisesRegex(pmi.PMIError, "note 'mask' names 'hole-dia', which is no annotation of this "
                                                  r"pmi.annotate\(\) call"):
            pmi.annotate(box, pmi.flatness("top-flat", top, 0.05), pmi.note("mask", MASK, faces=[top],
                                                                            annotations=["hole-dia"]))
        with self.assertRaisesRegex(pmi.PMIError, "note 'see' names note 'deburr': a note names annotations"):
            pmi.annotate(box, pmi.note("deburr", "Break all sharp edges 0.2 max"),
                         pmi.note("see", "See note 2", annotations=["deburr"]))
        for text in ("", "   ", None, 3):
            with self.assertRaisesRegex(pmi.PMIError, "note 'blank': a note's text is a non-empty string"):
                pmi.note("blank", text)  # type: ignore[arg-type]
        # A note's id is one of its part's ids, as its annotations' are.
        with self.assertRaisesRegex(pmi.PMIError, "two annotations on one part are 'top-flat'"):
            pmi.annotate(box, pmi.flatness("top-flat", top, 0.05), pmi.note("top-flat", "Lap this face"))
        with self.assertRaisesRegex(pmi.PMIError, "library note 'primer-mask': its text is a non-empty string"):
            pmi.annotate(box, library={"primer-mask": ""})
        with self.assertRaisesRegex(pmi.PMIError, "a library is a project's notes by name"):
            pmi.annotate(box, library=["primer-mask"])  # type: ignore[arg-type]

    def test_notes_and_the_library_survive_the_xbf_and_make_the_same_bytes(self) -> None:
        from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
        from OCP.XCAFDoc import XCAFDoc_AssemblyItemId, XCAFDoc_DocumentTool, XCAFDoc_NoteComment

        self.build(notes())
        loaded = document.Loaded(self.xbf)
        structure = loaded.structure()
        self.assertEqual(structure["pmi_library"], [{"part": 0, "name": "primer-mask", "text": MASK}])
        self.assertEqual((self.served()["pmi"], self.served()["pmi_library"]),
                         (structure["pmi"], structure["pmi_library"]))
        # XCAF's notes: comments by one fixed user with no timestamp, in the code's order.
        tool = XCAFDoc_DocumentTool.NotesTool_s(loaded.doc.Main())
        labels = TDF_LabelSequence()
        tool.GetNotes(labels)
        said = [XCAFDoc_NoteComment.Get_s(labels.Value(at)) for at in range(1, labels.Length() + 1)]
        self.assertEqual([(note.Comment().ToExtString(), note.UserName().ToExtString(), note.TimeStamp().ToExtString())
                          for note in said], [("Break all sharp edges 0.2 max", "cadgen", ""), (MASK, "cadgen", "")])

        def label(entry: str) -> object:
            found = TDF_Label()
            TDF_Tool.Label_s(loaded.doc.GetData(), entry, found)
            return found

        def texts(found: TDF_LabelSequence) -> list[str]:
            return [XCAFDoc_NoteComment.Get_s(found.Value(at)).Comment().ToExtString()
                    for at in range(1, found.Length() + 1)]

        # The general note on the part; the flag note on the hole's face, its sub-shape index the
        # face's ordinal in the part's face map (the ref grammar's), and on the diameter's GD&T label.
        self.assertEqual(tool.NbAnnotatedItems(), 3)
        part = loaded.prototypes[0]
        found = TDF_LabelSequence()
        tool.GetNotes(label(part.entry), found)
        self.assertEqual(texts(found), ["Break all sharp edges 0.2 max"])
        ordinal = _ordinal(loaded, _by_id(structure["pmi"])["mask"]["refs"][0]["ref"])
        self.assertEqual(pmi._surface(pmi._faces(part.shape).FindKey(ordinal))[0], "cylinder")
        for at in range(1, pmi._faces(part.shape).Extent() + 1):
            found = TDF_LabelSequence()
            tool.GetSubshapeNotes(XCAFDoc_AssemblyItemId(part.entry), at, found)
            self.assertEqual(texts(found), [MASK] if at == ordinal else [], at)
        [diameter] = [record for record in pmi.records_of_document(loaded.doc, loaded.prototypes, loaded.name)
                      if (record["extra"] or {}).get("id") == "hole-dia"]
        found = TDF_LabelSequence()
        tool.GetNotes(label(diameter["entry"]), found)
        self.assertEqual(texts(found), [MASK])
        # The same code makes the same bytes, built warm or fresh.
        first = self.xbf.read_bytes()
        self.xbf.unlink()
        self.build(notes())
        self.assertEqual(self.xbf.read_bytes(), first)
        self.xbf.unlink()
        engine_build._WRITTEN.clear()
        self.build(notes())
        self.assertEqual(self.xbf.read_bytes(), first)

    def test_a_library_alone_is_served_and_a_note_keeps_any_text(self) -> None:
        model = '''
import build123d as bd
from cadgen.engine import pmi, xbf


@xbf(out="XBF/pmi_plate.xbf")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    body.label = "plate"
    return pmi.annotate(body, {notes}library={{"primer-mask": "{mask}", "finish": "Ra 1.6 µm"}})
'''
        # A project's library before any note is written: the viewer offers what the build saw.
        self.build(model.format(notes="", mask=MASK))
        structure = document.Loaded(self.xbf).structure()
        self.assertEqual(structure["pmi"], [])
        self.assertEqual(structure["pmi_library"], [{"part": 0, "name": "primer-mask", "text": MASK},
                                                    {"part": 0, "name": "finish", "text": "Ra 1.6 µm"}])
        self.assertEqual(self.served()["pmi_library"], structure["pmi_library"])
        self.build(model.format(notes='pmi.note("finish", "Ra 1.6 µm, ⌀ holes ±0.1"), ', mask=MASK))
        [finish] = pmi.read(self.xbf)
        self.assertEqual((finish["note"]["number"], finish["note"]["text"]), (1, "Ra 1.6 µm, ⌀ holes ±0.1"))

    def test_a_step_of_a_document_with_notes_is_written_and_checked_without_them(self) -> None:
        """Review Focus 5: a STEP carries no note (OCCT's writer writes none), so a note never stops
        one, and the check matches the GD&T alone."""
        self.build(notes())
        served = pmi.read(self.xbf)
        result = ap242.verify(served, self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (3, 3, []))
        text = self.step.read_text(encoding="utf-8")
        self.assertNotIn("Break all sharp edges", text)
        self.assertNotIn(MASK, text)
        self.assertNotIn("note", {entry["kind"] for entry in pmi.read(self.step)})
        # A flag note gone missing: the build and its STEP are written, the check the same, and an
        # export of the saved document says nothing of the note.
        report = self.build(notes(mask="'face 99'"))
        self.assertEqual([(problem["id"], problem["status"]) for problem in report["pmi"]["problems"]],
                         [("mask", "missing")])
        result = ap242.verify(pmi.read(self.xbf), self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (3, 3, []))
        said: list[str] = []
        export.translate(self.xbf, "step", self.folder / "again.step", log=said.append)
        self.assertEqual([line for line in said if "pmi" in line], [])
        self.assertEqual(pmi.dropped(export.Source.read(self.xbf).view(), "step"), [])


# A plate (0..100, 0..60, 0..10) with a hole through it at (50, 30) and named views (the values
# ILLUSTRATIVE): section A-A through the hole, seen from the front, showing the hole's diameter and
# position, the diameter's callout placed for that view; the iso view, which shows everything; and
# ``{more}``.
VIEWS = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10, align=bd.Align.MIN) - bd.Pos(50, 30, 0) * bd.Cylinder(
        5, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body.label = "plate"
    bottom = body.faces().sort_by(bd.Axis.Z)[0]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom),
        pmi.diameter("hole-dia", hole, tolerance=pmi.plus_minus(0.1, 0)),
        pmi.position("hole-pos", hole, 0.1, datums=["A"]),
        pmi.note("deburr", "Break all sharp edges 0.2 max"),
        pmi.view("A-A", camera="front", shows=["hole-dia", "hole-pos"], section=pmi.section("y", 30),
                 place={"hole-dia": pmi.place((5, 30, 0), (10, 0, 10))}, label="Section A-A"),
        pmi.view("iso", camera="iso"),
        {more}
    )
'''
# A part given views alone.
VIEWS_ALONE = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    body.label = "plate"
    return pmi.annotate(body, pmi.view("iso", camera="iso"), pmi.view("top", camera="top"))
'''


def views(more: str = "") -> str:
    return VIEWS.replace("{more}", more)


class ViewTest(_Folder):
    def served(self) -> dict:
        """The structure the last build served."""
        return engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure

    def test_a_view_holds_its_camera_section_shows_and_placements(self) -> None:
        report = self.build(views('pmi.view("down", camera=pmi.camera((0, -1, 1), (0, 0, 1)), shows=["deburr"]),'))
        # Views are no annotations: the report counts the four, and ``pmi`` lists none.
        self.assertEqual(_but_coverage(report), {"annotations": 4, "problems": []})
        self.assertEqual([entry["kind"] for entry in pmi.read(self.xbf)], ["datum", "dimension", "geometric_tolerance",
                                                                           "note"])
        served = document.Loaded(self.xbf).structure()["pmi_views"]
        self.assertEqual(served, self.served()["pmi_views"])
        section, iso, down = served
        self.assertEqual(section, {
            "part": 0, "name": "A-A", "label": "Section A-A",
            "camera": {"preset": "front", "direction": [0.0, -1.0, 0.0], "up": [0.0, 0.0, 1.0],
                       "projection": "orthographic"},
            "section": {"axis": "y", "at": 30.0, "invert": False}, "shows": ["hole-dia", "hole-pos"],
            "place": {"hole-dia": {"anchor": [5.0, 30.0, 0.0], "offset": [10.0, 0.0, 10.0]}}})
        # The iso view shows every annotation and note (``shows`` null), with no section.
        self.assertEqual((iso["name"], iso["label"], iso["camera"]["preset"], iso["section"], iso["shows"], iso["place"]),
                         ("iso", None, "iso", None, None, {}))
        # A camera of the code's own: unit vectors, the direction from the part toward the eye.
        self.assertEqual(pmi.camera((0, -1, 1), (0, 0, 2)), {"direction": [0.0, -1 / math.sqrt(2), 1 / math.sqrt(2)],
                                                             "up": [0.0, 0.0, 1.0]})
        self.assertEqual(down["camera"], {"preset": None, **pmi.camera((0, -1, 1), (0, 0, 1)),
                                          "projection": "orthographic"})
        self.assertEqual(pmi.section("z", 4, invert=True), {"axis": "z", "at": 4.0, "invert": True})

    def test_a_preset_camera_is_the_snapshot_presets_own(self) -> None:
        from cadgen.engine import snapshot
        from cadgen.engine.render.occt import direction_of

        names = sorted(snapshot.CAMERA_PRESETS)
        self.build(views("".join(f'pmi.view("{name} preset", camera="{name}"),' for name in names)))
        served = {view["name"]: view["camera"] for view in self.served()["pmi_views"]}
        top = served["top preset"]
        self.assertEqual((top["preset"], top["direction"], top["up"]), ("top", [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]))
        for name in names:
            direction, up = direction_of(snapshot.parse_camera(name))
            camera = served[f"{name} preset"]
            self.assertEqual(camera["preset"], name)
            for held, drawn in zip(camera["direction"] + camera["up"], list(direction) + list(up)):
                self.assertAlmostEqual(held, float(drawn), places=15, msg=name)
        with self.assertRaisesRegex(pmi.PMIError, "view 'A-A': a camera is a preset "
                                                  rf"\({', '.join(names)}\) or pmi.camera\(direction, up\)"):
            pmi.view("A-A", camera="30:20")

    def test_views_survive_the_xbf_as_xcaf_views_and_make_the_same_bytes(self) -> None:
        from OCP.gp import gp_Pln
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
        from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_View
        from OCP.XCAFView import XCAFView_ProjectionType_Parallel

        from cadgen.engine.document import _entry

        self.build(views())
        loaded = document.Loaded(self.xbf)
        tool = XCAFDoc_DocumentTool.ViewTool_s(loaded.doc.Main())
        labels = TDF_LabelSequence()
        tool.GetViewLabels(labels)
        found = {XCAFDoc_View.Set_s(labels.Value(at)).GetObject().Name().ToCString(): labels.Value(at)
                 for at in range(1, labels.Length() + 1)}
        self.assertEqual(list(found), ["A-A", "iso"])
        entries = {(record["extra"] or {}).get("id"): record["entry"]
                   for record in pmi.records_of_document(loaded.doc, loaded.prototypes, loaded.name)}

        def linked(method: object, label: object) -> list[str]:
            sequence = TDF_LabelSequence()
            method(label, sequence)  # type: ignore[operator]
            return [_entry(sequence.Value(at)) for at in range(1, sequence.Length() + 1)]

        # Section A-A: parallel, looking along +Y (XCAF's view direction is the one looked along,
        # the served direction's opposite), up +Z, its eye the part's box centre (50, 30, 5) moved
        # toward the eye by the box's diagonal; on its part, with the GD&T it shows.
        held = XCAFDoc_View.Set_s(found["A-A"]).GetObject()
        self.assertEqual(held.Type(), XCAFView_ProjectionType_Parallel)
        look, up, eye = held.ViewDirection(), held.UpDirection(), held.ProjectionPoint()
        self.assertEqual([(look.X(), look.Y(), look.Z()), (up.X(), up.Y(), up.Z())], [(0.0, 1.0, 0.0), (0.0, 0.0, 1.0)])
        diagonal = math.sqrt(100 ** 2 + 60 ** 2 + 10 ** 2)
        for held_at, wanted in zip((eye.X(), eye.Y(), eye.Z()), (50.0, 30.0 - diagonal, 5.0)):
            self.assertAlmostEqual(held_at, wanted, places=6)
        self.assertEqual(linked(tool.GetRefShapeLabel, found["A-A"]), [loaded.prototypes[0].entry])
        self.assertEqual(linked(tool.GetRefGDTLabel, found["A-A"]), [entries["hole-dia"], entries["hole-pos"]])
        # Its section, an XCAF clipping plane named for it: at y = 30, its normal into the half kept
        # (the Clip's lower side, -Y), capped as the Clip caps.
        planes = XCAFDoc_DocumentTool.ClippingPlaneTool_s(loaded.doc.Main())
        listed = TDF_LabelSequence()
        planes.GetClippingPlanes(listed)
        self.assertEqual(linked(tool.GetRefClippingPlaneLabel, found["A-A"]),
                         [_entry(listed.Value(at)) for at in range(1, listed.Length() + 1)])
        plane_label = listed.Value(1)
        plane, name = gp_Pln(), TCollection_ExtendedString()
        self.assertTrue(planes.GetClippingPlane(plane_label, plane, name, False))
        point, normal = plane.Location(), plane.Axis().Direction()
        self.assertEqual((name.ToExtString(), point.Y(), (normal.X(), normal.Y(), normal.Z()), planes.GetCapping(plane_label)),
                         ("A-A", 30.0, (0.0, -1.0, 0.0), True))
        # The iso view shows every annotation, its GD&T all linked, and cuts nothing.
        self.assertEqual(linked(tool.GetRefGDTLabel, found["iso"]), [entries["A"], entries["hole-dia"], entries["hole-pos"]])
        self.assertEqual(linked(tool.GetRefClippingPlaneLabel, found["iso"]), [])
        # The notes a view shows are its cadgen attribute's: OCCT's SetView files a view's notes under
        # its clipping-plane link, where a reader would take them for planes.
        deburr = TDF_Label()
        TDF_Tool.Label_s(loaded.doc.GetData(), entries["deburr"], deburr)
        self.assertEqual(linked(tool.GetViewLabelsForNote, deburr), [])
        # The same code makes the same bytes, built warm or fresh.
        first = self.xbf.read_bytes()
        self.xbf.unlink()
        self.build(views())
        self.assertEqual(self.xbf.read_bytes(), first)
        self.xbf.unlink()
        engine_build._WRITTEN.clear()
        self.build(views())
        self.assertEqual(self.xbf.read_bytes(), first)

    def test_an_unknown_id_a_duplicate_name_and_a_place_of_an_unshown_id_are_refused(self) -> None:
        import build123d as bd

        box = bd.Box(10, 10, 10)
        top = box.faces().sort_by(bd.Axis.Z)[-1]
        flat = pmi.flatness("top-flat", top, 0.05)
        with self.assertRaisesRegex(pmi.PMIError, "view 'A-A' shows 'hole-dia', which is no annotation of this "
                                                  r"pmi.annotate\(\) call; its ids are 'top-flat'"):
            pmi.annotate(box, flat, pmi.view("A-A", camera="front", shows=["hole-dia"]))
        with self.assertRaisesRegex(pmi.PMIError, "two views of one part are named 'A-A': a view's name is unique"):
            pmi.annotate(box, flat, pmi.view("A-A", camera="front"), pmi.view("A-A", camera="back"))
        lap = pmi.note("lap", "Lap this face", faces=[top])
        with self.assertRaisesRegex(pmi.PMIError, "view 'A-A' places 'top-flat', which it does not show"):
            pmi.annotate(box, flat, lap, pmi.view("A-A", camera="front", shows=["lap"],
                                                  place={"top-flat": pmi.place((0, 0, 5))}))
        with self.assertRaisesRegex(pmi.PMIError, "view 'iso' places 'gone', which is no annotation of this"):
            pmi.annotate(box, flat, pmi.view("iso", camera="iso", place={"gone": pmi.place((0, 0, 5))}))
        # A view is no annotation: a note names none.
        with self.assertRaisesRegex(pmi.PMIError, "note 'see' names 'iso', which is no annotation"):
            pmi.annotate(box, flat, pmi.view("iso", camera="iso"), pmi.note("see", "See view iso", annotations=["iso"]))
        # Each value is refused by name where it is made.
        for given, said in ((lambda: pmi.view("", camera="front"), "a view's name is a non-empty string"),
                            (lambda: pmi.view("A-A", camera="front", shows=["lap", "lap"]),
                             "view 'A-A' shows 'lap' twice"),
                            (lambda: pmi.view("A-A", camera="front", place={"lap": (0, 0, 5)}),
                             r"view 'A-A': a placement is pmi.place\(anchor, offset\)"),
                            (lambda: pmi.view("A-A", camera="front", section={"axis": "x"}),
                             r"view 'A-A': a section is pmi.section\(axis, at\)"),
                            (lambda: pmi.view("A-A", camera={"direction": [0, 0, 2], "up": [0, 1, 0]}),
                             r"view 'A-A': a camera is a preset .* or pmi.camera\(direction, up\)"),
                            (lambda: pmi.camera((0, 0, 1), (0, 0, -2)), "a camera's up is not along its direction"),
                            (lambda: pmi.camera((0, 0, 0), (0, 0, 1)), "a camera's direction is longer than 0"),
                            (lambda: pmi.section("w", 3), "a section's axis is x, y or z, not 'w'"),
                            (lambda: pmi.section("x", float("nan")), "a section's place is a finite number"),
                            (lambda: pmi.section("x", 3, invert=1), "a section's invert is True or False")):
            with self.assertRaisesRegex(pmi.PMIError, said):
                given()
        # Views alone are a part's too.
        self.assertIs(pmi.annotate(box, pmi.view("iso", camera="iso")), box)

    def test_a_step_of_a_document_with_views_is_written_and_checked_without_them(self) -> None:
        """Review Focus 5: a STEP carries no view (OCCT's writer writes none), so a view never stops
        one, and the check matches the GD&T alone."""
        from cadgen.engine.export import viewer

        self.build(views())
        result = ap242.verify(pmi.read(self.xbf), self.step)
        self.assertEqual((result["matched"], result["total"], result["problems"]), (3, 3, []))
        text = self.step.read_text(encoding="utf-8")
        self.assertNotIn("CAMERA_MODEL", text)
        self.assertNotIn("Section A-A", text)
        self.assertEqual(document.Loaded(self.step).structure()["pmi_views"], [])
        said: list[str] = []
        export.translate(self.xbf, "step", self.folder / "again.step", log=said.append)
        self.assertEqual([line for line in said if "pmi" in line], [])
        self.assertEqual(pmi.dropped(export.Source.read(self.xbf).view(), "step"), [])
        # A part given views alone: its STEP is written, carrying no PMI, and the viewer offers it.
        report = self.build(VIEWS_ALONE)
        self.assertEqual(report["pmi"], {"annotations": 0, "problems": []})
        structure = document.Loaded(self.xbf).structure()
        self.assertEqual((structure["pmi"], [view["name"] for view in structure["pmi_views"]]), ([], ["iso", "top"]))
        self.assertEqual(pmi.read(self.step), [])
        [step_row] = [row for row in viewer.options(export.Source.read(self.xbf)) if row["format"] == "step"]
        self.assertEqual((step_row["reason"], step_row["pmi"]), (None, False))


# A plate with a hole through it, datums A and B on its bottom and front, the hole's size, and
# ``{more}``: values ILLUSTRATIVE.
REQUIREMENTS = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
    body.label = "plate"
    bottom, top = body.faces().sort_by(bd.Axis.Z)[0], body.faces().sort_by(bd.Axis.Z)[-1]
    front, left = body.faces().sort_by(bd.Axis.Y)[0], body.faces().sort_by(bd.Axis.X)[0]
    hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return pmi.annotate(
        body,
        pmi.datum("A", bottom),
        pmi.datum("B", front),
        pmi.diameter("hole-size", hole, tolerance=pmi.plus_minus(0.1, 0)),
        {more}
    )
'''
# The hole located: datum C on the left face, and the hole's position to A|B|C.
LOCATED = 'pmi.datum("C", left), pmi.position("hole-position", hole, 0.1, datums=["A", "B", "C"]),'
# A requirement of each conflict: B named by no frame; the hole's limits, which its measured 10 mm
# lies outside, and which miss its size's 10.0–10.1; a flatness wider than the general profile on the
# top, and one wider than the left face's own profile.
EACH_CONFLICT = '''pmi.diameter("hole-limits", hole, tolerance=pmi.limits(9.9, 9.95)),
        pmi.flatness("top-flatness", top, 0.6),
        pmi.profile("left-profile", left, 0.2),
        pmi.flatness("left-flatness", left, 0.3),
        pmi.general_profile("general", 0.5, datums=["A"]),'''


def requirements(more: str) -> str:
    return REQUIREMENTS.replace("{more}", more)


class CoverageTest(_Folder):
    def served(self) -> dict:
        """The structure the last build served, after checking the file serves the same coverage."""
        structure = engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure
        self.assertEqual(structure["pmi_coverage"], document.Loaded(self.xbf).structure()["pmi_coverage"])
        return structure

    def test_faces_nothing_controls_are_listed(self) -> None:
        report = self.build(requirements(LOCATED))
        loaded = document.Loaded(self.xbf)
        structure = self.served()
        [found] = structure["pmi_coverage"]
        self.assertEqual((found["part"], found["conflicts"]), (0, []))
        # The six faces of the box, sorted: the hole has a size and a position; a datum is no requirement.
        faces = pmi._faces(loaded.prototypes[0].shape)
        planes = [at for at in range(1, faces.Extent() + 1) if pmi._surface(faces.FindKey(at))[0] == "plane"]
        self.assertEqual(len(planes), 6)
        self.assertEqual(found["uncovered"], sorted(found["uncovered"]))
        self.assertEqual(sorted(_ordinal(loaded, ref) for ref in found["uncovered"]), planes)
        self.assertEqual(report["pmi"]["coverage"], [{"part": "plate", "uncovered": found["uncovered"],
                                                      "conflicts": []}])
        # Pure: of a part's entries and its faces alone, in any order.
        hole = _by_id(structure["pmi"])["hole-size"]["refs"][0]["ref"]
        self.assertEqual(pmi.coverage(structure["pmi"], [hole, *reversed(found["uncovered"])]),
                         {"uncovered": found["uncovered"], "conflicts": []})

    def test_a_general_profile_covers_them(self) -> None:
        # A's own flatness, and a general profile to A of every other face nothing controls.
        general = 'pmi.flatness("bottom-flatness", bottom, 0.05), pmi.general_profile("general", 0.5, datums=["A"]),'
        report = self.build(requirements(LOCATED + general))
        self.assertEqual(self.served()["pmi_coverage"], [{"part": 0, "uncovered": [], "conflicts": []}])
        self.assertNotIn("coverage", report["pmi"])
        # Profiled to A|B|C, it leaves the datum features it names to their own control: B and C have none.
        report = self.build(requirements(LOCATED + general.replace('["A"]', '["A", "B", "C"]')))
        structure = self.served()
        found = _by_id(structure["pmi"])
        named = sorted(found[letter]["refs"][0]["ref"] for letter in "BC")
        self.assertEqual(structure["pmi_coverage"], [{"part": 0, "uncovered": named, "conflicts": []}])
        self.assertEqual(report["pmi"]["coverage"], [{"part": "plate", "uncovered": named, "conflicts": []}])

    def test_a_basic_dimension_covers_no_face(self) -> None:
        """A basic dimension is no requirement: the position it locates covers the hole, and the
        datum features it starts from (B, C) still want controls of their own, as A does."""
        basics = 'pmi.basic("hole-from-B", front, hole), pmi.basic("hole-from-C", left, hole),'
        general = 'pmi.general_profile("general", 0.5, datums=["A", "B", "C"]),'
        self.build(requirements(LOCATED + basics + general))
        structure = self.served()
        found = _by_id(structure["pmi"])
        named = sorted(found[letter]["refs"][0]["ref"] for letter in "ABC")
        self.assertEqual(structure["pmi_coverage"], [{"part": 0, "uncovered": named, "conflicts": []}])
        # Each datum feature given a flatness of its own: every face has a requirement.
        flatness = "".join(f'pmi.flatness("{letter}-flatness", {face}, 0.05),'
                           for letter, face in (("A", "bottom"), ("B", "front"), ("C", "left")))
        report = self.build(requirements(LOCATED + basics + general + flatness))
        self.assertEqual(self.served()["pmi_coverage"], [{"part": 0, "uncovered": [], "conflicts": []}])
        self.assertNotIn("coverage", report["pmi"])

    def test_each_conflict_is_said(self) -> None:
        self.build(requirements(EACH_CONFLICT))
        structure = self.served()
        [found] = structure["pmi_coverage"]
        self.assertEqual(found["conflicts"], [
            {"kind": "unused_datum", "ids": ["B"],
             "problem": "datum B is in no tolerance's frame: name it where a requirement is measured from it, or "
                        "remove it"},
            {"kind": "outside_limits", "ids": ["hole-limits"],
             "problem": "the diameter measures 10 mm, outside its limits 9.90–9.95: model it within them, or correct "
                        "the limits"},
            {"kind": "apart", "ids": ["hole-size", "hole-limits"],
             "problem": "two diameters of the same face whose zones do not meet, 10.0–10.1 and 9.90–9.95: no part "
                        "holds both; keep the one meant"},
            {"kind": "form_over_profile", "ids": ["top-flatness", "general"],
             "problem": "flatness 0.6 is wider than the surface profile 0.5 on its face, which holds its form within "
                        "0.5 already: make the flatness narrower than the profile, or remove it"},
            {"kind": "form_over_profile", "ids": ["left-flatness", "left-profile"],
             "problem": "flatness 0.3 is wider than the surface profile 0.2 on its face, which holds its form within "
                        "0.2 already: make the flatness narrower than the profile, or remove it"},
        ])
        # Every requirement holds as written: each is ok, and the faces left are A's alone (the general
        # profile leaves the datum it names to its own control).
        self.assertTrue(all(entry["status"] == "ok" for entry in structure["pmi"]))
        self.assertEqual(found["uncovered"], [_by_id(structure["pmi"])["A"]["refs"][0]["ref"]])

    def test_a_note_is_unlinked_only_when_every_link_is_broken(self) -> None:
        """Review Focus 2: a flag note linked to a face or an annotation that holds is linked; one whose
        every face and annotation is broken is linked to nothing; a general note names nothing to break."""
        def unlinked() -> list[dict]:
            """The xbf's: a build whose STEP is refused has written it, but keeps no document of its own."""
            return [conflict for found in document.Loaded(self.xbf).structure()["pmi_coverage"]
                    for conflict in found["conflicts"] if conflict["kind"] == "unlinked_note"]

        self.build(notes())
        self.assertEqual(unlinked(), [])
        # Its face gone, the diameter it names holds.
        self.build(notes(mask="'face 99'"))
        self.assertEqual(_by_id(pmi.read(self.xbf))["mask"]["status"], "missing")
        self.assertEqual(unlinked(), [])
        # The diameter it names broken, its face holds (the STEP is refused for the diameter, not the note).
        self.build(notes(hole="'face 99'", mask=HOLE), ok=False)
        self.assertEqual(unlinked(), [])
        # The hole removed: its face and the diameter both gone, it keeps its number and is said.
        loaded = document.Loaded(self.xbf)
        faces = pmi._faces(loaded.prototypes[0].shape)
        [ordinal] = [at for at in range(1, faces.Extent() + 1) if pmi._surface(faces.FindKey(at))[0] == "cylinder"]
        name = loaded.prototypes[0].face_names[ordinal]
        report = self.build(notes(hole=repr(name), cut="pass"), ok=False)
        self.assertEqual(unlinked(), [{"kind": "unlinked_note", "ids": ["mask"],
                                       "problem": "Note 3 is linked to nothing: every face and annotation it names is "
                                                  "broken; point it at what it is for, or remove it"}])
        self.assertIn({"kind": "unlinked_note", "ids": ["mask"], "problem": unlinked()[0]["problem"]},
                      report["pmi"]["coverage"][0]["conflicts"])

    def test_the_build_warns_and_never_fails(self) -> None:
        said: list[str] = []
        report = self.build(requirements(EACH_CONFLICT), log=said)
        self.assertEqual(report["pmi"]["problems"], [])
        self.assertTrue(self.step.is_file())
        [found] = self.served()["pmi_coverage"]
        self.assertEqual(report["pmi"]["coverage"], [{"part": "plate", "uncovered": found["uncovered"],
                                                      "conflicts": found["conflicts"]}])
        self.assertEqual([line for line in said if line.startswith("warning: pmi:")],
                         [f"warning: pmi: plate: 1 face has no requirement: {found['uncovered'][0]}"]
                         + [f"warning: pmi: plate: {', '.join(conflict['ids'])}: {conflict['problem']}"
                            for conflict in found["conflicts"]])
        said.clear()
        self.build(requirements(LOCATED), log=said)
        [found] = self.served()["pmi_coverage"]
        self.assertEqual([line for line in said if line.startswith("warning: pmi:")],
                         [f"warning: pmi: plate: 6 faces have no requirement: {', '.join(found['uncovered'])}"])

    def test_a_part_with_no_pmi_says_nothing(self) -> None:
        # An assembly of an annotated base and a pin given no PMI: the base's coverage alone.
        report = self.build('''
import build123d as bd
from cadgen.engine import pmi, xbf


@xbf(out="XBF/pmi_plate.xbf")
def pmi_plate():
    base = bd.Box(100, 60, 10)
    base.label = "base"
    base = pmi.annotate(base, pmi.datum("A", base.faces().sort_by(bd.Axis.Z)[0]),
                        pmi.flatness("base-top", base.faces().sort_by(bd.Axis.Z)[-1], 0.02))
    pin = bd.Cylinder(3, 20).moved(bd.Pos(30, 0, 15))
    pin.label = "pin"
    return bd.Compound(children=[base, pin], label="fixture")
''')
        structure = self.served()
        names = [prototype["name"] for prototype in structure["prototypes"]]
        self.assertEqual([names[found["part"]] for found in structure["pmi_coverage"]], ["base"])
        self.assertEqual([(found["part"], len(found["uncovered"]), [conflict["ids"] for conflict in found["conflicts"]])
                          for found in report["pmi"]["coverage"]], [("base", 5, [["A"]])])
        # A part given views alone has no requirement to cover, and a model given no PMI says nothing.
        report = self.build(VIEWS_ALONE)
        self.assertEqual((report["pmi"], self.served()["pmi_coverage"]), ({"annotations": 0, "problems": []}, []))
        report = self.build('''
import build123d as bd
from cadgen.engine import xbf


@xbf(out="XBF/pmi_plate.xbf")
def pmi_plate():
    return bd.Box(100, 60, 10)
''')
        self.assertNotIn("pmi", report)
        self.assertNotIn("pmi_coverage", document.Loaded(self.xbf).structure())


# A plate whose one variable ``cut`` is a round hole and then a square pocket: the name the hole's face
# gets from it passes to a flat side of the square, parallel to the left face (the viewer's v3).
CUT = '''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    cut = {cut}
    body = body - cut
    body.label = "plate"
    left = body.faces().sort_by(bd.Axis.X)[0]
    return pmi.annotate(body, pmi.datum("C", left), pmi.basic("hole-from-left", left, {hole}))
'''
ROUND, SQUARE = "bd.Cylinder(5, 10)", "bd.Box(12, 12, 10)"


class FaceKindTest(_Folder):
    def hole_name(self) -> str:
        """The round hole's element name, as the served document names it."""
        self.build(CUT.format(cut=ROUND, hole="body.faces().filter_by(bd.GeomType.CYLINDER)[0]"))
        loaded = document.Loaded(self.xbf)
        faces = pmi._faces(loaded.prototypes[0].shape)
        [ordinal] = [at for at in range(1, faces.Extent() + 1) if pmi._surface(faces.FindKey(at))[0] == "cylinder"]
        return loaded.prototypes[0].face_names[ordinal]

    def named(self, cut: str, name: str, *, ok: bool | None = True) -> dict:
        return self.build(CUT.format(cut=cut, hole=repr(name)), ok=ok)

    def test_a_name_that_comes_to_name_another_kind_of_face_is_warned(self) -> None:
        name = self.hole_name()
        report = self.named(ROUND, name)
        self.assertEqual(report["pmi"]["problems"], [])
        self.assertEqual(_by_id(pmi.read(self.xbf))["hole-from-left"]["dimension"]["nominal"]["value"], 50.0)
        # The hole made a square: the name now names a flat side 44 from the left face. The build says
        # so, as a warning of its report and of the structure it serves; the document is the code's.
        report = self.named(SQUARE, name)
        self.assertEqual(report["pmi"]["problems"], [])
        [warning] = report["pmi"]["warnings"]
        said = f"{name} named a cylinder face on the last build and names a plane face now"
        self.assertTrue(warning.startswith(f"plate/hole-from-left: {said}"), warning)
        served = _by_id(engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure["pmi"])
        [text] = served["hole-from-left"]["warnings"]
        self.assertTrue(text.startswith(said), text)
        entry = _by_id(pmi.read(self.xbf))["hole-from-left"]
        self.assertEqual((entry["status"], entry["dimension"]["nominal"]["value"], entry["warnings"]), ("ok", 44.0, []))

    def test_after_a_restart_the_saved_document_is_the_last_build(self) -> None:
        name = self.hole_name()
        self.named(ROUND, name)
        engine_build._WRITTEN.clear()  # a fresh process: nothing of the last build but its xbf
        report = self.named(SQUARE, name)
        self.assertEqual([warning.split(":")[0] for warning in report["pmi"]["warnings"]], ["plate/hole-from-left"])

    def test_the_document_is_the_codes_whatever_was_built_before(self) -> None:
        """The same code and closure make the same xbf, built fresh or after the round hole: it holds
        what the code says and this build's geometry resolves, no status, no word of a previous build."""
        name = self.hole_name()
        self.named(ROUND, name)
        self.named(SQUARE, name, ok=None)
        after = self.xbf.read_bytes()
        self.xbf.unlink()
        engine_build._WRITTEN.clear()
        self.named(SQUARE, name, ok=None)
        self.assertEqual(self.xbf.read_bytes(), after)
        loaded = document.Loaded(self.xbf)
        for record in pmi.records_of_document(loaded.doc, loaded.prototypes, loaded.name):
            self.assertEqual(set(record["extra"]), {"schema", "id", "kind", "label", "presentation", "refs", "unlinked"})

    def test_the_warning_is_the_last_builds_alone(self) -> None:
        name = self.hole_name()
        self.named(ROUND, name)
        self.named(SQUARE, name)
        report = self.named(SQUARE, name)  # built again, unchanged: its last build named the plane
        self.assertNotIn("warnings", report["pmi"])

    def test_a_face_the_code_selects_is_not_held_to_its_kind(self) -> None:
        """A build123d Face is what the code's own selection picks each build: never warned of."""
        self.build(CUT.format(cut=ROUND, hole="body.faces().sort_by(bd.Axis.X)[-1]"))
        report = self.build(CUT.format(cut=ROUND, hole="body.faces().filter_by(bd.GeomType.CYLINDER)[0]"))
        self.assertEqual(_but_coverage(report), {"annotations": 2, "problems": []})


class AssemblyTest(_Folder):
    def test_each_part_of_an_assembly_carries_its_own_pmi_once_however_often_it_is_placed(self) -> None:
        self.build('''
import build123d as bd
from cadgen.engine import pmi, step, xbf


def pin():
    body = bd.Cylinder(3, 20)
    body.label = "pin"
    return pmi.annotate(body, pmi.diameter("pin-diameter", body.faces().filter_by(bd.GeomType.CYLINDER)[0],
                                           tolerance=pmi.plus_minus(0, -0.01)))


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    base = bd.Box(100, 60, 10)
    base.label = "base"
    base = pmi.annotate(base, pmi.datum("A", base.faces().sort_by(bd.Axis.Z)[0]),
                        pmi.flatness("base-top", base.faces().sort_by(bd.Axis.Z)[-1], 0.02))
    first, second = pin().moved(bd.Pos(-30, 0, 15)), pin().moved(bd.Pos(30, 0, 15))
    first.label, second.label = "pin", "pin"
    return bd.Compound(children=[base, first, second], label="fixture")
''')
        loaded = document.Loaded(self.xbf)
        structure = loaded.structure()
        found = _by_id(structure["pmi"])
        self.assertEqual(sorted(found), ["A", "base-top", "pin-diameter"])
        self.assertTrue(all(entry["status"] == "ok" for entry in found.values()))
        names = [prototype["name"] for prototype in structure["prototypes"]]
        self.assertEqual(names[found["A"]["part"]], "base")
        self.assertEqual(names[found["pin-diameter"]["part"]], "pin")
        self.assertEqual(found["pin-diameter"]["dimension"]["nominal"]["value"], 6.0)
        self.assertEqual(found["pin-diameter"]["dimension"]["tolerance"], {"type": "plus_minus", "upper": 0.0, "lower": -0.01})
        self.assertTrue(found["pin-diameter"]["refs"][0]["ref"].startswith("fixture/pin.1/"), found["pin-diameter"]["refs"])
        self.assertEqual(_face(loaded, found["pin-diameter"]), ("cylinder", {"radius": 3.0}))
        # The STEP: each annotation once, on the part's own face.
        report = ap242.report(self.step)
        self.assertEqual(report["problems"], [])
        self.assertEqual([datum["identification"] for datum in report["datums"]], ["A"])
        [size] = report["dimensions"]
        self.assertEqual((size["nominal"]["value"], size["tolerance"]["lower"], size["tolerance"]["upper"]), (6.0, -0.01, 0.0))
        self.assertEqual(size["features"][0]["surface"]["radius"], 3.0)
        [flatness] = report["tolerances"]
        self.assertEqual((flatness["entity"], flatness["magnitude"]["value"], flatness["magnitude"]["unit"]),
                         ("FLATNESS_TOLERANCE", 0.02, "mm"))
        # OCCT's reader finds a datum through the tolerances naming it only: A, named by none, is in
        # the file (above) but not in what OCCT reads back.
        self.assertEqual(sorted(entry["kind"] for entry in pmi.read(self.step)), ["dimension", "geometric_tolerance"])

    def test_an_annotation_linked_to_nothing_keeps_its_part(self) -> None:
        """Its presentation is in its part's frame: a broken callout of a placed pin is the pin's."""
        self.build('''
import build123d as bd
from cadgen.engine import pmi, xbf


@xbf(out="XBF/pmi_plate.xbf")
def pmi_plate():
    base = bd.Box(100, 60, 10)
    base.label = "base"
    base = pmi.annotate(base, pmi.datum("A", base.faces().sort_by(bd.Axis.Z)[0]))
    pin = bd.Cylinder(3, 20)
    pin.label = "pin"
    pin = pmi.annotate(pin, pmi.diameter("pin-diameter", "face 9", presentation=pmi.place((3, 0, 0), (10, 0, 0))))
    placed = pin.moved(bd.Pos(30, 0, 15))
    placed.label = "pin"
    return bd.Compound(children=[base, placed], label="fixture")
''')
        structure = document.Loaded(self.xbf).structure()
        entry = _by_id(structure["pmi"])["pin-diameter"]
        self.assertEqual(entry["status"], "missing")
        self.assertEqual(structure["prototypes"][entry["part"]]["name"], "pin")
        served = engine_build.held(self.folder / "pmi_plate.py", "pmi_plate").structure["pmi"]
        self.assertEqual(served, structure["pmi"])


class UnitsTest(_Folder):
    def test_a_tolerance_with_no_dimension_beside_it_is_in_millimetres(self) -> None:
        """OCCT's writer takes the GD&T unit from the first dimension and, with none, writes a bare
        metre: the export puts the millimetre back (``export.step._pmi_records``)."""
        self.build('''
import build123d as bd
from cadgen.engine import pmi, step, xbf


@xbf(out="XBF/pmi_plate.xbf")
@step(out="pmi_plate.step")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    body.label = "plate"
    return pmi.annotate(body, pmi.flatness("top", body.faces().sort_by(bd.Axis.Z)[-1], 0.05))
''')
        [tolerance] = ap242.report(self.step)["tolerances"]
        self.assertEqual((tolerance["magnitude"]["value"], tolerance["magnitude"]["unit"]), (0.05, "mm"))
        self.assertNotIn(b"SI_UNIT($,.METRE.)", self.step.read_bytes())
        self.assertEqual(pmi.read(self.step)[0]["geometric_tolerance"]["value"], 0.05)


class RefTest(_Folder):
    def hole_name(self) -> str:
        """The hole's element name, as the served document names it."""
        self.build(NAMED.format(cut="body = body - bd.Cylinder(5, 10)", ref="face 1"), ok=False)
        loaded = document.Loaded(self.xbf)
        faces = pmi._faces(loaded.prototypes[0].shape)
        [ordinal] = [at for at in range(1, faces.Extent() + 1) if pmi._surface(faces.FindKey(at))[0] == "cylinder"]
        return loaded.prototypes[0].face_names[ordinal]

    def test_a_named_ref_resolves_and_a_lost_one_is_missing_and_kept(self) -> None:
        hole = self.hole_name()
        report = self.build(NAMED.format(cut="body = body - bd.Cylinder(5, 10)", ref=hole))
        self.assertEqual(report["pmi"]["problems"], [])
        found = _by_id(pmi.read(self.xbf))
        self.assertEqual(found["hole-diameter"]["refs"][0]["written"], hole)
        self.assertEqual(found["hole-diameter"]["dimension"]["nominal"]["value"], 10.0)
        # The hole removed: the ref names nothing. The build says so, the xbf keeps the annotation
        # with its status and its tolerance, and the STEP refuses to drop it.
        report = self.build(NAMED.format(cut="pass", ref=hole), ok=False)
        self.assertEqual(report["pmi"]["problems"][0]["id"], "hole-diameter")
        self.assertEqual(report["pmi"]["problems"][0]["status"], "missing")
        self.assertIn("hole-diameter", report["error"])
        self.assertIn("a STEP would drop PMI", report["error"])
        kept = _by_id(pmi.read(self.xbf))["hole-diameter"]
        self.assertEqual(kept["status"], "missing")
        self.assertIn(f"no face {hole}", kept["problem"])
        self.assertEqual(kept["refs"][0]["ref"], hole)
        self.assertEqual(kept["dimension"], {"type": "diameter", "basic": False, "nominal": None,
                                             "tolerance": {"type": "plus_minus", "upper": 0.1, "lower": 0.0}})
        self.assertEqual(_by_id(pmi.read(self.xbf))["A"]["status"], "ok")

    def test_a_face_the_annotation_cannot_stand_on_is_invalid(self) -> None:
        report = self.build(NAMED.format(cut="body = body - bd.Cylinder(5, 10)", ref="face 1"), ok=False)
        [problem] = report["pmi"]["problems"]
        self.assertEqual((problem["id"], problem["status"]), ("hole-diameter", "invalid"))
        self.assertIn("is a plane face; a diameter is on a cylinder face", problem["problem"])

    def test_a_ref_naming_several_faces_is_ambiguous(self) -> None:
        faces = pmi._faces(__import__("build123d").Box(1, 1, 1).wrapped)
        found = pmi._ref({"role": "feature", "written": "f:box.twin.1", "face": None}, faces,
                         ["f:box.twin.1", "f:box.other.1", "f:box.twin.1"], {"box"})
        self.assertEqual((found.status, found.candidates), ("ambiguous", [1, 3]))
        found = pmi._ref({"role": "feature", "written": "box/f:box.other.1", "face": None}, faces,
                         ["f:box.twin.1", "f:box.other.1", "f:box.twin.1"], {"box"})
        self.assertEqual((found.status, found.ordinal), ("ok", 2))
        found = pmi._ref({"role": "feature", "written": "lid/f:box.other.1", "face": None}, faces,
                         ["f:box.twin.1", "f:box.other.1", "f:box.twin.1"], {"box"})
        self.assertEqual(found.status, "invalid")

    def test_a_shape_replaced_after_it_was_annotated_is_said(self) -> None:
        report = self.build('''
import build123d as bd
from cadgen.engine import pmi, xbf


@xbf(out="XBF/pmi_plate.xbf")
def pmi_plate():
    body = bd.Box(100, 60, 10)
    pmi.annotate(body, pmi.flatness("top", body.faces().sort_by(bd.Axis.Z)[-1], 0.05))
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), 2)
    return body
''')
        self.assertEqual(report["pmi"]["unattached"], ["top"])

    def test_each_model_of_a_script_says_only_the_annotations_its_own_body_lost(self) -> None:
        # The first model keeps its annotations: a run's record taken by its first report would
        # say the second's loss there.
        script = self.folder / "two.py"
        script.write_text(textwrap.dedent('''
            import build123d as bd
            from cadgen.engine import pmi, xbf


            @xbf(out="XBF/whole.xbf")
            def whole():
                body = bd.Box(100, 60, 10)
                return pmi.annotate(body, pmi.flatness("kept", body.faces().sort_by(bd.Axis.Z)[-1], 0.05))


            @xbf(out="XBF/lossy.xbf")
            def lossy():
                body = bd.Box(100, 60, 10)
                pmi.annotate(body, pmi.flatness("top", body.faces().sort_by(bd.Axis.Z)[-1], 0.05))
                return bd.fillet(body.edges().filter_by(bd.Axis.Z), 2)
        '''), encoding="utf-8")
        reports = {report["source"]["name"]: report for report in engine_build.build(script, None, cwd=self.folder)}
        self.assertEqual(reports["lossy"]["pmi"]["unattached"], ["top"])
        self.assertNotIn("unattached", reports["whole"]["pmi"])


class RefusedTest(_Folder):
    def test_what_is_not_supported_is_refused_by_name(self) -> None:
        import build123d as bd

        box = bd.Box(10, 10, 10)
        top = box.faces().sort_by(bd.Axis.Z)[-1]
        with self.assertRaisesRegex(pmi.PMIUnsupported, "perpendicularity is not written verified"):
            pmi.geometric("perp", "perpendicularity", top, 0.1, datums=["A"])
        with self.assertRaisesRegex(pmi.PMIUnsupported, "a radius dimension is not written verified"):
            pmi.dimension("r", "radius", top)
        with self.assertRaisesRegex(pmi.PMIUnsupported, "a tolerance is pmi.plus_minus"):
            pmi.diameter("d", top, tolerance={"type": "fit", "class": "H7"})
        with self.assertRaisesRegex(pmi.PMIUnsupported, "assembly-level PMI"):
            pmi.annotate(bd.Compound(children=[box]), pmi.flatness("f", top, 0.1))
        with self.assertRaisesRegex(pmi.PMIError, r"upper deviation is above its lower \(0.1\), not -0.1"):
            pmi.plus_minus(-0.1, 0.1)
        with self.assertRaisesRegex(pmi.PMIUnsupported, "one position per datum"):
            pmi.annotate(box, pmi.datum("A", top), pmi.datum("B", top),
                         pmi.position("p1", top, 0.1, datums=["A", "B"]), pmi.position("p2", top, 0.1, datums=["B", "A"]))

    def test_an_export_that_makes_the_document_again_is_refused(self) -> None:
        self.build(plate())
        with self.assertRaisesRegex(export.ExportRefused, "PMI annotation"):
            export.translate(self.xbf, "step", self.folder / "part.step", part="plate")
        with self.assertRaisesRegex(export.ExportRefused, "PMI annotation"):
            export.translate(self.xbf, "xbf", self.folder / "part.xbf", part="plate")
        # A mesh carries no PMI, as it carries no B-rep: written.
        export.translate(self.xbf, "stl", self.folder / "plate.stl")

    def test_an_xbf_made_again_is_refused_for_views_or_a_library_alone(self) -> None:
        """An xbf made again carries none of the code's PMI: views alone, or a notes library alone,
        would be lost as annotations would (law 17), so it is refused, naming them; a STEP carries
        neither, whole or not, and is written."""
        from cadgen.engine.export import viewer

        library = VIEWS_ALONE.replace('pmi.view("iso", camera="iso"), pmi.view("top", camera="top")',
                                      'library={"primer-mask": "Mask these features before coating with primer"}')
        for model, said in ((VIEWS_ALONE, r"plate holds 2 named view\(s\) \(iso, top\), and an xbf written from "
                                          r"it is a document made again, which carries none yet: export it as built, "
                                          r"whole"),
                            (library, r"plate holds a notes library \(primer-mask\), and an xbf written from it")):
            self.build(model)
            with self.assertRaisesRegex(export.ExportRefused, said):
                export.translate(self.xbf, "xbf", self.folder / "part.xbf", part="plate")
            self.assertFalse((self.folder / "part.xbf").exists())
            xbf_row = next(row for row in viewer.options(export.Source.read(self.xbf), part="plate")
                           if row["format"] == "xbf")
            self.assertTrue(xbf_row["pmi"])
            self.assertRegex(xbf_row["reason"], said)
            for part in (None, "plate"):
                export.translate(self.xbf, "step", self.folder / "again.step", part=part)
                self.assertTrue((self.folder / "again.step").is_file())


class _Foreign:
    """A document another system wrote: a box holding XCAF's GD&T, made by OCCT directly."""

    def __init__(self, shape: object) -> None:
        from OCP.UnitsMethods import UnitsMethods_LengthUnit_Millimeter
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        self.shape = shape
        self.doc = document._new_document()
        XCAFDoc_DocumentTool.SetLengthUnit_s(self.doc, 1.0, UnitsMethods_LengthUnit_Millimeter)  # as the engine's are
        self.shapes = XCAFDoc_DocumentTool.ShapeTool_s(self.doc.Main())
        self.tool = XCAFDoc_DocumentTool.DimTolTool_s(self.doc.Main())
        self.label = self.shapes.AddShape(shape.wrapped, False, False)

    def sub(self, element: object) -> object:
        from OCP.TDF import TDF_Label

        found = TDF_Label()
        self.shapes.AddSubShape(self.label, element.wrapped, found)
        return found

    def tolerance(self, kind: str, element: object, value: float, **set: object) -> object:
        """A tolerance of ``kind`` on ``element``, or on each of a list of them."""
        from OCP import XCAFDimTolObjects as X
        from OCP.TDF import TDF_LabelSequence
        from OCP.XCAFDoc import XCAFDoc_GeomTolerance

        at = self.tool.AddGeomTolerance()
        given = X.XCAFDimTolObjects_GeomToleranceObject()
        given.SetType(getattr(X, f"XCAFDimTolObjects_GeomToleranceType_{kind}"))
        given.SetValue(value)
        for name, argument in set.items():
            getattr(given, name)(*argument)
        XCAFDoc_GeomTolerance.Set_s(at).SetObject(given)
        elements = TDF_LabelSequence()
        for each in element if isinstance(element, list) else [element]:
            elements.Append(self.sub(each))
        self.tool.SetGeomTolerance(elements, at)
        return at

    def dimension(self, kind: str, elements: list, value: float, **set: object) -> object:
        from OCP import XCAFDimTolObjects as X
        from OCP.XCAFDoc import XCAFDoc_Dimension

        at = self.tool.AddDimension()
        given = X.XCAFDimTolObjects_DimensionObject()
        given.SetType(getattr(X, f"XCAFDimTolObjects_DimensionType_{kind}"))
        given.SetValue(value)
        for name, argument in set.items():
            getattr(given, name)(*argument)
        XCAFDoc_Dimension.Set_s(at).SetObject(given)
        self.tool.SetDimension(*map(self.sub, elements), at)
        return at

    def step(self, path: Path) -> Path:
        from cadgen.engine.export.step import write_document

        self.shapes.UpdateAssemblies()
        write_document(self.doc, path)
        return path

    def xbf(self, path: Path) -> Path:
        self.shapes.UpdateAssemblies()
        document.save(self.doc, path, compare=False)
        return path


def _meaning(entry: dict) -> tuple:
    """What an entry says, its id and refs' spelling apart."""
    return (entry["kind"], entry["status"], entry["xcaf_type"], entry.get("reason"),
            json.dumps({key: entry.get(key) for key in ("datum", "dimension", "geometric_tolerance", "values")},
                       sort_keys=True), [(ref["role"], ref["status"]) for ref in entry["refs"]])


class ForeignTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-pmi-foreign-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_pmi_this_module_does_not_model_is_listed_as_unsupported(self) -> None:
        """A STEP written with a cylindricity (XCAF's, by OCCT directly) reads back listed. (OCCT's
        writer drops a perpendicularity that names no datum, silently: hence a form tolerance.)"""
        import build123d as bd

        box = bd.Box(10, 10, 10)
        foreign = _Foreign(box)
        foreign.tolerance("Cylindricity", box.faces().sort_by(bd.Axis.Z)[-1], 0.2)
        [entry] = pmi.read(foreign.step(self.folder / "foreign.step"))
        self.assertEqual((entry["kind"], entry["xcaf_type"], entry["status"]),
                         ("unsupported", "XCAFDimTolObjects_GeomToleranceType_Cylindricity", "ok"))
        self.assertIn("cylindricity", entry["reason"])
        self.assertEqual(entry["values"]["value"], 0.2)

    def test_what_a_file_says_beyond_the_model_is_unsupported_with_why(self) -> None:
        """A flatness with a projected zone or a maximum value says more than a plain one: it is
        listed unsupported, saying why, never read as the plain one (limits with more: ``LimitsTest``).
        A nominal read from a file was measured by nothing here: its source is the file."""
        import build123d as bd
        from OCP import XCAFDimTolObjects as X

        body = bd.Box(20, 20, 10) - bd.Cylinder(4, 10)
        top, hole = body.faces().sort_by(bd.Axis.Z)[-1], body.faces().filter_by(bd.GeomType.CYLINDER)[0]
        foreign = _Foreign(body)
        foreign.dimension("Size_Diameter", [hole], 8.0, SetLowerTolValue=(0.0,), SetUpperTolValue=(0.1,))
        foreign.tolerance("Flatness", top, 0.2, SetZoneModifier=(X.XCAFDimTolObjects_GeomToleranceZoneModif_Projected,),
                          SetValueOfZoneModifier=(5.0,))
        foreign.tolerance("Flatness", top, 0.1, SetMaxValueModifier=(0.3,))
        plain, projected, capped = pmi.read(foreign.xbf(self.folder / "foreign.xbf"))
        self.assertEqual(plain["kind"], "dimension")
        self.assertEqual(plain["dimension"]["nominal"], {"value": 8.0, "unit": "mm", "source": "file"})
        self.assertEqual(plain["dimension"]["tolerance"], {"type": "plus_minus", "upper": 0.1, "lower": 0.0})
        self.assertEqual((projected["kind"], projected["xcaf_type"]), ("unsupported", "XCAFDimTolObjects_GeomToleranceType_Flatness"))
        self.assertIn("projected", projected["reason"])
        self.assertIn("maximum", capped["reason"])

    def test_a_vendor_step_converts_and_exports_its_pmi_as_read(self) -> None:
        """A vendor's STEP (the skill's vendor workflow): its xbf keeps the file's GD&T as read, and a
        STEP of either is written. A distance between two edges is no annotation on faces: listed,
        linked to its edges and kept, never refused and never drawn."""
        import build123d as bd

        box = bd.Box(10, 10, 10)
        foreign = _Foreign(box)
        foreign.tolerance("Flatness", box.faces().sort_by(bd.Axis.Z)[-1], 0.2)
        edges = box.edges().filter_by(bd.Axis.Z)
        foreign.dimension("Location_LinearDistance", [edges[0], edges[1]], 10.0)
        vendor = foreign.step(self.folder / "vendor.step")
        flatness, distance = sorted(pmi.read(vendor), key=lambda entry: entry["kind"])
        self.assertEqual((flatness["kind"], flatness["status"]), ("geometric_tolerance", "ok"))
        self.assertEqual((distance["kind"], distance["status"], distance["reason"]), ("unsupported", "ok", "linked to an edge"))
        self.assertEqual(distance["xcaf_type"], "XCAFDimTolObjects_DimensionType_Location_LinearDistance")
        self.assertTrue(all("/edge " in ref["ref"] and ref["status"] == "ok" for ref in distance["refs"]), distance["refs"])
        read = sorted(map(_meaning, pmi.read(vendor)))
        export.translate(vendor, "xbf", self.folder / "vendor.xbf")
        self.assertEqual(sorted(map(_meaning, pmi.read(self.folder / "vendor.xbf"))), read)
        for source in (vendor, self.folder / "vendor.xbf"):
            export.translate(source, "step", self.folder / "again.step")
            self.assertEqual(sorted(map(_meaning, pmi.read(self.folder / "again.step"))), read)

    def test_an_export_of_a_foreign_document_says_what_it_leaves_out(self) -> None:
        """A partial STEP is a document made again, which carries no PMI: written, and said."""
        import build123d as bd

        from cadgen.engine.worker import _export

        box = bd.Box(10, 10, 10)
        foreign = _Foreign(box)
        foreign.tolerance("Flatness", box.faces().sort_by(bd.Axis.Z)[-1], 0.2)
        vendor = foreign.step(self.folder / "vendor.step")
        said: list[str] = []
        part = self.folder / "part.step"
        _export({"source": {"path": str(vendor)}, "destinations": [str(part)], "part": document.Loaded(vendor).name},
                said.append)
        self.assertTrue(part.is_file())
        self.assertEqual([text for text in said if text.startswith("warning: pmi:")],
                         ["warning: pmi: part.step: geometric_tolerance-1 is not carried whole: a partial STEP is a "
                          "document made again, which carries no PMI"])


class FixtureTest(_Folder):
    def test_the_committed_fixture_is_a_fresh_builds_pmi(self) -> None:
        """``pmi_golden/pmi_plate.step`` says what a build of the plate says, to a reader of no OCCT;
        and ``pmi_golden/pmi_plate.pmi.json`` is the structure's ``pmi`` a viewer is served."""
        self.build(plate())
        if WRITE:
            shutil.copyfile(self.step, FIXTURE / "pmi_plate.step")
            shutil.copyfile(self.xbf, FIXTURE / "pmi_plate.xbf")
            (FIXTURE / "pmi_plate.pmi.json").write_text(json.dumps(pmi.read(self.xbf), indent=2) + "\n", encoding="utf-8")
        self.assertEqual(_said(ap242.report(FIXTURE / "pmi_plate.step")), _said(ap242.report(self.step)))
        served = json.loads((FIXTURE / "pmi_plate.pmi.json").read_text(encoding="utf-8"))
        self.assertEqual(served, pmi.read(self.xbf))
        self.assertEqual(served, pmi.read(FIXTURE / "pmi_plate.xbf"))


if __name__ == "__main__":
    unittest.main()
