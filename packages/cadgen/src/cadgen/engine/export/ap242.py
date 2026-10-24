"""AP242 semantic PMI read back from a STEP file without OCCT, and checked against a document's.

A viewer's STEP export is checked in the file it wrote (``verify``): this module reads the file
with a Part 21 tokenizer of its own, sharing no code with the engine's writer or OCCT's STEP
translator, and walks AP242's PMI entities as ISO 10303-242 and the CAx-IF Recommended Practices
for PMI define them:

- dimensions: ``DIMENSIONAL_SIZE`` / ``DIMENSIONAL_LOCATION``, their nominal from the
  ``DIMENSIONAL_CHARACTERISTIC_REPRESENTATION``'s ``SHAPE_DIMENSION_REPRESENTATION``, its
  limits (its items named ``'lower limit'`` and ``'upper limit'``), its descriptive notes (a basic
  dimension's ``'theoretical'``), and their ``PLUS_MINUS_TOLERANCE``'s ``TOLERANCE_VALUE``
  (lower, upper);
- datums: ``DATUM`` (its identification), the ``DATUM_FEATURE`` a ``SHAPE_ASPECT_RELATIONSHIP``
  ties to it;
- geometric tolerances: any ``*_TOLERANCE`` entity (simple or complex), its magnitude, its
  ``DATUM_SYSTEM``'s compartments in order, its ``TOLERANCE_ZONE``'s form;
- each annotation's geometry: the ``GEOMETRIC_ITEM_SPECIFIC_USAGE`` of its shape aspect, the
  ``ADVANCED_FACE`` it identifies (its name), and that face's surface: a ``PLANE`` (origin,
  normal) or a ``CYLINDRICAL_SURFACE`` (radius), another by its type; a tolerance on several
  faces is on a ``COMPOSITE_SHAPE_ASPECT``, each face's through the aspect a
  ``SHAPE_ASPECT_RELATIONSHIP`` relates to it;
- every measure's unit, from its unit entity (``SI_UNIT(.MILLI.,.METRE.)`` is mm).

It also says what is malformed for a strict reader: a measure written untyped where AP242's
``measure_value`` select needs its type, a reference to no record, and an entity it does not read.

``compare`` matches a document's PMI entries (``pmi.read``) one to one with what the file says,
without guessing identities: a face name the file uses twice, two parts reusing a face name, or a
datum letter written twice verifies nothing. It is a bounded check of the semantics this engine
writes, not an AP242 validator or a test of any importer.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen.engine import refs

# --- the file as records ---------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    id: int


@dataclass(frozen=True)
class Enum:
    name: str


@dataclass(frozen=True)
class Typed:
    type: str
    value: Any


UNSET = None
DERIVED = "*"

_REF = re.compile(r"#(\d+)")
_ENUM = re.compile(r"\.([A-Z_][A-Z0-9_]*)\.")
_POINT_NUMBER = re.compile(r"[-+]?\.?\d[\d.]*(?:[eE][-+]?\d+)?")
_NUMBER = re.compile(r"[-+]?\d+(\.\d*)?([eE][-+]?\d+)?")
_KEYWORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SCHEMA = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'")


def _tokens(text: str):
    at, end = 0, len(text)
    while at < end:
        char = text[at]
        if char.isspace():
            at += 1
        elif char == "'":
            close = at + 1
            while True:
                close = text.index("'", close)
                if close + 1 < end and text[close + 1] == "'":
                    close += 2
                    continue
                break
            yield ("str", text[at + 1:close].replace("''", "'"))
            at = close + 1
        elif char == "#":
            match = _REF.match(text, at)
            yield ("ref", int(match.group(1)))
            at = match.end()
        elif char == ".":
            match = _ENUM.match(text, at)
            if match:
                yield ("enum", match.group(1))
            else:
                match = _POINT_NUMBER.match(text, at)
                yield ("num", match.group(0))
            at = match.end()
        elif char in "-+0123456789":
            match = _NUMBER.match(text, at)
            yield ("num", match.group(0))
            at = match.end()
        elif char in "(),=;$*":
            yield (char, char)
            at += 1
        elif char == '"':
            close = text.index('"', at + 1)
            yield ("binary", text[at + 1:close])
            at = close + 1
        else:
            match = _KEYWORD.match(text, at)
            if not match:
                raise ValueError(f"unexpected {text[at:at + 20]!r}")
            yield ("kw", match.group(0).upper())
            at = match.end()


def _number(text: str) -> Any:
    return float(text) if any(char in text for char in ".eE") else int(text)


def _value(kind: str, text: Any) -> Any:
    if kind == "ref":
        return Ref(text)
    if kind == "enum":
        return Enum(text)
    if kind == "num":
        return _number(text)
    if kind == "$":
        return UNSET
    if kind == "*":
        return DERIVED
    return text  # a string, or binary


def _parameters(tokens: list, at: int) -> tuple[list, int]:
    """A parenthesised parameter list from ``tokens[at]`` (its ``(``): its values and the end."""
    if tokens[at][0] != "(":
        raise ValueError(f"a parameter list starts with '(', not {tokens[at]}")
    at += 1
    values: list = []
    if tokens[at][0] == ")":
        return values, at + 1
    while True:
        kind, value = tokens[at]
        if kind == "(":
            inner, at = _parameters(tokens, at)
            values.append(tuple(inner))
        elif kind == "kw":
            inner, at = _parameters(tokens, at + 1)
            values.append(Typed(value, inner[0] if len(inner) == 1 else tuple(inner)))
        else:
            values.append(_value(kind, value))
            at += 1
        kind = tokens[at][0]
        at += 1
        if kind == ")":
            return values, at
        if kind != ",":
            raise ValueError(f"parameters are separated by ',', not {tokens[at - 1]}")


def parse(text: str) -> dict[int, list[tuple[str, list]]]:
    """Every record of a Part 21 file's DATA section: its partial entities, each its type and
    parameters (one for a simple record, several for a complex one)."""
    body = text[text.index("DATA;") + 5:text.index("ENDSEC;", text.index("DATA;"))]
    records: dict[int, list[tuple[str, list]]] = {}
    for statement in _statements(body):
        tokens = list(_tokens(statement))
        if tokens[0][0] != "ref" or tokens[1][0] != "=":
            raise ValueError(f"a record starts '#n=': {statement[:60]!r}")
        number, at = tokens[0][1], 2
        if tokens[at][0] == "(":
            parts, at = [], at + 1
            while tokens[at][0] != ")":
                name = tokens[at][1]
                values, at = _parameters(tokens, at + 1)
                parts.append((name, values))
            records[number] = parts
        else:
            values, _end = _parameters(tokens, at + 1)
            records[number] = [(tokens[at][1], values)]
    return records


def _statements(body: str):
    """The DATA section's statements, each up to its ``;`` outside a string."""
    start, at, quoted = 0, 0, False
    while at < len(body):
        char = body[at]
        if char == "'":
            quoted = not quoted
        elif char == ";" and not quoted:
            statement = body[start:at].strip()
            if statement:
                yield statement
            start = at + 1
        at += 1


# --- the report --------------------------------------------------------------------------------

# A limit dimension's representation items (CAx-IF's value range), by name.
_LIMITS = ("lower limit", "upper limit")


class Report:
    def __init__(self, records: dict[int, list[tuple[str, list]]]) -> None:
        self.records = records
        self.problems: list[str] = []
        self.referrers: dict[int, list[int]] = {}
        for number, parts in records.items():
            for _type, values in parts:
                for ref in _refs(values):
                    self.referrers.setdefault(ref, []).append(number)
                    if ref not in records:
                        self.problems.append(f"#{number} refers to #{ref}, which is no record")

    def types(self, number: int) -> list[str]:
        return [name for name, _values in self.records.get(number, [])]

    def part(self, number: int, name: str) -> list:
        for found, values in self.records[number]:
            if found == name:
                return values
        raise KeyError(f"#{number} is no {name}: {self.types(number)}")

    def of_type(self, name: str) -> list[int]:
        return sorted(number for number, parts in self.records.items() if any(found == name for found, _ in parts))

    def referring(self, number: int, name: str) -> list[int]:
        return sorted(referrer for referrer in self.referrers.get(number, []) if name in self.types(referrer))

    # Units and measures.
    def unit(self, number: int) -> str:
        parts = dict(self.records[number])
        if "SI_UNIT" in parts:
            prefix, name = parts["SI_UNIT"]
            prefix = prefix.name if isinstance(prefix, Enum) else None
            base = name.name
            symbol = {"METRE": "m", "RADIAN": "rad", "STERADIAN": "sr"}.get(base, base.lower())
            prefixes = {"MILLI": "m", "CENTI": "c", "MICRO": "u", "KILO": "k", None: ""}
            return (prefixes[prefix] if prefix in prefixes else prefix.lower()) + symbol
        if "CONVERSION_BASED_UNIT" in parts:
            return parts["CONVERSION_BASED_UNIT"][0]
        return "+".join(parts)

    def measure(self, number: int) -> dict[str, Any]:
        """A measure-with-unit record: its value, unit, and the type it is written with."""
        values = None
        for name, given in self.records[number]:
            if name in ("MEASURE_WITH_UNIT", "LENGTH_MEASURE_WITH_UNIT", "PLANE_ANGLE_MEASURE_WITH_UNIT") and given:
                values = given
        if values is None:
            raise KeyError(f"#{number} holds no measure: {self.types(number)}")
        component, unit = values[0], values[1]
        typed = isinstance(component, Typed)
        if not typed:
            self.problems.append(f"#{number}: {self.types(number)} holds an untyped measure value ({component}); "
                                 "AP242's measure_value is a select and needs its type (LENGTH_MEASURE(...))")
        return {"value": float(component.value if typed else component), "unit": self.unit(unit.id),
                "type": component.type if typed else None}

    # Geometry.
    def face(self, aspect: int) -> dict[str, Any] | None:
        """What a shape aspect identifies: its usage's face, named, with its surface."""
        usages = self.referring(aspect, "GEOMETRIC_ITEM_SPECIFIC_USAGE")
        if len(usages) != 1:
            self.problems.append(f"#{aspect}: {len(usages)} GEOMETRIC_ITEM_SPECIFIC_USAGE (one is expected)")
            return None
        item = self.part(usages[0], "GEOMETRIC_ITEM_SPECIFIC_USAGE")[4].id
        if "ADVANCED_FACE" not in self.types(item):
            return {"item": self.types(item)}
        name, _bounds, geometry, same_sense = self.part(item, "ADVANCED_FACE")
        return {"face": f"#{item}", "name": name, "surface": self.surface(geometry.id),
                "same_sense": same_sense.name if isinstance(same_sense, Enum) else same_sense}

    def features(self, aspect: int) -> list[dict[str, Any] | None]:
        """What a toleranced shape aspect identifies: its face, or a ``COMPOSITE_SHAPE_ASPECT``'s
        faces, one through each aspect a ``SHAPE_ASPECT_RELATIONSHIP`` relates to it, in order."""
        if "COMPOSITE_SHAPE_ASPECT" not in self.types(aspect):
            return [self.face(aspect)]
        members = []
        for relation in self.referring(aspect, "SHAPE_ASPECT_RELATIONSHIP"):
            _name, _description, relating, related = self.part(relation, "SHAPE_ASPECT_RELATIONSHIP")
            if relating == Ref(aspect):
                members.append(related.id)
        if not members:
            self.problems.append(f"#{aspect}: a COMPOSITE_SHAPE_ASPECT that relates no shape aspect")
        return [self.face(member) for member in members]

    def surface(self, number: int) -> dict[str, Any]:
        kind = self.types(number)[0]
        values = self.part(number, kind)
        if kind == "PLANE":
            origin, normal = self.placement(values[1].id)
            return {"type": "plane", "origin": origin, "normal": normal}
        if kind == "CYLINDRICAL_SURFACE":
            origin, axis = self.placement(values[1].id)
            return {"type": "cylinder", "radius": float(values[2]), "origin": origin, "axis": axis}
        return {"type": kind.lower()}

    def placement(self, number: int) -> tuple[list[float], list[float]]:
        values = self.part(number, "AXIS2_PLACEMENT_3D")
        origin = [float(v) for v in self.part(values[1].id, "CARTESIAN_POINT")[1]]
        axis = [float(v) for v in self.part(values[2].id, "DIRECTION")[1]] if values[2] is not UNSET else [0.0, 0.0, 1.0]
        return origin, axis

    # PMI.
    def dimensions(self) -> list[dict[str, Any]]:
        found = []
        for kind in ("DIMENSIONAL_SIZE", "DIMENSIONAL_LOCATION"):
            for number in self.of_type(kind):
                values = self.part(number, kind)
                entry: dict[str, Any] = {"record": f"#{number}", "entity": kind}
                if kind == "DIMENSIONAL_SIZE":
                    entry["name"] = values[1]
                    entry["features"] = [self.face(values[0].id)]
                else:
                    entry["name"] = values[0]
                    entry["features"] = [self.face(values[2].id), self.face(values[3].id)]
                entry["nominal"] = self.nominal(number)
                entry["limits"] = self.limits(number)
                entry["notes"] = self.notes(number)
                entry["tolerance"] = self.plus_minus(number)
                found.append(entry)
        return found

    def _representations(self, dimension: int) -> list[int]:
        return [self.part(holder, "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION")[1].id
                for holder in self.referring(dimension, "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION")]

    def _role(self, item: int) -> str | None:
        """A representation item's name: what its value is (``'nominal value'``, ``'lower limit'``)."""
        names = [values[0] for name, values in self.records[item] if name == "REPRESENTATION_ITEM"]
        return names[0] if names else None

    def nominal(self, dimension: int) -> dict[str, Any] | None:
        for representation in self._representations(dimension):
            for item in self.part(representation, "SHAPE_DIMENSION_REPRESENTATION")[1]:
                if "DESCRIPTIVE_REPRESENTATION_ITEM" in self.types(item.id) or self._role(item.id) in _LIMITS:
                    continue  # a note (``notes``) or a limit (``limits``), not the value
                measure = self.measure(item.id)
                measure["role"] = self._role(item.id)
                return measure
        return None

    def limits(self, dimension: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """A dimension's limits, (lower, upper), each a measure: its representation's items named
        ``'lower limit'`` and ``'upper limit'`` (CAx-IF's), or None where it has none."""
        found = {}
        for representation in self._representations(dimension):
            for item in self.part(representation, "SHAPE_DIMENSION_REPRESENTATION")[1]:
                if self._role(item.id) in _LIMITS:
                    found[self._role(item.id)] = self.measure(item.id)
        if not found:
            return None
        if len(found) != 2:
            self.problems.append(f"#{dimension}: a dimension of one limit ({', '.join(found)}); limits are a lower "
                                 "and an upper")
            return None
        return found["lower limit"], found["upper limit"]

    def notes(self, dimension: int) -> list[list[str]]:
        """A dimension's descriptive items, [name, description] each: CAx-IF's dimension modifiers
        (5.3), ``['dimensional note', 'theoretical']`` for a basic dimension."""
        found = []
        for representation in self._representations(dimension):
            for item in self.part(representation, "SHAPE_DIMENSION_REPRESENTATION")[1]:
                if "DESCRIPTIVE_REPRESENTATION_ITEM" in self.types(item.id):
                    name, description = self.part(item.id, "DESCRIPTIVE_REPRESENTATION_ITEM")
                    found.append([name, description])
        return found

    def plus_minus(self, dimension: int) -> dict[str, Any] | None:
        for holder in self.referring(dimension, "PLUS_MINUS_TOLERANCE"):
            tolerance_value = self.part(holder, "PLUS_MINUS_TOLERANCE")[0].id
            lower, upper = self.part(tolerance_value, "TOLERANCE_VALUE")
            low, high = self.measure(lower.id), self.measure(upper.id)
            if low["unit"] != high["unit"]:
                self.problems.append(f"#{tolerance_value}: its lower and upper deviations are in different units "
                                     f"({low['unit']}, {high['unit']})")
            return {"lower": low["value"], "upper": high["value"], "unit": high["unit"],
                    "types": [low["type"], high["type"]]}
        return None

    def datums(self) -> list[dict[str, Any]]:
        found = []
        for number in self.of_type("DATUM"):
            values = self.part(number, "DATUM")
            features = []
            for relation in self.referring(number, "SHAPE_ASPECT_RELATIONSHIP"):
                relating = self.part(relation, "SHAPE_ASPECT_RELATIONSHIP")[2].id
                if "DATUM_FEATURE" in self.types(relating):
                    features.append(self.face(relating))
            found.append({"record": f"#{number}", "identification": values[4], "features": features})
        return found

    def tolerances(self) -> list[dict[str, Any]]:
        found = []
        for number, parts in sorted(self.records.items()):
            names = [name for name, _ in parts]
            kinds = [name for name in names if name.endswith("_TOLERANCE") and name not in
                     ("PLUS_MINUS_TOLERANCE", "GEOMETRIC_TOLERANCE")]
            if not kinds:
                if any(name.startswith("GEOMETRIC_TOLERANCE") for name in names):
                    self.problems.append(f"#{number}: a geometric tolerance of no characteristic this reads")
                continue
            supported = {kinds[0], "GEOMETRIC_TOLERANCE", "GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE"}
            for name in names:
                if name not in supported:
                    self.problems.append(f"#{number}: {name} is not read here, so its meaning is not checked")
            base = dict(parts).get("GEOMETRIC_TOLERANCE") or dict(parts)[kinds[0]]
            magnitude, aspect = base[2], base[3]
            entry: dict[str, Any] = {"record": f"#{number}", "entity": kinds[0],
                                     "magnitude": self.measure(magnitude.id), "datums": [], "zone": None,
                                     "features": self.features(aspect.id)}
            reference = dict(parts).get("GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE")
            for system in reference[0] if reference else ():
                for compartment in self.part(system.id, "DATUM_SYSTEM")[4]:
                    base_datum = self.part(compartment.id, "DATUM_REFERENCE_COMPARTMENT")[4]
                    entry["datums"].append(self.part(base_datum.id, "DATUM")[4] if isinstance(base_datum, Ref)
                                           else str(base_datum))
            for zone in self.referring(number, "TOLERANCE_ZONE"):
                form = self.part(zone, "TOLERANCE_ZONE")[5].id
                entry["zone"] = self.part(form, "TOLERANCE_ZONE_FORM")[0]
                for definition in self.referrers.get(zone, []):
                    entry.setdefault("zone_definitions", []).append(self.types(definition))
            found.append(entry)
        return found


def _refs(values: Any):
    if isinstance(values, Ref):
        yield values.id
    elif isinstance(values, Typed):
        yield from _refs(values.value)
    elif isinstance(values, (list, tuple)):
        for value in values:
            yield from _refs(value)


def report(path: Path, data: bytes | None = None) -> dict[str, Any]:
    """What a STEP file's PMI says: its schema, dimensions, datums and tolerances, the face names
    it uses more than once, and its problems. ``data`` is the file's bytes where they are read
    already (``verify``)."""
    text = (path.read_bytes() if data is None else data).decode("utf-8")
    found = Report(parse(text))
    schema = _SCHEMA.search(text.split("DATA;", 1)[0])
    result = {"file": path.name, "schema": schema.group(1) if schema else None,
              "dimensions": found.dimensions(), "datums": found.datums(), "tolerances": found.tolerances()}
    # Every face counts, annotated or not: another part can reuse an annotated face's name.
    names = Counter(found.part(number, "ADVANCED_FACE")[0] for number in found.of_type("ADVANCED_FACE"))
    result["ambiguousFaceNames"] = sorted(name for name, count in names.items() if count > 1)
    result["problems"] = sorted(set(found.problems))
    return result


# --- the check of an export --------------------------------------------------------------------


def _near(actual: Any, expected: Any) -> bool:
    return (isinstance(actual, (int, float)) and isinstance(expected, (int, float))
            and math.isfinite(actual) and math.isfinite(expected)
            and abs(actual - expected) <= 1e-9 * max(1, abs(actual), abs(expected)))


def _measure(actual: Any, expected: Any) -> bool:
    return (isinstance(actual, dict) and isinstance(expected, dict)
            and actual.get("unit") == expected.get("unit")
            and _near(actual.get("value"), expected.get("value")))


def _element(ref: str) -> str:
    """A canonical ref's element: the face's name, which the STEP writes on its ``ADVANCED_FACE``."""
    element = refs.parse(ref)[1][-1].element
    return element if isinstance(element, str) else f"{element[0]} {element[1]}"


def _dimension_matches(dimension: dict[str, Any], row: dict[str, Any]) -> bool:
    kind = dimension.get("type")
    if kind not in ("diameter", "distance") or row.get("name") != {"diameter": "diameter", "distance": "linear distance"}[kind]:
        return False
    nominal, tolerance = dimension.get("nominal"), dimension.get("tolerance")
    # A basic dimension carries AP242's 'theoretical' note (CAx-IF 5.3), and nothing else does.
    if bool(dimension.get("basic")) != (["dimensional note", "theoretical"] in (row.get("notes") or [])):
        return False
    actual = row.get("tolerance")
    if tolerance is not None and tolerance.get("type") == "limits":
        # Limits are sizes of their own: a file's serve no nominal (``nominal: null``), and are millimetres.
        unit = nominal.get("unit") if isinstance(nominal, dict) else "mm"
        return actual is None and _limits_match(tolerance, unit, row)
    if not isinstance(nominal, dict):
        return False
    if row.get("limits") is not None or not _measure(row.get("nominal"), nominal):
        return False
    if tolerance is None:
        return actual is None
    return (tolerance.get("type") == "plus_minus" and isinstance(actual, dict)
            and actual.get("unit") == nominal.get("unit")
            and _near(actual.get("lower"), tolerance.get("lower"))
            and _near(actual.get("upper"), tolerance.get("upper")))


def _limits_match(tolerance: dict[str, Any], unit: Any, row: dict[str, Any]) -> bool:
    """A dimension given limits against a row: the same two limits, in the nominal's unit. XCAF
    holds the limits alone, so the file's nominal value is their midpoint, never the one measured."""
    lower, upper, limits = tolerance.get("lower"), tolerance.get("upper"), row.get("limits")
    if not (isinstance(lower, (int, float)) and isinstance(upper, (int, float))
            and isinstance(limits, (list, tuple)) and len(limits) == 2):
        return False
    return (_measure(limits[0], {"value": lower, "unit": unit}) and _measure(limits[1], {"value": upper, "unit": unit})
            and _measure(row.get("nominal"), {"value": (lower + upper) / 2, "unit": unit}))


# The entity each characteristic the engine writes is written as.
_TOLERANCE_ENTITIES = {"flatness": "FLATNESS_TOLERANCE", "position": "POSITION_TOLERANCE",
                       "surface_profile": "SURFACE_PROFILE_TOLERANCE"}


def _tolerance_matches(tolerance: dict[str, Any], row: dict[str, Any]) -> bool:
    entity = _TOLERANCE_ENTITIES.get(tolerance.get("characteristic"))
    # The reader does not establish material modifiers or zones other than a diameter's.
    if entity is None or tolerance.get("modifier") or tolerance.get("zone") not in (None, "", "diameter"):
        return False
    return (row.get("entity") == entity
            and _measure(row.get("magnitude"), tolerance)
            and row.get("datums", []) == tolerance.get("datums", [])
            and row.get("zone") == ("cylindrical or circular" if tolerance.get("zone") == "diameter" else None))


def _matches(entry: dict[str, Any], row: dict[str, Any]) -> bool:
    given = entry.get("refs") or []
    if not given or any(not isinstance(ref.get("ref"), str) or ref.get("status", "ok") != "ok" for ref in given):
        return False
    if sorted(_element(ref["ref"]) for ref in given) != sorted(feature.get("name", "") for feature in row.get("features", [])):
        return False
    if entry["kind"] == "datum":
        letter = (entry.get("datum") or {}).get("letter")
        return bool(letter) and row.get("identification") == letter
    if entry["kind"] == "dimension":
        return _dimension_matches(entry.get("dimension") or {}, row)
    if entry["kind"] == "geometric_tolerance":
        return _tolerance_matches(entry.get("geometric_tolerance") or {}, row)
    return False


def _written_as_nothing(entry: dict[str, Any]) -> bool:
    """A general profile that covers no face: linked to nothing, so the writer writes no record of it."""
    return (entry.get("kind") == "geometric_tolerance" and entry.get("status") == "ok" and not entry.get("refs")
            and bool((entry.get("geometric_tolerance") or {}).get("general")))


def compare(entries: list[dict[str, Any]], found: dict[str, Any]) -> dict[str, Any]:
    """A document's PMI entries against a file's ``report``: how many match one record each, of
    how many, and why any does not. A general profile that covers no face matches no record, and
    is verified by none being left over. A note is the document's alone (a STEP carries none): it is
    neither expected nor counted."""
    entries = _carried(entries)
    problems = list(found.get("problems") or [])
    if not entries:
        problems.append("The model has no PMI to verify.")
    if not str(found.get("schema", "")).startswith("AP242_"):
        problems.append("The file does not declare AP242.")
    owners_of: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        for ref in entry.get("refs", []):
            if isinstance(ref.get("ref"), str):
                owners_of[_element(ref["ref"])].add(ref["ref"])
    if any(len(owners) > 1 for owners in owners_of.values()):
        problems.append("Different model parts reuse a face name; their exported associations cannot be verified.")
    ambiguous = found.get("ambiguousFaceNames")
    if not isinstance(ambiguous, list):
        problems.append("The reader did not establish whether exported face names are unique.")
    elif any(name in owners_of for name in ambiguous):
        problems.append("An exported face name is ambiguous across the geometry; its association cannot be verified.")
    letters = [datum.get("identification") for datum in found.get("datums", [])]
    if len(set(letters)) != len(letters):
        problems.append("Exported datum letters are repeated; their references cannot be verified.")
    result = {"matched": 0, "total": len(entries), "problems": problems}
    if problems:
        return result
    remaining = list(found.get("datums", [])) + list(found.get("dimensions", [])) + list(found.get("tolerances", []))
    for entry in entries:
        if _written_as_nothing(entry):
            result["matched"] += 1
            continue
        match = next((at for at, row in enumerate(remaining) if entry.get("status") == "ok" and _matches(entry, row)), None)
        if match is None:
            problems.append(f"{entry.get('label') or entry.get('id')}: values, units, datum order or face association "
                            "could not be verified.")
        else:
            remaining.pop(match)
            result["matched"] += 1
    if remaining:
        problems.append(f"{len(remaining)} exported annotations did not match the model.")
    return result


def _carried(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries a STEP carries: every one but the notes, the xbf's alone (``pmi.step_entries``)."""
    return [entry for entry in entries if entry.get("kind") != "note"]


def verify(entries: list[dict[str, Any]], target: Path) -> dict[str, Any]:
    """``compare`` of the file at ``target``, with the SHA-256 of the bytes checked, read once: the
    result belongs to those bytes, whatever the viewer opens next. A check the reader cannot
    complete counts what ``compare`` would, the notes never."""
    data = target.read_bytes()
    try:
        result = compare(entries, report(target, data))
    except Exception as error:  # noqa: BLE001 - a file the reader cannot read is a failed check, never a failed export
        result = {"matched": 0, "total": len(_carried(entries)),
                  "problems": [f"The STEP reader could not complete the check: {error}"]}
    return {**result, "sha256": hashlib.sha256(data).hexdigest()}
