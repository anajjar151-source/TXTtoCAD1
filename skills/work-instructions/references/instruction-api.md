# `cadgen.work_instruction` reference

```python
from cadgen.work_instruction import (
    work_instruction, Instruction, Spec, Drawing, Datasheet, Stated, Cited,
    Torque, Material, Adhesive, Layup, Cure, Machining,
)
```

## Template

Every document, product and value below is a PLACEHOLDER showing the script's
shape: `PS-XXXX`, `ADHESIVE-X` and the `<...>` values are not real, and none
of them is a default. A real script carries only what the user's documents
state, each value copied from the section it cites. A value they do not state
is left out, and prints NOT STATED.

```python
from pathlib import Path

from cadgen.work_instruction import (
    Adhesive, Cited, Cure, Datasheet, Drawing, Instruction, Material, Spec,
    work_instruction,
)

# The documents, as the user supplied them: number, title, revision.
FASTENING = Spec("PS-XXXX", "<fastening spec title>", revision="<rev>")
BONDING = Spec("PS-YYYY", "<bonding spec title>", revision="<rev>")
TDS = Datasheet("ADHESIVE-X", revision="<rev or date>")
DWG = Drawing("DWG-ZZZZ", revision="<rev>", title="<drawing title>")

# Each process record once. Prep comes from the bonding spec (the record's
# per=); the spec defers mixing to the manufacturer, so mix cites the data
# sheet. Pot life is left out: neither document the user gave states it, so
# it prints NOT STATED.
ADHESIVE = Adhesive(
    "ADHESIVE-X",
    prep="<prep as PS-YYYY section 5.1 states it>",
    mix=Cited("<mix ratio as the data sheet states it>", per=TDS.at("Mixing")),
    cure="<cure as PS-YYYY section 5.1 states it>",
    per=BONDING.at("5.1"),
)
LOCKING = Material("<threadlocker>", per=FASTENING.at("<section>"),
                   note="<how it is applied>")


@work_instruction(out="../PDF/bracket_assembly_wi.pdf")
def bracket_assembly_wi():
    wi = Instruction(
        Path(__file__).parent / "../STEP/bracket_assembly.step",
        title="BRACKET ASSEMBLY", number="WI-0001", revision="A", drawing=DWG,
        scope="<what this builds, as the user puts it>",
        safety=["<PPE and hazards, as the user's documents state them>"],
        tools=["<fixture the user names>"],
    )
    wi.operation("Prepare")
    wi.step("Load the base plate on the fixture", install=["base_plate"])

    wi.operation("Bond the bracket")
    (wi.step("Bond the bracket to the base plate", install=["bracket"],
             camera="bottom")
       .caution("<caution, in the user's words>")
       .bond(ADHESIVE, surfaces=["#o1.2.f5"]))
    wi.step("Cure the bond").cure(
        Cure("<cure name>", cycle="<cycle as stated>", per=BONDING.at("<section>")))

    wi.operation("Install the pin")
    (wi.step("Install the pin", install=["pin"])
       # Once stated: torque=Torque(<low>, <high>, "in-lbf", per=FASTENING.at(...)),
       # or per=DWG.at("<note>") where a drawing callout differs from the table.
       .fasten("<nut part number>", qty=1, torque=None, locking=LOCKING)
       .inspect("<acceptance criterion as stated>", per=DWG.at("<note>"),
                record="<measured value, unit>"))
    return wi


if __name__ == "__main__":
    bracket_assembly_wi()
```

## `@work_instruction(out="<path>.pdf")`

Declares the instruction. The function returns an `Instruction`; calling it
writes one PDF at `out` (relative to the script), prints every open item, and
returns `[path]`. A refused or failed run leaves no file at `out`, not even an
earlier one.

## `Instruction(step_path, *, title, number, revision, ...)`

| Argument | Meaning |
| --- | --- |
| `step_path` | the assembly STEP; a single part is refused |
| `title`, `number`, `revision` | the instruction's own; on every page |
| `part_number`, `author` | optional; the author signs "prepared by" |
| `drawing` | the assembly `Drawing`, first under APPLICABLE DOCUMENTS |
| `status` | `draft` (default, DRAFT on every page) or `released` (refused while anything is open) |
| `size` | `LETTER` (default) or `A4`, portrait |
| `camera` | every figure's camera: `iso` (default), `front`, `back`, `left`, `right`, `top`, `bottom` |
| `pictures` | `False` writes no figures and needs no browser |
| `scope` | one sentence: what this builds and when it applies |
| `safety` | lines of PPE and hazards, as the user's documents state them |
| `tools` | fixtures and tooling the user names, listed under EQUIPMENT |
| `revisions` | `(rev, date, change)` rows |

`wi.operation(title)` starts the next operation: a heading row over the steps
after it and a line in the front pages' overview. Steps keep one sequence
across operations.

`wi.step(title, *, install=(), camera=None, picture=True)` adds the next step
and returns it. One step is one action. `install` names the parts the step
puts in place: a label (every part carrying it, or a subassembly's), or an
occurrence ref (`#o1.2`; a subassembly ref installs everything under it). A
part is installed by one step only. A step that installs nothing (a cure, an
inspection) still has a figure of what is installed so far, and none while
nothing is.

`wi.open_items()` returns what the run prints: each NOT STATED value, each
inspection criterion with no source, and each part no step installs.

## Step operations

Each returns the step, so they chain, and prints in the order called.

| Method | Prints | The floor records |
| --- | --- | --- |
| `instruct(text)` | the user's words | |
| `fasten(hardware, *, qty=None, torque=None, locking=None, sequence=None)` | hardware, torque (NOT STATED when `None`), threadlocker, sequence | actual torque |
| `bond(adhesive, *, surfaces=())` | adhesive, prep, mix, pot life, cure | adhesive lot, expiry, mixed at, mated at |
| `layup(layup)` | material, ply schedule, debulk | material lot, out-time |
| `cure(cure)` | the cycle | oven or autoclave ID, start, end, chart no. |
| `machine(machining, *, surfaces=())` | operation, tool, speed, feed, coolant | machine ID |
| `apply(material, *, surfaces=())` | a sealant, primer or other consumable and how it goes on | |
| `inspect(text, *, per=None, record=None)` | a QA hold point; with no `per` its source prints NOT STATED and is an open item | the measured value `record` names |
| `warning(text)`, `caution(text)`, `note(text)` | a box above the step, in the user's words | |

`bond`, `layup`, `cure` and `machine` take `None` for a record nobody has
stated yet; it prints NOT STATED. `surfaces` are face refs (`#o1.2.f3`, from
`cadgen.read_scene(path).resolve("#o1.2")[0].entities("face")`), each resolved
to exactly one face when the step names it and drawn on the step's figure;
each must be on a part installed by that step or before.

## Sources

Every record and every torque takes `per=`, and nothing else is accepted:

| Source | Prints | For |
| --- | --- | --- |
| `Spec(number, title, revision=).at(section)` | `PS-2001 Rev D §4.2, Table 3` | a rule of the company's process spec |
| `Drawing(number, revision=, title="").at(callout)` | `DWG-1042 Rev B, note 4 (drawing callout)` | a requirement the drawing states, including a deviation from the spec |
| `Datasheet(product, revision=).at(section)` | `EA 9394 datasheet, 2019-05, Mixing` | a manufacturer's data sheet the spec defers to |
| `Stated(by, on=date)` | `stated by A. Zhou, 2026-10-23` | something the user said, and only that |

A record's `per` covers every field. A field from a different document is
`Cited(text, per=...)` in place of the plain text, and prints its own source.

## Records

A field left out prints NOT STATED if it is required, and nothing if optional.

| Record | Required | Optional |
| --- | --- | --- |
| `Torque(low, high=None, unit="", *, per)` | `low` and `unit` (`in-lbf`, `ft-lbf`, `N-m`) | `high` for a range |
| `Adhesive(name, *, prep, mix, pot_life, cure, per)` | `prep`, `mix`, `pot_life`, `cure` | |
| `Layup(name, *, plies, debulk, per)` | `plies` | `debulk` |
| `Cure(name, *, cycle, per)` | `cycle` | |
| `Machining(name, *, tool, speed, feed, coolant, per)` | `tool`, `speed`, `feed` | `coolant` |
| `Material(name, *, per, note)` | | `note` |

Values are text as the document writes them (`"100:17 by weight"`,
`"3000 rpm"`): nothing is parsed, converted or rounded; a torque prints the
numbers given. Adhesives, layup materials and threadlockers are listed under
MATERIALS with lot and expiry blanks; a torque wrench and an oven are listed
under EQUIPMENT with ID and calibration-due blanks.

## The figures

One snapshot packet renders every step's figure in one browser. Each shows the
assembly as it stands after the step, as hidden-line art (black edges,
whatever colours the STEP carries): parts a later step installs are left out,
parts installed earlier are outlines, the step's own parts are filled blue,
and named surfaces are filled purple. Every figure shares one camera fitted to
the whole assembly, so a part sits in the same place in each.

## What the run prints

| Line | Meaning |
| --- | --- |
| `open item: step 2 (bond): pot life not stated` | a value the documents or the user still owe |
| `open item: step 4 (inspect): criterion source not stated` | an inspection with no document behind it |
| `open item: #o1.4 pin: no step installs it` | a part the order leaves out |
| `wrote <path> (N pages)` | the PDF |

A step taller than a page is refused, naming the step: split it into shorter
steps.
