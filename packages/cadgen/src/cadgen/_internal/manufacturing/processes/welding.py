"""Welding (lite): the distortion and residual stress welds leave in the part they join, by inherent strain.

The study names the base metal (``alloy``: :data:`cadgen._internal.manufacturing.processes.weldments.METALS`) and its ``welds``. A weld
runs along the edge two faces share (``faces``: the plate it lies on, then the plate that meets it, as a fillet on a
T joint) or along a line between two points on a face (``line_mm`` and the face, as a butt weld across a plate); it
has its ``process`` (``gmaw``/``mig``, ``gtaw``/``tig``, ``smaw``, ``laser``), its net heat input per pass
(``heat_input_kJ_mm``, or volts, amps and travel speed, or a laser's power and speed, with the process's thermal
efficiency) and its ``passes``.

Each weld gets the inherent strain of its zone (:mod:`cadgen._internal.manufacturing.processes.weldments`): along the weld, -σ_y / E over
the material nearest it whose area matches the tendon force (F_T / σ_y); across it, in a strip of each plate a plate
thickness wide, a strain varying through the plate's thickness whose integrals are the classical transverse shrinkage
and angular distortion for the plate's Q / h². Every weld is applied at once and the part, free, held only against
rigid motion, is solved once (:func:`cadgen._internal.manufacturing.processes.inherent_strain.solve_once`).

It writes the distortion (its rigid motion taken out), the residual stress (von Mises, and the longitudinal stress near
the welds), and the weld zone. Its findings are a checklist: the distortion against ``tolerance_mm``, each weld's
angular distortion beside the empirical estimate (the hand check), the bowing of a long weld beside beam theory, and
the residual stress near yield, flagged for a fatigue-critical part. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import (
    AnalysisResult, FieldSpec, Inputs, SolveContext, plan_value, xyz,
)
from cadgen._internal.manufacturing.processes.base import Process, finding_of

__all__ = ["LIMITS", "Weld", "WeldingInputs", "WeldingProcess"]

#: This process's findings, held to its closed set (``base.FINDING_TYPES``).
finding = finding_of("welding")

LIMITS = (
    "Every weld is applied at once, not in sequence, and the part is free: in this linear model neither the order of "
    "the welds nor clamping while they cool changes the result (real clamps hold some distortion back).",
    "Each weld is the classical relations' inherent strain, sized by its heat input and the plates' thickness from "
    "measurements on steel and scaled to the metal by α / (c ρ): an estimate of the zone, not a thermal history.",
    "Linear elastic, the base metal's yield throughout: near a weld the stress is about yield, as it is in a weld; an "
    "aluminium's softened heat-affected zone is not modelled.",
    "Straight welds; a multi-pass weld's angular distortion and transverse shrinkage add pass by pass, its tendon force "
    "is one pass's.",
)
#: A weld's simulated angular distortion within this factor of Satoh and Terasaki's passes the hand check.
HAND_FACTOR = 2.0
#: A residual stress at this share of yield or more is "near yield".
NEAR_YIELD = 0.8
WELD_KEYS = {"faces", "line_mm", "process", "heat_input_kJ_mm", "volts", "amps", "travel_speed_mm_s", "power_W",
             "efficiency", "passes", "thickness_mm", "label"}
MOST_PASSES = 50


@dataclass(frozen=True)
class Weld:
    label: str
    faces: tuple[str, ...]
    #: Two points (mm) the weld runs between, or ``None`` for the edge its two faces share.
    line: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    process: Any
    #: The net heat input of one pass, J/mm.
    heat_J_mm: float
    passes: int = 1
    #: The plates' thicknesses (one per face, mm), or ``None`` to measure them.
    thickness: tuple[float, ...] | None = None
    #: How the heat input was found, in words.
    heat_words: str = ""


@dataclass(frozen=True)
class WeldingInputs(Inputs):
    metal: Any = None
    welds: tuple[Weld, ...] = ()
    tolerance_mm: float | None = None
    fatigue_critical: bool = False


def _point(raw, where: str) -> tuple[float, float, float]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError(f"{where}: a point as [x, y, z] in mm")
    return tuple(kinds.number(value, where=where) for value in raw)


def _heat(entry: dict, process, where: str) -> tuple[float, str]:
    """The net heat input of a pass, J/mm, and how it was found: given, or k U I / v, or k P / v."""
    arc = [key for key in ("volts", "amps") if key in entry]
    beam = "power_W" in entry
    given = "heat_input_kJ_mm" in entry
    ways = sum([given, bool(arc), beam])
    example = ("heat_input_kJ_mm (the net heat input per pass, efficiency included), or volts, amps and "
               "travel_speed_mm_s" if process.source == "arc" else "heat_input_kJ_mm, or power_W and travel_speed_mm_s")
    if ways != 1:
        raise ValueError(f"{where}: give the heat one way: {example}")
    if given:
        for key in ("travel_speed_mm_s", "efficiency"):
            if key in entry:
                raise ValueError(f"{where}.{key}: heat_input_kJ_mm is already the net heat input; give one or the other")
        kj = kinds.number(entry["heat_input_kJ_mm"], where=f"{where}.heat_input_kJ_mm", positive=True)
        if not 0.01 <= kj <= 20.0:
            raise ValueError(f"{where}.heat_input_kJ_mm: {kj:g} kJ/mm is not a weld's; arc welds put in about 0.2 to 4")
        return kj * 1000.0, "the study's net heat input"
    if arc and process.source != "arc":
        raise ValueError(f"{where}: a {process.key} weld takes power_W and travel_speed_mm_s, not volts and amps")
    if beam and process.source != "beam":
        raise ValueError(f"{where}: a {process.key} weld takes volts, amps and travel_speed_mm_s, not power_W")
    if "travel_speed_mm_s" not in entry or (arc and len(arc) != 2):
        raise ValueError(f"{where}: {example}")
    speed = kinds.number(entry["travel_speed_mm_s"], where=f"{where}.travel_speed_mm_s", positive=True)
    efficiency = process.efficiency
    if "efficiency" in entry:
        efficiency = kinds.number(entry["efficiency"], where=f"{where}.efficiency", positive=True)
        if efficiency > 1.0:
            raise ValueError(f"{where}.efficiency: the share of the energy that heats the work, at most 1, got {efficiency:g}")
    if beam:
        power = kinds.number(entry["power_W"], where=f"{where}.power_W", positive=True)
        return efficiency * power / speed, f"{efficiency:g} × {power:g} W / {speed:g} mm/s"
    volts = kinds.number(entry["volts"], where=f"{where}.volts", positive=True)
    amps = kinds.number(entry["amps"], where=f"{where}.amps", positive=True)
    return efficiency * volts * amps / speed, f"{efficiency:g} × {volts:g} V × {amps:g} A / {speed:g} mm/s"


def _parse_weld(entry: dict, index: int) -> Weld:
    from cadgen._internal.manufacturing.processes.weldments import PROCESSES, lookup_process

    where = f"welds[{index}]"
    kinds.known(entry, WELD_KEYS, where, "a weld takes faces (and line_mm), process, its heat (heat_input_kJ_mm, or "
                "volts, amps and travel_speed_mm_s, or power_W and travel_speed_mm_s; efficiency), passes, thickness_mm "
                "and label")
    if "faces" not in entry:
        raise ValueError(f"{where}.faces: the plate the weld lies on, then the plate that meets it (their shared edge is "
                         "the weld), or one face with line_mm")
    faces = kinds.faces(entry, where=where)
    if len(faces) > 2:
        raise ValueError(f"{where}.faces: at most two faces: the plate the weld lies on, then the one that meets it")
    line = None
    if "line_mm" in entry:
        raw = entry["line_mm"]
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError(f"{where}.line_mm: the weld's two ends, like [[0, 0, 10], [100, 0, 10]] mm")
        line = (_point(raw[0], f"{where}.line_mm[0]"), _point(raw[1], f"{where}.line_mm[1]"))
        if math.dist(*line) <= 0:
            raise ValueError(f"{where}.line_mm: its two ends are the same point")
    elif len(faces) != 2:
        raise ValueError(f"{where}: one face makes no edge; give the face that meets it too, or the weld's line_mm")
    if "process" not in entry:
        raise ValueError(f"{where}.process: how it is welded, one of {', '.join(PROCESSES)}")
    process = lookup_process(entry["process"], f"{where}.process")
    heat, words = _heat(entry, process, where)
    passes = kinds.whole(entry.get("passes", 1), where=f"{where}.passes", words=f"how many passes, 1 to {MOST_PASSES}",
                         high=MOST_PASSES)
    thickness = None
    if "thickness_mm" in entry:
        raw = entry["thickness_mm"]
        values = raw if isinstance(raw, list) else [raw]
        if len(values) not in (1, len(faces)):
            raise ValueError(f"{where}.thickness_mm: one thickness, or one per face ({len(faces)})")
        values = [kinds.number(value, where=f"{where}.thickness_mm", positive=True) for value in values]
        thickness = tuple(values * len(faces)) if len(values) == 1 else tuple(values)
    label = kinds.text(entry, "label", where=where).get("label", f"weld {index + 1}")
    return Weld(label, faces, line, process, heat, passes, thickness, words)


class WeldingProcess(Process):
    name: ClassVar[str] = "welding"
    word: ClassVar[str] = "Welding"
    extras_word: ClassVar[str] = "welding"
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"alloy", "welds", "tolerance_mm", "fatigue_critical"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2, 1)
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "residual stress (von Mises)", "MPa"),
        FieldSpec("displacement", "_DISPLACEMENT", "distortion", "mm", 3, 1000.0),
        FieldSpec("longitudinal_stress", "_LONGITUDINAL_STRESS", "stress along the weld", "MPa", signed=True),
        FieldSpec("weld_zone", "_WELD_ZONE", "weld zone", ""),
    )
    checks: ClassVar[tuple] = ()
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum",
                  "options": ["von_mises", "displacement", "longitudinal_stress", "weld_zone"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "defeature", "linear_elements")
    noun: ClassVar[str] = "these welds"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> WeldingInputs:
        from cadgen._internal.manufacturing.processes.weldments import METALS, lookup_metal

        if "material" in document:
            raise ValueError(f"study.material: a welding study names its base metal with 'alloy', one of {', '.join(METALS)}")
        for key in ("parts", "connections"):
            if key in document:
                raise ValueError(f"study.{key}: a welding study solves the weldment as one part; model the welded "
                                 "plates as one solid, or name one occurrence with --occurrence")
        if "alloy" not in document:
            raise ValueError(f"study.alloy: the base metal, one of {', '.join(METALS)}")
        metal = lookup_metal(document["alloy"])
        entries = kinds.entries(document, "welds", '{"faces": ["#o1.f3", "#o1.f7"], "process": "gmaw", '
                                                   '"heat_input_kJ_mm": 0.8}')
        if not entries:
            raise ValueError('study.welds: the welds, like [{"faces": ["#o1.f3", "#o1.f7"], "process": "gmaw", '
                             '"heat_input_kJ_mm": 0.8}]')
        welds = tuple(_parse_weld(entry, index) for index, entry in enumerate(entries))
        tolerance = None
        if "tolerance_mm" in document:
            tolerance = kinds.number(document["tolerance_mm"], where="tolerance_mm", positive=True)
        critical = document.get("fatigue_critical", False)
        if not isinstance(critical, bool):
            raise ValueError(f"fatigue_critical: true or false, got {kinds.json_text(critical)}")
        refs = tuple(dict.fromkeys(ref for weld in welds for ref in weld.faces))
        return WeldingInputs(refs, (), False, metal=metal, welds=welds, tolerance_mm=tolerance,
                             fatigue_critical=critical)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: WeldingInputs):
        from cadgen._internal.fea import fit

        return fit.solid_estimate(ctx)

    def apply(self, rung, ctx: SolveContext, inputs: WeldingInputs):
        from cadgen._internal.fea import fit

        return fit.apply_generic(rung, self, ctx, inputs)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: WeldingInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.manufacturing.processes import inherent_strain as IS
        from cadgen._internal.fea.analyses.thermal import space_result
        from cadgen._internal.fea.materials import Material

        if ctx.assembly is not None:
            raise ValueError("welding: the document holds several parts; model the welded plates as one solid (the "
                             "weldment), or name one occurrence with --occurrence")
        started = time.perf_counter()
        space, volume = ctx.space, ctx.volume
        metal = inputs.metal
        material = Material(metal.name, metal.E, metal.nu, metal.yield_strength, metal.density * 1e-12)
        points = space.dof_locations
        centroids = IS.element_centroids(space)
        volumes = IS.element_volumes(space)
        X = IS.quadrature_points(space)                      # (3, E, Q)
        dx = space.basis.dx                                  # (E, Q)
        E_count, Q_count = dx.shape
        strain = np.zeros((3, 3, E_count, Q_count))
        in_zone = np.zeros(E_count, dtype=bool)
        nearest = np.full(E_count, np.inf)
        tangent_of = np.zeros((E_count, 3))
        ordinals = np.asarray(volume.boundary_ordinal)
        triangles = np.asarray(space.boundary_quadratic)
        plans = []
        for index, weld in enumerate(inputs.welds):
            plan = _weld_plan(space, weld, ctx, ordinals, triangles, metal)
            p0, t, length = plan["p0"], plan["t"], plan["length_mm"]
            along = (centroids - p0) @ t
            inside = (along >= -0.5 * volume.max_h) & (along <= length + 0.5 * volume.max_h)
            radial = np.linalg.norm((centroids - p0) - np.outer(along, t), axis=1)
            closer = inside & (radial < nearest)
            nearest[closer], tangent_of[closer] = radial[closer], t
            # Along the weld: the material nearest it whose area carries the tendon force at yield.
            force = plan["tendon_N"]
            candidates = np.flatnonzero(inside)
            order = candidates[np.argsort(radial[candidates])]
            needed = force / metal.yield_strength * length
            count = int(np.searchsorted(np.cumsum(volumes[order]), needed)) + 1
            zone = order[:min(count, len(order))]
            longitudinal = -force * length / (metal.E * float(volumes[zone].sum()))
            strain[:, :, zone, :] += longitudinal * np.outer(t, t)[:, :, None, None]
            in_zone[zone] = True
            plan.update({"zone": zone, "zone_area_mm2": float(volumes[zone].sum()) / length,
                         "longitudinal_strain": longitudinal})
            # Across it: in each plate a strip whose strain through the thickness gives S and θ.
            for plate in plan["plates"]:
                h, n, w = plate["thickness_mm"], plate["normal"], plate["lateral"]
                depth = (centroids - plate["origin"]) @ n
                side = (centroids - p0) @ w
                lateral_ok = (side >= -h) & (side <= h) if plate["two_sided"] else (side >= 0.0) & (side <= h)
                rows = np.flatnonzero(inside & (depth >= -h) & (depth <= 0.25 * volume.max_h) & lateral_ok)
                if len(rows) == 0:
                    raise ValueError(f"welding: {weld.label}: no material found under {plate['face']} within its "
                                     f"{h:.3g} mm thickness of the weld; check the faces and thickness_mm")
                zeta = np.einsum("i,ieq->eq", n, X[:, rows, :] - plate["origin"][:, None, None]) + 0.5 * h
                weights = dx[rows]
                m0, m1, m2 = weights.sum(), (weights * zeta).sum(), (weights * zeta * zeta).sum()
                target = np.array([-plate["shrinkage_mm"] * h * length, -plate["angle_rad"] * h ** 3 * length / 12.0])
                a, b = np.linalg.solve(np.array([[m0, m1], [m1, m2]]), target)
                strain[:, :, rows, :] += (a + b * zeta)[None, None] * np.outer(w, w)[:, :, None, None]
                in_zone[rows] = True
                plate["strip"] = rows
            plans.append(plan)
        held = IS.hold_free(space)
        method = {"iterative": "iterative", "matrix_free": "iterative"}.get(plan_value(ctx, "solver", "direct"))
        timings = {"assemble_s": time.perf_counter() - started}
        started = time.perf_counter()
        once = IS.solve_once(space, material, strain, held, method=method)
        timings["solve_s"] = time.perf_counter() - started
        started = time.perf_counter()
        u = space.nodal(once.u)
        shape = u - IS.rigid_part(points, u)
        moved = np.linalg.norm(shape, axis=1)
        von_mises = IS.nodal_von_mises(space, once.stress)
        along_stress = np.einsum("ei,ijeq,ej->eq", tangent_of, once.stress, tangent_of)
        longitudinal_field = space.scalar.project(along_stress)
        element_long = (along_stress * dx).sum(axis=1) / np.maximum(volumes, 1e-300)
        zone_nodes = np.zeros(space.scalar_count)
        zone_nodes[np.unique(space.scalar.element_dofs[:, in_zone])] = 1.0
        for plan in plans:
            _measure(space, plan, shape, centroids, volumes, metal, volume.max_h, element_long)
        for plan in plans:
            _beam_bow(plan, plans, centroids, volumes, metal, volume.max_h)
        size = float(max(np.ptp(points, axis=0)))
        tolerance = inputs.tolerance_mm if inputs.tolerance_mm is not None else IS.default_tolerance_mm(size)
        timings["post_s"] = time.perf_counter() - started
        # The tension along the welds: its 90th percentile over the weld zones (the peak element is the mesh's).
        zone_rows = np.flatnonzero(in_zone)
        peak_long = float(np.quantile(element_long[zone_rows], 0.9)) if len(zone_rows) else 0.0
        peak_at = xyz(centroids[zone_rows[int(np.argmax(element_long[zone_rows]))]]) if len(zone_rows) else None
        return space_result(
            space, {"von_mises": von_mises, "displacement": shape, "longitudinal_stress": longitudinal_field,
                    "weld_zone": zone_nodes},
            deformation=shape, solver=once.how, timings=timings, warnings=list(once.warnings),
            scalars={"plans": plans, "shape_max_mm": float(moved.max()), "shape_at": xyz(points[int(moved.argmax())]),
                     "vm_max": float(von_mises.max()), "vm_at": xyz(points[int(von_mises.argmax())]),
                     "longitudinal_peak": peak_long, "longitudinal_at": peak_at, "tolerance_mm": tolerance,
                     "tolerance_given": inputs.tolerance_mm is not None, "size_mm": size, "analysis_warnings": []},
        )

    # -- findings ------------------------------------------------------------------------------------

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: WeldingInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        s = result.scalars
        plans = s["plans"]
        found = [self._distortion(inputs, s), self._angles(plans), self._hand_check(plans)]
        bows = [plan for plan in plans if plan.get("bow_mm") is not None]
        if bows:
            found.append(self._bowing(max(bows, key=lambda plan: plan["bow_mm"]), s["tolerance_mm"]))
        found.append(self._residual(inputs, s))
        return found

    def _distortion(self, inputs: WeldingInputs, s: dict) -> dict:
        tolerance = s["tolerance_mm"]
        source = "the study's" if s["tolerance_given"] else f"ISO 2768-2 K for its {s['size_mm']:.3g} mm"
        value = s["shape_max_mm"]
        measured = {"value": round(value, 6), "limit": tolerance, "units": "mm", "pass_when": "below",
                    "quantity": "distortion"}
        item = [{"text": "distorts most here", "ref": None, "at": s["shape_at"]}]
        detail = "the largest distance any point moved from the CAD, the part's rigid motion taken out"
        if value <= tolerance:
            return finding("info", "distortion", f"The welds distort it {value:.3g} mm at most, within the {tolerance:g} "
                           f"mm tolerance ({source})", detail, item, measured=measured)
        plans = s["plans"]
        worst = max(plans, key=lambda plan: abs(plan["angle_rad"]))
        ratio = 0.9 * tolerance / value
        heat = round(worst["heat_J_mm"] * ratio / 1000.0, 3)
        alternatives = [
            {"action": "balance_welds", "summary": f"Weld the other side of {worst['label']}'s joint as well, or "
                       "alternate sides pass by pass, so the shrinkage balances", "where": [worst["middle"]],
             "params": {"weld": worst["label"]}},
            {"action": "preset", "summary": f"Preset the plates against it: open the joint by its "
                       f"{math.degrees(worst['angle_rad']):.2g}° before welding", "where": [worst["middle"]],
             "params": {"weld": worst["label"], "preset_deg": round(math.degrees(worst["angle_rad"]), 3)}},
        ]
        plate = worst["plates"][0]
        if plate["parameter"] < 10.6:
            alternatives.append({"action": "thicken", "summary": f"Thicken the plate under {worst['label']}: a plate "
                                 "this lightly heated turns less as it gets thicker", "where": [plate["face"]],
                                 "params": {"thickness_mm": round(plate["thickness_mm"] / math.sqrt(ratio), 2)}})
        return finding("error", "distortion", f"The welds distort it {value:.3g} mm at {s['shape_at']} mm, past the "
                       f"{tolerance:g} mm tolerance ({source}); {worst['label']} turns its joint the most "
                       f"({math.degrees(worst['angle_rad']):.2g}°)", detail, item, measured=measured, fix={
                           "action": "reduce_heat_input",
                           "summary": f"Weld {worst['label']} with less heat, about {heat:g} kJ/mm a pass (a smaller "
                                      "weld, faster travel), if the joint's strength allows",
                           "where": [worst["middle"]], "params": {"weld": worst["label"], "heat_input_kJ_mm": heat},
                           "alternatives": alternatives})

    def _angles(self, plans: list[dict]) -> dict:
        words = "; ".join(f"{plan['label']} {math.degrees(plan['angle_rad']):.2g}° ({plan['joint']}, "
                          f"Q {plan['heat_J_mm'] / 1000:.3g} kJ/mm × {plan['passes']})" for plan in plans)
        return finding("info", "angular_distortion", f"Angular distortion, the joint closing on the weld's side: {words}",
                       "each plate's rotation about the weld, fitted to its face's displacement beyond the weld zone, "
                       "summed over the plates the weld joins; positive closes the joint on the weld's side",
                       [{"text": plan["label"], "ref": None, "at": plan["middle"]} for plan in plans])

    def _hand_check(self, plans: list[dict]) -> dict:
        ratios = []
        for plan in plans:
            if plan["angle_empirical_rad"] > 0:
                ratios.append((plan["angle_rad"] / plan["angle_empirical_rad"], plan))
        if not ratios:
            return finding("info", "hand_check", "No hand check applies: no weld turns its plate by the empirical estimate",
                           "Satoh and Terasaki's angular distortion is zero for these welds")
        spread_of = [(max(r, 1.0 / r) if r > 0 else math.inf, r, plan) for r, plan in ratios]
        spread, ratio, plan = max(spread_of, key=lambda item: item[0])
        measured = {"value": round(spread, 4), "limit": HAND_FACTOR, "units": "×", "pass_when": "below",
                    "quantity": "simulated angle against Satoh and Terasaki"}
        summary = (f"Hand check: {plan['label']} turns its joint {math.degrees(plan['angle_rad']):.2g}°; Satoh and "
                   f"Terasaki's angular distortion for its Q / h² gives {math.degrees(plan['angle_empirical_rad']):.2g}° "
                   f"({ratio:.2g}×)")
        detail = ("θ = 1.44e-3 Q/h² rad (Q/h² ≤ 6.27 J/mm³), 0.1061 (Q/h²) / ((Q/h² - 6.16)² + 73.6) beyond, per plate "
                  "for its share of the heat, summed over the plates; the simulation adds what the rest of the part holds "
                  "back or lets go")
        if spread > HAND_FACTOR:
            return finding("warning", "hand_check_far", summary + f": more than {HAND_FACTOR:g} times apart; check the "
                           "weld's faces, its heat input and the plates' thicknesses", detail, measured=measured, fix={
                               "action": "check_inputs", "summary": "Check the weld's faces (the plate it lies on first), "
                               "its heat input and the plates' thickness_mm", "where": [plan["middle"]],
                               "params": {"weld": plan["label"],
                                          "thickness_mm": [round(p["thickness_mm"], 3) for p in plan["plates"]]}})
        return finding("info", "hand_check", summary, detail, measured=measured)

    def _bowing(self, plan: dict, tolerance: float) -> dict:
        """The bow along the longest-bowing weld, beside beam theory's: a check of the simulation's bow. A bow under a
        tenth of the tolerance is too small to tell from the part's own bending: it passes against the tolerance."""
        item = [{"text": "the middle of the weld", "ref": None, "at": plan["middle"]}]
        summary = f"Along {plan['label']} ({plan['length_mm']:.3g} mm) the part bows {plan['bow_mm']:.3g} mm"
        detail = ("the sagitta of the weld line's own displacement across it, the part's rigid motion taken out; a weld "
                  "off the section's neutral axis bows it, a balanced pair does not. Beam theory: the welds' tendon forces "
                  "F_T, each e off the mid-length section's centroid, bow it Σ F_T e L² / (8 E I)")
        beam = plan.get("bow_beam_mm")
        if beam is None or max(beam, plan["bow_mm"]) < 0.1 * tolerance:
            words = "the section is too short to set beside beam theory" if beam is None else (
                f"beam theory gives {beam:.3g} mm; both under a tenth of the {tolerance:g} mm tolerance")
            return finding("info", "bowing", f"{summary}; {words}", detail, item, measured={
                "value": round(plan["bow_mm"], 6), "limit": tolerance, "units": "mm", "pass_when": "below",
                "quantity": "bow along the weld"})
        ratio = plan["bow_mm"] / beam if beam > 0 else math.inf
        spread = max(ratio, 1.0 / ratio) if ratio > 0 else math.inf
        measured = {"value": round(spread, 4), "limit": HAND_FACTOR, "units": "×", "pass_when": "below",
                    "quantity": "simulated bow against beam theory"}
        summary += f"; beam theory gives {beam:.3g} mm ({ratio:.2g}×)"
        if spread > HAND_FACTOR:
            return finding("warning", "bowing", summary + f": more than {HAND_FACTOR:g} times apart, so the bow is the "
                           "section's own (short, or far from a beam) rather than a beam's; read it from the field",
                           detail, item, measured=measured, fix={
                               "action": "check_inputs", "summary": "Check the weld's line and faces; a weld much shorter "
                               "than the part's section is past beam theory", "where": [plan["middle"]],
                               "params": {"weld": plan["label"]}})
        return finding("info", "bowing", summary, detail, item, measured=measured)

    def _residual(self, inputs: WeldingInputs, s: dict) -> dict:
        yield_ = inputs.metal.yield_strength
        value = s["longitudinal_peak"]
        item = [{"text": "the peak stress along a weld", "ref": None, "at": s["longitudinal_at"]}] if s["longitudinal_at"] else []
        detail = (f"the stress along the weld in its zone, the 90th percentile of its elements; von Mises peaks at "
                  f"{s['vm_max']:.3g} MPa at {s['vm_at']} mm. Linear elastic: past yield, the weld yields and holds about "
                  "yield")
        near = value >= NEAR_YIELD * yield_
        level = (f"{value:.3g} MPa in tension, past the {yield_:g} MPa yield (in the part it holds about yield)"
                 if value > yield_ else f"{value:.3g} MPa in tension ({value / yield_:.0%} of the {yield_:g} MPa yield)")
        if not inputs.fatigue_critical:
            return finding("info", "residual_stress", f"Along the welds the residual stress reaches {level}, as a weld's "
                           "does; mark the study fatigue_critical to check it", detail, item)
        measured = {"value": round(value, 4), "limit": round(NEAR_YIELD * yield_, 4), "units": "MPa", "pass_when": "below",
                    "quantity": "tension along the weld"}
        if near:
            return finding("warning", "residual_stress", f"Along the welds the residual stress reaches {level}, near "
                           "yield, in a fatigue-critical part: take yield-level tension in its fatigue check, or relieve "
                           "it", detail, item, measured=measured, fix={
                               "action": "stress_relieve", "summary": "Stress-relieve the weldment (a post-weld heat "
                               "treatment), or peen the weld toes, and take yield-level tension in the fatigue check "
                               "until then", "where": [s["longitudinal_at"]], "params": {"post_weld_heat_treatment": True}})
        return finding("info", "residual_stress", f"Along the welds the residual stress stays at {value:.3g} MPa, under "
                       f"{NEAR_YIELD:.0%} of the {yield_:g} MPa yield", detail, item, measured=measured)

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: WeldingInputs, check_results: list[dict]) -> dict:
        s = result.scalars
        welds = []
        for plan in s["plans"]:
            welds.append({
                "label": plan["label"], "process": plan["process"], "joint": plan["joint"],
                "heat_input_kJ_mm": round(plan["heat_J_mm"] / 1000.0, 6), "heat": plan["heat_words"],
                "passes": plan["passes"], "length_mm": round(plan["length_mm"], 4),
                "from_mm": xyz(plan["p0"]), "to_mm": xyz(plan["p1"]),
                "tendon_force_kN": round(plan["tendon_N"] / 1000.0, 6),
                "zone_area_mm2": round(plan["zone_area_mm2"], 4),
                "longitudinal_strain": round(plan["longitudinal_strain"], 9),
                "plates": [{"face": plate["face"], "thickness_mm": round(plate["thickness_mm"], 4),
                            "heat_share": round(plate["share"], 4), "Q_over_h2_J_mm3": round(plate["parameter"], 4),
                            "transverse_shrinkage_mm": round(plate["shrinkage_mm"], 6),
                            "angle_empirical_deg": round(math.degrees(plate["angle_rad"]), 6),
                            "angle_deg": None if plate.get("measured_rad") is None else round(math.degrees(plate["measured_rad"]), 6)}
                           for plate in plan["plates"]],
                "angle_deg": round(math.degrees(plan["angle_rad"]), 6),
                "angle_empirical_deg": round(math.degrees(plan["angle_empirical_rad"]), 6),
                "bow_mm": None if plan.get("bow_mm") is None else round(plan["bow_mm"], 6),
                "bow_beam_mm": None if plan.get("bow_beam_mm") is None else round(plan["bow_beam_mm"], 6),
                "longitudinal_stress_MPa": round(plan.get("zone_stress_MPa", 0.0), 4),
            })
        return {
            "alloy": inputs.metal.name,
            "yield_MPa": inputs.metal.yield_strength,
            "welds": welds,
            "max_distortion_mm": round(s["shape_max_mm"], 6),
            "max_distortion_at_mm": s["shape_at"],
            "max_angle_deg": round(max(abs(w["angle_deg"]) for w in welds), 6),
            "max_von_mises_MPa": round(s["vm_max"], 4),
            "max_von_mises_at_mm": s["vm_at"],
            "max_longitudinal_stress_MPa": round(s["longitudinal_peak"], 4),
            "tolerance_mm": s["tolerance_mm"],
            "tolerance_source": "study" if s["tolerance_given"] else f"ISO 2768-2 K for {s['size_mm']:.4g} mm",
            "fatigue_critical": inputs.fatigue_critical,
            "checks": check_results,
        }

    def ready_words(self, summary: dict) -> str:
        """The verdict's headline when nothing is to fix: "Ready to weld · 0.62° angular distortion"."""
        return f"Ready to weld · {summary['max_angle_deg']:.2g}° angular distortion"

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        largest = float(np.linalg.norm(result.fields["displacement"], axis=1).max())
        return requested or auto_deformation_scale(largest, bbox_diagonal)

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        fields = result.fields
        longitudinal = fields["longitudinal_stress"]
        return {
            "von_mises": (0.0, round(float(fields["von_mises"].max()), 4)),
            "displacement": (0.0, round(float(np.linalg.norm(fields["displacement"], axis=1).max()), 6)),
            "longitudinal_stress": (round(float(longitudinal.min()), 4), round(float(longitudinal.max()), 4)),
            "weld_zone": (0.0, 1.0),
        }

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: WeldingInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = {
            # The viewer's "Made of" reads the material's name: the base metal is the weldment's material.
            "material": {"name": inputs.metal.name},
            "alloy": inputs.metal.as_dict(),
            "welds": [{"label": weld.label, "faces": bare(weld.faces), "process": weld.process.key,
                       "heat_input_kJ_mm": weld.heat_J_mm / 1000.0, "passes": weld.passes,
                       **({"line_mm": [list(p) for p in weld.line]} if weld.line else {}),
                       **({"thickness_mm": list(weld.thickness)} if weld.thickness else {})}
                      for weld in inputs.welds],
            "fatigue_critical": inputs.fatigue_critical,
        }
        if inputs.tolerance_mm is not None:
            echo["tolerance_mm"] = inputs.tolerance_mm
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        lines = [f"{summary['alloy']}: distortion up to {summary['max_distortion_mm']:.3g} mm at "
                 f"{summary['max_distortion_at_mm']} mm (tolerance {summary['tolerance_mm']:g} mm)"]
        for weld in summary["welds"]:
            bow = f", bows {weld['bow_mm']:.3g} mm" if weld["bow_mm"] is not None else ""
            lines.append(f"{weld['label']}: {weld['joint']}, {weld['heat_input_kJ_mm']:.3g} kJ/mm × {weld['passes']}, "
                         f"turns {weld['angle_deg']:.3g}° (Satoh and Terasaki {weld['angle_empirical_deg']:.3g}°){bow}")
        lines.append(f"residual stress along the welds up to {summary['max_longitudinal_stress_MPa']:.3g} MPa (yield "
                     f"{summary['yield_MPa']:g} MPa)")
        return lines


# -- the welds on the mesh -----------------------------------------------------------------------------


def _weld_plan(space, weld: Weld, ctx: SolveContext, ordinals, triangles, metal) -> dict:
    """Where the weld runs and what it does to each plate: its line, the plates' normals, thicknesses and heat shares,
    and the classical relations' tendon force, transverse shrinkage and angle for each."""
    import numpy as np

    from cadgen._internal.manufacturing.processes import weldments

    points = space.dof_locations
    faces = []
    for ref in weld.faces:
        rows = np.flatnonzero(ordinals == ctx.ordinal_of[ref])
        if len(rows) == 0:
            raise ValueError(f"welding: {weld.label}: {ref} has no surface on the mesh")
        normal = weldments.outward_normal(space, rows)
        faces.append({"ref": ref, "rows": rows, "nodes": np.unique(triangles[rows]), "normal": normal})
    if weld.line is not None:
        p0, p1 = (np.asarray(p, dtype=float) for p in weld.line)
    else:
        shared = np.intersect1d(faces[0]["nodes"], faces[1]["nodes"])
        if len(shared) < 2:
            raise ValueError(f"welding: {weld.label}: {weld.faces[0]} and {weld.faces[1]} share no edge; a weld runs "
                             "along the edge two faces share, or give its line_mm")
        line_points = points[shared]
        centre = line_points.mean(axis=0)
        direction = np.linalg.svd(line_points - centre)[2][0]
        reach = (line_points - centre) @ direction
        p0, p1 = centre + reach.min() * direction, centre + reach.max() * direction
    length = float(np.linalg.norm(p1 - p0))
    if not length > 1e-6 * max(float(np.ptp(points, axis=0).max()), 1e-300):
        raise ValueError(f"welding: {weld.label}: its line has no length")
    t = (p1 - p0) / length
    fillet = len(faces) == 2 and abs(float(faces[0]["normal"] @ faces[1]["normal"])) < 0.9
    plates = []
    members = faces if fillet else faces[:1]
    for index, face in enumerate(members):
        n = face["normal"]
        if abs(float(n @ t)) > 0.2:
            raise ValueError(f"welding: {weld.label}: the weld does not run along {face['ref']} (it crosses it at "
                             f"{math.degrees(math.acos(min(1.0, abs(float(n @ t))))):.0f}° to its normal)")
        w = np.cross(n, t)
        w /= np.linalg.norm(w)
        nodes = np.unique(np.concatenate([f["nodes"] for f in (faces if not fillet else [face])]))
        side = (points[nodes] - p0) @ w
        if np.median(side) < 0:
            w, side = -w, -side
        origin = points[face["nodes"]].mean(axis=0)
        origin = p0 + ((origin - p0) @ n) * n                # the face's plane, through the weld
        thickness = None if weld.thickness is None else weld.thickness[index]
        if thickness is None:
            rows = face["rows"]
            centres = points[triangles[rows][:, :3]].mean(axis=1)
            lateral = np.abs((centres - p0) @ w)
            pick = rows[np.argsort(lateral)[: min(16, len(rows))]]
            starts = points[triangles[pick][:, :3]].mean(axis=1) - 1e-6 * n
            thickness = weldments.thickness_along(space, starts, -n)
            if thickness is None:
                raise ValueError(f"welding: {weld.label}: could not measure the plate under {face['ref']}; give the "
                                 "weld's thickness_mm")
        two_sided = (not fillet) and side.min() < -0.25 * thickness and side.max() > 0.25 * thickness
        plates.append({"face": face["ref"], "normal": n, "lateral": w, "origin": origin, "thickness_mm": float(thickness),
                       "two_sided": bool(two_sided), "lateral_max": float(side.max()), "nodes": face["nodes"] if fillet
                       else nodes})
    shares = weldments.heat_shares([plate["thickness_mm"] for plate in plates]) if fillet else [1.0]
    for plate, share in zip(plates, shares):
        heat = share * weld.heat_J_mm
        plate["share"] = share
        plate["parameter"] = heat * metal.shrink / weldments.REFERENCE.shrink / plate["thickness_mm"] ** 2
        plate["angle_rad"] = weld.passes * weldments.angular_200(metal, heat, plate["thickness_mm"])
        plate["shrinkage_mm"] = weld.passes * weldments.transverse_200(metal, heat, plate["thickness_mm"], fillet=fillet)
    return {"label": weld.label, "process": weld.process.key, "joint": "fillet" if fillet else "butt",
            "heat_J_mm": weld.heat_J_mm, "heat_words": weld.heat_words, "passes": weld.passes, "p0": p0, "p1": p1,
            "t": t, "length_mm": length, "middle": xyz(0.5 * (p0 + p1)), "plates": plates,
            "tendon_N": weldments.tendon_force_N(metal, weld.heat_J_mm),
            "angle_empirical_rad": sum(plate["angle_rad"] for plate in plates)}


def _rotation(points, shape, nodes, p0, t, plate, length, max_h, sign: float = 1.0) -> float | None:
    """A plate face's rotation about the weld, radians, closing the joint positive: the slope of its points'
    displacement along its normal against their distance from the weld, beyond the weld's strip."""
    import numpy as np

    lateral = sign * ((points[nodes] - p0) @ plate["lateral"])
    along = (points[nodes] - p0) @ t
    far = float(lateral.max())
    start = min(plate["thickness_mm"], 0.5 * far)
    use = (lateral >= start) & (along >= 0.1 * length) & (along <= 0.9 * length)
    if use.sum() < 4 or far - start < 0.5 * max_h:
        return None
    a = np.column_stack([np.ones(int(use.sum())), lateral[use], along[use]])
    coefficients, *_ = np.linalg.lstsq(a, shape[nodes][use] @ plate["normal"], rcond=None)
    return float(coefficients[1])


def _measure(space, plan: dict, shape, centroids, volumes, metal, max_h, element_long) -> None:
    """The weld's angular distortion and bow as simulated, and beam theory's bow, into ``plan``."""
    import numpy as np

    points = space.dof_locations
    p0, t, length = plan["p0"], plan["t"], plan["length_mm"]
    total = 0.0
    for plate in plan["plates"]:
        if plate["two_sided"]:
            parts = [_rotation(points, shape, plate["nodes"], p0, t, plate, length, max_h, sign) for sign in (1.0, -1.0)]
            measured = sum(part for part in parts if part is not None) if any(p is not None for p in parts) else None
        else:
            measured = _rotation(points, shape, plate["nodes"], p0, t, plate, length, max_h)
        plate["measured_rad"] = measured
        total += measured or 0.0
    plan["angle_rad"] = total
    zone = plan["zone"]
    plan["zone_stress_MPa"] = float(np.median(element_long[zone])) if len(zone) else 0.0
    # The bow: the weld line's own displacement across it, a parabola along it.
    along = (points - p0) @ t
    radial = np.linalg.norm((points - p0) - np.outer(along, t), axis=1)
    near = np.flatnonzero((radial <= 1.5 * max_h) & (along >= 0.0) & (along <= length))
    plan["bow_mm"] = None
    if len(near) >= 5 and length > 4.0 * max_h:
        across = shape[near] - np.outer(shape[near] @ t, t)
        a = np.column_stack([np.ones(len(near)), along[near], along[near] ** 2])
        coefficients, *_ = np.linalg.lstsq(a, across, rcond=None)
        plan["bow_mm"] = float(np.linalg.norm(coefficients[2]) * length ** 2 / 4.0)


def _beam_bow(plan: dict, plans: list[dict], centroids, volumes, metal, max_h) -> None:
    """Beam theory's bow along ``plan``'s weld: the tendon forces of every weld along it (parallel, overlapping),
    each off the part's mid-length section's centroid by its zone's offset, bend the part with the moment Σ F_T e;
    the curvature M / (E I) bows it M L² / (8 E I)."""
    import numpy as np

    plan["bow_beam_mm"], plan["eccentricity_mm"] = None, None
    p0, t, length = plan["p0"], plan["t"], plan["length_mm"]
    element_along = (centroids - p0) @ t
    slab = max(1.5 * max_h, length / 20.0)
    section = np.flatnonzero(np.abs(element_along - 0.5 * length) <= slab / 2)
    if len(section) < 4:
        return
    v = volumes[section]
    centre = (centroids[section] * v[:, None]).sum(axis=0) / v.sum()
    moment = np.zeros(3)
    for other in plans:
        if abs(float(other["t"] @ t)) < 0.99 or len(other["zone"]) == 0:
            continue
        reach = (np.array([other["p0"], other["p1"]]) - p0) @ t
        if reach.max() < 0.25 * length or reach.min() > 0.75 * length:
            continue
        zone = other["zone"]
        zone_centre = (centroids[zone] * volumes[zone][:, None]).sum(axis=0) / volumes[zone].sum()
        offset = (zone_centre - centre) - ((zone_centre - centre) @ t) * t
        moment += other["tendon_N"] * offset
        if other is plan:
            plan["eccentricity_mm"] = float(np.linalg.norm(offset))
    size = float(np.linalg.norm(moment))
    if size <= 1e-9:
        plan["bow_beam_mm"] = 0.0
        return
    e_hat = moment / size
    inertia = float((v * ((centroids[section] - centre) @ e_hat) ** 2).sum()) / slab
    plan["bow_beam_mm"] = size * length ** 2 / (8.0 * metal.E * inertia)
