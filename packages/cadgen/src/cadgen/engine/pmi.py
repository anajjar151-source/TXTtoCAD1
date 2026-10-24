"""Semantic PMI: manufacturing requirements on a part's own faces, kept in its XCAF document
as XCAF's GD&T objects and written to STEP AP242 as AP242's semantic entities.

A model gives its part annotations, each on faces of that part, and returns the part::

    from cadgen.engine import pmi, step, xbf

    @xbf(out="XBF/plate.xbf")
    @step("plate.step")
    def plate():
        body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
        bottom = body.faces().sort_by(bd.Axis.Z)[0]
        top = body.faces().sort_by(bd.Axis.Z)[-1]
        hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
        return pmi.annotate(body,
            pmi.datum("A", bottom),
            pmi.distance("thickness", bottom, top, tolerance=pmi.plus_minus(0.2)),
            pmi.diameter("hole", hole, tolerance=pmi.plus_minus(0.1, 0)),
            pmi.flatness("top-flat", top, 0.05),
            pmi.position("hole-pos", hole, 0.1, datums=["A"]))

**What is held.** What the code says and what this build's geometry resolves, nothing else: XCAF's
``XCAFDimTolObjects`` objects on the GD&T tool's labels (``XCAFDoc_DimTolTool``) hold the kind,
values and units (millimetres, the document's) and link the annotation to the sub-shape labels of
the faces it is on; beside each, a ``TDF_Reference`` to its part's shape label and one cadgen
attribute (``EXTRA_GUID``, JSON of ``SCHEMA``) holding what XCAF has no place for: the author's id
and label, the kind, each ref as the code wrote it, the presentation, a general profile's flag, and
an annotation linked to nothing its values (XCAF gives values meaning only through geometry). The
id and the kind are in XCAF too (its semantic name, its object). No status, no problem and nothing
of a previous build is held: an annotation's status is derived where the document is read
(``records_of_document``), as a build derives it, and a general profile's faces with it. The STEP
writer reads the XCAF objects and writes AP242's semantic PMI
(``DIMENSIONAL_SIZE``/``DIMENSIONAL_LOCATION`` with ``PLUS_MINUS_TOLERANCE`` or their limits,
``DATUM``/``DATUM_FEATURE``, ``FLATNESS_TOLERANCE``, ``POSITION_TOLERANCE`` and
``SURFACE_PROFILE_TOLERANCE`` with their ``DATUM_SYSTEM``) on ``SHAPE_ASPECT``s whose
``GEOMETRIC_ITEM_SPECIFIC_USAGE`` names the face (a profile on several faces: on a
``COMPOSITE_SHAPE_ASPECT`` relating one such aspect per face). The cadgen attribute is not
written to a STEP.

**Notes** (``note``) are the xbf's alone: XCAF comments in its notes tool (``XCAFDoc_NotesTool``),
by one fixed user (``NOTE_USER``) with no timestamp, so the same code makes the same bytes; each
with the same ``TDF_Reference`` and cadgen attribute beside it (the id, label, presentation, refs
and the ids it names as written; the text is XCAF's). A general note names no face and no
annotation and is attached to its part's shape label; a flag note is attached to each face it is
on (``AddNoteToSubshape``, the sub-shape index the face's ordinal in its part's face map, where
the note is ``ok``) and to the GD&T label of each annotation it names. A note's faces resolve as
any ref does, on a face of any kind; one whose face is gone keeps its number and text, its status
saying so. Its number is derived where served: Note 1 is the part's general profile where it has
one, then each note in the code's order. OCCT's STEP writer writes no notes, so a STEP carries
none and is never refused for one (``step_entries``). A part's notes library (``annotate``'s
``library``: the project's notes by name, the dict its own module holds; cadgen ships none) is one
JSON attribute (``LIBRARY_GUID``) on its shape label, served as ``pmi_library``. A note this module
did not write (no cadgen attribute) is not read.

**Views** (``view``) are the xbf's alone too: a part's named views, the views its requirements are
walked through in (a front, a section, a detail; an iso view showing all). Each is seen down a camera
-- a preset's name, ``cadgen snapshot --camera``'s own table (``render/presets.py``), or
``camera(direction, up)``, ``direction`` from the part toward the eye as a preset's is --
orthographic, cut where it has a section (``section``: the viewer's Clip, ``{axis, at, invert}``),
showing the ids of its ``annotate`` call it names (every one where it names none) with its own
placements of them (``place``), all in its part's frame. Each is an XCAF view in the views tool
(``XCAFDoc_ViewTool``): parallel, looking along its direction reversed (XCAF's view direction is
the one looked along), its eye the part's box centre moved toward the eye by the box's diagonal,
its window that diagonal and its zoom 1; linked to its part's shape label and the GD&T labels it
shows, its section an XCAF clipping plane (``XCAFDoc_ClippingPlaneTool``) named for it; beside it
the same ``TDF_Reference`` and a cadgen attribute holding the view as the code gave it, which the
structure's ``pmi_views`` is served from. The notes it shows are that attribute's alone: OCCT's
``SetView`` files a view's notes under its clipping-plane link. OCCT's STEP writer writes no views,
so a STEP carries none and is never refused for one. An xbf made again from a document (one part
of it) carries no views, notes or library yet, and is refused for any of them, by name
(``refuse_dropped``). A view this module did not write is not read.

**Values.** A dimension's nominal is the geometry's, measured at document time: a cylinder's
diameter, the distance between two parallel planes. No nominal is typed in. A tolerance is held
only where the code gives one (``plus_minus``: signed deviations, upper above lower; ``limits``:
the least and the greatest size, absolute). XCAF holds a dimension's lower deviation as a
magnitude and the STEP writer negates it, so ``plus_minus(0.2)`` is written
``TOLERANCE_VALUE(-0.2, 0.2)``; the conversion is this module's, both ways. XCAF holds limits as a
dimension's two values in place of its nominal, its value then their midpoint, which the STEP
writer writes as the nominal value beside CAx-IF's ``'lower limit'`` and ``'upper limit'`` items:
the nominal of one the code made is measured again where its document is read, and one read from
a file has none (the file states limits; the midpoint XCAF rebuilds is no fact of it).

**References.** A ref is a face of the part annotated: a build123d ``Face`` of the shape given to
``annotate`` (numbered against it at once), or a ref in the engine's grammar (``refs``) -- an
element name (``f:plate.body.6``), the canonical ``owner/element`` ref a document serves, or an
ordinal (``face 7``). Element names are the engine's persistent naming (``kernel.trace``): a face
keeps its name across edits that do not change how it is made. Each build resolves every ref
against the part as built now: ``ok``; ``missing`` -- it names nothing (with what the name's atom
is called now, where anything is); ``ambiguous`` -- it names several faces (each listed); or
``invalid`` -- it names a face the annotation cannot stand on (a diameter on a plane, two planes
not parallel, a datum letter the part does not define). An annotation's status is its worst ref's.
One not ``ok`` is kept in the document, with its values and refs as written, and linked to no
geometry; the build reports it, and a STEP export refuses to drop it. A ref written as text that
names another kind of face than on the model's last build (a hole whose name passed to a flat side
of the cut that replaced it) is warned of (``warn``): the build's report and its served structure
say so, the document never.

**The general profile** (``general_profile``) is ASME Y14.5's "unless otherwise noted, all
surfaces": a surface profile of every face of its part that nothing else controls
(``otherwise_controlled``: a face with a size or location requirement of its own), computed by each
build from that build's annotations and geometry alone, never written in the code and never kept
from an earlier build. The datum features it names are controlled on their own and left out (no
face is profiled relative to itself). The document links it to exactly those faces, and a STEP
has it as a ``SURFACE_PROFILE_TOLERANCE`` on them, so a reader gets the faces themselves. It is
not XCAF's ``All_Over`` modifier, which in ASME means every surface beside any other requirement.
It has no ref to break: it is ``ok`` (``invalid`` where its frame names a datum the part lacks),
and one covering no face is linked to nothing and written to no STEP.

**Coverage** (``coverage``) holds a part to every face having a requirement, most through its
general profile. Of each part carrying PMI, where its document is served (``coverage_of``, the
structure's ``pmi_coverage``), and in the build's report from the same: the faces no ``ok``
toleranced dimension or geometric tolerance names (the general profile names those it covers; a
basic dimension, a datum and a note cover nothing, and the datum features a general profile names
are left to controls of their own), and the requirements that cannot both hold or hold nothing --
a datum no frame names, a flag note every link of which is broken, a limits dimension its measured
nominal lies outside, two dimensions of one type on the same faces whose zones do not meet, a
flatness wider than a profile on its face. Derived, never held, and warned of: it never fails a
build.

**A document another system wrote** (a vendor's STEP, or an xbf converted from one) lists its
GD&T as XCAF reads it. What this module does not hold whole -- another characteristic or dimension
type, a fit, a qualifier, a modifier, limits beside any of them, a datum target, a link to an edge or
a point -- is listed ``unsupported`` with its XCAF type and why, never refused and never read as less
than it says.
An xbf converted from it copies its GD&T as read (``copy``); an export of it says what it leaves
out (``dropped``) where one of a document the code made is refused (``refuse_dropped``).

**Presentation** (``place``) is where a viewer draws an annotation: an anchor and a text offset in
millimetres, in the annotated part's frame. It is no part of the semantic record: it is never
written to a STEP, and moving it changes nothing an annotation means.

**Scope.** What is written and read back is verified end to end (the engine's PMI tests, with
an AP242 reader of no OCCT):
datums on a plane or cylinder; diameter and linear-distance dimensions with a plus-minus
tolerance or limits; basic (theoretically exact) distances, from planes and hole axes, with no
tolerance, marked as AP242 marks them (CAx-IF's 'theoretical' dimension note); flatness; position
with an ordered datum reference frame and a diametral zone; a surface profile on one face or
several, of any kind, with a frame of up to three datums or none; a part's general profile, on
the faces nothing else controls; and, in the xbf alone, general and flag notes, a part's notes
library and its named views. Every
other XCAF characteristic, dimension type, modifier and tolerance form is refused by name
(``PMIUnsupported``), never approximated. PMI is part-level: an annotation is on one part, and an
assembly is refused.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = ["DIMENSION_TYPES", "GEOMETRIC_CHARACTERISTICS", "PMIError", "PMIUnsupported", "annotate", "basic", "camera",
           "coverage", "datum", "diameter", "dimension", "distance", "flatness", "general_profile", "geometric",
           "limits", "note", "otherwise_controlled", "place", "plus_minus", "position", "profile", "read", "section",
           "step_entries", "view"]

# The attribute an annotated shape holds its annotations in (a tuple of plain dicts), as a part's
# configurations are held (``kernel.memo`` keys it).
PMI = "xbf_pmi"
# The GUID of the cadgen attribute beside each XCAF GD&T object, and its JSON's schema (see the
# module): an attribute of another schema is not read.
EXTRA_GUID = "5d3a7c1e-9f42-4b86-a0e5-3c7b9d2f6e18"
SCHEMA = "cadgen.pmi/1"
# The GUID of a part's notes library (``annotate``'s ``library``), one JSON attribute of ``SCHEMA`` on its
# shape label.
LIBRARY_GUID = "471db751-90aa-42aa-8fda-c0a0418a5689"
# The GD&T tool's label under the main label (``XCAFDoc_DocumentTool::DimTolLabel``), the views
# tool's (``XCAFDoc_DocumentTool::ViewsLabel``) and the notes tool's (``XCAFDoc_DocumentTool::NotesLabel``).
DIMTOL_TAG = 4
VIEWS_TAG = 7
NOTES_TAG = 9
# A note is an XCAF comment by one fixed user with no timestamp: the same code makes the same bytes.
NOTE_USER = "cadgen"
NOTE_TYPE = "XCAFDoc_NoteComment"
STATUSES = ("ok", "missing", "ambiguous", "invalid")
# A basic dimension's mark in AP242 (CAx-IF PMI Recommended Practices 4.1, 5.3, Table 7): the
# descriptive item's name and description.
THEORETICAL = ("dimensional note", "theoretical")
UNIT = "mm"

# The dimension types and geometric characteristics written and read back, verified; every other
# XCAF one is refused by name.
DIMENSION_TYPES = ("diameter", "distance")
GEOMETRIC_CHARACTERISTICS = ("flatness", "position", "surface_profile")
# XCAF's other characteristics, so a request for one is refused as unsupported rather than unknown.
_XCAF_CHARACTERISTICS = ("angularity", "circular_runout", "circularity_or_roundness", "coaxiality", "concentricity",
                         "cylindricity", "flatness", "line_profile", "parallelism", "perpendicularity", "position",
                         "straightness", "surface_profile", "symmetry", "total_runout")
_XCAF_DIMENSION_TYPES = ("diameter", "distance", "radius", "angle", "curved_distance", "linear_distance",
                         "spherical_diameter", "spherical_radius", "toroidal_minor_diameter", "thickness")
# Every kind of face, as ``_surface`` names OCCT's surface types (``GeomAbs_SurfaceType``).
_EVERY_SURFACE = ("plane", "cylinder", "cone", "sphere", "torus", "beziersurface", "bsplinesurface",
                  "surfaceofrevolution", "surfaceofextrusion", "offsetsurface", "othersurface")
# The faces each annotation stands on.
# A basic dimension is a distance between planes, a plane and a hole's axis, or two axes.
_SURFACES = {"datum": ("plane", "cylinder"), "diameter": ("cylinder",), "distance": ("plane",),
             "basic": ("plane", "cylinder"),
             "flatness": ("plane",), "position": ("cylinder",), "surface_profile": _EVERY_SURFACE,
             "note": _EVERY_SURFACE}


class PMIError(ValueError):
    """An annotation the code gave wrongly: said by name, before anything is written."""


class PMIUnsupported(PMIError):
    """An annotation outside what this module writes and reads back verified: refused by name,
    never approximated."""


# --- authoring -------------------------------------------------------------------------------


def plus_minus(upper: float, lower: float | None = None) -> dict[str, Any]:
    """A plus-minus tolerance: signed deviations from the nominal, ``lower`` below ``upper``
    (``-upper`` when not given: ``plus_minus(0.2)`` is ±0.2; ``plus_minus(0.1, 0)`` is +0.1/0)."""
    upper = _number(upper, "a tolerance's upper deviation")
    lower = -upper if lower is None else _number(lower, "a tolerance's lower deviation")
    if not upper > lower:
        raise PMIError(f"a plus-minus tolerance's upper deviation is above its lower ({lower}), not {upper}")
    return {"type": "plus_minus", "upper": upper, "lower": lower}


def limits(lower: float, upper: float) -> dict[str, Any]:
    """Limits: the least and the greatest size, absolute millimetres, ``upper`` above ``lower``
    (``limits(10.0, 10.05)`` is 10.00–10.05). In place of deviations; the nominal is still
    measured."""
    lower = _number(lower, "a dimension's lower limit")
    upper = _number(upper, "a dimension's upper limit")
    if not lower > 0:
        raise PMIError(f"a dimension's lower limit is a size above 0, not {lower}")
    if not upper > lower:
        raise PMIError(f"a dimension's upper limit (the second) is above its lower, not {lower} and {upper}")
    return {"type": "limits", "lower": lower, "upper": upper}


def place(anchor: Iterable[float], offset: Iterable[float] = (0.0, 0.0, 0.0)) -> dict[str, Any]:
    """Where a viewer draws an annotation (provisional): ``anchor`` on or near its feature and the
    text ``offset`` from it, millimetres in the annotated part's frame. Not semantic: never in a
    STEP, and moving it changes nothing the annotation means."""
    return _place(anchor, offset)


def _place(anchor: Any, offset: Any) -> dict[str, Any]:
    return {"anchor": _point(anchor, "an anchor"), "offset": _point(offset, "an offset")}


def datum(letter: str, ref: Any, *, label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """Datum ``letter`` (``A``..``Z``) on a planar or cylindrical face. Its id is its letter."""
    if not isinstance(letter, str) or len(letter) != 1 or not letter.isascii() or not letter.isupper():
        raise PMIError(f"a datum's letter is one capital A..Z, not {letter!r}")
    return _annotation(letter, "datum", [("feature", ref)], label, presentation, datum={"letter": letter})


def dimension(id: str, type: str, *refs: Any, tolerance: dict | None = None, basic: bool = False,
              label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """A dimension of ``type`` (``DIMENSION_TYPES``) between ``refs``; its nominal is measured
    from the geometry. ``basic``: theoretically exact (ASME's basic, ISO's theoretical), a
    distance with no tolerance that locates what a geometric tolerance controls. Other types
    are refused (``PMIUnsupported``)."""
    if basic and tolerance is not None:
        raise PMIError(f"dimension {id!r}: a basic dimension is theoretically exact: it takes no tolerance")
    if basic and type != "distance":
        raise PMIUnsupported(f"dimension {id!r}: a basic {type} is not written verified yet; a basic dimension "
                             "is a distance")
    if type not in DIMENSION_TYPES:
        if type in _XCAF_DIMENSION_TYPES:
            raise PMIUnsupported(f"dimension {id!r}: a {type} dimension is not written verified yet; "
                                 f"the types are {', '.join(DIMENSION_TYPES)}")
        raise PMIError(f"dimension {id!r}: no dimension type {type!r}; the types are {', '.join(DIMENSION_TYPES)}")
    wanted = 1 if type == "diameter" else 2
    if len(refs) != wanted:
        raise PMIError(f"dimension {id!r}: a {type} dimension is on {wanted} face{'s' if wanted > 1 else ''}, "
                       f"not {len(refs)}")
    roles = ["feature"] if wanted == 1 else ["from", "to"]
    return _annotation(id, "dimension", list(zip(roles, refs)), label, presentation,
                       dimension={"type": type, "basic": bool(basic), "tolerance": _tolerance(tolerance, id)})


def diameter(id: str, ref: Any, *, tolerance: dict | None = None, label: str | None = None,
             presentation: dict | None = None) -> dict[str, Any]:
    """The diameter of a cylindrical face (a hole, a boss), measured; ``tolerance`` given explicitly."""
    return dimension(id, "diameter", ref, tolerance=tolerance, label=label, presentation=presentation)


def distance(id: str, ref_from: Any, ref_to: Any, *, tolerance: dict | None = None, label: str | None = None,
             presentation: dict | None = None) -> dict[str, Any]:
    """The distance between two parallel planar faces, measured; ``tolerance`` given explicitly."""
    return dimension(id, "distance", ref_from, ref_to, tolerance=tolerance, label=label, presentation=presentation)


def basic(id: str, ref_from: Any, ref_to: Any, *, label: str | None = None,
          presentation: dict | None = None) -> dict[str, Any]:
    """A basic (theoretically exact) distance, measured, with no tolerance: between two parallel
    planes, from a plane to a hole's axis parallel to it, or between two parallel axes. What a
    position tolerance's true position is located by."""
    return dimension(id, "distance", ref_from, ref_to, basic=True, label=label, presentation=presentation)


def geometric(id: str, characteristic: str, ref: Any, value: float, *, datums: Iterable[str] = (),
              diameter_zone: bool = False, label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """A geometric tolerance of ``characteristic`` (``GEOMETRIC_CHARACTERISTICS``) of ``value``
    millimetres on one face (a surface profile: on one, or on each of a list of them), referring
    to ``datums`` in order (primary first); a diametral zone with ``diameter_zone``. Other
    characteristics are refused (``PMIUnsupported``)."""
    refs = list(ref) if characteristic == "surface_profile" and isinstance(ref, (list, tuple)) else [ref]
    if not refs:
        raise PMIError(f"tolerance {id!r}: a surface profile is on one face or more, not none")
    return _geometric(id, characteristic, refs, value, datums, diameter_zone, label, presentation, general=False)


def _geometric(id: str, characteristic: str, refs: list[Any], value: float, datums: Iterable[str],
               diameter_zone: bool, label: str | None, presentation: dict | None, *, general: bool) -> dict[str, Any]:
    """A geometric tolerance on ``refs`` (``geometric``); ``general``: the part's general profile,
    on no ref the code writes (``general_profile``)."""
    if characteristic not in GEOMETRIC_CHARACTERISTICS:
        if characteristic in _XCAF_CHARACTERISTICS:
            raise PMIUnsupported(f"tolerance {id!r}: {characteristic} is not written verified yet; the "
                                 f"characteristics are {', '.join(GEOMETRIC_CHARACTERISTICS)}")
        raise PMIError(f"tolerance {id!r}: no characteristic {characteristic!r}; the characteristics are "
                       f"{', '.join(GEOMETRIC_CHARACTERISTICS)}")
    value = _number(value, f"tolerance {id!r}'s value")
    if not value > 0:
        raise PMIError(f"tolerance {id!r}: a tolerance zone is wider than 0, not {value}")
    letters = list(datums)
    for letter in letters:
        if not isinstance(letter, str) or len(letter) != 1 or not letter.isupper():
            raise PMIError(f"tolerance {id!r}: a datum is named by its letter, not {letter!r}")
    if len(set(letters)) != len(letters):
        raise PMIError(f"tolerance {id!r}: a datum is named once in a frame, not {letters}")
    if len(letters) > 3:
        raise PMIError(f"tolerance {id!r}: a datum reference frame has three datums at most, not {len(letters)}")
    if characteristic == "flatness" and (letters or diameter_zone):
        raise PMIError(f"tolerance {id!r}: flatness is a form tolerance, with no datum and no diametral zone")
    if characteristic == "position" and not letters:
        raise PMIUnsupported(f"tolerance {id!r}: a position with no datum is not written verified yet; name its datums")
    if characteristic == "surface_profile" and diameter_zone:
        raise PMIError(f"tolerance {id!r}: a surface profile's zone is a width about the profile: no diametral zone")
    return _annotation(id, "geometric_tolerance", [("feature", given) for given in refs], label, presentation,
                       geometric_tolerance={"characteristic": characteristic, "value": value, "unit": UNIT,
                                            "zone": "diameter" if diameter_zone else None, "modifier": None,
                                            "datums": letters, "general": general})


def flatness(id: str, ref: Any, value: float, *, label: str | None = None,
             presentation: dict | None = None) -> dict[str, Any]:
    """Flatness of ``value`` millimetres on a planar face."""
    return geometric(id, "flatness", ref, value, label=label, presentation=presentation)


def position(id: str, ref: Any, value: float, *, datums: Iterable[str], diameter_zone: bool = True,
             label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """Position of a cylindrical feature (a hole's axis), ``value`` millimetres, a diametral
    zone by default, relative to ``datums`` in order."""
    return geometric(id, "position", ref, value, datums=datums, diameter_zone=diameter_zone, label=label,
                     presentation=presentation)


def profile(id: str, refs: Any, value: float, *, datums: Iterable[str] = (), label: str | None = None,
            presentation: dict | None = None) -> dict[str, Any]:
    """The profile of a surface, ``value`` millimetres wide about its true profile: on a face, or
    on each of a list of faces of any kind (one requirement on all of them), relative to
    ``datums`` in order (none to three)."""
    return geometric(id, "surface_profile", refs, value, datums=datums, label=label, presentation=presentation)


def general_profile(id: str, value: float, *, datums: Iterable[str] = (), label: str | None = None) -> dict[str, Any]:
    """The part's general profile, ``value`` millimetres wide, relative to ``datums`` in order
    (none to three): ASME Y14.5's "unless otherwise noted, all surfaces", a surface profile of every
    face of the part that nothing else controls (``otherwise_controlled``), its faces computed by
    each build from that build's annotations and geometry. Not XCAF's ``All_Over`` modifier (every
    surface, beside any other requirement): it is written as a surface profile on exactly the faces
    it covers. One per part."""
    return _geometric(id, "surface_profile", [], value, datums, False, label, None, general=True)


def note(id: str, text: str, *, faces: Any = (), annotations: Iterable[str] = (), label: str | None = None,
         presentation: dict | None = None) -> dict[str, Any]:
    """A note of the part saying ``text``, the code's words (a project's notes library's, or its
    own): a general note where it names no face and no annotation; a flag note on ``faces`` (a
    face, or a list of faces of any kind) and on the ``annotations`` of the same ``annotate`` call
    it names by id. Numbered among its part's notes as the code gives them, after the part's
    general profile, which is Note 1 where it has one. Its id is one of the part's ids. Kept in the
    xbf, never in a STEP (AP242's writer here writes no notes)."""
    if not isinstance(text, str) or not text.strip():
        raise PMIError(f"note {id!r}: a note's text is a non-empty string, not {text!r}")
    refs = list(faces) if isinstance(faces, (list, tuple)) else [faces]
    named = [annotations] if isinstance(annotations, str) else list(annotations)
    for at, given in enumerate(named):
        if not isinstance(given, str) or not given.strip():
            raise PMIError(f"note {id!r}: an annotation is named by its id, not {given!r}")
        if given in named[:at]:
            raise PMIError(f"note {id!r}: names {given!r} twice; a note names each annotation once")
    return _annotation(id, "note", [("feature", face) for face in refs], label, presentation,
                       note={"text": text, "annotations": named})


def camera(direction: Iterable[float], up: Iterable[float]) -> dict[str, Any]:
    """A view's camera of the code's own: ``direction`` from the part toward the eye (as a
    preset's, ``cadgen snapshot --camera``'s: ``front`` is ``(0, -1, 0)``) and the camera's
    ``up``, in the part's frame, each made a unit vector. An ``up`` along the direction is refused."""
    found = [_unit(direction, "a camera's direction"), _unit(up, "a camera's up")]
    if _cross(*found) < 1e-9:
        raise PMIError(f"a camera's up is not along its direction, not {list(up)} with {list(direction)}")
    return {"direction": found[0], "up": found[1]}


def section(axis: str, at: float, *, invert: bool = False) -> dict[str, Any]:
    """A view's section: the viewer's Clip, one plane across ``axis`` (``x``, ``y`` or ``z``) at
    ``at`` millimetres in the part's frame, keeping the lower side (``invert``: the upper)."""
    return _section(axis, at, invert)


def _section(axis: Any, at: Any, invert: Any) -> dict[str, Any]:
    if axis not in ("x", "y", "z"):
        raise PMIError(f"a section's axis is x, y or z, not {axis!r}")
    if not isinstance(invert, bool):
        raise PMIError(f"a section's invert is True or False, not {invert!r}")
    return {"axis": axis, "at": _number(at, "a section's place"), "invert": invert}


def view(name: str, *, camera: str | dict, shows: Sequence[str] | None = None, section: dict | None = None,
         place: Mapping[str, dict] | None = None, label: str | None = None) -> dict[str, Any]:
    """A named view of the part, given to ``annotate`` among its annotations: seen down ``camera``
    (a preset's name, ``cadgen snapshot --camera``'s, or ``pmi.camera(direction, up)``), orthographic,
    cut by ``section`` (``pmi.section``) where it has one, showing the annotations and notes of the
    same call ``shows`` names by id (None: every one, as an iso view does), each it ``place``-s by
    id drawn there in this view (``pmi.place``) and elsewhere as its own presentation says. Its
    name is unique among its part's views. Kept in the xbf as an XCAF view, never in a STEP."""
    from cadgen.engine.render.presets import PRESETS

    if not isinstance(name, str) or not name.strip():
        raise PMIError(f"a view's name is a non-empty string, not {name!r}")
    if label is not None and not isinstance(label, str):
        raise PMIError(f"view {name!r}: a label is a string, not {label!r}")
    if not (camera in PRESETS if isinstance(camera, str) else _is_camera(camera)):
        raise PMIError(f"view {name!r}: a camera is a preset ({', '.join(sorted(PRESETS))}) or pmi.camera(direction, "
                       f"up), not {camera!r}")
    named = None if shows is None else [shows] if isinstance(shows, str) else list(shows)
    for at, given in enumerate(named or ()):
        if not isinstance(given, str) or not given.strip():
            raise PMIError(f"view {name!r}: an annotation is shown by its id, not {given!r}")
        if given in named[:at]:
            raise PMIError(f"view {name!r} shows {given!r} twice; a view shows each annotation once")
    if section is not None:
        if not isinstance(section, dict) or set(section) != {"axis", "at", "invert"}:
            raise PMIError(f"view {name!r}: a section is pmi.section(axis, at), not {section!r}")
        section = _section(section["axis"], section["at"], section["invert"])
    placed: dict[str, Any] = {}
    for id, given in (place or {}).items():
        if not isinstance(id, str) or not id.strip():
            raise PMIError(f"view {name!r}: an annotation is placed by its id, not {id!r}")
        if not isinstance(given, dict) or set(given) != {"anchor", "offset"}:
            raise PMIError(f"view {name!r}: a placement is pmi.place(anchor, offset), not {given!r}")
        placed[id] = _place(given["anchor"], given["offset"])
    return {"pmi": 1, "kind": "view", "name": name, "label": label,
            "camera": camera if isinstance(camera, str) else {"direction": list(camera["direction"]),
                                                              "up": list(camera["up"])},
            "shows": named, "section": section, "place": placed}


def _is_camera(given: Any) -> bool:
    """Whether ``given`` is a camera ``camera`` made: a unit direction and a unit up, not along it."""
    if not isinstance(given, dict) or set(given) != {"direction", "up"}:
        return False
    try:
        found = [_point(given[key], "a camera's " + key) for key in ("direction", "up")]
    except PMIError:
        return False
    return all(abs(math.sqrt(sum(c * c for c in v)) - 1.0) < 1e-9 for v in found) and _cross(*found) >= 1e-9


def _unit(value: Any, what: str) -> list[float]:
    found = _point(value, what)
    length = math.sqrt(sum(c * c for c in found))
    if not length > 0:
        raise PMIError(f"{what} is longer than 0, not {value!r}")
    return [c / length + 0.0 for c in found]


def _cross(first: list[float], second: list[float]) -> float:
    """The length of two vectors' cross product: 0 where they lie along one line."""
    (a, b, c), (d, e, f) = first, second
    return math.sqrt((b * f - c * e) ** 2 + (c * d - a * f) ** 2 + (a * e - b * d) ** 2)


def annotate(shape: Any, *annotations: dict[str, Any], library: Mapping[str, str] | None = None) -> Any:
    """``shape`` given ``annotations`` (replacing any it held): the part a model returns, or
    one part of its assembly. A ``Face`` given as a ref is numbered against ``shape`` now. Ids are
    unique on a part, a note's with the rest, as are datum letters; a note names annotations of
    this call; and a datum holds one place in every frame that names it (XCAF holds one position
    per datum). Its views (``view``) are among them, each name unique among its views, each
    showing and placing ids of this call (a view's placement of an id it does not show is
    refused). ``library`` is the project's notes by name, the dict its own module holds (cadgen
    ships none): kept with the part, for a viewer to offer, and no requirement. Returns ``shape``."""
    import build123d as bd

    if not isinstance(shape, bd.Shape) or getattr(shape, "wrapped", None) is None:
        raise PMIError(f"pmi.annotate() takes the part its annotations are on, not {type(shape).__name__}")
    if getattr(shape, "children", None):
        raise PMIUnsupported("pmi.annotate() is given one part: assembly-level PMI is not written yet; annotate "
                             "each part")
    held: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    ids: set[str] = set()
    places: dict[str, tuple[int, str]] = {}
    faces = None
    for given in annotations:
        if not isinstance(given, dict) or given.get("pmi") != 1:
            raise PMIError(f"pmi.annotate() takes annotations made by pmi.datum(), pmi.diameter(), ...: "
                           f"not {given!r}")
        if given["kind"] == "view":
            if any(other["name"] == given["name"] for other in views):
                raise PMIError(f"two views of one part are named {given['name']!r}: a view's name is unique")
            views.append(dict(given))
            continue
        if given["id"] in ids:
            raise PMIError(f"two annotations on one part are {given['id']!r}: an id is unique")
        ids.add(given["id"])
        refs = []
        for ref in given["refs"]:
            target = ref["target"]
            if isinstance(target, str):
                refs.append({"role": ref["role"], "written": target, "face": None})
                continue
            if faces is None:
                faces = _faces(shape.wrapped)
            ordinal = faces.FindIndex(target.wrapped)
            refs.append({"role": ref["role"], "written": f"face {ordinal}" if ordinal else "a face of another shape",
                         "face": ordinal or 0})
        entry = {key: value for key, value in given.items() if key != "refs"}
        entry["refs"] = refs
        for at, letter in enumerate((given.get("geometric_tolerance") or {}).get("datums") or (), 1):
            if letter in places and places[letter][0] != at:
                raise PMIUnsupported(f"datum {letter} is datum {places[letter][0]} of {places[letter][1]!r} and datum "
                                     f"{at} of {given['id']!r}: XCAF holds one position per datum")
            places.setdefault(letter, (at, given["id"]))
        held.append(entry)
    letters = [entry["datum"]["letter"] for entry in held if entry["kind"] == "datum"]
    if len(set(letters)) != len(letters):
        raise PMIError(f"a part defines each datum letter once, not {letters}")
    general = [entry["id"] for entry in held if _general(entry)]
    if len(general) > 1:
        raise PMIError(f"a part has one general profile, not {' and '.join(map(repr, general))}")
    kinds = {entry["id"]: entry["kind"] for entry in held}
    for entry in held:
        for named in (entry.get("note") or {}).get("annotations") or ():
            if named not in kinds:
                raise PMIError(f"note {entry['id']!r} names {named!r}, which is no annotation of this pmi.annotate() "
                               f"call; its ids are {', '.join(map(repr, kinds))}")
            if kinds[named] == "note":
                raise PMIError(f"note {entry['id']!r} names note {named!r}: a note names annotations, not notes")
    for given in views:
        shown = given["shows"]
        for named in [*(shown or ()), *given["place"]]:
            if named not in kinds:
                raise PMIError(f"view {given['name']!r} {'shows' if named in (shown or ()) else 'places'} {named!r}, "
                               f"which is no annotation of this pmi.annotate() call; its ids are "
                               f"{', '.join(map(repr, kinds)) or 'none'}")
            if shown is not None and named not in shown:
                raise PMIError(f"view {given['name']!r} places {named!r}, which it does not show; its shows are "
                               f"{', '.join(map(repr, shown))}")
    _note_call(held)
    held.extend(views)
    if library is not None:
        held.extend(_library_entry(library))
    shape.__dict__[PMI] = tuple(held)
    return shape


def _library_entry(library: Any) -> list[dict[str, Any]]:
    """A part's notes library as ``annotate`` holds it among its annotations: one entry of kind
    ``library``, each note's name and text in the project's order; none for an empty one."""
    if not isinstance(library, Mapping):
        raise PMIError("pmi.annotate(library=...): a library is a project's notes by name, a dict of each note's "
                       f"name to its text, not {type(library).__name__}")
    found = []
    for name, text in library.items():
        if not isinstance(name, str) or not name.strip():
            raise PMIError(f"a library's note is named by a non-empty string, not {name!r}")
        if not isinstance(text, str) or not text.strip():
            raise PMIError(f"library note {name!r}: its text is a non-empty string, not {text!r}")
        found.append({"name": name, "text": text})
    return [{"pmi": 1, "kind": "library", "library": found}] if found else []


def _annotations(given: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """What ``annotate`` gave a part, its views and library apart: its annotations, notes among them."""
    return [entry for entry in given if entry["kind"] not in ("library", "view")]


def _views(given: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """A part's views as ``annotate`` gave them (``view``), in the code's order."""
    return [entry for entry in given if entry["kind"] == "view"]


def _library(given: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """A part's notes library as ``annotate`` gave it (``_library_entry``): each note's name and text."""
    return next((list(entry["library"]) for entry in given if entry["kind"] == "library"), [])


def _annotation(id: str, kind: str, refs: list[tuple[str, Any]], label: str | None, presentation: dict | None,
                **values: Any) -> dict[str, Any]:
    import build123d as bd

    if not isinstance(id, str) or not id.strip():
        raise PMIError(f"an annotation's id is a non-empty string, not {id!r}")
    if label is not None and not isinstance(label, str):
        raise PMIError(f"annotation {id!r}: a label is a string, not {label!r}")
    for _role, target in refs:
        if not isinstance(target, (str, bd.Face)):
            raise PMIError(f"annotation {id!r}: a ref is a face of the part -- a build123d Face, or a ref such as "
                           f"'f:plate.body.6' or 'face 7' -- not {type(target).__name__}")
    if presentation is not None and (not isinstance(presentation, dict) or set(presentation) != {"anchor", "offset"}):
        raise PMIError(f"annotation {id!r}: a presentation is pmi.place(anchor, offset)")
    return {"pmi": 1, "id": id, "kind": kind, "label": label, "presentation": presentation,
            "refs": [{"role": role, "target": target} for role, target in refs], **values}


def _general(spec: dict[str, Any]) -> bool:
    """Whether an annotation is its part's general profile (``general_profile``)."""
    return spec["kind"] == "geometric_tolerance" and bool(spec["geometric_tolerance"].get("general"))


def _tolerance(tolerance: dict | None, id: str) -> dict | None:
    if tolerance is None:
        return None
    if not isinstance(tolerance, dict) or tolerance.get("type") not in ("plus_minus", "limits"):
        raise PMIUnsupported(f"dimension {id!r}: a tolerance is pmi.plus_minus(...) or pmi.limits(...); fits and "
                             "general tolerances are not written yet")
    return dict(tolerance)


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PMIError(f"{what} is a finite number, not {value!r}")
    return float(value)


def _point(value: Any, what: str) -> list[float]:
    try:
        found = [_number(item, what) for item in value]
    except TypeError:
        found = []
    if len(found) != 3:
        raise PMIError(f"{what} is three numbers, millimetres, not {value!r}")
    return found


def _note_call(held: list[dict[str, Any]]) -> None:
    """``annotate``'s annotations, kept on the build's run under the model whose body gave them."""
    from cadgen.engine.refs import _current_run

    run = _current_run()
    if run is not None:
        run.pmi.setdefault(run.scope, []).extend(_text(entry) for entry in held)


def unattached(run: Any, scope: str, tree: Any) -> list[str]:
    """The ids of the annotations the model ``scope``'s body gave to a shape its result does not
    hold (one a later operation replaced), each once."""
    held = {_text(entry) for _part, given in tree.pmi for entry in given}
    return sorted({json.loads(text)["id"] for text in run.pmi.get(scope, ()) if text not in held})


def _text(entry: dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


# --- document time: harvest and resolve --------------------------------------------------------


def harvest(obj: Any, part: Any, held: dict[int, tuple[Any, tuple]], path: str) -> None:
    """The annotations ``obj`` holds, for the part prototype it is (``document.collect``): one
    geometry placed twice with two sets of annotations is refused by name."""
    given = obj.__dict__.get(PMI) if obj is not None else None
    if not given:
        return
    found = held.get(id(part))
    if found is not None and found[1] != given:
        raise PMIError(f"{path}: one part placed twice is given two sets of annotations; PMI is on the part, once")
    held[id(part)] = (part, given)


def refuse_assembly(obj: Any, path: str) -> None:
    if obj is not None and obj.__dict__.get(PMI):
        raise PMIUnsupported(f"{path}: an assembly is annotated; assembly-level PMI is not written yet: annotate "
                             "each part")


@dataclass
class Ref:
    role: str
    written: str | None  # None: a face a general profile covers, which the code does not write
    ordinal: int | None
    status: str
    candidates: list[int] = field(default_factory=list)
    problem: str | None = None


@dataclass
class Resolved:
    """One annotation as the part is built now: its refs resolved, its status, and its nominal."""

    spec: dict[str, Any]
    refs: list[Ref]
    status: str
    problem: str | None
    nominal: float | None = None


def resolve(tree: Any) -> list[tuple[Any, list[Resolved]]]:
    """Each annotated part of ``tree`` (named: ``Part.names``) with its annotations resolved
    against it, in the tree's order, made once per tree."""
    if tree.pmi_resolved is not None:
        return tree.pmi_resolved
    found = []
    for part, given in tree.pmi or ():
        names = list((part.names or {}).get("faces") or [])
        found.append((part, _resolved_part(_annotations(given), part.shape, names, {part.name, tree.root.name})))
    tree.pmi_resolved = found
    return found


def _resolved_part(given: Iterable[dict[str, Any]], shape: Any, names: list[str | None],
                   owners: set[str]) -> list[Resolved]:
    """A part's annotations (as the code gives them) resolved against its ``shape``, whose faces
    are named ``names`` by ordinal, in the document owned as ``owners`` name it; its general
    profile, where it is ``ok``, on every face the others leave (``_covered``)."""
    given = list(given)
    faces = _faces(shape)
    letters = {entry["datum"]["letter"] for entry in given if entry["kind"] == "datum"}
    found = [_resolved(entry, faces, names, owners, letters) for entry in given]
    for item in found:
        if _general(item.spec) and item.status == "ok":
            item.refs = _covered(found, item.spec["geometric_tolerance"]["datums"], faces.Extent())
    return found


def _covered(items: list[Resolved], datums: list[str], count: int) -> list[Ref]:
    """The faces a part's general profile to ``datums`` covers, of the ``count`` it has: each that
    none of its resolved annotations ``items`` controls (``otherwise_controlled``, its faces spelled
    by ordinal) and that is no feature of a datum it names, which is controlled on its own (no
    face is profiled relative to itself), in the part's order. This build's annotations and
    geometry alone decide it."""
    controlled = otherwise_controlled([
        {"kind": item.spec["kind"], "status": item.status,
         **{key: item.spec[key] for key in ("dimension", "geometric_tolerance") if key in item.spec},
         "refs": [{"role": ref.role, "ref": f"face {ref.ordinal}"} for ref in item.refs]} for item in items])
    named = {f"face {ref.ordinal}" for item in items if item.spec["kind"] == "datum" and item.status == "ok"
             and item.spec["datum"]["letter"] in datums for ref in item.refs}
    left = controlled | named
    return [Ref("feature", None, at, "ok") for at in range(1, count + 1) if f"face {at}" not in left]


def otherwise_controlled(entries: list[dict[str, Any]]) -> set[str]:
    """The faces of ``entries`` (structure entries, ``entries``: their refs as they spell them,
    canonical where served) that have a size or location requirement of their own, which a general
    profile leaves to it: each ref of a plus-minus or limits dimension, and the feature of a
    position or of a profile not general. A basic dimension locates such a feature, counted as it
    is, and leaves the datum it starts from to that face's own control; a form control alone
    (flatness) or a datum leaves a face to the general profile; and an entry not ``ok`` controls
    nothing (it is linked to nothing). Pure: of ``entries`` alone."""
    controlled: set[str] = set()
    for entry in entries:
        if entry.get("status") != "ok":
            continue
        if entry["kind"] == "dimension":
            if (entry["dimension"].get("tolerance") or {}).get("type") in ("plus_minus", "limits"):
                controlled.update(ref["ref"] for ref in entry["refs"])
        elif entry["kind"] == "geometric_tolerance":
            given = entry["geometric_tolerance"]
            if given["characteristic"] == "position" or (given["characteristic"] == "surface_profile"
                                                         and not given.get("general")):
                controlled.update(ref["ref"] for ref in entry["refs"] if ref["role"] == "feature")
    return controlled


# The conflicts ``coverage`` says, in the order it says them.
CONFLICTS = ("unused_datum", "unlinked_note", "outside_limits", "apart", "form_over_profile")
# Millimetres a measured size may pass a limit by, and two zones miss each other by: its own rounding.
_ROUNDING = 1e-6


def coverage(entries: list[dict[str, Any]], faces: Sequence[str]) -> dict[str, Any]:
    """One part's coverage, of its structure entries (``entries``, their refs canonical) and the
    canonical refs of every face it has (``faces``): ``uncovered``, the faces no requirement is on,
    sorted, and ``conflicts``, the requirements that cannot both hold or hold nothing, each
    ``{"kind", "ids", "problem"}``. A face is covered by a requirement that is ``ok`` and names it
    (``_requirement``): a toleranced dimension (plus-minus or limits) or a geometric tolerance, the
    general profile by the faces it covers (``otherwise_controlled`` leaves them to it); one another
    system wrote that this module does not hold whole (``unsupported``) covers its faces as any does,
    but a datum or a basic dimension. A basic dimension covers nothing: it locates the feature a
    position or a profile controls, and leaves the datum it starts from to that datum. A datum and a
    note cover nothing, and a general profile leaves out the datum features it names: give each its
    own control.
    The conflicts (``CONFLICTS``, in that order, each in the entries'): ``unused_datum``, a datum no
    tolerance's frame names; ``unlinked_note``, a flag note every face and annotation of which is
    broken (one link that holds keeps it linked; a general note names nothing to break);
    ``outside_limits``, a limits dimension whose measured nominal lies outside them; ``apart``, two
    toleranced dimensions of one type on the same faces whose zones do not meet; and
    ``form_over_profile``, a flatness wider than a surface profile on its face (its own, or the
    general one). Warned of, never failing a build. Pure: of its arguments alone."""
    ok = [entry for entry in entries if entry["status"] == "ok"]
    covered = {ref["ref"] for entry in ok if _requirement(entry) for ref in entry["refs"]}
    said: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CONFLICTS}

    def say(kind: str, ids: list[str], problem: str) -> None:
        said[kind].append({"kind": kind, "ids": ids, "problem": problem})

    framed = {letter for entry in entries
              for letter in (entry.get("geometric_tolerance") or entry.get("values") or {}).get("datums") or ()}
    for entry in entries:
        if entry["kind"] == "datum" and entry["datum"]["letter"] not in framed:
            say("unused_datum", [entry["id"]], f"datum {entry['datum']['letter']} is in no tolerance's frame: name it "
                                               "where a requirement is measured from it, or remove it")
    statuses = {entry["id"]: entry["status"] for entry in entries if entry["kind"] != "note"}
    for entry in entries:
        if (entry["kind"] == "note" and not entry["note"]["general"]
                and all(ref["status"] != "ok" for ref in entry["refs"])
                and all(statuses.get(named) != "ok" for named in entry["note"]["annotations"])):
            say("unlinked_note", [entry["id"]], f"Note {entry['note']['number']} is linked to nothing: every face "
                                                "and annotation it names is broken; point it at what it is for, or "
                                                "remove it")
    zones = []
    for entry in ok:
        if entry["kind"] != "dimension":
            continue
        given = entry["dimension"]
        tolerance = given["tolerance"] or {}
        nominal = (given["nominal"] or {}).get("value")
        if tolerance.get("type") == "limits":
            zone = (tolerance["lower"], tolerance["upper"])
            if nominal is not None and not zone[0] - _ROUNDING <= nominal <= zone[1] + _ROUNDING:
                say("outside_limits", [entry["id"]], f"the {given['type']} measures {_mm(nominal)} mm, outside its "
                                                     f"limits {_sizes(*zone)}: model it within them, or correct the "
                                                     "limits")
        elif tolerance.get("type") == "plus_minus" and nominal is not None:
            zone = (nominal + tolerance["lower"], nominal + tolerance["upper"])
        else:
            continue
        zones.append((entry, (given["type"], frozenset(ref["ref"] for ref in entry["refs"])), zone))
    for at, (first, key, zone) in enumerate(zones):
        for second, other, then in zones[at + 1:]:
            if other == key and max(zone[0], then[0]) > min(zone[1], then[1]) + _ROUNDING:
                say("apart", [first["id"], second["id"]],
                    f"two {key[0]}s of the same face{'s' if len(key[1]) > 1 else ''} whose zones do not meet, "
                    f"{_sizes(*zone)} and {_sizes(*then)}: no part holds both; keep the one meant")
    profiles = [entry for entry in ok if entry["kind"] == "geometric_tolerance"
                and entry["geometric_tolerance"]["characteristic"] == "surface_profile"]
    for entry in ok:
        if entry["kind"] != "geometric_tolerance" or entry["geometric_tolerance"]["characteristic"] != "flatness":
            continue
        value, on = entry["geometric_tolerance"]["value"], {ref["ref"] for ref in entry["refs"]}
        for profile in profiles:
            width = profile["geometric_tolerance"]["value"]
            if value > width and on & {ref["ref"] for ref in profile["refs"]}:
                say("form_over_profile", [entry["id"], profile["id"]],
                    f"flatness {_mm(value)} is wider than the surface profile {_mm(width)} on its face, which holds "
                    f"its form within {_mm(width)} already: make the flatness narrower than the profile, or remove it")
    return {"uncovered": sorted(set(faces) - covered),
            "conflicts": [found for kind in CONFLICTS for found in said[kind]]}


def _requirement(entry: dict[str, Any]) -> bool:
    """Whether an entry is a requirement on the faces its refs name, which ``coverage`` counts them
    covered by: a dimension given a tolerance (plus-minus or limits), a geometric tolerance, or
    another system's annotation listed ``unsupported`` but a datum or a basic dimension. A basic
    dimension is none: it locates the feature a position or a profile controls, which covers it, and
    leaves the datum it starts from to that datum's own control; nor is a datum or a note."""
    if entry["kind"] == "dimension":
        return (entry["dimension"]["tolerance"] or {}).get("type") in ("plus_minus", "limits")
    if entry["kind"] == "unsupported":
        return (entry["xcaf_type"] != "XCAFDimTolObjects_DatumObject"
                and not (entry.get("values") or {}).get("basic"))
    return entry["kind"] == "geometric_tolerance"


def _mm(value: float) -> str:
    """A length in millimetres as a problem says it: to four decimals at most (``10``, ``9.95``)."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _sizes(lower: float, upper: float) -> str:
    """The least size and the greatest as the viewer writes limits (``pmiToleranceText``): at one
    number of places, what the more exact needs (four at most), an en dash between (``9.90–9.95``)."""
    places = max(len(_mm(value).partition(".")[2]) for value in (lower, upper))
    return f"{lower:.{places}f}–{upper:.{places}f}"


def _resolved(spec: dict[str, Any], faces: Any, names: list[str | None], owners: set[str],
              letters: set[str]) -> Resolved:
    """One annotation against the part as built: each ref, then the faces it names against the
    faces its kind stands on (``_SURFACES``), then its nominal measured."""
    refs = [_ref(given, faces, names, owners) for given in spec["refs"]]
    nominal = None
    problem = next((ref.problem for ref in refs if ref.status != "ok"), None)
    if all(ref.status == "ok" for ref in refs):
        surfaces = [_surface(faces.FindKey(ref.ordinal)) for ref in refs]
        what = _what(spec)
        wanted = _SURFACES[what]
        for ref, surface in zip(refs, surfaces):
            if surface[0] not in wanted:
                ref.status = "invalid"
                ref.problem = (f"{ref.written} is a {surface[0]} face; a {what.replace('_', ' ')} is on a "
                               f"{' or '.join(wanted)} face")
        if what in ("surface_profile", "note"):
            for at, ref in enumerate(refs):
                earlier = next((other for other in refs[:at] if other.ordinal == ref.ordinal), None)
                if earlier is not None:
                    ref.status = "invalid"
                    ref.problem = (f"{ref.written} names face {ref.ordinal}, as {earlier.written} does: a "
                                   f"{what.replace('_', ' ')} is on each face once")
        if all(ref.status == "ok" for ref in refs):
            if what == "diameter":
                nominal = 2.0 * surfaces[0][1]["radius"]
            elif what in ("distance", "basic"):
                nominal, why = _separation([faces.FindKey(ref.ordinal) for ref in refs], [ref.written for ref in refs])
                if why is not None:
                    refs[1].status, refs[1].problem = "invalid", why
        problem = next((ref.problem for ref in refs if ref.status != "ok"), None)
    status = _worst(ref.status for ref in refs)
    if status == "ok" and spec["kind"] == "geometric_tolerance":
        undefined = [letter for letter in spec["geometric_tolerance"]["datums"] if letter not in letters]
        if undefined:
            status, problem = "invalid", f"datum {', '.join(undefined)} is not defined on this part"
    return Resolved(spec, refs, status, problem, nominal)


def _what(spec: dict[str, Any]) -> str:
    """What an annotation is, as ``_SURFACES`` knows it: a datum, a note, a dimension's type
    (``basic`` for a basic one) or a tolerance's characteristic."""
    if spec["kind"] in ("datum", "note"):
        return spec["kind"]
    if spec["kind"] == "dimension":
        return "basic" if spec["dimension"].get("basic") else spec["dimension"]["type"]
    return spec["geometric_tolerance"]["characteristic"]


def _owner_label(segment: Any, owners: set[str]) -> str:
    """The label an owner's last segment names: ``LABEL.N`` is the N-th ``LABEL`` where no owner
    bears the text whole, as the grammar reads it (``refs._group``)."""
    from cadgen.engine import refs as grammar

    numbered = None if segment.quoted or segment.text in owners else grammar._INDEXED.fullmatch(segment.text)
    return numbered[1] if numbered else segment.text


def _ref(given: dict[str, Any], faces: Any, names: list[str | None], owners: set[str]) -> Ref:
    from cadgen.engine import refs as grammar

    role, written = given["role"], given["written"]
    count = faces.Extent()
    if given["face"] is not None:
        ordinal = given["face"]
        if not 1 <= ordinal <= count:
            return Ref(role, written, None, "missing", problem=f"{written} is not a face of the annotated part")
        return Ref(role, written, ordinal, "ok")
    try:
        file, selectors = grammar.parse(written)
    except grammar.RefError as error:
        return Ref(role, written, None, "invalid", problem=str(error))
    if file is not None or len(selectors) != 1 or selectors[0].element is None or selectors[0].kind != "face":
        return Ref(role, written, None, "invalid", problem=f"{written}: a PMI ref names one face of the annotated part")
    selector = selectors[0]
    if selector.owner:
        if _owner_label(selector.owner[-1], owners) not in owners:
            return Ref(role, written, None, "invalid", problem=f"{written}: {'/'.join(map(str, selector.owner))} is "
                                                               f"not the annotated part ({sorted(owners)[0]})")
    element = selector.element
    if isinstance(element, tuple):
        ordinal = element[1]
        if not 1 <= ordinal <= count:
            return Ref(role, written, None, "missing", problem=f"the part has no face {ordinal} (it has {count})")
        return Ref(role, written, ordinal, "ok")
    held = [at for at, text in enumerate(names, 1) if text == element and at <= count]
    if len(held) == 1:
        return Ref(role, written, held[0], "ok")
    if len(held) > 1:
        return Ref(role, written, None, "ambiguous", held,
                   f"{written} names {len(held)} faces: {', '.join(f'face {at}' for at in held)}")
    said = f"the part has no face {element}"
    atom = element.split(":", 1)[1].split(";", 1)[0]
    if "~" not in atom:  # a folded name: its digest says nothing of what it became (``refs._missing``)
        now = sorted({text for text in names if text and text.split(":", 1)[1].split(";", 1)[0] == atom})
        said += f": {atom} is now {', '.join(now)}" if now else f": no face is made of {atom} now"
    return Ref(role, written, None, "missing", problem=said)


def _datums_first(items: list[Resolved]) -> list[Resolved]:
    """A part's annotations in the order its document holds them: its datums, then the rest."""
    return [item for item in items if item.spec["kind"] == "datum"] + [item for item in items if item.spec["kind"] != "datum"]


def _separation(shapes: list[Any], written: list[str]) -> tuple[float | None, str | None]:
    """The distance between two faces as a location dimension measures it: between parallel
    planes, from a plane to a cylinder's axis parallel to it, or between parallel axes; or why
    there is none."""
    import numpy as np

    held = []
    for shape in shapes:
        kind, found = _surface(shape)
        held.append((kind, found if kind == "plane" else _axis(shape)))
    (first_kind, first), (second_kind, second) = held
    if first_kind == "plane" and second_kind == "plane":
        normal, other = np.array(first["normal"]), np.array(second["normal"])
        if abs(abs(float(normal @ other)) - 1.0) > 1e-9:
            return None, f"{written[0]} and {written[1]} are not parallel planes"
        found = abs(float((np.array(second["origin"]) - np.array(first["origin"])) @ normal))
        return (found, None) if found > 1e-9 else (None, f"{written[0]} and {written[1]} lie in one plane")
    if first_kind == "cylinder" and second_kind == "cylinder":
        point, direction = np.array(first["point"]), np.array(first["direction"])
        if abs(abs(float(direction @ np.array(second["direction"]))) - 1.0) > 1e-9:
            return None, f"the axes of {written[0]} and {written[1]} are not parallel"
        found = float(np.linalg.norm(np.cross(np.array(second["point"]) - point, direction)))
        return (found, None) if found > 1e-9 else (None, f"{written[0]} and {written[1]} share one axis")
    plane, axis = (first, second) if first_kind == "plane" else (second, first)
    normal = np.array(plane["normal"])
    if abs(float(normal @ np.array(axis["direction"]))) > 1e-9:
        axis_of, plane_of = (written[1], written[0]) if first_kind == "plane" else (written[0], written[1])
        return None, f"the axis of {axis_of} is not parallel to the plane {plane_of}"
    found = abs(float((np.array(axis["point"]) - np.array(plane["origin"])) @ normal))
    return (found, None) if found > 1e-9 else (None, f"the axis lies in the plane {written[0]}")


def _axis(face: Any) -> dict[str, Any]:
    """A cylindrical face's axis: a point on it and its unit direction."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopoDS import TopoDS

    axis = BRepAdaptor_Surface(TopoDS.Face_s(face)).Cylinder().Axis()
    point, direction = axis.Location(), axis.Direction()
    return {"point": (point.X(), point.Y(), point.Z()), "direction": (direction.X(), direction.Y(), direction.Z())}


def _worst(statuses: Iterable[str]) -> str:
    found = "ok"
    for status in statuses:
        if STATUSES.index(status) > STATUSES.index(found):
            found = status
    return found


def _faces(shape: Any) -> Any:
    """A part's faces by their ordinals, as the ref grammar numbers them (``refs._map``)."""
    from cadgen.engine import refs as grammar

    return grammar._map(shape, "face")


def _surface(face: Any) -> tuple[str, dict[str, Any]]:
    """A face's surface: ``plane`` (origin, unit normal), ``cylinder`` (radius, axis), or another
    kind by name."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.TopoDS import TopoDS

    adaptor = BRepAdaptor_Surface(TopoDS.Face_s(face))
    kind = adaptor.GetType()
    if kind == GeomAbs_Plane:
        plane = adaptor.Plane()
        origin, normal = plane.Location(), plane.Axis().Direction()
        return "plane", {"origin": (origin.X(), origin.Y(), origin.Z()), "normal": (normal.X(), normal.Y(), normal.Z())}
    if kind == GeomAbs_Cylinder:
        return "cylinder", {"radius": adaptor.Cylinder().Radius()}
    return str(kind.name).replace("GeomAbs_", "").lower(), {}


def faces_named(tree: Any) -> dict[tuple[str, str], dict[tuple[str, str], str]]:
    """The kind of face (plane, cylinder) each ref of a built tree's annotations names, by
    annotation (part, id), then ref (role, written): what ``warn`` compares two builds by."""
    found: dict = {}
    for part, items in resolve(tree) if tree is not None and tree.pmi else ():
        faces = _faces(part.shape)
        for item in items:
            found[(part.name, item.spec["id"])] = {(ref.role, ref.written): _surface(faces.FindKey(ref.ordinal))[0]
                                                   for ref in item.refs if ref.ordinal is not None}
    return found


def faces_named_in(path: Any) -> dict[tuple[str, str], dict[tuple[str, str], str]]:
    """The same, of the model's saved xbf: its last build, where this process has not built it. A
    file that cannot be read holds nothing to compare with."""
    from cadgen.engine import document

    try:
        loaded = document.load(path)
        records = records_of_document(loaded.doc, loaded.prototypes, loaded.name)
    except Exception:  # noqa: BLE001 - no last build is nothing to warn of, never a failed build
        return {}
    found: dict = {}
    for record in records:
        if record["extra"] is None:
            continue
        prototype = loaded.prototypes[record["part"]]
        faces = _faces(prototype.shape)
        found[(prototype.name, record["extra"]["id"])] = {(ref["role"], ref["written"]): _surface(
            faces.FindKey(ref["ordinal"]))[0] for ref in record["refs"] if ref["ordinal"] is not None}
    return found


def warn(tree: Any, previous: dict[tuple[str, str], dict[tuple[str, str], str]]) -> None:
    """Each ref of ``tree``'s annotations written as text that names another kind of face than on
    the model's last build (``previous``: ``faces_named`` of its tree, or ``faces_named_in`` its
    xbf) -- a hole whose name passed to a flat side of the cut that replaced it -- where the
    annotation stands on the face it names now (elsewhere its status says so): warned of in
    ``Tree.pmi_warnings``, the build's report and its served structure, never the document, which
    is what the code makes."""
    now = faces_named(tree)
    for part, items in resolve(tree):
        for item in items:
            key = (part.name, item.spec["id"])
            for ref, given in zip(item.refs, item.spec["refs"]):
                was = (previous.get(key) or {}).get((ref.role, ref.written))
                named = now[key].get((ref.role, ref.written))
                if given["face"] is None and ref.status == "ok" and was is not None and was != named:
                    tree.pmi_warnings.setdefault(key, []).append(
                        f"{ref.written} named a {was} face on the last build and names a {named} face now: another "
                        "face than the annotation was made on, measured as it is. Point the ref at the face meant, "
                        "or remove the annotation")


def signature(tree: Any) -> tuple:
    """What a tree's annotations are, for the build's signature: a change to one remakes the document."""
    return tuple(_text({"part": part.name, "pmi": list(given)}) for part, given in tree.pmi or ())


def problems(tree: Any) -> list[dict[str, Any]]:
    """Every annotation of ``tree`` that is not ``ok``: its part, id, status and why."""
    return [{"part": part.name, "id": item.spec["id"], "status": item.status, "problem": item.problem}
            for part, items in resolve(tree) for item in items if item.status != "ok"]


def warnings(tree: Any) -> list[str]:
    """Every warning of ``tree``'s annotations (``warn``), each naming its annotation (``part/id``)."""
    return [f"{part}/{id}: {text}" for (part, id), texts in tree.pmi_warnings.items() for text in texts]


# --- the XCAF document -------------------------------------------------------------------------


def write(doc: Any, tree: Any, label_of: Any) -> None:
    """The tree's annotations into ``doc``'s GD&T tool, each part's in its order, datums first
    (a tolerance's frame names them), then its notes into the notes tool, in the code's order
    (``_note``), its views into the views tool, in the code's order (``_view``), and its notes
    library onto its shape label; and the GD&T of the document the tree was read from
    (``Tree.pmi_source``: ``copy``). ``label_of(part)`` is the part's shape label."""
    if tree.pmi_source is not None:
        loaded, parts = tree.pmi_source
        copy(doc, loaded, lambda index: label_of(parts[index]))
    if not tree.pmi:
        return
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString
    from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Reference
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    guid = Standard_GUID(EXTRA_GUID)
    for part, items in resolve(tree):
        label = label_of(part)
        faces = _faces(XCAFDoc_ShapeTool.GetShape_s(label))

        def sub(ordinal: int) -> Any:
            found = TDF_Label()
            face = faces.FindKey(ordinal)
            if not shapes.FindSubShape(label, face, found):
                shapes.AddSubShape(label, face, found)
            return found

        datums: dict[str, Any] = {}
        made: dict[str, Any] = {}  # each annotation's GD&T label, by id: what a note names
        positions = {letter: at for item in items if item.spec["kind"] == "geometric_tolerance"
                     for at, letter in enumerate(item.spec["geometric_tolerance"]["datums"], 1)}
        ordered = _datums_first(items)
        for item in ordered:
            spec = item.spec
            if spec["kind"] == "note":
                continue
            linked = _on_faces(item)
            refs = [sub(ref.ordinal) for ref in item.refs] if linked else []
            if spec["kind"] == "datum":
                at = tool.AddDatum()
                _datum(at, spec["datum"]["letter"], positions.get(spec["datum"]["letter"], 0), spec["id"])
                if linked:
                    sequence = TDF_LabelSequence()
                    sequence.Append(refs[0])
                    tool.SetDatum(sequence, at)
                datums[spec["datum"]["letter"]] = at
            elif spec["kind"] == "dimension":
                at = tool.AddDimension()
                _dimension(at, spec, item.nominal)
                if linked and len(refs) == 1:
                    tool.SetDimension(refs[0], at)
                elif linked:
                    tool.SetDimension(refs[0], refs[1], at)
            else:
                at = tool.AddGeomTolerance()
                _tolerance_object(at, spec)
                if linked:
                    sequence = TDF_LabelSequence()
                    for ref in refs:
                        sequence.Append(ref)
                    tool.SetGeomTolerance(sequence, at)
                    for letter in spec["geometric_tolerance"]["datums"]:
                        tool.SetDatumToGeomTol(datums[letter], at)
            TDataStd_AsciiString.Set_s(at, guid, TCollection_AsciiString(_text(_extra(item))))
            TDF_Reference.Set_s(at, label)
            made[spec["id"]] = at
        for item in items:
            if item.spec["kind"] == "note":
                at = _note(XCAFDoc_DocumentTool.NotesTool_s(doc.Main()), item, label, made)
                TDataStd_AsciiString.Set_s(at, guid, TCollection_AsciiString(_text(_extra(item))))
                TDF_Reference.Set_s(at, label)
        for given in _views(part.pmi):
            at = _view(doc, given, label, made)
            TDataStd_AsciiString.Set_s(at, guid, TCollection_AsciiString(_text(_view_extra(given))))
            TDF_Reference.Set_s(at, label)
        library = _library(part.pmi)
        if library:
            TDataStd_AsciiString.Set_s(label, Standard_GUID(LIBRARY_GUID),
                                       TCollection_AsciiString(_text({"schema": SCHEMA, "library": library})))


def _note(notes: Any, item: Resolved, label: Any, made: dict[str, Any]) -> Any:
    """A note as an XCAF comment (``NOTE_USER``, no timestamp) in ``notes``, the notes tool; its
    label. A flag note is attached to each face it is on, where it is ``ok`` (the sub-shape index
    is the face's ordinal in its part's face map, as the ref grammar numbers faces), and to the
    GD&T label of each annotation it names (``made``, by id); a general note to its part's shape
    ``label``."""
    from OCP.TCollection import TCollection_ExtendedString

    spec = item.spec
    found = notes.CreateComment(TCollection_ExtendedString(NOTE_USER, True), TCollection_ExtendedString("", True),
                                TCollection_ExtendedString(spec["note"]["text"], True)).Label()
    if _on_faces(item):
        for ref in item.refs:
            notes.AddNoteToSubshape(found, label, ref.ordinal)
    for named in spec["note"]["annotations"]:
        notes.AddNote(found, made[named])
    if not spec["refs"] and not spec["note"]["annotations"]:
        notes.AddNote(found, label)
    return found


def _view(doc: Any, given: dict[str, Any], label: Any, made: dict[str, Any]) -> Any:
    """A view (``view``) as an XCAF view in ``doc``'s views tool; its label. Parallel, looking along
    the camera's direction reversed (XCAF's view direction is the one looked along; the code's, the
    way to the eye), its eye the part's box centre moved toward the eye by the box's diagonal, its
    window that diagonal each way and its zoom 1, each set (the same code makes the same bytes); on
    its part's shape ``label``, with the GD&T labels (``made``, by id) it shows, in its order (all
    of them, the document's order, where it names none), and its section as an XCAF clipping plane
    named for it, its normal into the half the Clip keeps, capped as the Clip caps. The notes it
    shows are its cadgen attribute's alone: OCCT's ``SetView`` files a view's notes under its
    clipping-plane link, where a reader would take them for planes."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool, XCAFDoc_View
    from OCP.XCAFView import XCAFView_Object, XCAFView_ProjectionType_Parallel

    tool = XCAFDoc_DocumentTool.ViewTool_s(doc.Main())
    camera = _camera_of(given["camera"])
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(XCAFDoc_ShapeTool.GetShape_s(label), box, False, False)
    low, high = box.CornerMin(), box.CornerMax()
    low_at, high_at = (low.X(), low.Y(), low.Z()), (high.X(), high.Y(), high.Z())
    diagonal = math.sqrt(sum((b - a) ** 2 for a, b in zip(low_at, high_at)))
    eye = [(a + b) / 2 + side * diagonal for a, b, side in zip(low_at, high_at, camera["direction"])]
    found = XCAFView_Object()
    found.SetName(_ascii(given["name"]))
    found.SetType(XCAFView_ProjectionType_Parallel)
    found.SetProjectionPoint(gp_Pnt(*eye))
    found.SetViewDirection(gp_Dir(*(-side for side in camera["direction"])))
    found.SetUpDirection(gp_Dir(*camera["up"]))
    found.SetZoomFactor(1.0)
    found.SetWindowHorizontalSize(diagonal)
    found.SetWindowVerticalSize(diagonal)
    at = tool.AddView()
    XCAFDoc_View.Set_s(at).SetObject(found)
    sequences = {"shapes": TDF_LabelSequence(), "gdts": TDF_LabelSequence(), "planes": TDF_LabelSequence()}
    sequences["shapes"].Append(label)
    for id in made if given["shows"] is None else given["shows"]:
        if id in made:
            sequences["gdts"].Append(made[id])
    cut = given["section"]
    if cut is not None:
        axis = "xyz".index(cut["axis"])
        point, normal = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        point[axis], normal[axis] = cut["at"], 1.0 if cut["invert"] else -1.0
        sequences["planes"].Append(XCAFDoc_DocumentTool.ClippingPlaneTool_s(doc.Main()).AddClippingPlane(
            gp_Pln(gp_Pnt(*point), gp_Dir(*normal)), TCollection_ExtendedString(given["name"], True), True))
    tool.SetView(sequences["shapes"], sequences["gdts"], sequences["planes"], at)
    return at


def _view_extra(given: dict[str, Any]) -> dict[str, Any]:
    """The cadgen attribute beside a view's XCAF view (see the module): the view as the code gave it,
    its camera as written (a preset's name, or ``camera``'s two unit vectors)."""
    return {"schema": SCHEMA, "kind": "view", **{key: given[key] for key in
                                                ("name", "label", "camera", "shows", "section", "place")}}


def _camera_of(written: Any) -> dict[str, Any]:
    """A view's camera as served: its preset's name or None, its direction (from the part toward the
    eye) and up, unit vectors in the part's frame (a preset's from the stills' own table,
    ``render/presets.py``), and its projection, orthographic."""
    from cadgen.engine.render.presets import PRESETS

    if isinstance(written, str):
        side, up = PRESETS[written]
        found = {"direction": _unit(side, "a preset's direction"), "up": _unit(up, "a preset's up")}
    else:
        found = {"direction": list(written["direction"]), "up": list(written["up"])}
    return {"preset": written if isinstance(written, str) else None, **found, "projection": "orthographic"}


def _on_faces(item: Resolved) -> bool:
    """Whether an annotation is linked to the faces it is on: ``ok``, and on one or more (a general
    profile covering none is linked to nothing, as one not ``ok`` is)."""
    return item.status == "ok" and bool(item.refs)


def _extra(item: Resolved) -> dict[str, Any]:
    """The cadgen attribute's JSON (see the module): what the code says that XCAF has no place for.
    A note's text is XCAF's (its comment), linked or not: beside it, what it names as written."""
    spec = item.spec
    if spec["kind"] == "note":
        return {"schema": SCHEMA, "id": spec["id"], "kind": "note", "label": spec["label"],
                "presentation": spec["presentation"], "refs": spec["refs"],
                "annotations": list(spec["note"]["annotations"])}
    found = {"schema": SCHEMA, "id": spec["id"], "kind": spec["kind"], "label": spec["label"],
             "presentation": spec["presentation"], "refs": spec["refs"],
             # What an unlinked annotation meant, for a reader: XCAF links values to geometry alone.
             "unlinked": None if _on_faces(item) else
             {key: spec[key] for key in ("dimension", "datum", "geometric_tolerance") if key in spec}}
    if _general(spec):
        found["general"] = True  # the part's general profile: its faces are computed, not written
    return found


def _ascii(text: str) -> Any:
    from OCP.TCollection import TCollection_HAsciiString

    return TCollection_HAsciiString(text)


def _datum(label: Any, letter: str, place: int, id: str) -> None:
    from OCP.XCAFDimTolObjects import XCAFDimTolObjects_DatumObject
    from OCP.XCAFDoc import XCAFDoc_Datum

    found = XCAFDimTolObjects_DatumObject()
    found.SetName(_ascii(letter))
    found.SetSemanticName(_ascii(id))
    if place:
        # A datum's place in the frames that name it: the writer writes a datum system of the
        # datums with a place, in its order, and none without.
        found.SetPosition(place)
    XCAFDoc_Datum.Set_s(label).SetObject(found)


def _dimension(label: Any, spec: dict[str, Any], nominal: float | None) -> None:
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_DimensionObject,
                                        XCAFDimTolObjects_DimensionType_Location_LinearDistance,
                                        XCAFDimTolObjects_DimensionType_Size_Diameter)
    from OCP.XCAFDoc import XCAFDoc_Dimension

    found = XCAFDimTolObjects_DimensionObject()
    found.SetSemanticName(_ascii(spec["id"]))
    kind = spec["dimension"]["type"]
    found.SetType(XCAFDimTolObjects_DimensionType_Size_Diameter if kind == "diameter"
                  else XCAFDimTolObjects_DimensionType_Location_LinearDistance)
    found.SetValue(nominal if nominal is not None else 0.0)
    if spec["dimension"].get("basic"):
        # CAx-IF's type 1 dimension modifier: a descriptive item 'dimensional note' of description
        # 'theoretical' in the dimension's shape_dimension_representation, which is what the
        # writer makes of an XCAF description (and its reader makes one of again).
        found.AddDescription(_ascii(THEORETICAL[1]), _ascii(THEORETICAL[0]))
    tolerance = spec["dimension"]["tolerance"]
    if tolerance is not None and nominal is not None:
        if tolerance["type"] == "limits":
            # XCAF holds limits as the dimension's two values, in place of its nominal (see the module).
            found.SetLowerBound(tolerance["lower"])
            found.SetUpperBound(tolerance["upper"])
        else:
            # XCAF's lower deviation is a magnitude the writer negates (see the module): -lower.
            found.SetLowerTolValue(-tolerance["lower"])
            found.SetUpperTolValue(tolerance["upper"])
    XCAFDoc_Dimension.Set_s(label).SetObject(found)


def _xcaf_characteristics() -> dict[str, Any]:
    """XCAF's type of each characteristic held (``GEOMETRIC_CHARACTERISTICS``): what a tolerance is
    written as and read back by."""
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_GeomToleranceType_Flatness,
                                        XCAFDimTolObjects_GeomToleranceType_Position,
                                        XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface)

    return {"flatness": XCAFDimTolObjects_GeomToleranceType_Flatness,
            "position": XCAFDimTolObjects_GeomToleranceType_Position,
            "surface_profile": XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface}


def _tolerance_object(label: Any, spec: dict[str, Any]) -> None:
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_GeomToleranceObject,
                                        XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
    from OCP.XCAFDoc import XCAFDoc_GeomTolerance

    given = spec["geometric_tolerance"]
    found = XCAFDimTolObjects_GeomToleranceObject()
    found.SetSemanticName(_ascii(spec["id"]))
    found.SetType(_xcaf_characteristics()[given["characteristic"]])
    found.SetValue(given["value"])
    if given["zone"] == "diameter":
        found.SetTypeOfValue(XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
    XCAFDoc_GeomTolerance.Set_s(label).SetObject(found)


def copy(doc: Any, loaded: Any, label_of: Callable[[int], Any]) -> None:
    """The GD&T of a document read from a file another system wrote (``loaded``, a
    ``document.Loaded``) copied as read into ``doc``, the document made of it again (an xbf of a
    STEP): every datum, dimension and geometric tolerance as XCAF holds it, each linked to the same
    faces, edges and points of the same parts (``label_of(index)``: prototype ``index``'s label in
    ``doc``), a tolerance to the same datums. One the file links to anything else (an occurrence's
    face, a whole part) is copied linked to nothing, as reading the file says it is (``missing``):
    its values kept, nothing approximated."""
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_DatumObject, XCAFDimTolObjects_DimensionObject,
                                        XCAFDimTolObjects_GeomToleranceObject)
    from OCP.XCAFDoc import (XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_DocumentTool, XCAFDoc_GeomTolerance,
                             XCAFDoc_ShapeTool)

    from cadgen.engine import refs as grammar
    from cadgen.engine.document import _entry

    source = _tool(loaded.doc)
    if source is None:
        return
    tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    by_entry = {prototype.entry: prototype for prototype in loaded.prototypes}
    theirs: dict[tuple[int, str], Any] = {}  # each prototype's elements, in the file's document and in ``doc``
    ours: dict[tuple[int, str], Any] = {}

    def placed(label: Any) -> Any:
        """A ref label's element as ``doc`` holds it, a sub-shape label of its part; None for none."""
        hit = _element(label, by_entry, theirs)
        if hit is None:
            return None
        index, kind, ordinal = hit
        part = label_of(index)
        if (index, kind) not in ours:
            ours[(index, kind)] = grammar._map(XCAFDoc_ShapeTool.GetShape_s(part), kind)
        element = ours[(index, kind)].FindKey(ordinal)
        found = TDF_Label()
        if not shapes.FindSubShape(part, element, found):
            shapes.AddSubShape(part, element, found)
        return found

    def linked(label: Any) -> list[Any]:
        """The elements a label links to, first and second, as ``doc``'s labels: none where one of
        them has no place there."""
        found = []
        for sequence in _linked(source, label):
            labels = TDF_LabelSequence()
            for at in range(1, sequence.Length() + 1):
                hit = placed(sequence.Value(at))
                if hit is None:
                    return [TDF_LabelSequence(), TDF_LabelSequence()]
                labels.Append(hit)
            found.append(labels)
        return found

    datums: dict[str, Any] = {}
    for label in _labels(source, "datum"):
        at = tool.AddDatum()
        XCAFDoc_Datum.Set_s(at).SetObject(XCAFDimTolObjects_DatumObject(XCAFDoc_Datum.Set_s(label).GetObject()))
        first, _second = linked(label)
        if first.Length():
            tool.SetDatum(first, at)
        datums[_entry(label)] = at
    for label in _labels(source, "dimension"):
        at = tool.AddDimension()
        XCAFDoc_Dimension.Set_s(at).SetObject(
            XCAFDimTolObjects_DimensionObject(XCAFDoc_Dimension.Set_s(label).GetObject()))
        first, second = linked(label)
        if first.Length():
            tool.SetDimension(first, second, at)
    for label in _labels(source, "geometric_tolerance"):
        at = tool.AddGeomTolerance()
        XCAFDoc_GeomTolerance.Set_s(at).SetObject(
            XCAFDimTolObjects_GeomToleranceObject(XCAFDoc_GeomTolerance.Set_s(label).GetObject()))
        first, _second = linked(label)
        if first.Length():
            tool.SetGeomTolerance(first, at)
        for datum in _datums_of(label):
            tool.SetDatumToGeomTol(datums[_entry(datum)], at)


def _tool(doc: Any) -> Any:
    """A document's GD&T tool (``XCAFDoc_DimTolTool``), or None where it has none."""
    from OCP.XCAFDoc import XCAFDoc_DimTolTool

    label = doc.Main().FindChild(DIMTOL_TAG, False)
    if label.IsNull() or not label.IsAttribute(XCAFDoc_DimTolTool.GetID_s()):
        return None
    return XCAFDoc_DimTolTool.Set_s(label)


def _notes_tool(doc: Any) -> Any:
    """A document's notes tool (``XCAFDoc_NotesTool``), or None where it has none."""
    from OCP.XCAFDoc import XCAFDoc_NotesTool

    label = doc.Main().FindChild(NOTES_TAG, False)
    if label.IsNull() or not label.IsAttribute(XCAFDoc_NotesTool.GetID_s()):
        return None
    return XCAFDoc_NotesTool.Set_s(label)


def _labels(tool: Any, kind: str) -> list[Any]:
    """The GD&T tool's labels of ``kind`` (``datum``, ``dimension``, ``geometric_tolerance``) that hold
    their object, in the tool's order; none where the document has no GD&T tool (``tool`` None)."""
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_GeomTolerance

    if tool is None:
        return []
    listed, attribute = {"datum": (tool.GetDatumLabels, XCAFDoc_Datum),
                         "dimension": (tool.GetDimensionLabels, XCAFDoc_Dimension),
                         "geometric_tolerance": (tool.GetGeomToleranceLabels, XCAFDoc_GeomTolerance)}[kind]
    sequence = TDF_LabelSequence()
    listed(sequence)
    return [sequence.Value(at) for at in range(1, sequence.Length() + 1)
            if sequence.Value(at).IsAttribute(attribute.GetID_s())]


def _linked(tool: Any, label: Any) -> tuple[Any, Any]:
    """The shape labels a GD&T label is linked to: its first and its second (a dimension's ``to``)."""
    from OCP.TDF import TDF_LabelSequence

    first, second = TDF_LabelSequence(), TDF_LabelSequence()
    tool.GetRefShapeLabel_s(label, first, second)
    return first, second


def _datums_of(label: Any) -> list[Any]:
    """The datum labels a geometric tolerance's frame names."""
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_DimTolTool

    named = TDF_LabelSequence()
    XCAFDoc_DimTolTool.GetDatumWithObjectOfTolerLabels_s(label, named)
    return [named.Value(at) for at in range(1, named.Length() + 1)]


def _element(label: Any, by_entry: dict[str, Any], maps: dict[tuple[int, str], Any]) -> tuple[int, str, int] | None:
    """The element a ref label is -- its prototype's index, its kind (``face``, ``edge``, ``vertex``)
    and its ordinal there -- or None where it is no element of a prototype (``by_entry``: the
    document's prototypes by their labels' entries; ``maps``: each prototype's elements, made once)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    from cadgen.engine import refs as grammar
    from cadgen.engine.document import _entry

    shape = XCAFDoc_ShapeTool.GetShape_s(label)
    kinds = {TopAbs_FACE: "face", TopAbs_EDGE: "edge", TopAbs_VERTEX: "vertex"}
    kind = None if shape.IsNull() else kinds.get(shape.ShapeType())
    owner = label.Father()
    prototype = by_entry.get(_entry(owner))
    if kind is None or prototype is None:
        return None
    if (prototype.index, kind) not in maps:
        maps[(prototype.index, kind)] = grammar._map(XCAFDoc_ShapeTool.GetShape_s(owner), kind)
    ordinal = maps[(prototype.index, kind)].FindIndex(shape)
    return (prototype.index, kind, ordinal) if ordinal else None


# --- read back ---------------------------------------------------------------------------------

# Why a ref of a document another system wrote resolves to nothing.
_NOT_LINKED = "the file links it to no face, edge or point of a part"


def records_of_document(doc: Any, prototypes: list[Any], root: str) -> list[dict[str, Any]]:
    """A document's annotations as records (``entries``' input): every GD&T object its tool holds,
    datums, dimensions and geometric tolerances in the tool's order, then the notes the code made
    in the notes tool's (a note another system wrote is not read), each resolved as the document
    is now. One the code made (its cadgen attribute) is resolved as its build resolved it
    (``_resolved``, against its part's faces and their names): its status is derived, never read.
    One another system wrote is resolved by the elements the file links it to, and what this module
    does not hold whole is ``unsupported``, with why (``_beyond_*``). ``prototypes`` are the document's
    (``document.Prototype``: each its label's entry and shape), ``root`` the name of its root."""
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_DimensionType_Location_LinearDistance,
                                        XCAFDimTolObjects_DimensionType_Size_Diameter,
                                        XCAFDimTolObjects_GeomToleranceTypeValue_Diameter,
                                        XCAFDimTolObjects_GeomToleranceTypeValue_None)
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_GeomTolerance, XCAFDoc_NoteComment

    from cadgen.engine.document import _entry

    dimensions = {XCAFDimTolObjects_DimensionType_Size_Diameter: "diameter",
                  XCAFDimTolObjects_DimensionType_Location_LinearDistance: "distance"}
    characteristics = {xcaf: name for name, xcaf in _xcaf_characteristics().items()}
    tool, notes_tool = _tool(doc), _notes_tool(doc)
    if tool is None and notes_tool is None:
        return []
    by_entry = {prototype.entry: prototype for prototype in prototypes}
    maps: dict[tuple[int, str], Any] = {}
    records: list[dict[str, Any]] = []

    def add(label: Any, kind: str, values: dict[str, Any], beyond: list[str], xcaf_type: str | None) -> None:
        """The record of a GD&T label holding an object of ``kind``."""
        held = _held_extra(label)
        first, second = ([_element(sequence.Value(at), by_entry, maps) for at in range(1, sequence.Length() + 1)]
                         for sequence in _linked(tool, label))
        if kind == "dimension" and second:
            targets = [("from", hit) for hit in first] + [("to", hit) for hit in second]
        else:
            targets = [("feature", hit) for hit in first]
        found = {"values": values, "targets": targets, "extra": held, "entry": _entry(label), "warnings": []}
        if held is not None:
            found.update(kind=held["kind"], xcaf_type=None, reason=None, part=_part_of(label, by_entry))
            records.append(found)
            return
        # Linked to an edge or a point: no annotation on faces, kept and listed, never drawn.
        beyond = beyond + [f"linked to {'an edge' if element == 'edge' else 'a point'}"
                           for element in sorted({hit[1] for _role, hit in targets if hit is not None} - {"face"})]
        refs = [{"role": role, "written": None, "status": "missing" if hit is None else "ok",
                 "ordinal": None if hit is None else hit[2], "candidates": [],
                 "problem": _NOT_LINKED if hit is None else None} for role, hit in targets]
        status = _worst(ref["status"] for ref in refs) if refs else "missing"
        parts = {hit[0] for _role, hit in targets if hit is not None}
        found.update(kind="unsupported" if beyond else kind, xcaf_type=xcaf_type if beyond else None,
                     reason="; ".join(beyond) or None, part=min(parts) if parts else None, status=status,
                     problem=None if status == "ok" else _NOT_LINKED, refs=refs)
        records.append(found)

    modified: set[str] = set()  # the datums a tolerance cannot be read with: modified, or targets
    for label in _labels(tool, "datum"):
        found = XCAFDoc_Datum.Set_s(label).GetObject()
        beyond = _beyond_datum(found)
        if beyond:
            modified.add(_entry(label))
        add(label, "datum", {"letter": _name_of(found)}, beyond, "XCAFDimTolObjects_DatumObject")
    for label in _labels(tool, "dimension"):
        found = XCAFDoc_Dimension.Set_s(label).GetObject()
        kind = dimensions.get(found.GetType())
        tolerance = None
        if found.IsDimWithPlusMinusTolerance():
            tolerance = {"type": "plus_minus", "upper": _as_held(found.GetUpperTolValue()),
                         "lower": _as_held(-found.GetLowerTolValue())}
        elif found.IsDimWithRange():
            tolerance = {"type": "limits", "lower": _as_held(found.GetLowerBound()),
                         "upper": _as_held(found.GetUpperBound())}
        notes = [(found.GetDescriptionName(at).ToCString(), found.GetDescription(at).ToCString())
                 for at in range(found.NbDescriptions())] if found.HasDescriptions() else []
        # A file's limits come with no nominal: XCAF's value is then their midpoint, no fact of the
        # file (one the code made is measured, below).
        nominal = None if found.IsDimWithRange() else _as_held(found.GetValue())
        values = {"type": kind, "basic": THEORETICAL in notes, "nominal": nominal, "tolerance": tolerance}
        if notes:
            values["notes"] = [list(note) for note in notes]
        add(label, "dimension", values, _beyond_dimension(found, kind, notes), found.GetType().name)
    for label in _labels(tool, "geometric_tolerance"):
        found = XCAFDoc_GeomTolerance.Set_s(label).GetObject()
        datums = _datums_of(label)
        letters = sorted((datum.GetPosition(), _name_of(datum))
                         for datum in (XCAFDoc_Datum.Set_s(named).GetObject() for named in datums))
        value_type = found.GetTypeOfValue()
        if value_type == XCAFDimTolObjects_GeomToleranceTypeValue_Diameter:
            zone = "diameter"
        elif value_type == XCAFDimTolObjects_GeomToleranceTypeValue_None:
            zone = None
        else:
            zone = "other"
        characteristic = characteristics.get(found.GetType())
        values = {"characteristic": characteristic, "value": _as_held(found.GetValue()), "unit": UNIT, "zone": zone,
                  "modifier": None, "datums": [letter for _place, letter in letters], "general": False}
        beyond = _beyond_tolerance(found, characteristic, zone)
        if any(_entry(named) in modified for named in datums):
            beyond.append("a datum it names has modifiers or is a datum target")
        add(label, "geometric_tolerance", values, beyond, found.GetType().name)
    labels = TDF_LabelSequence()
    if notes_tool is not None:
        notes_tool.GetNotes(labels)
    for label in (labels.Value(at) for at in range(1, labels.Length() + 1)):
        held = _held_extra(label)
        if held is None or held.get("kind") != "note" or not label.IsAttribute(XCAFDoc_NoteComment.GetID_s()):
            continue
        # Its text is XCAF's comment; its faces are resolved with its part's annotations, below.
        text = XCAFDoc_NoteComment.Get_s(label).Comment().ToExtString()
        records.append({"kind": "note", "values": {"text": text, "annotations": list(held["annotations"])},
                        "targets": [], "extra": held, "entry": _entry(label), "warnings": [], "xcaf_type": NOTE_TYPE,
                        "reason": None, "part": _part_of(label, by_entry)})
    # The code's annotations resolved as their build resolved them, each part's together (its general
    # profile covers what the others leave): the same faces again, from the document alone.
    of_part: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        if record["extra"] is not None:
            if record["extra"].get("general"):
                record["values"]["general"] = True  # the cadgen attribute's: XCAF has no place for it
            of_part.setdefault(record["part"], []).append(record)
    for index, held in of_part.items():
        prototype = prototypes[index]
        names = [prototype.face_names.get(at) for at in range(1, _faces(prototype.shape).Extent() + 1)]
        specs = [{"kind": record["extra"]["kind"], "refs": record["extra"]["refs"],
                  **(record["extra"].get("unlinked") or {record["extra"]["kind"]: record["values"]})} for record in held]
        for record, resolved in zip(held, _resolved_part(specs, prototype.shape, names, {prototype.name, root})):
            record.update(status=resolved.status, problem=resolved.problem, refs=_refs(resolved))
            if record["kind"] == "note":
                # A note's faces as resolved now (XCAF's links to them are for another reader, ``_note``).
                record["targets"] = ([(ref.role, (index, "face", ref.ordinal)) for ref in resolved.refs]
                                     if _on_faces(resolved) else [])
            if (record["values"].get("tolerance") or {}).get("type") == "limits":
                record["values"]["nominal"] = _as_held(resolved.nominal or 0.0)  # measured, as its build did
    return records


def _words(name: str) -> str:
    """An XCAF enumerator's name as words: ``..._Location_LinearDistance`` is ``location linear distance``."""
    tail = name.split("_", 2)[-1]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tail).replace("_", " ").lower()


def _beyond_datum(found: Any) -> list[str]:
    """What a datum of a file says that this module does not hold: modifiers, or a datum target."""
    from OCP.XCAFDimTolObjects import XCAFDimTolObjects_DatumModifWithValue_None

    beyond = []
    # The binding hands back a modifier-with-value's value alone (its kind is an out-parameter it
    # cannot fill): a value says one is set.
    if found.GetModifiers().Length() or found.GetModifierWithValue(XCAFDimTolObjects_DatumModifWithValue_None)[0]:
        beyond.append("it has modifiers")
    if found.IsDatumTarget():
        beyond.append("it is a datum target")
    return beyond


def _beyond_dimension(found: Any, kind: str | None, notes: list[tuple[str, str]]) -> list[str]:
    """What a dimension of a file says that this module does not hold: another type, a fit, a
    qualifier, modifiers, a note other than a basic one's, a basic dimension other than a distance;
    and limits beside any of them or on a basic dimension (limits are held alone). XCAF holds limits
    or deviations, never both."""
    beyond = []
    if kind is None:
        beyond.append(f"a {_words(found.GetType().name)} dimension is not one this holds")
    if found.IsDimWithClassOfTolerance():
        beyond.append("it has a class of tolerance (a fit)")
    if found.HasQualifier():
        beyond.append(f"it has a qualifier ({_words(found.GetQualifier().name)})")
    if found.GetModifiers().Length():
        beyond.append("it has modifiers")
    other = [list(note) for note in notes if note != THEORETICAL]
    if other:
        beyond.append(f"it has notes {other}")
    if THEORETICAL in notes and kind not in (None, "distance"):
        beyond.append(f"a basic {kind} is not one this holds")
    if found.IsDimWithRange() and (beyond or THEORETICAL in notes):
        beyond.append("it has limits (a range), held only on a dimension that says nothing more")
    return beyond


def _beyond_tolerance(found: Any, characteristic: str | None, zone: str | None) -> list[str]:
    """What a geometric tolerance of a file says that this module does not hold: another
    characteristic, modifiers, a material requirement, a zone modifier, a maximum value, a zone
    other than a width's or a diameter's, a diameter's on a surface profile."""
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_GeomToleranceMatReqModif_None,
                                        XCAFDimTolObjects_GeomToleranceZoneModif_None)

    beyond = []
    if characteristic is None:
        beyond.append(f"{_words(found.GetType().name)} is not a characteristic this holds")
    if found.GetModifiers().Length():
        beyond.append("it has modifiers")
    if found.GetMaterialRequirementModifier() != XCAFDimTolObjects_GeomToleranceMatReqModif_None:
        beyond.append(f"it has a material requirement ({_words(found.GetMaterialRequirementModifier().name)})")
    if found.GetZoneModifier() != XCAFDimTolObjects_GeomToleranceZoneModif_None:
        beyond.append(f"it has a {_words(found.GetZoneModifier().name)} zone")
    if found.GetMaxValueModifier() > 0:
        beyond.append("it has a maximum value")
    if zone == "other":
        beyond.append(f"its zone is {_words(found.GetTypeOfValue().name)}")
    if zone == "diameter" and characteristic == "surface_profile":
        beyond.append("a surface profile with a diametral zone is not one this holds")
    return beyond


def _refs(item: Resolved) -> list[dict[str, Any]]:
    """An annotation's refs as a record holds them (``records_of_document``, ``records_of_tree``)."""
    return [{"role": ref.role, "written": ref.written, "status": ref.status, "ordinal": ref.ordinal,
             "candidates": list(ref.candidates), "problem": ref.problem} for ref in item.refs]


def _name_of(datum: Any) -> str:
    """A datum object's letter; the empty string for none (a null handle reads as None)."""
    name = datum.GetName()
    return name.ToCString() if name is not None else ""


def records_of_tree(tree: Any, index_of: dict[int, int]) -> list[dict[str, Any]]:
    """A built tree's annotations as the records ``records_of_document`` reads back from its
    document: the same order (each part's datums, then the rest, its notes last), the same values,
    as XCAF holds them (``_as_held``), the same refs resolved; and each one's warnings (``warn``),
    which are the build's and no document's."""
    records = []
    for part, items in resolve(tree):
        index = index_of[id(part)]
        ordered = _datums_first(items)
        by_kind: dict[str, list] = {"datum": [], "dimension": [], "geometric_tolerance": [], "note": []}
        for item in ordered:
            spec = item.spec
            linked = _on_faces(item)
            targets = [(ref.role, (index, "face", ref.ordinal)) for ref in item.refs] if linked else []
            if spec["kind"] == "datum":
                values = {"letter": spec["datum"]["letter"]}
            elif spec["kind"] == "dimension":
                tolerance = spec["dimension"]["tolerance"] if item.nominal is not None else None
                values = {"type": spec["dimension"]["type"], "basic": bool(spec["dimension"].get("basic")),
                          "nominal": _as_held(item.nominal or 0.0),
                          "tolerance": None if tolerance is None else
                          {key: given if key == "type" else _as_held(given) for key, given in tolerance.items()}}
            elif spec["kind"] == "note":
                values = {"text": spec["note"]["text"], "annotations": list(spec["note"]["annotations"])}
            else:
                given = spec["geometric_tolerance"]
                values = {"characteristic": given["characteristic"], "value": _as_held(given["value"]), "unit": UNIT,
                          "zone": given["zone"], "modifier": None, "datums": list(given["datums"]) if linked else [],
                          "general": given["general"]}
            by_kind[spec["kind"]].append({
                "kind": spec["kind"], "values": values, "xcaf_type": NOTE_TYPE if spec["kind"] == "note" else None,
                "reason": None, "part": index,
                "targets": targets, "extra": json.loads(_text(_extra(item))), "entry": None, "status": item.status,
                "problem": item.problem, "refs": _refs(item),
                "warnings": list(tree.pmi_warnings.get((part.name, spec["id"])) or ())})
        records.extend(by_kind["datum"] + by_kind["dimension"] + by_kind["geometric_tolerance"] + by_kind["note"])
    # The document's GD&T tool lists datums, then dimensions, then tolerances, of every part; its
    # notes tool the notes after them.
    return sorted(records, key=lambda record: _KINDS.index(record["kind"]))


# The kinds of the code's records, in the order its document lists them.
_KINDS = ("datum", "dimension", "geometric_tolerance", "note")


def library_of_tree(tree: Any, index_of: dict[int, int]) -> list[dict[str, Any]]:
    """A built tree's notes libraries as ``library_of_document`` reads them back from its document:
    each note's ``part`` (a prototype index), ``name`` and ``text``, by part, in the project's order."""
    found = [{"part": index_of[id(part)], **given} for part, held in tree.pmi or () for given in _library(held)]
    return sorted(found, key=lambda given: given["part"])


def library_of_document(doc: Any, prototypes: list[Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi_library``: the notes library each part of a document holds (``annotate``'s
    ``library``, on its shape label), each note's ``part``, ``name`` and ``text``, by part, in the
    project's order; none where no part holds one."""
    from OCP.Standard import Standard_GUID
    from OCP.TDataStd import TDataStd_AsciiString
    from OCP.TDF import TDF_Label, TDF_Tool

    guid = Standard_GUID(LIBRARY_GUID)
    found = []
    for prototype in sorted(prototypes, key=lambda prototype: prototype.index):
        label, held = TDF_Label(), TDataStd_AsciiString()
        TDF_Tool.Label_s(doc.GetData(), prototype.entry, label)
        if label.IsNull() or not label.IsAttribute(guid) or not label.FindAttribute(guid, held):
            continue
        given = json.loads(held.Get().ToCString())
        if given.get("schema") == SCHEMA:
            found.extend({"part": prototype.index, "name": note["name"], "text": note["text"]}
                         for note in given["library"])
    return found


def views_of_tree(tree: Any, index_of: dict[int, int]) -> list[dict[str, Any]]:
    """A built tree's views as ``views_of_document`` reads them back from its document, by part, in
    the code's order."""
    found = [_view_entry(index_of[id(part)], json.loads(_text(_view_extra(given))))
             for part, held in tree.pmi or () for given in _views(held)]
    return sorted(found, key=lambda given: given["part"])


def views_of_document(doc: Any, prototypes: list[Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi_views``: each view the code gave a part of a document (``view``), served
    from its cadgen attribute (the XCAF view beside it is for another reader), by part, in the code's
    order: its ``part`` (a prototype index), ``name``, ``label``, ``camera`` (``_camera_of``),
    ``section`` (``{axis, at, invert}``, the Clip's, or None), ``shows`` (ids, or None for every
    annotation and note) and ``place`` (each placed id's ``{anchor, offset}``), in the part's frame.
    A view another system wrote (no cadgen attribute) is not read; none where there are none."""
    from OCP.TDF import TDF_LabelSequence
    from OCP.XCAFDoc import XCAFDoc_ViewTool

    label = doc.Main().FindChild(VIEWS_TAG, False)
    if label.IsNull() or not label.IsAttribute(XCAFDoc_ViewTool.GetID_s()):
        return []
    by_entry = {prototype.entry: prototype for prototype in prototypes}
    labels = TDF_LabelSequence()
    XCAFDoc_ViewTool.Set_s(label).GetViewLabels(labels)
    found = []
    for at in range(1, labels.Length() + 1):
        held = _held_extra(labels.Value(at))
        part = _part_of(labels.Value(at), by_entry)
        if held is not None and held.get("kind") == "view" and part is not None:
            found.append(_view_entry(part, held))
    return sorted(found, key=lambda given: given["part"])


def _view_entry(part: int, held: dict[str, Any]) -> dict[str, Any]:
    """A ``pmi_views`` entry of part ``part`` from the view's cadgen attribute (``_view_extra``)."""
    return {"part": part, "name": held["name"], "label": held["label"], "camera": _camera_of(held["camera"]),
            "section": held["section"], "shows": held["shows"], "place": held["place"]}


def _held_extra(label: Any) -> dict[str, Any] | None:
    """The cadgen attribute a label holds (``EXTRA_GUID``), or None where it holds none of ``SCHEMA``."""
    from OCP.Standard import Standard_GUID
    from OCP.TDataStd import TDataStd_AsciiString

    guid, found = Standard_GUID(EXTRA_GUID), TDataStd_AsciiString()
    if label.IsAttribute(guid) and label.FindAttribute(guid, found):
        held = json.loads(found.Get().ToCString())
        return held if held.get("schema") == SCHEMA else None
    return None


def _part_of(label: Any, by_entry: dict[str, Any]) -> int | None:
    """The prototype index of what the code gave a part: its label's ``TDF_Reference``'s."""
    from OCP.TDF import TDF_Reference

    from cadgen.engine.document import _entry

    found = TDF_Reference()
    if not label.FindAttribute(TDF_Reference.GetID_s(), found):
        return None
    prototype = by_entry.get(_entry(found.Get()))
    return None if prototype is None else prototype.index


def _as_held(value: float) -> float:
    """A real as XCAF holds and reads it back: a double, its zero unsigned (a deviation of 0 is
    held as the magnitude -0)."""
    return float(value) + 0.0


def entries(records: list[dict[str, Any]], structure: dict[str, Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi``: one JSON-plain entry per record -- ``id``, ``kind`` (``dimension``,
    ``datum``, ``geometric_tolerance``, ``note``, ``unsupported``), ``label``, ``status``,
    ``problem``, ``warnings``, ``part`` (a prototype index), ``refs`` (each ``role``, ``ref`` --
    canonical as ``refs`` spells it for this document --, ``written``, ``status``, ``candidates``,
    ``problem``), ``presentation``, ``xcaf_type``, an unsupported one's ``reason``, and the kind's
    own block of values. A note's (``note``) is its ``number`` (its part's general profile Note 1
    where it has one, then each note in the code's order), ``text``, ``general`` (it names no face
    and no annotation) and the ``annotations`` it names, as written."""
    canonical = _canonical(structure)
    found = []
    counters: dict[str, int] = {}
    # Each part's notes are numbered after its general profile, Note 1 where it has one.
    numbers = {record["part"]: 1 for record in records if (record["extra"] or {}).get("general")}
    for record in records:
        extra, kind = record["extra"], record["kind"]
        targets = list(record["targets"])
        refs = []
        for at, ref in enumerate(record["refs"]):
            hit = targets[at][1] if at < len(targets) else None
            refs.append({"role": ref["role"], "written": ref["written"], "status": ref["status"],
                         "ref": canonical(*hit) if hit is not None else ref["written"],
                         "candidates": [canonical(record["part"], "face", ordinal)
                                        for ordinal in ref["candidates"]] or None,
                         "problem": ref["problem"]})
        if extra is not None:
            ident, label, presentation = extra["id"], extra["label"], extra["presentation"]
            unlinked = extra.get("unlinked")
        else:
            counters[kind] = counters.get(kind, 0) + 1
            ident = (record["values"].get("letter") or kind) if kind == "datum" else f"{kind}-{counters[kind]}"
            label, presentation, unlinked = None, None, None
        entry = {"id": ident, "kind": kind, "label": label, "status": record["status"], "problem": record["problem"],
                 "warnings": list(record["warnings"]), "part": record["part"], "refs": refs,
                 "presentation": presentation, "xcaf_type": record["xcaf_type"]}
        values = record["values"]
        if kind == "datum":
            entry["datum"] = {"letter": values["letter"]}
        elif kind == "dimension":
            if unlinked is not None:
                entry["dimension"] = {"type": unlinked["dimension"]["type"],
                                      "basic": bool(unlinked["dimension"].get("basic")), "nominal": None,
                                      "tolerance": unlinked["dimension"]["tolerance"]}
            else:
                # Measured from the geometry where the code made it; as the file says, where another
                # system did, and none where the file states limits alone.
                entry["dimension"] = {"type": values["type"], "basic": bool(values.get("basic")),
                                      "nominal": None if values["nominal"] is None else
                                      {"value": values["nominal"], "unit": UNIT,
                                       "source": "geometry" if extra is not None else "file"},
                                      "tolerance": values["tolerance"]}
        elif kind == "geometric_tolerance":
            entry["geometric_tolerance"] = dict(unlinked["geometric_tolerance"] if unlinked is not None else values)
        elif kind == "note":
            numbers[record["part"]] = numbers.get(record["part"], 0) + 1
            entry["note"] = {"number": numbers[record["part"]], "text": values["text"],
                             "general": not extra["refs"] and not values["annotations"],
                             "annotations": list(values["annotations"])}
        else:
            entry["reason"] = record["reason"]
            entry["values"] = values
        found.append(entry)
    return found


def _canonical(structure: dict[str, Any]) -> Callable[[int, str, int], str]:
    """How ``structure`` spells an element of a prototype -- by its index, the element's kind and
    its ordinal -- canonically, as ``refs`` spells it for that document: under the prototype's first
    placement, by its name where it has one."""
    from cadgen.engine import refs as grammar

    root = grammar.structure_tree(structure)
    first_node: dict[int, Any] = {}
    for node in root.parts():
        first_node.setdefault(node.payload["prototype"], node)
    one_part = len(root.parts()) == 1
    prototypes = structure["prototypes"]
    named = {"face": "faceNames", "edge": "edgeNames", "vertex": "vertexNames"}

    def canonical(index: int, kind: str, ordinal: int) -> str:
        name = (prototypes[index].get(named[kind]) or {}).get(str(ordinal))
        node = first_node.get(index)
        if node is None:
            return name or f"{kind} {ordinal}"
        return grammar._element_ref(root, node, kind, ordinal, name, one_part)

    return canonical


def coverage_of(structure: dict[str, Any], shapes: Mapping[int, Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi_coverage``: ``coverage`` of each part its ``pmi`` has an entry on, as
    ``{"part", "uncovered", "conflicts"}``, by part (a prototype index), its faces every face of its
    shape (``shapes``, by prototype index) as the structure spells them. A part with no entry says
    nothing. Derived where the structure is served, the build's report read from the same."""
    entries = structure.get("pmi") or []
    canonical = _canonical(structure)
    found = []
    for index in sorted({entry["part"] for entry in entries if entry["part"] is not None}):
        faces = [canonical(index, "face", at) for at in range(1, _faces(shapes[index]).Extent() + 1)]
        found.append({"part": index, **coverage([entry for entry in entries if entry["part"] == index], faces)})
    return found


def read(source: Any) -> list[dict[str, Any]]:
    """The annotations a document holds (``entries``): an ``.xbf`` or a ``.step`` by its path,
    read as the viewer reads it (``document.Loaded``)."""
    from pathlib import Path

    from cadgen.engine import document

    return list(document.Loaded(Path(source)).structure().get("pmi") or [])


# --- exports -----------------------------------------------------------------------------------


def step_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries of a document's PMI (``entries``) a STEP carries: every one but its notes, which
    are the xbf's alone (OCCT's STEP writer writes no notes)."""
    return [entry for entry in entries if entry.get("kind") != "note"]


def dropped(view: Any, kind: str) -> list[tuple[dict[str, Any], str]]:
    """Each annotation of a document that a ``kind`` file written from ``view`` does not carry whole,
    and why: a posed or partial STEP or xbf, or an xbf of a document this engine wrote, is a document
    made again from the view (``tree.tree_of``), which carries no PMI; and a STEP drops one linked to
    no geometry, as an xbf of a STEP (which copies its GD&T as read, ``copy``) keeps one the file links
    to no element of a part linked to nothing. A STEP carries no note, whole or not, and is never
    refused for one (``step_entries``). A mesh carries no B-rep, so no PMI."""
    entries = view.source.structure.get("pmi") or []
    if kind == "step":
        entries = step_entries(entries)
    if kind not in ("step", "xbf") or not entries:
        return []
    shown = "STEP" if kind == "step" else kind
    if view.posed or view.parted:
        why = f"a {'posed' if view.posed else 'partial'} {shown} is a document made again, which carries no PMI"
        return [(entry, why) for entry in entries]
    if kind == "xbf" and not view.source.foreign:
        return [(entry, "an xbf written from it is a document made again, which carries no PMI") for entry in entries]
    return [(entry, f"{entry['status']}: {entry['problem']}") for entry in entries if entry["status"] != "ok"]


def refuse_dropped(view: Any, kind: str) -> None:
    """A ``kind`` file of ``view`` that would not carry whole an annotation the code made
    (``dropped``), refused by name: it would be no translation of the model's document; so is an
    xbf made again of one holding the code's views or notes library (``pmi_views``,
    ``pmi_library``), which it would lose as it would annotations, named. One of a document another
    system wrote is written: ``export.translate`` says what it leaves out."""
    from cadgen.engine.export import ExportRefused

    lost = [(entry, why) for entry, why in dropped(view, kind) if _from_code(entry)]
    structure = view.source.structure
    if kind == "xbf":
        again = view.posed or view.parted or not view.source.foreign
        views = [given["name"] for given in structure.get("pmi_views") or []] if again else []
        library = [given["name"] for given in structure.get("pmi_library") or []] if again else []
        held = [f"{len(structure['pmi'])} PMI annotation(s)"] if lost else []
        if views:
            held.append(f"{len(views)} named view(s) ({', '.join(views)})")
        if library:
            held.append(f"a notes library ({', '.join(library)})")
        if held:
            said = held[0] if len(held) == 1 else f"{', '.join(held[:-1])} and {held[-1]}"
            raise ExportRefused(f"{view.source.name} holds {said}, and an xbf written from it is a document made "
                                "again, which carries none yet: export it as built, whole")
        return
    if not lost:
        return
    held = len(step_entries(structure["pmi"]))
    if view.posed or view.parted:
        raise ExportRefused(f"the document holds {held} PMI annotation(s), and a posed or partial STEP is a "
                            "document made again, which carries none: export it as built, whole")
    raise ExportRefused("a STEP would drop PMI linked to no geometry: "
                        + "; ".join(f"{entry['id']} ({why})" for entry, why in lost)
                        + ". Fix the refs in the model, or remove the annotations")


def _from_code(entry: dict[str, Any]) -> bool:
    """Whether an entry is an annotation a model's code made (its refs as the code wrote them, a
    general profile, whose faces none writes, or a note, which only the code's are read as), not one
    read from a file another system wrote."""
    return (any(ref.get("written") is not None for ref in entry.get("refs") or ())
            or bool((entry.get("geometric_tolerance") or {}).get("general")) or entry.get("kind") == "note")
