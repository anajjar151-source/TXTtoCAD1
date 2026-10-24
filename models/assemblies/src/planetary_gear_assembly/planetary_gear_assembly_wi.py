"""Work instruction for the planetary gear assembly ($work-instructions sample).

A manual sample, not a test fixture. It cites no process spec, because this
demo assembly has none; every value a spec or drawing would carry is left out,
so the draft shows what engineering still owes as NOT STATED and open items.
Run `python planetary_gear_assembly.py` first to write the STEP.
"""

from pathlib import Path

from cadgen.work_instruction import Instruction, work_instruction


@work_instruction(out="../../PDF/planetary_gear_assembly/planetary_gear_assembly_wi.pdf")
def planetary_gear_assembly_wi():
    wi = Instruction(Path(__file__).parent / "../../STEP/planetary_gear_assembly/planetary_gear_assembly.step",
                     title="PLANETARY GEAR ASSEMBLY", number="WI-DEMO-001", revision="A",
                     scope="Assembly of the demo planetary gear stage from its machined parts.",
                     revisions=[("A", "2026-10-23", "First issue")])

    wi.operation("Prepare the carrier")
    wi.step("Place the carrier plate on the bench, pin bosses up", install=["carrier_plate"])

    wi.operation("Install the planet pins")
    for n in (1, 2, 3):
        wi.step(f"Press planet pin {n} into the carrier", install=[f"planet_pin_{n}"]).caution(
            "Support the carrier under the boss while pressing.")

    wi.operation("Install the gears")
    for n in (1, 2, 3):
        wi.step(f"Slide planet gear {n} onto its pin", install=[f"planet_gear_{n}_18_teeth"])
    wi.step("Insert the sun gear between the planets", install=["sun_gear_24_teeth"]).instruct(
        "Rotate the sun gear until it meshes with all three planets.")
    (wi.step("Fit the ring gear over the planets", install=["ring_gear_60_internal_teeth"])
       .inspect("The stage turns through one full carrier revolution without binding"))
    return wi


if __name__ == "__main__":
    planetary_gear_assembly_wi()
