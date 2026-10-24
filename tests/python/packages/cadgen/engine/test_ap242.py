"""An exported file's requirements must match its source, without guessing identities
(``export/ap242.py``): the AP242 reader of no OCCT, and ``compare``/``verify`` of a document's PMI
against the file it wrote."""

from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.engine.export.ap242 import Report, compare, parse, report, verify

GOLDEN = Path(__file__).resolve().parent / "pmi_golden"


def fixtures() -> tuple[list[dict], dict]:
    """Three entries as a document serves them, and the report of a file that holds them."""
    entries = [
        {"id": "A", "kind": "datum", "status": "ok", "refs": [{"ref": "part/f:base.1"}], "datum": {"letter": "A"}},
        {"id": "bore", "kind": "dimension", "status": "ok", "refs": [{"ref": "part/f:bore.1"}],
         "dimension": {"type": "diameter", "nominal": {"value": 10, "unit": "mm"},
                       "tolerance": {"type": "plus_minus", "lower": 0, "upper": 0.05}}},
        {"id": "position", "kind": "geometric_tolerance", "status": "ok", "refs": [{"ref": "part/f:bore.1"}],
         "geometric_tolerance": {"characteristic": "position", "value": 0.1, "unit": "mm", "zone": "diameter",
                                 "datums": ["A"]}},
    ]
    found = {"schema": "AP242_TEST", "problems": [], "ambiguousFaceNames": [],
             "datums": [{"identification": "A", "features": [{"name": "f:base.1"}]}],
             "dimensions": [{"name": "diameter", "features": [{"name": "f:bore.1"}],
                             "nominal": {"value": 10, "unit": "mm"},
                             "tolerance": {"lower": 0, "upper": 0.05, "unit": "mm"}}],
             "tolerances": [{"entity": "POSITION_TOLERANCE", "features": [{"name": "f:bore.1"}],
                             "magnitude": {"value": 0.1, "unit": "mm"}, "zone": "cylindrical or circular",
                             "datums": ["A"]}]}
    return entries, found


class VerificationTest(unittest.TestCase):
    def test_reader_refuses_unchecked_exported_tolerance_extensions(self) -> None:
        records = parse((GOLDEN / "pmi_plate.step").read_text(encoding="utf-8"))
        number = next(number for number, parts in records.items() if any(name == "POSITION_TOLERANCE" for name, _ in parts))
        for extension in ("GEOMETRIC_TOLERANCE_WITH_MODIFIERS", "GEOMETRIC_TOLERANCE_WITH_MAXIMUM_TOLERANCE"):
            altered = copy.deepcopy(records)
            altered[number].append((extension, (("MAXIMUM_MATERIAL_REQUIREMENT",),)))
            reader = Report(altered)
            reader.tolerances()
            self.assertTrue(any(extension in problem for problem in reader.problems), reader.problems)

    def test_matches_and_detects_changed_values_units_faces_datums_and_extras(self) -> None:
        entries, found = fixtures()
        self.assertEqual(compare(entries, found), {"matched": 3, "total": 3, "problems": []})
        for collection, key, value in [("dimensions", "tolerance", {"lower": 0, "upper": 0.5, "unit": "mm"}),
                                       ("tolerances", "magnitude", {"value": 0.1, "unit": "m"}),
                                       ("datums", "features", [{"name": "f:wrong.1"}]),
                                       ("tolerances", "datums", ["B"])]:
            changed = copy.deepcopy(found)
            changed[collection][0][key] = value
            self.assertTrue(compare(entries, changed)["problems"])
        found["dimensions"] *= 2
        self.assertTrue(compare(entries, found)["problems"])

    def test_ambiguous_associations_fail_closed(self) -> None:
        entries, found = fixtures()
        for altered in [{**found, "ambiguousFaceNames": ["f:bore.1"]},
                        {key: value for key, value in found.items() if key != "ambiguousFaceNames"},
                        {**found, "datums": found["datums"] * 2},
                        {**found, "problems": ["Mixed deviation units"]},
                        {**found, "schema": "AUTOMOTIVE_DESIGN"}]:
            self.assertEqual(compare(entries, altered)["matched"], 0)
        other = copy.deepcopy(entries[1])
        other["refs"][0]["ref"] = "other/f:bore.1"
        self.assertEqual(compare(entries + [other], found)["matched"], 0)

    def test_unsupported_modifiers_and_empty_pmi_never_claim_success(self) -> None:
        entries, found = fixtures()
        entries[2]["geometric_tolerance"]["modifier"] = "maximum_material_condition"
        self.assertEqual(compare(entries, found)["matched"], 2)
        self.assertTrue(compare([], {**found, "datums": [], "dimensions": [], "tolerances": []})["problems"])

    def test_checks_the_provided_export_and_binds_result_to_its_bytes(self) -> None:
        entries, found = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "export.step"
            target.write_bytes(b"exported bytes")
            with patch("cadgen.engine.export.ap242.report", return_value=found) as reader:
                result = verify(entries, target)
            reader.assert_called_once_with(target, b"exported bytes")
            self.assertEqual(result["matched"], 3)
            self.assertEqual(result["sha256"], hashlib.sha256(b"exported bytes").hexdigest())
            with patch("cadgen.engine.export.ap242.report", side_effect=ValueError("unsupported syntax")):
                self.assertTrue(verify(entries, target)["problems"])

    def test_a_note_is_never_counted_even_where_the_check_fails(self) -> None:
        """A STEP carries no note: a failed check counts the GD&T alone, as a completed one does."""
        entries, _found = fixtures()
        note = {"id": "deburr", "kind": "note", "status": "ok", "refs": [],
                "note": {"number": 1, "text": "Break all sharp edges 0.2 max", "general": True, "annotations": []}}
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "export.step"
            target.write_bytes(b"exported bytes")
            with patch("cadgen.engine.export.ap242.report", side_effect=ValueError("unsupported syntax")):
                result = verify([entries[0], note], target)
        self.assertEqual((result["matched"], result["total"]), (0, 1))
        self.assertEqual(result["problems"], ["The STEP reader could not complete the check: unsupported syntax"])

    def test_the_committed_fixture_verifies_whole_basic_dimensions_included(self) -> None:
        """The plate's served PMI against its own exported STEP: every annotation, its two basic
        dimensions too (their 'theoretical' note), matched one to one."""
        from cadgen.engine import pmi

        entries = pmi.read(GOLDEN / "pmi_plate.xbf")
        self.assertEqual(sum(1 for entry in entries if (entry.get("dimension") or {}).get("basic")), 2)
        result = verify(entries, GOLDEN / "pmi_plate.step")
        self.assertEqual((result["matched"], result["total"], result["problems"]), (9, 9, []))

    def test_a_basic_flag_the_file_does_not_carry_is_not_verified(self) -> None:
        entries, found = fixtures()
        entries.append({"id": "hole-from-B", "kind": "dimension", "status": "ok",
                        "refs": [{"ref": "part/f:front.1"}, {"ref": "part/f:bore.1"}],
                        "dimension": {"type": "distance", "basic": True, "nominal": {"value": 30, "unit": "mm"},
                                      "tolerance": None}})
        row = {"name": "linear distance", "features": [{"name": "f:front.1"}, {"name": "f:bore.1"}],
               "nominal": {"value": 30, "unit": "mm"}, "tolerance": None, "notes": [["dimensional note", "theoretical"]]}
        self.assertEqual(compare(entries, {**found, "dimensions": found["dimensions"] + [row]})["matched"], 4)
        bare = {**row, "notes": []}  # the same distance with no 'theoretical' note: not the basic one modelled
        self.assertEqual(compare(entries, {**found, "dimensions": found["dimensions"] + [bare]})["matched"], 3)

    def test_limits_match_by_value_and_unit_and_never_as_a_plus_minus(self) -> None:
        """A dimension given limits matches a row of the same two limits in the nominal's unit, its
        nominal value their midpoint (XCAF holds the limits alone), and no plus-minus tolerance."""
        entries, found = fixtures()
        entries[1]["dimension"]["tolerance"] = {"type": "limits", "lower": 10.0, "upper": 10.05}
        row = found["dimensions"][0]
        row.update(tolerance=None, nominal={"value": 10.025, "unit": "mm"},
                   limits=({"value": 10.0, "unit": "mm"}, {"value": 10.05, "unit": "mm"}))
        self.assertEqual(compare(entries, found), {"matched": 3, "total": 3, "problems": []})
        for change in ({"limits": ({"value": 10.0, "unit": "mm"}, {"value": 10.1, "unit": "mm"})},
                       {"limits": ({"value": 10.0, "unit": "m"}, {"value": 10.05, "unit": "m"})},
                       {"limits": None, "tolerance": {"lower": 0, "upper": 0.05, "unit": "mm"}},
                       {"nominal": {"value": 10.0, "unit": "mm"}}):
            changed = copy.deepcopy(found)
            changed["dimensions"][0].update(change)
            self.assertEqual(compare(entries, changed)["matched"], 2, change)
        entries[1]["dimension"]["tolerance"] = {"type": "plus_minus", "lower": 0, "upper": 0.05}
        self.assertEqual(compare(entries, {**found, "dimensions": [{**row, "tolerance": {
            "lower": 0, "upper": 0.05, "unit": "mm"}, "nominal": {"value": 10, "unit": "mm"}}]})["matched"], 2)

    def test_reader_reads_a_dimensions_limits_beside_its_nominal(self) -> None:
        reader = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=DIMENSIONAL_SIZE($,'diameter');
          #2=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#1,#3);
          #3=SHAPE_DIMENSION_REPRESENTATION('',(#5,#4,#6),$);
          #4=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
              MEASURE_WITH_UNIT(POSITIVE_LENGTH_MEASURE(10.),#7) REPRESENTATION_ITEM('lower limit'));
          #5=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
              MEASURE_WITH_UNIT(POSITIVE_LENGTH_MEASURE(10.05),#7) REPRESENTATION_ITEM('upper limit'));
          #6=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
              MEASURE_WITH_UNIT(POSITIVE_LENGTH_MEASURE(10.025),#7) REPRESENTATION_ITEM('nominal value'));
          #7=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
          ENDSEC; END-ISO-10303-21;"""))
        self.assertEqual((reader.nominal(1)["value"], reader.nominal(1)["role"]), (10.025, "nominal value"))
        self.assertEqual([(bound["value"], bound["unit"]) for bound in reader.limits(1)], [(10.0, "mm"), (10.05, "mm")])
        self.assertEqual(reader.problems, [])

    def test_a_profile_matches_on_its_faces_in_any_order_and_on_no_other(self) -> None:
        entries, found = fixtures()
        entries.append({"id": "sides", "kind": "geometric_tolerance", "status": "ok",
                        "refs": [{"ref": "part/f:front.1"}, {"ref": "part/f:left.1"}, {"ref": "part/f:bore.1"}],
                        "geometric_tolerance": {"characteristic": "surface_profile", "value": 0.5, "unit": "mm",
                                                "zone": None, "datums": ["A"], "general": False}})
        row = {"entity": "SURFACE_PROFILE_TOLERANCE", "magnitude": {"value": 0.5, "unit": "mm"}, "zone": None,
               "datums": ["A"], "features": [{"name": "f:bore.1"}, {"name": "f:front.1"}, {"name": "f:left.1"}]}
        self.assertEqual(compare(entries, {**found, "tolerances": found["tolerances"] + [row]}),
                         {"matched": 4, "total": 4, "problems": []})
        for change in ({"features": row["features"][:2]}, {"features": row["features"] + [{"name": "f:top.1"}]},
                       {"entity": "FLATNESS_TOLERANCE"}, {"datums": []}, {"zone": "cylindrical or circular"}):
            self.assertEqual(compare(entries, {**found, "tolerances": found["tolerances"] + [{**row, **change}]})["matched"],
                             3, change)

    def test_reader_reads_each_face_of_a_composite_shape_aspect(self) -> None:
        """A tolerance on several faces is on a COMPOSITE_SHAPE_ASPECT, each face's own aspect related
        to it, as OCCT's writer writes it: every face read, in order."""
        reader = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=SURFACE_PROFILE_TOLERANCE('','',#2,#3);
          #2=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.5),#4);
          #3=COMPOSITE_SHAPE_ASPECT('','',#9,.T.);
          #4=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
          #5=SHAPE_ASPECT('','',#9,.T.);
          #6=SHAPE_ASPECT_RELATIONSHIP('',$,#3,#5);
          #7=GEOMETRIC_ITEM_SPECIFIC_USAGE('','',#5,#9,#20);
          #8=SHAPE_ASPECT('','',#9,.T.);
          #10=SHAPE_ASPECT_RELATIONSHIP('',$,#3,#8);
          #11=GEOMETRIC_ITEM_SPECIFIC_USAGE('','',#8,#9,#21);
          #9=PRODUCT_DEFINITION_SHAPE('','',$);
          #20=ADVANCED_FACE('f:front.1',(),#22,.T.);
          #21=ADVANCED_FACE('f:left.1',(),#22,.T.);
          #22=CONICAL_SURFACE('',$,1.,0.5);
          ENDSEC; END-ISO-10303-21;"""))
        [tolerance] = reader.tolerances()
        self.assertEqual(tolerance["entity"], "SURFACE_PROFILE_TOLERANCE")
        self.assertEqual([feature["name"] for feature in tolerance["features"]], ["f:front.1", "f:left.1"])
        self.assertEqual(reader.problems, [])
        empty = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=SURFACE_PROFILE_TOLERANCE('','',#2,#3);
          #2=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.5),#4);
          #3=COMPOSITE_SHAPE_ASPECT('','',$,.T.);
          #4=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
          ENDSEC; END-ISO-10303-21;"""))
        self.assertEqual(empty.tolerances()[0]["features"], [])
        self.assertTrue(any("relates no shape aspect" in problem for problem in empty.problems), empty.problems)

    def test_reader_checks_unannotated_face_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step = Path(temp) / "duplicate.step"
            step.write_text("ISO-10303-21; HEADER; FILE_SCHEMA(('AP242_TEST')); ENDSEC; DATA;\n"
                            "#1=ADVANCED_FACE('f:bore.1',(),$,.T.);\n"
                            "#2=ADVANCED_FACE('f:bore.1',(),$,.T.);\nENDSEC; END-ISO-10303-21;", encoding="utf-8")
            self.assertEqual(report(step)["ambiguousFaceNames"], ["f:bore.1"])

    def test_reader_checks_both_deviation_units(self) -> None:
        reader = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=PLUS_MINUS_TOLERANCE(#2,#3,$);
          #2=TOLERANCE_VALUE(#4,#5);
          #3=DIMENSIONAL_SIZE($,'diameter');
          #4=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(-0.2),#6);
          #5=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.2),#7);
          #6=SI_UNIT($,.METRE.);
          #7=SI_UNIT(.MILLI.,.METRE.);
          ENDSEC; END-ISO-10303-21;"""))
        reader.plus_minus(3)
        self.assertTrue(any("unit" in problem.lower() for problem in reader.problems))


if __name__ == "__main__":
    unittest.main()
