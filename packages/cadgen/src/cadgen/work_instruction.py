"""Work instructions: ``@work_instruction``, :class:`Instruction` and the process records.

A work instruction is the HOW of one build: the steps a technician follows to put
one specific assembly together, in order, with the values each step needs. An
engineering drawing states the finished state; a process specification states
the company's rules for a kind of work (fastening, bonding, curing, layup,
machining) across every part. A work instruction applies those rules to one
assembly, so the technician holds exactly the steps for this build and not a
hundred pages of spec.

Every value a step prints -- a torque, an adhesive's mix ratio and pot life, a
cure cycle, a ply schedule, a feed and speed -- names where it came from: a
section of a process spec the user supplied (:class:`Spec`), a callout on the
assembly drawing (:class:`Drawing`), or something the user said
(:class:`Stated`). Nothing here has a default value for any of them. A value
nobody stated prints as a captioned blank, ``NOT STATED``, and the run lists it,
so a draft says exactly what engineering still owes the floor. A released
instruction (``status="released"``) refuses to be written with one.

Usage (every document and value here is a placeholder: a real one is copied
from the section of the user's document it cites)::

    import cadgen
    from pathlib import Path
    from cadgen.work_instruction import work_instruction, Instruction, Spec, Drawing, Torque

    FASTENING = Spec("PS-XXXX", "<fastening spec title>", revision="<rev>")
    DWG = Drawing("DWG-ZZZZ", revision="<rev>")

    @work_instruction(out="../PDF/bracket_assembly_wi.pdf")
    def bracket_assembly_wi():
        wi = Instruction(Path(__file__).parent / "../STEP/bracket_assembly.step",
                         title="BRACKET ASSEMBLY", number="WI-0001", revision="A", drawing=DWG)
        wi.step("Place the base plate on the fixture", install=["base_plate"])
        wi.step("Fasten the bracket to the base plate", install=["bracket"]).fasten(
            "<screw part number>", qty=4,
            torque=Torque(1, 2, "in-lbf", per=FASTENING.at("<table>")))  # <low>, <high> as stated
        return wi

    if __name__ == "__main__":
        bracket_assembly_wi()

Running the script writes one PDF at ``out``: a cover page (documents, parts,
materials, open items) and a page per step, each with a picture of the assembly
as it stands after that step -- drawn as line art, the step's own parts filled,
parts still to come left out -- and the fill-ins the floor records
(lot numbers, mix and cure times, stamps).

Like ``@eng_drawing`` this is a document over a document, with no public function
and no CLI: the script is the program. Import discipline: nothing here pulls in
matplotlib or the CAD kernel at module scope.
"""

from __future__ import annotations

import functools
import math
from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

__all__ = [
    "work_instruction", "Instruction", "Step",
    "Spec", "Drawing", "Datasheet", "Stated", "Source", "Cited",
    "Torque", "Material", "Adhesive", "Layup", "Cure", "Machining",
    "TORQUE_UNITS", "CAMERAS", "PAGE_SIZES", "STATUSES", "SOURCE_KINDS", "NOTICES",
]

TORQUE_UNITS = ("in-lbf", "ft-lbf", "N-m")
CAMERAS = ("iso", "front", "back", "left", "right", "top", "bottom")
PAGE_SIZES = ("LETTER", "A4")
NOTICES = ("WARNING", "CAUTION", "NOTE")
STATUSES = ("draft", "released")
NOT_STATED = "NOT STATED"


def _text(name: str, value, *, required: bool = True) -> str | None:
    """A printed field: a non-blank string, or None where the field may be absent."""
    if value is None:
        if required:
            raise TypeError(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    value = " ".join(value.split())
    if not value:
        raise ValueError(f"{name} must not be blank: leave it out (None) to print it as {NOT_STATED}")
    return value


def _lines(name: str, values) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} takes a list of lines, not one string: {name}=[{values!r}]")
    return [_text(f"{name} line", value) for value in values]


def _one_of(name: str, value, allowed: Sequence[str]) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}; got {value!r}")
    return value


# --- where a value comes from ------------------------------------------------

SOURCE_KINDS = ("spec", "drawing", "datasheet", "stated")


@dataclass(frozen=True)
class Source:
    """Where one value comes from: made by :meth:`Spec.at`, :meth:`Drawing.at`,
    :meth:`Datasheet.at` or :func:`Stated`. ``kind`` is one of :data:`SOURCE_KINDS`,
    and a document and (but for ``stated``) the place in it are required."""

    kind: str
    document: str
    where: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        _one_of("Source kind", self.kind, SOURCE_KINDS)
        object.__setattr__(self, "document", _text("Source document", self.document))
        if self.kind != "stated":
            object.__setattr__(self, "where", _text(f"the place in {self.document}", self.where or None))

    def cite(self) -> str:
        if self.kind == "stated":
            return self.document
        if self.kind == "drawing":
            return f"{self.document}, {self.where} (drawing callout)"
        return f"{self.document} {self.where}" if self.kind == "spec" else f"{self.document}, {self.where}"


@dataclass(frozen=True)
class Spec:
    """A company process specification as the user supplied it: its number, title
    and revision. ``spec.at("4.2, Table 3")`` is a :class:`Source` naming the
    section a value was read from."""

    number: str
    title: str
    revision: str

    def __post_init__(self) -> None:
        for name in ("number", "title", "revision"):
            object.__setattr__(self, name, _text(f"Spec {name}", getattr(self, name)))

    @property
    def name(self) -> str:
        return f"{self.number} Rev {self.revision}"

    def at(self, section: str) -> Source:
        return Source("spec", self.name, f"\u00a7{_text('Spec.at section', section)}", self.title)


@dataclass(frozen=True)
class Drawing:
    """The assembly drawing. ``drawing.at("note 4")`` is a :class:`Source` for a
    value a drawing callout states -- a deviation from the general spec."""

    number: str
    revision: str
    title: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", _text("Drawing number", self.number))
        object.__setattr__(self, "revision", _text("Drawing revision", self.revision))
        object.__setattr__(self, "title", _text("Drawing title", self.title or None, required=False) or "")

    @property
    def name(self) -> str:
        return f"{self.number} Rev {self.revision}"

    def at(self, callout: str) -> Source:
        return Source("drawing", self.name, _text("Drawing.at callout", callout), self.title)


@dataclass(frozen=True)
class Datasheet:
    """A manufacturer's technical data sheet the user supplied, for a product the
    spec defers to (an adhesive's mix ratio and pot life, a prepreg's cure).
    ``revision`` is as the sheet prints it -- a revision letter or a date."""

    product: str
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "product", _text("Datasheet product", self.product))
        object.__setattr__(self, "revision", _text("Datasheet revision", self.revision))

    @property
    def name(self) -> str:
        return f"{self.product} datasheet, {self.revision}"

    def at(self, section: str) -> Source:
        return Source("datasheet", self.name, _text("Datasheet.at section", section), "Manufacturer's data sheet")


def Stated(by: str, *, on: str) -> Source:  # noqa: N802 - reads as the record it makes
    """A value the user stated themself: who said it and the date (``on``, as
    written, e.g. ``"2026-10-23"``). Use it only for what the person actually
    said; a value read from a document cites that document instead."""
    return Source("stated", f"stated by {_text('Stated by', by)}, {_text('Stated on', on)}")


def _source(owner: str, per) -> Source:
    if not isinstance(per, Source):
        raise TypeError(
            f"{owner} needs per=: where the value comes from -- Spec(...).at(section), "
            "Drawing(...).at(callout), Datasheet(...).at(section) or Stated(by, on=date). "
            "A value with no source is not written down."
        )
    return per


@dataclass(frozen=True)
class Cited:
    """One field of a record that comes from a different document than the rest:
    ``Adhesive(..., mix=Cited("100:17 by weight", per=TDS.at("Mixing")), per=SPEC.at("5.1"))``."""

    text: str
    _: KW_ONLY
    per: Source | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _text("Cited text", self.text))
        _source("Cited", self.per)


# --- process records ---------------------------------------------------------


@dataclass(frozen=True)
class Torque:
    """A torque, ``Torque(20, 25, "in-lbf", per=...)`` for a range or
    ``Torque(30, unit="N-m", per=...)`` for one value. The unit is one of
    :data:`TORQUE_UNITS`; nothing is converted or rounded."""

    low: float
    high: float | None = None
    unit: str = ""
    _: KW_ONLY
    per: Source | None = None

    def __post_init__(self) -> None:
        for name in ("low", "high"):
            value = getattr(self, name)
            if value is None and name == "high":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Torque {name} must be a positive number, got {value!r}")
        if self.high is not None and self.high < self.low:
            raise ValueError(f"Torque high ({self.high}) is below low ({self.low})")
        _one_of("Torque unit", self.unit, TORQUE_UNITS)
        _source("Torque", self.per)

    def text(self) -> str:
        span = _num(self.low) if self.high is None or self.high == self.low else f"{_num(self.low)}\u2013{_num(self.high)}"
        return f"{span} {self.unit}"


def _num(value: float) -> str:
    """The number as it was given: 12.345678 stays 12.345678, and 40.0 prints 40."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


@dataclass(frozen=True)
class _Record:
    """A process record: its fields are printed text (or :class:`Cited` text), a
    required one left out prints as NOT STATED. Subclasses name REQUIRED and OPTIONAL."""

    REQUIRED = ()
    OPTIONAL = ()

    def __post_init__(self) -> None:
        kind = type(self).__name__
        object.__setattr__(self, "name", _text(f"{kind} name", self.name))
        for key in self.REQUIRED + self.OPTIONAL:
            value = getattr(self, key)
            if not isinstance(value, Cited):
                object.__setattr__(self, key, _text(f"{kind} {key}", value, required=False))
        _source(kind, self.per)

    def fields(self) -> list[tuple[str, str | None, Source | None]]:
        """(caption, text, source) to print; a required field's None is NOT STATED."""
        rows = []
        for key in self.REQUIRED + tuple(k for k in self.OPTIONAL if getattr(self, k) is not None):
            value = getattr(self, key)
            if isinstance(value, Cited):
                rows.append((key.replace("_", " "), value.text, value.per))
            else:
                rows.append((key.replace("_", " "), value, self.per if value is not None else None))
        return rows

    def missing(self) -> list[str]:
        return [key.replace("_", " ") for key in self.REQUIRED if getattr(self, key) is None]


@dataclass(frozen=True)
class Material(_Record):
    """A consumable a step uses with no process record of its own: a
    threadlocker, a sealant, a primer. ``note`` is how it is applied, as stated."""

    name: str
    _: KW_ONLY
    per: Source | None = None
    note: str | Cited | None = None
    OPTIONAL = ("note",)


@dataclass(frozen=True)
class Adhesive(_Record):
    """A bonding process record: surface prep, mixing, pot life and cure, each as
    the spec states it -- or, where the spec defers to the manufacturer, as
    :class:`Cited` text from the :class:`Datasheet`."""

    name: str
    _: KW_ONLY
    prep: str | Cited | None = None
    mix: str | Cited | None = None
    pot_life: str | Cited | None = None
    cure: str | Cited | None = None
    per: Source | None = None
    REQUIRED = ("prep", "mix", "pot_life", "cure")


@dataclass(frozen=True)
class Layup(_Record):
    """A composite layup: the material and the ply schedule, and debulking where
    the spec calls for it."""

    name: str
    _: KW_ONLY
    plies: str | Cited | None = None
    debulk: str | Cited | None = None
    per: Source | None = None
    REQUIRED = ("plies",)
    OPTIONAL = ("debulk",)


@dataclass(frozen=True)
class Cure(_Record):
    """A cure cycle: ramp, hold, pressure and cool-down as the spec states them."""

    name: str
    _: KW_ONLY
    cycle: str | Cited | None = None
    per: Source | None = None
    REQUIRED = ("cycle",)


@dataclass(frozen=True)
class Machining(_Record):
    """A machining operation's cutting data: tool, speed and feed, with coolant
    where the spec states it."""

    name: str
    _: KW_ONLY
    tool: str | Cited | None = None
    speed: str | Cited | None = None
    feed: str | Cited | None = None
    coolant: str | Cited | None = None
    per: Source | None = None
    REQUIRED = ("tool", "speed", "feed")
    OPTIONAL = ("coolant",)


# --- steps -------------------------------------------------------------------

# What the floor writes down in each kind of operation: the actual reading and the
# lot, time and equipment it was made with. Blanks to fill in, not values anyone owes:
# a NOT STATED field is engineering's; these are the technician's. The tools a step
# uses (a torque wrench, an oven) are listed once, on the front pages, with their
# calibration blanks.
RECORDS = {
    "fasten": ("Actual torque",),
    "bond": ("Adhesive lot", "Expiry", "Mixed at", "Mated at"),
    "layup": ("Material lot", "Out-time"),
    "cure": ("Oven / autoclave ID", "Start", "End", "Chart no."),
    "machine": ("Machine ID",),
}
# Equipment a kind of operation implies, for the front pages' equipment list.
EQUIPMENT = {"fasten": "Torque wrench", "cure": "Oven / autoclave"}


@dataclass(frozen=True)
class _Line:
    """One printed row: a ``None`` value is NOT STATED, and so is a ``None``
    source where one is owed (an inspection criterion with no document)."""

    caption: str
    value: str | None
    source: Source | None = None
    cite: bool = False


@dataclass
class _Op:
    kind: str
    lines: list[_Line]
    missing: list[str] = field(default_factory=list)
    record: str | None = None  # an inspection's measured-value caption
    surfaces: tuple[tuple[str, str], ...] = ()  # (face ref, the leaf occurrence it is on)


class Step:
    """One step: a title, the parts it installs, and its operations in order.
    Made by :meth:`Instruction.step`; every method returns the step, so they chain."""

    def __init__(self, instruction: "Instruction", number: int, title: str, install: tuple[str, ...],
                 camera: str | None, picture: bool, operation: int | None) -> None:
        self._instruction = instruction
        self.number = number
        self.title = title
        self.install = install
        self.camera = camera
        self.picture = picture
        self.operation = operation
        self.ops: list[_Op] = []
        self.notices: list[tuple[str, str]] = []
        self.hold = False
        self.record: str | None = None

    def _add(self, op: _Op) -> "Step":
        self.ops.append(op)
        return self

    def instruct(self, text: str) -> "Step":
        """A plain instruction, in the words the user gave."""
        return self._add(_Op("instruct", [_Line("", _text("instruct text", text))]))

    def _notice(self, kind: str, text: str) -> "Step":
        self.notices.append((kind, _text(f"{kind.lower()} text", text)))
        return self

    def warning(self, text: str) -> "Step":
        """A WARNING (harm to people), boxed above the step it governs."""
        return self._notice("WARNING", text)

    def caution(self, text: str) -> "Step":
        """A CAUTION (harm to the hardware), boxed above the step it governs."""
        return self._notice("CAUTION", text)

    def note(self, text: str) -> "Step":
        """A NOTE, boxed above the step."""
        return self._notice("NOTE", text)

    def fasten(self, hardware: str, *, qty: int | None = None, torque: Torque | None = None,
               locking: Material | None = None, sequence: str | None = None) -> "Step":
        """Install threaded hardware. ``torque=None`` prints NOT STATED: a threaded
        joint with no stated torque is an open item, not a default."""
        hardware = _text("fasten hardware", hardware)
        if qty is not None and (isinstance(qty, bool) or not isinstance(qty, int) or qty < 1):
            raise ValueError(f"fasten qty must be a positive integer, got {qty!r}")
        if torque is not None and not isinstance(torque, Torque):
            raise TypeError("fasten torque= takes a Torque(...)")
        if locking is not None and not isinstance(locking, Material):
            raise TypeError("fasten locking= takes a Material(...)")
        lines = [_Line("Hardware", f"{hardware}{f', qty {qty}' if qty else ''}"),
                 _Line("Torque", torque.text() if torque else None, torque.per if torque else None)]
        if locking is not None:
            self._instruction._use(locking)
            lines += [_Line("Locking", locking.name, locking.per)]
            lines += [_Line(caption.capitalize(), value, source) for caption, value, source in locking.fields()]
        if sequence is not None:
            lines.append(_Line("Sequence", _text("fasten sequence", sequence)))
        return self._add(_Op("fasten", lines, missing=[] if torque else ["torque"]))

    def _record(self, kind: str, record, cls, label: str, surfaces=()) -> "Step":
        if record is None:
            return self._add(_Op(kind, [_Line(label, None)], missing=[label.lower()],
                                 surfaces=self._faces(surfaces)))
        if not isinstance(record, cls):
            raise TypeError(f"{kind}() takes a {cls.__name__}(...) or None, got {type(record).__name__}")
        lines = [_Line(label, record.name, record.per)]
        lines += [_Line(caption.capitalize(), value, source) for caption, value, source in record.fields()]
        if kind in ("bond", "layup"):  # a consumable the kit list carries; a cure or a cut is not
            self._instruction._use(record)
        return self._add(_Op(kind, lines, missing=record.missing(), surfaces=self._faces(surfaces)))

    def bond(self, adhesive: Adhesive | None, *, surfaces: Iterable[str] = ()) -> "Step":
        """Bond with an adhesive. ``surfaces`` are face refs (``#o1.2.f3``) marked
        on the step's picture; ``None`` for the adhesive prints NOT STATED."""
        return self._record("bond", adhesive, Adhesive, "Adhesive", surfaces)

    def layup(self, layup: Layup | None) -> "Step":
        return self._record("layup", layup, Layup, "Material")

    def cure(self, cure: Cure | None) -> "Step":
        return self._record("cure", cure, Cure, "Cure")

    def machine(self, machining: Machining | None, *, surfaces: Iterable[str] = ()) -> "Step":
        return self._record("machine", machining, Machining, "Operation", surfaces)

    def apply(self, material: Material, *, surfaces: Iterable[str] = ()) -> "Step":
        """Apply a consumable (sealant, primer, threadlocker) with no record of its own."""
        if not isinstance(material, Material):
            raise TypeError("apply() takes a Material(...)")
        self._instruction._use(material)
        lines = [_Line("Apply", material.name, material.per)]
        lines += [_Line("How", value, source) for _caption, value, source in material.fields()]
        return self._add(_Op("apply", lines, surfaces=self._faces(surfaces)))

    def _faces(self, refs) -> tuple[tuple[str, str], ...]:
        """Each surface ref resolved on the assembly to exactly one face."""
        if isinstance(refs, (str, bytes)):
            raise TypeError(f"surfaces takes a sequence of face refs, not one string: surfaces=({refs!r},)")
        out = []
        for ref in refs:
            ref = _text("surface ref", ref)
            try:
                found = self._instruction.scene.resolve(ref)
            except Exception as exc:  # noqa: BLE001 - re-raised naming the step
                raise ValueError(f"step {self.number}: {ref} is not on {self._instruction.step_path.name}: {exc}") from exc
            if len(found) != 1 or found[0].kind != "face":
                raise ValueError(f"step {self.number}: surfaces takes face refs such as '#o1.2.f3'; "
                                 f"{ref} names {len(found)} {found[0].kind if found else 'entity'}(s)")
            out.append((found[0].ref, found[0].occurrence_ref))
        return tuple(out)

    def inspect(self, text: str, *, per: Source | None = None, record: str | None = None) -> "Step":
        """An inspection hold point: the step is not complete until QA stamps it.
        The criterion cites where it comes from; with ``per=None`` its source
        prints NOT STATED and is an open item. ``record`` captions a blank for
        the measured value (``"Pin height, mm"``)."""
        if per is not None:
            _source("inspect", per)
        self.hold = True
        line = _Line("Inspect", _text("inspect text", text), per, cite=True)
        op = _Op("inspect", [line], missing=[] if per else ["criterion source"])
        op.record = _text("inspect record", record, required=False)
        return self._add(op)


class Instruction:
    """The work instruction for one assembly STEP.

    ``status`` is ``draft`` (the default: every page says DRAFT, and NOT STATED
    values and parts no step installs are listed) or ``released`` (either one is
    refused). ``size`` is one of :data:`PAGE_SIZES` (US Letter by default),
    ``camera`` one of :data:`CAMERAS` for every step's picture (a step may name
    its own). ``pictures=False`` writes the document with no pictures and needs
    no browser.

    The front pages carry ``scope`` (a sentence: what this instruction builds and
    when it applies), ``safety`` (the PPE and hazards the user's documents state),
    ``tools`` (fixtures and tooling the user names, beside the equipment the steps
    imply) and ``revisions`` (``(rev, date, change)`` rows), each only if given.
    """

    def __init__(self, step_path: str | Path, *, title: str, number: str, revision: str,
                 part_number: str = "", drawing: Drawing | None = None, author: str = "",
                 status: str = "draft", size: str = "LETTER", camera: str = "iso", pictures: bool = True,
                 scope: str = "", safety: Sequence[str] = (), tools: Sequence[str] = (),
                 revisions: Sequence[tuple[str, str, str]] = ()) -> None:
        self.step_path = Path(step_path).resolve()
        if self.step_path.suffix.lower() not in (".step", ".stp"):
            raise ValueError(f"Instruction takes an assembly .step, got {str(step_path)!r}")
        if not self.step_path.is_file():
            raise FileNotFoundError(f"no STEP at {self.step_path}: run the assembly's model first")
        self.title = _text("title", title)
        self.number = _text("number", number)
        self.revision = _text("revision", revision)
        self.part_number = _text("part_number", part_number or None, required=False) or ""
        self.author = _text("author", author or None, required=False) or ""
        if drawing is not None and not isinstance(drawing, Drawing):
            raise TypeError("drawing= takes a Drawing(number, revision=...)")
        self.drawing = drawing
        self.status = _one_of("status", status, STATUSES)
        self.size = _one_of("size", size, PAGE_SIZES)
        self.camera = _one_of("camera", camera, CAMERAS)
        self.pictures = bool(pictures)
        self.scope = _text("scope", scope or None, required=False) or ""
        self.safety = _lines("safety", safety)
        self.tools = _lines("tools", tools)
        if isinstance(revisions, (str, bytes)) or any(
                not isinstance(row, (tuple, list)) or len(row) != 3 for row in revisions):
            raise TypeError("revisions takes (rev, date, change) rows")
        self.revisions = [tuple(_text("revisions cell", cell) for cell in row) for row in revisions]
        self.operations: list[str] = []
        self.steps: list[Step] = []
        self.materials: list[_Record] = []
        self._scene = None
        self._installed: dict[str, int] = {}
        self.scene  # read now: a single part, or a file that is no assembly, is refused before any step

    @property
    def scene(self):
        if self._scene is None:
            from cadgen.step_scene import read_scene

            self._scene = read_scene(self.step_path)
            if len(list(self._scene.leaves())) < 2:
                raise TypeError(f"{self.step_path.name} is a single part: a work instruction is for an assembly")
        return self._scene

    def leaves(self) -> list:
        return list(self.scene.leaves())

    def _leaf_refs(self, key: str) -> list[str]:
        """The leaf occurrences a part name or occurrence ref installs."""
        key = _text("install ref", key)
        leaves = self.leaves()
        by_ref = {leaf.ref: leaf for leaf in leaves}
        if key in by_ref:
            return [key]
        if key.startswith("#o"):
            under = [leaf.ref for leaf in leaves if leaf.ref.startswith(key + ".")]
            if under:
                return under
        else:
            named = [leaf.ref for leaf in leaves if leaf.label == key or (leaf.label or "").split(":")[0] == key]
            if named:
                return named
            try:  # a subassembly's label, or a numbered alias of a shared one
                found = self.scene.resolve(key)
            except Exception:  # noqa: BLE001 - not a name the assembly has; refused below with the list
                found = ()
            under = [leaf.ref for sel in found if sel.kind == "occurrence"
                     for leaf in leaves if leaf.ref == sel.ref or leaf.ref.startswith(sel.ref + ".")]
            if under:
                return under
        listing = ", ".join(f"{leaf.ref} {leaf.label or '(unnamed)'}" for leaf in leaves)
        raise KeyError(f"{key!r} is not a part of {self.step_path.name}; its parts are: {listing}")

    def operation(self, title: str) -> "Instruction":
        """Start the next operation: a heading over the steps that follow it (and a
        line in the front pages' overview). Steps keep one sequence across them."""
        self.operations.append(_text("operation title", title))
        return self

    def step(self, title: str, *, install: Iterable[str] = (), camera: str | None = None,
             picture: bool = True) -> Step:
        """Add the next step. ``install`` names the parts this step puts in place
        (labels, or occurrence refs such as ``#o1.2``; a label several parts share
        installs every one of them). A part is installed by one step only."""
        if isinstance(install, (str, bytes)):
            raise TypeError(f"install takes a sequence of part names or refs, not one string: install=({install!r},)")
        number = len(self.steps) + 1
        # Everything that can refuse is checked before a part is claimed, so a refused
        # step leaves the parts free for the next one.
        title = _text("step title", title)
        camera = None if camera is None else _one_of("camera", camera, CAMERAS)
        refs: list[str] = []
        for key in install:
            for ref in self._leaf_refs(key):
                if ref in self._installed:
                    raise ValueError(f"step {number} installs {key!r} ({ref}), which step {self._installed[ref]} already installs")
                if ref not in refs:
                    refs.append(ref)
        for ref in refs:
            self._installed[ref] = number
        step = Step(self, number, title, tuple(refs), camera, bool(picture),
                    len(self.operations) if self.operations else None)
        self.steps.append(step)
        return step

    def _use(self, record) -> None:
        if record not in self.materials:
            self.materials.append(record)

    def equipment(self) -> list[str]:
        """The equipment the steps imply, then the tools the user named, each once."""
        implied = [EQUIPMENT[op.kind] for step in self.steps for op in step.ops if op.kind in EQUIPMENT]
        return list(dict.fromkeys(implied + self.tools))

    def open_items(self) -> list[str]:
        """Everything engineering still owes: each NOT STATED value, and each part no step installs."""
        items = []
        for step in self.steps:
            for op in step.ops:
                items += [f"step {step.number} ({op.kind}): {name} not stated" for name in op.missing]
        for leaf in self.leaves():
            if leaf.ref not in self._installed:
                items.append(f"{leaf.ref} {leaf.label or '(unnamed)'}: no step installs it")
        return items

    def documents(self) -> list[tuple[str, str]]:
        """(document, title) for the drawing and every spec a value cites, in first-cited order."""
        seen: dict[str, str] = {}
        if self.drawing is not None:
            seen[self.drawing.name] = self.drawing.title or "Assembly drawing"
        for step in self.steps:
            for op in step.ops:
                for line in op.lines:
                    source = line.source
                    if source is not None and source.kind in ("spec", "drawing", "datasheet"):
                        seen.setdefault(source.document, source.title)
        return list(seen.items())


# --- the decorator -----------------------------------------------------------


def work_instruction(func: Callable[..., Any] | None = None, *, out: str | Path | None = None):
    """Declare a work instruction. The function returns an :class:`Instruction`;
    calling it (the script's ``__main__`` does) writes one PDF at ``out``, prints
    every open item, and returns the path written.

    ``out`` is required and relative paths resolve against the script.
    """

    def apply(fn: Callable[..., Any]) -> Callable[..., Any]:
        import inspect

        if out is None:
            raise ValueError(
                f"@work_instruction {fn.__name__} needs out=<path>.pdf: the instruction is that PDF, "
                "and cadgen does not choose where it lands."
            )
        target_spec = Path(out)
        if target_spec.suffix.lower() != ".pdf":
            raise ValueError(f"@work_instruction out= must name a .pdf, got {out!r}")
        script = Path(inspect.getsourcefile(fn) or inspect.getfile(fn)).resolve()

        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> list[Path]:
            target = target_spec if target_spec.is_absolute() else (script.parent / target_spec).resolve()
            try:
                return write(target, fn(*args, **kwargs))
            except BaseException as error:
                # A refused or failed run leaves nothing at out=: an older instruction
                # still there would read as this run's.
                target.unlink(missing_ok=True)
                try:
                    from cadgen import analytics

                    if isinstance(error, Exception):  # a mistake in cadgen's own code, never the author's
                        analytics.report(error, "build", bugs_only=True)
                except Exception:  # noqa: BLE001 - a crash report never adds a failure to one
                    pass
                raise

        def write(target: Path, wi: Any) -> list[Path]:
            if not isinstance(wi, Instruction):
                raise TypeError(f"@work_instruction {fn.__name__} must return an Instruction")
            if not wi.steps:
                raise ValueError(f"@work_instruction {fn.__name__} has no steps")
            items = wi.open_items()
            if wi.status == "released" and items:
                raise ValueError(
                    f"@work_instruction {fn.__name__} is released with {len(items)} open item(s); "
                    "state them or keep it a draft:\n  " + "\n  ".join(items)
                )
            from cadgen._internal.work_instruction_pages import write_pdf

            pages = write_pdf(wi, target, open_items=items)
            for item in items:
                print(f"{fn.__name__}: open item: {item}")
            print(f"wrote {target} ({pages} page{'s' if pages != 1 else ''})")
            return [target]

        run.__cadgen_work_instruction__ = True  # type: ignore[attr-defined]
        return run

    return apply(func) if func is not None else apply
