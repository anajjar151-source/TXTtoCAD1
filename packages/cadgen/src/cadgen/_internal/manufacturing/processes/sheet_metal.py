"""Sheet metal bending (estimate): every bend of a bent sheet off the press brake. Tier 2.

The part is read from its STEP as a bent sheet (:mod:`cadgen._internal.manufacturing.processes.bends`): flats joined by bends whose inside
and outside are cylinders of one axis, one thickness apart. A part with no bends, or not of one thickness, is refused
in a sentence. For each bend, by hand formulas (:mod:`cadgen._internal.manufacturing.processes.brake`), each an estimate:

- springback: Gardiner's radius after release and the angle it keeps, the springback and the overbend that brings it
  back to the CAD's angle; beside it Hosford and Caddell's power-law value, which counts work hardening;
- cracking: the outer fibre's strain e = 1 / (2R/t + 1) against the sheet's at its minimum R/t (by temper and
  thickness, and along the grain where the study gives the rolling direction and the sheet a value for it);
- the flat pattern: DIN 6935's K-factor, the bend allowance and the bend deduction.

The study names the ``material`` (:data:`cadgen._internal.manufacturing.processes.brake.SHEETS`, or an object with its own numbers), and may
give ``thickness_mm`` (else measured), ``tolerance_deg`` (the springback a bend may have, 1° by default), ``fixed_face``
(a face of the flat held still, else the largest flat) and ``grain_direction`` (the rolling direction). It writes, on the
mesh only to show it, each bend's springback and its outer strain as a share of its limit, and the displacement off the
brake: each bend opens by its springback and the flats past it turn with it, out from the held flat, so the part is
drawn as it comes off the brake. Its findings are its verdict, one pass or fail per bend and check. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import (
    AnalysisResult, FieldSpec, Inputs, SolveContext, by_severity, xyz,
)
from cadgen._internal.manufacturing.processes.base import Process, finding_of

__all__ = ["DEFAULT_TOLERANCE_DEG", "LIMITS", "SheetMetalInputs", "SheetMetalProcess"]

#: This process's findings, held to its closed set (``base.FINDING_TYPES``).
finding = finding_of("sheet_metal")

DEFAULT_TOLERANCE_DEG = 1.0
#: The study's thickness and the measured one differ by more than this share: a warning.
THICKNESS_DIFFERS = 0.05
#: A bend this close to taking no set (R Y / (E t) of 1/2) is drawn with this share of its angle kept at least.
_KEPT_FLOOR = 0.01
#: A bend whose axis is within this angle of the rolling direction runs along the grain.
_ALONG_GRAIN_DEG = 45.0
NOT_FORMING = "not a forming simulation"
LIMITS = (
    "An estimate per bend by hand formulas, " + NOT_FORMING + ": Gardiner's springback (the sheet elastic-perfectly "
    "plastic at its yield strength), the outer-fibre strain against the sheet's minimum R/t, DIN 6935's K-factor.",
    "The inside radius is the CAD's: an air bend takes a radius the die opening sets, not the punch's, and springs back "
    "more at a larger one; the shop's own bend table and a test bend override these numbers.",
    "Work hardening is not in Gardiner's relation: a sheet that hardens strongly (annealed stainless, n 0.45) springs "
    "back more; Hosford and Caddell's power-law value is given beside it.",
    "The minimum R/t is its source's for either direction unless the sheet has an along-the-grain value; no thinning, "
    "anisotropy or residual stress, and the flats stay flat and turn rigidly.",
)


@dataclass(frozen=True)
class SheetMetalInputs(Inputs):
    sheet: Any = None
    #: The study's thickness, mm; ``None`` to use the measured one.
    thickness_mm: float | None = None
    tolerance_deg: float = DEFAULT_TOLERANCE_DEG
    fixed_face: str | None = None
    #: The rolling direction (unit); ``None`` when the study does not give it.
    grain: tuple[float, float, float] | None = None


def _figure(value: float) -> str:
    """Three significant figures: 1.19, 90, 0.0532."""
    return f"{value:.3g}"


def _degrees(value: float) -> str:
    return f"{value:.3g}°" if abs(value) < 100 else f"{value:.1f}°"


def _parse_grain(raw) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError("grain_direction: the sheet's rolling direction as [x, y, z], like [1, 0, 0]")
    components = [kinds.number(c, where="grain_direction") for c in raw]
    size = math.sqrt(sum(c * c for c in components))
    if not size > 0:
        raise ValueError("grain_direction: the direction is zero")
    return tuple(c / size for c in components)  # type: ignore[return-value]


class SheetMetalProcess(Process):
    name: ClassVar[str] = "sheet_metal"
    tier: ClassVar[int] = 2
    word: ClassVar[str] = "Sheet metal"
    extras_word: ClassVar[str] = "sheet metal (estimate)"
    estimate_only: ClassVar[bool] = True
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"thickness_mm", "tolerance_deg", "fixed_face", "grain_direction"})
    #: The mesh only carries the fields to the viewer: linear tets are enough.
    mesh_orders: ClassVar[tuple[int, ...]] = (1,)
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("springback", "_SPRINGBACK", "springback angle", "°"),
        FieldSpec("strain_ratio", "_STRAIN_RATIO", "outer strain over its limit", ""),
        FieldSpec("displacement", "_DISPLACEMENT", "springback displacement", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = ()
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["springback", "strain_ratio", "displacement"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ()
    noun: ClassVar[str] = "this bend"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> SheetMetalInputs:
        from cadgen._internal.manufacturing.processes.brake import SHEETS, sheet_from_spec

        for key in ("parts", "connections"):
            if key in document:
                raise ValueError(f"study.{key}: a sheet metal study reads one part, the bent sheet; name it with "
                                 "--occurrence")
        if "material" not in document:
            raise ValueError(f"study.material: the sheet, one of {', '.join(SHEETS)}, or an object with its numbers")
        sheet = sheet_from_spec(document["material"])
        thickness = None
        if "thickness_mm" in document:
            thickness = kinds.number(document["thickness_mm"], where="thickness_mm", positive=True)
        tolerance = DEFAULT_TOLERANCE_DEG
        if "tolerance_deg" in document:
            tolerance = kinds.number(document["tolerance_deg"], where="tolerance_deg", positive=True)
        fixed = None
        if "fixed_face" in document:
            fixed = document["fixed_face"]
            if not isinstance(fixed, str) or not fixed.strip():
                raise ValueError(f"fixed_face: a face of the flat to hold still, like \"#o1.f1\"; got "
                                 f"{kinds.json_text(fixed)}")
            fixed = fixed.strip()
        grain = _parse_grain(document["grain_direction"]) if "grain_direction" in document else None
        return SheetMetalInputs((fixed,) if fixed else (), (), False, sheet=sheet, thickness_mm=thickness,
                                tolerance_deg=tolerance, fixed_face=fixed, grain=grain)

    # -- the ladder: nothing to fit (the formulas are per bend; the mesh only carries the fields) -----

    def estimate(self, ctx: SolveContext, inputs: SheetMetalInputs):
        """Nothing to fit. Before the mesh, the part is read as a sheet, so one that is not is refused unmeshed."""
        from cadgen._internal.fea.fit import Estimate

        if ctx.volume is None and ctx.assembly is None and getattr(ctx.geometry, "shape", None) is not None:
            self._read(ctx, inputs)
        return Estimate(dofs=0, memory_bytes=0, seconds=0.0)

    def _read(self, ctx: SolveContext, inputs: SheetMetalInputs):
        from cadgen._internal.manufacturing.processes.bends import read_sheet

        geometry = ctx.geometry
        return read_sheet(geometry.shape, part=geometry.occurrence_ref or ctx.part_name, volume_mm3=geometry.volume_mm3,
                          area_mm2=geometry.area_mm2,
                          fixed_ordinal=ctx.ordinal_of[inputs.fixed_face] if inputs.fixed_face else None,
                          fixed_ref=inputs.fixed_face or "")

    def apply(self, rung, ctx: SolveContext, inputs: SheetMetalInputs):
        return None

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: SheetMetalInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.manufacturing.processes import bends as sheet_bends
        from cadgen._internal.manufacturing.processes import brake
        from cadgen._internal.fea.analyses.thermal import space_result

        if ctx.assembly is not None:
            raise ValueError("sheet_metal: the document holds several parts; a sheet metal study reads one, so name it "
                             "with --occurrence")
        started = time.perf_counter()
        geometry = ctx.geometry
        part = geometry.occurrence_ref or ctx.part_name
        sheet = self._read(ctx, inputs)
        material = inputs.sheet
        t = inputs.thickness_mm if inputs.thickness_mm is not None else sheet.thickness
        records = []
        for b, bend in enumerate(sheet.bends):
            radius, angle = bend.radius, bend.angle_deg
            g = brake.gardiner(radius, t, material)
            hardening_kept = brake.hosford_caddell(radius, t, material)
            along = None
            if inputs.grain is not None:
                along = abs(float(np.dot(bend.inner.axis, inputs.grain))) >= math.cos(math.radians(_ALONG_GRAIN_DEG))
            minimum = material.min_ratio(t, bool(along))
            strain, limit = brake.outer_strain(radius, t), brake.strain_limit(minimum)
            K = brake.k_factor(radius / t)
            records.append({
                "index": b, "bend": bend, "radius": radius, "angle": angle, "r_over_t": radius / t, "gardiner": g,
                "kept": g["kept"], "springback": angle * (1.0 - g["kept"]),
                "final_angle": angle * g["kept"], "overbend": angle / g["kept"] - angle if g["kept"] > 0 else math.inf,
                "hardening": angle * (1.0 - hardening_kept), "along": along, "min_r_t": minimum,
                "along_table": along is True and material.min_r_t_along is not None,
                "strain": strain, "limit": limit, "ratio": strain / limit, "K": K,
                **brake.allowance(radius, t, angle, K),
            })
        nodes = ctx.space.dof_locations
        bend_of, flat_of, _ = sheet_bends.node_regions(sheet, nodes, ctx.volume.tets, ctx.space.boundary_quadratic,
                                                       ctx.volume.boundary_ordinal)
        kept = [max(r["kept"], _KEPT_FLOOR) for r in records]
        displacement, turned = sheet_bends.spring_back(sheet, kept, nodes, bend_of, flat_of)
        inside = bend_of >= 0
        springback = np.zeros(len(nodes))
        springback[inside] = np.array([r["springback"] for r in records])[bend_of[inside]]
        strain_ratio = np.zeros(len(nodes))
        strain_ratio[inside] = np.array([r["ratio"] for r in records])[bend_of[inside]]
        reliefs = sheet_bends.missing_reliefs(geometry.shape, sheet)
        timings = {"estimate_s": time.perf_counter() - started}
        result = space_result(
            ctx.space, {"springback": springback, "strain_ratio": strain_ratio, "displacement": displacement},
            solver="hand formulas (Gardiner, DIN 6935)", timings=timings,
            scalars={"sheet": sheet, "records": records, "thickness": t, "turned": turned, "reliefs": reliefs,
                     "faces": {o: fp.ref for o, fp in ctx.volume.faces.items()}, "part": part},
        )
        result.deformation = displacement
        return result

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        """True scale: the part drawn as it comes off the brake."""
        return requested if requested is not None else 1.0

    # -- findings ------------------------------------------------------------------------------------
    # Every check says pass (an info with what it measured) or fail (with the fix that makes it pass); notes measure
    # nothing.

    def ready_words(self, summary: dict) -> str:
        """The verdict's headline when nothing is to fix: "Ready to bend · 2 bends · overbend up to 1.21°"."""
        count = len(summary["bends"])
        overbends = [b["overbend_deg"] for b in summary["bends"] if b["overbend_deg"] is not None]
        tail = f" · overbend up to {_degrees(max(overbends))}" if overbends else ""
        return f"Ready to bend · {count} bend{'s' if count != 1 else ''}{tail}"

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: SheetMetalInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        s = result.scalars
        sheet, records, t = s["sheet"], s["records"], s["thickness"]
        found = []
        for record in sorted(records, key=lambda r: r["bend"].number):
            found += self._bend_findings(s, record, inputs, t)
        found += self._angle_error(s, inputs)
        found += self._hardening(s, inputs)
        found += self._reliefs(s, t)
        if inputs.thickness_mm is not None:
            found.append(self._thickness(s, t))
        for bend in sheet.bends:
            if bend.parent_side is None:
                found.append(finding(
                    "info", "bend_closes_loop",
                    f"Bend {bend.number} closes a loop of flats: its springback is held by the rest, which this estimate "
                    "does not solve; the flats are turned by the other bends", "a closed box or tube of sheet",
                    [self._item(s, bend)]))
        found.append(finding(
            "info", "sheet_metal_estimate",
            f"This is an estimate of {len(sheet.bends)} bend{'s' if len(sheet.bends) != 1 else ''} by hand formulas, "
            f"{NOT_FORMING}: the shop's bend table and a test bend set the real overbend",
            LIMITS[0]))
        return by_severity(found)

    def _refs(self, s: dict, bend) -> list[str]:
        return [s["faces"][o] for o in bend.ordinals if o in s["faces"]]

    def _item(self, s: dict, bend) -> dict:
        refs = self._refs(s, bend)
        return {"text": f"bend {bend.number}", "ref": refs[0] if refs else None, "at": xyz(bend.middle())}

    def _bend_findings(self, s: dict, record: dict, inputs: SheetMetalInputs, t: float) -> list[dict]:
        bend, sheet = record["bend"], inputs.sheet
        n = bend.number
        refs, item = self._refs(s, bend), [self._item(s, bend)]
        found = []
        grain = ("" if record["along"] is None else " along the grain (the hard way)" if record["along"]
                 else " across the grain")
        grain_note = ""
        if record["along"] and not record["along_table"]:
            grain_note = ("; its source gives one minimum for either direction, so along the grain keep a margin, or "
                          "give the sheet's min_r_t_along_grain from its mill certificate")
        where = (f"at R {_figure(record['radius'])} mm, R/t {_figure(record['r_over_t'])}, in "
                 f"{_figure(t)} mm {sheet.name}{grain}")
        strain = {"quantity": f"bend {n} outer strain", "value": round(100.0 * record["strain"], 4),
                  "limit": round(100.0 * record["limit"], 4), "units": "%", "pass_when": "below"}
        how = "the outer fibre's strain e = 1 / (2R/t + 1) against the strain at the sheet's minimum R/t" + grain_note
        if record["ratio"] > 1.0 + 1e-9:
            needed = math.ceil(record["min_r_t"] * t * 10.0 - 1e-9) / 10.0
            alternatives = [{"action": "softer_temper", "summary": f"Use a softer temper or alloy whose minimum R/t is "
                             f"{_figure(record['r_over_t'])} or less at {_figure(t)} mm", "where": refs,
                             "params": {"min_r_t": round(record["r_over_t"], 4)}}]
            if record["along"]:
                alternatives.insert(0, {"action": "turn_blank", "summary": f"Turn the blank so bend {n} runs across the "
                                        "grain", "where": refs, "params": {"grain": "across"}})
            found.append(finding(
                "error", "bend_may_crack",
                f"Bend {n} may crack on its outside: {where}, it stretches its outer fibre {record['strain']:.0%}, past the "
                f"{record['limit']:.0%} its minimum R/t of {_figure(record['min_r_t'])} allows",
                how, item, measured=strain,
                fix={"action": "increase_radius",
                     "summary": f"Open bend {n} to an inside radius of at least {needed:g} mm ({_figure(record['min_r_t'])}t).",
                     "where": refs, "params": {"inner_radius_mm": needed}, "alternatives": alternatives}))
        else:
            found.append(finding(
                "info", "bend_formable",
                f"Bend {n} bends without cracking: {where}, it stretches its outer fibre {record['strain']:.0%}, within the "
                f"{record['limit']:.0%} its minimum R/t of {_figure(record['min_r_t'])} allows",
                how, item, measured=strain))
        tolerance = inputs.tolerance_deg
        measured = {"quantity": f"bend {n} springback", "value": round(record["springback"], 6), "limit": tolerance,
                    "units": "°", "pass_when": "below"}
        hardening = f" ({_degrees(record['hardening'])} with work hardening)"
        if record["gardiner"]["elastic"]:
            gentlest = round(0.4 * sheet.E * t / sheet.yield_strength, 1)
            found.append(finding(
                "error", "bend_takes_no_set",
                f"Bend {n} takes no set: at R {_figure(record['radius'])} mm the {_figure(t)} mm {sheet.name} never yields "
                "through its thickness, so it springs back flat",
                "Gardiner's relation: R Y / (E t) at or past 1/2 is an elastic bend", item, measured=measured,
                fix={"action": "reduce_radius", "summary": f"Bend {n} to an inside radius under {gentlest:g} mm.",
                     "where": refs, "params": {"inner_radius_mm": gentlest},
                     "alternatives": [{"action": "form_in_die", "summary": f"Form bend {n} in a die rather than a press "
                                       "brake", "where": refs, "params": {}}]}))
        elif record["springback"] > tolerance:
            found.append(finding(
                "warning", "springback_over_tolerance",
                f"Bend {n} springs back {_degrees(record['springback'])}{hardening}, to {_degrees(record['final_angle'])} "
                f"at R {_figure(record['gardiner']['final_radius_mm'])} mm, past the ±{_degrees(tolerance)} tolerance: "
                f"overbend it {_degrees(record['overbend'])} on the press brake",
                "Gardiner's springback for the CAD's radius and angle; the overbend is the angle it springs back from to "
                "land on the CAD's", item, measured=measured,
                fix={"action": "overbend",
                     "summary": f"Overbend bend {n} by {_degrees(record['overbend'])} on the press brake, to "
                                f"{_degrees(record['angle'] + record['overbend'])}, so it springs back to "
                                f"{_degrees(record['angle'])}.",
                     "where": refs, "params": {"overbend_deg": round(record["overbend"], 4),
                                               "bend_to_deg": round(record["angle"] + record["overbend"], 4)}}))
        else:
            found.append(finding(
                "info", "springback_within_tolerance",
                f"Bend {n} springs back {_degrees(record['springback'])}{hardening}, within the ±{_degrees(tolerance)} "
                f"tolerance (overbend {_degrees(record['overbend'])} to land on {_degrees(record['angle'])})",
                "Gardiner's springback for the CAD's radius and angle", item, measured=measured))
        return found

    def _angle_error(self, s: dict, inputs: SheetMetalInputs) -> list[dict]:
        sheet, turned, records = s["sheet"], s["turned"], s["records"]
        if not sheet.tree:
            return []
        far = max(range(len(sheet.flats)), key=lambda i: (turned[i], -sheet.flats[i].number))
        flat, error = sheet.flats[far], turned[far]
        path = self._path(sheet, far)
        between = ", ".join(f"bend {sheet.bends[b].number} by {_degrees(records[b]['overbend'])}" for b in path)
        held = sheet.flats[sheet.fixed].number
        measured = {"quantity": f"flat {flat.number} off its angle", "value": round(error, 6),
                    "limit": inputs.tolerance_deg, "units": "°", "pass_when": "below"}
        item = [{"text": f"flat {flat.number}", "ref": s["faces"].get(flat.ordinals[0]) if flat.ordinals else None,
                 "at": xyz(flat.centre) if flat.centre is not None else None}]
        words = (f"flat {flat.number}, {len(path)} bend{'s' if len(path) != 1 else ''} from the held flat {held}, ends "
                 f"{_degrees(error)} off its CAD angle")
        if error > inputs.tolerance_deg:
            return [finding(
                "warning", "angle_error_over_tolerance",
                f"The far flat is off: {words}, past the ±{_degrees(inputs.tolerance_deg)} tolerance"
                + ("; it carries the springback of every bend between" if len(path) > 1 else ""),
                "each flat turned by the springback of every bend between it and the held flat", item, measured=measured,
                fix={"action": "overbend", "summary": f"Overbend each bend between flat {held} and flat {flat.number}: "
                     f"{between}.",
                     "where": [ref for b in path for ref in self._refs(s, sheet.bends[b])],
                     "params": {"bends": [{"bend": sheet.bends[b].number,
                                           "overbend_deg": round(records[b]["overbend"], 4)} for b in path]}})]
        return [finding("info", "angle_error_within_tolerance",
                        f"The far flat is within tolerance: {words}, within ±{_degrees(inputs.tolerance_deg)}",
                        "each flat turned by the springback of every bend between it and the held flat", item,
                        measured=measured)]

    def _path(self, sheet, flat: int) -> list[int]:
        """The bends from the held flat out to ``flat``, nearest first."""
        parent = {child: (b, up) for b, up, child in sheet.tree}
        path = []
        while flat in parent:
            b, flat = parent[flat]
            path.append(b)
        return path[::-1]

    def _hardening(self, s: dict, inputs: SheetMetalInputs) -> list[dict]:
        """With work hardening, the bends Gardiner passes: past the tolerance, a warning to confirm by a test bend. A
        bend Gardiner already fails is that check's, and with none passing there is nothing to judge here."""
        records, sheet = s["records"], inputs.sheet
        tolerance = inputs.tolerance_deg
        passing = [r for r in records if not r["gardiner"]["elastic"] and r["springback"] <= tolerance]
        if not passing:
            return []
        worst = max(passing, key=lambda r: r["hardening"])
        bend = worst["bend"]
        measured = {"quantity": f"bend {bend.number} springback with work hardening",
                    "value": round(worst["hardening"], 6), "limit": tolerance, "units": "°", "pass_when": "below"}
        how = ("Hosford and Caddell's power-law moment, the sheet hardening as σ = K ε^n; Gardiner's relation takes it "
               "perfectly plastic at its yield")
        if worst["hardening"] > tolerance:
            overbend = worst["angle"] * worst["hardening"] / max(worst["angle"] - worst["hardening"], 1e-9)
            return [finding(
                "warning", "springback_work_hardening",
                f"With {sheet.name}'s work hardening (n {_figure(sheet.n)}), bend {bend.number} may spring back "
                f"{_degrees(worst['hardening'])}, past the ±{_degrees(tolerance)} tolerance Gardiner's "
                f"{_degrees(worst['springback'])} passes: confirm with a test bend",
                how, [self._item(s, bend)], measured=measured,
                fix={"action": "test_bend", "summary": f"Bend a test piece of this sheet to bend {bend.number}'s radius and "
                     f"measure its springback before setting the overbend (about {_degrees(overbend)} by this estimate).",
                     "where": self._refs(s, bend), "params": {"overbend_deg": round(overbend, 4)}})]
        return [finding(
            "info", "springback_work_hardening_within_tolerance",
            f"With {sheet.name}'s work hardening (n {_figure(sheet.n)}) too, every bend springs back within "
            f"±{_degrees(tolerance)}: the most, bend {bend.number}, {_degrees(worst['hardening'])}",
            how, [self._item(s, bend)], measured=measured)]

    def _reliefs(self, s: dict, t: float) -> list[dict]:
        sheet, missing = s["sheet"], s["reliefs"]
        how = "probed just past each end of every bend, a quarter thickness into each flat it joins"
        if not missing:
            return [finding("info", "reliefs", "Every bend ends at an edge or a relief cut: nothing tears at a bend's end",
                            how, measured={"quantity": "bend ends with no relief", "value": 0, "limit": 1, "units": "",
                                           "pass_when": "below"})]
        found = []
        for b in sorted({m[0] for m in missing}, key=lambda b: sheet.bends[b].number):
            bend = sheet.bends[b]
            ends = [m for m in missing if m[0] == b]
            width = round(t / 2.0, 3)
            depth = round(bend.radius + t + 0.5, 3)
            found.append(finding(
                "warning", "relief_missing",
                f"Bend {bend.number} ends inside flat {sheet.flats[ends[0][2]].number} at {len(ends)} "
                f"end{'s' if len(ends) != 1 else ''} with no relief cut: the sheet beside it tears or bulges there",
                how, [{"text": f"bend {bend.number}'s end", "ref": None, "at": point} for _, point, _ in ends],
                measured={"quantity": f"bend {bend.number} ends with no relief", "value": len(ends), "limit": 1,
                          "units": "", "pass_when": "below"},
                fix={"action": "add_relief",
                     "summary": f"Cut a relief at each end of bend {bend.number}, at least {width:g} mm wide (t/2) and "
                                f"{depth:g} mm deep (R + t + 0.5 mm).",
                     "where": [point for _, point, _ in ends], "params": {"width_mm": width, "depth_mm": depth},
                     "alternatives": [{"action": "extend_bend", "summary": f"Run bend {bend.number} out to the edge of "
                                       "the flat", "where": self._refs(s, bend), "params": {}}]}))
        return found

    def _thickness(self, s: dict, t: float) -> dict:
        """The study's thickness against the measured one, when the study gives one."""
        sheet = s["sheet"]
        off = abs(t - sheet.thickness) / sheet.thickness
        measured = {"quantity": "thickness_mm off the measured", "value": round(100.0 * off, 4),
                    "limit": 100.0 * THICKNESS_DIFFERS, "units": "%", "pass_when": "below"}
        how = "the bends' inside and outside cylinders are the measured thickness apart"
        if off > THICKNESS_DIFFERS:
            return finding(
                "warning", "thickness_differs",
                f"The study's thickness_mm, {_figure(t)} mm, is not the {_figure(sheet.thickness)} mm the part measures: "
                f"the numbers here use {_figure(t)} mm", how, measured=measured,
                fix={"action": "set_thickness", "summary": f"Model the sheet {_figure(t)} mm thick, as the study says.",
                     "where": [ref for bend in sheet.bends for ref in self._refs(s, bend)],
                     "params": {"thickness_mm": t},
                     "alternatives": [{"action": "set_study_thickness", "summary": f"Give the measured "
                                       f"{_figure(sheet.thickness)} mm as thickness_mm", "where": [],
                                       "params": {"thickness_mm": round(sheet.thickness, 4)}}]})
        return finding("info", "thickness_matches", f"The study's thickness_mm, {_figure(t)} mm, is the part's", how,
                       measured=measured)

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: SheetMetalInputs, check_results: list[dict]) -> dict:
        import numpy as np

        s = result.scalars
        sheet, records, t, turned = s["sheet"], s["records"], s["thickness"], s["turned"]

        def finite(value, digits=4):
            return None if value is None or not math.isfinite(value) else round(value, digits)

        bends = []
        for r in sorted(records, key=lambda r: r["bend"].number):
            bend = r["bend"]
            bends.append({
                "bend": bend.number, "faces": self._refs(s, bend), "at_mm": xyz(bend.middle()),
                "joins": sorted(sheet.flats[i].number for i in bend.sides),
                "inner_radius_mm": round(r["radius"], 4), "r_over_t": round(r["r_over_t"], 4),
                "angle_deg": round(r["angle"], 4), "length_mm": round(bend.length, 4),
                "final_radius_mm": finite(r["gardiner"]["final_radius_mm"]), "final_angle_deg": round(r["final_angle"], 4),
                "springback_deg": round(r["springback"], 6), "overbend_deg": finite(r["overbend"], 6),
                "springback_hardening_deg": round(r["hardening"], 4),
                "gardiner_x": round(r["gardiner"]["x"], 8), "kept": round(r["kept"], 8),
                "grain": None if r["along"] is None else ("along" if r["along"] else "across"),
                "min_r_over_t": round(r["min_r_t"], 4), "outer_strain": round(r["strain"], 6),
                "strain_limit": round(r["limit"], 6), "strain_ratio": round(r["ratio"], 6), "may_crack": r["ratio"] > 1 + 1e-9,
                "k_factor": round(r["K"], 4), "bend_allowance_mm": round(r["bend_allowance_mm"], 4),
                "bend_deduction_mm": finite(r["bend_deduction_mm"]),
            })
        flats = [{"flat": flat.number, "faces": [s["faces"][o] for o in flat.ordinals if o in s["faces"]],
                  "area_mm2": round(flat.area, 4), "angle_error_deg": round(turned[i], 6)}
                 for i, flat in sorted(enumerate(sheet.flats), key=lambda pair: pair[1].number)]
        far = max(flats, key=lambda f: f["angle_error_deg"]) if flats else None
        magnitude = np.linalg.norm(result.fields["displacement"], axis=1)
        summary = {
            "estimate": True,
            "estimate_line": self.estimate_line(len(sheet.bends), t, inputs.sheet.name),
            "material": inputs.sheet.name,
            "thickness_mm": round(t, 4),
            "thickness_measured_mm": round(sheet.thickness, 4),
            "tolerance_deg": inputs.tolerance_deg,
            "held_flat": sheet.flats[sheet.fixed].number,
            "grain_direction": None if inputs.grain is None else [round(c, 6) for c in inputs.grain],
            "bends": bends,
            "flats": flats,
            "max_springback_deg": max(b["springback_deg"] for b in bends),
            "max_strain_ratio": max(b["strain_ratio"] for b in bends),
            "cracking_bends": [b["bend"] for b in bends if b["may_crack"]],
            "far_flat": None if far is None else far["flat"],
            "max_angle_error_deg": None if far is None else far["angle_error_deg"],
            "max_displacement_mm": round(float(magnitude.max()), 6),
            "missing_reliefs": [{"bend": sheet.bends[b].number, "at_mm": point} for b, point, _ in s["reliefs"]],
            "checks": check_results,
        }
        return summary

    @staticmethod
    def estimate_line(count: int, t: float, name: str) -> str:
        return (f"Estimate: {count} bend{'s' if count != 1 else ''} in {_figure(t)} mm {name} by hand formulas "
                f"(Gardiner's springback, the outer strain against the minimum R/t, DIN 6935's K-factor); {NOT_FORMING}")

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {
            "springback": (0.0, max(summary["max_springback_deg"], 1e-9)),
            # The limit is 1: a bend at or past it reads red whatever the rest.
            "strain_ratio": (0.0, max(summary["max_strain_ratio"], 1.0)),
            "displacement": (0.0, max(summary["max_displacement_mm"], 1e-9)),
        }

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: SheetMetalInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = {
            # The viewer's "Made of" reads the material's name.
            "material": {"name": inputs.sheet.name},
            "sheet": inputs.sheet.as_dict(),
            "tolerance_deg": inputs.tolerance_deg,
        }
        if inputs.thickness_mm is not None:
            echo["thickness_mm"] = inputs.thickness_mm
        if inputs.fixed_face is not None:
            echo["fixed_face"] = bare((inputs.fixed_face,))[0]
        if inputs.grain is not None:
            echo["grain_direction"] = list(inputs.grain)
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        lines = [summary["estimate_line"]]
        for bend in summary["bends"]:
            grain = f", {bend['grain']} the grain" if bend["grain"] else ""
            deduction = ("" if bend["bend_deduction_mm"] is None else f", BD {_figure(bend['bend_deduction_mm'])} mm")
            lines.append(
                f"bend {bend['bend']}: {_degrees(bend['angle_deg'])} at R {_figure(bend['inner_radius_mm'])} mm "
                f"(R/t {_figure(bend['r_over_t'])}{grain}), {_figure(bend['length_mm'])} mm long, joins flats "
                f"{' and '.join(map(str, bend['joins']))}; springs back {_degrees(bend['springback_deg'])} "
                f"({_degrees(bend['springback_hardening_deg'])} with work hardening), overbend "
                f"{'n/a' if bend['overbend_deg'] is None else _degrees(bend['overbend_deg'])}; outer strain "
                f"{bend['outer_strain']:.0%} of {bend['strain_limit']:.0%} allowed; K {bend['k_factor']:.2f}, "
                f"BA {_figure(bend['bend_allowance_mm'])} mm{deduction}")
        if summary["far_flat"] is not None:
            lines.append(f"held flat {summary['held_flat']}; the farthest off is flat {summary['far_flat']}, "
                         f"{_degrees(summary['max_angle_error_deg'])} off its CAD angle")
        return lines
