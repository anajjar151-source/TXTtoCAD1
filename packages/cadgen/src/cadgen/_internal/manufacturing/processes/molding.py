"""Injection molding (lite): a moulded part cooling in its mould from the melt until it can be ejected, and its warp.

The study names the ``resin`` (:data:`cadgen._internal.manufacturing.processes.resins.RESINS`); the melt and mould temperatures default to
the middle of the resin's processing window and the ejection temperature to the resin's, and ``melt_temperature_C``,
``mold_temperature_C`` and ``ejection_temperature_C`` override them. The mould is a heat transfer coefficient
``h_W_m2K`` (default :data:`STEEL_H`, a steel mould's contact with the plastic) to the mould temperature on every
face. The cavity starts full and packed at the melt temperature (there is no fill), and casting's enthalpy march
(:mod:`cadgen._internal.manufacturing.processes.solidification`) cools it until every point is below the ejection temperature, a
semi-crystalline resin releasing its crystallisation heat over its crystallisation range.

It writes the time each point reaches the ejection temperature (the default view: the last to eject is hottest), the
temperature per frame, the mean cooling rate from the melt to ejection, and the warp: each point shrinks by the
resin's mould shrinkage, from the low end of its range at the thinnest wall toward the high end the longer it stayed
hot (:func:`cadgen._internal.manufacturing.processes.resins.linear_shrinkage`, a model of cadgen's own, not a published
law: the warp is an estimate, and its findings say so); the shrinkage's mean is what the cavity is cut oversize
for, and what differs from it is an inherent strain, solved on the part held 3-2-1 (:mod:`cadgen._internal.manufacturing.processes.warp`).
Its findings are the moulder's checklist, each saying pass or what to change: the cooling time against the plate
formula for the thickest wall (the hand check), sink and void risk where a section stays hot long after the nominal
wall, the warp against ``warp_tolerance_mm``, and walls outside the resin's recommended range. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import (
    AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext, frame_attributes, max_frames, xyz,
)
from cadgen._internal.manufacturing.processes.base import Process, finding_of

__all__ = ["LIMITS", "MoldingInputs", "MoldingProcess"]

#: This process's findings, held to its closed set (``base.FINDING_TYPES``).
finding = finding_of("molding")

LIMITS = (
    "The cavity starts full and packed at the melt temperature: filling and packing are not simulated, so a thin "
    "wall far from the gate that freezes before it fills (a short shot) is not seen.",
    "The mould is a heat transfer coefficient to its temperature on every face, not meshed: no cooling channels, "
    "and a core or a corner of the mould that runs hot is not seen.",
    "Constant room-temperature properties; crystallisation releases its heat evenly over a fixed range, whatever the "
    "cooling rate.",
    "The warp is an estimate from a model of cadgen's own, not a published law: each point's shrinkage is placed in the "
    "resin's published mould shrinkage range by how long it stayed hot (the low end where the thinnest wall cooled, "
    "toward the high end, as 1 - t_thin / t, where it stayed hot longer), the same in every direction (no flow or "
    "fibre orientation, no pressure history), applied elastically after ejection. Read its pattern and its order of "
    "magnitude, never its last digit, and confirm a warp that matters with the moulder's own simulation or a trial.",
)
#: A steel mould's contact coefficient with the plastic, W/(m² K): Moldflow's standard value.
STEEL_H = 2500.0
#: Poisson's ratio of every resin in the warp solve (thermoplastics run 0.33-0.42); the modulus cancels from the warp.
POISSON = 0.38
#: A region that stays hot this many times as long as the nominal wall is a sink risk: a rib of 0.6 of the wall leaves
#: a root about 9 % thicker than the wall, which stays hot about 1.2 times as long.
SINK_RATIO = 1.2
#: ... and this many times (a section about 1.7 times the wall, a boss) sinks or voids: an error.
VOID_RATIO = 3.0
#: A rib's thickness should stay under this share of the wall it stands on.
RIB_SHARE = 0.6
#: A hot region must hold this share of the part's volume, and this many times the nominal wall cubed, to be one
#: (smaller are the mesh's ripples).
HOT_VOLUME, HOT_BALL = 0.001, 0.5
#: The nominal wall stays hot as long as this quantile of its sections (by area): its own middle, mesh scatter and all.
NOMINAL_LATE = 0.9
#: Hot regions named, at most.
MOST_SPOTS = 5
#: The hand check and the simulation disagree past this factor: a warning.
HAND_FACTOR = 3.0
#: Elements across the wall a study with no mesh.size_mm is meshed at, and the fewest a run is trusted with: linear
#: tets with a lumped heat capacity cool a wall's middle about 10 % slow three across, 5 % four across, 23 % two across.
ACROSS_WALL = 3.0
#: The thinnest wall is the wall a share of the surface this large is at or under (one sliver of a ray is not a wall).
WALL_AREA = 0.005
#: A section crosses a wall when its middle is at least this share of it from every surface (a quarter: a ball half as
#: wide as the section fits there); a plate's edge face's section runs along the plate, its middle a wall's half away.
WALL_RAY = 0.25
GOAL = "below the ejection temperature everywhere"


@dataclass(frozen=True)
class MoldingInputs(Inputs):
    resin: Any = None
    melt_C: float = 0.0
    mold_C: float = 0.0
    eject_C: float = 0.0
    h: float = STEEL_H
    #: The study's warp tolerance, mm; ``None`` to report the warp only.
    warp_tolerance_mm: float | None = None


def time_words(seconds: float) -> str:
    from cadgen._internal.fea.analyses.thermal_transient import time_label

    return time_label(seconds)


def _rib_share(ratio: float) -> float:
    """The rib (as a share of the wall) whose root stays hot ``ratio`` times as long as the wall: a T-junction's
    inscribed circle is w + r² / (4 w) across, and the time grows with its square."""
    return 2.0 * math.sqrt(max(math.sqrt(ratio) - 1.0, 0.0))


class MoldingProcess(Process):
    name: ClassVar[str] = "molding"
    word: ClassVar[str] = "Injection molding"
    extras_word: ClassVar[str] = "molding"
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "resin", "melt_temperature_C", "mold_temperature_C", "ejection_temperature_C", "h_W_m2K", "warp_tolerance_mm",
    })
    #: Linear tets: their lumped capacity is positive, which the enthalpy march needs (the warp elevates them).
    mesh_orders: ClassVar[tuple[int, ...]] = (1,)
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("ejection_time", "_EJECTION_TIME", "time to ejection temperature", "s", signed=True),
        FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True, per_frame=True),
        FieldSpec("cooling_rate", "_COOLING_RATE", "mean cooling rate, melt to ejection", "°C/s"),
        FieldSpec("shrinkage", "_SHRINKAGE", "linear shrinkage", "%", signed=True),
        FieldSpec("warp", "_DISPLACEMENT", "warp", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = ()
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "frame", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum",
                  "options": ["ejection_time", "temperature", "cooling_rate", "shrinkage", "warp"]},
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "defeature")
    noun: ClassVar[str] = "this moulding"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> MoldingInputs:
        from cadgen._internal.manufacturing.processes.resins import RESINS, lookup_resin

        if "material" in document:
            raise ValueError(f"study.material: a molding study names its plastic with 'resin', one of {', '.join(RESINS)}")
        for key in ("parts", "connections"):
            if key in document:
                raise ValueError(f"study.{key}: a molding study solves one part, the moulding; solve one occurrence "
                                 "with --occurrence")
        if "resin" not in document:
            raise ValueError(f"study.resin: the resin it is moulded in, one of {', '.join(RESINS)}")
        resin = lookup_resin(document["resin"])
        melt = kinds.number(document["melt_temperature_C"], where="melt_temperature_C") if "melt_temperature_C" in document \
            else resin.melt_C
        mold = kinds.number(document["mold_temperature_C"], where="mold_temperature_C") if "mold_temperature_C" in document \
            else resin.mold_C
        eject = (kinds.number(document["ejection_temperature_C"], where="ejection_temperature_C")
                 if "ejection_temperature_C" in document else resin.eject_C)
        if mold >= eject:
            field = "mold_temperature_C" if "mold_temperature_C" in document else "ejection_temperature_C"
            raise ValueError(f"{field}: the mould at {mold:g} °C is not below the ejection temperature ({eject:g} °C): the "
                             "part would never cool enough to eject")
        if melt <= eject:
            field = "melt_temperature_C" if "melt_temperature_C" in document else "ejection_temperature_C"
            raise ValueError(f"{field}: the melt at {melt:g} °C is not above the ejection temperature ({eject:g} °C)")
        if resin.crystallises is not None and melt <= resin.crystallises[1]:
            raise ValueError(f"melt_temperature_C: {melt:g} °C is not above where {resin.name} starts to crystallise "
                             f"({resin.crystallises[1]:g} °C): it would not flow")
        h = STEEL_H
        if "h_W_m2K" in document:
            h = kinds.number(document["h_W_m2K"], where="h_W_m2K", positive=True)
        tolerance = None
        if "warp_tolerance_mm" in document:
            tolerance = kinds.number(document["warp_tolerance_mm"], where="warp_tolerance_mm", positive=True)
        return MoldingInputs((), (), False, resin=resin, melt_C=melt, mold_C=mold, eject_C=eject, h=h,
                             warp_tolerance_mm=tolerance)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: MoldingInputs):
        """The cooling (casting's march: a few thousand preconditioned solves of a temperature problem) and the warp,
        one elastic solve on quadratic tets made from the same linear ones.

        A study that names no ``mesh.size_mm`` is meshed :data:`ACROSS_WALL` elements across its wall, the wall taken
        as 2 V / A before meshing (a plate's own thickness), and never coarser than the default: the linear tets'
        lumped heat capacity cools a wall one element thick at once, and slows the middle of a wall two thick by a
        fifth."""
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.thermal import ladder_estimate
        from cadgen._internal.fea.mesh import default_mesh_size

        plan, geometry = ctx.plan, ctx.geometry
        if plan is not None and plan.size_mm is None and geometry is not None and geometry.area_mm2 > 0:
            wall = 2.0 * geometry.volume_mm3 / geometry.area_mm2
            plan.size_mm = min(default_mesh_size(geometry.bbox_diagonal_mm), wall / ACROSS_WALL)
        heat = ladder_estimate(ctx, steps=4000, frames=2 * max_frames(ctx))
        order = ctx.plan.order
        ctx.plan.order = 2
        try:
            warp = fit.solid_estimate(ctx)
        finally:
            ctx.plan.order = order
        return fit.Estimate(dofs=max(heat.dofs, warp.dofs), memory_bytes=max(heat.memory_bytes, warp.memory_bytes),
                            seconds=heat.seconds + warp.seconds)

    def apply(self, rung, ctx: SolveContext, inputs: MoldingInputs):
        from cadgen._internal.fea import fit

        return fit.apply_generic(rung, self, ctx, inputs)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: MoldingInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import timestep
        from cadgen._internal.manufacturing.processes import solidification, warp
        from cadgen._internal.fea.analyses.thermal import plan_solver, space_result
        from cadgen._internal.fea.operators import DIRECT_SOLVE_BELOW

        if ctx.assembly is not None:
            raise ValueError("molding: the document holds several parts; a molding study solves one, so name it with "
                             "--occurrence")
        space = ctx.space
        if space.order != 1:
            raise ValueError("molding: solved on linear tets (mesh.order 1)")
        resin = inputs.resin
        started = time.perf_counter()
        nodes = space.dof_locations
        m = solidification.node_volumes(space)
        part_volume = float(m.sum())
        rows = np.ones(len(space.boundary_quadratic), dtype=bool)
        films = [solidification.Film(space.facets_of_rows(rows), inputs.mold_C, lambda t0, t1, h=inputs.h: h)]
        walls = _walls(space, np.zeros(len(nodes)))
        hand = _hand(resin, inputs, walls.thickest_mm)
        timings = {"assemble_s": time.perf_counter() - started}
        started = time.perf_counter()
        iterative = plan_solver(ctx) is not None or len(nodes) >= DIRECT_SOLVE_BELOW
        run = solidification.march(
            space, resin.solved(inputs.melt_C, inputs.eject_C), pour_C=inputs.melt_C, films=films, held=None,
            first_step_s=hand["best_s"] / 1000.0, hand_s=hand["best_s"], end_s=None, span_C=inputs.melt_C - inputs.mold_C,
            frames=max_frames(ctx), iterative=iterative, log=ctx.log, limit_s=timestep.time_limit(ctx),
            stop_C=inputs.eject_C, goal=GOAL, watch_C=_sink_C(resin, inputs),
        )
        timings["cool_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"followed the cooling for {run.end_s:.4g} s in {run.steps} steps in {timings['cool_s']:.1f}s")
        started = time.perf_counter()
        eject = run.freeze_s
        walls = _walls(space, eject)
        # The warp: each point's shrinkage by how long it stayed hot against the thinnest wall, less the mean (the
        # cavity is cut oversize by it), as an inherent strain on the part held 3-2-1.
        reference = walls.thinnest_s if walls.thinnest_s > 0 else float(np.median(eject))
        ratio = eject / max(reference, 1e-12)
        low, high = resin.shrinkage   # resins.linear_shrinkage, at every node
        shrinkage = np.where(ratio > 1.0, low + (high - low) * (1.0 - 1.0 / np.maximum(ratio, 1.0)), low)
        tets = np.asarray(space.mesh.t)
        volumes = _tet_volumes(space)
        per_tet = shrinkage[tets].mean(axis=0) / 100.0
        mean_shrinkage = float(volumes @ per_tet / volumes.sum())
        warnings_out: list[str] = []
        warped = warp.warp(space, -(per_tet - mean_shrinkage), POISSON, warnings=warnings_out)
        timings["warp_s"] = time.perf_counter() - started
        started = time.perf_counter()
        graph = solidification.mesh_graph(space)
        # Sink: how long each point stays hot against the nominal wall, to the ejection temperature, or for a resin that
        # crystallises above it, to where it starts to (the crystallisation plateau would stretch small differences).
        sink_times = run.watch_s if run.watch_s is not None else eject
        sink_nominal_s = _walls(space, sink_times).nominal_late_s if run.watch_s is not None else walls.nominal_late_s
        spots = _hot_regions(sink_times, graph, m, sink_nominal_s, max(HOT_VOLUME * part_volume,
                                                                       HOT_BALL * walls.nominal_mm ** 3))
        rate = (inputs.melt_C - inputs.eject_C) / np.maximum(eject, 1e-12)
        temperatures = [state for _, state in run.frames]
        too_hot = [i for i, state in enumerate(temperatures) if float(state.max()) > inputs.eject_C]
        default = too_hot[-1] if too_hot else 0
        series = Series(kind="time", unit="s", default=default, frames=[
            SeriesFrame(value=round(t, 9), label=time_words(t), attributes=frame_attributes({"temperature": "_TEMPERATURE"}, i))
            for i, (t, _) in enumerate(run.frames)
        ])
        mean_eject = _crossing(run.curve_t, run.curve_mean, inputs.eject_C)
        warnings = []
        if run.stopped_at is not None:
            warnings.append(timestep.stopped_sentence(time_words(run.stopped_at), "ejectable", timestep.time_limit(ctx)))
        if run.cut_short:
            warnings.append(run.cut_short[0].upper() + run.cut_short[1:])
        timings["post_s"] = time.perf_counter() - started
        result = space_result(
            space,
            {"ejection_time": eject, "temperature": temperatures[0], "cooling_rate": rate, "shrinkage": shrinkage,
             "warp": warped.displacement},
            series=series, frame_fields={"temperature": temperatures},
            curves={"too_hot_percent": {"x": [round(t, 9) for t in run.curve_t], "x_unit": "s",
                                        "y": [round(v, 6) for v in run.curve_above], "y_unit": "%"},
                    "mean_temperature": {"x": [round(t, 9) for t in run.curve_t], "x_unit": "s",
                                         "y": [round(v, 6) for v in run.curve_mean], "y_unit": "°C"}},
            solver=f"{run.solver}; the warp by {warped.how} on {warped.dofs} quadratic DOF", timings=timings,
            warnings=list(warnings) + warnings_out,
            scalars={"run": run, "walls": walls, "hand": hand, "spots": spots, "warp": warped, "volume_mm3": part_volume,
                     "mass_g": resin.density * part_volume * 1e6, "mean_shrinkage": mean_shrinkage, "reference_s": reference,
                     "mean_eject_s": mean_eject, "size_mm": float(ctx.volume.max_h), "sink_times": sink_times,
                     "sink_nominal_s": sink_nominal_s, "analysis_warnings": warnings},
        )
        result.deformation = warped.displacement
        result.dofs = max(result.dofs, warped.dofs)
        return result

    def ready_words(self, summary: dict) -> str:
        """The verdict's headline when nothing is to fix."""
        return f"Ready to mold · ejects in {time_words(summary['cooling_time_s'])}"

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        return requested or auto_deformation_scale(float(np.linalg.norm(result.fields["warp"], axis=1).max()), bbox_diagonal)

    # -- findings ------------------------------------------------------------------------------------

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: MoldingInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.timestep import stopped_finding

        s = result.scalars
        run = s["run"]
        found = []
        if run.stopped_at is not None:
            found.append(stopped_finding(s["analysis_warnings"][0]))
        if run.cut_short:
            found.append(finding("warning", "not_ejectable", f"Not ejectable everywhere at the end: {run.cut_short}",
                                 "the time to ejection of the points still too hot is the end of the run, a lower bound",
                                 fix={"action": "check_inputs", "summary": "Check the temperatures and h, or give a "
                                      "lower mould temperature", "where": [], "params": {}}))
        found.append(self._mesh(result))
        found.append(self._cooling(result, inputs))
        found.append(self._hand_check(result, inputs))
        found += self._sink(ctx, result, inputs)
        found += self._walls(ctx, result, inputs)
        found.append(self._warp(result, inputs))
        found += self._window(inputs)
        if inputs.resin.key == "pa66-gf30":
            found.append(finding("info", "fibre_filled", f"{inputs.resin.name} shrinks about half as much along the "
                                 "flow as across it; the warp here takes its shrinkage as the same every way, so it can "
                                 "miss the warp that difference makes", "glass fibres line up with the flow and hold "
                                 "the plastic along it"))
        return found

    def _where(self, ctx: SolveContext, row: int) -> str | None:
        ordinal = int(ctx.volume.boundary_ordinal[row]) if row >= 0 else None
        face = ctx.volume.faces.get(ordinal) if ordinal is not None else None
        return face.ref if face else None

    def _mesh(self, result: AnalysisResult) -> dict:
        s = result.scalars
        nominal, size = s["walls"].nominal_mm, s["size_mm"]
        across = nominal / size
        measured = {"quantity": "elements across the wall", "value": round(across, 3), "limit": ACROSS_WALL, "units": "",
                    "pass_when": "above"}
        if across >= ACROSS_WALL * 0.9:
            return finding("info", "mesh_across_wall", f"About {across:.2g} elements across the nominal {nominal:.2g} mm "
                           "wall: enough to follow its cooling", "the mesh's element size against the nominal wall",
                           measured=measured)
        size = round(nominal / ACROSS_WALL, 3)
        return finding("warning", "coarse_mesh", f"Only about {across:.2g} elements across the nominal {nominal:.2g} mm "
                       "wall: the middle of the wall cools too slowly here (a fifth too slowly at two across), and a "
                       "wall one element thick cools at once", "linear tets with a lumped heat capacity cool a wall's "
                       "middle about 10 % slow at three elements across and 5 % at four",
                       measured=measured, fix={"action": "refine_mesh", "where": [], "params": {"mesh_size_mm": size},
                                               "summary": f"Solve again with mesh.size_mm {size:g}"})

    def _cooling(self, result: AnalysisResult, inputs: MoldingInputs) -> dict:
        eject = result.fields["ejection_time"]
        last = int(eject.argmax())
        at = xyz(result.dof_locations[last])
        return finding("info", "cooling_time",
                       f"Ejectable everywhere at {time_words(float(eject.max()))}: the last point to reach "
                       f"{inputs.eject_C:g} °C is at {at} mm", "the time from the cavity full at the melt temperature "
                       "until every point is below the ejection temperature; filling and packing add to the cycle",
                       [{"text": "the last to cool", "ref": None, "at": at}])

    def _hand_check(self, result: AnalysisResult, inputs: MoldingInputs) -> dict:
        s = result.scalars
        hand, total = s["hand"], float(result.fields["ejection_time"].max())
        ratio = total / hand["best_s"] if hand["best_s"] > 0 else math.inf
        latent = " with its crystallisation heat" if inputs.resin.semi_crystalline else ""
        summary = (f"The plate formula for the thickest wall ({hand['wall_mm']:.3g} mm, α = {hand['alpha_mm2_s']:.3g} "
                   f"mm²/s): {time_words(hand['mean_s'])} to its mean at {inputs.eject_C:g} °C (8/π²) and "
                   f"{time_words(hand['centre_s'])} to its middle (4/π) against a mould face held at "
                   f"{inputs.mold_C:g} °C; with the mould's h{latent}, {time_words(hand['best_s'])} to its middle. The "
                   f"simulation: every point at {time_words(total)} ({ratio:.2g} times)")
        measured = {"quantity": "simulation against the plate formula", "value": round(ratio, 4), "limit": HAND_FACTOR,
                    "units": "×", "pass_when": "below" if ratio >= 1.0 else "above"}
        if ratio < 1.0:
            measured["limit"] = round(1.0 / HAND_FACTOR, 6)
        if 1.0 / HAND_FACTOR <= ratio <= HAND_FACTOR:
            return finding("info", "hand_check", summary, "t = s² / (π² α) ln(C (T_melt - T_mould) / (T_eject - "
                           "T_mould)) for a plate cooled on both faces; a boss or a corner cools sooner than a plate of "
                           "its thickness, a semi-crystalline resin later than its α says", measured=measured)
        return finding("warning", "hand_check_far", summary + f": more than {HAND_FACTOR:g} times apart; check the "
                       "resin, the temperatures and h", "the plate formula for the part's thickest wall",
                       measured=measured, fix={"action": "check_inputs", "summary": "Check the resin, the three "
                                               "temperatures and h_W_m2K against the moulder's", "where": [], "params": {}})

    def _sink(self, ctx: SolveContext, result: AnalysisResult, inputs: MoldingInputs) -> list[dict]:
        s = result.scalars
        walls, spots = s["walls"], s["spots"]
        nominal = walls.nominal_mm
        rib = RIB_SHARE * nominal
        nodes = result.dof_locations
        found = []
        for spot in spots[:MOST_SPOTS]:
            at = xyz(nodes[spot.peak])
            ratio = spot.ratio
            thick = nominal * math.sqrt(ratio)
            measured = {"quantity": "stays hot, against the nominal wall", "value": round(ratio, 4), "limit": SINK_RATIO,
                        "units": "×",
                        "pass_when": "below"}
            fix = {"action": "thin", "where": [at], "params": {"thickness_mm": round(nominal, 3),
                                                              "rib_thickness_mm": round(rib, 3)},
                   "summary": (f"Core it out so no section is thicker than the nominal {nominal:.2g} mm wall (a hollow "
                               f"boss's wall, or a rib, about {RIB_SHARE:g} of it: {rib:.2g} mm)" if ratio >= VOID_RATIO
                               else f"Thin it toward the nominal {nominal:.2g} mm wall; a rib at its root under "
                                    f"{RIB_SHARE:g} of the wall ({rib:.2g} mm)")}
            item = [{"text": "stays hot longest here", "ref": None, "at": at}]
            if ratio >= VOID_RATIO:
                summary = (f"A section at {at} mm stays hot {ratio:.2g} times as long as the nominal {nominal:.2g} mm "
                           f"wall (as a wall about {thick:.2g} mm thick would), {spot.volume_mm3:.3g} mm³ of it: it "
                           "shrinks after the skin around it has set, so a sink mark or a void inside is likely")
                found.append(finding("error", "sink_void", summary, "a section 1.7 times the wall or more cools three times "
                                     "as long; the plastic there shrinks after the skin has set and pulls it in, or "
                                     "tears a void inside", item, measured=measured, fix=fix))
            else:
                share = _rib_share(ratio)
                rib = (f"; at a rib's root that is a rib about {share:.2g} of the wall, over the {RIB_SHARE:g} moulders "
                       "keep ribs under" if share <= 1.0 else "")
                summary = (f"A section at {at} mm stays hot {ratio:.2g} times as long as the nominal {nominal:.2g} mm "
                           f"wall (as a wall about {thick:.2g} mm thick would): a sink mark is likely opposite it{rib}")
                found.append(finding("warning", "sink_risk", summary, "a section thicker than the wall around it stays "
                                     "hot after the wall has set and shrinks into it", item, measured=measured, fix=fix))
        if found:
            return found
        times, reference = s["sink_times"], s["sink_nominal_s"]
        worst = float(times.max()) / reference if reference > 0 else 1.0
        at = xyz(nodes[int(times.argmax())])
        return [finding("info", "no_sink", f"No section stays hot more than {SINK_RATIO:g} times as long as the nominal "
                        f"{nominal:.2g} mm wall (the last to cool, at {at} mm, {worst:.2g} times): no sink marks or "
                        "voids from thick sections", f"a rib of {RIB_SHARE:g} of the wall leaves a root that stays hot "
                        f"about {SINK_RATIO:g} times as long",
                        [{"text": "the last to cool", "ref": None, "at": at}],
                        measured={"quantity": "stays hot, against the nominal wall", "value": round(worst, 4),
                                  "limit": SINK_RATIO, "units": "×",
                                  "pass_when": "below"})]

    def _walls(self, ctx: SolveContext, result: AnalysisResult, inputs: MoldingInputs) -> list[dict]:
        walls = result.scalars["walls"]
        low, high = inputs.resin.wall_mm
        name = inputs.resin.name
        found = []
        thin_ref, thick_ref = self._where(ctx, walls.thinnest_row), self._where(ctx, walls.thickest_row)
        thin_item = [{"text": f"a {walls.thinnest_mm:.2g} mm wall", "ref": thin_ref, "at": walls.thinnest_at}]
        thick_item = [{"text": f"a {walls.thickest_mm:.2g} mm wall", "ref": thick_ref, "at": walls.thickest_at}]
        thin = {"quantity": "thinnest wall", "value": round(walls.thinnest_mm, 4), "limit": low, "units": "mm",
                "pass_when": "above"}
        thick = {"quantity": "thickest section", "value": round(walls.thickest_mm, 4), "limit": high, "units": "mm",
                 "pass_when": "below"}
        where_thin = [thin_ref] if thin_ref else [walls.thinnest_at]
        where_thick = [thick_ref] if thick_ref else [walls.thickest_at]
        if walls.thinnest_mm < low:
            found.append(finding("warning", "thin_wall", f"The thinnest wall, {walls.thinnest_mm:.2g} mm at "
                                 f"{walls.thinnest_at} mm, is under the {low:g} mm {name} is recommended down to: it may "
                                 "freeze before it fills (a short shot)", "the design guides' wall range for the resin; "
                                 "the cavity here starts full, so this run cannot see the fill itself", thin_item,
                                 measured=thin, fix={"action": "thicken", "where": where_thin,
                                                     "params": {"thickness_mm": low},
                                                     "summary": f"Thicken it to {low:g} mm, or gate closer to it"}))
        else:
            found.append(finding("info", "thinnest_wall", f"The thinnest wall, {walls.thinnest_mm:.2g} mm, is within "
                                 f"the {low:g}-{high:g} mm recommended for {name}", "each face's wall measured along its "
                                 "inward normal, and across where that runs along the wall", thin_item, measured=thin))
        if walls.thickest_mm > high:
            found.append(finding("warning", "thick_wall", f"The thickest section, {walls.thickest_mm:.2g} mm at "
                                 f"{walls.thickest_at} mm, is over the {high:g} mm {name} is recommended up to: it "
                                 "lengthens the cycle and sinks or voids as it shrinks", "the design guides' wall range "
                                 "for the resin", thick_item, measured=thick,
                                 fix={"action": "thin", "where": where_thick, "params": {"thickness_mm": high},
                                      "summary": f"Core it out to {high:g} mm or less, keeping the wall even"}))
        else:
            found.append(finding("info", "thickest_wall", f"The thickest section, {walls.thickest_mm:.2g} mm, is "
                                 f"within the {high:g} mm {name} is recommended up to", "the design guides' wall range "
                                 "for the resin", thick_item, measured=thick))
        return found

    def _warp(self, result: AnalysisResult, inputs: MoldingInputs) -> dict:
        import numpy as np

        s = result.scalars
        magnitude = np.linalg.norm(result.fields["warp"], axis=1)
        top = int(magnitude.argmax())
        warp = float(magnitude[top])
        at = xyz(result.dof_locations[top])
        held = [xyz(result.dof_locations[vertex]) for vertex, _ in s["warp"].held]
        late = xyz(result.dof_locations[int(result.fields["ejection_time"].argmax())])
        spread = (f"shrinkage {float(result.fields['shrinkage'].min()):.2g}-{float(result.fields['shrinkage'].max()):.2g} "
                  f"% (mean {100 * s['mean_shrinkage']:.2g} %, which the cavity is cut oversize for)")
        item = [{"text": "warps most here", "ref": None, "at": at}]
        how = (f"an estimate from cadgen's own shrinkage model, not a published law; held 3-2-1 at {held[0]}, {held[1]} "
               f"and {held[2]} mm; {spread}")
        tolerance = inputs.warp_tolerance_mm
        if tolerance is None:
            return finding("info", "warp", f"Warps about {warp:.3g} mm at most (an estimate), at {at} mm, held 3-2-1 at "
                           "three corners; give warp_tolerance_mm to judge it", how, item)
        measured = {"quantity": "warp (an estimate)", "value": round(warp, 6), "limit": tolerance, "units": "mm",
                    "pass_when": "below"}
        if warp > tolerance:
            return finding("error", "warp_over_tolerance", f"Warps about {warp:.3g} mm at {at} mm (an estimate), over "
                           f"the {tolerance:g} mm tolerance", how + "; the region that stays hot longest shrinks most and pulls the part "
                           "toward it", item, measured=measured,
                           fix={"action": "thin", "where": [late],
                                "params": {"thickness_mm": round(s["walls"].nominal_mm, 3)},
                                "summary": f"Even the walls: thin the section that cools last toward the nominal "
                                           f"{s['walls'].nominal_mm:.2g} mm wall, or choose a resin that shrinks less"})
        return finding("info", "warp_within_tolerance", f"Warps about {warp:.3g} mm at most (an estimate), within the "
                       f"{tolerance:g} mm tolerance", how, item, measured=measured)

    def _window(self, inputs: MoldingInputs) -> list[dict]:
        """The melt and the mould each inside the resin's processing window: a check each, measured against the bound
        it is nearer."""
        resin = inputs.resin
        found = []
        for word, kind, value, (low, high), key in (
            ("melt", "melt_window", inputs.melt_C, resin.melt_range, "melt_temperature_C"),
            ("mould", "mold_window", inputs.mold_C, resin.mold_range, "mold_temperature_C"),
        ):
            upper = value > 0.5 * (low + high)
            measured = {"quantity": f"{word} temperature", "value": round(value, 4), "limit": high if upper else low,
                        "units": "°C", "pass_when": "below" if upper else "above"}
            if low <= value <= high:
                found.append(finding("info", kind, f"The {word} at {value:g} °C is within {resin.name}'s "
                                     f"{low:g}-{high:g} °C", "a processing guide's window for the resin; the grade's own "
                                     "datasheet overrides it", measured=measured))
                continue
            middle = round(0.5 * (low + high), 1)
            found.append(finding("warning", kind.replace("window", "outside_window"), f"The {word} at {value:g} °C is "
                                 f"outside {resin.name}'s {low:g}-{high:g} °C", "a processing guide's window for the "
                                 "resin; the grade's own datasheet overrides it", measured=measured,
                                 fix={"action": "change_process", "where": [], "params": {key: middle},
                                      "summary": f"Set the {word} to about {middle:g} °C, or confirm the grade's own "
                                                 "window"}))
        return found

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: MoldingInputs, check_results: list[dict]) -> dict:
        import numpy as np

        s = result.scalars
        run, walls, hand, warped = s["run"], s["walls"], s["hand"], s["warp"]
        eject = result.fields["ejection_time"]
        last = int(eject.argmax())
        magnitude = np.linalg.norm(result.fields["warp"], axis=1)
        top = int(magnitude.argmax())
        summary = {
            "cooling_time_s": round(float(eject.max()), 6),
            "last_to_cool_at_mm": xyz(result.dof_locations[last]),
            "mean_ejectable_s": round(s["mean_eject_s"], 6) if s["mean_eject_s"] is not None else None,
            "ejectable": bool(run.solid),
            "end_s": round(run.end_s, 6),
            "resin": inputs.resin.name,
            "melt_temperature_C": round(inputs.melt_C, 4),
            "mold_temperature_C": round(inputs.mold_C, 4),
            "ejection_temperature_C": round(inputs.eject_C, 4),
            "h_W_m2K": inputs.h,
            "volume_mm3": round(s["volume_mm3"], 4),
            "mass_g": round(s["mass_g"], 4),
            "hand_check": {key: (round(value, 6) if isinstance(value, float) else value) for key, value in hand.items()},
            "nominal_wall_mm": round(walls.nominal_mm, 4),
            "thinnest_wall_mm": round(walls.thinnest_mm, 4),
            "thickest_wall_mm": round(walls.thickest_mm, 4),
            "wall_range_mm": list(inputs.resin.wall_mm),
            "nominal_wall_cools_s": round(walls.nominal_s, 6),
            "hot_spots": [{"at_mm": xyz(result.dof_locations[spot.peak]), "ejectable_at_s": round(spot.time_s, 6),
                           "times_nominal": round(spot.ratio, 4), "volume_mm3": round(spot.volume_mm3, 4)}
                          for spot in s["spots"]],
            "max_warp_mm": round(float(magnitude[top]), 6),
            "max_warp_at_mm": xyz(result.dof_locations[top]),
            "warp_tolerance_mm": inputs.warp_tolerance_mm,
            "held_at_mm": [{"at_mm": xyz(result.dof_locations[vertex]), "axes": "".join("xyz"[a] for a in axes)}
                           for vertex, axes in warped.held],
            "hold_reaction_share": round(warped.reaction_share, 9),
            "shrinkage_percent": [round(float(result.fields["shrinkage"].min()), 4),
                                  round(float(result.fields["shrinkage"].max()), 4)],
            "mean_shrinkage_percent": round(100 * s["mean_shrinkage"], 4),
            "heat_to_mould_J": round(run.heat_out / 1000.0, 6),
            "energy_balance": round(abs((run.energy_start - run.energy_end) - run.heat_out)
                                    / max(abs(run.energy_start - run.energy_end), 1e-12), 9),
            "steps": run.steps,
            "frames": len(run.frames),
            "checks": check_results,
        }
        if run.stopped_at is not None:
            summary["stopped_at_s"] = round(run.stopped_at, 9)
        return summary

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        fields, frames = result.fields, result.frame_fields

        def span(values) -> tuple[float, float]:
            return float(values.min()), float(values.max())

        return {
            "ejection_time": span(fields["ejection_time"]),
            "temperature": (min(float(t.min()) for t in frames["temperature"]), max(float(t.max()) for t in frames["temperature"])),
            "cooling_rate": span(fields["cooling_rate"]),
            "shrinkage": span(fields["shrinkage"]),
            "warp": (0.0, summary["max_warp_mm"]),
        }

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: MoldingInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = {
            # The viewer's "Made of" reads the material's name: the resin is the moulding's material.
            "material": {"name": inputs.resin.name},
            "resin": inputs.resin.as_dict(),
            "melt_temperature_C": inputs.melt_C,
            "mold_temperature_C": inputs.mold_C,
            "ejection_temperature_C": inputs.eject_C,
            "h_W_m2K": inputs.h,
        }
        if inputs.warp_tolerance_mm is not None:
            echo["warp_tolerance_mm"] = inputs.warp_tolerance_mm
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        hand = summary["hand_check"]
        lines = [
            f"ejectable in {time_words(summary['cooling_time_s'])}; the last to cool at {summary['last_to_cool_at_mm']} mm",
            f"{summary['resin']} at {summary['melt_temperature_C']:g} °C into a mould at {summary['mold_temperature_C']:g} "
            f"°C (h = {summary['h_W_m2K']:g} W/(m² K)), ejected below {summary['ejection_temperature_C']:g} °C",
            f"plate formula for the thickest wall ({hand['wall_mm']:g} mm): {time_words(hand['mean_s'])} to its mean, "
            f"{time_words(hand['best_s'])} to its middle with the mould's h",
            f"walls {summary['thinnest_wall_mm']:g} to {summary['thickest_wall_mm']:g} mm (nominal "
            f"{summary['nominal_wall_mm']:g} mm); {len(summary['hot_spots'])} hot spot"
            f"{'s' if len(summary['hot_spots']) != 1 else ''}; warp about {summary['max_warp_mm']:.3g} mm (an estimate)",
        ]
        return lines


# -- the pieces solve() reads ------------------------------------------------------------------------


@dataclass
class Walls:
    """The part's walls as the surface measures them, and when each is ejectable."""

    #: The area-weighted median wall, mm, and when it is ejectable through, s; and the latest its sections are (their
    #: :data:`NOMINAL_LATE` quantile), what a sink is judged against.
    nominal_mm: float
    nominal_s: float
    nominal_late_s: float
    thinnest_mm: float
    #: When the thinnest walls (within a tenth of it) are ejectable through, s.
    thinnest_s: float
    thinnest_row: int
    thinnest_at: list
    thickest_mm: float
    thickest_row: int
    thickest_at: list


@dataclass(frozen=True)
class HotRegion:
    peak: int
    time_s: float
    ratio: float
    volume_mm3: float


def _tet_volumes(space):
    import numpy as np

    points, tets = space.mesh.p, space.mesh.t
    corners = points[:, tets]
    edges = corners[:, 1:, :] - corners[:, :1, :]
    return np.abs(np.linalg.det(np.moveaxis(edges, -1, 0))) / 6.0


def _surface_samples(space):
    """Points spread over every surface triangle (its corners, edge middles, centroid and three more inside), for the
    distance from a point to the surface."""
    import numpy as np

    triangles = np.asarray(space.boundary_quadratic)[:, :3]
    corners = space.dof_locations[triangles]                         # (B, 3, 3)
    weights = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0.5, 0.5, 0], [0, 0.5, 0.5], [0.5, 0, 0.5],
                        [1 / 3, 1 / 3, 1 / 3], [2 / 3, 1 / 6, 1 / 6], [1 / 6, 2 / 3, 1 / 6], [1 / 6, 1 / 6, 2 / 3]])
    return np.einsum("wk,bkd->bwd", weights, corners).reshape(-1, 3)


def _walls(space, eject) -> Walls:
    """Each surface triangle's wall: its section along the inward normal (:func:`solidification.sections`) where that
    crosses a wall, its middle at least :data:`WALL_RAY` of the section from every surface. A section that runs along a
    wall instead (from a plate's edge face, or a rib's top, or a triangle at a wall's very edge) measures no wall and is
    left out. The nominal wall is the walls' area-weighted median, the thinnest their low end; the thickest is the
    widest ball that fits at a section's middle (a boss as tall as it is wide is as thick as it is wide)."""
    import numpy as np
    from scipy.spatial import cKDTree

    from cadgen._internal.manufacturing.processes import solidification

    cut = solidification.sections(space, eject)
    rows = solidification.boundary_facet_rows(space)
    tree = cKDTree(_surface_samples(space))
    across, _ = tree.query(cut.middle)
    crossing = cut.measured & (across >= WALL_RAY * cut.thickness)
    wall = np.where(crossing, cut.thickness, np.nan)
    ball = np.where(crossing, np.minimum(cut.thickness, 2.0 * across), np.nan)
    facets = space.mesh.facets[:, space.mesh.boundary_facets()].T
    corners = space.dof_locations[facets]
    area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    good = np.isfinite(wall) & (wall > 0)
    if not good.any():
        raise ValueError("molding: no wall of the part could be measured")
    index = np.flatnonzero(good)

    def quantile(values, share: float) -> int:
        """The triangle at which the area of the walls sorted by ``values`` reaches ``share`` of the surface's."""
        order = index[np.argsort(values[index], kind="stable")]
        cumulative = np.cumsum(area[order])
        return int(order[min(np.searchsorted(cumulative, share * cumulative[-1]), len(order) - 1)])

    def median(values) -> float:
        return float(values[quantile(values, 0.5)])

    nominal = median(wall)
    near_nominal = index[np.abs(wall[index] - nominal) <= 0.1 * nominal]
    order = near_nominal[np.argsort(cut.freeze_s[near_nominal], kind="stable")]
    cumulative = np.cumsum(area[order])
    late = float(cut.freeze_s[order[min(np.searchsorted(cumulative, NOMINAL_LATE * cumulative[-1]), len(order) - 1)]])

    # The thinnest and the thickest walls hold at least WALL_AREA of the surface: one sliver of a ray is not a wall.
    # The thinnest wall holds at least WALL_AREA of the surface (one sliver of a ray is not a wall); the widest ball is
    # never a sliver's, so the thickest is the largest.
    thin, thick = quantile(wall, WALL_AREA), int(index[np.argmax(ball[index])])
    near_thin = index[wall[index] <= 1.1 * wall[thin]]
    return Walls(
        nominal_mm=nominal, nominal_s=median(cut.freeze_s), nominal_late_s=late, thinnest_mm=float(wall[thin]),
        thinnest_s=float(np.median(cut.freeze_s[near_thin])), thinnest_row=int(rows[thin]),
        thinnest_at=xyz(cut.middle[thin]), thickest_mm=float(ball[thick]), thickest_row=int(rows[thick]),
        thickest_at=xyz(cut.middle[thick]),
    )


def _hand(resin, inputs: MoldingInputs, wall_mm: float) -> dict:
    """The plate formula for the thickest wall: to its mean and its middle with the mould face at the mould
    temperature (the handbook's), and to its middle through the mould's h with any crystallisation heat folded into
    the heat capacity (the best hand estimate, which the march starts from)."""
    from cadgen._internal.manufacturing.processes.resins import diffusivity, plate_cooling

    alpha = diffusivity(resin)
    temperatures = (inputs.melt_C, inputs.mold_C, inputs.eject_C)
    released = 0.0
    if resin.crystallises is not None:
        end, onset = resin.crystallises
        released = resin.latent_heat * min(max((onset - inputs.eject_C) / (onset - end), 0.0), 1.0)
    apparent = diffusivity(resin, latent=released, span_C=inputs.melt_C - inputs.eject_C)
    best = plate_cooling(wall_mm, apparent, *temperatures, mean=False, h=inputs.h, k=resin.conductivity)
    return {
        "rule": "s^2 / (pi^2 alpha) ln(C (T_melt - T_mold) / (T_eject - T_mold))",
        "wall_mm": wall_mm,
        "alpha_mm2_s": alpha,
        "mean_s": plate_cooling(wall_mm, alpha, *temperatures, mean=True),
        "centre_s": plate_cooling(wall_mm, alpha, *temperatures, mean=False),
        "apparent_alpha_mm2_s": apparent,
        # Where the one-term series has no answer (the ejection temperature close to the melt's), the wall's own
        # diffusion time sets the march's first step and its patience.
        "best_s": best if best > 0 else wall_mm ** 2 / (math.pi ** 2 * alpha),
    }


def _sink_C(resin, inputs: MoldingInputs) -> float | None:
    """The temperature a sink is judged at, when it is not the ejection temperature: where a semi-crystalline resin
    starts to crystallise, when that is above its ejection temperature."""
    if resin.crystallises is None or resin.crystallises[1] <= inputs.eject_C:
        return None
    return float(resin.crystallises[1])


def _hot_regions(eject, graph, volumes, nominal_s: float, least_mm3: float) -> list[HotRegion]:
    """The connected regions of at least ``least_mm3`` that stay hot more than :data:`SINK_RATIO` times as long as the
    nominal wall, latest first, each its latest point, how many times the nominal wall's time, and its volume."""
    import numpy as np
    import scipy.sparse as sparse
    from scipy.sparse.csgraph import connected_components

    if not nominal_s > 0:
        return []
    hot = eject > SINK_RATIO * nominal_s
    if not hot.any():
        return []
    indptr, indices = graph
    n = len(eject)
    adjacency = sparse.csr_matrix((np.ones(len(indices)), indices, indptr), shape=(n, n))
    picked = np.flatnonzero(hot)
    count, labels = connected_components(adjacency[picked][:, picked], directed=False)
    regions = []
    for label in range(count):
        members = picked[labels == label]
        volume = float(volumes[members].sum())
        if volume < least_mm3:
            continue
        peak = int(members[np.argmax(eject[members])])
        regions.append(HotRegion(peak, float(eject[peak]), float(eject[peak]) / nominal_s, volume))
    return sorted(regions, key=lambda region: -region.time_s)


def _crossing(times: list, values: list, level: float) -> float | None:
    """When ``values`` first falls to ``level``, interpolated; ``None`` if it never does."""
    for i in range(1, len(values)):
        if values[i] <= level < values[i - 1]:
            share = (values[i - 1] - level) / (values[i - 1] - values[i])
            return times[i - 1] + share * (times[i] - times[i - 1])
    return None
